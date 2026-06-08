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

from enum import Enum
from typing import Any, Iterable, List, Mapping, Optional

from tlog.types import Entry


class EventEntryKey(str, Enum):
    operation_type = "operation_type"
    operation_result = "operation_result"
    runtime_engine = "runtime_engine"
    workload_id = "workload_id"
    launch_id = "launch_id"
    instance_id = "instance_id"
    image_name = "image_name"
    image_tag = "image_tag"
    image_digest = "image_digest"
    image_platform = "image_platform"
    container_name = "container_name"
    container_id = "container_id"
    output_image_digest = "output_image_digest"
    dockerfile_digest = "dockerfile_digest"
    build_context_digest = "build_context_digest"
    base_image_digests = "base_image_digests"
    build_status = "build_status"
    sbom_digest = "sbom_digest"
    pushed_subject_digest = "pushed_subject_digest"
    target_ref = "target_ref"
    publish_status = "publish_status"
    launch_config_digest = "launch_config_digest"
    privileged = "privileged"
    network_mode = "network_mode"
    mounts = "mounts"
    devices = "devices"
    capabilities = "capabilities"
    launch_env_keys = "launch_env_keys"
    launch_env_digest = "launch_env_digest"
    launch_result = "launch_result"
    image_ref = "image_ref"


def event_entry(key: EventEntryKey | str, value: Any) -> Entry:
    resolved_key = key.value if isinstance(key, EventEntryKey) else key
    return Entry(key=resolved_key, value=value)


def event_entries(items: Mapping[EventEntryKey | str, Any]) -> List[Entry]:
    return [event_entry(key, value) for key, value in items.items() if value is not None]


def add_event_entries(target: List[Entry], items: Iterable[Entry]) -> None:
    target.extend(items)


def runtime_operation_entries(
    operation_type: str,
    *,
    operation_result: str,
    runtime_engine: str,
    workload_id: Optional[str] = None,
    launch_id: Optional[str] = None,
    instance_id: Optional[str] = None,
    image: Optional[Mapping[str, Any]] = None,
    container: Optional[Mapping[str, Any]] = None,
) -> List[Entry]:
    image_data = dict(image or {})
    container_data = dict(container or {})
    entries = event_entries(
        {
            EventEntryKey.operation_type: operation_type,
            EventEntryKey.operation_result: operation_result,
            EventEntryKey.runtime_engine: runtime_engine,
            EventEntryKey.workload_id: workload_id,
            EventEntryKey.launch_id: launch_id,
            EventEntryKey.instance_id: instance_id,
        }
    )

    if operation_type in {"pull", "build", "create"}:
        add_event_entries(
            entries,
            event_entries(
                {
                    EventEntryKey.image_name: image_data.get("name"),
                    EventEntryKey.image_tag: image_data.get("tag") if operation_type in {"pull", "build"} else None,
                    EventEntryKey.image_digest: image_data.get("digest") if operation_type == "pull" else None,
                    EventEntryKey.image_platform: image_data.get("platform") if operation_type == "build" else None,
                }
            ),
        )

    if operation_type == "create":
        add_event_entries(
            entries,
            event_entries(
                {
                    EventEntryKey.container_name: container_data.get("name"),
                    EventEntryKey.container_id: container_data.get("id"),
                }
            ),
        )
    elif operation_type in {"start", "stop", "rm"}:
        add_event_entries(entries, event_entries({EventEntryKey.container_id: container_data.get("id")}))

    return entries


def build_identity_entries(
    *,
    output_image_digest: Optional[str],
    dockerfile_digest: str,
    build_context_digest: str,
    base_image_digests: List[Any],
    build_status: str,
) -> List[Entry]:
    return event_entries(
        {
            EventEntryKey.dockerfile_digest: dockerfile_digest,
            EventEntryKey.build_context_digest: build_context_digest,
            EventEntryKey.base_image_digests: base_image_digests,
            EventEntryKey.build_status: build_status,
            EventEntryKey.output_image_digest: output_image_digest,
        }
    )


def publish_identity_entries(*, pushed_subject_digest: Optional[str], target_ref: str, publish_status: str) -> List[Entry]:
    return event_entries(
        {
            EventEntryKey.pushed_subject_digest: pushed_subject_digest,
            EventEntryKey.target_ref: target_ref,
            EventEntryKey.publish_status: publish_status,
        }
    )


def launch_security_entries(security_projection: Mapping[str, Any], *, image_digest: Any, launch_config_digest: str) -> List[Entry]:
    return event_entries(
        {
            EventEntryKey.image_digest: image_digest,
            EventEntryKey.launch_config_digest: launch_config_digest,
            EventEntryKey.privileged: security_projection.get("privileged"),
            EventEntryKey.network_mode: security_projection.get("network_mode"),
            EventEntryKey.mounts: security_projection.get("mounts"),
            EventEntryKey.devices: security_projection.get("devices"),
            EventEntryKey.capabilities: security_projection.get("capabilities"),
            EventEntryKey.launch_env_keys: security_projection.get("launch_env_keys"),
            EventEntryKey.launch_env_digest: security_projection.get("launch_env_digest"),
        }
    )


__all__ = [
    "EventEntryKey",
    "add_event_entries",
    "build_identity_entries",
    "event_entries",
    "event_entry",
    "launch_security_entries",
    "publish_identity_entries",
    "runtime_operation_entries",
]