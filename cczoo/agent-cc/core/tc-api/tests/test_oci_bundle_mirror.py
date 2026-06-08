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

import importlib
import json
from pathlib import Path
from unittest.mock import patch

from tlog.backends.rekor.oci_mirror import OciBundleMirror, build_mirror_annotations
from tc_api.trucon.database import (
    enqueue_mirror_publish,
    get_mirror_publish_job,
    get_pending_mirror_publishes,
    init_db,
    update_mirror_publish_status,
)

trucon_app_mod = importlib.import_module("tc_api.trucon.app")


def test_mirror_publish_queue_persists_retryable_jobs(tmp_path):
    db_path = str(tmp_path / "queue.db")
    init_db(db_path)
    enqueue_mirror_publish(
        record_id="rec-1",
        chain_id="default",
        payload_hash="sha256:" + ("ab" * 32),
        bundle_json='{"bundle":1}',
        annotations={"chain_id": "default", "payload_b64": "e30="},
        db_path=db_path,
    )

    jobs = get_pending_mirror_publishes(db_path)
    assert len(jobs) == 1

    update_mirror_publish_status("rec-1", "FAILED_RETRYABLE", last_error="boom", increment_retry_count=True, db_path=db_path)
    job = get_mirror_publish_job("rec-1", db_path)
    assert job is not None
    assert job["status"] == "FAILED_RETRYABLE"
    assert job["retry_count"] == 1


def test_submit_daemon_publishes_confirmed_bundle_to_mirror(tmp_path):
    mirror_dir = Path(tmp_path) / "mirror"
    mirror = OciBundleMirror(str(mirror_dir))

    record = {
        "record_id": "rec-1",
        "chain_id": "default",
        "sequence_num": 1,
        "event_id": "evt-1",
        "event_digest": "sha384:evt-1",
        "payload": json.dumps({
            "bundle": json.dumps({"bundle": "value"}),
        }),
    }

    with patch.object(trucon_app_mod, "_compute_bundle_payload_hash", return_value="sha256:" + ("ab" * 32)), \
         patch.object(trucon_app_mod, "_extract_bundle_payload_b64", return_value="e30="):
        with patch.object(trucon_app_mod, "enqueue_mirror_publish") as enqueue_publish:
            trucon_app_mod._enqueue_mirror_publish_for_record(record, "log-1")

    annotations = build_mirror_annotations(
        chain_id="default",
        sequence_num=1,
        event_digest="sha384:evt-1",
        rekor_log_id="log-1",
        payload_b64="e30=",
        event_id="evt-1",
    )
    manifest = mirror.publish_bundle(
        payload_hash="sha256:" + ("ab" * 32),
        bundle_json=json.dumps({"bundle": "value"}),
        annotations=annotations,
    )
    resolved = mirror.resolve_bundle("sha256:" + ("ab" * 32))

    enqueue_publish.assert_called_once()
    assert manifest["artifactDigest"].startswith("sha256:")
    assert resolved is not None
    assert resolved["annotations"]["rekor_log_id"] == "log-1"


def test_drain_mirror_publish_queue_publishes_pending_job(tmp_path):
    db_path = str(tmp_path / "queue.db")
    init_db(db_path)
    mirror_dir = Path(tmp_path) / "mirror"
    payload_hash = "sha256:" + ("cd" * 32)
    enqueue_mirror_publish(
        record_id="rec-2",
        chain_id="default",
        payload_hash=payload_hash,
        bundle_json=json.dumps({"bundle": "queued"}),
        annotations={"chain_id": "default", "payload_b64": "e30=", "rekor_log_id": "log-2"},
        db_path=db_path,
    )

    original_get_pending = trucon_app_mod.get_pending_mirror_publishes
    original_update_status = trucon_app_mod.update_mirror_publish_status
    original_mirror = trucon_app_mod._bundle_mirror

    try:
        trucon_app_mod._bundle_mirror = OciBundleMirror(str(mirror_dir))

        def _patched_get_pending():
            return original_get_pending(db_path)

        def _patched_update_status(record_id, status, **kwargs):
            kwargs.setdefault("db_path", db_path)
            return original_update_status(record_id, status, **kwargs)

        with patch.object(trucon_app_mod, "get_pending_mirror_publishes", side_effect=_patched_get_pending), \
             patch.object(trucon_app_mod, "update_mirror_publish_status", side_effect=_patched_update_status):
            trucon_app_mod._drain_mirror_publish_queue()
    finally:
        trucon_app_mod._bundle_mirror = original_mirror

    job = get_mirror_publish_job("rec-2", db_path)
    assert job is not None
    assert job["status"] == "PUBLISHED"
    assert job["artifact_digest"].startswith("sha256:")
    resolved = OciBundleMirror(str(mirror_dir)).resolve_bundle(payload_hash)
    assert resolved is not None
    assert resolved["annotations"]["rekor_log_id"] == "log-2"