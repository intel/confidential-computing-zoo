#!/usr/bin/env python3

# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import argparse
import errno
import json
import os
import pty
import selectors
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from tc_api.docktap.preflight import ensure_docktap_authorization


PROMPT_TEXT = "Enter verification code:"
STARTED_MARKERS = (
    "Proxy listening on:",
    "Docker proxy listening on",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Atomically run Docktap with OOB Sigstore login, replay pulls, and capture logs.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--trucon-url", default="http://127.0.0.1:8001")
    parser.add_argument("--socket-path", default="/var/run/docktap/docker.sock")
    parser.add_argument("--docker-socket-path", default="/var/run/docker.sock")
    parser.add_argument("--image", default="hello-world:latest")
    parser.add_argument("--openclaw-container", default="openclaw-gateway")
    parser.add_argument("--health-port", type=int, default=8002)
    parser.add_argument("--startup-timeout", type=float, default=15.0)
    parser.add_argument("--post-replay-wait", type=float, default=8.0)
    parser.add_argument("--verification-code")
    parser.add_argument("--log-file")
    parser.add_argument("--keep-running", action="store_true")
    parser.add_argument("--skip-openclaw", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def venv_python(root: Path) -> Path:
    return root / "venv" / "bin" / "python"


def timestamped_log_path(root: Path) -> Path:
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return log_dir / f"docktap-oob-atomic-{stamp}.log"


def iter_trucon_pids() -> list[int]:
    pids: list[int] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        cmdline_path = entry / "cmdline"
        try:
            raw = cmdline_path.read_bytes()
        except OSError:
            continue
        cmdline = raw.replace(b"\x00", b" ").decode("utf-8", errors="ignore")
        if "tc_api.trucon.app:app" in cmdline:
            pids.append(int(entry.name))
    return pids


def iter_docktap_pids(socket_path: str) -> list[int]:
    pids: list[int] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        cmdline_path = entry / "cmdline"
        try:
            raw = cmdline_path.read_bytes()
        except OSError:
            continue
        cmdline = raw.replace(b"\x00", b" ").decode("utf-8", errors="ignore")
        if "tc_api.docktap.main" in cmdline and socket_path in cmdline:
            pids.append(int(entry.name))
    return pids


def terminate_existing_docktap(socket_path: str) -> None:
    for pid in iter_docktap_pids(socket_path):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue


def discover_trucon_service_token() -> str:
    env_token = os.environ.get("TRUCON_SERVICE_TOKEN", "").strip()
    if env_token:
        return env_token

    for pid in iter_trucon_pids():
        environ_path = Path("/proc") / str(pid) / "environ"
        try:
            raw = environ_path.read_bytes()
        except OSError:
            continue
        for item in raw.split(b"\x00"):
            if item.startswith(b"TRUCON_SERVICE_TOKEN="):
                token = item.split(b"=", 1)[1].decode("utf-8", errors="ignore").strip()
                if token:
                    return token
    raise RuntimeError(
        "Could not discover TRUCON_SERVICE_TOKEN from the environment or a running TruCon process."
    )


def run_sigstore_oob_login(root: Path, args: argparse.Namespace) -> str:
    master_fd, slave_fd = pty.openpty()
    child = subprocess.Popen(
        [
            str(venv_python(root)),
            "-m",
            "tc_api.cli.client",
            "--base-url",
            args.base_url,
            "--sigstore-login",
            "oob",
            "sigstore-token",
            "--format",
            "json",
        ],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(root / "src")},
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        text=False,
        start_new_session=True,
    )
    os.close(slave_fd)

    selector = selectors.DefaultSelector()
    selector.register(master_fd, selectors.EVENT_READ)
    chunks: list[str] = []
    tail = ""
    code_sent = False

    try:
        while True:
            events = selector.select(timeout=0.1)
            if not events:
                if child.poll() is not None:
                    break
                continue
            for key, _ in events:
                try:
                    data = os.read(key.fd, 4096)
                except OSError as exc:
                    # PTY readers commonly receive EIO once the child closes
                    # the slave end. Treat that as EOF so the completed token
                    # payload can still be parsed.
                    if exc.errno == errno.EIO:
                        data = b""
                    else:
                        raise
                if not data:
                    continue
                text = data.decode("utf-8", errors="replace")
                sys.stdout.write(text)
                sys.stdout.flush()
                chunks.append(text)
                tail = (tail + text)[-8192:]
                if PROMPT_TEXT in tail and not code_sent:
                    verification_code = args.verification_code or input("Verification code: ").strip()
                    if not verification_code:
                        raise RuntimeError("Verification code is required.")
                    os.write(master_fd, (verification_code + "\n").encode("utf-8"))
                    code_sent = True
            if child.poll() is not None:
                break
    finally:
        selector.close()
        os.close(master_fd)

    returncode = child.wait()
    output = "".join(chunks)
    if returncode != 0:
        raise RuntimeError(f"Sigstore OOB login failed with exit code {returncode}.")

    json_start = output.find("{")
    json_end = output.rfind("}")
    if json_start == -1 or json_end == -1 or json_end <= json_start:
        raise RuntimeError("Could not parse identity_token JSON from OOB login output.")
    payload = json.loads(output[json_start : json_end + 1])
    identity_token = str(payload.get("identity_token") or "").strip()
    if not identity_token:
        raise RuntimeError("OOB login completed but no identity_token was returned.")
    return identity_token


class DocktapProcess:
    def __init__(self, root: Path, args: argparse.Namespace, identity_token: str, trucon_token: str, log_path: Path):
        self.root = root
        self.args = args
        self.identity_token = identity_token
        self.trucon_token = trucon_token
        self.log_path = log_path
        self.started = threading.Event()
        self._stop_reader = threading.Event()
        self._reader: Optional[threading.Thread] = None
        self._log_handle = log_path.open("w", encoding="utf-8")
        self.process = self._spawn()

    def _spawn(self) -> subprocess.Popen[str]:
        env = dict(os.environ)
        env.pop("TRUCON_UDS_PATH", None)
        env["PYTHONPATH"] = f"{self.root / 'docktap'}:{self.root / 'src'}"
        env["TRUCON_URL"] = self.args.trucon_url
        env["TRUCON_SERVICE_TOKEN"] = self.trucon_token
        env["DOCKTAP_SIGSTORE_IDENTITY_TOKEN"] = self.identity_token
        env["DOCKTAP_EXPLICIT_SIGSTORE_IDENTITY_MIN_TTL"] = "0"
        env["DOCKTAP_HEALTH_PORT"] = str(self.args.health_port)

        Path(self.args.socket_path).parent.mkdir(parents=True, exist_ok=True)

        argv = [
            str(venv_python(self.root)),
            "-m",
            "tc_api.docktap.main",
            "--socket-path",
            self.args.socket_path,
            "--docker-socket-path",
            self.args.docker_socket_path,
        ]
        if self.args.debug:
            argv.append("--debug")

        process = subprocess.Popen(
            argv,
            cwd=self.root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        self._reader = threading.Thread(target=self._stream_logs, args=(process,), daemon=True)
        self._reader.start()
        return process

    def _stream_logs(self, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            self._log_handle.write(line)
            self._log_handle.flush()
            if any(marker in line for marker in STARTED_MARKERS):
                self.started.set()
        self._stop_reader.set()

    def wait_until_started(self, timeout_seconds: float) -> None:
        if self.started.wait(timeout_seconds):
            return
        if self.process.poll() is not None:
            raise RuntimeError(f"Docktap exited early with exit code {self.process.returncode}. See {self.log_path}.")
        raise RuntimeError(f"Docktap did not report startup within {timeout_seconds} seconds. See {self.log_path}.")

    def stop(self) -> None:
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        if self._reader is not None:
            self._reader.join(timeout=2)
        self._log_handle.close()


def run_command(command: list[str], *, env: Optional[dict[str, str]] = None) -> None:
    completed = subprocess.run(command, env=env, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {' '.join(command)}")


def replay_pulls(root: Path, args: argparse.Namespace) -> None:
    host_env = dict(os.environ)
    host_env["DOCKER_HOST"] = f"unix://{args.socket_path}"
    run_command(["docker", "pull", args.image], env=host_env)

    if args.skip_openclaw:
        return

    run_command(
        [
            "docker",
            "exec",
            args.openclaw_container,
            "sh",
            "-lc",
            f"docker pull {args.image}",
        ]
    )


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = repo_root()
    log_path = Path(args.log_file) if args.log_file else timestamped_log_path(root)

    print(f"[atomic-oob] log file: {log_path}")
    trucon_token = discover_trucon_service_token()
    print("[atomic-oob] discovered live TRUCON_SERVICE_TOKEN")
    terminate_existing_docktap(args.socket_path)
    print("[atomic-oob] cleared any existing Docktap process on the target socket")

    identity_token = run_sigstore_oob_login(root, args)
    print("[atomic-oob] acquired fresh Sigstore identity token")
    readiness = ensure_docktap_authorization(args.base_url, "default", identity_token=identity_token)
    print(
        "[atomic-oob] authorization preflight ready "
        f"via {readiness.get('source')} for {readiness.get('chain_id')}"
    )

    docktap = DocktapProcess(root, args, identity_token, trucon_token, log_path)
    try:
        docktap.wait_until_started(args.startup_timeout)
        print("[atomic-oob] docktap is listening; replaying pulls now")
        replay_pulls(root, args)
        print(f"[atomic-oob] pull replay finished; waiting {args.post_replay_wait:.1f}s for commit logs")
        time.sleep(args.post_replay_wait)
        print(f"[atomic-oob] done; logs captured in {log_path}")
        if args.keep_running:
            print("[atomic-oob] leaving Docktap running; press Ctrl+C to stop this wrapper")
            while True:
                time.sleep(1)
        return 0
    finally:
        if not args.keep_running:
            docktap.stop()


if __name__ == "__main__":
    raise SystemExit(main())