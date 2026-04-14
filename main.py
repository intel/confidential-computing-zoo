from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os
import uuid
import asyncio
import tempfile
import base64
from datetime import datetime
import json
import shutil
import logging
import hashlib
import pickle
from sigstore.oidc import Issuer
from trusted_container_log import ChainedTransparencyLog
from models import *
from services import DockerService
from kbs_service import KBSService
from config import (
    HOST, PORT, DEBUG, UPLOAD_DIR, BUILD_DIR, LOGS_DIR,
    DOCKER_REGISTRY, DOCKER_REPOSITORY, ENABLE_TDX, TRUCON_URL
)

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def has_proxy_configuration() -> bool:
    proxy_keys = (
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
    )
    return any(os.environ.get(key) for key in proxy_keys)


def log_proxy_configuration(operation: str) -> None:
    if has_proxy_configuration():
        logger.info("%s using configured proxy environment", operation)
    else:
        logger.info("%s running without proxy environment", operation)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    from trusted_container_log.api import TrustedLogAPI
    from trusted_container_log.tlog_impl import SigstoreLogAdapter
    
    # tc_api is stateless for the commit path — RTMR extend is TruCon's job.
    # local_mr is no longer used here.
    app.state.trusted_log = TrustedLogAPI(
        local_mr=None,
        immutable_log=SigstoreLogAdapter(),
        trucon_url=TRUCON_URL,
    )
    
    yield
    
    # Shutdown logic
    logger.info("TC API Service shutting down...")

