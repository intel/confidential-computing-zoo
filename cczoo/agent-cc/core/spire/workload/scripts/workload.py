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

"""Linux workload authentication deployment and lifecycle."""
import argparse
from deployment import Deployment, PROFILE, SERVICE_UNITS, render_services
import calendar
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import time
import tempfile
import uuid
from launch_state import execute as execute_launch, operation_lock, digest
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, ProxyHandler

PACKAGE = Path(__file__).resolve().parents[1]
UNITS = list(SERVICE_UNITS.values())


def run(argv, timeout=30, check=True):
    r = subprocess.run([str(a) for a in argv], capture_output=True, text=True, timeout=timeout)
    if check and r.returncode:
        raise RuntimeError(f"{Path(argv[0]).name} failed ({r.returncode}): {r.stderr.strip()}")
    return r.stdout.strip()


def write_json(path, value):
    # Recovery decisions depend on these records surviving a crash. Flush both
    # file contents and the directory entry before the caller submits side effects.
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        if sys.platform == "linux":
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        tmp.unlink(missing_ok=True)


def protected_file(path):
    p = Path(path)
    s = p.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o022:
        raise ValueError(f"{p} must be a root-owned file without group/other write")
    return p


def baseline(c):
    a = c["approved"]
    for f in ("image_config_digest", "config_digest"):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", a.get(f, "")):
            raise ValueError(f"missing approved.{f}; use an approved content digest")
    for f in ("mr_td", "rtmr_0", "rtmr_1", "rtmr2_baseline"):
        if not re.fullmatch(r"[0-9a-f]{96}", a.get(f, "")):
            raise ValueError(f"missing approved.{f}")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", a.get("policy_id", "")):
        raise ValueError("invalid approved.policy_id")
    if not a.get("executable", "").startswith("/"):
        raise ValueError("approved.executable is required")
    return a


def render_policy(a):
    text = (PACKAGE / "policy/workload_cpu.rego.tmpl").read_text()
    for k, v in a.items():
        text = text.replace("@" + k.upper() + "@", json.dumps(v))
    if re.search(r"@[A-Z0-9_]+@", text):
        raise ValueError("incomplete workload policy")
    return text


def policy_bytes(c):
    """Default remains strict. An explicit reviewed artifact is byte/hash pinned.

    This does not infer a TCB exception from the policy ID or edit any Rego.
    The operator supplies the exact policy installed on the Trustee server.
    """
    baseline(c)
    artifact = c.get("approved_policy_artifact")
    if artifact is None:
        return render_policy(Deployment(c).policy_values()).encode()
    if (not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}
            or not re.fullmatch(r"[0-9a-f]{64}", artifact.get("sha256", ""))
            or not Path(artifact.get("path", "")).is_absolute()):
        raise ValueError("approved_policy_artifact requires absolute path and explicit SHA-256")
    contents = protected_file(artifact["path"]).read_bytes()
    if not contents or len(contents) > 65536 or hashlib.sha256(contents).hexdigest() != artifact["sha256"]:
        raise ValueError("approved policy artifact is empty, oversized or SHA-256 differs")
    contents.decode("utf-8")
    return contents


