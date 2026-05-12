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
