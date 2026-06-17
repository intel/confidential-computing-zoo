# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import logging
import os
import subprocess
import time
from datetime import datetime
from typing import Optional, Tuple

from ..config import (
    COSIGN_CMD,
    SKOPEO_CMD,
)
from ..models import PublishResult
from ..transparency.commit_client import TrustedLogAPI
from ..transparency.events import publish_identity_entries
from ..utils.registry import canonical_registry_ref
from tlog.types import Entry

logger = logging.getLogger(__name__)


class PublishServiceMixin:
    def sign_image(self, image_name: str, private_key_path: str, tlog: TrustedLogAPI, record_id: str) -> Tuple[bool, Optional[str]]:
        """
        Sign image with cosign with enhanced validation. Handles remote registry images.
        
        Args:
            image_name: Image name/reference. If not a full registry path, it will be constructed
            private_key_path: Path to the cosign private key for signing
            
        Returns:
            Tuple[bool, Optional[str]]: (success, signature_path)
                - success: True if signing successful, False otherwise
                - signature_path: Full registry reference to the signature if successful, None otherwise
        """
        try:
            # Validate private key exists
            if not os.path.exists(private_key_path):
                logger.error(f"Private key file not found: {private_key_path}")

                signing_log = {
                        "status": "failed",
                        "error": {
                            "type": "FileNotFoundError",
                            "message": f"Private key file not found: {private_key_path}"
                        }
                }
                tlog.add_entry(record_id, Entry(key="image_signing", value=signing_log))

                return False, None
            
            # Sign the same canonical registry ref that launch verification will later check.
            full_image_ref = canonical_registry_ref(image_name)
            
            logger.info(f"Constructed full image reference: {full_image_ref}")
            
            # Set environment to skip password prompt for testing
            env = os.environ.copy()
            env['COSIGN_PASSWORD'] = ''  # Empty password for testing keys
            
            cmd = [COSIGN_CMD, "sign", "--key", private_key_path, full_image_ref, "--yes"]
            
            logger.info(f"Signing image: {full_image_ref}")
            logger.debug(f"Sign command: {' '.join(cmd[:4])} [key-file] {full_image_ref} --yes")
            
            result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
            
            if result.returncode == 0:
                logger.info(f"Successfully signed image {full_image_ref}")
                # Signature reference follows cosign format: registry/repo/image:tag.sig
                signature_ref = f"{full_image_ref}.sig"
                
                signing_log = {
                    "command": " ".join(cmd),
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "private_key_path": private_key_path,
                    "signature_ref": signature_ref,
                    "status": "success"
                }
                tlog.add_entry(record_id, Entry(key="image_signing", value=signing_log))

                return True, signature_ref
            else:
                logger.error(f"Failed to sign image: {result.stderr}")
                logger.debug(f"Sign stdout: {result.stdout}")
                
                signing_log = {
                    "command": " ".join(cmd),
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "private_key_path": private_key_path,
                    "status": "failed",
                    "error": {
                        "type": "subprocess.CalledProcessError",
                        "message": result.stderr
                    }
                }
                tlog.add_entry(record_id, Entry(key="image_signing", value=signing_log))

                return False, None
                
        except subprocess.TimeoutExpired:
            logger.error(f"Image signing timed out for: {image_name}")
            
            signing_log = {
                "command": " ".join(cmd),
                "status": "timeout",
                "error": {
                    "type": "subprocess.TimeoutExpired",
                    "message": f"Image signing timed out for: {image_name}"
                }
            }
            tlog.add_entry(record_id, Entry(key="image_signing", value=signing_log))

            return False, None
        except FileNotFoundError:
            logger.error(f"Cosign command not found: {COSIGN_CMD}")
            
            signing_log = {
                "status": "failed",
                "error": {
                    "type": "FileNotFoundError",
                    "message": f"Cosign command not found: {COSIGN_CMD}"
                }
            }
            tlog.add_entry(record_id, Entry(key="image_signing", value=signing_log))

            return False, None
        except Exception as e:
            logger.error(f"Unexpected error signing image: {str(e)}")
            return False, None

    def create_sbom_attestation(self, image_name: str, sbom_path: str, private_key_path: str, tlog: TrustedLogAPI, record_id: str) -> Tuple[bool, Optional[str]]:
        """
        Create and publish SBOM attestation for remote registry images
        
        Args:
            image_name: Image name/reference (e.g., user-id-bld-id or full path)
            sbom_path: Path to the SBOM JSON file
            private_key_path: Path to the cosign private key for signing
            
        Returns:
            Tuple[bool, Optional[str]]: (success, attestation_path)
                - success: True if attestation successful, False otherwise
                - attestation_path: Full registry reference to the SBOM attestation if successful, None otherwise
        """
        try:
            # Validate inputs
            if not os.path.exists(sbom_path):
                logger.error(f"SBOM file not found: {sbom_path}")

                attestation_log = {
                    "status": "failed",
                    "error": {
                        "type": "FileNotFoundError",
                        "message": f"SBOM file not found: {sbom_path}"
                    }
                }
                tlog.add_entry(record_id, Entry(key="sbom_attestation", value=attestation_log))

                return False, None
            
            if not os.path.exists(private_key_path):
                logger.error(f"Private key file not found: {private_key_path}")

                attestation_log = {
                    "status": "failed",
                    "error": {
                        "type": "FileNotFoundError",
                        "message": f"Private key file not found: {private_key_path}"
                    }
                }
                tlog.add_entry(record_id, Entry(key="sbom_attestation", value=attestation_log))

                return False, None
            
            # Validate SBOM content
            try:
                with open(sbom_path, 'r', encoding='utf-8') as f:
                    sbom_data = json.load(f)
                if not sbom_data.get('spdxVersion'):
                    logger.warning("SBOM may be invalid - missing spdxVersion")
            except (json.JSONDecodeError, Exception) as e:
                logger.error(f"Invalid SBOM file: {e}")
                
                attestation_log = {
                    "status": "failed",
                    "error": {
                        "type": "json.JSONDecodeError",
                        "message": f"Invalid SBOM file: {e}"
                    }
                }
                tlog.add_entry(record_id, Entry(key="sbom_attestation", value=attestation_log))

                return False, None
            
            full_image_ref = canonical_registry_ref(image_name)
            
            logger.info(f"Constructed full image reference: {full_image_ref}")
            
            # Set environment for cosign
            env = os.environ.copy()
            env['COSIGN_PASSWORD'] = ''  # Empty password for testing keys
            
            cmd = [
                COSIGN_CMD, "attest",
                "--key", private_key_path,
                "--predicate", sbom_path,
                "--type", "spdx",
                full_image_ref,
                "--yes"
            ]
            
            logger.info(f"Creating SBOM attestation for: {full_image_ref}")
            logger.debug(f"Attest command: {' '.join(cmd[:6])} [key-file] --predicate [sbom-file] --type spdx {full_image_ref} --yes")
            
            result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
            
            if result.returncode == 0:
                logger.info(f"Successfully created SBOM attestation for {full_image_ref}")
                # Attestation reference follows cosign format: registry/repo/image:tag.att.<type>
                attestation_ref = f"{full_image_ref}.att.sbom"
                
                attestation_log = {
                    "command": " ".join(cmd),
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "validation": {
                        "spdx_version_present": bool(sbom_data.get('spdxVersion')),
                        "is_valid_json": True
                    },
                    "input_files": {
                        "sbom_path": sbom_path,
                        "private_key_path": private_key_path
                    },
                    "output_ref": attestation_ref,
                    "status": "success"
                }
                tlog.add_entry(record_id, Entry(key="sbom_attestation", value=attestation_log))

                return True, attestation_ref
            else:
                logger.error(f"Failed to create SBOM attestation: {result.stderr}")
                logger.debug(f"Attestation stdout: {result.stdout}")
                
                attestation_log = {
                    "command": " ".join(cmd),
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "validation": {
                        "spdx_version_present": bool(sbom_data.get('spdxVersion')),
                        "is_valid_json": True
                    },
                    "input_files": {
                        "sbom_path": sbom_path,
                        "private_key_path": private_key_path
                    },
                    "status": "failed",
                    "error": {
                        "type": "subprocess.CalledProcessError",
                        "message": result.stderr
                    }
                }
                tlog.add_entry(record_id, Entry(key="sbom_attestation", value=attestation_log))

                return False, None
                
        except subprocess.TimeoutExpired:
            logger.error(f"SBOM attestation timed out for: {image_name}")
            
            attestation_log = {
                "command": " ".join(cmd),
                "status": "timeout",
                "error": {
                    "type": "subprocess.TimeoutExpired",
                    "message": f"SBOM attestation timed out for: {image_name}"
                }
            }
            tlog.add_entry(record_id, Entry(key="sbom_attestation", value=attestation_log))

            return False, None
        except FileNotFoundError:
            logger.error(f"Cosign command not found: {COSIGN_CMD}")
            
            attestation_log = {
                "status": "failed",
                "error": {
                    "type": "FileNotFoundError",
                    "message": f"Cosign command not found: {COSIGN_CMD}"
                }
            }
            tlog.add_entry(record_id, Entry(key="sbom_attestation", value=attestation_log))

            return False, None
        except Exception as e:
            logger.error(f"Unexpected error creating SBOM attestation: {str(e)}")
            return False, None

    def push_image(self, source_ref: str, dest_ref: str, tlog: TrustedLogAPI, record_id: str, max_retries: int = 3, retry_delay: int = 5) -> bool:
        """
        Push image using skopeo copy with retry mechanism.
        
        Args:
            source_ref: Complete source reference (e.g., 'oci:/path:tag' or 'docker-daemon:image:tag')
            dest_ref: Complete destination reference (e.g., 'docker://registry/repo:tag')
                For registry destinations, format should be: docker://registry/repository:tag
            max_retries: Maximum number of retry attempts (default: 3)
            retry_delay: Delay between retries in seconds (default: 5)
            
        Returns:
            bool: True if push successful, False otherwise
        """

        # Extract image name for registry destination
        def extract_image_name(ref: str) -> str:
            # Normalize transport prefixes before deriving the publish target name.
            normalized_ref = ref
            if normalized_ref.startswith('oci:'):
                normalized_ref = normalized_ref[4:]
            elif normalized_ref.startswith('docker-daemon:'):
                normalized_ref = normalized_ref[len('docker-daemon:'):]

            parts = normalized_ref.split('/')
            image_name = parts[-1]
            if ':' not in image_name:
                image_name += ':latest-encrypted'
            return image_name
            
        # Fix source reference format if it's an OCI reference
        if source_ref.startswith('oci:'):
            # Remove any duplicate 'oci:' prefixes
            source_ref = 'oci:' + source_ref.replace('oci:', '')
            
        # Fix destination reference format for registry while preserving repository path.
        if dest_ref.startswith('docker://'):
            destination_path = dest_ref[len('docker://'):]
            path_parts = destination_path.split('/')
            registry = path_parts[0]
            repository_parts = path_parts[1:-1]
            image_name = extract_image_name(source_ref)
            repository_prefix = '/'.join(repository_parts)
            if repository_prefix:
                dest_ref = f"docker://{registry}/{repository_prefix}/{image_name}"
            else:
                dest_ref = f"docker://{registry}/{image_name}"

        insecure_local_registry = dest_ref.startswith("docker://localhost:") or dest_ref.startswith("docker://127.0.0.1:")
        attempt = 0
        while attempt < max_retries:
            try:
                attempt += 1
                logger.info(f"Pushing image (attempt {attempt}/{max_retries}): {source_ref} -> {dest_ref}")
                
                cmd = [SKOPEO_CMD, "copy", source_ref, dest_ref]
                if insecure_local_registry:
                    cmd.insert(2, "--dest-tls-verify=false")
                logger.debug(f"Push command: {' '.join(cmd)}")

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                
                if result.returncode == 0:
                    logger.info(f"Successfully pushed image to {dest_ref}")
                    
                    push_log = {
                        "command": " ".join(cmd),
                        "exit_code": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "retry_attempts": attempt,
                        "max_retries": max_retries,
                        "retry_delay": retry_delay,
                        "source_ref": source_ref,
                        "dest_ref": dest_ref,
                        "status": "success"
                    }
                    tlog.add_entry(record_id, Entry(key="image_push", value=push_log))
                    self.add_tlog_entries(
                        tlog,
                        record_id,
                        publish_identity_entries(
                            pushed_subject_digest=self._resolve_image_digest(source_ref.replace("oci:", "").replace("docker-daemon:", "")),
                            target_ref=dest_ref,
                            publish_status="success",
                        ),
                    )

                    return True
                else:
                    logger.warning(f"Push attempt {attempt} failed: {result.stderr}")
                    logger.debug(f"Push stdout: {result.stdout}")
                    
                    if attempt < max_retries:
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"All push attempts failed after {max_retries} tries")
                        
                        push_log = {
                            "command": " ".join(cmd),
                            "exit_code": result.returncode,
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                            "retry_attempts": attempt,
                            "max_retries": max_retries,
                            "retry_delay": retry_delay,
                            "source_ref": source_ref,
                            "dest_ref": dest_ref,
                            "status": "failed",
                            "error": {
                                "type": "subprocess.CalledProcessError",
                                "message": result.stderr
                            }
                        }
                        tlog.add_entry(record_id, Entry(key="image_push", value=push_log))
                        self.add_tlog_entries(
                            tlog,
                            record_id,
                            publish_identity_entries(
                                pushed_subject_digest=None,
                                target_ref=dest_ref,
                                publish_status="failed",
                            ),
                        )

                        return False
                
            except subprocess.TimeoutExpired:
                logger.warning(f"Push attempt {attempt} timed out")
                if attempt < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"All push attempts timed out after {max_retries} tries")
                    
                    push_log = {
                        "command": " ".join(cmd),
                        "retry_attempts": attempt,
                        "max_retries": max_retries,
                        "retry_delay": retry_delay,
                        "source_ref": source_ref,
                        "dest_ref": dest_ref,
                        "status": "timeout",
                        "error": {
                            "type": "subprocess.TimeoutExpired",
                            "message": f"Push attempt {attempt} timed out"
                        }
                    }
                    tlog.add_entry(record_id, Entry(key="image_push", value=push_log))
                    tlog.add_entry(record_id, Entry(key="target_ref", value=dest_ref))
                    tlog.add_entry(record_id, Entry(key="publish_status", value="failed"))

                    return False
            except FileNotFoundError:
                logger.error(f"Skopeo command not found: {SKOPEO_CMD}")
                
                push_log = {
                    "status": "failed",
                    "error": {
                        "type": "FileNotFoundError",
                        "message": f"Skopeo command not found: {SKOPEO_CMD}"
                    }
                }
                tlog.add_entry(record_id, Entry(key="image_push", value=push_log))
                tlog.add_entry(record_id, Entry(key="target_ref", value=dest_ref))
                tlog.add_entry(record_id, Entry(key="publish_status", value="failed"))

                return False  # Don't retry if command not found
            except Exception as e:
                logger.warning(f"Push attempt {attempt} failed with error: {str(e)}")
                if attempt < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"All push attempts failed after {max_retries} tries: {str(e)}")
                    return False
        
        return False

    def get_publish_status(self, build_id: str) -> Optional[PublishResult]:
        """Get publish status by publish_id"""
        publishID = "pub-" + build_id.split("-")[-1]
        return self.publish_results.get(publishID)

    def update_publish_status(self,user_id: str, build_id: str, status: str, publish_id: str, step: str = None, luks_path: str = '', **kwargs):
        try:
            if publish_id in self.publish_results:
                publish_result = self.publish_results[publish_id]
                old_status = publish_result.status
                publish_result.status = status
                publish_result.updated_at = datetime.now()
                
                if step:
                    publish_result.current_step = step
                
                # Log status changes
                if old_status != status:
                    logger.info(f"Publish {publish_id} status: {old_status} -> {status}")
                
                # Update additional fields
                for key, value in kwargs.items():
                    if hasattr(publish_result, key):
                        setattr(publish_result, key, value)
                        logger.debug(f"Updated {key} for publish {publish_id}")
                
                # Trigger cleanup for completed builds
                if status in ['success', 'failed'] and status != old_status:
                    # Clean up in background (keep logs for failed builds)
                    try:
                        keep_logs = (status == 'failed')
                        self.cleanup_build_artifacts(build_id, luks_path,keep_logs=keep_logs)
                    except Exception as e:
                        logger.warning(f"Cleanup failed for build {publish_id}: {e}")
                        
            else:
                # Create new build result
                logger.info(f"Creating new publish status for {publish_id}: {status}")
                self.publish_results[publish_id] = PublishResult(
                    user_id=user_id,
                    publish_id=publish_id,
                    build_id=build_id,
                    status=status,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    **kwargs
                )
                
        except Exception as e:
            logger.error(f"Error updating publish status for {build_id}: {str(e)}")

    async def verify_attestation(self, image_id: str, user_id: str,  tlog: TrustedLogAPI, record_id: str, luks_path: str = '') -> Tuple[str, Optional[str]]:
        """
        Verify attestation and retrieve decryption key if successful
        
        Args:
            image_id: ID of the image to verify
            user_id: ID of the user requesting verification
            
        Returns:
            Tuple[str, Optional[str]]: (attestation_result, decryption_key)
            attestation_result can be "trusted", "untrusted", or "failed"
            decryption_key is None if attestation fails
        """
        try:
            attestation_result, decryption_key = self.get_pubKey_from_KBS(luks_path, tlog, record_id)
            return attestation_result, decryption_key
            
        except Exception as e:
            logger.error(f"Attestation failed: {str(e)}")
            return "failed", None

    def decrypt_image(self, image_id: str, decryption_key: str) -> Optional[str]:
        """
        Decrypt an encrypted container image
        
        Args:
            image_id: ID of the encrypted image
            decryption_key: Key received from KBS after successful attestation
            
        Returns:
            Optional[str]: URL of decrypted image if successful, None otherwise
        """
        try:
            # Create temporary file for decryption key
            key_path = decryption_key
                
            try:
                # Use skopeo to decrypt the image
                encrypted_ref = f"docker://{self.registry}/{image_id}"
                decrypted_ref = f"docker://{self.registry}/{image_id}-decrypted"
                
                cmd = [
                    "skopeo", "copy",
                    "--decryption-key", key_path,
                    encrypted_ref,
                    decrypted_ref
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error(f"Image decryption failed: {result.stderr}")
                    return None
                    
                return decrypted_ref
                
            finally:
                os.unlink(key_path)
                
        except Exception as e:
            logger.error(f"Decryption error: {str(e)}")
            return None

    def verify_sbom(self,imagesurl,sbom_url,tlog: TrustedLogAPI, record_id: str, cosign_pubkey='cosign.pub') -> bool:

        if imagesurl.startswith("oci:"):
            image_path = imagesurl[4:]
            layout_ok = os.path.isdir(image_path) and os.path.exists(os.path.join(image_path, "index.json")) and os.path.exists(os.path.join(image_path, "oci-layout"))
            if not layout_ok:
                tlog.add_entry(record_id, Entry(key="verify_sbom_status", value="failed"))
                tlog.add_entry(record_id, Entry(key="verify_sbom_mode", value="local_oci_layout"))
                return False

            try:
                with open(sbom_url, "r", encoding="utf-8") as handle:
                    sbom_data = json.load(handle)
            except Exception as exc:
                logger.error(f"Failed to load local SBOM {sbom_url}: {exc}")
                tlog.add_entry(record_id, Entry(key="verify_sbom_status", value="failed"))
                tlog.add_entry(record_id, Entry(key="verify_sbom_mode", value="local_oci_layout"))
                return False

            if not isinstance(sbom_data, dict) or not sbom_data.get("spdxVersion"):
                tlog.add_entry(record_id, Entry(key="verify_sbom_status", value="failed"))
                tlog.add_entry(record_id, Entry(key="verify_sbom_mode", value="local_oci_layout"))
                return False

            tlog.add_entry(record_id, Entry(key="verify_sbom_mode", value="local_oci_layout"))
            tlog.add_entry(record_id, Entry(key="verify_sbom_status", value="success"))
            return True

        images_fullName = imagesurl.replace("docker.io/","")
        # 1. verify signed image
        try:
            cosign_cmd = [
                    COSIGN_CMD, "verify", "--key", cosign_pubkey, images_fullName
                ]
            cosign_verify = subprocess.run(cosign_cmd, capture_output=True, text=True)
            logger.info(f"Vertify CMD: {' '.join(cosign_cmd)}")
            tlog.add_entry(record_id, Entry(key="verify_sbom_cmd", value=" ".join(cosign_cmd)))

            if cosign_verify.returncode != 0:
                failure_detail = cosign_verify.stderr.strip() or cosign_verify.stdout.strip() or "cosign verify failed without output"
                logger.warning("Cosign verify failed for %s: %s", images_fullName, failure_detail)
                tlog.add_entry(record_id, Entry(key="verify_sbom_status", value="failed"))
                return False
            tlog.add_entry(record_id, Entry(key="verify_sbom_status", value="success"))

        except Exception as e:
            logger.error(f"Verify signed image {images_fullName} failed: {str(e)}")
            tlog.add_entry(record_id, Entry(key="error", value=f"{e}"))

        #2. verify attestation
        try:
            cosign_attcmd = [
                    COSIGN_CMD, "verify-attestation", "--key", cosign_pubkey, "--type", "spdx", images_fullName]
            
            cosign_attverify = subprocess.run(cosign_attcmd, capture_output=True, text=True)
            logger.info(f"Attestation_Vertify CMD: {' '.join(cosign_attcmd)}")
            tlog.add_entry(record_id, Entry(key="verify_attestation_cmd", value=" ".join(cosign_attcmd)))

            if cosign_attverify.returncode != 0:
                failure_detail = cosign_attverify.stderr.strip() or cosign_attverify.stdout.strip() or "cosign verify-attestation failed without output"
                logger.warning("Cosign verify-attestation failed for %s: %s", images_fullName, failure_detail)
                tlog.add_entry(record_id, Entry(key="verify_attestation_status", value="failed"))
                return False

            ''' base64_str = json.loads(cosign_verify.stdout)
            import base64
            sbomJS = json.loads(base64.b64decode(base64_str['payload']).decode("utf-8"))['predicate']
            decrypted_data = json.loads(sbomJS)
            
            with open(sbom_url,'r') as f:
                data = json.load(f)
            
            if decrypted_data['spdxVersion'] == data['spdxVersion']:
                logger.info(f"Success to verify-attest")
                return True
            else:
                logger.error(f"Failed to verify-attest")
                return False

            for key in sbomJS:
                if key not in data:
                    logger.error(f"Failed to verify-attest: {cosign_verify.stderr}")
                    return False
            '''
            return True
            
        except Exception as e:
            logger.error(f"Verify signed attestation image {imagesurl} failed: {str(e)}")
            tlog.add_entry(record_id, Entry(key="error", value=f"{str(e)}"))


__all__ = ['PublishServiceMixin']