def render(c):
    d = Deployment(c)
    a = baseline(c)
    for unit in UNITS:
        if run(["systemctl", "is-active", unit], check=False) in ("active", "activating", "reloading", "deactivating"):
            raise ValueError(f"stop {unit} before applying deployment configuration")
    d.etc.mkdir(parents=True, exist_ok=True, mode=0o700)
    policy = policy_bytes(c)
    (d.etc / (a["policy_id"] + "_cpu.rego")).write_bytes(policy)
    plugin = {
        "evidence_endpoint": "unix://" + d.provider_socket.as_posix(),
        "target_registration_path": d.target.as_posix(),
        "agent_id": d.identity["agent_id"],
        "trustee_endpoint": c["trustee_url"],
        **{k: c[k] for k in ("trustee_ca_path", "trustee_server_name", "ear_public_key_path", "ear_expected_issuer", "ear_expected_profile")},
        "workload_id": d.workload["id"],
        "config_env": d.workload["config_env"],
        **{k: a[k] for k in ("policy_id", "image_config_digest", "config_digest")},
        "request_timeout": f"{d.request_timeout_seconds}s",
    }
    hcl = "\n".join(f"            {k} = {json.dumps(v)}" for k, v in plugin.items())
    overlay = '''agent {
    log_format = "json"
    log_level = "INFO"
    log_file = ""
    socket_path = "@AGENT_SOCKET@"
    experimental {
        broker {
            socket_path = "@BROKER_SOCKET@"
            brokers = [{
                id = "@HELPER_ID@"
                allowed_reference_types = [{ type_url = "type.googleapis.com/spiffe.broker.WorkloadPIDReference" }]
            }]
        }
    }
}
plugins {
    WorkloadAttestor "unix" {
        plugin_data { discover_workload_path = true workload_size_limit = 268435456 }
    }
    WorkloadAttestor "argus_tdx" {
        plugin_cmd = @WORKLOAD_PLUGIN@
        plugin_data {
''' + hcl + '''
        }
    }
}
'''
    overlay = d.render(overlay.replace("@WORKLOAD_PLUGIN@", json.dumps((d.bin / "argus-tdx-workloadattestor").as_posix())))
    (d.etc / "agent-overlay.conf").write_text(overlay)
    protected_file(c["node_agent_config"])
    run([d.bin / "argus-agent-config", "-source", c["node_agent_config"], "-overlay", d.etc / "agent-overlay.conf", "-node-binary", d.bin / "argus-tdx-nodeattestor-agent", "-output", d.etc / "agent.conf", "-trust-domain", d.identity["trust_domain"], "-agent-id", d.identity["agent_id"], "-evidence-socket", d.provider_socket])
    render_services(c, PACKAGE)
    for unit in (d.etc / "systemd").glob("*.service"):
        run(["install", "-m", "0644", unit, Path("/etc/systemd/system") / unit.name])
    run(["systemctl", "daemon-reload"])
    for f in d.etc.glob("*.conf"):
        f.chmod(0o600)
    return {"rendered": str(d.etc), "policy_sha256": hashlib.sha256(policy).hexdigest(),
            "policy_source": "reviewed-artifact" if c.get("approved_policy_artifact") else "strict-template"}


def binary_version(binary):
    # Official SPIRE writes -version to stderr via its CLI UI.
    result = subprocess.run([str(binary), "-version"], capture_output=True, text=True, timeout=10, check=True)
    version = (result.stdout + result.stderr).strip()
    if version != "1.15.3":
        raise ValueError(f"{binary}: expected 1.15.3, got {version}")
    return version


def id_string(value):
    if isinstance(value, str):
        return value
    return "spiffe://" + value.get("trust_domain", value.get("trustDomain", "")) + value.get("path", "")


def selectors(c, identity):
    # The Helper uses local binary selectors to reach the Broker; the target
    # requires the remote-appraisal selectors returned by WorkloadAttestor.
    d = Deployment(c)
    if identity == d.identity["helper_id"]:
        digest = hashlib.sha256((d.bin / "spiffe-helper").read_bytes()).hexdigest()
        return {"unix:uid:0", "unix:path:" + (d.bin / "spiffe-helper").as_posix(), "unix:sha256:" + digest}
    a = baseline(c)
    return {"argus_tdx:verified:true", "argus_tdx:workload_id:" + d.workload["id"],
            "argus_tdx:policy:" + a["policy_id"], "argus_tdx:agent_id:" + d.identity["agent_id"],
            "argus_tdx:image_config_digest:" + a["image_config_digest"],
            "argus_tdx:config_digest:" + a["config_digest"]}


def audit_entries(c, entries, required, identity):
    # Every matching entry must enforce the contract. One permissive alternative
    # could issue the same identity without the intended attestation selectors.
    d = Deployment(c)
    if not entries:
        raise ValueError(f"no Entry for {identity}")
    for e in entries:
        have = {s["type"] + ":" + s["value"] for s in e.get("selectors", [])}
        parent = e.get("parent_id", e.get("parentId", {}))
        sid = e.get("spiffe_id", e.get("spiffeId", {}))
        attr = e.get("additional_attributes", e.get("additionalAttributes", {}))
        prefetch_off = attr.get("disable_x509_svid_prefetch", attr.get("disableX509SvidPrefetch", False))
        if id_string(sid) != identity or id_string(parent) != d.identity["agent_id"] or not required.issubset(have):
            raise ValueError(f"bypass Entry {e.get('id')} for {identity}; review/remove it before starting")
        if e.get("admin") or e.get("downstream") or e.get("store_svid", e.get("storeSvid")):
            raise ValueError(f"unexpected privileges/storage on Entry {e.get('id')}")
        if identity == d.identity["target_id"] and not prefetch_off:
            # The target identity must be obtained on demand through its
            # PID-reference subscription, not prefetched at Agent startup.
            raise ValueError(f"target Entry {e.get('id')} must disable X509 SVID prefetch")


