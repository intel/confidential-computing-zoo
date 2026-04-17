"""
CCEL (CC Event Log) reader and digest computation.

Reads the raw CCEL binary from ACPI tables and computes its SHA-384 digest
for inclusion in Event Log 0 (baseline record).
"""

import hashlib
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

CCEL_ACPI_PATH = "/sys/firmware/acpi/tables/CCEL"


def read_ccel_binary(path: str = CCEL_ACPI_PATH) -> Optional[bytes]:
    """Read the raw CCEL binary from the ACPI tables path.

    Returns None if the file does not exist (non-TEE or no CCEL support).
    """
    if not os.path.exists(path):
        logger.info("CCEL ACPI table not found at %s", path)
        return None
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception as e:
        logger.warning("Failed to read CCEL from %s: %s", path, e)
        return None


def compute_ccel_digest(path: str = CCEL_ACPI_PATH) -> Optional[str]:
    """Compute SHA-384 digest of the raw CCEL binary.

    Returns 'sha384:<hex>' or None if CCEL is not available.
    """
    data = read_ccel_binary(path)
    if data is None:
        return None
    return "sha384:" + hashlib.sha384(data).hexdigest()
