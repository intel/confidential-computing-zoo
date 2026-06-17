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
from typing import Optional, Tuple

from ..config import (
    BUILD_DIR,
    COSIGN_CMD,
    DOCKER_CMD,
    SKOPEO_CMD,
    SYFT_CMD,
)
from ..transparency.commit_client import TrustedLogAPI
from ..transparency.events import EventEntryKey, build_identity_entries
from tlog.types import Entry

logger = logging.getLogger(__name__)


def _json_or_text(value: str):
    if not value:
        return ""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


class BuildServiceMixin:
    def build_image(self, dockerfile_content: str, build_id: str, user_id: str, tlog: TrustedLogAPI, record_id: str, luks_path: str = '') -> bool:
        """Build Docker image from dockerfile content with optimized error handling"""
        try:
            self.update_build_status(user_id, build_id, "preparing",luks_path, step="Setting up build environment")
            if luks_path:
                if os.path.exists(luks_path):
                    build_path = os.path.join(luks_path, build_id)
                else:
                    build_path = os.path.join(BUILD_DIR, build_id)
                    logger.info("NOW build image not in luks.")
            else:
                build_path = os.path.join(BUILD_DIR, build_id)
                logger.info("NOW build image not in luks.")
            os.makedirs(build_path, exist_ok=True)
            
            # Write dockerfile to build directory
            if os.path.exists(dockerfile_content):
                dockerfile_path = dockerfile_content
            else:
                dockerfile_path = os.path.join(build_path, "Dockerfile")
                with open(dockerfile_path, 'w', encoding='utf-8') as f:
                    f.write(dockerfile_content)
            
            # Validate dockerfile content
            if not dockerfile_content.strip():
                logger.error("Empty dockerfile content provided")
                return False
            
            # Build the image with optimized parameters
            image_name = self.local_build_image_ref(build_id)
            if luks_path:
                cmd = [
                    # "DOCKER_BUILDKIT=1",
                    DOCKER_CMD, "build",
                    "-f", dockerfile_path,
                    "--no-cache",  # Ensure fresh build
                    "--force-rm",  # Remove intermediate containers
                    "-t", image_name,
                    os.path.dirname(dockerfile_path)
                ]
            else:
                cmd = [
                    DOCKER_CMD, "build",
                    "--no-cache",  # Ensure fresh build
                    "--force-rm",  # Remove intermediate containers
                    "-t", image_name,
                    build_path
                ]
            
            logger.info(f"Building image: {image_name}")
            logger.info(f"Build command: {' '.join(cmd)}")
            
            self.update_build_status(user_id, build_id, "building", luks_path, step="Building container image")
            
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

            if result.returncode == 0:
                logger.info(f"Successfully built image {image_name}")
                output_image_digest = self._resolve_image_digest(image_name)
                self.add_tlog_entries(
                    tlog,
                    record_id,
                    build_identity_entries(
                        output_image_digest=output_image_digest,
                        dockerfile_digest=dockerfile_digest,
                        build_context_digest=build_context_digest,
                        base_image_digests=base_image_digests,
                        build_status=build_log["status"],
                    ),
                )
                
                # Save build logs
                log_path = os.path.join(build_path, f"{build_id}-build.log")
                with open(log_path, 'w', encoding='utf-8') as f:
                    f.write(f"Build stdout:\n{result.stdout}\n")
                    f.write(f"Build stderr:\n{result.stderr}\n")
                
                return True
            else:
                logger.error(f"Failed to build image: {result.stderr}")
                self.add_tlog_entries(
                    tlog,
                    record_id,
                    build_identity_entries(
                        output_image_digest=None,
                        dockerfile_digest=dockerfile_digest,
                        build_context_digest=build_context_digest,
                        base_image_digests=base_image_digests,
                        build_status=build_log["status"],
                    ),
                )
                
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

    def generate_sbom(self, image_name: str, build_id: str, tlog: TrustedLogAPI, record_id: str, luks_path: str) -> Optional[str]:
        """Generate SBOM for the image with enhanced error handling"""
        try:
            if luks_path:
                if os.path.exists(luks_path):
                    build_path = os.path.join(luks_path, build_id)
                else:
                    build_path = os.path.join(BUILD_DIR, build_id)
                    logger.info("NOW build image not in luks.")
            else:
                build_path = os.path.join(BUILD_DIR, build_id)
                logger.info("NOW generate sbom file not in luks file.")
            sbom_path = os.path.join(build_path, f"{build_id}-sbom.json")
            
            # Ensure build directory exists
            os.makedirs(build_path, exist_ok=True)
            
            # Generate SBOM with timeout and better error handling
            cmd = [SYFT_CMD, image_name, "-o", "spdx-json"]
            
            logger.info(f"Generating SBOM for image: {image_name}")
            logger.debug(f"SBOM command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                env=self._syft_environment(),
            )
            
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
                tlog.add_entry(record_id, Entry(key=EventEntryKey.sbom_digest.value, value=self._file_sha384_digest(sbom_path)))

                return sbom_path
            else:
                logger.error(f"Failed to generate SBOM: {result.stderr}")
                logger.debug(f"SBOM stdout: {result.stdout}")

                sbom_log = {
                    "command": " ".join(cmd),
                    "exit_code": result.returncode,
                    "stdout": _json_or_text(result.stdout),
                    "stderr": _json_or_text(result.stderr),
                    "status": "failed",
                    "error": {
                        "type": "subprocess.CalledProcessError",
                        "message": result.stderr or result.stdout or "SBOM generation failed"
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

    def encrypt_image(self, image_name: str, build_id: str, public_key_path: str, tlog: TrustedLogAPI, record_id: str, luks_path: str) -> Optional[str]:
        """Encrypt image using skopeo with optimized workflow"""
        archive_path = None
        docker_save_cmd = None
        cmd = None
        key_validation_detail = None
        try:
            # Setup paths for encrypted image
            if luks_path:
                if os.path.exists(luks_path):
                    build_path = os.path.join(luks_path, build_id)
                else:
                    build_path = os.path.join(BUILD_DIR, build_id)
                    logger.info("NOW is not in luks.")
            else:
                build_path = os.path.join(BUILD_DIR, build_id)
                logger.info("NOW is not in luks.")
            image_base_name = image_name.rsplit(":", 1)[0].split("/")[-1]
            encrypted_path = os.path.join(build_path, image_base_name)
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
            
            logger.info("Starting encryption process for image: %s using public key %s", image_name, public_key_path)
            key_valid, key_validation_detail = self._validate_public_encryption_key(public_key_path)
            if not key_valid:
                logger.error("Encryption key validation failed for %s: %s", public_key_path, key_validation_detail)
                encryption_log = {
                    "public_key_path": public_key_path,
                    "status": "failed",
                    "error": {
                        "type": "InvalidEncryptionKey",
                        "message": key_validation_detail,
                    }
                }
                tlog.add_entry(record_id, Entry(key="image_encryption", value=encryption_log))
                return None
            cmd = [
                SKOPEO_CMD, "copy",
                "--encryption-key", f"jwe:{public_key_path}",
                f"docker-daemon:{image_name}",
                f"oci:{encrypted_path}:latest-encrypted"
            ]

            logger.debug(f"Executing encryption command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                env=self._syft_environment(),
            )

            transport_error = f"{result.stdout}\n{result.stderr}".lower()
            needs_archive_fallback = (
                result.returncode != 0
                and (
                    "client version" in transport_error
                    or "server api version" in transport_error
                    or "api version" in transport_error
                    or "docker-daemon" in transport_error
                )
            )

            if needs_archive_fallback:
                logger.warning(
                    "docker-daemon transport failed during encryption, retrying via docker-archive: %s",
                    result.stderr or result.stdout,
                )

                archive_path = os.path.join(build_path, f"{build_id}-image.tar")
                docker_save_cmd = [DOCKER_CMD, "save", "-o", archive_path, image_name]
                logger.debug(f"Executing docker save command: {' '.join(docker_save_cmd)}")
                docker_save_result = subprocess.run(
                    docker_save_cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if docker_save_result.returncode != 0:
                    logger.error(f"Docker save failed before encryption fallback: {docker_save_result.stderr}")

                    encryption_log = {
                        "public_key_path": public_key_path,
                        "key_validation": key_validation_detail,
                        "command": " ".join(cmd),
                        "exit_code": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "docker_save_command": " ".join(docker_save_cmd),
                        "docker_save_exit_code": docker_save_result.returncode,
                        "docker_save_stdout": docker_save_result.stdout,
                        "docker_save_stderr": docker_save_result.stderr,
                        "status": "failed",
                        "error": {
                            "type": "subprocess.CalledProcessError",
                            "message": docker_save_result.stderr,
                        },
                    }
                    tlog.add_entry(record_id, Entry(key="image_encryption", value=encryption_log))
                    return None

                cmd = [
                    SKOPEO_CMD, "copy",
                    "--encryption-key", f"jwe:{public_key_path}",
                    f"docker-archive:{archive_path}",
                    f"oci:{encrypted_path}:latest-encrypted"
                ]

                logger.debug(f"Executing fallback encryption command: {' '.join(cmd)}")
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env=self._syft_environment(),
                )
            
            if result.returncode == 0:
                logger.info(f"Successfully encrypted image {image_name} to {encrypted_path}")

                encryption_log = {
                    "public_key_path": public_key_path,
                    "key_validation": key_validation_detail,
                    "command": " ".join(cmd),
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "output_path": encrypted_path,
                    "status": "success"
                }
                if docker_save_cmd:
                    encryption_log["docker_save_command"] = " ".join(docker_save_cmd)
                tlog.add_entry(record_id, Entry(key="image_encryption", value=encryption_log))

                # Return OCI reference in the correct format
                return f"oci:{encrypted_path}"  # Return absolute path for skopeo
            else:
                logger.error(f"Image encryption failed: {result.stderr}")
                logger.debug(f"Encryption stdout: {result.stdout}")

                encryption_log = {
                    "public_key_path": public_key_path,
                    "key_validation": key_validation_detail,
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
                if docker_save_cmd:
                    encryption_log["docker_save_command"] = " ".join(docker_save_cmd)
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
        finally:
            if archive_path and os.path.exists(archive_path):
                try:
                    os.remove(archive_path)
                except OSError:
                    logger.debug("Failed to remove temporary archive %s", archive_path)

    def export_image_to_oci(self, image_name: str, build_id: str, tlog: TrustedLogAPI, record_id: str) -> Optional[str]:
        """Export a daemon image to OCI layout without encryption."""
        archive_path = None
        docker_save_cmd = None
        cmd = None
        try:
            build_path = os.path.join(BUILD_DIR, build_id)
            plain_path = os.path.join(build_path, "plain")
            os.makedirs(plain_path, exist_ok=True)

            logger.info(f"Starting OCI export for image: {image_name}")
            archive_path = os.path.join(build_path, f"{build_id}-image.tar")

            docker_save_cmd = [DOCKER_CMD, "save", "-o", archive_path, image_name]
            logger.debug(f"Executing docker save command: {' '.join(docker_save_cmd)}")
            docker_save_result = subprocess.run(
                docker_save_cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if docker_save_result.returncode != 0:
                logger.error(f"Docker save failed before OCI export: {docker_save_result.stderr}")

                export_log = {
                    "docker_save_command": " ".join(docker_save_cmd),
                    "docker_save_exit_code": docker_save_result.returncode,
                    "docker_save_stdout": docker_save_result.stdout,
                    "docker_save_stderr": docker_save_result.stderr,
                    "status": "failed",
                    "error": {
                        "type": "subprocess.CalledProcessError",
                        "message": docker_save_result.stderr,
                    },
                }
                tlog.add_entry(record_id, Entry(key="image_export", value=export_log))
                return None

            cmd = [
                SKOPEO_CMD,
                "copy",
                f"docker-archive:{archive_path}",
                f"oci:{plain_path}:latest",
            ]
            logger.debug(f"Executing OCI export command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                env=self._syft_environment(),
            )

            if result.returncode == 0:
                logger.info(f"Successfully exported image {image_name} to {plain_path}")

                export_log = {
                    "docker_save_command": " ".join(docker_save_cmd),
                    "command": " ".join(cmd),
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "output_path": plain_path,
                    "status": "success",
                }
                tlog.add_entry(record_id, Entry(key="image_export", value=export_log))
                return f"oci:{plain_path}"

            logger.error(f"OCI export failed: {result.stderr}")
            logger.debug(f"OCI export stdout: {result.stdout}")

            export_log = {
                "docker_save_command": " ".join(docker_save_cmd),
                "command": " ".join(cmd),
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "status": "failed",
                "error": {
                    "type": "subprocess.CalledProcessError",
                    "message": result.stderr,
                },
            }
            tlog.add_entry(record_id, Entry(key="image_export", value=export_log))
            return None
        except subprocess.TimeoutExpired:
            logger.error(f"OCI export timed out for image: {image_name}")
            export_log = {
                "docker_save_command": " ".join(docker_save_cmd) if docker_save_cmd else None,
                "command": " ".join(cmd) if cmd else None,
                "status": "timeout",
                "error": {
                    "type": "subprocess.TimeoutExpired",
                    "message": f"OCI export timed out for image: {image_name}",
                },
            }
            tlog.add_entry(record_id, Entry(key="image_export", value=export_log))
            return None
        except FileNotFoundError as exc:
            logger.error(f"OCI export command not found: {exc}")
            export_log = {
                "status": "failed",
                "error": {
                    "type": "FileNotFoundError",
                    "message": str(exc),
                },
            }
            tlog.add_entry(record_id, Entry(key="image_export", value=export_log))
            return None
        except Exception as exc:
            logger.error(f"Unexpected error exporting image to OCI: {str(exc)}")
            export_log = {
                "status": "failed",
                "error": {
                    "type": str(type(exc)),
                    "message": str(exc),
                },
            }
            tlog.add_entry(record_id, Entry(key="image_export", value=export_log))
            return None
        finally:
            if archive_path and os.path.exists(archive_path):
                try:
                    os.remove(archive_path)
                except OSError:
                    logger.debug("Failed to remove temporary archive %s", archive_path)

    def generate_key(self, build_id: str, tlog: TrustedLogAPI, record_id: str, luks_path: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
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
            if luks_path:
                if os.path.exists(luks_path):
                    key_dir = os.path.join(luks_path, build_id)
                else:
                    key_dir = os.path.join(BUILD_DIR, build_id)
                    logger.info("NOW generate key not in luks file.")
            else:
                key_dir = os.path.join(BUILD_DIR, build_id)
                logger.info("NOW generate key not in luks file.")
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


__all__ = ['BuildServiceMixin']
