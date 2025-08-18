from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import JSONResponse
import os
import asyncio
import tempfile
import base64
from datetime import datetime
import json
import shutil
import logging
from models import *
from services import DockerService
from kbs_service import KBSService
from config import HOST, PORT, DEBUG, UPLOAD_DIR, BUILD_DIR, LOGS_DIR

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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
    logger.debug(f"Created directory: {directory}")

@app.get("/")
async def root():
    """Health check endpoint"""
    logger.info("Health check request received")
    return {"message": "TC API Service is running", "timestamp": datetime.now()}

@app.post("/api/build-package", response_model=BuildPackageResponse)
async def build_package(request: BuildPackageRequest, background_tasks: BackgroundTasks):
    """Build and package a container image"""
    try:
        logger.info(f"Build package request received for user: {request.user_id}")
        
        # Generate build ID
        build_id = docker_service.generate_uuid(prefix="bld")
        logger.debug(f"Generated build ID: {build_id}")
        
        # Create build directory
        build_path = os.path.join(BUILD_DIR, build_id)
        os.makedirs(build_path, exist_ok=True)
        logger.debug(f"Created build directory: {build_path}")

        # Save dockerfile content
        dockerfile_path = os.path.join(build_path, "Dockerfile")
        with open(dockerfile_path, "w") as f:
            f.write(request.dockerfile)
        logger.debug(f"Saved Dockerfile to: {dockerfile_path}")

        # Save app binary if provided
        if request.app_binary:
            binary_path = os.path.join(build_path, "app.bin")
            with open(binary_path, "wb") as f:
                f.write(base64.b64decode(request.app_binary))
            logger.debug(f"Saved app binary to: {binary_path}")

        # Save config files if provided
        if request.configs:
            config_dir = os.path.join(build_path, "configs")
            os.makedirs(config_dir, exist_ok=True)
            for i, config in enumerate(request.configs):
                config_path = os.path.join(config_dir, f"config_{i}")
                with open(config_path, "wb") as f:
                    f.write(base64.b64decode(config))
            logger.debug(f"Saved {len(request.configs)} config files")

        # Save data files if provided
        if request.data:
            data_dir = os.path.join(build_path, "data")
            os.makedirs(data_dir, exist_ok=True)
            for i, data in enumerate(request.data):
                data_path = os.path.join(data_dir, f"data_{i}")
                with open(data_path, "wb") as f:
                    f.write(base64.b64decode(data))
            logger.debug(f"Saved {len(request.data)} data files")
        
        # Initialize build status
        docker_service.update_build_status(build_id, "submitted")
        logger.info(f"Build {build_id} status updated to: submitted")
       
        # Start background build process
        background_tasks.add_task(
            build_container_async, 
            request, 
            build_id
        )
        logger.info(f"Started background build task for build ID: {build_id}")
        
        return BuildPackageResponse(
            build_id=build_id,
            status="submitted",
            estimated_time="120s"
        )
        
    except Exception as e:
        logger.error(f"Build package request failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start build: {str(e)}")

