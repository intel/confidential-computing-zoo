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
from .models import BuildResult, LaunchResult, PublishResult, TransparencyResult, LunksResult
from .config import *
import hashlib
from sigstore.oidc import Issuer
from sigstore.verify.verifier import Verifier
from sigstore.verify import policy
from sigstore.models import Bundle
from sigstore import hashes as sigstore_hashes
from .tlog_client import TrustedLogAPI
from .tlog.types import Entry
from pathlib import Path
from sigstore.verify import policy

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class DockerService:
    def __init__(self):
        self.builds: Dict[str, BuildResult] = {}
        self.launchs: Dict[str, LaunchResult] = {}
        self.publishs: Dict[str, PublishResult] = {}
        self.transparencyLog: Dict[str, TransparencyResult] = {}
        self.lunks: Dict[str, LunksResult] = {}

    def generate_uuid(self, prefix: str = "bld") -> str:
        """
        Generate a unique ID with specified prefix
        
        Args:
            prefix: Prefix for the ID ("bld" for build, "launch" for launch)
            
        Returns:
            str: Generated ID in format "{prefix}-{uuid}"
        """
        return f"{prefix}-{uuid.uuid4().hex[:7]}"

    def normalize_workload_id(self, user_id: str, image_id: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        metadata = metadata or {}
        workload_id = metadata.get("workload_id")
        if isinstance(workload_id, str) and workload_id.strip():
            return workload_id.strip()
        if image_id:
            return image_id.split(":", 1)[0]
        return user_id

    def _sha384_digest(self, payload: str) -> str:
        return "sha384:" + hashlib.sha384(payload.encode("utf-8")).hexdigest()

    def _json_sha384_digest(self, payload: Any) -> str:
        return self._sha384_digest(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))

    def _file_sha384_digest(self, file_path: str) -> str:
        with open(file_path, "rb") as handle:
            return "sha384:" + hashlib.sha384(handle.read()).hexdigest()

    def _directory_sha384_digest(self, directory: str) -> str:
        digest = hashlib.sha384()
        for root, _, files in os.walk(directory):
            for file_name in sorted(files):
                file_path = os.path.join(root, file_name)
                rel_path = os.path.relpath(file_path, directory)
                digest.update(rel_path.encode("utf-8"))
                with open(file_path, "rb") as handle:
                    digest.update(handle.read())
        return "sha384:" + digest.hexdigest()

    def _extract_base_images(self, dockerfile_content: str) -> list[str]:
        base_images = []
        for line in dockerfile_content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.upper().startswith("FROM "):
                ref = stripped.split()[1]
                if ref not in base_images:
                    base_images.append(ref)
        return base_images

    def _resolve_image_digest(self, image_ref: str) -> str:
        try:
            cmd = [DOCKER_CMD, "image", "inspect", image_ref, "--format", "{{json .RepoDigests}}"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                repo_digests = json.loads(result.stdout.strip())
                if isinstance(repo_digests, list) and repo_digests:
                    digest_ref = repo_digests[0]
                    if "@" in digest_ref:
                        return digest_ref.split("@", 1)[1]
        except Exception as exc:
            logger.debug("Falling back to synthetic digest for %s: %s", image_ref, exc)
        return self._sha384_digest(image_ref)

    def _build_launch_security_projection(self, launch_id: str, workload_id: str) -> Dict[str, Any]:
        mounts = [
            "/etc/hosts:/etc/hosts",
        ]
        devices = []
        if ENABLE_TDX:
            mounts.extend([
                "/etc/sgx_default_qcnl.conf:/etc/sgx_default_qcnl.conf",
                "/usr/share/doc/libtdx-attest-dev/examples/:/td-attest/",
                "/etc/tdx-attest.conf:/etc/tdx-attest.conf",
            ])
            devices.append("/dev/tdx_guest")
        return {
            "launch_id": launch_id,
            "workload_id": workload_id,
            "privileged": True,
            "network_mode": "host",
            "mounts": mounts,
            "devices": devices,
            "capabilities": ["ALL"],
            "launch_env_keys": ["HF_HUB_OFFLINE"],
            "launch_env_digest": self._json_sha384_digest({"HF_HUB_OFFLINE": "1"}),
        }
    
    def build_image(self, dockerfile_content: str, build_id: str, user_id: str, tlog: TrustedLogAPI, record_id: str) -> bool:
        """Build Docker image from dockerfile content with optimized error handling"""
        try:
            self.update_build_status(user_id, build_id, "preparing", step="Setting up build environment")
            build_path = os.path.join(BUILD_DIR, build_id)
            os.makedirs(build_path, exist_ok=True)
            
            # Write dockerfile to build directory
            dockerfile_path = os.path.join(build_path, "Dockerfile")
            with open(dockerfile_path, 'w', encoding='utf-8') as f:
                f.write(dockerfile_content)
            
            # Validate dockerfile content
            if not dockerfile_content.strip():
                logger.error("Empty dockerfile content provided")
                return False
            
            # Build the image with optimized parameters
            image_name = f"{user_id}-{build_id}:latest"
            cmd = [
                DOCKER_CMD, "build",
                "--no-cache",  # Ensure fresh build
                "--force-rm",  # Remove intermediate containers
                "-t", image_name,
                build_path
            ]
            
            logger.info(f"Building image: {image_name}")
            logger.debug(f"Build command: {' '.join(cmd)}")
            
            self.update_build_status(user_id, build_id, "building", step="Building container image")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            build_log = {
                "command: ": " ".join(cmd),
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "status": "success" if result.returncode == 0 else "failed"
            }
            tlog.add_entry(record_id, Entry(key="build_image", value=build_log))
            dockerfile_digest = self._file_sha384_digest(dockerfile_path)
            build_context_digest = self._directory_sha384_digest(build_path)
            base_image_digests = [self._resolve_image_digest(ref) for ref in self._extract_base_images(dockerfile_content)]
            tlog.add_entry(record_id, Entry(key="dockerfile_digest", value=dockerfile_digest))
            tlog.add_entry(record_id, Entry(key="build_context_digest", value=build_context_digest))
            tlog.add_entry(record_id, Entry(key="base_image_digests", value=base_image_digests))
            tlog.add_entry(record_id, Entry(key="build_status", value=build_log["status"]))

            if result.returncode == 0:
                logger.info(f"Successfully built image {image_name}")
                tlog.add_entry(record_id, Entry(key="output_image_digest", value=self._resolve_image_digest(image_name)))
                
                # Save build logs
                log_path = os.path.join(build_path, f"{build_id}-build.log")
                with open(log_path, 'w', encoding='utf-8') as f:
                    f.write(f"Build stdout:\n{result.stdout}\n")
                    f.write(f"Build stderr:\n{result.stderr}\n")
                
                return True
            else:
                logger.error(f"Failed to build image: {result.stderr}")
                
                # Save error logs
                error_log_path = os.path.join(build_path, f"{build_id}-error.log")
                with open(error_log_path, 'w', encoding='utf-8') as f:
                    f.write(f"Build failed:\n{result.stderr}\n")
                    f.write(f"Build stdout:\n{result.stdout}\n")
                
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Build timed out for: {user_id}-{build_id}")
            return False
        except FileNotFoundError:
            logger.error(f"Docker command not found: {DOCKER_CMD}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error building image: {str(e)}")
            return False
    
    def generate_sbom(self, image_name: str, build_id: str, tlog: TrustedLogAPI, record_id: str) -> Optional[str]:
        """Generate SBOM for the image with enhanced error handling"""
        try:
            build_path = os.path.join(BUILD_DIR, build_id)
            sbom_path = os.path.join(build_path, f"{build_id}-sbom.json")
            
            # Ensure build directory exists
            os.makedirs(build_path, exist_ok=True)
            
            # Generate SBOM with timeout and better error handling
            cmd = [SYFT_CMD, image_name, "-o", "spdx-json"]
            
            logger.info(f"Generating SBOM for image: {image_name}")
            logger.debug(f"SBOM command: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                # Validate SBOM content before saving
                try:
                    sbom_data = json.loads(result.stdout)
                    if not sbom_data.get('spdxVersion'):
                        logger.warning("Generated SBOM may be invalid - missing spdxVersion")
                except json.JSONDecodeError:
                    logger.error("Generated SBOM is not valid JSON")
                    return None
                
                # Save SBOM to file
                with open(sbom_path, 'w', encoding='utf-8') as f:
                    f.write(result.stdout)
                
                logger.info(f"Successfully generated SBOM: {sbom_path}")

                sbom_log = {
                        "command": " ".join(cmd),
                        "exit_code": result.returncode,
                        "stderr": result.stderr,
                        "validation": {
                            "spdx_version_present": bool(sbom_data.get('spdxVersion')),
                            "is_valid_json": True
                        },
                        "output_path": sbom_path,
                        "status": "success"
                }
                tlog.add_entry(record_id, Entry(key="sbom_generation", value=sbom_log))
                tlog.add_entry(record_id, Entry(key="sbom_digest", value=self._file_sha384_digest(sbom_path)))

                return sbom_path
            else:
                logger.error(f"Failed to generate SBOM: {result.stderr}")
                logger.debug(f"SBOM stdout: {result.stdout}")

                sbom_log = {
                    "command": " ".join(cmd),
                    "exit_code": result.returncode,
                    "stdout": json.loads(result.stdout),
                    "stderr": json.loads(result.stderr),
                    "status": "failed",
                    "error": {
                        "type": "subprocess.CalledProcessError",
                        "message": json.loads(result.stderr)
                    }
                }
                tlog.add_entry(record_id, Entry(key="sbom_generation", value=sbom_log))
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"SBOM generation timed out for: {image_name}")

            sbom_log = {
                "command": " ".join(cmd),
                "status": "timeout",
                "error": {
                    "type": "subprocess.TimeoutExpired",
                    "message": f"SBOM generation timed out for: {image_name}"
                }
            }
            tlog.add_entry(record_id, Entry(key="sbom_generation", value=sbom_log))

            return None
        except FileNotFoundError:
            logger.error(f"Syft command not found: {SYFT_CMD}")

            sbom_log = {
                "status": "failed",
                "error": {
                    "type": "FileNotFoundError",
                    "message": f"Syft command not found: {SYFT_CMD}"
                }
            }
            tlog.add_entry(record_id, Entry(key="sbom_generation", value=sbom_log))

            return None
        except Exception as e:
            logger.error(f"Unexpected error generating SBOM: {str(e)}")

            sbom_log = {
                "status": "failed",
                "error": {
                    "type": str(type(e)),
                    "message": str(e)
                }
            }
            tlog.add_entry(record_id, Entry(key="sbom_generation", value=sbom_log))

            return None
    
    def encrypt_image(self, image_name: str, build_id: str, public_key_path: str, tlog: TrustedLogAPI, record_id: str) -> Optional[str]:
        """Encrypt image using skopeo with optimized workflow"""
        try:
            # Setup paths for encrypted image
            build_path = os.path.join(BUILD_DIR, build_id)
            # Extract user_id from image_name (format: user_id-build_id:latest)
            user_id = image_name.split('-')[0]
            # Create OCI storage path with user_id-build_id format
            encrypted_path = os.path.join(build_path, f"{user_id}-{build_id}")
            os.makedirs(encrypted_path, exist_ok=True)
            
            # Validate public key exists
            if not os.path.exists(public_key_path):
                logger.error(f"Public key file not found: {public_key_path}")

                encryption_log = {
                    "status": "failed",
                    "error": {
                        "type": "FileNotFoundError",
                        "message": f"Public key file not found: {public_key_path}"
                    }
                }
                tlog.add_entry(record_id, Entry(key="image_encryption", value=encryption_log))
                return None
            
            logger.info(f"Starting encryption process for image: {image_name}")
            
            # Use OCI format for encrypted image storage in build directory with user_id
            cmd = [
                SKOPEO_CMD, "copy",
                "--encryption-key", f"jwe:{public_key_path}",
                f"docker-daemon:{image_name}",  # image_name already contains :latest
                f"oci:{encrypted_path}:latest-encrypted"
            ]
            
            logger.debug(f"Executing encryption command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                logger.info(f"Successfully encrypted image {image_name} to {encrypted_path}")

                encryption_log = {
                    "command": " ".join(cmd),
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "output_path": encrypted_path,
                    "status": "success"
                }
                tlog.add_entry(record_id, Entry(key="image_encryption", value=encryption_log))

                # Return OCI reference in the correct format
                return f"oci:{encrypted_path}"  # Return absolute path for skopeo
            else:
                logger.error(f"Image encryption failed: {result.stderr}")
                logger.debug(f"Encryption stdout: {result.stdout}")

                encryption_log = {
                    "command": " ".join(cmd),
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "status": "failed",
                    "error": {
                        "type": "subprocess.CalledProcessError",
                        "message": result.stderr
                    }
                }
                tlog.add_entry(record_id, Entry(key="image_encryption", value=encryption_log))

                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"Image encryption timed out for: {image_name}")
            
            encryption_log = {
                "command": " ".join(cmd),
                "status": "timeout",
                "error": {
                    "type": "subprocess.TimeoutExpired",
                    "message": f"Image encryption timed out for: {image_name}"
                }
            }
            tlog.add_entry(record_id, Entry(key="image_encryption", value=encryption_log))

            return None
        except FileNotFoundError:
            logger.error(f"Skopeo command not found: {SKOPEO_CMD}")
            
            encryption_log = {
                "image_encryption": {
                    "status": "failed",
                    "error": {
                        "type": "FileNotFoundError",
                        "message": f"Skopeo command not found: {SKOPEO_CMD}"
                    }
                }
            }
            tlog.add_entry(record_id, Entry(key="image_encryption", value=encryption_log))

            return None
        except Exception as e:
            logger.error(f"Unexpected error during image encryption: {str(e)}")
            return None
    
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
            
            # Extract proper base name and construct registry reference
            #base_name = self._extract_base_name(image_name)
            base_name = image_name.split("/")[-1] + ":latest-encrypted"
            full_image_ref = f"{DOCKER_REGISTRY}/{DOCKER_REPOSITORY}/{base_name}"
            
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
            
            # Extract proper base name and construct registry reference
            #base_name = self._extract_base_name(image_name)
            base_name = image_name.split("/")[-1] + ":latest-encrypted"
            full_image_ref = f"{DOCKER_REGISTRY}/{DOCKER_REPOSITORY}/{base_name}"
            
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
            # For path like 'oci:/path/to/builds/bld-123/user-id-bld-123'
            # Return 'user-id-bld-123:latest-encrypted'
            parts = ref.split('/')
            image_name = parts[-1]
            if ':' not in image_name:
                image_name += ':latest-encrypted'
            return image_name
            
        # Fix source reference format if it's an OCI reference
        if source_ref.startswith('oci:'):
            # Remove any duplicate 'oci:' prefixes
            source_ref = 'oci:' + source_ref.replace('oci:', '')
            
        # Fix destination reference format for registry
        if dest_ref.startswith('docker://'):
            registry = dest_ref.split('/')[2]  # Get registry name
            image_name = extract_image_name(source_ref)
            dest_ref = f"docker://{registry}/{image_name}"
        attempt = 0
        while attempt < max_retries:
            try:
                attempt += 1
                logger.info(f"Pushing image (attempt {attempt}/{max_retries}): {source_ref} -> {dest_ref}")
                
                cmd = [SKOPEO_CMD, "copy", source_ref, dest_ref]
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
                    tlog.add_entry(record_id, Entry(key="pushed_subject_digest", value=self._resolve_image_digest(source_ref.replace("oci:", "").replace("docker-daemon:", ""))))
                    tlog.add_entry(record_id, Entry(key="target_ref", value=dest_ref))
                    tlog.add_entry(record_id, Entry(key="publish_status", value="success"))

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
                        tlog.add_entry(record_id, Entry(key="target_ref", value=dest_ref))
                        tlog.add_entry(record_id, Entry(key="publish_status", value="failed"))

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
    
    def get_build_status(self, build_id: str) -> Optional[BuildResult]:
        """Get build status by build_id"""
        return self.builds.get(build_id)
    
    def update_build_status(self,user_id: str, build_id: str, status: str, step: str = None, **kwargs):
        """
        Update build status with enhanced tracking and step information
        
        Status can be one of:
        - submitted: Initial build request received
        - preparing: Setting up build environment
        - building: Building container image
        - generating_sbom: Generating SBOM
        - encrypting: Encrypting image (if requested)
        - pushing: Pushing to registry
        - signing: Signing image and SBOM
        - success: Build completed successfully
        - failed: Build failed
        """
        try:
            if build_id in self.builds:
                build_result = self.builds[build_id]
                old_status = build_result.status
                build_result.status = status
                build_result.updated_at = datetime.now()
                
                if step:
                    build_result.current_step = step
                
                # Log status changes
                if old_status != status:
                    logger.info(f"Build {build_id} status: {old_status} -> {status}")
                
                # Update additional fields
                for key, value in kwargs.items():
                    if hasattr(build_result, key):
                        setattr(build_result, key, value)
                        logger.debug(f"Updated {key} for build {build_id}")
                
                # Trigger cleanup for completed builds
                if status in ['success', 'failed'] and status != old_status:
                    # Clean up in background (keep logs for failed builds)
                    try:
                        keep_logs = (status == 'failed')
                        self.cleanup_build_artifacts(build_id, keep_logs=keep_logs)
                    except Exception as e:
                        logger.warning(f"Cleanup failed for build {build_id}: {e}")
                        
            else:
                # Create new build result
                logger.info(f"Creating new build status for {build_id}: {status}")
                self.builds[build_id] = BuildResult(
                    user_id=user_id,
                    build_id=build_id,
                    status=status,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    **kwargs
                )
                
        except Exception as e:
            logger.error(f"Error updating build status for {build_id}: {str(e)}")

    
    def get_publish_status(self, build_id: str) -> Optional[PublishResult]:
        """Get publish status by publish_id"""
        publishID = "pub-" + build_id.split("-")[-1]
        return self.publishs.get(publishID)
    
    def update_publish_status(self,user_id: str, build_id: str, status: str, publish_id: str, step: str = None, **kwargs):
        try:
            if publish_id in self.publishs:
                publish_result = self.publishs[publish_id]
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
                        self.cleanup_build_artifacts(build_id, keep_logs=keep_logs)
                    except Exception as e:
                        logger.warning(f"Cleanup failed for build {publish_id}: {e}")
                        
            else:
                # Create new build result
                logger.info(f"Creating new publish status for {publish_id}: {status}")
                self.publishs[publish_id] = PublishResult(
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


    def cleanup_build_artifacts(self, build_id: str, keep_logs: bool = True) -> bool:
        """Clean up temporary build artifacts to save disk space"""
        try:
            build_path = os.path.join(BUILD_DIR, build_id)
            
            if not os.path.exists(build_path):
                logger.warning(f"Build directory not found: {build_path}")
                return True
            
            logger.info(f"Cleaning up build artifacts for: {build_id}")
            
            # List of files/directories to clean up
            cleanup_items = [
                "encryption",  # Encryption working directory
                "plain",       # OCI plain format (if using old method)
                "encrypted",   # OCI encrypted format (if using old method)
            ]
            
            # Optionally keep logs
            if not keep_logs:
                cleanup_items.extend([
                    f"{build_id}-build.log",
                    f"{build_id}-error.log"
                ])
            
            for item in cleanup_items:
                item_path = os.path.join(build_path, item)
                try:
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                        logger.debug(f"Removed file: {item}")
                    elif os.path.isdir(item_path):
                        import shutil
                        shutil.rmtree(item_path)
                        logger.debug(f"Removed directory: {item}")
                except Exception as e:
                    logger.warning(f"Failed to remove {item}: {e}")
            
            logger.info(f"Cleanup completed for build: {build_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            return False
    
    def get_image_info(self, image_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a Docker image"""
        try:
            cmd = [DOCKER_CMD, "inspect", image_name]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                import json
                image_info = json.loads(result.stdout)[0]
                
                # Extract useful information
                info = {
                    "id": image_info.get("Id", ""),
                    "created": image_info.get("Created", ""),
                    "size": image_info.get("Size", 0),
                    "architecture": image_info.get("Architecture", ""),
                    "os": image_info.get("Os", ""),
                    "config": {
                        "env": image_info.get("Config", {}).get("Env", []),
                        "cmd": image_info.get("Config", {}).get("Cmd", []),
                        "exposed_ports": list(image_info.get("Config", {}).get("ExposedPorts", {}).keys())
                    }
                }
                
                return info
            else:
                logger.error(f"Failed to inspect image {image_name}: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"Image inspection timed out: {image_name}")
            return None
        except Exception as e:
            logger.error(f"Error inspecting image: {str(e)}")
            return None
    
    async def verify_attestation(self, image_id: str, user_id: str,  tlog: TrustedLogAPI, record_id: str) -> Tuple[str, Optional[str]]:
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
            attestation_result, decryption_key = self.get_pubKey_from_KBS(tlog, record_id)
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
    
    def generate_key(self, build_id: str, tlog: TrustedLogAPI, record_id: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Generate a cosign key pair for signing and an openssl key for encryption.
        
        Args:
            build_id: Build ID for key file naming
            
        Returns:
            Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]: 
                (private_signing_key_path, public_signing_key_path, 
                 private_encryption_key_path, public_encryption_key_path)
            Returns (None, None, None, None) if generation fails.
        """
        try:
            key_dir = os.path.join(BUILD_DIR, build_id)
            os.makedirs(key_dir, exist_ok=True)

            # 1. Generate Cosign signing key pair
            cosign_key_prefix = os.path.join(key_dir, f"{build_id}-cosign")
            private_signing_key_path = f"{cosign_key_prefix}.key"
            public_signing_key_path = f"{cosign_key_prefix}.pub"

            logger.info(f"Generating cosign key pair with prefix {cosign_key_prefix}")
            env = os.environ.copy()
            env['COSIGN_PASSWORD'] = ''
            
            cosign_cmd = [
                COSIGN_CMD, "generate-key-pair",
                f"--output-key-prefix={cosign_key_prefix}"
            ]
            cosign_result = subprocess.run(cosign_cmd, capture_output=True, text=True, env=env)
            
            if cosign_result.returncode != 0:
                logger.error(f"Failed to generate cosign keys: {cosign_result.stderr}")
                
                key_log = {
                    "cosign_command": " ".join(cosign_cmd),
                    "cosign_exit_code": cosign_result.returncode,
                    "cosign_stdout": cosign_result.stdout,
                    "cosign_stderr": cosign_result.stderr,
                    "status": "failed",
                    "error": {
                        "type": "subprocess.CalledProcessError",
                        "message": f"Failed to generate cosign keys: {cosign_result.stderr}"
                    }
                }
                tlog.add_entry(record_id, Entry(key="key_generation", value=key_log))

                return None, None, None, None

            # 2. Generate OpenSSL encryption key pair
            openssl_priv_key_path = os.path.join(key_dir, f"{build_id}-openssl.key")
            public_encryption_key_path = os.path.join(key_dir, f"{build_id}-openssl.pub")

            logger.info(f"Generating openssl key pair in {key_dir}")
            
            # Generate private key
            openssl_priv_cmd = [
                "openssl", "genpkey",
                "-algorithm", "RSA",
                "-out", openssl_priv_key_path,
                "-pkeyopt", "rsa_keygen_bits:2048"
            ]
            openssl_priv_result = subprocess.run(openssl_priv_cmd, capture_output=True, text=True)
            if openssl_priv_result.returncode != 0:
                logger.error(f"F:set nuailed to generate openssl private key: {openssl_priv_result.stderr}")
                
                key_log = {
                    "openssl_command": " ".join(openssl_priv_cmd),
                    "openssl_exit_code": openssl_priv_result.returncode,
                    "openssl_stdout": openssl_priv_result.stdout,
                    "openssl_stderr": openssl_priv_result.stderr,
                    "status": "failed",
                    "error": {
                        "type": "subprocess.CalledProcessError",
                        "message": f"Failed to generate openssl private key: {openssl_priv_result.stderr}"
                    }
                }
                tlog.add_entry(record_id, Entry(key="key_generation", value=key_log))

                return None, None, None, None

            # Generate public key from private key
            openssl_pub_cmd = [
                "openssl", "rsa",
                "-pubout",
                "-in", openssl_priv_key_path,
                "-out", public_encryption_key_path
            ]
            openssl_pub_result = subprocess.run(openssl_pub_cmd, capture_output=True, text=True)
            if openssl_pub_result.returncode != 0:
                logger.error(f"Failed to generate openssl public key: {openssl_pub_result.stderr}")
                
                key_log = {
                    "openssl_command": " ".join(openssl_pub_cmd),
                    "openssl_exit_code": openssl_pub_result.returncode,
                    "openssl_stdout": openssl_pub_result.stdout,
                    "openssl_stderr": openssl_pub_result.stderr,
                    "status": "failed",
                    "error": {
                        "type": "subprocess.CalledProcessError",
                        "message": f"Failed to generate openssl public key: {openssl_pub_result.stderr}"
                    }
                }
                tlog.add_entry(record_id, Entry(key="key_generation", value=key_log))

                return None, None, None, None

            key_log = {
                "cosign_command": " ".join(cosign_cmd),
                "cosign_exit_code": cosign_result.returncode,
                "cosign_stdout": cosign_result.stdout,
                "cosign_stderr": cosign_result.stderr,
                "openssl_command": " ".join(openssl_priv_cmd),
                "openssl_exit_code": openssl_priv_result.returncode,
                "openssl_stdout": openssl_priv_result.stdout,
                "openssl_stderr": openssl_priv_result.stderr,
                "output_files": {
                    "private_signing_key_path": private_signing_key_path,
                    "public_signing_key_path": public_signing_key_path,
                    "private_encryption_key_path": openssl_priv_key_path,
                    "public_encryption_key_path": public_encryption_key_path
                },
                "status": "success"
            }
            tlog.add_entry(record_id, Entry(key="key_generation", value=key_log))


            return private_signing_key_path, public_signing_key_path, openssl_priv_key_path, public_encryption_key_path
            
        except Exception as e:
            logger.error(f"Key generation failed: {str(e)}")
            return None, None, None, None

    def _extract_base_name(self, image_name: str) -> str:
        """
        Extract clean base name from image reference for registry
        
        Args:
            image_name: Raw image name/reference (can be path or registry format)
            
        Returns:
            str: Clean base name in format 'test-bld-id:latest-encrypted'
        """
        # Remove any registry prefix if present
        if '://' in image_name:
            image_name = image_name.split('://', 1)[1]
            
        # Split path and get last component
        parts = image_name.split('/')
        base_name = parts[-1]
        
        # Handle local file paths in the name
        if '.' in base_name:
            # For paths like ./builds/bld-id/test-bld-id, get test-bld-id
            path_parts = base_name.split('.')
            if len(path_parts) > 1 and path_parts[-1] in ['json', 'sig', 'att']:
                # Remove file extensions like .json, .sig, .att
                base_name = path_parts[-2]
            else:
                base_name = path_parts[-1]
                
        # If it's just a build ID, add test- prefix
        if base_name.startswith('bld-'):
            base_name = f"test-{base_name}"
        # If it doesn't have test- prefix but has build id, add it
        elif not base_name.startswith('test-') and '-bld-' in base_name:
            base_name = f"test-{base_name.split('-bld-')[1]}"
            
        # Ensure proper tag
        if ':' not in base_name:
            base_name += ':latest-encrypted'
        elif not base_name.endswith('-encrypted'):
            base_name = base_name.split(':')[0] + ':latest-encrypted'
            
        return base_name


    def pull_image(self, tlog: TrustedLogAPI, record_id: str, image_url: str, openssl_key: str, target_dir: str, max_retries: int = 3, retry_delay: int = 5) -> bool:
        
        source_ref = image_url.replace("docker.io","docker:/")
        dest_ref = os.path.join('oci:'+target_dir,'encrypted')

        attempt = 0
        while attempt < max_retries:
            try:
                attempt += 1
                logger.info(f"Pulling image (attempt {attempt}/{max_retries}): {source_ref}")

                if openssl_key:
                    cmd = [SKOPEO_CMD, "copy", "--decryption-key", openssl_key, source_ref, dest_ref]
                else:
                    # Non-TDX mode can operate without decryption key when image is not encrypted.
                    cmd = [SKOPEO_CMD, "copy", source_ref, dest_ref]
                logger.debug(f"Pull command: {' '.join(cmd)}")

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

                if result.returncode == 0:
                    logger.info(f"Successfully pulled image to local")
                    
                    tlog.add_entry(record_id, Entry(key="pull_image", value={"pull_image": "success",
                                         "result_stdout": result.stdout,
                                         "result_stderr": result.stderr,
                                         "pull_cmd": " ".join(cmd)
                                        }))
                    return True
                else:
                    logger.warning(f"Pull attempt {attempt} failed: {result.stderr}")
                    logger.debug(f"Pull stdout: {result.stdout}")

                    if attempt < max_retries:
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"All pull attempts failed after {max_retries} tries")
                        
                        tlog.add_entry(record_id, Entry(key="pull_image", value={"pull_image": "failed",
                                            "result_stdout": result.stdout,
                                            "result_stderr": result.stderr,
                                            "pull_cmd": " ".join(cmd),
                                            "error": f"All pull attempts failed after {max_retries} tries"
                                            }))
                        return False

            except subprocess.TimeoutExpired:
                logger.warning(f"Pull attempt {attempt} timed out")
                if attempt < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"All pull attempts timed out after {max_retries} tries")
                    return False
            except FileNotFoundError:
                logger.error(f"Skopeo command not found: {SKOPEO_CMD}")
                tlog.add_entry(record_id, Entry(key="pull_image", value={"pull_image": "failed",
                                     "error": f"Skopeo command not found: {SKOPEO_CMD}"}))
                return False  # Don't retry if command not found
            except Exception as e:
                tlog.add_entry(record_id, Entry(key="pull_image", value={"pull_image": "failed",
                                     "error": f"{e}"}))
                logger.warning(f"Pull attempt {attempt} failed with error: {str(e)}")
                if attempt < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"All pull attempts failed after {max_retries} tries: {str(e)}")
                    return False

        return False

    def update_launch_status(self,user_id: str, launch_id: str, status: str, **kwargs):

        try:
            if launch_id in self.launchs:
                launch_result = self.launchs[launch_id]
                old_status = launch_result.status
                launch_result.status = status
                launch_result.updated_at = datetime.now()

                # Log status changes
                if old_status != status:
                    logger.info(f"launch {launch_id} status: {old_status} -> {status}")

                # Update additional fields
                for key, value in kwargs.items():
                    if hasattr(launch_result, key):
                        setattr(launch_result, key, value)
                        logger.debug(f"Updated {key} for build {launch_id}")

            else:
                # Create new launch result
                logger.info(f"Creating new launch status for {launch_id}: {status}")
                self.launchs[launch_id] = LaunchResult(
                    user_id=user_id,
                    launch_id=launch_id,
                    status=status,
                    updated_at=datetime.now(),
                    **kwargs
                )

        except Exception as e:
            logger.error(f"Error updating build status for {launch_id}: {str(e)}")

    def update_transparencylog_status(self,user_id: str, log_id: str, status: str, build_id: str, **kwargs):

        try:
            if log_id in self.transparencyLog:
                tlog_result = self.transparencyLog[log_id]
                old_status = tlog_result.status
                tlog_result.status = status

                # Log status changes
                if old_status != status:
                    logger.info(f"transparency log {log_id} status: {old_status} -> {status}")

                # Update additional fields
                for key, value in kwargs.items():
                    if hasattr(tlog_result, key):
                        setattr(tlog_result, key, value)
                        logger.debug(f"Updated {key} for transparency log {log_id}")
            else:
                # Create new launch result
                logger.info(f"Creating new transparency log status for {log_id}: {status}")
                # get transparency log
                tlog_path = os.path.join(BUILD_DIR, build_id)
                tlog_file = ''
                data = ''
                for i in os.listdir(tlog_path):
                    if i.endswith("transparency.json"):
                        tlog_file = os.path.join(tlog_path,i)
                        break
                if os.path.exists(tlog_file):
                    with open(tlog_file,'r',encoding='utf-8') as f:
                        #tlog_result.transparency_log = json.load(f)
                        data = json.load(f)
                else:
                    logger.debug(f"Transparency log not found.")
                #print("CEHCK______",type(json.dumps(data,indent=4)))
                self.transparencyLog[log_id] = TransparencyResult(
                    user_id=user_id,
                    build_id=build_id,
                    log_id=str(log_id),
                    status=status,
                    transparency_log=json.dumps(data,indent=4),
                    **kwargs
                )

        except Exception as e:
            logger.error(f"Error updating transparency log status for {log_id}: {str(e)}")

    def get_transparencyLog_status(self, log_id: str) -> Optional[TransparencyResult]:
        """Get transparency log status by log_id"""
        return self.transparencyLog.get(log_id)

    def verify_sbom(self,imagesurl,sbom_url,tlog: TrustedLogAPI, record_id: str, cosign_pubkey='cosign.pub') -> bool:

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
                logger.debug(f"Failed to verify: {cosign_verify.stderr}")
                tlog.add_entry(record_id, Entry(key="verify_sbom_status", value="failed"))
                return False
            tlog.add_entry(record_id, Entry(key="verify_sbom_status", value="success"))

        except Exception as e:
            logger.error(f"Verify signed image {images_fullName} failed: {str(e)}")
            tlog.add_entry(record_id, Entry(key="error", value=f"{e}"))

        #2. verify attestation
        try:
            cosign_attcmd = [
                    COSIGN_CMD, "verify-attestation", "--key", cosign_pubkey, "--type", "spdx", imagesurl]
            
            cosign_attverify = subprocess.run(cosign_attcmd, capture_output=True, text=True)
            logger.info(f"Attestation_Vertify CMD: {' '.join(cosign_attcmd)}")
            tlog.add_entry(record_id, Entry(key="verify_attestation_cmd", value=" ".join(cosign_attcmd)))

            if cosign_attverify.returncode != 0:
                logger.debug(f"Failed to verify: {cosign_attverify.stderr}")
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


    def get_launch_status(self, launch_id: str) -> Optional[LaunchResult]:
        """Get launch status by launch_id"""
        return self.launchs.get(launch_id)


    async def launch_containers(self, tlog, record_id, image_url, image_id, launch_pth, workload_id: Optional[str] = None, launch_id: Optional[str] = None):
        # skopeo copy oci:encrypt/ docker-daemon:test_pull:latest
        image_dir = 'oci:' + os.path.join(launch_pth,'encrypted')
        Newimage_name = 'docker-daemon:'+ image_id + ":latest"
        
        try:
            cmd = [SKOPEO_CMD, "copy", image_dir, Newimage_name]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if res.returncode == 0:
                logger.info(f"Success add {Newimage_name} image.")
                logger.debug(f"CMD: {' '.join(cmd)}")
                tlog.add_entry(record_id, Entry(key="pullImage", value={"pullImage_cmd": " ".join(cmd), "pullImage_status": "success"}))
            else:
                logger.info("Failed add image.")
                logger.debug(f"CMD: {' '.join(cmd)}")
                tlog.add_entry(record_id, Entry(key="pullImage_status", value="failed"))
                return False

            #get_imageID = [DOCKER_CMD, "images", "--format", "'{{.ID}}'"]
            cmd = ["docker", "images","--format", "{{.Repository}} {{.Tag}} {{.ID}}","--no-trunc"]
            output = subprocess.check_output(cmd, text=True)
            images = []
            for line in output.strip().split('\n'):
                if not line: continue
                repo, tag, full_id = line.split(' ', 2)
                short_id = full_id.split(':')[-1][:12]
                images.append({
                    "repository": repo,
                    "tag": tag,
                    "id": short_id,
                    "full_id": full_id
                    })

            imageID = ''
            for i in images:
                if image_id in i['repository']:
                    imageID = i['id']
                    break
            logger.info(f"Get image id {imageID}")

            # run docker image
            docker_cmd = [
                DOCKER_CMD,
                "run",
                "-d",
                "-it",
                "--privileged",
                "-e",
                "HF_HUB_OFFLINE=1",
                "-v",
                "/etc/hosts:/etc/hosts",
                "--network=host",
            ]
            if workload_id:
                docker_cmd.extend(["--label", f"io.trucon.workload-id={workload_id}"])
            if launch_id:
                docker_cmd.extend(["--label", f"io.trucon.launch-id={launch_id}"])
            if ENABLE_TDX:
                docker_cmd.extend([
                    "-v",
                    "/etc/sgx_default_qcnl.conf:/etc/sgx_default_qcnl.conf",
                    "-v",
                    "/dev/tdx_guest:/dev/tdx_guest",
                    "-v",
                    "/usr/share/doc/libtdx-attest-dev/examples/:/td-attest/",
                    "-v",
                    "/etc/tdx-attest.conf:/etc/tdx-attest.conf",
                ])
            else:
                logger.info("ENABLE_TDX=false, skipping TDX device and attestation mounts")

            docker_cmd.append(imageID)
            logger.info(f"Runcmd : {' '.join(docker_cmd)}")
            dockerRUn = subprocess.run(docker_cmd, capture_output=True, text=True)
            if dockerRUn.returncode == 0:
                logger.info(f"Success run image {image_id}.")
                tlog.add_entry(record_id, Entry(key="launch_cmd", value={"launch_cmd": " ".join(docker_cmd),
                                     "launch_status": "success",
                                     "launch_stdout": dockerRUn.stdout,
                                     }))
                tlog.add_entry(record_id, Entry(key="launch_result", value="success"))
            else:
                logger.info("Failed run image.")
                logger.debug(f"CMD: {' '.join(docker_cmd)}")
                tlog.add_entry(record_id, Entry(key="launch_status", value={"launch_status": "failed",
                                     "launch_stderr": dockerRUn.stderr}))
                tlog.add_entry(record_id, Entry(key="launch_result", value="failed"))
                return False

            # docker ps -q --latest
            getID = [DOCKER_CMD, "ps", "-q", "--latest"]
            getID_res = subprocess.run(getID, capture_output=True, text=True)
            if getID_res.returncode == 0:
                containerID = getID_res.stdout.replace("\n","")
                logger.info(f"Success get image ID {containerID}")
                tlog.add_entry(record_id, Entry(key="getContainerID_cmd", value={"getContainerID_cmd": " ".join(getID),
                                     "getContainerID_status": "success",
                                     "getID_stdout": getID_res.stdout
                                     }))
                tlog.add_entry(record_id, Entry(key="instance_id", value=containerID))
            else:
                logger.info("Failed get container ID.")
                tlog.add_entry(record_id, Entry(key="getContainerID_status", value={"getContainerID_status": "failed",
                                     "getID_stderr": getID_res.stderr
                                     }))
                return False
            
            #docker inspect ID --format '{{.State.Status}}'
            getStatus = [DOCKER_CMD, "inspect", "--format", "'{{.State.Status}}'", containerID]
            getStatus_res = subprocess.run(getStatus, capture_output=True, text=True)
            if getStatus_res.returncode == 0:
                status_text = getStatus_res.stdout.replace("\n", "")
                logger.info(f"Success get container {containerID} status: {status_text}")
                tlog.add_entry(record_id, Entry(key="getStatus_cmd", value={"getStatus_cmd": " ".join(getStatus),
                                     "get_status": getStatus_res.stdout}))
            else:
                logger.info("Failed get container status.")
                logger.error(f"get container status cmd: {' '.join(getStatus)}")
                tlog.add_entry(record_id, Entry(key="get_status", value={"get_status": "failed",
                                     "getStatus_stderr": getStatus_res.stderr
                                     }))
                return False
            
            tlog.add_entry(record_id, Entry(key="container_info", value={"container_ID": getID_res.stdout, "container_Status": getStatus_res.stdout}))
            return [{"container_ID": getID_res.stdout, "container_Status": getStatus_res.stdout}]

        except Exception as e:
            logger.error(f"Launch contaioner failed: {str(e)}")
            tlog.add_entry(record_id, Entry(key="Deploy_launch status", value="success"))
            return False


    def get_pubKey_from_KBS(self, tlog: TrustedLogAPI = None, record_id: str = None):
        try:
            key_dict = {'opensslKey':'openssl.key', 'cosignKey':'cosign.key', 'opensslPub':'openssl.pub', 'cosignPub':'cosign.pub'}
            if os.path.exists('openssl.pub'):
                for key,value in key_dict.items():
                    if not os.path.exists(value):
                        logger.info(f"Failed get {key}!")
                        tlog.add_entry(record_id, Entry(key="get_key", value="failed"))
                        return False, None
                    else:
                        key_dict[key] = os.path.realpath(value)
                        tlog.add_entry(record_id, Entry(key="get_key", value="true"))
                return 'trusted', key_dict

            opensslKey_cmd = ["curl", KBS_URL+"openssl.key", "-o","openssl.key"]
            cosignPub_cmd = ["curl", KBS_URL+"cosign.pub", "-o","cosign.pub"]
            opensslPub_cmd = ["curl", KBS_URL+"openssl.pub", "-o","openssl.pub"]
            cosignKey_cmd = ["curl", KBS_URL+"cosign.key", "-o","cosign.key"]

            opensslKey_res = subprocess.run(opensslKey_cmd, capture_output=True, text=True)
            cosignPub_res = subprocess.run(cosignPub_cmd, capture_output=True, text=True)
            opensslPub_res = subprocess.run(opensslPub_cmd, capture_output=True, text=True)
            cosignKey_res = subprocess.run(cosignKey_cmd, capture_output=True, text=True)

            for key,value in key_dict.items():
                if not os.path.exists(value):
                    logger.info(f"Failed get {key}!")
                    tlog.add_entry(record_id, Entry(key="get_key", value="failed"))
                    return False, None
                else:
                    key_dict[key] = os.path.realpath(value)
            tlog.add_entry(record_id, Entry(key="key", value=key_dict))
            return 'trusted', key_dict

        except Exception as e:
            logger.error(f"Launch contaioner failed: {str(e)}")
            tlog.add_entry(record_id, Entry(key="key", value=f"Get key failed: {e}"))
            return False, None

    def commit_and_save_receipt(self, api_type, build_id, tlog: TrustedLogAPI, record_id: str, identity_token_str: str):
        """Commit the accumulated entries via TrustedLogAPI and save a receipt file."""
        try:
            from .tlog.types import CommitResult
            result = tlog.commit_record(
                record_id=record_id,
                event_type=api_type,
                commit_options={"identity_token": identity_token_str},
            )
            receipt = {
                "record_id": result.record_id,
                "event_id": result.event_id,
                "queue_status": result.queue_status.value if result.queue_status else None,
                "mr_value": result.mr_value,
            }
            receipt_path = os.path.join(BUILD_DIR, build_id, f"{api_type}-commit-receipt.json")
            os.makedirs(os.path.dirname(receipt_path), exist_ok=True)
            with open(receipt_path, "w", encoding="utf-8") as f:
                json.dump(receipt, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved {api_type} commit receipt to {receipt_path}")
            return True, result.record_id
        except Exception as e:
            logger.error(f"Commit failed for {api_type}: {e}")
            return False, None

    def verify_chain_state(self, api_type, tlog: TrustedLogAPI, chain_id: str = "default"):
        """Lightweight verification: query TruCon chain-state and check head."""
        logger.info("Verifying chain state via TruCon...")
        try:
            from .trucon.internal_transport import request_json

            data = request_json(
                "GET",
                f"/chain-state/{chain_id}",
                caller_service="tc_api",
                timeout=10,
                trucon_url=tlog._trucon_url,
            )
            if data.get("head_record_id"):
                logger.info(f"Chain '{chain_id}' head at record {data['head_record_id']}, seq={data.get('sequence_num')}")
                return "success"
            else:
                logger.warning(f"Chain '{chain_id}' has no head record yet")
                return "pending"
        except Exception as e:
            logger.warning(f"TruCon chain-state query failed: {e}")
            return "degraded"

    async def get_summaryTransparencylog(self, build_id, launch_id):
        """"
        get all transparency log
        """
        try:
            build_path = os.path.join(BUILD_DIR, build_id)
            logger.info(f"Get build_path: {build_path}")
            launch_path = os.path.join(BUILD_DIR, launch_id)
            logger.info(f"Get launch_path: {launch_path}")
            
            def get_log(path,api):
                try:
                    logid = ''
                    content = ''
                    for i in [os.path.join(j) for j in os.listdir(path) if j.startswith(api)]:
                        if f"{api}-transparency_log" in i:
                            logid = i.split("-")[-1][:9]
                            logger.info(f"Get {api}_logId: {api}_{logid}")

                        if f"{api}-transparency.json" == i:
                            log_path = os.path.join(path,i)
                            logger.info(f"Get {api}_log for: {i}")
                            with open(log_path, 'r', encoding='utf-8') as f:
                                content = json.load(f)
                            if not content:
                                logger.error(f"get {api}-transparency log failed")
                    
                    if (not logid) or (not content):
                        logger.debug("Get transparency log failed.")
                        return None, None
                    else:
                        return logid, content
                
                except Exception as e:
                    logger.debug(f"Get transparency log failed. {e}")
                    return None, None

            # get build transparency log
            #build_log = [os.path.join(i) for i in os.listdir(build_path) if i.startswith('build')]
            build_logId, build_content = get_log(build_path,"build")
            #publish_log = [os.path.join(i) for i in os.listdir(build_path) if i.startswith('publish')]
            publish_logId, publish_content = get_log(build_path,"publish")
            #launch_log = [os.path.join(i) for i in os.listdir(launch_path) if i.startswith('launch')]
            launch_logId, launch_content = get_log(launch_path,"launch")
            
            # get log id
            logids = {"build": build_logId,
                      "publish": publish_logId,
                      "launch": launch_logId
                      }

            summary = {"build": f"{json.dumps(build_content,indent=2)}",
                       "publish": f"{json.dumps(publish_content,indent=2)}",
                       "launch": f"{json.dumps(launch_content,indent=2)}"
                       }
            #logger.info(f"Workflow transparency log: {json.dumps(summary, indent=2)}")
            respone = {"build_id": build_id, "launch_id": launch_id, "log_id": logids, "transparencylog": summary}

            #logger.info(f"Workflow transparency log: {json.dumps(respone, indent=2)}")
            return respone
        except Exception as e:
            logger.error(f"Get Workflow transparency log failed")
            return None


    def create_lunks_block(self, user_id, tlog: TrustedLogAPI, record_id: str, passwd, VFS_SIZE, VFS_PATH):
        LOOP_DEVICE = subprocess.run(['losetup', '-f'], capture_output=True, text=True, timeout=600).stdout.strip()
        MAPPER_DIR = f"{random.randint(0, 32767)}{random.randint(0, 32767)}{random.randint(0, 32767)}{random.randint(0, 32767)}"
        cmd = "./scripts/create_encrypted_vfs.sh "+VFS_PATH+" "+VFS_SIZE+" "+passwd+" "+MAPPER_DIR+" "+LOOP_DEVICE
        try:
            result = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,text=True)
            logger.info(result.stdout.read())
            if result.wait() == 0:
                logger.info(result.stdout.read())
                self.update_lunks_status(user_id, "creating", step="create_encrypted_vfs: success",passwd=passwd,vfs_size=VFS_SIZE,vfs_path=VFS_PATH,mapper_dir=MAPPER_DIR,loop_device=LOOP_DEVICE)
                tlog.add_entry(record_id, Entry(key="create_encrypted_vfs", value="completed"))
                return MAPPER_DIR,LOOP_DEVICE
            else:
                logger.debug(f"create_encrypted_vfs failed: {cmd}")
                self.update_lunks_status(user_id, "creating", step="create_encrypted_vfs: failed")
                tlog.add_entry(record_id, Entry(key="createLunks", value="create_encrypted_vfs failed"))
                return
        except Exception as e:
            logger.debug(f"crate lunks failed.{e}")
            tlog.add_entry(record_id, Entry(key="create_lunks_failed", value=f"e"))
            return

    def mount_lunks_block(self, user_id, tlog: TrustedLogAPI, record_id: str, MAPPER_DIR, passwd, MOUNT_PATH, VFS_PATH,LOOP_DEVICE):
        cmd = "./scripts/mount_encrypted_vfs.sh "+VFS_PATH+" "+MOUNT_PATH+" "+MAPPER_DIR+" "+passwd+" "+LOOP_DEVICE
        try:
            result = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,text=True)
            logger.info(result.stdout.read())
            if result.wait() == 0:
                logger.info(result.stdout.read())
                self.update_lunks_status(user_id, "mounting", step="mount_encrypted_vfs: success",mount_path=MOUNT_PATH,vfs_path=VFS_PATH)
                tlog.add_entry(record_id, Entry(key="mount_encrypted_vfs", value="completed"))
                return MOUNT_PATH
            else:
                logger.debug(f"mount_encrypted_vfs failed: {cmd}")
                self.update_lunks_status(user_id, "mounting", step="mount_encrypted_vfs: failed")
                tlog.add_entry(record_id, Entry(key="mountLunks", value="mount_encrypted_vfs failed"))
                return
        except Exception as e:
            logger.debug(f"mount lunks failed.{e}")
            tlog.add_entry(record_id, Entry(key="mount_lunks_failed", value=f"e"))
            return


    def unmount_lunks_block(self, user_id, tlog: TrustedLogAPI, record_id: str, MAPPER_DIR, MOUNT_PATH, LOOP_DEVICE):
        MAPPER_PATH=f'/dev/mapper/{MAPPER_DIR}'
        cmd = "./scripts/unmount_encrypted_vfs.sh "+" "+MOUNT_PATH+" "+MAPPER_PATH+" "+LOOP_DEVICE
        try:
            result = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,text=True)
            if result.wait() == 0:
                logger.info(result.stdout.read())
                self.update_lunks_status(user_id, "umounting", step="unmount_encrypted_vfs: success")
                tlog.add_entry(record_id, Entry(key="unmount_encrypted_vfs", value="completed"))
            else:
                logger.debug(f"unmount_encrypted_vfs failed: {cmd}")
                self.update_lunks_status(user_id, "umounting", step="unmount_encrypted_vfs: failed")
                tlog.add_entry(record_id, Entry(key="unmountLunks", value="unmount_encrypted_vfs failed"))
        except Exception as e:
            logger.debug(f"unmount lunks failed.{e}")
            tlog.add_entry(record_id, Entry(key="unmount_lunks_failed", value=f"e"))
            return


    def get_lunks_status(self, user_id: str) -> Optional[LunksResult]:
        """Get lunks status by user_id"""
        return self.lunks.get(user_id)

    
    def update_lunks_status(self,user_id: str, status: str, step: str = None, **kwargs):

        try:
            if user_id in self.lunks:
                lunks_result = self.lunks[user_id]
                old_status = lunks_result.status
                lunks_result.status = status
                lunks_result.updated_at = datetime.now()

                if step:
                    lunks_result.step = step

                # Log status changes
                if old_status != status:
                    logger.info(f"Lunks {user_id} status: {old_status} -> {status}")

                # Update additional fields
                for key, value in kwargs.items():
                    if hasattr(lunks_result, key):
                        setattr(lunks_result, key, value)
                        logger.debug(f"Updated {key} for build {user_id}")

                # Trigger cleanup for completed builds
                if status in ['success', 'failed'] and status != old_status:
                    # Clean up in background (keep logs for failed builds)
                    try:
                        keep_logs = (status == 'failed')
                        self.cleanup_build_artifacts('', keep_logs=keep_logs)
                    except Exception as e:
                        logger.warning(f"Cleanup failed for lunks {user_id}: {e}")

            else:
                # Create new build result
                logger.info(f"Creating new lunks status for {user_id}: {status}")
                self.lunks[user_id] = LunksResult(
                    user_id=user_id,
                    status=status,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    **kwargs
                )

        except Exception as e:
            logger.error(f"Error updating lunks status for {user_id}: {str(e)}")

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

