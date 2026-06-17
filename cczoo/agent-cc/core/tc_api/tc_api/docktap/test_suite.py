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

"""Unified docktap test suite.

This script consolidates distributed test scripts into a single entry point.

Examples:
    python docktap/test_suite.py all
    python docktap/test_suite.py lifecycle
    python docktap/test_suite.py mixed --clients 5
    python docktap/test_suite.py docker-direct --docker-socket /var/run/docker.sock
    python docktap/test_suite.py all --use-running-proxy
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, List, Tuple


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PROXY_SCRIPT = BASE_DIR / "stream_test.py"
DEFAULT_SOCKET_PATH = "/tmp/test-stream.sock"
DEFAULT_DOCKER_SOCKET = "/var/run/docker.sock"


def _print_section(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def wait_for_socket(socket_path: str, timeout: float = 10.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(socket_path):
            return True
        time.sleep(0.2)
    return False


def send_request(socket_path: str, request_text: str, timeout: float = 60.0) -> bytes:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(socket_path)
        sock.sendall(request_text.encode("utf-8"))

        response = b""
        while True:
            try:
                chunk = sock.recv(16384)
                if not chunk:
                    break
                response += chunk
                if b"\r\n\r\n" in response:
                    break
            except socket.timeout:
                break
        return response
    finally:
        sock.close()


def looks_like_http_response(resp: bytes) -> bool:
    return resp.startswith(b"HTTP/") or b"HTTP/1.1" in resp[:32]


class ProxyManager:
    def __init__(self, proxy_script: Path, socket_path: str, use_running_proxy: bool) -> None:
        self.proxy_script = proxy_script
        self.socket_path = socket_path
        self.use_running_proxy = use_running_proxy
        self.proc: subprocess.Popen[str] | None = None

    def __enter__(self) -> "ProxyManager":
        if self.use_running_proxy:
            if not os.path.exists(self.socket_path):
                raise RuntimeError(
                    f"Expected running proxy socket not found: {self.socket_path}"
                )
            return self

        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

        self.proc = subprocess.Popen(
            [sys.executable, str(self.proxy_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(self.proxy_script.parent),
        )

        if not wait_for_socket(self.socket_path, timeout=10):
            self.stop()
            raise RuntimeError("Proxy socket was not created in time")

        return self

    def stop(self) -> None:
        if self.proc is None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=3)
        finally:
            self.proc = None
            if os.path.exists(self.socket_path):
                os.remove(self.socket_path)

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self.use_running_proxy:
            self.stop()


def test_docker_direct(docker_socket: str) -> Tuple[bool, str]:
    _print_section("docker-direct")
    ping_req = b"HEAD /_ping HTTP/1.1\r\nHost: localhost\r\n\r\n"
    pull_req = (
        b"POST /v1.41/images/create?fromImage=busybox HTTP/1.1\r\n"
        b"Host: localhost\r\n\r\n"
    )

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(docker_socket)
        sock.sendall(ping_req)
        ping_resp = sock.recv(4096)
        sock.close()
    except Exception as exc:
        return False, f"docker ping failed: {exc}"

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        # Direct pull API can take longer before first bytes in constrained environments.
        sock.settimeout(20)
        sock.connect(docker_socket)
        sock.sendall(pull_req)
        pull_resp = sock.recv(4096)
        sock.close()
    except Exception as exc:
        return False, f"docker pull-api failed: {exc}"

    ok = looks_like_http_response(ping_resp) and len(pull_resp) > 0
    return ok, "direct docker socket checks complete"


def test_concurrent_same(socket_path: str, image: str = "nginx") -> Tuple[bool, str]:
    _print_section("concurrent-same")
    results: List[bool] = []

    def pull() -> None:
        req = f"POST /v1.41/images/create?fromImage={image} HTTP/1.1\r\nHost: localhost\r\n\r\n"
        resp = send_request(socket_path, req)
        results.append(looks_like_http_response(resp) or len(resp) > 0)

    t1 = threading.Thread(target=pull)
    t2 = threading.Thread(target=pull)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    ok = len(results) == 2 and all(results)
    return ok, f"2 concurrent pulls for {image}"


def test_parallel_images(
    socket_path: str, images: List[str] | None = None
) -> Tuple[bool, str]:
    _print_section("parallel-images")
    if images is None:
        images = ["busybox", "alpine", "redis:alpine"]

    results: List[bool] = []

    def pull(image: str) -> None:
        req = f"POST /v1.41/images/create?fromImage={image} HTTP/1.1\r\nHost: localhost\r\n\r\n"
        resp = send_request(socket_path, req)
        results.append(looks_like_http_response(resp) or len(resp) > 0)

    threads = [threading.Thread(target=pull, args=(img,)) for img in images]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ok = len(results) == len(images) and all(results)
    return ok, f"{len(images)} parallel image pulls"


def test_create_parallel(socket_path: str) -> Tuple[bool, str]:
    _print_section("create-parallel")
    created: List[bool] = []

    def create(name: str) -> None:
        body = json.dumps({"Image": "busybox", "name": name})
        req = (
            f"POST /v1.41/containers/create?name={name} HTTP/1.1\r\n"
            f"Host: localhost\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n\r\n"
            f"{body}"
        )
        resp = send_request(socket_path, req)
        created.append(b"201" in resp or b"HTTP/1.1 2" in resp)

    names = ["suite-parallel-1", "suite-parallel-2"]
    threads = [threading.Thread(target=create, args=(n,)) for n in names]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Cleanup best-effort
    for name in names:
        send_request(socket_path, f"DELETE /v1.41/containers/{name}?force=1 HTTP/1.1\r\nHost: localhost\r\n\r\n")

    ok = len(created) == len(names) and all(created)
    return ok, "parallel container create"


def test_lifecycle(socket_path: str, container: str = "suite-lifecycle") -> Tuple[bool, str]:
    _print_section("lifecycle")

    steps: List[Tuple[str, bytes]] = []

    req = "POST /v1.41/images/create?fromImage=busybox HTTP/1.1\r\nHost: localhost\r\n\r\n"
    steps.append(("pull", send_request(socket_path, req)))
    time.sleep(0.3)

    body = json.dumps({"Image": "busybox", "name": container, "Cmd": ["echo", "hello"]})
    req = (
        f"POST /v1.41/containers/create?name={container} HTTP/1.1\r\n"
        f"Host: localhost\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n\r\n"
        f"{body}"
    )
    steps.append(("create", send_request(socket_path, req)))

    req = f"POST /v1.41/containers/{container}/start HTTP/1.1\r\nHost: localhost\r\n\r\n"
    steps.append(("start", send_request(socket_path, req)))

    req = f"POST /v1.41/containers/{container}/stop HTTP/1.1\r\nHost: localhost\r\n\r\n"
    steps.append(("stop", send_request(socket_path, req)))

    req = f"DELETE /v1.41/containers/{container}?force=1 HTTP/1.1\r\nHost: localhost\r\n\r\n"
    steps.append(("rm", send_request(socket_path, req)))

    ok = all(len(resp) > 0 for _, resp in steps)
    return ok, "container lifecycle flow"


def test_multi_container(
    socket_path: str, count: int = 3, image: str = "nginx"
) -> Tuple[bool, str]:
    _print_section("multi-container")

    names = [f"suite-{image.replace(':', '-')}-{i}" for i in range(count)]

    send_request(
        socket_path,
        f"POST /v1.41/images/create?fromImage={image} HTTP/1.1\r\nHost: localhost\r\n\r\n",
    )
    time.sleep(0.3)

    ok = True
    for name in names:
        body = json.dumps({"Image": image, "name": name})
        req = (
            f"POST /v1.41/containers/create?name={name} HTTP/1.1\r\n"
            f"Host: localhost\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n\r\n"
            f"{body}"
        )
        ok = ok and len(send_request(socket_path, req)) > 0

    for name in names:
        ok = ok and len(send_request(socket_path, f"POST /v1.41/containers/{name}/start HTTP/1.1\r\nHost: localhost\r\n\r\n")) > 0

    for name in names:
        ok = ok and len(send_request(socket_path, f"POST /v1.41/containers/{name}/stop HTTP/1.1\r\nHost: localhost\r\n\r\n")) > 0

    for name in names:
        send_request(socket_path, f"DELETE /v1.41/containers/{name}?force=1 HTTP/1.1\r\nHost: localhost\r\n\r\n")

    return ok, f"{count} containers from {image}"


def test_mixed(socket_path: str, clients: int = 5) -> Tuple[bool, str]:
    _print_section("mixed")
    images = ["nginx", "nginx", "alpine", "redis:alpine", "busybox"]
    if clients < len(images):
        images = images[:clients]
    elif clients > len(images):
        images.extend(["busybox"] * (clients - len(images)))

    results: List[bool] = []

    def pull(image: str) -> None:
        req = f"POST /v1.41/images/create?fromImage={image} HTTP/1.1\r\nHost: localhost\r\n\r\n"
        resp = send_request(socket_path, req, timeout=180)
        results.append(len(resp) > 0)

    threads = [threading.Thread(target=pull, args=(img,)) for img in images]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ok = len(results) == len(images) and all(results)
    return ok, f"{len(images)} mixed concurrent clients"


def test_session_behavior(socket_path: str) -> Tuple[bool, str]:
    _print_section("session")

    # Single-connection ping
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(30)
    try:
        sock.connect(socket_path)
        sock.sendall(b"GET /_ping HTTP/1.1\r\nHost: localhost\r\n\r\n")
        first = sock.recv(4096)
        # Some proxy implementations close after one request.
        second_ok = True
        try:
            sock.sendall(b"GET /v1.41/_ping HTTP/1.1\r\nHost: localhost\r\n\r\n")
            second = sock.recv(4096)
            second_ok = len(second) > 0
        except Exception:
            second_ok = True
    finally:
        sock.close()

    # New-connection ping
    third = send_request(socket_path, "GET /_ping HTTP/1.1\r\nHost: localhost\r\n\r\n")

    ok = len(first) > 0 and second_ok and len(third) > 0
    return ok, "session behavior smoke check"


def run_suite(args: argparse.Namespace) -> int:
    tests: List[Tuple[str, Callable[[], Tuple[bool, str]]]] = []

    if args.mode == "docker-direct":
        tests = [("docker-direct", lambda: test_docker_direct(args.docker_socket))]
    elif args.mode == "session":
        tests = [("session", lambda: test_session_behavior(args.socket_path))]
    elif args.mode == "concurrent-same":
        tests = [("concurrent-same", lambda: test_concurrent_same(args.socket_path, args.same_image))]
    elif args.mode == "parallel-images":
        tests = [("parallel-images", lambda: test_parallel_images(args.socket_path, args.images))]
    elif args.mode == "create-parallel":
        tests = [("create-parallel", lambda: test_create_parallel(args.socket_path))]
    elif args.mode == "lifecycle":
        tests = [("lifecycle", lambda: test_lifecycle(args.socket_path, args.container_name))]
    elif args.mode == "multi-container":
        tests = [("multi-container", lambda: test_multi_container(args.socket_path, args.containers, args.multi_image))]
    elif args.mode == "mixed":
        tests = [("mixed", lambda: test_mixed(args.socket_path, args.clients))]
    else:
        tests = [
            ("docker-direct", lambda: test_docker_direct(args.docker_socket)),
            ("concurrent-same", lambda: test_concurrent_same(args.socket_path, args.same_image)),
            ("parallel-images", lambda: test_parallel_images(args.socket_path, args.images)),
            ("create-parallel", lambda: test_create_parallel(args.socket_path)),
            ("lifecycle", lambda: test_lifecycle(args.socket_path, args.container_name)),
            ("multi-container", lambda: test_multi_container(args.socket_path, args.containers, args.multi_image)),
            ("mixed", lambda: test_mixed(args.socket_path, args.clients)),
            ("session", lambda: test_session_behavior(args.socket_path)),
        ]

    _print_section(f"docktap test suite: {args.mode}")

    require_proxy = any(name != "docker-direct" for name, _ in tests)
    failures: List[Tuple[str, str]] = []

    manager = ProxyManager(args.proxy_script, args.socket_path, args.use_running_proxy)
    if require_proxy:
        manager.__enter__()

    try:
        for name, fn in tests:
            try:
                ok, message = fn()
            except Exception as exc:
                ok, message = False, f"exception: {exc}"

            status = "PASS" if ok else "FAIL"
            print(f"[{status}] {name}: {message}")
            if not ok:
                failures.append((name, message))
    finally:
        if require_proxy:
            manager.__exit__(None, None, None)

    _print_section("summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {len(tests) - len(failures)}")
    print(f"Failed: {len(failures)}")
    if failures:
        for name, msg in failures:
            print(f"- {name}: {msg}")
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified docktap test suite")
    parser.add_argument(
        "mode",
        nargs="?",
        default="all",
        choices=[
            "all",
            "docker-direct",
            "session",
            "concurrent-same",
            "parallel-images",
            "create-parallel",
            "lifecycle",
            "multi-container",
            "mixed",
        ],
    )
    parser.add_argument("--proxy-script", type=Path, default=DEFAULT_PROXY_SCRIPT)
    parser.add_argument("--socket-path", default=DEFAULT_SOCKET_PATH)
    parser.add_argument("--docker-socket", default=DEFAULT_DOCKER_SOCKET)
    parser.add_argument("--use-running-proxy", action="store_true")
    parser.add_argument("--same-image", default="nginx")
    parser.add_argument("--images", nargs="*", default=["busybox", "alpine", "redis:alpine"])
    parser.add_argument("--container-name", default="suite-lifecycle")
    parser.add_argument("--containers", type=int, default=3)
    parser.add_argument("--multi-image", default="nginx")
    parser.add_argument("--clients", type=int, default=5)
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(run_suite(parse_args()))
