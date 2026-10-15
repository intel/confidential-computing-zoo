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

"""Reproducible provenance of payload and installed scripts; contains no secrets."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def installed_sources(root):
    return sorted(p for folder in ("scripts", "config", "policy", "systemd")
                  for p in (root / folder).iterdir() if p.is_file()
                  and (p.suffix == ".py" or p.name == "nginx-hook.sh" if folder == "scripts" else True))


def build_inputs(root):
    return sorted((root / "scripts").glob("*.sh"))


def generate(root, output, artifacts):
    def git(*args, at=None):
        return subprocess.check_output(["git", "-C", str(at or root), *args], timeout=30)
    repo = Path(git("rev-parse", "--show-toplevel").decode().strip())
    scope = ["cczoo/agent-cc/core/spire", "cczoo/agent-cc/core/argus", "cczoo/agent-cc/core/tc_api", "cczoo/agent-cc/core/tlog"]
    patch = git("diff", "--binary", "HEAD", "--", *scope, at=repo)
    untracked = git("ls-files", "--others", "--exclude-standard", "-z", "--", *scope, at=repo).decode().split("\0")
    # Hash untracked source too: newly added implementation is absent from git diff.
    extra = {name: sha(repo / name) for name in untracked if name and (repo / name).is_file()
             and not any(part in ("build", "__pycache__", "node_modules") for part in Path(name).parts)}
    # These hashes correlate local source and installed bytes. The manifest is
    # not signed and does not replace Quote verification or upstream trust pins.
    return {"schema_version": 1, "source_revision": git("rev-parse", "HEAD").decode().strip(),
            "tracked_patch_sha256": hashlib.sha256(patch).hexdigest(), "untracked_source_sha256": extra,
            "artifacts": {name: sha(output / name) for name in artifacts},
            "installed_sources": {p.relative_to(root).as_posix(): sha(p) for p in installed_sources(root)},
            "build_inputs": {p.relative_to(root).as_posix(): sha(p) for p in build_inputs(root)}}


def verify(root, output, manifest, artifacts):
    # Require exactly the payload installed by install.sh, including supporting
    # scripts and templates; stale files from another build are not sufficient.
    if manifest.get("schema_version") != 1 or set(manifest.get("artifacts", {})) != set(artifacts):
        raise ValueError("build provenance has incomplete artifact list")
    if manifest["artifacts"] != {name: sha(output / name) for name in artifacts}:
        raise ValueError("build provenance binary checksum mismatch")
    if manifest.get("installed_sources") != {p.relative_to(root).as_posix(): sha(p) for p in installed_sources(root)}:
        raise ValueError("scripts/configuration changed since build; rebuild before installing")
    if manifest.get("build_inputs") != {p.relative_to(root).as_posix(): sha(p) for p in build_inputs(root)}:
        raise ValueError("build/install scripts changed since build; rebuild before installing")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("create", "verify"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("artifacts", nargs="+")
    args = parser.parse_args()
    path = args.output / "build-manifest.json"
    if args.action == "create":
        from workload import write_json
        write_json(path, generate(args.root, args.output, args.artifacts))
    else:
        verify(args.root, args.output, json.loads(path.read_text()), args.artifacts)


if __name__ == "__main__":
    main()
