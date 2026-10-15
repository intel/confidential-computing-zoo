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

"""Durable client-side launch recovery; never retry an uncertain creation POST."""
from contextlib import contextmanager
import hashlib
import http.client
import json
import os
import re
import socket
import ssl
import time
from urllib.error import HTTPError, URLError
import uuid

from deployment import PROFILE, protected_file


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@contextmanager
def operation_lock(directory):
    """The lock inode is persistent: unlinking it would permit concurrent owners."""
    import fcntl
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(directory / "operation.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("another deployment operation is running") from None
        yield
    finally:
        os.close(fd)


def valid_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,256}", value):
        raise ValueError("invalid TC API launch ID")
    return value


def transient(error):
    if isinstance(error, HTTPError):
        return error.code in (502, 503, 504)
    reason = error.reason if isinstance(error, URLError) else error
    # TLS/identity failure must never be hidden behind a network retry.
    return not isinstance(reason, ssl.SSLError) and isinstance(
        reason, (TimeoutError, socket.timeout, ConnectionError, http.client.RemoteDisconnected))


def validated_container(result, launch_id, deployment):
    # Correlate the API result with the intended operation before registration.
    # Registration and Provider collection still re-observe the live container.
    if result.get("launch_id") != launch_id:
        raise ValueError("TC API launch result ID mismatch")
    instances = (result.get("evidence") or {}).get("instance_ids") or result.get("instance_ids")
    if not isinstance(instances, list) or len(instances) != 1 or not isinstance(instances[0], dict):
        raise ValueError("expected one TC API container")
    info = instances[0]
    expected = {"launch_id": launch_id, "workload_id": deployment.workload["id"],
                "attestation_profile": PROFILE,
                "runtime_image_config_digest": deployment.c["approved"]["image_config_digest"]}
    if any(info.get(k) != v for k, v in expected.items()) or not re.fullmatch(r"[0-9a-f]{64}", info.get("container_ID", "")):
        raise ValueError("TC API response differs from required launch/workload/profile/image association")
    return info


