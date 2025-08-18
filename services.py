import subprocess
import uuid
import os
import json
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from models import BuildResult
from config import *

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class DockerService:
    def __init__(self):
        self.builds: Dict[str, BuildResult] = {}
    
    def generate_uuid(self, prefix: str = "bld") -> str:
        """
        Generate a unique ID with specified prefix
        
        Args:
            prefix: Prefix for the ID ("bld" for build, "launch" for launch)
            
        Returns:
            str: Generated ID in format "{prefix}-{uuid}"
        """
        return f"{prefix}-{uuid.uuid4().hex[:7]}"
    
    def build_image(self, dockerfile_content: str, build_id: str, user_id: str) -> bool:
        """Build Docker image from dockerfile content with optimized error handling"""
        try:
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
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode == 0:
                logger.info(f"Successfully built image {image_name}")
                
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
    
    def generate_sbom(self, image_name: str, build_id: str) -> Optional[str]:
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
                return sbom_path
            else:
                logger.error(f"Failed to generate SBOM: {result.stderr}")
                logger.debug(f"SBOM stdout: {result.stdout}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"SBOM generation timed out for: {image_name}")
            return None
        except FileNotFoundError:
            logger.error(f"Syft command not found: {SYFT_CMD}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating SBOM: {str(e)}")
            return None
    
    def encrypt_image(self, image_name: str, build_id: str, public_key_path: str) -> Optional[str]:
        """Encrypt image using skopeo with optimized workflow"""
        try:
            encrypted_name = f"{image_name}-encrypted"
            work_dir = os.path.join(BUILD_DIR, build_id, "encryption")
            os.makedirs(work_dir, exist_ok=True)
            
            # Validate public key exists
            if not os.path.exists(public_key_path):
                logger.error(f"Public key file not found: {public_key_path}")
                return None
            
            logger.info(f"Starting encryption process for image: {image_name}")
            
            # Direct encryption: docker-daemon -> docker-daemon with encryption
            # This skips intermediate OCI storage for better performance
            cmd = [
                SKOPEO_CMD, "copy",
                "--encryption-key", public_key_path,
                f"docker-daemon:{image_name}",
                f"docker-daemon:{encrypted_name}"
            ]
            
            logger.debug(f"Executing encryption command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                logger.info(f"Successfully encrypted image: {image_name} -> {encrypted_name}")
                
                # Verify encrypted image exists
                verify_cmd = [DOCKER_CMD, "images", encrypted_name, "--quiet"]
                verify_result = subprocess.run(verify_cmd, capture_output=True, text=True)
                
                if verify_result.returncode == 0 and verify_result.stdout.strip():
                    return encrypted_name
                else:
                    logger.error(f"Encrypted image verification failed: {encrypted_name}")
                    return None
            else:
                logger.error(f"Image encryption failed: {result.stderr}")
                logger.debug(f"Encryption stdout: {result.stdout}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"Image encryption timed out for: {image_name}")
            return None
        except FileNotFoundError:
            logger.error(f"Skopeo command not found: {SKOPEO_CMD}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during image encryption: {str(e)}")
            return None
    
    def sign_image(self, image_name: str, private_key_path: str) -> bool:
        """Sign image with cosign with enhanced validation"""
        try:
            # Validate private key exists
            if not os.path.exists(private_key_path):
                logger.error(f"Private key file not found: {private_key_path}")
                return False
            
            # Set environment to skip password prompt for testing
            env = os.environ.copy()
            env['COSIGN_PASSWORD'] = ''  # Empty password for testing keys
            
            cmd = [COSIGN_CMD, "sign", "--key", private_key_path, image_name, "--yes"]
            
            logger.info(f"Signing image: {image_name}")
            logger.debug(f"Sign command: {' '.join(cmd[:4])} [key-file] {image_name} --yes")
            
            result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
            
            if result.returncode == 0:
                logger.info(f"Successfully signed image {image_name}")
                return True
            else:
                logger.error(f"Failed to sign image: {result.stderr}")
                logger.debug(f"Sign stdout: {result.stdout}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Image signing timed out for: {image_name}")
            return False
        except FileNotFoundError:
            logger.error(f"Cosign command not found: {COSIGN_CMD}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error signing image: {str(e)}")
            return False
    
    def create_sbom_attestation(self, image_name: str, sbom_path: str, private_key_path: str) -> bool:
        """Create and publish SBOM attestation with validation"""
        try:
            # Validate inputs
            if not os.path.exists(sbom_path):
                logger.error(f"SBOM file not found: {sbom_path}")
                return False
            
            if not os.path.exists(private_key_path):
                logger.error(f"Private key file not found: {private_key_path}")
                return False
            
            # Validate SBOM content
            try:
                with open(sbom_path, 'r', encoding='utf-8') as f:
                    sbom_data = json.load(f)
                if not sbom_data.get('spdxVersion'):
                    logger.warning("SBOM may be invalid - missing spdxVersion")
            except (json.JSONDecodeError, Exception) as e:
                logger.error(f"Invalid SBOM file: {e}")
                return False
            
            # Set environment for cosign
            env = os.environ.copy()
            env['COSIGN_PASSWORD'] = ''  # Empty password for testing keys
            
            cmd = [
                COSIGN_CMD, "attest",
                "--key", private_key_path,
                "--predicate", sbom_path,
                "--type", "spdx",
                image_name,
                "--yes"
            ]
            
            logger.info(f"Creating SBOM attestation for: {image_name}")
            logger.debug(f"Attest command: {' '.join(cmd[:6])} [key-file] --predicate [sbom-file] --type spdx {image_name} --yes")
            
            result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
            
            if result.returncode == 0:
                logger.info(f"Successfully created SBOM attestation for {image_name}")
                return True
            else:
                logger.error(f"Failed to create SBOM attestation: {result.stderr}")
                logger.debug(f"Attestation stdout: {result.stdout}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"SBOM attestation timed out for: {image_name}")
            return False
        except FileNotFoundError:
            logger.error(f"Cosign command not found: {COSIGN_CMD}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error creating SBOM attestation: {str(e)}")
            return False
    
    def push_image(self, image_name: str, registry_repo: str) -> bool:
        """Push image to registry with retry logic"""
        try:
            remote_name = f"{registry_repo}/{image_name}"
            
            logger.info(f"Pushing image: {image_name} -> {remote_name}")
            
            # Tag the image
            tag_cmd = [DOCKER_CMD, "tag", image_name, remote_name]
            logger.debug(f"Tag command: {' '.join(tag_cmd)}")
            
            tag_result = subprocess.run(tag_cmd, capture_output=True, text=True, timeout=60)
            
            if tag_result.returncode != 0:
                logger.error(f"Failed to tag image: {tag_result.stderr}")
                return False
            
            # Push the image with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    push_cmd = [DOCKER_CMD, "push", remote_name]
                    logger.debug(f"Push command (attempt {attempt + 1}): {' '.join(push_cmd)}")
                    
                    push_result = subprocess.run(push_cmd, capture_output=True, text=True, timeout=300)
                    
                    if push_result.returncode == 0:
                        logger.info(f"Successfully pushed image to {remote_name}")
                        return True
                    else:
                        logger.warning(f"Push attempt {attempt + 1} failed: {push_result.stderr}")
                        if attempt < max_retries - 1:
                            logger.info(f"Retrying push in 5 seconds...")
                            import time
                            time.sleep(5)
                        
                except subprocess.TimeoutExpired:
                    logger.warning(f"Push attempt {attempt + 1} timed out")
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying push...")
            
            logger.error(f"Failed to push image after {max_retries} attempts")
            return False
                
        except FileNotFoundError:
            logger.error(f"Docker command not found: {DOCKER_CMD}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error pushing image: {str(e)}")
            return False
    
    def get_build_status(self, build_id: str) -> Optional[BuildResult]:
        """Get build status by build_id"""
        return self.builds.get(build_id)
    
    def update_build_status(self, build_id: str, status: str, **kwargs):
        """Update build status with enhanced tracking"""
        try:
            if build_id in self.builds:
                build_result = self.builds[build_id]
                old_status = build_result.status
                build_result.status = status
                build_result.updated_at = datetime.now()
                
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
                    build_id=build_id,
                    status=status,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    **kwargs
                )
                
        except Exception as e:
            logger.error(f"Error updating build status for {build_id}: {str(e)}")
    
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
    
    async def verify_attestation(self, image_id: str, user_id: str) -> Tuple[str, Optional[str]]:
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
            # Get attestation report from worker node
            attestation_report = await self._get_attestation_report(image_id)
            
            # Verify with KBS service
            attestation_result, decryption_key = await self.kbs_service.verify_attestation(
                attestation_report=attestation_report,
                image_id=image_id,
                user_id=user_id
            )
            
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
            with tempfile.NamedTemporaryFile(mode='w', suffix='.key', delete=False) as f:
                f.write(decryption_key)
                key_path = f.name
                
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
    
    def generate_cosign_keypair(self, build_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Generate a cosign key pair for signing and encryption
        
        Args:
            build_id: Build ID for key file naming
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (private_key, certificate) content
            Returns (None, None) if generation fails
        """
        try:
            key_path = os.path.join(BUILD_DIR, build_id, "cosign.key")
            cert_path = os.path.join(BUILD_DIR, build_id, "cosign.crt")
            logger.info(f"Generating cosign key pair at {key_path} and {cert_path}")
            # Generate key pair using cosign
            cmd = [
                "cosign", "generate-key-pair",
                "--output-key-file", key_path,
                "--output-cert-file", cert_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Failed to generate cosign keys: {result.stderr}")
                return None, None
            
            # Read generated keys
            with open(key_path, 'r') as f:
                private_key = f.read()
            with open(cert_path, 'r') as f:
                certificate = f.read()
                
            return private_key, certificate
            
        except Exception as e:
            logger.error(f"Key generation failed: {str(e)}")
            return None, None
