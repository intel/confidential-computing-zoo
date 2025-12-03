import json, os
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from datetime import datetime

from sigstore.sign import SigningContext
from sigstore.oidc import IdentityToken
from sigstore.models import Bundle
from sigstore.verify import Verifier
from sigstore.verify.policy import VerificationPolicy

@dataclass
class ChainEntry:
    sequence_number: int
    timestamp: str
    previous_hash: Optional[str]
    current_hash: str
    data: Dict[str, Any]
    signature_log_index: int

@dataclass
class VerificationResult:
    success: bool
    chain_id: str
    verified_entries: int
    total_entries: int
    errors: List[str]
    details: Dict[str, Any]

@dataclass
class SingleEntryVerificationResult:
    success: bool
    errors: List[str]
    details: Dict[str, Any]

class ChainedTransparencyLog:
    """Transparent log with chain authentication support"""

    def __init__(self, identity_token: Optional[IdentityToken] = None, chain_id: Optional[str] = None):
        self._pending_entries = {}
        self._identity_token = identity_token
        self._chain_id = chain_id or self._generate_chain_id()
        self._chain_history: List[ChainEntry] = []
        self._current_sequence = 0
        self._last_signature_hash: Optional[str] = None

    def set_identity_token(self, identity_token: IdentityToken) -> None:
        """
        Set or update the identity token for the log

        Args:
            identity_token: The identity token to set

        Raises:
            ValueError: If identity_token is None
        """
        if identity_token is None:
            raise ValueError("Identity token cannot be None")

        self._identity_token = identity_token

    @classmethod
    def from_backup_file(cls, backup_file_path: str, identity_token: Optional[IdentityToken] = None) -> 'ChainedTransparencyLog':
        """
        Construct a ChainedTransparencyLog instance from a backup file

        Args:
            backup_file_path: Backup file path
            identity_token: Identity token (optional)

        Returns:
            ChainedTransparencyLog: Instance restored from backup file

        Raises:
            FileNotFoundError: Backup file not found
            ValueError: Invalid backup file format
        """
        try:
            with open(backup_file_path, 'r', encoding='utf-8') as f:
                chain_data = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Backup file not found: {backup_file_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format in backup file: {e}")
        
        # Validate required fields
        required_fields = ['chain_id', 'chain_history', 'current_state']
        for field in required_fields:
            if field not in chain_data:
                raise ValueError(f"Missing required field in backup file: {field}")
        
        # Create instance
        instance = cls(identity_token=identity_token, chain_id=chain_data['chain_id'])
        
        # Restore chain history
        try:
            instance._chain_history = [
                ChainEntry(**entry) for entry in chain_data['chain_history']
            ]
        except TypeError as e:
            raise ValueError(f"Invalid chain history format: {e}")
        
        # Restore current state
        current_state = chain_data['current_state']
        required_state_fields = ['sequence_number', 'last_signature_hash', 'pending_entries']
        for field in required_state_fields:
            if field not in current_state:
                raise ValueError(f"Missing required field in current_state: {field}")
        
        instance._current_sequence = current_state['sequence_number']
        instance._last_signature_hash = current_state['last_signature_hash']
        instance._pending_entries = current_state['pending_entries']
        
        # Validate chain integrity
        if not instance.verify_chain_integrity():
            raise ValueError("Chain integrity verification failed after restoration")
        
        return instance

    @classmethod
    def from_backup_file_safe(cls, backup_file_path: str, identity_token: Optional[IdentityToken] = None) -> Optional['ChainedTransparencyLog']:
        """
        Safely construct an instance from a backup file,
        returning None on failure instead of raising an exception.
        
        Args:
            backup_file_path: Backup file path
            identity_token: Identity token (optional)

        Returns:
            ChainedTransparencyLog or None: Instance restored from backup file or None on failure
        """
        try:
            return cls.from_backup_file(backup_file_path=backup_file_path, identity_token=identity_token)
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            return None

    def save_to_backup_file(self, backup_file_path: str):
        """
        Save the current chain state to a backup file
        
        Args:
            backup_file_path: Backup file path
        """
        chain_data = self.export_chain()

        # Ensure directory exists
        backup_path = Path(backup_file_path)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(backup_file_path, 'w', encoding='utf-8') as f:
            json.dump(chain_data, f, ensure_ascii=False)

    def _generate_chain_id(self) -> str:
        """Generate a unique chain ID"""
        timestamp = datetime.now().isoformat()
        return hashlib.sha256(f"{timestamp}_{id(self)}".encode()).hexdigest()[:16]

    def _calculate_content_hash(self, content: bytes) -> str:
        """Calculate the SHA256 hash of the content"""
        return hashlib.sha256(content).hexdigest()

    def sign_pending_entries(self) -> Bundle:
        """
        Sign the pending entries list and submit to transparency log

        Returns:
            Bundle: A Sigstore bundle
        """
        if not self._pending_entries:
            raise ValueError("No pending entries to sign")
        if not self._identity_token:
            raise ValueError("Identity token is not set")

        # Create chain payload
        serialized_entries = json.dumps(self._pending_entries).encode('utf-8')

        signing_ctx = SigningContext.production()
        with signing_ctx.signer(self._identity_token, cache=True) as signer:
            signing_result = signer.sign_artifact(serialized_entries)

            # Calculate the hash of the current signature content
            current_hash = self._calculate_content_hash(serialized_entries)

            # Create chain entry
            chain_entry = ChainEntry(
                sequence_number=self._current_sequence,
                timestamp=datetime.now().isoformat(),
                previous_hash=self._last_signature_hash,
                current_hash=current_hash,
                data=self._pending_entries.copy(),
                signature_log_index=self._extract_log_index(signing_result)
            )

            # Update chain state
            self._chain_history.append(chain_entry)
            self._last_signature_hash = current_hash
            self._current_sequence += 1

            # Clear pending entries
            self.clear_pending_entries()

            return signing_result

    def _extract_log_index(self, bundle: Bundle) -> int:
        """Extract unique identifier from Bundle"""
        return bundle.log_entry.log_index

    def sign_file_with_chain(self, file_path: str, metadata: Optional[Dict[str, Any]] = None) -> Bundle:
        """
        Add file to the chain and sign it
        
        Args:
            file_path: Path to the file
            metadata: Optional metadata

        Returns:
            Bundle: Sigstore bundle
        """
        file_content = Path(file_path).read_bytes()
        file_hash = self._calculate_content_hash(file_content)

        entry_data = {
            "file_path": file_path,
            "file_hash": file_hash,
            "file_size": len(file_content),
            "metadata": metadata or {}
        }

        self.add_entry({f"file_{self._current_sequence}": entry_data})
        return self.sign_pending_entries()

    def sign_file(self, file_path: str) -> Bundle:
        """
        Sign the specified file and submit to transparency log
        
        Args:
            file_path: Path to the file to be signed
            
        Returns:
            Bundle: A Sigstore bundle
        """
        if not self._identity_token:
            raise ValueError("Identity token is not set")

        file_content = Path(file_path).read_bytes()

        signing_ctx = SigningContext.production()
        with signing_ctx.signer(self._identity_token, cache=True) as signer:
            signing_result = signer.sign_artifact(file_content)
            return signing_result

    def add_entry(self, entry_data: dict) -> dict:
        """
        Add entry to the pending signature list
        
        Args:
            entry_data: Entry data to be added
            
        Returns:
            dict: Updated pending entries list
        """
        self._pending_entries.update(entry_data)
        return self._pending_entries

    def clear_pending_entries(self):
        """Clear all pending entries from the signature list"""
        self._pending_entries = {}

    def verify_chain_integrity(self) -> bool:
        """Verify chain integrity"""
        if not self._chain_history:
            return True
            
        for i, entry in enumerate(self._chain_history):
            # Verify sequence number
            if entry.sequence_number != i:
                return False

            # Verify previous hash
            if i > 0:
                expected_previous = self._chain_history[i-1].current_hash
                if entry.previous_hash != expected_previous:
                    return False
            else:
                if entry.previous_hash is not None:
                    return False
        return True

    def verify_chain(self, sigstore_file_list: List, policy: VerificationPolicy) -> VerificationResult:
        """
        Verify the entire chain using the provided Sigstore files and policy
        
        Args:
            chain_file: Chain file path (e.g. chain.sigstore.json)
            sigstore_file_list: Sigstore file list (e.g. ["entry1_568145964.sigstore.json", ...])
            policy: Verification policy

        Returns:
            VerificationResult: Verification result
        """
        errors = []
        verified_entries = 0
        total_entries = len(self._chain_history)

        try:
            print(f"Verifying chain {self._chain_id} with {total_entries} entries...")

            # 1. Verify chain integrity
            if not self.verify_chain_integrity():
                errors.append("Chain integrity verification failed")
            
            # 2. Crate mapping from sigstore files
            sigstore_file_map = self._create_sigstore_file_mapping(sigstore_file_list)

            # 3. Verify each entry in order
            for i, entry in enumerate(self._chain_history):
                print(f"Verifying entry {i + 1}/{total_entries} (sequence: {entry.sequence_number})...")
                
                try:
                    # Verify single entry
                    entry_result = self._verify_single_entry(entry, sigstore_file_map, policy)
                    if entry_result.success:
                        verified_entries += 1
                        print(f"✓ Entry {i + 1} verified successfully")
                    else:
                        errors.extend([f"Entry {i + 1}: {error}" for error in entry_result.errors])
                        print(f"✗ Entry {i + 1} verification failed")
                        
                except Exception as e:
                    error_msg = f"Entry {i + 1} verification error: {str(e)}"
                    errors.append(error_msg)
                    print(f"✗ {error_msg}")

            # 4. Generate verification result
            success = len(errors) == 0 and verified_entries == total_entries
            
            result = VerificationResult(
                success=success,
                chain_id=self._chain_id,
                verified_entries=verified_entries,
                total_entries=total_entries,
                errors=errors,
                details={
                    "chain_integrity_valid": self.verify_chain_integrity(),
                    "all_signatures_valid": verified_entries == total_entries,
                    "verification_summary": f"{verified_entries}/{total_entries} entries verified",
                    "chain_summary": self.get_chain_summary()
                }
            )
            
            if success:
                print(f"🎉 Chain verification completed successfully! All {total_entries} entries verified.")
            else:
                print(f"❌ Chain verification failed. {verified_entries}/{total_entries} entries verified.")
                for error in errors:
                    print(f"   - {error}")
            
            return result
            
        except Exception as e:
            return VerificationResult(
                success=False,
                chain_id=self._chain_id,
                verified_entries=verified_entries,
                total_entries=total_entries,
                errors=[f"Chain verification error: {str(e)}"],
                details={}
            )

    def _create_sigstore_file_mapping(self, sigstore_file_list: List[str]) -> Dict[str, Dict[str, str]]:
        """Create a mapping from signature_log_index to sigstore and json files"""
        mapping = {}
        
        for sigstore_file in sigstore_file_list:
            try:
                # Extract information from filename
                # Example: "entry1_568145964.sigstore.json" -> entry1, 568145964
                filename = Path(sigstore_file).stem  # Remove extension
                if filename.endswith('.sigstore'):
                    filename = filename[:-9]  # Remove '.sigstore'
                
                parts = filename.split('_')
                if len(parts) >= 2:
                    entry_prefix = '_'.join(parts[:-1])
                    log_index = parts[-1]
                    
                    wkpath = sigstore_file.parent
                    json_file = f"{wkpath}/{entry_prefix}.json"
                    
                    mapping[log_index] = {
                        'sigstore_file': sigstore_file,
                        'json_file': json_file,
                        'entry_prefix': entry_prefix
                    }
            except (ValueError, IndexError) as e:
                print(f"⚠️  Warning: Could not parse sigstore file name {sigstore_file}: {e}")
        
        return mapping

    def _verify_single_entry(self, entry: ChainEntry, sigstore_file_map: Dict[str, Dict[str, str]], 
                            policy) -> SingleEntryVerificationResult:
        """Validate a single chain entry"""
        errors = []
        # signature_log_index
        try:
            signature_log_index = entry.signature_log_index
            if not signature_log_index:
                return SingleEntryVerificationResult(
                    success=False,
                    errors=["Missing signature_log_index in entry"],
                    details={}
                )

            # Find matching files
            # Since signature_log_index may be part of a hash, we need to find matching files
            matched_files = None
            for log_index, file_info in sigstore_file_map.items():
                # Check if signature_log_index is contained in the filename, or vice versa
                if (str(signature_log_index) in log_index or 
                    log_index in str(signature_log_index) or
                    str(signature_log_index) == log_index):
                    matched_files = file_info
                    break

            if not matched_files:
                return SingleEntryVerificationResult(
                    success=False,
                    errors=[f"No sigstore file found for signature_log_index {signature_log_index} or sequence {entry.sequence_number}"],
                    details={}
                )

            sigstore_file = matched_files['sigstore_file']
            json_file = matched_files['json_file']
            
            if not Path(sigstore_file).exists():
                errors.append(f"Sigstore file not found: {sigstore_file}")
            
            if not Path(json_file).exists():
                errors.append(f"JSON file not found: {json_file}")
            
            if errors:
                return SingleEntryVerificationResult(success=False, errors=errors, details={})
            
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                
                if json_data != entry.data:
                    errors.append("JSON file content does not match chain entry data")
                    errors.append(f"Expected: {entry.data}")
                    errors.append(f"Found in file: {json_data}")
            except Exception as e:
                errors.append(f"Error reading JSON file {json_file}: {e}")
            
            if errors:
                return SingleEntryVerificationResult(success=False, errors=errors, details={})
            
            # Verify that the calculated hash matches
            try:
                calculated_hash = self._calculate_content_hash(
                    json.dumps(entry.data).encode('utf-8')
                )
                if calculated_hash != entry.current_hash:
                    errors.append(f"Hash mismatch: calculated {calculated_hash}, stored {entry.current_hash}")
            except Exception as e:
                errors.append(f"Error calculating hash: {e}")
            
            if errors:
                return SingleEntryVerificationResult(success=False, errors=errors, details={})

            # Use Sigstore to verify the signature
            try:
                verifier = Verifier.production()
                print(f"Verifying using sigstore file: {sigstore_file} and json file: {json_file}")
                json_content = Path(json_file).read_bytes()
                sigstore_content = Path(sigstore_file).read_bytes()
                
                verifier.verify_artifact(
                    json_content,
                    Bundle.from_json(sigstore_content),
                    policy
                )
                
                return SingleEntryVerificationResult(
                    success=True,
                    errors=[],
                    details={
                        "sequence_number": entry.sequence_number,
                        "signature_log_index": signature_log_index,
                        "sigstore_file": sigstore_file,
                        "json_file": json_file,
                        "timestamp": entry.timestamp,
                        "current_hash": entry.current_hash
                    }
                )
                
            except Exception as e:
                return SingleEntryVerificationResult(
                    success=False,
                    errors=[f"Sigstore verification failed: {str(e)}"],
                    details={}
                )
                
        except Exception as e:
            return SingleEntryVerificationResult(
                success=False,
                errors=[f"Entry verification error: {str(e)}"],
                details={}
            )

    def get_verification_summary(self) -> Dict[str, Any]:
        """Get summary information related to verification"""
        return {
            "chain_id": self._chain_id,
            "total_entries": len(self._chain_history),
            "chain_integrity": self.verify_chain_integrity(),
            "entries_details": [
                {
                    "sequence_number": entry.sequence_number,
                    "timestamp": entry.timestamp,
                    "signature_log_index": entry.signature_log_index,
                    "current_hash": entry.current_hash,
                    "data_keys": list(entry.data.keys()) if isinstance(entry.data, dict) else "non-dict"
                }
                for entry in self._chain_history
            ]
        }

    def get_chain_summary(self) -> Dict[str, Any]:
        """Get chain summary"""
        return {
            "chain_id": self._chain_id,
            "total_entries": len(self._chain_history),
            "current_sequence": self._current_sequence,
            "last_signature_hash": self._last_signature_hash,
            "chain_integrity": self.verify_chain_integrity(),
            "pending_entries_count": len(self._pending_entries)
        }

    def export_chain(self) -> Dict[str, Any]:
        """Export complete chain data"""
        return {
            "chain_id": self._chain_id,
            "chain_history": [asdict(entry) for entry in self._chain_history],
            "current_state": {
                "sequence_number": self._current_sequence,
                "last_signature_hash": self._last_signature_hash,
                "pending_entries": self._pending_entries
            }
        }

    def import_chain(self, chain_data: Dict[str, Any]):
        """Import chain data to continue an existing chain"""
        self._chain_id = chain_data["chain_id"]
        self._chain_history = [
            ChainEntry(**entry) for entry in chain_data["chain_history"]
        ]
        current_state = chain_data["current_state"]
        self._current_sequence = current_state["sequence_number"]
        self._last_signature_hash = current_state["last_signature_hash"]
        self._pending_entries = current_state["pending_entries"]

    @property
    def pending_entries(self) -> dict:
        """Get current pending entries"""
        return self._pending_entries.copy()

    @property
    def has_pending_entries(self) -> bool:
        """Check if there are any pending entries"""
        return bool(self._pending_entries)

    @property
    def chain_length(self) -> int:
        """Get chain length"""
        return len(self._chain_history)

    @property
    def chain_id(self) -> str:
        """Get chain ID"""
        return self._chain_id