def execute(deployment, request, write_json, *, resume=False, launch_id=None, budget=600,
            monotonic=time.monotonic, sleep=time.sleep):
    """Caller owns operation_lock. Secrets only exist in outgoing request bodies."""
    d, c = deployment, deployment.c
    state_path = d.records / "launch-state.json"
    config_digest = digest(c)
    state = json.loads(protected_file(state_path).read_text()) if state_path.exists() else None

    def save(stage, **fields):
        state.update(stage=stage, updated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **fields)
        write_json(state_path, state)

    if resume:
        if state is None:
            if launch_id is None:
                raise ValueError("no saved launch; resume requires an explicit known --launch-id")
            state = {"schema_version": 1, "run_id": str(uuid.uuid4()), "config_sha256": config_digest,
                     "workload_id": d.workload["id"], "target_id": d.identity["target_id"]}
        # Resume the same operation under the same settings. A new image, key
        # binding or identity must not be attached to an old server launch ID.
        if state.get("schema_version") != 1 or state.get("config_sha256") != config_digest:
            raise ValueError("saved launch configuration differs; reconcile before resuming")
        if launch_id and state.get("launch_id") not in (None, launch_id):
            raise ValueError("explicit launch ID differs from the saved operation")
        launch_id = valid_id(launch_id or state.get("launch_id"))
        save("polling", launch_id=launch_id)
    else:
        if state and state.get("stage") != "complete":
            raise ValueError("unfinished or uncertain launch exists; use resume-launch, do not create again")
        if d.target.exists():
            raise ValueError("registered target exists; stop and reconcile it before creating a new instance")
        token = os.environ.get("TC_API_IDENTITY_TOKEN")
        if not token:
            raise ValueError("missing TC_API_IDENTITY_TOKEN for transparency-log upload")
        state = {"schema_version": 1, "run_id": str(uuid.uuid4()), "config_sha256": config_digest,
                 "workload_id": d.workload["id"], "target_id": d.identity["target_id"]}
        # Persist BEFORE submitting, including the window before the ID is returned.
        save("submission_unknown")
        payload = {"image_id": c["image_id"], "image_url": c["image_url"], "user_id": c["tc_api_user_id"],
                   "identity_token": token, "attestation_required": False,
                   "metadata": {"workload_id": d.workload["id"], "service_name": d.workload["id"],
                                "workload_attestation_profile": PROFILE}}
        try:
            launch_id = valid_id(request(c, "/api/deploy-launch", payload)["launch_id"])
        except Exception as error:
            # No response text: upstream error bodies can contain credentials.
            save("submission_unknown", error_type=type(error).__name__)
            raise ValueError("launch submission outcome unknown; reconcile server state and resume with its ID") from None
        save("polling", launch_id=launch_id)

    deadline, commit_attempted = monotonic() + budget, False
    while monotonic() < deadline:
        try:
            result = request(c, "/api/launch-result/" + launch_id)
        except HTTPError as error:
            if error.code == 428:
                # Only an explicit resume may finish a pending transparency commit.
                try:
                    detail = json.loads(error.read(65536)).get("detail", {})
                except (ValueError, AttributeError):
                    detail = {}
                route = "/api/deploy-launch/commit/" + launch_id
                if not isinstance(detail, dict) or detail.get("launch_id") != launch_id or \
                        detail.get("retry_path") != route or detail.get("retry_method") != "POST":
                    save("rejected", error_type="InvalidCommitChallenge")
                    raise ValueError("TC API signing challenge has mismatched launch/path") from None
                save("signing_required")
                token = os.environ.get("TC_API_IDENTITY_TOKEN")
                if not resume or not token or commit_attempted:
                    raise ValueError("fresh signing identity required; run resume-launch with TC_API_IDENTITY_TOKEN") from None
                commit_attempted = True
                save("commit_unknown")
                try:
                    request(c, route, {"identity_token": token})
                except Exception as commit_error:
                    save("commit_unknown", error_type=type(commit_error).__name__)
                    if not transient(commit_error):
                        raise ValueError("signing commit did not confirm success; resume by querying the existing launch") from None
                # Always reconcile by GET, even when a commit response was received.
                continue
            if not transient(error):
                save("query_rejected", error_type="HTTPError", http_status=error.code)
                raise ValueError(f"launch query rejected (HTTP {error.code}); saved ID retained") from None
            save("polling", error_type="HTTPError", http_status=error.code)
            sleep(2)
            continue
        except Exception as error:
            save("polling" if transient(error) else "query_rejected", error_type=type(error).__name__)
            if not transient(error):
                raise ValueError("launch query failed; saved ID retained for explicit recovery") from None
            sleep(2)
            continue
        if not isinstance(result, dict) or result.get("launch_id") != launch_id or result.get("user_id") != c["tc_api_user_id"]:
            save("rejected", error_type="LaunchAssociationMismatch")
            raise ValueError("TC API launch result ID or user mismatch")
        phase = result.get("status")
        if phase == "failed":
            save("failed")
            raise ValueError(f"TC API launch {launch_id} failed; inspect its protected server log")
        if phase == "success":
            try:
                info = validated_container(result, launch_id, d)
            except ValueError:
                save("rejected", error_type="ContainerAssociationMismatch")
                raise
            write_json(d.run / "launch.json", {"launch_id": launch_id, "container": info})
            save("complete", container_id=info["container_ID"])
            write_json(d.records / ("launch-" + state["run_id"] + ".json"), state)
            return {"launch_id": launch_id, "container_id": info["container_ID"], "run_id": state["run_id"],
                    "config_sha256": config_digest, "resumed": resume}
        if phase not in ("initiated", "pending", "launching", "signing"):
            save("rejected", error_type="UnknownServerStage")
            raise ValueError("unknown TC API launch state; saved ID retained")
        save("polling", server_stage=phase)
        sleep(2)
    save("query_timeout")
    raise TimeoutError(f"launch {launch_id} polling timed out; use resume-launch with the same configuration")
