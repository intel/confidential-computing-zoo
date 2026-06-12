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

import json
import logging
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from tlog.backends.rekor.oci_mirror import OciBundleMirror, build_mirror_annotations

from .bundles import compute_bundle_payload_hash, extract_bundle_payload_b64
from .database import (
    enqueue_mirror_publish,
    get_all_chain_ids,
    get_db_connection,
    get_failed_by_chain,
    get_pending_by_chain,
    get_pending_mirror_publishes,
    get_queue_stats,
    increment_retry,
    set_status_submitting,
    update_chain_state,
    update_mirror_publish_status,
    update_record_confirmed,
    update_status,
)

logger = logging.getLogger("trucon")

MAX_RETRIES = 10
POLL_INTERVAL = 5.0


def _extract_preconfirmed_owner_key_submission(bundle_json: str) -> Optional[Dict[str, Any]]:
    try:
        parsed = json.loads(bundle_json)
    except Exception:
        return None

    if not isinstance(parsed, dict) or not parsed.get("_owner_key_signed"):
        return None

    rekor_uuid = parsed.get("rekor_uuid")
    rekor_log_index = parsed.get("rekor_log_index")
    log_id = rekor_uuid or rekor_log_index
    if log_id is None:
        raise ValueError("Owner-key-signed bundle is missing Rekor identifiers")

    receipt: Dict[str, Any] = {
        "uuid": str(rekor_uuid) if rekor_uuid is not None else None,
        "entryUUID": str(rekor_uuid) if rekor_uuid is not None else None,
        "log_index": int(rekor_log_index) if isinstance(rekor_log_index, int) else rekor_log_index,
        "logIndex": int(rekor_log_index) if isinstance(rekor_log_index, int) else rekor_log_index,
    }
    return {
        "log_id": str(log_id),
        "receipt": receipt,
    }


