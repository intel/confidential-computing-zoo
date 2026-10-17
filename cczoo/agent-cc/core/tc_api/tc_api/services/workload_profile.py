# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Configured workload launch profile for host-managed NGINX/SPIFFE Helper.

Paths come from the operator's TC API environment, never request mount strings.
Existing transparency-log submission still records the launch result.
"""
import json
import os
import re
from pathlib import Path, PurePosixPath
import stat

PROFILE = "nginx-spiffe"
TMPFS = "/tmp:rw,noexec,nosuid,size=256m"
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
WORKLOAD_FIELDS = {"id", "config_path", "data_path", "listen_port", "tls_port", "published_port"}


def application_settings(settings):
    """Validate explicit application inputs without recognizing product names."""
    name, environment = settings["config_env"], settings["environment"]
    if not isinstance(name, str) or not ENV_NAME.fullmatch(name):
        raise ValueError("invalid configuration environment variable")
    if not isinstance(environment, dict) or not 1 <= len(environment) <= 128:
        raise ValueError("environment must be a bounded nonempty map")
    for key, value in environment.items():
        if not isinstance(key, str) or not ENV_NAME.fullmatch(key) or not isinstance(value, str) or \
                len(value) > 8192 or any(c in value for c in "\r\n\0"):
            raise ValueError("invalid workload environment entry")
    if environment.get(name) != settings["config_path"]:
        raise ValueError("configuration environment binding differs from config_path")
    # Application semantics are explicit equality rules, not product-name tests
    # or executable callbacks supplied by a launch request.
    checks = settings["config_json_checks"]
    if not isinstance(checks, list) or len(checks) > 64:
        raise ValueError("config_json_checks must be a bounded list")
    for check in checks:
        if not isinstance(check, dict) or set(check) not in ({"pointer", "value"}, {"pointer", "workload_field"}):
            raise ValueError("each configuration check requires a pointer and one expected value")
        pointer = check["pointer"]
        if not isinstance(pointer, str) or len(pointer) > 1024 or (pointer and not pointer.startswith("/")) or re.search(r"~(?![01])", pointer):
            raise ValueError("invalid configuration JSON pointer")
        if "workload_field" in check:
            if not isinstance(check["workload_field"], str) or check["workload_field"] not in WORKLOAD_FIELDS:
                raise ValueError("unsupported configuration workload_field")
        elif type(check["value"]) not in (str, int, float, bool, type(None)):
            raise ValueError("configuration check value must be a JSON scalar")


def check_application_config(settings):
    config = Path(settings["config_host_path"])
    if not config.is_file() or config.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("workload configuration is missing or too large")
    checks = settings["config_json_checks"]
    if not checks:
        return  # Non-JSON configurations remain covered by the approved digest.
    data = json.loads(config.read_text(encoding="utf-8"))
    for check in checks:
        value = data
        for token in check["pointer"].split("/")[1:]:
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(value, dict) and token in value:
                value = value[token]
            elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", token) and len(token) <= 10 and int(token) < len(value):
                value = value[int(token)]
            else:
                raise ValueError("configuration JSON pointer does not resolve")
        expected = settings[check["workload_field"]] if "workload_field" in check else check["value"]
        # Python considers True == 1; require the JSON value's type as well.
        if type(value) is not type(expected) or value != expected:
            raise ValueError("workload configuration does not satisfy a configured JSON check")

def profile_settings(metadata, workload_id):
    # Request metadata only selects this profile. Paths, mounts and environment
    # come from the protected operator-owned file, never from request overrides.
    name = (metadata or {}).get("workload_attestation_profile")
    if name is None:
        return None
    if name != PROFILE:
        raise ValueError("unsupported workload attestation profile")
    value = os.environ.get("ARGUS_WORKLOAD_CONFIG", "")
    if not value.startswith("/"):
        raise ValueError("ARGUS_WORKLOAD_CONFIG must name the generated absolute configuration path")
    source = Path(value)
    info = source.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_size > 65536:
        raise ValueError("workload configuration must be a protected root-owned file")
    deployment = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(deployment, dict) or set(deployment) != {"workload"}:
        raise ValueError("invalid workload launch configuration fields")
    settings = deployment["workload"]
    keys = {"id", "config_host_path", "data_host_path", "config_path", "data_path", "listen_port", "tls_port", "published_port",
            "config_env", "environment", "config_json_checks"}
    if not isinstance(settings, dict) or set(settings) != keys or settings["id"] != workload_id:
        raise ValueError("workload configuration fields or workload ID mismatch")
    for key in ("config_host_path", "data_host_path", "config_path", "data_path"):
        value = settings[key]
        if not isinstance(value, str) or not re.fullmatch(r"/[A-Za-z0-9_./-]+", value) or value.startswith("//") or str(PurePosixPath(value)) != value or ".." in PurePosixPath(value).parts:
            raise ValueError("workload paths must be clean absolute Linux paths")
    if PurePosixPath(settings["config_path"]).is_relative_to(settings["data_path"]) or PurePosixPath(settings["config_host_path"]).is_relative_to(settings["data_host_path"]):
        raise ValueError("configuration must not be inside the writable data directory")
    if any(PurePosixPath(settings[key]).is_relative_to("/tmp") for key in ("config_path", "data_path")):
        raise ValueError("application mounts must remain outside temporary storage")
    for key in ("listen_port", "tls_port", "published_port"):
        if type(settings[key]) is not int or not 1 <= settings[key] <= 65535:
            raise ValueError("invalid workload port")
    if settings["listen_port"] == settings["tls_port"]:
        raise ValueError("business and TLS listener ports must differ")
    application_settings(settings)
    check_application_config(settings)
    if not Path(settings["data_host_path"]).is_dir():
        raise ValueError("workload data directory is missing")
    return settings

def launch_environment(settings):
    return dict(settings["environment"])

def security_projection(settings, launch_id, workload_id):
    # Record environment names here; launch.py adds a digest of their values.
    # Plaintext environment values must not be copied into transparency entries.
    mounts = [f"{settings['config_host_path']}:{settings['config_path']}:ro", f"{settings['data_host_path']}:{settings['data_path']}"]
    return {"launch_id": launch_id, "workload_id": workload_id, "privileged": False,
            "network_mode": "bridge", "mounts": mounts,
            "devices": [], "capabilities": [], "read_only_rootfs": True,
            "tmpfs": [TMPFS],
            "published_ports": [f"{settings['published_port']}:{settings['tls_port']}"], "attestation_profile": PROFILE,
            "launch_env_keys": sorted(launch_environment(settings))}

def docker_command(binary, settings):
    # Quote generation stays in the guest Provider. The application receives
    # only its approved config/data mounts, with no attestation device required.
    command = [
        binary, "run", "-d", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--network=bridge",
        f"--publish={settings['published_port']}:{settings['tls_port']}",
        "--mount", f"type=bind,source={settings['config_host_path']},target={settings['config_path']},readonly",
        "--mount", f"type=bind,source={settings['data_host_path']},target={settings['data_path']}",
        "--tmpfs", TMPFS,
    ]
    return command

def observed_container(container, launch_id, workload_id):
    """Keep actual image content ID separate from legacy log image_digest."""
    image = container.get("Image", "")
    cid = container.get("Id", "")
    labels = container.get("Config", {}).get("Labels") or {}
    state = container.get("State", {})
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image) or not re.fullmatch(r"[0-9a-f]{64}", cid):
        raise ValueError("Docker did not return actual content identifiers")
    if labels.get("io.trucon.launch-id") != launch_id or labels.get("io.trucon.workload-id") != workload_id:
        raise ValueError("container launch labels mismatch")
    if not state.get("Running") or not isinstance(state.get("Pid"), int) or state["Pid"] <= 0:
        raise ValueError("container is not running")
    return {
        "container_ID": cid, "container_Status": state["Status"],
        "launch_id": launch_id, "workload_id": workload_id,
        "runtime_image_config_digest": image,
        "container_init_host_pid": state["Pid"],
        "container_started_at": state["StartedAt"],
        "attestation_profile": PROFILE,
    }
