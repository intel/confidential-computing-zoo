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

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from .transparency.events import EventEntryKey


PROFILE_VERIFIED = "verified"
PROFILE_WARNING = "warning"
PROFILE_INCOMPLETE = "incomplete"
PROFILE_FAILED = "failed"

RUNTIME_OPERATION_TYPES = {"pull", "create", "start", "stop", "rm"}
CONTAINER_RUNTIME_OPERATION_TYPES = {"create", "start", "stop", "rm"}
KNOWN_RUNTIME_ENGINES = {"docker", "podman"}


@dataclass(slots=True)
class ProfileEvaluation:
    profile: str
    status: str
    matched_event_ids: List[str] = field(default_factory=list)
    target_launch_id: Optional[str] = None
    target_workload_id: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _entries_oldest_first(entries: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return list(reversed(list(entries)))


def _entry_values(predicate_entries: List[Dict[str, Any]], key: str) -> List[Any]:
    values: List[Any] = []
    for entry in predicate_entries or []:
        if not isinstance(entry, dict) or entry.get("key") != key:
            continue
        value = entry.get("value")
        if isinstance(value, dict) and key in value:
            value = value[key]
        values.append(value)
    return values


def _latest_value(predicate_entries: List[Dict[str, Any]], key: str) -> Any:
    values = _entry_values(predicate_entries, key)
    return values[-1] if values else None


def _flatten_event_fields(event_set: List[Dict[str, Any]]) -> Dict[str, Any]:
    flattened: Dict[str, Any] = {}
    for event in event_set:
        for entry in event.get("predicate_entries") or []:
            if not isinstance(entry, dict) or "key" not in entry:
                continue
            key = entry["key"]
            value = entry.get("value")
            if isinstance(value, dict) and key in value:
                value = value[key]
            flattened[key] = value
    return flattened


def _build_event_set(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    oldest = _entries_oldest_first(entries)
    build_events = [entry for entry in oldest if entry.get("event_type") == "build"]
    return build_events[-1:] if build_events else []


def _publish_event_set(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    oldest = _entries_oldest_first(entries)
    publish_events = [entry for entry in oldest if entry.get("event_type") == "publish"]
    return publish_events[-1:] if publish_events else []


def select_latest_launch_event_set(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered_entries = list(entries)
    launch_entries = [entry for entry in ordered_entries if entry.get("event_type") == "launch"]
    if not launch_entries:
        return []

    latest_launch = max(
        launch_entries,
        key=lambda entry: entry.get("created") or "",
    ) if any(entry.get("created") for entry in launch_entries) else launch_entries[-1]
    target_launch_id = _latest_value(latest_launch.get("predicate_entries") or [], EventEntryKey.launch_id.value)
    if not target_launch_id:
        return [latest_launch]

    event_set = []
    for entry in ordered_entries:
        if _latest_value(entry.get("predicate_entries") or [], EventEntryKey.launch_id.value) == target_launch_id:
            event_set.append(entry)
    if not event_set:
        event_set = [latest_launch]
    return event_set


def _runtime_event_set(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    oldest = _entries_oldest_first(entries)
    runtime_events: List[Dict[str, Any]] = []
    for entry in oldest:
        operation_type = _latest_value(entry.get("predicate_entries") or [], EventEntryKey.operation_type.value)
        if operation_type in RUNTIME_OPERATION_TYPES:
            runtime_events.append(entry)
    return runtime_events


def _evaluate_runtime_engine_specific(
    runtime_engine: str,
    event_id: str,
    warnings: List[str],
) -> bool:
    if runtime_engine in KNOWN_RUNTIME_ENGINES:
        return True

    warnings.append(
        f"{event_id}: Unsupported runtime_engine for engine-specific evaluation: {runtime_engine}"
    )
    return False


def evaluate_build_profile(entries: List[Dict[str, Any]]) -> ProfileEvaluation:
    event_set = _build_event_set(entries)
    if not event_set:
        return ProfileEvaluation(profile="build", status=PROFILE_INCOMPLETE, errors=["No build event found"])

    fields = _flatten_event_fields(event_set)
    errors = []
    warnings = []
    for key in (
        EventEntryKey.output_image_digest.value,
        EventEntryKey.dockerfile_digest.value,
        EventEntryKey.build_context_digest.value,
        EventEntryKey.base_image_digests.value,
        EventEntryKey.build_status.value,
    ):
        value = fields.get(key)
        if value in (None, "", []):
            errors.append(f"Missing required field: {key}")

    if fields.get(EventEntryKey.build_status.value) not in (None, "success"):
        errors.append(f"Build status is not successful: {fields.get(EventEntryKey.build_status.value)}")

    if fields.get(EventEntryKey.sbom_digest.value) in (None, ""):
        warnings.append("Missing optional field: sbom_digest")

    status = PROFILE_FAILED if errors else (PROFILE_WARNING if warnings else PROFILE_VERIFIED)
    return ProfileEvaluation(
        profile="build",
        status=status,
        matched_event_ids=[entry.get("event_id") for entry in event_set if entry.get("event_id")],
        errors=errors,
        warnings=warnings,
        details={"fields": fields},
    )


def evaluate_publish_profile(entries: List[Dict[str, Any]]) -> ProfileEvaluation:
    event_set = _publish_event_set(entries)
    if not event_set:
        return ProfileEvaluation(profile="publish", status=PROFILE_INCOMPLETE, errors=["No publish event found"])

    fields = _flatten_event_fields(event_set)
    errors = []
    for key in (EventEntryKey.pushed_subject_digest.value, EventEntryKey.target_ref.value, EventEntryKey.publish_status.value):
        value = fields.get(key)
        if value in (None, ""):
            errors.append(f"Missing required field: {key}")

    if fields.get(EventEntryKey.publish_status.value) not in (None, "success"):
        errors.append(f"Publish status is not successful: {fields.get(EventEntryKey.publish_status.value)}")

    status = PROFILE_FAILED if errors else PROFILE_VERIFIED
    return ProfileEvaluation(
        profile="publish",
        status=status,
        matched_event_ids=[entry.get("event_id") for entry in event_set if entry.get("event_id")],
        errors=errors,
        details={"fields": fields},
    )


def evaluate_launch_profile(entries: List[Dict[str, Any]]) -> ProfileEvaluation:
    event_set = select_latest_launch_event_set(entries)
    if not event_set:
        return ProfileEvaluation(profile="launch", status=PROFILE_INCOMPLETE, errors=["No launch event found"])

    fields = _flatten_event_fields(event_set)
    target_launch_id = fields.get(EventEntryKey.launch_id.value)
    target_workload_id = fields.get(EventEntryKey.workload_id.value)
    errors = []
    warnings = []
    required_fields = (
        EventEntryKey.launch_id.value,
        EventEntryKey.workload_id.value,
        EventEntryKey.image_digest.value,
        EventEntryKey.launch_config_digest.value,
        EventEntryKey.privileged.value,
        EventEntryKey.network_mode.value,
        EventEntryKey.mounts.value,
        EventEntryKey.devices.value,
        EventEntryKey.capabilities.value,
    )
    for key in required_fields:
        value = fields.get(key)
        if value in (None, ""):
            errors.append(f"Missing required field: {key}")

    successful_container_scope = False
    instance_values: List[Any] = []
    for event in event_set:
        event_fields = _flatten_event_fields([event])
        if event_fields.get(EventEntryKey.operation_type.value) in CONTAINER_RUNTIME_OPERATION_TYPES and event_fields.get(EventEntryKey.operation_result.value) == "success":
            successful_container_scope = True
            instance_values.append(event_fields.get(EventEntryKey.instance_id.value) or event_fields.get(EventEntryKey.container_id.value))
    if successful_container_scope and not any(value not in (None, "") for value in instance_values):
        errors.append("Missing required field: instance_id")

    if fields.get(EventEntryKey.launch_env_keys.value) in (None, "") and fields.get(EventEntryKey.launch_env_digest.value) in (None, ""):
        warnings.append("Missing optional environment projection metadata")

    launch_result = fields.get(EventEntryKey.launch_result.value)
    if launch_result not in (None, "success"):
        errors.append(f"Launch result is not successful: {launch_result}")

    status = PROFILE_FAILED if errors else (PROFILE_WARNING if warnings else PROFILE_VERIFIED)
    return ProfileEvaluation(
        profile="launch",
        status=status,
        matched_event_ids=[entry.get("event_id") for entry in event_set if entry.get("event_id")],
        target_launch_id=target_launch_id,
        target_workload_id=target_workload_id,
        errors=errors,
        warnings=warnings,
        details={"fields": fields},
    )


def evaluate_runtime_profile(entries: List[Dict[str, Any]]) -> ProfileEvaluation:
    event_set = _runtime_event_set(entries)
    if not event_set:
        return ProfileEvaluation(profile="docktap-runtime", status=PROFILE_INCOMPLETE, errors=["No runtime events found"])

    errors = []
    warnings = []
    unsupported_runtime_engines = []
    for event in event_set:
        fields = _flatten_event_fields([event])
        event_id = event.get("event_id") or "<unknown>"
        operation_type = fields.get(EventEntryKey.operation_type.value)
        runtime_engine = fields.get(EventEntryKey.runtime_engine.value)
        if fields.get(EventEntryKey.operation_result.value) in (None, ""):
            errors.append(f"{event_id}: Missing required field: operation_result")
        if runtime_engine in (None, ""):
            errors.append(f"{event_id}: Missing required field: runtime_engine")
        if operation_type in CONTAINER_RUNTIME_OPERATION_TYPES:
            if fields.get(EventEntryKey.workload_id.value) in (None, ""):
                errors.append(f"{event_id}: Missing required field: workload_id")
            if (fields.get(EventEntryKey.instance_id.value) or fields.get(EventEntryKey.container_id.value)) in (None, ""):
                errors.append(f"{event_id}: Missing required field: instance_id")
        if operation_type in {"pull", "create"} and not any(fields.get(key) not in (None, "") for key in (EventEntryKey.image_digest.value, EventEntryKey.image_name.value, EventEntryKey.image_ref.value)):
            errors.append(f"{event_id}: Missing required image identity")
        if operation_type in {"stop", "rm"} and fields.get(EventEntryKey.launch_id.value) in (None, ""):
            warnings.append(f"{event_id}: Missing optional launch_id for post-launch runtime event")
        if runtime_engine not in (None, ""):
            if not _evaluate_runtime_engine_specific(str(runtime_engine), event_id, warnings):
                unsupported_runtime_engines.append(str(runtime_engine))

    if errors:
        status = PROFILE_FAILED
    elif unsupported_runtime_engines:
        status = PROFILE_INCOMPLETE
    elif warnings:
        status = PROFILE_WARNING
    else:
        status = PROFILE_VERIFIED
    return ProfileEvaluation(
        profile="docktap-runtime",
        status=status,
        matched_event_ids=[entry.get("event_id") for entry in event_set if entry.get("event_id")],
        errors=errors,
        warnings=warnings,
        details={
            "event_count": len(event_set),
            "unsupported_runtime_engines": unsupported_runtime_engines,
        },
    )


def evaluate_profiles(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    evaluations = [
        evaluate_build_profile(entries),
        evaluate_publish_profile(entries),
        evaluate_launch_profile(entries),
        evaluate_runtime_profile(entries),
    ]
    return {evaluation.profile: evaluation.to_dict() for evaluation in evaluations}