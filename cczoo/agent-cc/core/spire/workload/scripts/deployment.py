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

"""One strict deployment input for a single attested workload instance."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import stat


PROFILE = "nginx-spiffe"
# This deployment manages one instance. Lifecycle commands and rendered service
# definitions share these unit names so cleanup addresses the same processes.
SERVICE_UNITS = {"helper": "argus-helper", "nginx": "argus-nginx", "authz": "argus-authz",
                 "agent": "argus-workload-agent", "provider": "argus-tdx-provider"}
PACKAGE = Path(__file__).resolve().parents[1]
IDENTITY_KEYS = {"trust_domain", "agent_id", "helper_id", "target_id"}
PATH_KEYS = {"install_dir", "config_dir", "records_dir", "spire_bin_dir", "run_name"}
WORKLOAD_KEYS = {"id", "config_host_path", "data_host_path", "config_path", "data_path",
                 "data_encryption", "data_luks_uuid", "docker_host_proc_path", "docker_host_pid_path",
                 "docker_host_sysfs_dev_block_path", "listen_port", "tls_port", "published_port",
                 "config_env", "environment", "config_json_checks"}
EXISTING_KEYS = {"node_agent_config", "trustee_url", "trustee_ca_path", "trustee_server_name",
                 "ear_public_key_path", "ear_expected_issuer", "ear_expected_profile", "approved",
                 "server_ssh", "server_script", "server_config", "server_unit", "server_socket",
                 "tc_api_url", "tc_api_user_id", "image_id", "image_url", "client_cert", "client_key",
                 "client_bundle", "business_url", "trucon_socket_path"}


def object_keys(value, required, optional=()):
    if not isinstance(value, dict) or required - value.keys() or value.keys() - required - set(optional):
        raise ValueError("missing or unknown deployment configuration fields")


def linux_path(value):
    # These paths also appear in systemd, Docker argv and NGINX. Restrict their
    # alphabet so values cannot introduce directives, expansions or mount args.
    if not isinstance(value, str) or not re.fullmatch(r"/[A-Za-z0-9_./-]+", value) or value.startswith("//") or \
            str(PurePosixPath(value)) != value or ".." in PurePosixPath(value).parts:
        raise ValueError(f"expected a clean absolute Linux path: {value!r}")
    return value


def protected_file(value):
    p = Path(value)
    s = p.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o022:
        raise ValueError(f"{p} must be a root-owned file without group/other write")
    return p


class Deployment:
    def __init__(self, c):
        # Reject unknown fields before generating HCL, systemd or NGINX inputs;
        # typos must not silently weaken a declared identity or launch restriction.
        object_keys(c, EXISTING_KEYS | {"identity", "paths", "workload"},
                    {"approved_policy_artifact", "request_timeout_seconds", "business_headers"})
        for key in EXISTING_KEYS - {"approved"}:
            if not isinstance(c[key], str) or (not c[key] and key != "server_ssh"):
                raise ValueError(f"deployment {key} must be a string")
        # Bind header names to environment-variable names only. Probe credentials
        # are read at execution time and are separate from server startup settings.
        self.business_headers = c.get("business_headers", {})
        if not isinstance(self.business_headers, dict) or len(self.business_headers) > 32:
            raise ValueError("business_headers must map header names to environment variable names")
        headers = set()
        for name, variable in self.business_headers.items():
            if not isinstance(name, str) or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}", name) or \
                    name.lower() in headers or not isinstance(variable, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", variable):
                raise ValueError("invalid or duplicate business header binding")
            headers.add(name.lower())
        object_keys(c["approved"], {"policy_id", "image_config_digest", "config_digest", "executable", "mr_td", "rtmr_0", "rtmr_1", "rtmr2_baseline"})
        linux_path(c["trucon_socket_path"])
        self.request_timeout_seconds = c.get("request_timeout_seconds", 55)
        if type(self.request_timeout_seconds) is not int or not 51 <= self.request_timeout_seconds <= 60:
            raise ValueError("request_timeout_seconds must be an integer in [51,60], above the Trustee 50s budget")
        # Evidence collection and Trustee appraisal are sequential requests.
        # Leave time for the initial local identity and SVID publication too.
        self.startup_timeout_seconds = 2 * self.request_timeout_seconds + 10
        i, p, w = c["identity"], c["paths"], c["workload"]
        object_keys(i, IDENTITY_KEYS, {"client_id", "allowed_client_ids"})
        if ("client_id" in i) == ("allowed_client_ids" in i):
            raise ValueError("configure exactly one of identity.client_id or identity.allowed_client_ids")
        clients = [i["client_id"]] if "client_id" in i else i["allowed_client_ids"]
        if not isinstance(clients, list) or not clients or any(not isinstance(v, str) for v in clients):
            raise ValueError("allowed_client_ids must be a nonempty list of exact SPIFFE IDs")
        if len(set(clients)) != len(clients):
            raise ValueError("allowed_client_ids must not contain duplicate identities")
        self.allowed_client_ids = tuple(clients)
        object_keys(p, PATH_KEYS)
        object_keys(w, WORKLOAD_KEYS)
        if not isinstance(i["trust_domain"], str) or not re.fullmatch(r"[a-z0-9._-]+", i["trust_domain"]):
            raise ValueError("invalid trust_domain")
        prefix = "spiffe://" + i["trust_domain"]
        ids = [i[k] for k in ("agent_id", "helper_id", "target_id")] + clients
        for value in ids:
            if not isinstance(value, str) or not value.startswith(prefix + "/") or \
                    not re.fullmatch(r"(?:/[A-Za-z0-9_.-]+)+", value[len(prefix):]) or \
                    any(part in (".", "..") for part in value[len(prefix):].split("/")):
                raise ValueError("SPIFFE IDs must be unescaped identities in the configured trust domain")
        if len(set(ids)) != len(ids):
            raise ValueError("Agent, Helper, target and client identities must be distinct")
        node = i["agent_id"].removeprefix(prefix + "/spire/agent/argus_tdx/")
        if not i["agent_id"].startswith(prefix + "/spire/agent/argus_tdx/") or \
                not re.fullmatch(r"[A-Za-z0-9_.-]+", node) or not node.strip("."):
            raise ValueError("invalid argus_tdx Agent identity")
        if not isinstance(w["id"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", w["id"]):
            raise ValueError("invalid workload id")
        for key in ("listen_port", "tls_port", "published_port"):
            if type(w[key]) is not int or not 1 <= w[key] <= 65535:
                raise ValueError(f"invalid workload {key}")
        if w["listen_port"] == w["tls_port"]:
            raise ValueError("business and TLS listener ports must differ")
        for key in ("config_host_path", "data_host_path", "config_path", "data_path",
                    "docker_host_proc_path", "docker_host_pid_path", "docker_host_sysfs_dev_block_path"):
            linux_path(w[key])
        if w["data_encryption"] != "luks-dm-crypt" or not isinstance(w["data_luks_uuid"], str) or \
                not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", w["data_luks_uuid"]):
            raise ValueError("workload data must declare its LUKS dm-crypt UUID")
        if not isinstance(w["config_env"], str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", w["config_env"]):
            raise ValueError("invalid configuration environment variable")
        environment = w["environment"]
        if not isinstance(environment, dict) or not 1 <= len(environment) <= 128:
            raise ValueError("environment must be a bounded nonempty map")
        for key, value in environment.items():
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", key) or \
                    not isinstance(value, str) or len(value) > 8192 or any(ch in value for ch in "\r\n\0"):
                raise ValueError("invalid workload environment entry")
        if environment.get(w["config_env"]) != w["config_path"]:
            raise ValueError("configuration environment binding differs from config_path")
        checks = w["config_json_checks"]
        if not isinstance(checks, list) or len(checks) > 64:
            raise ValueError("config_json_checks must be a bounded list")
        for check in checks:
            if not isinstance(check, dict) or set(check) not in ({"pointer", "value"}, {"pointer", "workload_field"}):
                raise ValueError("each configuration check requires a pointer and one expected value")
            pointer = check["pointer"]
            if not isinstance(pointer, str) or len(pointer) > 1024 or (pointer and not pointer.startswith("/")) or re.search(r"~(?![01])", pointer):
                raise ValueError("invalid configuration JSON pointer")
            if "workload_field" in check:
                if not isinstance(check["workload_field"], str) or check["workload_field"] not in {"id", "config_path", "data_path", "listen_port", "tls_port", "published_port"}:
                    raise ValueError("unsupported configuration workload_field")
            elif type(check["value"]) not in (str, int, float, bool, type(None)):
                raise ValueError("configuration check value must be a JSON scalar")
        if PurePosixPath(w["config_path"]).is_relative_to(w["data_path"]) or \
                PurePosixPath(w["config_host_path"]).is_relative_to(w["data_host_path"]):
            raise ValueError("configuration must not be inside the writable data directory")
        executable = c["approved"]["executable"]
        linux_path(executable)
        if any(PurePosixPath(value).is_relative_to("/tmp") for value in (w["config_path"], w["data_path"], executable)) or PurePosixPath(executable).is_relative_to(w["data_path"]):
            raise ValueError("application configuration and executable must remain outside writable mounts")
        for key in PATH_KEYS - {"run_name"}:
            linux_path(p[key])
            if p[key] in ("/etc", "/opt", "/var", "/run", "/usr"):
                raise ValueError("deployment directories must have a dedicated child directory")
        # Keep persistent configuration/records outside runtime cleanup trees.
        # A stop or credential cleanup must not remove the deployment input.
        roots = [PurePosixPath(p[k]) for k in PATH_KEYS - {"run_name"}]
        if any(a.is_relative_to(b) for a in roots for b in roots if a != b) or len(set(roots)) != len(roots):
            raise ValueError("deployment directories must not overlap")
        if not isinstance(p["run_name"], str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,40}", p["run_name"]):
            raise ValueError("run_name must be a short lowercase systemd directory prefix")
        runtime_roots = [PurePosixPath("/run") / (p["run_name"] + suffix) for suffix in
                         ("", "-workload", "-credentials", "-nginx", "-authz", "-spire-agent", "-spire-broker")]
        if any(a.is_relative_to(b) or b.is_relative_to(a) for a in roots for b in runtime_roots):
            raise ValueError("deployment directories must not overlap runtime cleanup directories")
        for key in ("node_agent_config", "trustee_ca_path", "ear_public_key_path", "server_script", "server_config",
                    "server_socket", "client_cert", "client_key", "client_bundle"):
            linux_path(c[key])
        self.c, self.identity, self.workload = c, i, w
        self.install = Path(p["install_dir"])
        self.bin = self.install / "bin"
        self.etc = Path(p["config_dir"])
        self.records = Path(p["records_dir"])
        self.spire = Path(p["spire_bin_dir"])
        self.run_name = p["run_name"]
        self.run = Path("/run") / (self.run_name + "-workload")
        self.credentials = Path("/run") / (self.run_name + "-credentials")
        self.nginx = Path("/run") / (self.run_name + "-nginx")
        self.authz = Path("/run") / (self.run_name + "-authz")
        self.agent = Path("/run") / (self.run_name + "-spire-agent")
        self.broker = Path("/run") / (self.run_name + "-spire-broker")
        self.provider_socket = Path("/run") / self.run_name / "evidence-provider.sock"
        self.target = self.run / "target.json"
        self.environment = self.etc / "environment.json"
        self.units = dict(SERVICE_UNITS)

    def unit(self, role):
        return self.units[role] + ".service"

    def policy_values(self):
        # Render approval from operator input, never from a newly observed target.
        return {**self.c["approved"], "agent_id": self.identity["agent_id"], "workload_id": self.workload["id"],
                "config_path": self.workload["config_path"], "config_env": self.workload["config_env"],
                "listen_port": str(self.workload["listen_port"])}

    def tokens(self):
        return {"BIN": self.bin.as_posix(), "INSTALL": self.install.as_posix(), "ETC": self.etc.as_posix(),
                "SPIRE": self.spire.as_posix(), "RUN_NAME": self.run_name, "TARGET": self.target.as_posix(),
                "CREDENTIALS": self.credentials.as_posix(), "NGINX_RUN": self.nginx.as_posix(),
                "AUTHZ_SOCKET": (self.authz / "authz.sock").as_posix(),
                "PROVIDER_SOCKET": self.provider_socket.as_posix(), "AGENT_SOCKET": (self.agent / "agent.sock").as_posix(),
                "TRUCON_SOCKET": self.c["trucon_socket_path"],
                "STARTUP_TIMEOUT": str(self.startup_timeout_seconds) + "s",
                "BROKER_SOCKET": (self.broker / "broker.sock").as_posix(),
                "AGENT_ID": self.identity["agent_id"], "HELPER_ID": self.identity["helper_id"],
                "TARGET_ID": self.identity["target_id"],
                "CLIENT_ID": self.allowed_client_ids[0],
                "CLIENT_ID_ARGS": " ".join("-client-id " + value for value in self.allowed_client_ids),
                "WORKLOAD_ID": self.workload["id"], "DATA_PATH": self.workload["data_path"],
                "TLS_PORT": str(self.workload["tls_port"]), "LISTEN_PORT": str(self.workload["listen_port"])}

    def render(self, text):
        tokens = self.tokens()
        return re.sub(r"@([A-Z_]+)@", lambda m: tokens[m[1]], text)


def write_file(path, contents, mode=0o600):
    # Replace generated files atomically so readers never see a partial config.
    # A leftover .next file is an error rather than an input to follow or reuse.
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".next")
    # Never follow a leftover temporary symlink.
    import os
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            output.write(contents)
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def render_services(c, package=PACKAGE):
    d = Deployment(c)
    d.etc.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ("helper.conf", "nginx.conf"):
        write_file(d.etc / name, d.render((package / "config" / name).read_text()))
    for path in (package / "systemd").glob("*.service"):
        write_file(d.etc / "systemd" / path.name, d.render(path.read_text()), 0o644)
    write_file(d.bin / "nginx-hook.sh", d.render((package / "scripts/nginx-hook.sh").read_text()), 0o755)
    write_file(d.environment, json.dumps(c, indent=2) + "\n")
    # Only TC API launch settings are exported, never Trustee or client keys.
    launch_config = {"workload": d.workload}
    write_file(d.etc / "tc-api-workload.json", json.dumps(launch_config, indent=2) + "\n")
    return d


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("paths", "units", "render-services"))
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    c = json.loads(protected_file(args.config).read_text())
    d = Deployment(c)
    if args.action == "paths":
        for value in (d.install, d.etc, d.records, d.spire, d.run):
            print(value.as_posix())
    elif args.action == "units":
        print("\n".join(d.units.values()))
    else:
        render_services(c)


if __name__ == "__main__":
    main()
