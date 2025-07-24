import subprocess
import uuid
import os
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from models import BuildResult
from config import *

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DockerService:
    def __init__(self):
        self.builds: Dict[str, BuildResult] = {}
    
    def generate_build_id(self) -> str:
        """Generate a unique build ID"""

        return f"bld-{str(uuid.uuid4())[:8]}"
    
    def build_image(self, dockerfile_content: str, build_id: str, user_id: str) -> bool:
        """Build Docker image from dockerfile content"""
        try:
            build_path = os.path.join(BUILD_DIR, build_id)
            os.makedirs(build_path, exist_ok=True)
            logger.info(f"Building image for user {user_id} with build ID {build_id} at {build_path} {dockerfile_content}")
            # Write dockerfile to build directory
            dockerfile_path = os.path.join(build_path, "Dockerfile")
            with open(dockerfile_path, 'w') as f:
                f.write(dockerfile_content)
            
            # Build the image
            image_name = f"{user_id}-{build_id}:latest"
            cmd = [DOCKER_CMD, "build", "-t", image_name, build_path]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Successfully built image {image_name}")
                return True
            else:
                logger.error(f"Failed to build image: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error building image: {str(e)}")
            return False
    
    def generate_sbom(self, image_name: str, build_id: str) -> Optional[str]:
        """Generate SBOM for the image"""
        try:
            sbom_path = os.path.join(BUILD_DIR, build_id, f"{build_id}-sbom.json")
            cmd = [SYFT_CMD, image_name, "-o", "spdx-json"]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                with open(sbom_path, 'w') as f:
                    f.write(result.stdout)
                return sbom_path
            else:
                logger.error(f"Failed to generate SBOM: {result.stderr}")
                return None
                
        except Exception as e:
            logger.error(f"Error generating SBOM: {str(e)}")
            return None
    
    def encrypt_image(self, image_name: str, build_id: str, public_key_path: str) -> Optional[str]:
        """Encrypt image using skopeo"""
        try:
            encrypted_name = f"{image_name}-encrypted"
            plain_oci_path = os.path.join(BUILD_DIR, build_id, "plain")
            encrypted_oci_path = os.path.join(BUILD_DIR, build_id, "encrypted")
            
            # Copy to plain OCI format
            cmd1 = [SKOPEO_CMD, "copy", f"docker-daemon:{image_name}", f"oci:{plain_oci_path}:latest"]
            result1 = subprocess.run(cmd1, capture_output=True, text=True)
            
            if result1.returncode != 0:
                logger.error(f"Failed to copy to OCI format: {result1.stderr}")
                return None
            
            # Encrypt the image
            cmd2 = [SKOPEO_CMD, "copy", "--encryption-key", public_key_path, 
                   f"oci:{plain_oci_path}:latest", f"oci:{encrypted_oci_path}:latest"]
            result2 = subprocess.run(cmd2, capture_output=True, text=True)
            
            if result2.returncode != 0:
                logger.error(f"Failed to encrypt image: {result2.stderr}")
                return None
            
            # Copy back to Docker daemon
            cmd3 = [SKOPEO_CMD, "copy", f"oci:{encrypted_oci_path}:latest", f"docker-daemon:{encrypted_name}"]
            result3 = subprocess.run(cmd3, capture_output=True, text=True)
            
            if result3.returncode == 0:
                return encrypted_name
            else:
                logger.error(f"Failed to copy encrypted image back: {result3.stderr}")
                return None
                
        except Exception as e:
            logger.error(f"Error encrypting image: {str(e)}")
            return None
    
    def sign_image(self, image_name: str, private_key_path: str) -> bool:
        """Sign image with cosign"""
        try:
            cmd = [COSIGN_CMD, "sign", "--key", private_key_path, image_name]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Successfully signed image {image_name}")
                return True
            else:
                logger.error(f"Failed to sign image: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error signing image: {str(e)}")
            return False
    
    def create_sbom_attestation(self, image_name: str, sbom_path: str, private_key_path: str) -> bool:
        """Create and publish SBOM attestation"""
        try:
            cmd = [COSIGN_CMD, "attest", "--key", private_key_path, 
                   "--predicate", sbom_path, "--type", "spdx", image_name]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Successfully created SBOM attestation for {image_name}")
                return True
            else:
                logger.error(f"Failed to create SBOM attestation: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error creating SBOM attestation: {str(e)}")
            return False
    
    def push_image(self, image_name: str, registry_repo: str) -> bool:
        """Push image to registry"""
        try:
            remote_name = f"{registry_repo}/{image_name}"
            
            # Tag the image
            tag_cmd = [DOCKER_CMD, "tag", image_name, remote_name]
            tag_result = subprocess.run(tag_cmd, capture_output=True, text=True)
            
            if tag_result.returncode != 0:
                logger.error(f"Failed to tag image: {tag_result.stderr}")
                return False
            
            # Push the image
            push_cmd = [DOCKER_CMD, "push", remote_name]
            push_result = subprocess.run(push_cmd, capture_output=True, text=True)
            
            if push_result.returncode == 0:
                logger.info(f"Successfully pushed image to {remote_name}")
                return True
            else:
                logger.error(f"Failed to push image: {push_result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error pushing image: {str(e)}")
            return False
    
    def get_build_status(self, build_id: str) -> Optional[BuildResult]:
        """Get build status by build_id"""
        return self.builds.get(build_id)
    
    def update_build_status(self, build_id: str, status: str, **kwargs):
        """Update build status"""
        if build_id in self.builds:
            build_result = self.builds[build_id]
            build_result.status = status
            build_result.updated_at = datetime.now()
            
            for key, value in kwargs.items():
                if hasattr(build_result, key):
                    setattr(build_result, key, value)
        else:
            # Create new build result
            self.builds[build_id] = BuildResult(
                build_id=build_id,
                status=status,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                **kwargs
            )
