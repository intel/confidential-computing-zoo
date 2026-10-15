#!/usr/bin/env python3
# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""NGINX publication and cleanup using the same deployment as Helper."""
import argparse
import json
import os
import shutil
from deployment import Deployment, protected_file
from workload import run


def hook(c, action):
    d = Deployment(c)
    nginx = ["nginx", "-c", d.etc / "nginx.conf"]
    if action in ("publish", "exec"):
        # The application binds loopback inside its container network namespace.
        # Enter only that network namespace; binaries and credentials stay on host.
        target = json.loads(run([d.bin / "argus-workload", "-action", "check", "-registration", d.target]))
        namespace = ["nsenter", "--target", target["pid"], "--net"]
    if action == "publish":
        d.nginx.mkdir(parents=True, exist_ok=True, mode=0o755)
        run([*nginx, "-t"])
        active = run(["systemctl", "is-active", d.unit("nginx")], check=False) == "active"
        run(["systemctl", "reload" if active else "start", d.unit("nginx")])
        run(["systemctl", "is-active", "--quiet", d.unit("nginx")])
        # An active unit does not prove reload completion. Require a fresh TLS
        # handshake to present the exact leaf from the just-published generation.
        run([*namespace, d.bin / "spiffe-mtls-probe", "-tls-only", "-url", f"https://127.0.0.1:{d.workload['tls_port']}",
             "-server-id", d.identity["target_id"], "-cert", d.credentials / "current/svid.pem",
             "-key", d.credentials / "current/key.pem", "-bundle", d.credentials / "current/bundle.pem"])
    elif action == "reload":
        run([*nginx, "-t"])
        run([*nginx, "-s", "reload"])
    elif action == "exec":
        argv = [str(v) for v in [*namespace, *nginx, "-g", "daemon off;"]]
        os.execvp(argv[0], argv)
    elif action == "stop":
        run(["systemctl", "stop", d.unit("nginx")])
    elif action == "clear":
        # systemd invokes stop before clear: removing files alone cannot erase
        # certificates/keys held by an already running NGINX process.
        if d.credentials.is_symlink():
            raise ValueError("credential directory must not be a symlink")
        if d.credentials.exists():
            for child in d.credentials.iterdir():
                if child.is_symlink() or child.is_file():
                    child.unlink()
                elif child.name.startswith("generation-"):
                    shutil.rmtree(child)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("publish", "reload", "exec", "stop", "clear"))
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    hook(json.loads(protected_file(args.config).read_text()), args.action)


if __name__ == "__main__":
    main()