async def build_container_async(request: BuildPackageRequest, build_id: str):
    """Async function to build container in background"""
    try:
        # Update status to building
        docker_service.update_build_status(build_id, "building")
        logger.info(f"Starting build process for build ID: {build_id}")
        
        # Build the image
        image_name = f"{request.user_id}-{build_id}:latest"
        logger.debug(f"Building image: {image_name}")
        build_success = docker_service.build_image(request.dockerfile, build_id, request.user_id)
        
        if not build_success:
            logger.error(f"Docker build failed for build ID: {build_id}")
            docker_service.update_build_status(build_id, "failed", error_message="Docker build failed")
            return

        # Generate cosign keys if not provided
        logger.debug(f"cheking sign_key and cert for build ID: {build_id} {request.sign_key} {request.cert}")
        if not request.sign_key or not request.cert:
            logger.info(f"Generating cosign keys for build ID: {build_id}")
            sign_key, cert = docker_service.generate_cosign_keypair(build_id)
            
            if not sign_key or not cert:
                logger.error(f"Failed to generate signing keys for build ID: {build_id}")
                docker_service.update_build_status(
                    build_id, 
                    "failed",
                    error_message="Failed to generate signing keys"
                )
                return
                
            request.sign_key = sign_key
            request.cert = cert
            logger.debug(f"Successfully generated cosign keys for build ID: {build_id}")
            
            # Update build info with key locations
            docker_service.update_build_status(
                build_id,
                "building",
                cert_url=f"/api/artifacts/{build_id}/cosign.crt"
            )

        # Sign and encrypt image if keys are available
        if request.sign_key and request.cert:
            try:
                # Sign image
                logger.info(f"Signing image {image_name}")
                sign_success = docker_service.sign_image(
                    image_name,
                    request.sign_key,
                    request.cert
                )
                if not sign_success:
                    raise Exception("Image signing failed")
                logger.debug(f"Successfully signed image {image_name}")
                
                # Encrypt image if requested
                if request.encrypt:
                    logger.info(f"Encrypting image {image_name}")
                    encrypt_success = docker_service.encrypt_image(
                        image_name,
                        request.cert
                    )
                    if not encrypt_success:
                        raise Exception("Image encryption failed")
                    logger.debug(f"Successfully encrypted image {image_name}")
                
            except Exception as e:
                logger.error(f"Image signing/encryption failed for build ID {build_id}: {str(e)}")
                docker_service.update_build_status(
                    build_id,
                    "failed",
                    error_message=f"Image signing/encryption failed: {str(e)}"
                )
                return

        # Generate and sign SBOM
        try:
            logger.info(f"Generating SBOM for image {image_name}")
            sbom_path = os.path.join(BUILD_DIR, build_id, "sbom.json")
            sbom_success = docker_service.generate_sbom(
                image_name,
                sbom_path
            )
            if not sbom_success:
                raise Exception("SBOM generation failed")
            logger.debug(f"Successfully generated SBOM at {sbom_path}")
            
            # Sign SBOM if keys are available
            if request.sign_key and request.cert:
                logger.info(f"Signing SBOM for build ID {build_id}")
                sbom_sign_success = docker_service.sign_sbom(
                    sbom_path,
                    request.sign_key,
                    request.cert
                )
                if not sbom_sign_success:
                    raise Exception("SBOM signing failed")
                logger.debug(f"Successfully signed SBOM for build ID {build_id}")
                
        except Exception as e:
            logger.error(f"SBOM processing failed for build ID {build_id}: {str(e)}")
            docker_service.update_build_status(
                build_id,
                "failed",
                error_message=f"SBOM processing failed: {str(e)}"
            )
            return

        # Update build status with success
        logger.info(f"Build completed successfully for build ID: {build_id}")
        docker_service.update_build_status(
            build_id,
            "success",
            image_id=image_name,
            sbom_url=f"/api/artifacts/{build_id}/sbom.json",
            image_url=f"docker.io/myrepo/{image_name}",
            cert_url=f"/api/artifacts/{build_id}/cosign.crt"
        )
        
    except Exception as e:
        logger.error(f"Build failed for build ID {build_id}: {str(e)}")
        docker_service.update_build_status(
            build_id,
            "failed",
            error_message=str(e)
        )

@app.put("/api/publish-package", response_model=PublishPackageResponse)
async def publish_package(request: PublishPackageRequest):
    """Publish image and SBOM to registry with key management and logging"""
    try:
        # Extract image name and tags from metadata
        tags = request.metadata.get("tags", ["latest"])
        image_name = f"{request.user_id}-{request.image_id}:{tags[0]}"
        registry_repo = "docker.io/myrepo"
        
        # 1. Push image and SBOM to registry
        push_success = docker_service.push_image(image_name, registry_repo)
        if not push_success:
            raise HTTPException(status_code=500, detail="Failed to push image to registry")
            
        # Push SBOM
        '''
        sbom_success = docker_service.push_sbom(image_name, registry_repo)
        if not sbom_success:
            raise HTTPException(status_code=500, detail="Failed to push SBOM")
        '''
        # 2. Register keys with KBS and RVPS
        build_info = docker_service.get_build_info(request.image_id)
        if not build_info:
            raise HTTPException(status_code=404, detail="Build information not found")
        '''    
        # Register encryption key and signature cert with KBS
        key_registration = await kbs_service.register_keys(
            image_id=request.image_id,
            user_id=request.user_id,
            encryption_cert=build_info.cert,
            signing_cert=build_info.signing_cert,
            policy=request.metadata.get("policy", {})
        )
        
        if not key_registration:
            raise HTTPException(status_code=500, detail="Failed to register keys with KBS")
        '''
        # 3. Publish evidence to transparent log if requested
        log_id = None
        '''
        if request.log_evidence:
            # Create evidence bundle
            evidence = {
                "image_id": request.image_id,
                "user_id": request.user_id,
                "timestamp": datetime.now().isoformat(),
                "build_info": build_info.dict(),
                "metadata": request.metadata
            }
            
            # Submit to transparent log
            log_id = await docker_service.publish_evidence(evidence)
            if not log_id:
                raise HTTPException(status_code=500, detail="Failed to publish evidence")
        '''
        return PublishPackageResponse(
            status="success",
            image_url=f"{registry_repo}/{image_name}",
            sbom_url=f"{registry_repo}/{image_name}.spdx.json",
            log_id=f"tx-{log_id}" if log_id else f"uuid-{uuid.uuid4()}",
            published_at=datetime.now()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to publish package: {str(e)}"
        )


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


