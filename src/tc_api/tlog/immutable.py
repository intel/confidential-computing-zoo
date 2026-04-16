from abc import ABC, abstractmethod
from typing import Any, Optional, Tuple

from sigstore.models import Bundle


class ImmutableLogAdapter(ABC):
    @abstractmethod
    def submit_bundle(self, bundle: Bundle, prev_log_id: Optional[str] = None) -> Tuple[str, str, Any]:
        """
        Submit a signed bundle to the immutable log.
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