# Initialize FastAPI app
app = FastAPI(
    title="TC API - Trusted Container Build and Publish Service",
    description="RESTful API for building, signing, encrypting and publishing Docker images",
    version="1.0.0",
    lifespan=lifespan
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
        
        tl_signer = ChainedTransparencyLog()
        tl_signer.add_entry({"build_id": build_id})

        # Create build directory
        build_path = os.path.join(BUILD_DIR, build_id)
        os.makedirs(build_path, exist_ok=True)
        logger.debug(f"Created build directory: {build_path}")

        tl_signer.add_entry({"build_path": build_path})

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

        binary_hash = hashlib.sha256(base64.b64decode(request.app_binary)).hexdigest()
        tl_signer.add_entry({"app_binary_path": binary_path, "app_binary_hash": binary_hash})
        
        # Save config files if provided
        if request.configs:
            config_dir = os.path.join(build_path, "configs")
            os.makedirs(config_dir, exist_ok=True)
            for i, config in enumerate(request.configs):
                config_path = os.path.join(config_dir, f"config_{i}")
                with open(config_path, "wb") as f:
                    f.write(base64.b64decode(config))
            logger.debug(f"Saved {len(request.configs)} config files")
            config_hashes = [hashlib.sha256(base64.b64decode(c)).hexdigest() for c in request.configs]
            tl_signer.add_entry({"config_dir": config_dir,
                                 "config_count": len(request.configs),
                                 "config_hashes": config_hashes})

        # Save data files if provided
        if request.data:
            data_dir = os.path.join(build_path, "data")
            os.makedirs(data_dir, exist_ok=True)
            for i, data in enumerate(request.data):
                data_path = os.path.join(data_dir, f"data_{i}")
                with open(data_path, "wb") as f:
                    f.write(base64.b64decode(data))
            logger.debug(f"Saved {len(request.data)} data files")
            data_hashes = [hashlib.sha256(base64.b64decode(d)).hexdigest() for d in request.data]
            tl_signer.add_entry({"data_dir": data_dir,
                                 "data_count": len(request.data),
                                 "data_hashes": data_hashes})
        
        # Initialize build status
        docker_service.update_build_status(request.user_id, build_id, "submitted")
        logger.info(f"Build {build_id} status updated to: submitted")
        # Start background build process
        background_tasks.add_task(
            build_container_async, 
            request, 
            build_id,
            tl_signer
        )
        logger.info(f"Started background build task for build ID: {build_id}")
        
        # Return immediately with submitted status
        return BuildPackageResponse(
            build_id=build_id,
            status="submitted",
            estimated_time="120s",
            user_id=request.user_id
        )
        
    except Exception as e:
        logger.error(f"Build package request failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start build: {str(e)}")

def build_container_async(request: BuildPackageRequest, build_id: str, tl_signer: ChainedTransparencyLog):
    """Function to build container in background with detailed status tracking"""
    try:
        # Start with preparing status
        docker_service.update_build_status(request.user_id, build_id, "preparing", step="Initializing build process")
        logger.info(f"Starting build process for build ID: {build_id}")
        
        # Build the image
        image_name = f"{request.user_id}-{build_id}:latest"
        logger.debug(f"Building image: {image_name}")
        tl_signer.add_entry({"image_name": image_name})
        docker_service.update_build_status(request.user_id, build_id, "building", step="Building container image")
        build_success = docker_service.build_image(request.dockerfile, build_id, request.user_id, tl_signer)
        
        if not build_success:
            logger.error(f"Docker build failed for build ID: {build_id}")
            docker_service.update_build_status(request.user_id, build_id, "failed", step="Container build failed")
            return

        # Generate keys if not provided
        decryption_key = None
        public_encryption_key = None
        private_encryption_key = None
        logger.debug(f"Checking for provided sign_key and cert for build ID: {build_id}")
        if not request.sign_key or not request.cert:
            docker_service.update_build_status(request.user_id, build_id, "preparing", step="Get signing and encryption keys")
            logger.info(f"Get keys for build ID: {build_id}")
            if ENABLE_TDX:
                # Get key from KBS when TDX mode is enabled.
                logger.info("Starting get key from KBS")
                attestation_result, decryption_key = docker_service.get_pubKey_from_KBS(tl_signer)
                if attestation_result != "trusted":
                    docker_service.update_build_status(
                        request.user_id,
                        build_id,
                        "failed",
                        error_message="Attestation failed: get key failed."
                    )
                    logger.debug("get key failed")
                    return
            else:
                logger.info("ENABLE_TDX=false, skipping KBS attestation key retrieval")
            
            docker_service.update_build_status(request.user_id, build_id, "preparing", step="Generating signing and encryption keys")
            logger.info(f"Generating keys for build ID: {build_id}")
            sign_key, cert, priv_enc_key, pub_enc_key = docker_service.generate_key(build_id, tl_signer)
            
            if not sign_key or not cert or not priv_enc_key or not pub_enc_key:
                logger.error(f"Failed to generate keys for build ID: {build_id}")
                docker_service.update_build_status(
                    request.user_id,
                    build_id, 
                    "failed",
                    step="Key generation failed",
                    error_message="Failed to generate keys"
                )
                return
                
            request.sign_key = sign_key
            request.cert = cert
            private_encryption_key = priv_enc_key
            public_encryption_key = pub_enc_key
            if not decryption_key:
                decryption_key = {"opensslPub": pub_enc_key}
            logger.debug(f"Successfully generated keys for build ID: {build_id}")
            
            docker_service.update_build_status(
                request.user_id,
                build_id,
                "preparing",
                step="Keys generated successfully",
                cert_url=f"/api/artifacts/{build_id}/{os.path.basename(cert)}"
            )

        # Generate SBOM and handle encryption
        try:
            # Generate SBOM
            docker_service.update_build_status(request.user_id, build_id, "generating_sbom", step="Generating SBOM")
            logger.info(f"Generating SBOM for image {image_name}")
            sbom_path = docker_service.generate_sbom(
                image_name,
                build_id,
                tl_signer
            )
            if not sbom_path:
                raise Exception("SBOM generation failed")
            logger.debug(f"Successfully generated SBOM at {sbom_path}")

            # Encrypt image if requested
            if request.encrypt:
                if not decryption_key:
                    logger.error(f"Encryption requested for build {build_id}, but no encryption key available.")
                    raise Exception("Encryption requested, but no encryption key available")

                docker_service.update_build_status(request.user_id, build_id, "encrypting", step="Encrypting container image")
                logger.info(f"Encrypting image {image_name}")
                encrypted_image_name = docker_service.encrypt_image(
                    image_name,
                    build_id,
                    decryption_key['opensslPub'],
                    tl_signer
                )
                if not encrypted_image_name:
                    raise Exception("Image encryption failed")
                logger.debug(f"Successfully encrypted image {image_name}")
                image_name = encrypted_image_name

        except Exception as e:
            logger.error(f"Image encryption or SBOM generation failed for build ID {build_id}: {str(e)}")
            docker_service.update_build_status(
                request.user_id,
                build_id,
                "failed",
                step="SBOM/Encryption failed",
                error_message=f"Image encryption or SBOM generation failed: {str(e)}"
            )
            return

		# Save transparencyLog
        logger.info("Save transparencyLog")
        #docker_service.update_transparencylog_status(request.user_id, 'LogID', "adding", build_id)
        log_proxy_configuration("Build transparency log")

        from sigstore.oidc import Issuer
        issuer = Issuer.production()
        identity_token = issuer.identity_token()

        tl_signer.set_identity_token(identity_token)
        tlog_status, tlog_id = docker_service.save_transparencyLog("build",build_id,tl_signer)
        docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "added", build_id)
        if tlog_status:
            logger.info(f"Save build transparency success.")
        else:
            logger.info(f"Save build transparency failed.")

		# Verify transparencyLog
        logger.info("Verify transparencyLog")
        verify_tlog_status = docker_service.verify_transpaerncyLog("build", identity_token, build_id)

        # Update build status with success
        logger.info(f"Build completed successfully for build ID: {build_id}")
        docker_service.update_build_status(
            request.user_id,
            build_id,
            "success",
            step="Build completed successfully",
            image_id=image_name,
            log_id=tlog_id,
            sbom_url=f"{image_name[4:].replace('test-','')}-sbom.json",
            image_url=f"{image_name[4:]}",
            transparencyLog_verify=verify_tlog_status,
            cert_url=f"/api/artifacts/{build_id}/cosign.crt"
        )
        
    except Exception as e:
        logger.error(f"Build failed for build ID {build_id}: {str(e)}")
        docker_service.update_build_status(
            request.user_id,
            build_id,
            "failed",
            step="Unexpected error",
            log_id=f"{tlog_id}" if tlog_id else f"uuid-{uuid.uuid4()}",
            error_message=str(e)
        )

