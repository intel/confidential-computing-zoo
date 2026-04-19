from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional


PROFILE_VERIFIED = "verified"
PROFILE_WARNING = "warning"
PROFILE_INCOMPLETE = "incomplete"
PROFILE_FAILED = "failed"


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


def _collect_field(event_set: List[Dict[str, Any]], key: str) -> Any:
    for event in reversed(event_set):
        value = _latest_value(event.get("predicate_entries") or [], key)
        if value is not None:
            return value
    return None


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
    target_launch_id = _latest_value(latest_launch.get("predicate_entries") or [], "launch_id")
    if not target_launch_id:
        return [latest_launch]

    event_set = []
    for entry in ordered_entries:
        if _latest_value(entry.get("predicate_entries") or [], "launch_id") == target_launch_id:
            event_set.append(entry)
    if not event_set:
        event_set = [latest_launch]
    return event_set


def _runtime_event_set(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    oldest = _entries_oldest_first(entries)
    return [entry for entry in oldest if str(entry.get("event_type") or "").startswith("docker_")]


def evaluate_build_profile(entries: List[Dict[str, Any]]) -> ProfileEvaluation:
    event_set = _build_event_set(entries)
    if not event_set:
        return ProfileEvaluation(profile="build", status=PROFILE_INCOMPLETE, errors=["No build event found"])

    fields = _flatten_event_fields(event_set)
    errors = []
    warnings = []
    for key in ("output_image_digest", "dockerfile_digest", "build_context_digest", "base_image_digests", "build_status"):
        value = fields.get(key)
        if value in (None, "", []):
            errors.append(f"Missing required field: {key}")

    if fields.get("build_status") not in (None, "success"):
        errors.append(f"Build status is not successful: {fields.get('build_status')}")

    if fields.get("sbom_digest") in (None, ""):
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
    for key in ("pushed_subject_digest", "target_ref", "publish_status"):
        value = fields.get(key)
        if value in (None, ""):
            errors.append(f"Missing required field: {key}")

    if fields.get("publish_status") not in (None, "success"):
        errors.append(f"Publish status is not successful: {fields.get('publish_status')}")

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
    target_launch_id = fields.get("launch_id")
    target_workload_id = fields.get("workload_id")
    errors = []
    warnings = []
    required_fields = (
        "launch_id",
        "workload_id",
        "image_digest",
        "launch_config_digest",
        "privileged",
        "network_mode",
        "mounts",
        "devices",
        "capabilities",
    )
    for key in required_fields:
        value = fields.get(key)
        if value in (None, ""):
            errors.append(f"Missing required field: {key}")

    successful_container_scope = False
    instance_values: List[Any] = []
    for event in event_set:
        event_fields = _flatten_event_fields([event])
        if event_fields.get("operation_type") in {"create", "start", "stop", "rm"} and event_fields.get("operation_result") == "success":
            successful_container_scope = True
            instance_values.append(event_fields.get("instance_id") or event_fields.get("container_id"))
    if successful_container_scope and not any(value not in (None, "") for value in instance_values):
        errors.append("Missing required field: instance_id")

    if fields.get("launch_env_keys") in (None, "") and fields.get("launch_env_digest") in (None, ""):
        warnings.append("Missing optional environment projection metadata")

    launch_result = fields.get("launch_result")
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
    for event in event_set:
        fields = _flatten_event_fields([event])
        event_id = event.get("event_id") or "<unknown>"
        operation_type = fields.get("operation_type")
        if fields.get("operation_result") in (None, ""):
            errors.append(f"{event_id}: Missing required field: operation_result")
        if operation_type in {"create", "start", "stop", "rm"}:
            if fields.get("workload_id") in (None, ""):
                errors.append(f"{event_id}: Missing required field: workload_id")
            if (fields.get("instance_id") or fields.get("container_id")) in (None, ""):
                errors.append(f"{event_id}: Missing required field: instance_id")
        if operation_type in {"pull", "create"} and not any(fields.get(key) not in (None, "") for key in ("image_digest", "image_name", "image_ref")):
            errors.append(f"{event_id}: Missing required image identity")
        if operation_type in {"stop", "rm"} and fields.get("launch_id") in (None, ""):
            warnings.append(f"{event_id}: Missing optional launch_id for post-launch runtime event")

    status = PROFILE_FAILED if errors else (PROFILE_WARNING if warnings else PROFILE_VERIFIED)
    return ProfileEvaluation(
        profile="docktap-runtime",
        status=status,
        matched_event_ids=[entry.get("event_id") for entry in event_set if entry.get("event_id")],
        errors=errors,
        warnings=warnings,
        details={"event_count": len(event_set)},
    )


def evaluate_profiles(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    evaluations = [
        evaluate_build_profile(entries),
        evaluate_publish_profile(entries),
        evaluate_launch_profile(entries),
        evaluate_runtime_profile(entries),
    ]
    return {evaluation.profile: evaluation.to_dict() for evaluation in evaluations}