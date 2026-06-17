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

from abc import ABC, abstractmethod
from typing import Any, Optional, Tuple


class ImmutableLogAdapter(ABC):
    @abstractmethod
    def submit_bundle(self, bundle: str, prev_log_id: Optional[str] = None) -> Tuple[str, str, Any]:
        """
        Submit a signed bundle to the immutable log.

        Args:
            bundle: Serialized bundle JSON string.
            prev_log_id: Optional previous log ID for chain linking.
        Returns:
            Tuple containing (log_id, status, receipt)
        """
        pass

    @abstractmethod
    def get_entry(self, log_id: str) -> Any:
        """
        Get an entry by its ID.
        """
        pass

    @abstractmethod
    def traverse(self, end_log_id: str, count: int = 10) -> list[Any]:
        """
        Traverse backward through the log chain.
        """
        pass

    def find_entries_by_payload_hash(self, payload_hash: str) -> list[Any]:
        """
        Discover immutable-log entries whose DSSE payload hash matches the given value.

        Implementations may use backend-native index APIs or local caches, but callers
        treat the results as predecessor candidates rather than protocol truth.
        """
        return []