@app.post("/api/publish-package", response_model=PublishPackageResponse)
async def publish_package(request: PublishPackageRequest):
    """Publish image and SBOM to registry with key management and logging"""
    try:
        image_name = request.image_id.split("/")[-1]
        registry_repo = f"{DOCKER_REPOSITORY}/{image_name}:latest-encrypted"

        tl_signer = ChainedTransparencyLog()

        # 1. Push image and SBOM to registry
        try:
            # Generate build ID
            publish_id = "pub-" + request.build_id.split("-")[-1]
            logger.debug(f"Generated build ID: {publish_id}")
            tl_signer.add_entry({"publishID": publish_id})

            docker_service.update_publish_status(request.user_id, request.build_id, "pushing", publish_id, step="Pushing image to registry")
            logger.info(f"Pushing image {request.image_id} to registry")
            
            source_ref = f"oci:{request.image_id}"
            dest_ref = f"docker://{registry_repo}"

            log_proxy_configuration("Publish image push")

            push_success = docker_service.push_image(source_ref, dest_ref, tl_signer)
            if not push_success:
                raise Exception("Image push failed")
            logger.debug(f"Successfully pushed image to {dest_ref}")
            tl_signer.add_entry({
                "publish_source": source_ref,
                "publish_dest": dest_ref,
                "publishImage_status": push_success
                })
            

        except Exception as e:
            logger.error(f"Image push failed for build ID {request.build_id}: {str(e)}")
            tl_signer.add_entry({"publish_status": "failed",
                                "error": str(e)})
            docker_service.update_build_status(
                request.user_id,
                request.build_id,
                "failed",
                publish_id,
                step="Image push failed",
                error_message=f"Image push failed: {str(e)}"
            )
            return
        
        # Push SBOM
        logger.info(f"Starting get key from KBS")
        attestation_result, decryption_key = docker_service.get_pubKey_from_KBS(tl_signer)
        if decryption_key:
        # if request.sign_key and request.cert:
            try:
                docker_service.update_publish_status(request.user_id, request.build_id, "signing", publish_id, step="Signing image and SBOM")
                # Sign image
                logger.info(f"Signing image {request.image_id}")
                sign_success = docker_service.sign_image(
                    request.image_id,
                    decryption_key['cosignKey'],
                    tl_signer
                )
                if not sign_success:
                    raise Exception("Image signing failed")
                logger.debug(f"Successfully signed image {request.image_id}")
                tl_signer.add_entry({"publish_sbom": sign_success})

                # Create SBOM attestation
                logger.info(f"Creating SBOM attestation for build ID {request.build_id}")
                sbom_attestation_success = docker_service.create_sbom_attestation(
                    request.image_id,
                    request.sbom_url,
                    decryption_key['cosignKey'],
                    tl_signer
                )
                tl_signer.add_entry({"verfiy_sbom_status": sbom_attestation_success})
                if not sbom_attestation_success:
                    tl_signer.add_entry({"verfiy_sbom_status": sbom_attestation_success})
                    raise Exception("SBOM attestation failed")
                logger.debug(f"Successfully created SBOM attestation for build ID {request.build_id}")
                
            except Exception as e:
                logger.error(f"Image signing or SBOM attestation failed for build ID {request.build_id}: {str(e)}")
                tl_signer.add_entry({"error": f"{e}"})
                docker_service.update_publish_status(
                    request.user_id,
                    request.build_id,
                    "failed",
                    publish_id,
                    step="Signing failed",
                    #image_id=request.image_id,
                    #sbom_url=request.sbom_url,
                    #image_url=request.image_url,
                    error_message=f"Image signing or SBOM attestation failed: {str(e)}"
                )
                return

        from sigstore.oidc import Issuer
        issuer = Issuer.production()
        identity_token = issuer.identity_token()
        tl_signer.set_identity_token(identity_token)

		# Sign and submit to transparency log
        tlog_status, tlog_id = docker_service.save_transparencyLog("publish", request.build_id, tl_signer)
        docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "added", request.build_id)
        if tlog_status:
            logger.info(f"Save publish transparency success.")
        else:
            logger.info(f"Save publish transparency failed.")

		# Verify transparencyLog
        logger.info("Verify transparencyLog")
        verify_tlog_status = docker_service.verify_transpaerncyLog("publish", identity_token, request.build_id)

        docker_service.update_publish_status(request.user_id, request.build_id, "success", publish_id,
                                             step="complete publish verify",
                                             transparencyLog_verify=verify_tlog_status,
                                             log_id=tlog_id,
                                             image_id=request.image_id.split('/')[-1],
                                             sbom_url=request.sbom_url,
                                             image_url=f"docker.io/{registry_repo}"
                                             )
        return PublishPackageResponse(
            build_id=request.build_id,
            publish_id=publish_id,
            status="success",
		    image_id=request.image_id.split('/')[-1],
            sbom_url=request.sbom_url,
		    image_url=f"docker.io/{registry_repo}",
		    user_id=request.user_id,
		    transparencyLog_verify=verify_tlog_status,
		    log_id=f"{tlog_id}" if tlog_id else f"uuid-{uuid.uuid4()}",
		    published_at=datetime.now()
		)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to publish package: {str(e)}"
        )


