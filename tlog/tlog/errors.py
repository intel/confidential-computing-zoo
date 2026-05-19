from dataclasses import dataclass
from typing import Any, Dict, Optional

@dataclass
class TrustedLogError(Exception):
    code: str
    message: str
    stage: str
    retryable: bool
    details: Optional[Dict[str, Any]] = None

class RecordNotFoundError(TrustedLogError):
    pass

class BackendSubmitError(TrustedLogError):
    pass

class VerificationError(TrustedLogError):
    pass
