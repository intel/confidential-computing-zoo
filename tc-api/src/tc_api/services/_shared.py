import asyncio
import re
from pathlib import Path
import base64
import subprocess
import uuid
import os
import json
import logging
import time, random
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from ..models import BuildResult, LaunchResult, PublishResult, TransparencyResult, LunksResult
from ..config import *
import hashlib
from sigstore.oidc import Issuer
from sigstore.verify.verifier import Verifier
from sigstore.verify import policy
from sigstore.models import Bundle
from sigstore import hashes as sigstore_hashes
from ..trust.commit_client import TrustedLogAPI
from tlog.types import Entry
from pathlib import Path
from sigstore.verify import policy

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def save_file_async(file_path: str, content: str):
    directory = os.path.dirname(file_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    def write_file():
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, write_file)
def validate_filenames(file_dict: Dict[str, str], file_type: str, pattern: str, format_description: str):
    """
    Validate filename formats in the file dictionary

    Args:
        file_dict: File dictionary with filename as key and content as value
        file_type: File type description (e.g., "raw", "bundle", "chain")
        pattern: Regular expression pattern for validation
        format_description: Format description (e.g., "*.json", "entry*.sigstore.json", "chain.sigstore.json")

    Raises:
        ValueError: If filename format does not meet requirements
    """
    invalid_files = []

    for filename in file_dict.keys():
        if not re.match(pattern, filename):
            invalid_files.append(filename)

    if invalid_files:
        # Generate different examples based on file type
        if file_type.lower() == "raw":
            examples = "manifest.json, signature.json, metadata.json"
        elif file_type.lower() == "bundle":
            examples = "entry1.sigstore.json, entry_abc.sigstore.json, entry123.sigstore.json"
        elif file_type.lower() == "chain":
            examples = "chain.sigstore.json"
        else:
            examples = "please refer to the corresponding format requirements"

        raise ValueError(
            f"{file_type.capitalize()} file name format error. The following filenames do not conform to '{format_description}' format: {invalid_files}\n"
            f"Correct format examples: {examples}"
        )

    logger.info(f"{file_type.capitalize()} filename format validation passed, total {len(file_dict)} files")