def server_entries(c, identity):
    d = Deployment(c)
    raw = json.loads(run([d.spire / "spire-server", "entry", "show", "-socketPath", c["server_socket"], "-spiffeID", identity, "-output", "json"]))
    return raw.get("entries", [])


def entry_contract(c):
    d = Deployment(c)
    return {"parent_id": d.identity["agent_id"], "selectors": {
        identity: sorted(selectors(c, identity))
        for identity in (d.identity["helper_id"], d.identity["target_id"])}}


def server_check(c, apply=False):
    d = Deployment(c)
    pid = run(["systemctl", "show", c["server_unit"], "--property=MainPID", "--value"])
    if not pid.isdigit() or int(pid) <= 0:
        raise ValueError("SPIRE Server is not running")
    # Read the running executable, not just the version at the intended install path.
    version = binary_version(Path("/proc") / pid / "exe")
    binary_version(d.spire / "spire-server")
    contract = entry_contract(c)
    result = {"server_version": version, "server_pid": int(pid), "entries": {}, "entry_contract": contract}
    for identity in (d.identity["helper_id"], d.identity["target_id"]):
        required = set(contract["selectors"][identity])
        entries = server_entries(c, identity)
        if not entries and apply:
            cmd = [d.spire / "spire-server", "entry", "create", "-socketPath", c["server_socket"],
                   "-parentID", d.identity["agent_id"], "-spiffeID", identity, "-x509SVIDTTL", "300"]
            if identity == d.identity["target_id"]:
                cmd += ["-disableX509SVIDPrefetch"]
            for selector in sorted(required):
                cmd += ["-selector", selector]
            run(cmd)
            entries = server_entries(c, identity)
        audit_entries(c, entries, required, identity)
        result["entries"][identity] = [e["id"] for e in entries]
    return result


def remote_check(c):
    alias = c.get("server_ssh", "")
    if not alias:
        return server_check(c)
    if alias.startswith("-") or not re.fullmatch(r"[A-Za-z0-9_.@-]+", alias):
        raise ValueError("server_ssh must be one configured SSH host alias")
    expected = entry_contract(c)
    command = shlex.join(["python3", c["server_script"], "server-check", "--config", c["server_config"]])
    result = json.loads(run(["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", alias, command]))
    if not isinstance(result, dict) or result.get("entry_contract") != expected:
        raise ValueError("Server Entry contract differs from local deployment identities, baseline or Helper path/binary")
    return result


def direct_trustee(c):
    # This preflight checks direct TLS reachability, route behavior and installed
    # policy bytes. It does not submit evidence or establish a valid appraisal.
    parsed = urlsplit(c["trustee_url"])
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("trustee_url must be a direct HTTPS origin")
    protected_file(c["trustee_ca_path"])
    protected_file(c["ear_public_key_path"])
    # No HTTP(S)_PROXY or TC API relay: raw TCP from this TDVM to Trustee.
    ctx = ssl.create_default_context(cafile=c["trustee_ca_path"])
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    raw = socket.create_connection((parsed.hostname, parsed.port or 443), timeout=10)
    with ctx.wrap_socket(raw, server_hostname=c["trustee_server_name"]) as channel:
        host = parsed.netloc
        channel.sendall(f"POST /attestation HTTP/1.1\r\nHost: {host}\r\nContent-Type: application/json\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{{}}".encode())
        response = http.client.HTTPResponse(channel)
        response.begin()
        if response.status not in (400, 422):
            raise ValueError(f"direct Trustee /attestation schema probe returned HTTP {response.status}; expected 400/422")
    raw = socket.create_connection((parsed.hostname, parsed.port or 443), timeout=10)
    with ctx.wrap_socket(raw, server_hostname=c["trustee_server_name"]) as channel:
        policy_id = baseline(c)["policy_id"]
        channel.sendall(f"GET /policy/{policy_id}_cpu HTTP/1.1\r\nHost: {parsed.netloc}\r\nConnection: close\r\n\r\n".encode())
        response = http.client.HTTPResponse(channel)
        response.begin()
        contents = response.read(65537)
        if response.status != 200 or contents != policy_bytes(c):
            raise ValueError("Trustee workload policy is missing or differs from the rendered approved policy")
    key = run(["openssl", "pkey", "-pubin", "-in", c["ear_public_key_path"], "-text", "-noout"])
    if "prime256v1" not in key and "P-256" not in key:
        raise ValueError("EAR key must be fixed P-256 public key")
    return "HTTPS_AND_ATTESTATION_ROUTE_PASS"