@app.get("/api/publish-result/{build_id}", response_model=PublishResult)
async def get_publish_result(build_id: str):
    """Get publish result by publish ID"""
    try:
        publish_result = docker_service.get_publish_status(build_id)
        
        if not publish_result:
            raise HTTPException(status_code=404, detail="Publish not found")
        
        return publish_result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get publish result: {str(e)}")

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

@app.get("/api/transparency-log/{log_id}", response_model=TransparencyResult)
async def get_transparencyLog(log_id: str):
    """Get transparency log result by build ID"""
    try:
        tlog_result = docker_service.get_transparencyLog_status(log_id)

        if not tlog_result:
            raise HTTPException(status_code=404, detail="Transparency log not found")

        return tlog_result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get transparency log result: {str(e)}")


@app.post("/api/deploy-launch", response_model=LaunchResponse)
async def deploy_launch(request: LaunchRequest, background_tasks: BackgroundTasks):
    """Deploy and launch container on worker nodes"""
    try:
        tl_signer = ChainedTransparencyLog()

        # Generate launch ID
        launch_id = docker_service.generate_uuid(prefix="launch")
        logger.info(f"CHECK launchID: {launch_id}")
        tl_signer.add_entry({"launch_id": launch_id})

        # Create launch directory
        launch_path = os.path.join(BUILD_DIR, launch_id)
        tl_signer.add_entry({"launch_path": launch_path})
        os.makedirs(launch_path, exist_ok=True)

        # Save launch configuration
        config_path = os.path.join(launch_path, "launch_config.json")
        with open(config_path, "w") as f:
            json.dump(request.model_dump(), f, indent=2)
        
        # Initialize launch status
        docker_service.update_launch_status(
            user_id=request.user_id,
            launch_id=launch_id,
            status="initiated",
            created_at=datetime.now()
        )
        
        # Start background launch process
        background_tasks.add_task(
            launch_container_async,
            request,
            launch_id,
            launch_path,
            tl_signer
        )
        
        return LaunchResponse(
            launch_id=launch_id,
            status="initiated",
            user_id=request.user_id
        )
        
    except Exception as e:
        # Clean up launch directory if creation failed
        if 'launch_path' in locals():
            shutil.rmtree(launch_path, ignore_errors=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to initiate launch: {str(e)}"
        )