@app.post("/api/deploy-launch", response_model=LaunchResponse)
async def deploy_launch(request: LaunchRequest, background_tasks: BackgroundTasks):
    """Deploy and launch container on worker nodes"""
    try:
        # Generate launch ID
        launch_id = docker_service.generate_uuid(prefix="launch")
        
        # Create launch directory
        launch_path = os.path.join(BUILD_DIR, launch_id)
        os.makedirs(launch_path, exist_ok=True)

        # Save launch configuration
        config_path = os.path.join(launch_path, "launch_config.json")
        with open(config_path, "w") as f:
            json.dump(request.dict(), f, indent=2)
            
        # Initialize launch status
        docker_service.update_launch_status(
            launch_id=launch_id,
            status="initiated",
            created_at=datetime.now()
        )
        
        # Start background launch process
        background_tasks.add_task(
            launch_container_async,
            request,
            launch_id,
            launch_path
        )
        
        return LaunchResponse(
            launch_id=launch_id,
            status="initiated"
        )
        
    except Exception as e:
        # Clean up launch directory if creation failed
        if 'launch_path' in locals():
            shutil.rmtree(launch_path, ignore_errors=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to initiate launch: {str(e)}"
        )

async def launch_container_async(request: LaunchRequest, launch_id: str, launch_path: str):
    """Async function to launch container in background"""
    try:
        docker_service.update_launch_status(launch_id, "launching")
        
        # Create log file
        log_file = os.path.join(launch_path, "launch.log")
        with open(log_file, "w") as f:
            f.write(f"Launch started at {datetime.now().isoformat()}\n")

        # 1. Pull and verify image
        pull_success = docker_service.pull_image(
            image_url=request.image_url,
            image_id=request.image_id,
            target_dir=launch_path
        )
        if not pull_success:
            docker_service.update_launch_status(
                launch_id, 
                "failed",
                error_message="Image pull failed"
            )
            return
            
        # 2. Verify SBOM if provided
        if request.sbom_url:
            sbom_valid = docker_service.verify_sbom(
                request.image_id,
                request.sbom_url
            )
            if not sbom_valid:
                docker_service.update_launch_status(
                    launch_id,
                    "failed",
                    error_message="SBOM verification failed"
                )
                return
        
        # 3. Perform attestation and handle decryption
        attestation_result = "trusted"
        if request.attestation_required:
            # Verify attestation and get decryption key
            attestation_result, decryption_key = await docker_service.verify_attestation(
                request.image_id,
                request.user_id
            )
            
            if attestation_result != "trusted":
                docker_service.update_launch_status(
                    launch_id,
                    "failed",
                    error_message=f"Attestation failed: {attestation_result}"
                )
                return
                
            # Decrypt image if attestation passed and key received
            if decryption_key:
                try:
                    decrypted_image = docker_service.decrypt_image(
                        image_id=request.image_id,
                        decryption_key=decryption_key
                    )
                    if not decrypted_image:
                        docker_service.update_launch_status(
                            launch_id,
                            "failed", 
                            error_message="Image decryption failed"
                        )
                        return
                    # Update image reference to use decrypted version
                    request.image_url = decrypted_image
                except Exception as e:
                    docker_service.update_launch_status(
                        launch_id,
                        "failed",
                        error_message=f"Decryption error: {str(e)}"
                    )
                    return
        
        # 4. Launch containers on worker nodes
        instance_ids = await docker_service.launch_containers(
            image_url=request.image_url,
            user_id=request.user_id,
            launch_id=launch_id
        )
        
        if not instance_ids:
            docker_service.update_launch_status(
                launch_id,
                "failed",
                error_message="Container launch failed"
            )
            return
            
        # 5. Create launch evidence
        evidence = {
            "launch_id": launch_id,
            "image_id": request.image_id,
            "user_id": request.user_id,
            "timestamp": datetime.now().isoformat(),
            "attestation_result": attestation_result,
            "instance_ids": instance_ids
        }
        
        # Submit to transparent log
        log_id = await docker_service.publish_evidence(evidence)
        
        # Update launch status to success
        docker_service.update_launch_status(
            launch_id=launch_id,
            status="success",
            validation="passed",
            attestation=attestation_result,
            log_id=f"tx-{log_id}" if log_id else f"uuid-{uuid.uuid4()}",
            instance_ids=instance_ids
        )
        
    except Exception as e:
        docker_service.update_launch_status(
            launch_id,
            "failed",
            error_message=str(e)
        )
        # Log error to launch.log
        with open(os.path.join(launch_path, "launch.log"), "a") as f:
            f.write(f"Error: {str(e)}\n")

@app.get("/api/launch-result/{launch_id}", response_model=LaunchResult)
async def get_launch_result(launch_id: str):
    """Get launch result by launch ID"""
    try:
        launch_result = docker_service.get_launch_status(launch_id)
        
        if not launch_result:
            raise HTTPException(
                status_code=404,
                detail="Launch not found"
            )
        
        return launch_result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get launch result: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, log_level="debug")
