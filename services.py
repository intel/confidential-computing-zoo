import subprocess
import uuid
import os
import json
import logging
import time
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from models import BuildResult, LaunchResult
from config import *

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class DockerService:
    def __init__(self):
        self.builds: Dict[str, BuildResult] = {}
        self.launchs: Dict[str, LaunchResult] = {}
    
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
            self.update_build_status(build_id, "preparing", step="Setting up build environment")
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
            
            self.update_build_status(build_id, "building", step="Building container image")
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
                # Return OCI reference in the correct format
                return f"oci:{encrypted_path}"  # Return absolute path for skopeo
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
    
    def sign_image(self, image_name: str, private_key_path: str) -> Tuple[bool, Optional[str]]:
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
                return True, signature_ref
            else:
                logger.error(f"Failed to sign image: {result.stderr}")
                logger.debug(f"Sign stdout: {result.stdout}")
                return False, None
                
        except subprocess.TimeoutExpired:
            logger.error(f"Image signing timed out for: {image_name}")
            return False, None
        except FileNotFoundError:
            logger.error(f"Cosign command not found: {COSIGN_CMD}")
            return False, None
        except Exception as e:
            logger.error(f"Unexpected error signing image: {str(e)}")
            return False, None
    
    def create_sbom_attestation(self, image_name: str, sbom_path: str, private_key_path: str) -> Tuple[bool, Optional[str]]:
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
                return False, None
            
            if not os.path.exists(private_key_path):
                logger.error(f"Private key file not found: {private_key_path}")
                return False, None
            
            # Validate SBOM content
            try:
                with open(sbom_path, 'r', encoding='utf-8') as f:
                    sbom_data = json.load(f)
                if not sbom_data.get('spdxVersion'):
                    logger.warning("SBOM may be invalid - missing spdxVersion")
            except (json.JSONDecodeError, Exception) as e:
                logger.error(f"Invalid SBOM file: {e}")
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
                return True, attestation_ref
            else:
                logger.error(f"Failed to create SBOM attestation: {result.stderr}")
                logger.debug(f"Attestation stdout: {result.stdout}")
                return False, None
                
        except subprocess.TimeoutExpired:
            logger.error(f"SBOM attestation timed out for: {image_name}")
            return False, None
        except FileNotFoundError:
            logger.error(f"Cosign command not found: {COSIGN_CMD}")
            return False, None
        except Exception as e:
            logger.error(f"Unexpected error creating SBOM attestation: {str(e)}")
            return False, None
    
    def push_image(self, source_ref: str, dest_ref: str, max_retries: int = 3, retry_delay: int = 5) -> bool:
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
                    return True
                else:
                    logger.warning(f"Push attempt {attempt} failed: {result.stderr}")
                    logger.debug(f"Push stdout: {result.stdout}")
                    
                    if attempt < max_retries:
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"All push attempts failed after {max_retries} tries")
                        return False
                
            except subprocess.TimeoutExpired:
                logger.warning(f"Push attempt {attempt} timed out")
                if attempt < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"All push attempts timed out after {max_retries} tries")
                    return False
            except FileNotFoundError:
                logger.error(f"Skopeo command not found: {SKOPEO_CMD}")
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
    
    def update_build_status(self, build_id: str, status: str, step: str = None, **kwargs):
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
            #attestation_report = await self._get_attestation_report(image_id)
            
            # Verify with KBS service
            attestation_result, decryption_key = self.get_pubKey_from_KBS() 
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
            #with tempfile.NamedTemporaryFile(mode='w', suffix='.key', delete=False) as f:
            #    f.write(decryption_key)
            #    key_path = f.name
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
    
    def generate_key(self, build_id: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
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
                return None, None, None, None

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


    def pull_image(self, image_url: str, openssl_key: str, target_dir: str, max_retries: int = 3, retry_delay: int = 5) -> bool:

        #  skopeo copy --decryption-key bld-437a737-openssl.key docker://testsig/test-bld-437a737:latest-encrypted oci:./encrypt
        #  skopeo copy oci:encrypt/ docker-daemon:test_pull:v1.0
        
        source_ref = image_url.replace("docker.io","docker:/")
        #openssl_key = image_id[5:]+'-openssl.key'
        dest_ref = os.path.join('oci:'+target_dir,'encrypted')

        attempt = 0
        while attempt < max_retries:
            try:
                attempt += 1
                logger.info(f"Pulling image (attempt {attempt}/{max_retries}): {source_ref}")

                cmd = [SKOPEO_CMD, "copy", "--decryption-key", openssl_key, source_ref, dest_ref]
                logger.debug(f"Pull command: {' '.join(cmd)}")

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

                if result.returncode == 0:
                    logger.info(f"Successfully pulled image to local")
                    return True
                else:
                    logger.warning(f"Pull attempt {attempt} failed: {result.stderr}")
                    logger.debug(f"Pull stdout: {result.stdout}")

                    if attempt < max_retries:
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"All pull attempts failed after {max_retries} tries")
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
                return False  # Don't retry if command not found
            except Exception as e:
                logger.warning(f"Pull attempt {attempt} failed with error: {str(e)}")
                if attempt < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"All pull attempts failed after {max_retries} tries: {str(e)}")
                    return False

        return False

    def update_launch_status(self, launch_id: str, status: str, **kwargs):

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
                    launch_id=launch_id,
                    status=status,
                    #created_at=datetime.now(),
                    updated_at=datetime.now(),
                    **kwargs
                )

        except Exception as e:
            logger.error(f"Error updating build status for {launch_id}: {str(e)}")

    def verify_sbom(self,imagesurl,sbom_url,cosign_pubkey='cosign.pub') -> bool:

        images_fullName = imagesurl.replace("docker.io/","")
        # 1. verify signed image
        # cosign verify images : cosign verify --key keyfile image_name
        try:
            cosign_cmd = [
                    COSIGN_CMD, "verify", "--key", cosign_pubkey, images_fullName
                ]
            cosign_verify = subprocess.run(cosign_cmd, capture_output=True, text=True)
            logger.info(f"Vertify CMD: {' '.join(cosign_cmd)}")

            if cosign_verify.returncode != 0:
                logger.debug(f"Failed to verify: {cosign_verify.stderr}")
                return False

        except Exception as e:
            logger.error(f"Verify signed image {images_fullName} failed: {str(e)}")

        #2. verify attestation
        # cosign verify-attestation --key keyfile --type spdx image_name | jq -r '.payload' | base64 -d > verified_sbom.json
        try:
            cosign_attcmd = [
                    COSIGN_CMD, "verify-attestation", "--key", cosign_pubkey, "--type", "spdx", imagesurl]
            
            cosign_attverify = subprocess.run(cosign_attcmd, capture_output=True, text=True)
            logger.info(f"Attestation_Vertify CMD: {' '.join(cosign_attcmd)}")

            if cosign_attverify.returncode != 0:
                logger.debug(f"Failed to verify: {cosign_attverify.stderr}")
                return False
            
            # verify sbom file for detial
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
        


    def get_launch_status(self, launch_id: str) -> Optional[BuildResult]:
        """Get launch status by launch_id"""
        return self.launchs.get(launch_id)


    async def launch_containers(self,image_url,user_id,launch_pth):
        # skopeo copy oci:encrypt/ docker-daemon:test_pull:latest
        image_dir = 'oci:' + os.path.join(launch_pth,'encrypted')
        Newimage_name = 'docker-daemon:'+ user_id + ":latest"
        try:
            cmd = [SKOPEO_CMD, "copy", image_dir, Newimage_name]
            res = subprocess.run(cmd, capture_output=True, text=True)

            if res.returncode == 0:
                logger.info("Success add image.")
            else:
                logger.info("Failed add image.")
                logger.debug(f"CMD: {' '.join(cmd)}")
                return False

            # docker run -d -p 8088:8088 test
            docker_cmd = [DOCKER_CMD, "run", "-d", "-p", "8088:8088", user_id]
            dockerRUn = subprocess.run(docker_cmd, capture_output=True, text=True)
            if dockerRUn.returncode == 0:
                logger.info("Success run image.")
                return [dockerRUn.stdout]
            else:
                logger.info("Failed run image.")
                logger.debug(f"CMD: {" ".join(docker_cmd)}")
                return False

        except Exception as e:
            logger.error(f"Launch contaioner failed: {str(e)}")
            return False


    def get_pubKey_from_KBS(self):
        try:
            opensslKey_cmd = ["curl", KBS_URL+"openssl.key", "-o","openssl.key"]
            cosignPub_cmd = ["curl", KBS_URL+"cosign.pub", "-o","cosign.pub"]
            opensslPub_cmd = ["curl", KBS_URL+"openssl.pub", "-o","openssl.pub"]
            cosignKey_cmd = ["curl", KBS_URL+"cosign.key", "-o","cosign.key"]
            opensslKey_res = subprocess.run(opensslKey_cmd, capture_output=True, text=True)
            cosignPub_res = subprocess.run(cosignPub_cmd, capture_output=True, text=True)
            opensslPub_res = subprocess.run(opensslPub_cmd, capture_output=True, text=True)
            cosignKey_res = subprocess.run(cosignKey_cmd, capture_output=True, text=True)

            if (opensslKey_res.returncode != 0) or (cosignPub_res.returncode != 0):
                logger.info(f"excute get key cmd failed!Error: {cosignPub_res.stderr}")
                logger.info(f"excute get key cmd failed!Error: {opensslKey_res.stderr}")

            if os.path.exists("openssl.key") and os.path.exists("cosign.pub") and os.path.exists("openssl.pub") and os.path.exists("cosign.key"):
                logger.info("Success get key!")
                opssl_key = os.path.realpath('openssl.key')
                cosign_key = os.path.realpath('cosign.key')
                opssl_pub = os.path.realpath('openssl.pub')
                cosign_pub = os.path.realpath('cosign.pub')

            else:
                logger.info("Failed get key!")
                return False, None

            return 'trusted', {'opensslKey':opssl_key, 'cosignKey':cosign_key, 'opensslPub':opssl_pub, 'cosignPub':cosign_pub}
        except Exception as e:
            logger.error(f"Launch contaioner failed: {str(e)}")
            return False, None