async def launch_container_async(request: LaunchRequest, launch_id: str, launch_path: str, tl_signer: ChainedTransparencyLog):
    """Async function to launch container in background"""
    try:
        docker_service.update_launch_status(request.user_id, launch_id, "launching")
        
        # Create log file
        log_file = os.path.join(launch_path, "launch.log")
        with open(log_file, "w") as f:
            f.write(f"Launch started at {datetime.now().isoformat()}\n")
        tl_signer.add_entry({"launch-log":log_file})

        # 3. Perform attestation and handle decryption
        attestation_result = "trusted"
        decryption_key = None
        if request.attestation_required:
            if ENABLE_TDX:
                # Verify attestation and get decryption key in TDX mode.
                logger.info("Attestation Verity and get keys")
                attestation_result, decryption_key = await docker_service.verify_attestation(
                    request.image_id,
                    request.user_id,
                    tl_signer
                )
                tl_signer.add_entry({"verify_image":attestation_result})
                tl_signer.add_entry({"verify_keys":decryption_key})

                if attestation_result != "trusted":
                    docker_service.update_launch_status(
                        request.user_id,
                        launch_id,
                        "failed",
                        error_message=f"Attestation failed: {attestation_result}"
                    )
                    logger.debug("Attestation Verity and get keys failed")
                    tl_signer.add_entry({"verify_image":attestation_result})
                    return
            else:
                logger.info("ENABLE_TDX=false, skipping attestation flow")

        log_proxy_configuration("Launch image pull")

        # 1. Pull and verify image
        logger.info("Get encrypted iamge and decrypt")
        pull_success = docker_service.pull_image(
            tl_signer,
            image_url=request.image_url,
            target_dir=launch_path,
            openssl_key=decryption_key['opensslKey'] if decryption_key else None
        )
        if not pull_success:
            docker_service.update_launch_status(
                request.user_id,
                launch_id, 
                "failed",
                error_message="Image pull failed"
            )
            logger.debug("Get encrypted iamge and decrypt failed")
            return
            
        # 2. Verify SBOM if provided
        logger.info("Verify SBOM")
        if request.sbom_url:
            sbom_valid = docker_service.verify_sbom(
                request.image_url,
                request.sbom_url,
                tl_signer,
                decryption_key['cosignPub']
            )
            tl_signer.add_entry({"sbom_verify": sbom_valid})
            if not sbom_valid:
                docker_service.update_launch_status(
                    request.user_id,
                    launch_id,
                    "failed",
                    error_message="SBOM verification failed"
                )
                logger.debug("Verify SBOM failed")
                tl_signer.add_entry({"sbom_verify": sbom_valid})
                return
        
        # 4. Launch containers on worker nodes
        logger.info("Launch container")
        instance_ids = await docker_service.launch_containers(
            tl_signer,
            image_url=request.image_url,
            image_id=request.image_id,
            launch_pth=launch_path
        )
        tl_signer.add_entry({"launch_instance_ids": instance_ids})
        if not instance_ids:
            docker_service.update_launch_status(
                request.user_id,
                launch_id,
                "failed",
                error_message="Container launch failed"
            )
            logger.debug("Launch container failed")
            tl_signer.add_entry({"launch_result": "failed"})
            return
            
        # 5. Create launch evidence
        evidences = {
            "launch_id": launch_id,
            "image_id": request.image_id,
            "user_id": request.user_id,
            "timestamp": datetime.now().isoformat(),
            "attestation_result": attestation_result,
            "instance_ids": instance_ids
        }

        from sigstore.oidc import Issuer
        issuer = Issuer.production()
        identity_token = issuer.identity_token()

        tl_signer.set_identity_token(identity_token)
        tlog_status, log_id = docker_service.save_transparencyLog("launch",launch_id,tl_signer)
        docker_service.update_transparencylog_status(request.user_id, str(log_id), "added", launch_id)
        if tlog_status:
            logger.info(f"Save build transparency success.")
        else:
            logger.info(f"Save build transparency failed.")

        # Verify transparencyLog
        logger.info("Verify transparencyLog")
        verify_tlog_status = docker_service.verify_transpaerncyLog("launch", identity_token, launch_id)

        # Update launch status to success
        docker_service.update_launch_status(
            request.user_id,
            launch_id=launch_id,
            status="success",
            validation="passed",
            attestation=attestation_result,
            evidence=evidences,
            transparencyLog_verify=verify_tlog_status,
            log_id=f"{log_id}" if log_id else f"uuid-{uuid.uuid4()}",
            instance_ids=instance_ids
        )
        
    except Exception as e:
        docker_service.update_launch_status(
            request.user_id,
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

@app.post("/api/get-summaryTransparencylog", response_model=SummaryTransparencyRespone)
async def get_summary_transparencylog(request: GetTransparencyRequest):
    """Get launch result by launch ID"""
    try:
        res = await docker_service.get_summaryTransparencylog(request.build_id, request.launch_id)

        if not res:
            raise HTTPException(
                status_code=404,
                detail="Launch not found"
            )

        return res

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get launch result: {str(e)}"
        )


