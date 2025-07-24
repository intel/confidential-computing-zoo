from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import JSONResponse
import os
import asyncio
import tempfile
from datetime import datetime
from models import *
from services import DockerService
from kbs_service import KBSService
from config import HOST, PORT, DEBUG, UPLOAD_DIR, BUILD_DIR, LOGS_DIR

# Initialize FastAPI app
app = FastAPI(
    title="TC API - Trusted Container Build and Publish Service",
    description="RESTful API for building, signing, encrypting and publishing Docker images",
    version="1.0.0"
)

# Initialize services
docker_service = DockerService()
kbs_service = KBSService()

# Create necessary directories
for directory in [UPLOAD_DIR, BUILD_DIR, LOGS_DIR]:
    os.makedirs(directory, exist_ok=True)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "TC API Service is running", "timestamp": datetime.now()}

@app.post("/api/build-package", response_model=BuildPackageResponse)
async def build_package(request: BuildPackageRequest, background_tasks: BackgroundTasks):
    """Build and package a container image"""
    try:
        # Generate build ID
        build_id = docker_service.generate_build_id()
        
        # Initialize build status
        docker_service.update_build_status(build_id, "submitted")
       
        # Start background build process
        background_tasks.add_task(
            build_container_async, 
            request, 
            build_id
        )
        
        return BuildPackageResponse(
            build_id=build_id,
            status="submitted",
            estimated_time="120s"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start build: {str(e)}")

async def build_container_async(request: BuildPackageRequest, build_id: str):
    """Async function to build container in background"""
    try:
        # Update status to building
        docker_service.update_build_status(build_id, "building")
        
        # Build the image
        image_name = f"{request.user_id}-{build_id}:latest"
        build_success = docker_service.build_image(request.dockerfile, build_id, request.user_id)
        
        if not build_success:
            docker_service.update_build_status(build_id, "failed", error_message="Docker build failed")
            return
        
        # Generate SBOM
        sbom_path = docker_service.generate_sbom(image_name, build_id)
        if not sbom_path:
            docker_service.update_build_status(build_id, "failed", error_message="SBOM generation failed")
            return
        
        final_image_name = image_name
        
        # Encrypt if requested
        if request.encrypt:
            # Save public key to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.pub', delete=False) as f:
                f.write(request.cert)  # Using cert as public key for encryption
                pub_key_path = f.name
            
            try:
                encrypted_name = docker_service.encrypt_image(image_name, build_id, pub_key_path)
                if encrypted_name:
                    final_image_name = encrypted_name
                else:
                    docker_service.update_build_status(build_id, "failed", error_message="Image encryption failed")
                    return
            finally:
                os.unlink(pub_key_path)
        
        # Sign the image
        with tempfile.NamedTemporaryFile(mode='w', suffix='.key', delete=False) as f:
            f.write(request.sign_key)
            private_key_path = f.name
        
        try:
            sign_success = docker_service.sign_image(final_image_name, private_key_path)
            if not sign_success:
                docker_service.update_build_status(build_id, "failed", error_message="Image signing failed")
                return
            
            # Create SBOM attestation
            attestation_success = docker_service.create_sbom_attestation(
                final_image_name, sbom_path, private_key_path
            )
            if not attestation_success:
                docker_service.update_build_status(build_id, "failed", error_message="SBOM attestation failed")
                return
                
        finally:
            os.unlink(private_key_path)
        
        # Get image ID (simplified - in real implementation, get from docker inspect)
        image_id = f"sha256:{build_id}abcd1234"
        
        # Update build status to success
        docker_service.update_build_status(
            build_id, 
            "success",
            image_id=image_id,
            sbom_url=f"/api/artifacts/{build_id}/sbom.json",
            image_url=f"docker.io/myrepo/{final_image_name}",
            cert_url=f"/api/artifacts/{build_id}/cert.pem",
            log_url=f"/api/artifacts/{build_id}/log.txt"
        )
        
    except Exception as e:
        docker_service.update_build_status(build_id, "failed", error_message=str(e))

@app.put("/api/publish-package")
async def publish_package(request: PublishPackageRequest):
    """Publish image and SBOM to registry"""
    try:
        # Extract image name from metadata
        tags = request.metadata.get("tags", ["latest"])
        image_name = f"{request.user_id}-image:{tags[0]}"
        
        # Push to registry (simplified implementation)
        registry_repo = f"docker.io/myrepo"
        push_success = docker_service.push_image(image_name, registry_repo)
        
        if not push_success:
            raise HTTPException(status_code=500, detail="Failed to push image to registry")
        
        return {
            "status": "success",
            "message": "Image and SBOM published successfully",
            "image_url": f"{registry_repo}/{image_name}",
            "published_at": datetime.now()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to publish package: {str(e)}")

@app.post("/api/keys/register")
async def register_key(request: RegisterKeyRequest):
    """Register key metadata with KBS"""
    try:
        # Convert policy model to dict
        policy_dict = request.policy.model_dump()
        
        # Register with KBS
        success = kbs_service.register_key(
            request.image_id,
            request.user_id,
            request.public_key,
            request.cert,
            policy_dict
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to register key with KBS")
        
        return {
            "status": "success",
            "message": "Key metadata registered successfully",
            "image_id": request.image_id,
            "user_id": request.user_id,
            "registered_at": datetime.now()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register key: {str(e)}")

@app.get("/api/build-result/{build_id}", response_model=BuildResult)
async def get_build_result(build_id: str):
    """Get build result by build ID"""
    try:
        build_result = docker_service.get_build_status(build_id)
        
        if not build_result:
            raise HTTPException(status_code=404, detail="Build not found")
        
        return build_result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get build result: {str(e)}")

@app.get("/api/artifacts/{build_id}/{artifact_type}")
async def get_artifact(build_id: str, artifact_type: str):
    """Get build artifacts (SBOM, logs, etc.)"""
    try:
        artifact_path = os.path.join(BUILD_DIR, build_id, f"{build_id}-{artifact_type}")
        
        if not os.path.exists(artifact_path):
            raise HTTPException(status_code=404, detail="Artifact not found")
        
        # In a real implementation, return the file content
        return {"message": f"Artifact {artifact_type} for build {build_id}", "path": artifact_path}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get artifact: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, log_level="debug")
