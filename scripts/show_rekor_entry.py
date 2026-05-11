#!/usr/bin/env python3

import argparse
import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_REKOR_URL = "https://rekor.sigstore.dev"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch and decode a Rekor transparency log entry by logIndex"
    )
    parser.add_argument(
        "log_index",
        type=int,
        help="Rekor logIndex to query",
    )
    parser.add_argument(
        "--rekor-url",
        default=DEFAULT_REKOR_URL,
        help="Base URL for the Rekor instance. Defaults to the public Sigstore Rekor.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print decoded output as JSON",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print only summary, entries, digest mapping, and Docker-event-related fields",
    )
    return parser


def _base64_json(value: str) -> dict[str, Any]:
    return json.loads(base64.b64decode(value).decode("utf-8"))


def _decode_body(entry: dict[str, Any]) -> dict[str, Any]:
    body = entry.get("body")
    if isinstance(body, dict):
        return body
    if not isinstance(body, str) or not body:
        return {}

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        pass

    try:
        return _base64_json(body)
    except Exception:
        return {}


def _decode_dsse_payload(body: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    spec = body.get("spec")
    if not isinstance(spec, dict):
        return {}, None

    payload = spec.get("payload")
    if isinstance(payload, dict):
        return payload, "spec.payload"
    if isinstance(payload, str):
        try:
            return _base64_json(payload), "spec.payload(base64)"
        except Exception:
            pass

    proposed_content = spec.get("proposedContent")
    if isinstance(proposed_content, dict):
        envelope = proposed_content.get("envelope")
        if isinstance(envelope, dict):
            payload = envelope.get("payload")
            if isinstance(payload, str):
                try:
                    return _base64_json(payload), "spec.proposedContent.envelope.payload"
                except Exception:
                    pass
        elif isinstance(envelope, str):
            try:
                envelope_json = json.loads(envelope)
                payload = envelope_json.get("payload")
                if isinstance(payload, str):
                    return _base64_json(payload), "spec.proposedContent.envelope(string).payload"
            except Exception:
                pass

    content = spec.get("content")
    if isinstance(content, dict):
        envelope = content.get("envelope")
        if isinstance(envelope, dict):
            payload = envelope.get("payload")
            if isinstance(payload, str):
                try:
                    return _base64_json(payload), "spec.content.envelope.payload"
                except Exception:
                    pass

    return {}, None


def _decode_attestation(entry: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    attestation = entry.get("attestation")
    if not isinstance(attestation, dict):
        return {}, None

    data = attestation.get("data")
    if isinstance(data, str):
        try:
            return _base64_json(data), "attestation.data"
        except Exception:
            pass

    payload = attestation.get("payload")
    if isinstance(payload, str):
        try:
            return _base64_json(payload), "attestation.payload"
        except Exception:
            pass

    envelope = attestation.get("envelope")
    if isinstance(envelope, dict):
        payload = envelope.get("payload")
        if isinstance(payload, str):
            try:
                return _base64_json(payload), "attestation.envelope.payload"
            except Exception:
                pass

    return {}, None


def _extract_payload_hash(body: dict[str, Any]) -> str | None:
    spec = body.get("spec")
    if not isinstance(spec, dict):
        return None

    candidates = [spec.get("payloadHash")]
    content = spec.get("content")
    if isinstance(content, dict):
        candidates.append(content.get("payloadHash"))

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        algorithm = candidate.get("algorithm")
        value = candidate.get("value")
        if isinstance(algorithm, str) and isinstance(value, str):
            return f"{algorithm}:{value}"
    return None


def _extract_subject_names(payload: dict[str, Any]) -> list[str]:
    subject = payload.get("subject")
    if not isinstance(subject, list):
        return []
    return [item.get("name") for item in subject if isinstance(item, dict) and isinstance(item.get("name"), str)]


def _decode_entry_value(value: Any) -> Any:
    if not isinstance(value, str):
        return None
    decoded = urllib.parse.unquote(value)
    if decoded == value:
        return None
    return decoded


def _build_entry_details(predicate: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entries = predicate.get("entries")
    entry_digests = predicate.get("entry_digests")
    if not isinstance(entries, list):
        entries = []
    if not isinstance(entry_digests, list):
        entry_digests = []

    detailed_entries = []
    digest_table = []
    max_len = max(len(entries), len(entry_digests))

    for index in range(max_len):
        entry = entries[index] if index < len(entries) and isinstance(entries[index], dict) else {}
        digest = entry_digests[index] if index < len(entry_digests) else None
        key = entry.get("key")
        value = entry.get("value")
        decoded_value = _decode_entry_value(value)

        detail = {
            "index": index,
            "key": key,
            "value": value,
            "decoded_value": decoded_value,
            "digest": digest,
        }
        detailed_entries.append(detail)
        digest_table.append(
            {
                "index": index,
                "digest": digest,
                "key": key,
                "value": value,
                "decoded_value": decoded_value,
            }
        )

    return detailed_entries, digest_table


def _build_summary(entry_uuid: str, entry: dict[str, Any]) -> dict[str, Any]:
    body = _decode_body(entry)
    dsse_payload, dsse_source = _decode_dsse_payload(body)
    attestation_payload, attestation_source = _decode_attestation(entry)
    payload = dsse_payload or attestation_payload
    payload_source = dsse_source or attestation_source
    predicate = payload.get("predicate") if isinstance(payload, dict) else {}
    if not isinstance(predicate, dict):
        predicate = {}
    detailed_entries, digest_table = _build_entry_details(predicate)

    verification = entry.get("verification")
    integrated_time = entry.get("integratedTime")
    log_index = entry.get("logIndex")
    log_id = entry.get("logID") or entry.get("logId")

    return {
        "entry_uuid": entry_uuid,
        "log_index": log_index,
        "integrated_time": integrated_time,
        "log_id": log_id,
        "body_kind": body.get("kind") if isinstance(body, dict) else None,
        "body_api_version": body.get("apiVersion") if isinstance(body, dict) else None,
        "payload_source": payload_source,
        "payload_hash": _extract_payload_hash(body),
        "subject_names": _extract_subject_names(payload),
        "predicate_type": payload.get("predicateType") if isinstance(payload, dict) else None,
        "predicate_summary": {
            "event_id": predicate.get("event_id"),
            "event_type": predicate.get("event_type"),
            "chain_id": predicate.get("chain_id"),
            "sequence_num": predicate.get("sequence_num"),
            "digest": predicate.get("digest"),
            "prev_event_digest": predicate.get("prev_event_digest"),
            "prev_lookup_hash": predicate.get("prev_lookup_hash"),
        },
        "entries": detailed_entries,
        "entry_digest_table": digest_table,
        "verification": verification,
        "decoded": {
            "body": body,
            "payload": payload,
        },
    }


def _render_text(summary: dict[str, Any]) -> str:
    predicate = summary.get("predicate_summary") or {}
    subject_names = summary.get("subject_names") or []
    verification = summary.get("verification") or {}
    detailed_entries = summary.get("entries") or []
    digest_table = summary.get("entry_digest_table") or []
    lines = [
        f"Entry UUID: {summary.get('entry_uuid')}",
        f"Log index: {summary.get('log_index')}",
        f"Integrated time: {summary.get('integrated_time')}",
        f"Log ID: {summary.get('log_id')}",
        f"Body kind: {summary.get('body_kind')}",
        f"Body apiVersion: {summary.get('body_api_version')}",
        f"Payload source: {summary.get('payload_source')}",
        f"Payload hash: {summary.get('payload_hash')}",
        "Subject names: " + (", ".join(subject_names) if subject_names else "none"),
        f"Predicate type: {summary.get('predicate_type')}",
        f"Predicate event_id: {predicate.get('event_id')}",
        f"Predicate event_type: {predicate.get('event_type')}",
        f"Predicate chain_id: {predicate.get('chain_id')}",
        f"Predicate sequence_num: {predicate.get('sequence_num')}",
        f"Predicate digest: {predicate.get('digest')}",
        f"Predicate prev_event_digest: {predicate.get('prev_event_digest')}",
        f"Predicate prev_lookup_hash: {predicate.get('prev_lookup_hash')}",
    ]

    if isinstance(verification, dict) and verification:
        lines.append("Verification: " + json.dumps(verification, ensure_ascii=False, sort_keys=True))
    else:
        lines.append("Verification: none")

    lines.append("Entries:")
    if detailed_entries:
        for item in detailed_entries:
            lines.append(f"  [{item['index']}] {item.get('key')} = {item.get('value')}")
            if item.get("decoded_value") is not None:
                lines.append(f"      decoded: {item.get('decoded_value')}")
    else:
        lines.append("  none")

    lines.append("Entry digest mapping:")
    if digest_table:
        for item in digest_table:
            lines.append(f"  [{item['index']}] {item.get('digest')}")
            lines.append(f"      key: {item.get('key')}")
            lines.append(f"      value: {item.get('value')}")
            if item.get("decoded_value") is not None:
                lines.append(f"      decoded: {item.get('decoded_value')}")
    else:
        lines.append("  none")

    lines.append("Decoded body:")
    lines.append(json.dumps(summary["decoded"]["body"], ensure_ascii=False, indent=2, sort_keys=True))
    lines.append("Decoded payload:")
    lines.append(json.dumps(summary["decoded"]["payload"], ensure_ascii=False, indent=2, sort_keys=True))
    return "\n".join(lines)


def _render_summary_only(summary: dict[str, Any]) -> str:
    predicate = summary.get("predicate_summary") or {}
    subject_names = summary.get("subject_names") or []
    detailed_entries = summary.get("entries") or []

    docker_keys = {
        "operation_type",
        "operation_result",
        "runtime_engine",
        "image_name",
        "image_tag",
        "image_digest",
        "container_name",
        "container_id",
        "workload_id",
        "launch_id",
        "instance_id",
    }
    docker_entries = [item for item in detailed_entries if item.get("key") in docker_keys]

    lines = [
        f"Entry UUID: {summary.get('entry_uuid')}",
        f"Log index: {summary.get('log_index')}",
        f"Body kind: {summary.get('body_kind')}",
        f"Payload source: {summary.get('payload_source')}",
        "Subject names: " + (", ".join(subject_names) if subject_names else "none"),
        f"Event type: {predicate.get('event_type')}",
        f"Event id: {predicate.get('event_id')}",
        f"Chain id: {predicate.get('chain_id')}",
        f"Sequence num: {predicate.get('sequence_num')}",
        f"Digest: {predicate.get('digest')}",
        f"Prev event digest: {predicate.get('prev_event_digest')}",
        f"Prev lookup hash: {predicate.get('prev_lookup_hash')}",
    ]

    lines.append("Docker-related entries:")
    if docker_entries:
        for item in docker_entries:
            lines.append(f"  [{item['index']}] {item.get('key')} = {item.get('value')}")
            if item.get("decoded_value") is not None:
                lines.append(f"      decoded: {item.get('decoded_value')}")
    else:
        lines.append("  none")

    return "\n".join(lines)


def _fetch_entries(rekor_url: str, log_index: int) -> dict[str, Any]:
    query = urllib.parse.urlencode({"logIndex": str(log_index)})
    url = f"{rekor_url.rstrip('/')}/api/v1/log/entries?{query}"
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        entries = _fetch_entries(args.rekor_url, args.log_index)
    except urllib.error.HTTPError as exc:
        parser.exit(1, f"Error: Rekor request failed: HTTP {exc.code}\n")
    except urllib.error.URLError as exc:
        parser.exit(1, f"Error: Rekor request failed: {exc.reason}\n")
    except json.JSONDecodeError as exc:
        parser.exit(1, f"Error: Rekor returned non-JSON data: {exc}\n")
    except Exception as exc:
        parser.exit(1, f"Error: {exc}\n")

    if not isinstance(entries, dict) or not entries:
        parser.exit(1, f"Error: no Rekor entry found for logIndex={args.log_index}\n")

    entry_uuid, entry = next(iter(entries.items()))
    summary = _build_summary(entry_uuid, entry)

    if args.json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    elif args.summary_only:
        print(_render_summary_only(summary))
    else:
        print(_render_text(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())