def preflight(c, client_mode="local"):
    d = Deployment(c)
    baseline(c)
    for tool in ("docker", "nsenter", "systemctl", "openssl", "timeout"):
        if not shutil.which(tool):
            raise ValueError(f"missing command: {tool}")
    result = {"agent_binary_version": binary_version(d.spire / "spire-agent"),
              "server": remote_check(c), "trustee_direct": direct_trustee(c)}
    for executable in ("spiffe-helper", "argus-agent-config", "argus-workload", "spiffe-authz", "spiffe-mtls-probe", "argus-tdx-workloadattestor", "argus-spire-evidence-provider"):
        if not os.access(d.bin / executable, os.X_OK):
            raise ValueError(f"missing executable: {d.bin / executable}")
    if run([d.bin / "spiffe-helper", "-version"]) != "argus-broker":
        raise ValueError("expected SPIFFE Helper built with Argus Broker support")
    if not Path("/sys/kernel/config/tsm/report").is_dir():
        raise ValueError("Linux TSM report interface is missing; real TDX is required")
    t = json.loads(run([d.bin / "argus-workload", "-action", "check", "-registration", d.target]))
    for k in ("policy_id", "image_config_digest", "config_digest", "executable"):
        if t[k] != c["approved"][k]:
            raise ValueError(f"registered target differs from approved {k}")
    expected = {"agent_id": d.identity["agent_id"], "workload_id": d.workload["id"],
                "config_path": d.workload["config_path"], "config_env": d.workload["config_env"],
                "listen_port": str(d.workload["listen_port"])}
    if any(t[k] != value for k, value in expected.items()):
        raise ValueError("registered target differs from deployment identity/configuration")
    # Remote client verification keeps the client SVID/key on the client host;
    # every other target binding, version, Entry, Trustee, policy and readiness
    # check remains. Local mode keeps the original strict credential checks.
    if client_mode == "remote":
        result["client_credentials"] = "REMOTE_CLIENT_VERIFICATION"
    elif client_mode == "local":
        for k in ("client_cert", "client_key", "client_bundle"):
            protected_file(c[k])
        result["client_credentials"] = "LOCAL_VERIFICATION"
    else:
        raise ValueError("client_mode must be local or remote")
    # Check existing Agent version too when this stack is already running.
    pid = run(["systemctl", "show", "argus-workload-agent", "--property=MainPID", "--value"], check=False)
    if pid.isdigit() and int(pid) > 0:
        result["running_agent_version"] = binary_version(Path("/proc") / pid / "exe")
    result.update({"target": t, "rekor_gate": "DEFERRED", "periodic_reattestation": "DEFERRED"})
    return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Both the authorization header and launch body contain credentials.
        # Require the configured TC API origin to answer the original request.
        return None


def tc_request(c, route, data=None):
    root = urlsplit(c["tc_api_url"])
    if root.scheme != "https" and not (root.scheme == "http" and root.hostname in ("localhost", "127.0.0.1")):
        raise ValueError("TC API must use HTTPS or local loopback HTTP")
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("TC_API_BEARER_TOKEN") or os.environ.get("TC_API_IDENTITY_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(c["tc_api_url"].rstrip("/") + route, data=None if data is None else json.dumps(data).encode(), headers=headers)
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=30) as response:
        return json.load(response)


def launch(c):
    d = Deployment(c)
    return execute_launch(d, tc_request, write_json)


def resume_launch(c, launch_id=None):
    return execute_launch(Deployment(c), tc_request, write_json, resume=True, launch_id=launch_id)