def extract_confirmed_rekor_identifiers(log_id: str, receipt: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    receipt_data = receipt or {}
    confirmed_rekor_uuid = receipt_data.get("uuid") or receipt_data.get("entryUUID")
    confirmed_rekor_log_index = receipt_data.get("log_index") or receipt_data.get("logIndex")
    confirmed_rekor_log_id = receipt_data.get("log_id") or receipt_data.get("logID") or log_id
    return {
        "confirmed_rekor_log_id": str(confirmed_rekor_log_id) if confirmed_rekor_log_id is not None else None,
        "confirmed_rekor_uuid": str(confirmed_rekor_uuid) if confirmed_rekor_uuid else None,
        "confirmed_rekor_log_index": str(confirmed_rekor_log_index) if confirmed_rekor_log_index is not None else None,
    }


class SubmitDaemon:
    def __init__(
        self,
        immutable_log: Any,
        bundle_mirror: Optional[OciBundleMirror],
        *,
        heartbeat_ticks: int,
    ) -> None:
        self.immutable_log = immutable_log
        self.bundle_mirror = bundle_mirror
        self.heartbeat_ticks = heartbeat_ticks
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.last_queue_snapshot: Optional[tuple[int, int, int, int, int]] = None
        self.last_queue_snapshot_tick = 0
        self.queue_snapshot_tick = 0

    def start(self) -> None:
        self.thread = threading.Thread(target=self.run, daemon=True, name="submit-daemon")
        self.thread.start()

    def stop(self, timeout: float = 10) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=timeout)
            self.thread = None

    def run(self) -> None:
        logger.info("Submit daemon started")
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception as exc:
                logger.error("Submit daemon error: %s", exc)
            self.stop_event.wait(timeout=POLL_INTERVAL)
        logger.info("Submit daemon stopped")

    def tick(self) -> None:
        chain_ids = get_all_chain_ids()
        for chain_id in chain_ids:
            failed = get_failed_by_chain(chain_id)
            if failed:
                for failed_record in failed:
                    if failed_record['status'] == 'FAILED_RETRYABLE':
                        update_status(failed_record['record_id'], 'PENDING')
                        logger.info("Record %s reset from FAILED_RETRYABLE to PENDING for retry", failed_record['record_id'])
                failed_terminal = [failed_record for failed_record in failed if failed_record['status'] == 'FAILED_TERMINAL']
                min_failed_seq = failed_terminal[0]['sequence_num'] if failed_terminal else None
            else:
                min_failed_seq = None

            pending = get_pending_by_chain(chain_id)
            for record in pending:
                seq = record['sequence_num']
                if min_failed_seq is not None and seq > min_failed_seq:
                    break

                record_id = record['record_id']
                payload = json.loads(record['payload'])
                bundle_json = payload.get('bundle')

                if not bundle_json:
                    logger.warning("Record %s has no bundle in payload, skipping", record_id)
                    continue

                set_status_submitting(record_id)
                submit_start = time.perf_counter()

                try:
                    self._submit_record(record, record_id, chain_id, seq, bundle_json, submit_start)
                except Exception as exc:
                    submit_ms = (time.perf_counter() - submit_start) * 1000
                    logger.info("metric=submit_latency latency_ms=%.1f record_id=%s outcome=%s", submit_ms, record_id, "failed_retryable")
                    logger.error("Failed to submit record %s to immutable backend: %s", record_id, exc)
                    self._handle_retry(record_id)

        self._drain_mirror_publish_queue()
        self._emit_queue_snapshot(get_queue_stats())

    def _submit_record(self, record: Any, record_id: str, chain_id: str, seq: int, bundle_json: str, submit_start: float) -> None:
        preconfirmed = _extract_preconfirmed_owner_key_submission(bundle_json)
        if preconfirmed is not None:
            self._confirm_record(
                record,
                record_id,
                chain_id,
                seq,
                preconfirmed["log_id"],
                submit_start,
                preconfirmed["receipt"],
            )
            return

        if self.immutable_log:
            log_id, status, receipt = self.immutable_log.submit_bundle(bundle_json)
            self._emit_secondary_backend_results(record_id)
            if status == "confirmed":
                self._confirm_record(record, record_id, chain_id, seq, log_id, submit_start, receipt)
            else:
                submit_ms = (time.perf_counter() - submit_start) * 1000
                logger.info("metric=submit_latency latency_ms=%.1f record_id=%s outcome=%s", submit_ms, record_id, "failed_retryable")
                self._handle_retry(record_id)
            return

        mock_log_id = f"mock-{uuid.uuid4().hex[:8]}"
        update_record_confirmed(record_id, mock_log_id)
        submit_ms = (time.perf_counter() - submit_start) * 1000
        logger.info("metric=submit_latency latency_ms=%.1f record_id=%s outcome=%s", submit_ms, record_id, "confirmed")
        self._emit_confirmation_lag(record, record_id)
        self._enqueue_mirror_publish_for_record(record, mock_log_id)
        logger.info("Record %s mock-confirmed (no immutable log)", record_id)

    def _confirm_record(
        self,
        record: Any,
        record_id: str,
        chain_id: str,
        seq: int,
        log_id: str,
        submit_start: float,
        receipt: Optional[Dict[str, Any]],
    ) -> None:
        confirmed_rekor = extract_confirmed_rekor_identifiers(log_id, receipt)
        update_record_confirmed(record_id, log_id)
        submit_ms = (time.perf_counter() - submit_start) * 1000
        logger.info("metric=submit_latency latency_ms=%.1f record_id=%s outcome=%s", submit_ms, record_id, "confirmed")
        self._emit_confirmation_lag(record, record_id)
        update_chain_state(chain_id=chain_id, head_record_id=record_id, sequence_num=seq, head_log_id=log_id)
        self._enqueue_mirror_publish_for_record(record, log_id)
        logger.info(
            "Record %s confirmed with confirmed_rekor_log_id=%s confirmed_rekor_uuid=%s confirmed_rekor_log_index=%s sequence_num=%s chain_id=%s",
            record_id,
            confirmed_rekor["confirmed_rekor_log_id"],
            confirmed_rekor["confirmed_rekor_uuid"],
            confirmed_rekor["confirmed_rekor_log_index"],
            seq,
            chain_id,
        )

    def _emit_confirmation_lag(self, record: Any, record_id: str) -> None:
        created_at = record['created_at'] if 'created_at' in record.keys() else None
        if not created_at:
            return
        confirmed_at = datetime.utcnow()
        created_dt = datetime.fromisoformat(created_at)
        lag_ms = (confirmed_at - created_dt).total_seconds() * 1000
        logger.info("metric=confirmation_lag lag_ms=%.1f record_id=%s", lag_ms, record_id)

    def _enqueue_mirror_publish_for_record(self, record: Any, log_id: Optional[str]) -> None:
        payload = json.loads(record["payload"])
        bundle_json = payload.get("bundle")
        if not isinstance(bundle_json, str) or not bundle_json:
            return

        payload_hash = compute_bundle_payload_hash(bundle_json)
        payload_b64 = extract_bundle_payload_b64(bundle_json)
        annotations = build_mirror_annotations(
            chain_id=record["chain_id"],
            sequence_num=record["sequence_num"],
            event_digest=record["event_digest"] if "event_digest" in record.keys() else None,
            rekor_log_id=log_id,
            payload_b64=payload_b64,
            event_id=record["event_id"] if "event_id" in record.keys() else None,
            prev_event_digest=record["prev_event_digest"] if "prev_event_digest" in record.keys() else None,
            prev_lookup_hash=record["prev_lookup_hash"] if "prev_lookup_hash" in record.keys() else None,
        )
        enqueue_mirror_publish(
            record_id=record["record_id"],
            chain_id=record["chain_id"],
            payload_hash=payload_hash,
            bundle_json=bundle_json,
            annotations=annotations,
        )

    def _drain_mirror_publish_queue(self) -> None:
        if self.bundle_mirror is None:
            return

        for job in get_pending_mirror_publishes():
            try:
                manifest = self.bundle_mirror.publish_bundle(
                    payload_hash=job["payload_hash"],
                    bundle_json=job["bundle_json"],
                    annotations=json.loads(job["annotations"]),
                )
                update_mirror_publish_status(job["record_id"], "PUBLISHED", artifact_digest=manifest.get("artifactDigest"), last_error=None)
            except Exception as exc:
                logger.warning("Mirror publish failed for record %s: %s", job["record_id"], exc)
                update_mirror_publish_status(
                    job["record_id"],
                    "FAILED_RETRYABLE",
                    last_error=str(exc),
                    increment_retry_count=True,
                )

    def _emit_queue_snapshot(self, stats: Dict[str, int]) -> None:
        snapshot = self._queue_snapshot_tuple(stats)
        self.queue_snapshot_tick += 1
        should_emit = self.last_queue_snapshot != snapshot

        if not should_emit and (self.queue_snapshot_tick - self.last_queue_snapshot_tick) >= self.heartbeat_ticks:
            should_emit = True

        if not should_emit:
            return

        self.last_queue_snapshot = snapshot
        self.last_queue_snapshot_tick = self.queue_snapshot_tick
        logger.info(
            "metric=queue_snapshot queue_depth=%d submitting=%d failed_retryable=%d failed_terminal=%d total_retries=%d",
            snapshot[0],
            snapshot[1],
            snapshot[2],
            snapshot[3],
            snapshot[4],
        )

    def _handle_retry(self, record_id: str) -> None:
        increment_retry(record_id, 'FAILED_RETRYABLE')
        with get_db_connection() as conn:
            row = conn.execute('SELECT retry_count FROM commit_queue WHERE record_id = ?', (record_id,)).fetchone()
            if row and row['retry_count'] >= MAX_RETRIES:
                update_status(record_id, 'FAILED_TERMINAL')
                logger.warning("Record %s moved to FAILED_TERMINAL after %d retries", record_id, MAX_RETRIES)

    @staticmethod
    def _queue_snapshot_tuple(stats: Dict[str, int]) -> tuple[int, int, int, int, int]:
        return (
            stats['queued_count'],
            stats['submitting_count'],
            stats['failed_retryable_count'],
            stats['failed_terminal_count'],
            stats['total_retry_count'],
        )

    def _emit_secondary_backend_results(self, record_id: str) -> None:
        results = getattr(self.immutable_log, "last_submit_results", None)
        primary_backend = getattr(self.immutable_log, "primary_backend", None)
        if not isinstance(results, dict) or len(results) <= 1 or primary_backend is None:
            return

        secondary_results = {
            backend: {
                "status": result.get("status"),
                "log_id": result.get("log_id"),
                "error": result.get("error"),
            }
            for backend, result in results.items()
            if backend != primary_backend
        }
        if secondary_results:
            logger.info(
                "record %s secondary immutable backend results=%s",
                record_id,
                json.dumps(secondary_results, sort_keys=True),
            )
