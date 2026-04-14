from abc import ABC, abstractmethod
from typing import Optional, Tuple
import logging
import os
import hashlib

logger = logging.getLogger(__name__)

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

class TdxMRAdapter(LocalMRAdapter):
    """
    Adapter for Intel TDX RTMRs directly utilizing the TDX Guest driver sysfs path.
    """
    def __init__(self, sysfs_base_path: str = "/sys/class/misc/tdx_guest/measurements/rtmr"):
        self.sysfs_base_path = sysfs_base_path

    def _get_path(self, index: int) -> str:
        # Expected pattern: /sys/class/misc/tdx_guest/measurements/rtmr0:sha384
        return f"{self.sysfs_base_path}{index}:sha384"

    def read(self, index: int) -> str:
        path = self._get_path(index)
        if not os.path.exists(path):
            raise FileNotFoundError(f"TDX guest measurements sysfs missing at {path}. Hardware unsupported.")
            
        try:
            with open(path, "rb") as f:
                return f.read().hex()
        except PermissionError:
            raise PermissionError(f"Insufficient permissions to read TDX RTMR sysfs at {path}")
        except Exception as e:
            logger.error(f"Error reading from {path}: {e}")
            raise

    def extend(self, index: int, digest: str) -> Tuple[str, str]:
        # Strip potential known prefixes
        if digest.startswith("sha384:"):
            digest = digest[7:]
            
        path = self._get_path(index)
        if not os.path.exists(path):
            raise FileNotFoundError(f"TDX guest extend sysfs missing at {path}")
            
        try:
            prev_val = self.read(index)
            
            # Convert string to exactly 48 bytes
            try:
                raw_bytes = bytes.fromhex(digest)
            except ValueError:
                raise ValueError(f"Provided digest is not a valid hex string: {digest}")
                
            if len(raw_bytes) != 48:
                raise ValueError(f"TDX RTMR requires exactly 48 bytes (sha384), but got {len(raw_bytes)}")
            
            with open(path, "rb+") as f:
                f.write(raw_bytes)
                
            new_val = self.read(index)
            return (new_val, prev_val)
        except PermissionError:
            raise PermissionError(f"Insufficient permissions to extend TDX RTMR sysfs at {path}")
        except Exception as e:
            logger.error(f"Error extending {path} with digest {digest}: {e}")
            raise