def runtime_manifest(c):
    """Content correlation, not a new attestation or a signed security receipt."""
    d = Deployment(c)
    result = {"schema_version": 1, "config_sha256": digest(c), "identity": d.identity,
              "workload_id": d.workload["id"], "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "build_integrity": "NOT_AVAILABLE"}
    policy = d.etc / (c["approved"]["policy_id"] + "_cpu.rego")
    if policy.is_file():
        result["policy_sha256"] = hashlib.sha256(protected_file(policy).read_bytes()).hexdigest()
    manifest_path = d.install / "build-manifest.json"
    if manifest_path.is_file():
        manifest_bytes = protected_file(manifest_path).read_bytes()
        manifest = json.loads(manifest_bytes)
        result["build_manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        result["source_revision"] = manifest.get("source_revision")
        result["tracked_patch_sha256"] = manifest.get("tracked_patch_sha256")
        observed = {}
        for name in manifest.get("artifacts", {}):
            relative = Path(name)
            if len(relative.parts) == 2 and relative.parts[0] == "bin":
                path = d.bin / relative.name
            elif len(relative.parts) == 3 and relative.parts[:2] == ("spire-1.15.3", "bin"):
                path = d.spire / relative.name
            else:
                raise ValueError("invalid installed build artifact path")
            observed[name] = hashlib.sha256(protected_file(path).read_bytes()).hexdigest() if path.exists() else None
        result["binaries_sha256"] = observed
        sources = {}
        for name in manifest.get("installed_sources", {}):
            relative = Path(name)
            if len(relative.parts) != 2 or relative.parts[0] not in ("scripts", "config", "policy", "systemd") or relative.name in (".", ".."):
                raise ValueError("invalid installed source path")
            path = d.install / relative
            sources[name] = hashlib.sha256(protected_file(path).read_bytes()).hexdigest() if path.exists() else None
        result["installed_sources_sha256"] = sources
        result["binary_integrity"] = "MATCH" if observed and observed == manifest.get("artifacts") else "MISMATCH"
        result["installed_source_integrity"] = "MATCH" if sources and sources == manifest.get("installed_sources") else "MISMATCH"
        result["build_integrity"] = "MATCH" if manifest.get("schema_version") == 1 and result["binary_integrity"] == result["installed_source_integrity"] == "MATCH" else "MISMATCH"
    for name in ("launch-state", "verify"):
        path = d.records / (name + ".json")
        if path.is_file():
            record = json.loads(protected_file(path).read_text())
            if name == "launch-state":
                result["launch"] = {k: record.get(k) for k in ("run_id", "launch_id", "container_id", "stage", "config_sha256")}
            else:
                result["verification_record_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                result["verification_checked_at"] = record.get("checked_at")
    if d.target.is_file():
        result["registered_target"] = json.loads(protected_file(d.target).read_text())
    return result


def register(c):
    d = Deployment(c)
    info = json.loads(protected_file(d.run / "launch.json").read_text())
    t = json.loads(run([d.bin / "argus-workload", "-action", "register", "-container", info["container"]["container_ID"], "-policy", baseline(c)["policy_id"], "-registration", d.target, "-agent-id", d.identity["agent_id"], "-workload-id", d.workload["id"], "-config", d.workload["config_path"], "-config-env", d.workload["config_env"], "-port", str(d.workload["listen_port"])]))
    if t["launch_id"] != info["launch_id"]:
        (d.run / "target.json").unlink()
        raise ValueError("registered launch differs from TC API response")
    return t


def start(c, client_mode="local"):
    record = preflight(c, client_mode)
    record["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # Do not reuse a socket or Agent data directory owned by a running process.
    for name in ("spire-agent", "argus-spire-evidence-provider"):
        running = run(["pgrep", "-f", "(^|/)" + name + "( |$)"], check=False)
        if running:
            raise ValueError(f"{name} is still running with PID(s) {running}; stop it before start")
    render(c)
    run(["systemctl", "start", Deployment(c).unit("helper")])
    deadline = time.monotonic() + Deployment(c).startup_timeout_seconds + 5
    while time.monotonic() < deadline:
        s = status(c)
        if s["ready"]:
            record.update(s)
            return record
        time.sleep(1)
    run(["systemctl", "stop", Deployment(c).unit("helper")])
    raise TimeoutError("target identity did not become ready; inspect journalctl -u argus-helper -u argus-workload-agent -u argus-tdx-provider")


def status(c):
    # Ready files are local operational state. Require the current systemd
    # invocation, exact target and unexpired credentials so stale files cannot pass.
    d = Deployment(c)
    units = {u: run(["systemctl", "is-active", u], check=False) for u in d.units.values()}
    serial, invocation, reason = None, None, None
    try:
        invocation = run(["systemctl", "show", d.unit("helper"), "--property=InvocationID", "--value"])
        receipt = json.loads(protected_file(d.credentials / "ready").read_text())
        target = json.loads(protected_file(d.target).read_text())
        if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
            raise ValueError("legacy or unsupported readiness")
        if not re.fullmatch(r"[0-9a-f]{32}", invocation) or receipt.get("invocation_id") != invocation:
            raise ValueError("readiness belongs to another Helper invocation")
        if not isinstance(target, dict) or receipt.get("target") != target or \
                target.get("agent_id") != d.identity["agent_id"] or target.get("workload_id") != d.workload["id"]:
            raise ValueError("readiness target differs from registration/deployment")
        if not isinstance(receipt.get("serial"), str) or not re.fullmatch(r"[1-9][0-9]*", receipt["serial"]):
            raise ValueError("invalid readiness serial")
        expiry = datetime.fromisoformat(receipt["expires_at"].replace("Z", "+00:00"))
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise ValueError("readiness credential expired")
        if invocation != run(["systemctl", "show", d.unit("helper"), "--property=InvocationID", "--value"]):
            # Reading the receipt must not span a Helper process restart.
            raise ValueError("Helper restarted during readiness check")
        serial = receipt["serial"]
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        reason = str(error) if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError) else type(error).__name__
    return {"units": units, "ready": all(v == "active" for v in units.values()) and serial is not None,
            "target_serial": serial, "helper_invocation_id": invocation, "readiness_error": reason}


def stop(c):
    d = Deployment(c)
    run(["systemctl", "stop", *d.units.values()])
    (d.run / "target.json").unlink(missing_ok=True)
    if (d.credentials / "ready").exists():
        raise ValueError("readiness was not removed")
    return {"stopped": True, "reregistration_required": True}


def event_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate operational event field")
    return result


def correlated_appraisal(journal, target, serial, invocation, helper_unit, agent_unit):
    # Correlate trusted local operational events, not independently verified
    # Quote/EAR tokens. Invocation and instance fields exclude stale runs;
    # later rotations may refer to the same subscription's accepted appraisal.
    expected = {k: target[k] for k in ("launch_id", "container_id", "pid", "start_time")}
    expected["policy"] = target["policy_id"]
    boot = target["boot_id"].replace("-", "")
    subscribed, appraisal, matched = False, None, None
    for line in journal.splitlines():
        try:
            record = json.loads(line, object_pairs_hook=event_object)
            fields = json.loads(record["MESSAGE"], object_pairs_hook=event_object)
        except (ValueError, TypeError, KeyError):
            continue
        if not isinstance(record, dict) or not isinstance(fields, dict) or \
                fields.get("event_version") != "1" or record.get("_BOOT_ID") != boot:
            continue
        unit = record.get("_SYSTEMD_UNIT")
        helper = unit == helper_unit and record.get("_SYSTEMD_INVOCATION_ID") == invocation
        same_target = all(fields.get(k) == v for k, v in expected.items())
        if helper and fields.get("event") in ("workload.subscription_started", "workload.subscription_ended"):
            subscribed = same_target and fields.get("event") == "workload.subscription_started" and fields.get("subscription_id") == invocation
            appraisal, matched = None, None
        if not subscribed:
            continue
        if unit == agent_unit and fields.get("event") == "workload.ear_accepted" and same_target and \
                isinstance(fields.get("nonce"), str) and re.fullmatch(r"[A-Za-z0-9_-]{43}", fields["nonce"]) and \
                isinstance(fields.get("ear_sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", fields["ear_sha256"]):
            appraisal = fields
        if helper and fields.get("event") == "workload.svid_published" and same_target and \
                fields.get("subscription_id") == invocation and fields.get("serial") == serial:
            matched = appraisal
    if matched is None:
        raise ValueError("missing correlated EAR acceptance/SVID publication log for the current Helper invocation and target")
    return matched


def helper_invocation(d):
    invocation = run(["systemctl", "show", d.unit("helper"), "--property=InvocationID", "--value"])
    if not re.fullmatch(r"[0-9a-f]{32}", invocation):
        raise ValueError("current Helper invocation is unavailable")
    return invocation


def verify(c):
    # Combine a real mTLS/business request with current local event correlation.
    # Log correlation explains the active subscription; it is not EAR verification.
    d = Deployment(c)
    s = status(c)
    if not s["ready"]:
        raise ValueError("workload is not ready")
    invocation = helper_invocation(d)
    target = json.loads(run([d.bin / "argus-workload", "-action", "check", "-registration", d.target]))
    probe = [d.bin / "spiffe-mtls-probe", "-url", c["business_url"], "-cert", c["client_cert"],
             "-key", c["client_key"], "-bundle", c["client_bundle"], "-server-id", d.identity["target_id"]]
    for header, variable in sorted(d.business_headers.items()):
        probe.extend(["-header-env", header + "=" + variable])
    proof = json.loads(run(probe))
    if proof["client_spiffe_id"] not in d.allowed_client_ids or proof["server_serial"] != s["target_serial"]:
        raise ValueError("business call did not use the expected client/current target SVID")
    started = json.loads(protected_file(d.records / "start.json").read_text())["started_at"]
    started_epoch = calendar.timegm(time.strptime(started, "%Y-%m-%dT%H:%M:%SZ"))
    journal = run(["journalctl", "-u", d.unit("provider"), "-u", d.unit("agent"), "-u", d.unit("helper"), "--since", f"@{started_epoch}", "--no-pager", "-o", "json"])
    appraisal = correlated_appraisal(journal, target, proof["server_serial"], invocation, d.unit("helper"), d.unit("agent"))
    if helper_invocation(d) != invocation or status(c) != s:
        raise ValueError("workload changed during verification; retry with the current instance")
    d.records.mkdir(parents=True, exist_ok=True, mode=0o700)
    (d.records / "last-verify-journal.jsonl").write_text(journal)
    (d.records / "last-verify-journal.jsonl").chmod(0o600)
    return {"target": target, "svid_and_business": proof, "server": remote_check(c), "appraisal": appraisal,
            "helper_invocation_id": invocation, "check_kind": "LOCAL_OPERATIONAL_CHECK",
            "appraisal_log": str(d.records / "last-verify-journal.jsonl")}












def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["render", "preflight", "launch", "resume-launch", "register", "start", "status", "stop", "verify", "manifest", "server-check", "apply-entries"])
    parser.add_argument("--config", required=True)
    parser.add_argument("--launch-id", help="known operation ID; only valid with resume-launch")
    parser.add_argument("--client-mode", choices=("local", "remote"), default="local", help="whether client SVID files are available on this host")
    args = parser.parse_args()
    if sys.platform != "linux" or os.geteuid() != 0:
        raise ValueError("run this lifecycle tool as root on the Linux service host")
    c = json.loads(protected_file(args.config).read_text())
    d = Deployment(c)
    if args.launch_id is not None and args.action != "resume-launch":
        parser.error("--launch-id requires resume-launch")
    if args.client_mode == "remote" and args.action not in ("preflight", "start"):
        parser.error("--client-mode remote is only valid with preflight or start")
    functions = {"render": render, "preflight": lambda c: preflight(c, args.client_mode),
                 "launch": launch, "resume-launch": lambda c: resume_launch(c, args.launch_id),
                 "register": register, "start": lambda c: start(c, args.client_mode),
                 "status": status, "stop": stop, "verify": verify, "manifest": runtime_manifest,
                 "server-check": server_check, "apply-entries": lambda c: server_check(c, apply=True)}
    if args.action in ("status", "server-check", "manifest"):
        result = functions[args.action](c)
    else:
        with operation_lock(d.records):
            # Serialize commands that change deployment state or write receipts;
            # read-only status queries do not acquire the operation lock.
            result = functions[args.action](c)
            result["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            write_json(d.records / (args.action + ".json"), result)
            write_json(d.records / "runtime-manifest.json", runtime_manifest(c))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        print(f"WORKLOAD_ATTESTATION=FAIL: {error}", file=sys.stderr)
        sys.exit(1)