@app.post("/api/verify-tlog", response_model=VerificationSummaryResponse)
async def verify_tlog(request: VerifyTlogRequest):
    """Verify transparency log"""
    log_proxy_configuration("Verify tlog")
    try:
        verify_result = await docker_service.verify_tlog(
            request.raw_file,
            request.bundle_file,
            request.chain_file,
            request.email_addr,
            request.identity_token
        )

        return verify_result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to verify transparency log: {str(e)}"
        )

@app.post("/api/create_lunks", response_model=CreateLunksRespone)
async def create_lunks(request: CreateLunksRequest):
    """create lunks"""
    try:
        tl_signer = ChainedTransparencyLog()

        logger.info(f"Create Lunks block file for user: {request.user_id}")

        # create encrypted vfs
        tl_signer.add_entry({"lunks": "Start creating lunks blocks"})
        mapdir,loopdevice = docker_service.create_lunks_block(request.user_id, tl_signer,request.passwd, request.vfs_size, request.vfs_path)
        # Save transparencyLog
        logger.info("Save transparencyLog")
        os.environ['http_proxy'] = "http://child-prc.intel.com:913"
        os.environ['https_proxy'] = "http://child-prc.intel.com:913"

        if "http_proxy" in os.environ:
            print("Proxy is setted.")
        else:
            print("Proxy is unsetted.")

        from sigstore.oidc import Issuer
        issuer = Issuer.production()
        identity_token = issuer.identity_token()

        tl_signer.set_identity_token(identity_token)
        tlog_status, tlog_id = docker_service.save_transparencyLog("create_lunks",'',tl_signer)
        docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "creating lunks block", '')
        if tlog_status:
            logger.info(f"Save create_lunks transparency success.")
        else:
            logger.info(f"Save create_lunks transparency failed.")

        # Verify transparencyLog
        logger.info("Verify transparencyLog")
        verify_tlog_status = docker_service.verify_transpaerncyLog("create_lunks", identity_token, '')

        del os.environ['http_proxy']
        del os.environ['https_proxy']

        docker_service.update_lunks_status(
            request.user_id,
            "create success",
            step="create_lunks completed successfully",
            log_id=tlog_id,
            transparencyLog_verify=verify_tlog_status
        )


        return CreateLunksRespone(
            user_id=request.user_id,
            passwd=request.passwd,
            mapper_dir=mapdir,
            vfs_path=request.vfs_path,
            loop_device=loopdevice,
            vfs_size=request.vfs_size
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create lunks: {str(e)}"
        )

