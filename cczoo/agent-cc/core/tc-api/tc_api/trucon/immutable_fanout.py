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

import logging
from typing import Any, Dict, Iterable, Optional, Tuple

from tlog.immutable import ImmutableLogAdapter

logger = logging.getLogger("trucon")


class CompositeImmutableLogAdapter(ImmutableLogAdapter):
    def __init__(
        self,
        *,
        primary_backend: str,
        primary_adapter: ImmutableLogAdapter,
        secondary_adapters: Iterable[tuple[str, ImmutableLogAdapter]] = (),
        write_policy: str = "primary",
    ) -> None:
        self.primary_backend = primary_backend
        self.primary_adapter = primary_adapter
        self.secondary_adapters = tuple(secondary_adapters)
        self.write_policy = write_policy
        self.last_submit_results: Dict[str, Dict[str, Any]] = {}

    def submit_bundle(self, bundle: str, prev_log_id: Optional[str] = None) -> Tuple[str, str, Any]:
        primary_result: Optional[Tuple[str, str, Any]] = None
        results: Dict[str, Dict[str, Any]] = {}

        adapters = ((self.primary_backend, self.primary_adapter), *self.secondary_adapters)
        for backend_name, adapter in adapters:
            try:
                log_id, status, receipt = adapter.submit_bundle(bundle, prev_log_id=prev_log_id)
                results[backend_name] = {
                    "backend": backend_name,
                    "log_id": log_id,
                    "status": status,
                    "receipt": receipt,
                }
                if backend_name == self.primary_backend:
                    primary_result = (log_id, status, receipt)
                elif status != "confirmed":
                    logger.warning(
                        "Secondary immutable backend %s returned non-confirmed status=%s",
                        backend_name,
                        status,
                    )
            except Exception as exc:
                results[backend_name] = {
                    "backend": backend_name,
                    "status": "error",
                    "error": str(exc),
                }
                if backend_name == self.primary_backend:
                    self.last_submit_results = results
                    raise
                logger.warning("Secondary immutable backend %s submission failed: %s", backend_name, exc)

        self.last_submit_results = results
        if primary_result is None:
            raise RuntimeError("Primary immutable backend did not produce a submission result")
        return primary_result

    def get_entry(self, log_id: str) -> Any:
        return self.primary_adapter.get_entry(log_id)

    def traverse(self, end_log_id: str, count: int = 10) -> list[Any]:
        return self.primary_adapter.traverse(end_log_id, count=count)

    def find_entries_by_payload_hash(self, payload_hash: str) -> list[Any]:
        return self.primary_adapter.find_entries_by_payload_hash(payload_hash)