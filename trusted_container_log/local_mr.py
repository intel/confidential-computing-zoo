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
    Adapter for Intel TDX RTMRs using the Linux TSM sysfs interface.
    Assuming typical sysfs paths like /sys/kernel/tsm/rtmr*/
    """
    def __init__(self, sysfs_base_path: str = "/sys/kernel/tsm/rtmr"):
        self.sysfs_base_path = sysfs_base_path

    def _get_val_path(self, index: int) -> str:
        # Example pattern: /sys/kernel/tsm/rtmr0/val or /sys/kernel/tsm/rtmr/0/val
        # Adjust as per specific kernel interface
        return os.path.join(self.sysfs_base_path, str(index), "val")
        
    def _get_extend_path(self, index: int) -> str:
        return os.path.join(self.sysfs_base_path, str(index), "extend")

    def read(self, index: int) -> str:
        path = self._get_val_path(index)
        if not os.path.exists(path):
            raise FileNotFoundError(f"TDX TSM sysfs missing at {path}. Hardware unsupported or missing permissions.")
            
        try:
            with open(path, "r") as f:
                return f.read().strip()
        except PermissionError:
            raise PermissionError(f"Insufficient permissions to read TDX RTMR sysfs at {path}")
        except Exception as e:
            logger.error(f"Error reading from {path}: {e}")
            raise

    def extend(self, index: int, digest: str) -> Tuple[str, str]:
        # Strip potential known prefixes
        if digest.startswith("sha384:"):
            digest = digest[8:]
            
        path = self._get_extend_path(index)
        if not os.path.exists(path):
            raise FileNotFoundError(f"TDX TSM extend sysfs missing at {path}")
            
        try:
            # Read previous matching TPM/TDX extend logic:
            # extend(digest) typically means writing binary or hex digest to sysfs
            prev_val = self.read(index)
            
            with open(path, "w") as f:
                f.write(digest)
                
            new_val = self.read(index)
            return (new_val, prev_val)
        except PermissionError:
            raise PermissionError(f"Insufficient permissions to extend TDX RTMR sysfs at {path}")
        except Exception as e:
            logger.error(f"Error extending {path} with digest {digest}: {e}")
            raise