@app.post("/api/mount_lunks", response_model=MountLunksRespone)
async def create_lunks(request: MountLunksRequest):
    """mount lunks"""
    try:
        logger.info(f"Mount Lunks block file for user: {request.user_id}")
        tl_signer = ChainedTransparencyLog()
        status = 'failed'
        # mount encrypted vfs
        mountPath = docker_service.mount_lunks_block(request.user_id, tl_signer, request.mapper_dir, request.passwd, request.mount_path,request.vfs_path,request.loop_device)

        # Save transparencyLog
        logger.info("Save transparencyLog")
        os.environ['http_proxy'] = "http://child-prc.intel.com:913"
        os.environ['https_proxy'] = "http://child-prc.intel.com:913"

        if "http_proxy" in os.environ:
            print("Proxy is setted.")
        else:
            print("Proxy is unsetted.")

        from sigstore.oidc import Issuer
        issuer = Issuer.production()
        identity_token = issuer.identity_token()

        tl_signer.set_identity_token(identity_token)
        tlog_status, tlog_id = docker_service.save_transparencyLog("mount_lunks",'',tl_signer)
        docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "mount_lunks block", '')
        if tlog_status:
            logger.info(f"Save build transparency success.")
        else:
            logger.info(f"Save build transparency failed.")

        # Verify transparencyLog
        logger.info("Verify transparencyLog")
        verify_tlog_status = docker_service.verify_transpaerncyLog("mount_lunks", identity_token, '')

        del os.environ['http_proxy']
        del os.environ['https_proxy']

        if  verify_tlog_status == "success":
            status = "mount_lunks success"

        docker_service.update_lunks_status(
            request.user_id,
            status,
            step="mount_lunks completed successfully",
            log_id=tlog_id,
            transparencyLog_verify=verify_tlog_status
        )

        return MountLunksRespone(
            user_id=request.user_id,
            passwd=request.passwd,
            mapper_dir=request.mapper_dir,
            vfs_path=request.vfs_path,
            loop_device=request.loop_device,
            mount_path=request.mount_path
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to mount lunks: {str(e)}"
        )

@app.post("/api/unmount_lunks", response_model=UnmountLunksRespone)
async def create_lunks(request: UnmountLunksRequest):
    """umount lunks"""
    try:
        logger.info(f"Umount Lunks block file for user: {request.user_id}")
        tl_signer = ChainedTransparencyLog()
        status = 'failed'
        # unmount encrypted vfs
        docker_service.unmount_lunks_block(request.user_id, tl_signer, request.mapper_dir, request.mount_path, request.loop_device)

        # Save transparencyLog
        logger.info("Save transparencyLog")
        #docker_service.update_transparencylog_status(request.user_id, 'LogID', "adding", build_id)
        os.environ['http_proxy'] = "http://child-prc.intel.com:913"
        os.environ['https_proxy'] = "http://child-prc.intel.com:913"

        if "http_proxy" in os.environ:
            print("Proxy is setted.")
        else:
            print("Proxy is unsetted.")

        from sigstore.oidc import Issuer
        issuer = Issuer.production()
        identity_token = issuer.identity_token()

        tl_signer.set_identity_token(identity_token)
        tlog_status, tlog_id = docker_service.save_transparencyLog("unmount_lunks",'',tl_signer)
        docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "unmount_lunks block", '')
        if tlog_status:
            logger.info(f"Save build transparency success.")
        else:
            logger.info(f"Save build transparency failed.")

        # Verify transparencyLog
        logger.info("Verify transparencyLog")
        verify_tlog_status = docker_service.verify_transpaerncyLog("unmount_lunks", identity_token, '')

        del os.environ['http_proxy']
        del os.environ['https_proxy']
        if  verify_tlog_status == "success":
            status = "unmount_lunks success"
        docker_service.update_lunks_status(
            request.user_id,
            status,
            step="unmount_lunks completed successfully",
            log_id=tlog_id,
            transparencyLog_verify=verify_tlog_status
        )

        return UnmountLunksRespone(
            user_id=request.user_id,
            mapper_dir=request.mapper_dir,
            loop_device=request.loop_device,
            mount_path=request.mount_path
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to unmount lunks: {str(e)}"
        )

@app.get("/api/lunks-result/{user_id}", response_model=LunksResult)
async def get_lunks_result(user_id: str):
    """Get lunks result by user ID"""
    try:
        lunks = docker_service.get_lunks_status(user_id)

        if not lunks:
            raise HTTPException(status_code=404, detail="User not found")

        return lunks

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get lunks result: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, log_level="debug")
