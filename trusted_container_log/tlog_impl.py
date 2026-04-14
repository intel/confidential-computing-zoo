from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple
import json
import logging
from sigstore.models import Bundle

logger = logging.getLogger(__name__)

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

class SigstoreLogAdapter(ImmutableLogAdapter):
    def __init__(self, rekor_url: str = "https://rekor.sigstore.dev"):
        self.rekor_url = rekor_url
        
    def submit_bundle(self, bundle: Bundle, prev_log_id: Optional[str] = None) -> Tuple[str, str, Any]:
        # Here we instantiate the RekorClient internally to actually submit
        try:
            from sigstore._internal.rekor.client import RekorClient
            client = RekorClient(self.rekor_url)
            
            # Reconstruct the mocked request that sign_dsse would normally do
            entry = client.log.entries.post(bundle=bundle)
            
            # The returned entry is typically a single-item dict with UUID as key
            if entry and isinstance(entry, dict) and len(entry) > 0:
                uuid = list(entry.keys())[0]
                return uuid, "confirmed", entry[uuid]
            
            return "unknown-id", "pending", {}
            
        except Exception as e:
            logger.error(f"Failed to submit bundle to Rekor: {e}")
            raise

    def get_entry(self, log_id: str) -> Any:
        try:
            from sigstore._internal.rekor.client import RekorClient
            client = RekorClient(self.rekor_url)
            entry = client.log.entries.get(log_id)
            return entry
        except Exception as e:
            logger.error(f"Failed to get entry {log_id} from Rekor: {e}")
            raise

    def traverse(self, end_log_id: str, count: int = 10) -> list[Any]:
        results = []
        current_id = end_log_id
        
        try:
            from sigstore._internal.rekor.client import RekorClient
            client = RekorClient(self.rekor_url)
            
            for _ in range(count):
                if not current_id:
                    break
                    
                entry = client.log.entries.get(current_id)
                if not entry:
                    break
                    
                # Store the entry itself (it's returned as a dict with current_id as key)
                val = list(entry.values())[0] if isinstance(entry, dict) and len(entry) > 0 else entry
                results.append(val)
                
                # Extract previous link depending on the type of entry
                # hashedrekord entries have different structures than dsse
                body = val.get("body", {})
                if isinstance(body, str):
                    try:
                        import base64
                        body = json.loads(base64.b64decode(body).decode('utf-8'))
                    except Exception:
                        pass
                
                # DSSE or intoto
                dsse_payload = body.get("spec", {}).get("payload")
                if isinstance(dsse_payload, str):
                    try:
                        import base64
                        payload = json.loads(base64.b64decode(dsse_payload).decode('utf-8'))
                        predicate = payload.get("predicate", {})
                        
                        # Fallback parsing handling how we created it 
                        if "prev_log_id" in predicate:
                            current_id = predicate.get("prev_log_id")
                        elif "prev_log_id" in payload:
                            current_id = payload.get("prev_log_id")
                        else:
                            current_id = None
                            
                    except Exception as e:
                        logger.warning(f"Could not parse payload for link: {e}")
                        current_id = None
                else:
                    # Generic fallback if not dsse
                    current_id = None

        except Exception as e:
            logger.error(f"Traverse hit an error: {e}")
            
        return results
