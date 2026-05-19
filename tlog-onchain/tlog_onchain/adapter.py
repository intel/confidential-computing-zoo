from typing import Any, Optional, Tuple

from tlog.immutable import ImmutableLogAdapter


class OnChainLogAdapter(ImmutableLogAdapter):
    """Placeholder on-chain backend for ImmutableLogAdapter.

    This adapter will be implemented when on-chain log support is added.
    """

    def submit_bundle(self, bundle: str, prev_log_id: Optional[str] = None) -> Tuple[str, str, Any]:
        raise NotImplementedError("On-chain log adapter is not yet implemented")

    def get_entry(self, log_id: str) -> Any:
        raise NotImplementedError("On-chain log adapter is not yet implemented")

    def traverse(self, end_log_id: str, count: int = 10) -> list[Any]:
        raise NotImplementedError("On-chain log adapter is not yet implemented")

    def find_entries_by_payload_hash(self, payload_hash: str) -> list[Any]:
        raise NotImplementedError("On-chain log adapter is not yet implemented")
