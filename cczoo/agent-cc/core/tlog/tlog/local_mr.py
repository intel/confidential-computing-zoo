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
from typing import Tuple


class LocalMRAdapter(ABC):
    @abstractmethod
    def read(self, index: int) -> str:
        """
        Reads the measurement register value.
        Args:
            index (int): Register index to read
        Returns:
            str: Hex digest of the register value
        """
        pass

    @abstractmethod
    def extend(self, index: int, digest: str) -> Tuple[str, str]:
        """
        Extends the given measurement register with a new digest.
        Args:
            index (int): Register index to extend
            digest (str): Digest to extend the register with (e.g. hex string)
        Returns:
            Tuple[str, str]: Tuple of (new_mr_value, prev_mr_value)
        """
        pass
