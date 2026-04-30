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
from .tlog_client import TrustedLogAPI
from .tlog.types import Entry
from .models import *
from .services import DockerService
from .kbs_service import KBSService
from .sigstore_identity import resolve_sigstore_identity_token
from .config import (
    HOST, PORT, DEBUG, UPLOAD_DIR, BUILD_DIR, LOGS_DIR,
    DOCKER_REGISTRY, DOCKER_REPOSITORY, ENABLE_TDX, TRUCON_URL,
    INIT_DEFAULT_CHAIN_ON_STARTUP,
    TRANSPARENCY_SERVICE_CHAIN_ID,
    TRANSPARENCY_WORKLOAD_CHAIN_PREFIX,
)

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def workload_transparency_chain_id(workload_id: str) -> str:
    return f"{TRANSPARENCY_WORKLOAD_CHAIN_PREFIX}{workload_id}"


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
    from .tlog_client import TrustedLogAPI
    from .trucon.adapters.sigstore import SigstoreLogAdapter
    
    # tc_api is stateless for the commit path — RTMR extend is TruCon's job.
    # local_mr is no longer used here.
    app.state.trusted_log = TrustedLogAPI(
        local_mr=None,
        immutable_log=SigstoreLogAdapter(),
        trucon_url=TRUCON_URL,
    )

    # Optionally initialize the default chain (Event Log 0 baseline).
    if INIT_DEFAULT_CHAIN_ON_STARTUP:
        try:
            app.state.trusted_log.init_chain("default")
        except Exception as e:
            logger.warning("init-chain for 'default' failed (non-fatal): %s", e)
    else:
        logger.info("Skipping default chain initialization during startup")
    
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
        
        tlog = app.state.trusted_log
        ctx = tlog.init_record(context={"chain_ref": TRANSPARENCY_SERVICE_CHAIN_ID})
        record_id = ctx.record_id
        tlog.add_entry(record_id, Entry(key="build_id", value=build_id))

        # Create build directory
        build_path = os.path.join(BUILD_DIR, build_id)
        os.makedirs(build_path, exist_ok=True)
        logger.debug(f"Created build directory: {build_path}")

        tlog.add_entry(record_id, Entry(key="build_path", value=build_path))

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
        tlog.add_entry(record_id, Entry(key="app_binary", value={"app_binary_path": binary_path, "app_binary_hash": binary_hash}))
        
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
            tlog.add_entry(record_id, Entry(key="config", value={"config_dir": config_dir,
                                 "config_count": len(request.configs),
                                 "config_hashes": config_hashes}))

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
            tlog.add_entry(record_id, Entry(key="data", value={"data_dir": data_dir,
                                 "data_count": len(request.data),
                                 "data_hashes": data_hashes}))
        
        # Initialize build status
        docker_service.update_build_status(request.user_id, build_id, "submitted")
        logger.info(f"Build {build_id} status updated to: submitted")
        # Start background build process
        background_tasks.add_task(
            build_container_async, 
            request, 
            build_id,
            tlog,
            record_id
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

def build_container_async(request: BuildPackageRequest, build_id: str, tlog: TrustedLogAPI, record_id: str):
    """Function to build container in background with detailed status tracking"""
    tlog_id = None
    try:
        # Start with preparing status
        docker_service.update_build_status(request.user_id, build_id, "preparing", step="Initializing build process")
        logger.info(f"Starting build process for build ID: {build_id}")
        
        # Build the image
        image_name = f"{request.user_id}-{build_id}:latest"
        logger.debug(f"Building image: {image_name}")
        tlog.add_entry(record_id, Entry(key="image_name", value=image_name))
        docker_service.update_build_status(request.user_id, build_id, "building", step="Building container image")
        build_success = docker_service.build_image(request.dockerfile, build_id, request.user_id, tlog, record_id)
        
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
                attestation_result, decryption_key = docker_service.get_pubKey_from_KBS(tlog, record_id)
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
            sign_key, cert, priv_enc_key, pub_enc_key = docker_service.generate_key(build_id, tlog, record_id)
            
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
                tlog,
                record_id
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
                    tlog,
                    record_id
                )
                if not encrypted_image_name:
                    raise Exception("Image encryption failed")
                logger.debug(f"Successfully encrypted image {image_name}")
                image_name = encrypted_image_name
            else:
                logger.info(f"Exporting non-encrypted image {image_name} to OCI layout")
                exported_image_name = docker_service.export_image_to_oci(
                    image_name,
                    build_id,
                    tlog,
                    record_id,
                )
                if not exported_image_name:
                    raise Exception("Image export failed")
                logger.debug(f"Successfully exported image {image_name}")
                image_name = exported_image_name

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

        # Commit to TruCon and save receipt
        logger.info("Committing build transparency log")
        log_proxy_configuration("Build transparency log")

        identity_token = request.identity_token or resolve_sigstore_identity_token(
            "build", logger=logger, min_ttl_seconds=0
        )
        tlog_id = None
        if identity_token:
            tlog_status, tlog_id = docker_service.commit_and_save_receipt("build", build_id, tlog, record_id, identity_token)
            docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "added", build_id)
            if tlog_status:
                logger.info("Save build transparency success.")
            else:
                logger.info("Save build transparency failed.")

            # Verify chain state via TruCon
            logger.info("Verify chain state")
            verify_tlog_status = docker_service.verify_chain_state("build", tlog, chain_id=TRANSPARENCY_SERVICE_CHAIN_ID)
        else:
            verify_tlog_status = "skipped"

        if image_name.startswith("oci:"):
            published_image_id = image_name
            published_image_url = image_name[4:]
            published_sbom_url = sbom_path
        else:
            published_image_id = image_name
            published_image_url = image_name
            published_sbom_url = sbom_path

        # Update build status with success
        logger.info(f"Build completed successfully for build ID: {build_id}")
        docker_service.update_build_status(
            request.user_id,
            build_id,
            "success",
            step="Build completed successfully",
            image_id=published_image_id,
            log_id=tlog_id,
            sbom_url=published_sbom_url,
            image_url=published_image_url,
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
        image_name = request.image_id.split("/")[-1].split(":")[0]
        registry_repo = f"{DOCKER_REPOSITORY}/{image_name}:latest-encrypted"

        tlog = app.state.trusted_log
        ctx = tlog.init_record(context={"chain_ref": TRANSPARENCY_SERVICE_CHAIN_ID})
        record_id = ctx.record_id

        # 1. Push image and SBOM to registry
        try:
            # Generate build ID
            publish_id = "pub-" + request.build_id.split("-")[-1]
            logger.debug(f"Generated build ID: {publish_id}")
            tlog.add_entry(record_id, Entry(key="publishID", value={"publishID": publish_id}))

            docker_service.update_publish_status(request.user_id, request.build_id, "pushing", publish_id, step="Pushing image to registry")
            logger.info(f"Pushing image {request.image_id} to registry")
            
            if request.image_id.startswith("oci:"):
                source_ref = request.image_id
            else:
                source_ref = f"docker-daemon:{request.image_id}"
            dest_ref = f"docker://{registry_repo}"

            log_proxy_configuration("Publish image push")

            push_success = docker_service.push_image(source_ref, dest_ref, tlog, record_id)
            if not push_success:
                raise Exception("Image push failed")
            logger.debug(f"Successfully pushed image to {dest_ref}")
            tlog.add_entry(record_id, Entry(key="log", value={
                "publish_source": source_ref,
                "publish_dest": dest_ref,
                "publishImage_status": push_success
                }))
            

        except Exception as e:
            logger.error(f"Image push failed for build ID {request.build_id}: {str(e)}")
            tlog.add_entry(record_id, Entry(key="publish_status", value={"publish_status": "failed",
                                "error": str(e)}))
            docker_service.update_publish_status(
                request.user_id,
                request.build_id,
                "failed",
                publish_id,
                step="Image push failed",
                error_message=f"Image push failed: {str(e)}"
            )
            raise HTTPException(status_code=400, detail=f"Image push failed: {str(e)}")
        
        # Push SBOM
        logger.info(f"Starting get key from KBS")
        attestation_result, decryption_key = docker_service.get_pubKey_from_KBS(tlog, record_id)
        if decryption_key:
        # if request.sign_key and request.cert:
            try:
                docker_service.update_publish_status(request.user_id, request.build_id, "signing", publish_id, step="Signing image and SBOM")
                # Sign image
                logger.info(f"Signing image {request.image_id}")
                sign_success = docker_service.sign_image(
                    request.image_id,
                    decryption_key['cosignKey'],
                    tlog,
            record_id
                )
                if not sign_success:
                    raise Exception("Image signing failed")
                logger.debug(f"Successfully signed image {request.image_id}")
                tlog.add_entry(record_id, Entry(key="publish_sbom", value={"publish_sbom": sign_success}))

                # Create SBOM attestation
                logger.info(f"Creating SBOM attestation for build ID {request.build_id}")
                sbom_attestation_success = docker_service.create_sbom_attestation(
                    request.image_id,
                    request.sbom_url,
                    decryption_key['cosignKey'],
                    tlog,
            record_id
                )
                tlog.add_entry(record_id, Entry(key="verify_sbom_status", value={"verify_sbom_status": sbom_attestation_success}))
                if not sbom_attestation_success:
                    tlog.add_entry(record_id, Entry(key="verify_sbom_status", value={"verify_sbom_status": sbom_attestation_success}))
                    raise Exception("SBOM attestation failed")
                logger.debug(f"Successfully created SBOM attestation for build ID {request.build_id}")
                
            except Exception as e:
                logger.error(f"Image signing or SBOM attestation failed for build ID {request.build_id}: {str(e)}")
                tlog.add_entry({"error": f"{e}"})
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
                raise HTTPException(status_code=500, detail=f"Image signing or SBOM attestation failed: {str(e)}")

        identity_token = request.identity_token or resolve_sigstore_identity_token(
            "publish", logger=logger, min_ttl_seconds=0
        )
        tlog_id = None
        if identity_token:
		# Sign and submit to transparency log
            tlog_status, tlog_id = docker_service.commit_and_save_receipt("publish", request.build_id, tlog, record_id, identity_token)
            docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "added", request.build_id)
            if tlog_status:
                logger.info(f"Save publish transparency success.")
            else:
                logger.info(f"Save publish transparency failed.")

		# Verify transparencyLog
            logger.info("Verify transparencyLog")
            verify_tlog_status = docker_service.verify_chain_state("publish", tlog, chain_id=TRANSPARENCY_SERVICE_CHAIN_ID)
        else:
            verify_tlog_status = "skipped"

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
        tlog = app.state.trusted_log
        workload_id = docker_service.normalize_workload_id(request.user_id, request.image_id, request.metadata)
        transparency_chain_id = workload_transparency_chain_id(workload_id)
        ctx = tlog.init_record(context={"chain_ref": transparency_chain_id})
        record_id = ctx.record_id

        # Generate launch ID
        launch_id = docker_service.generate_uuid(prefix="launch")
        logger.info(f"CHECK launchID: {launch_id}")
        tlog.add_entry(record_id, Entry(key="launch_id", value={"launch_id": launch_id}))
        tlog.add_entry(record_id, Entry(key="workload_id", value=workload_id))

        # Create launch directory
        launch_path = os.path.join(BUILD_DIR, launch_id)
        tlog.add_entry(record_id, Entry(key="launch_path", value={"launch_path": launch_path}))
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
            workload_id,
            transparency_chain_id,
            launch_path,
            tlog,
            record_id
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

async def launch_container_async(request: LaunchRequest, launch_id: str, workload_id: str, transparency_chain_id: str, launch_path: str, tlog: TrustedLogAPI, record_id: str):
    """Async function to launch container in background"""
    try:
        docker_service.update_launch_status(request.user_id, launch_id, "launching")
        
        # Create log file
        log_file = os.path.join(launch_path, "launch.log")
        with open(log_file, "w") as f:
            f.write(f"Launch started at {datetime.now().isoformat()}\n")
        tlog.add_entry(record_id, Entry(key="launch-log", value={"launch-log":log_file}))
        tlog.add_entry(record_id, Entry(key="workload_id", value=workload_id))
        image_digest = docker_service._resolve_image_digest(request.image_url or request.image_id)
        security_projection = docker_service._build_launch_security_projection(launch_id, workload_id)
        launch_config_digest = docker_service._json_sha384_digest({
            "request": request.model_dump(),
            "security_projection": security_projection,
        })
        tlog.add_entry(record_id, Entry(key="image_digest", value=image_digest))
        tlog.add_entry(record_id, Entry(key="launch_config_digest", value=launch_config_digest))
        tlog.add_entry(record_id, Entry(key="privileged", value=security_projection["privileged"]))
        tlog.add_entry(record_id, Entry(key="network_mode", value=security_projection["network_mode"]))
        tlog.add_entry(record_id, Entry(key="mounts", value=security_projection["mounts"]))
        tlog.add_entry(record_id, Entry(key="devices", value=security_projection["devices"]))
        tlog.add_entry(record_id, Entry(key="capabilities", value=security_projection["capabilities"]))
        tlog.add_entry(record_id, Entry(key="launch_env_keys", value=security_projection["launch_env_keys"]))
        tlog.add_entry(record_id, Entry(key="launch_env_digest", value=security_projection["launch_env_digest"]))

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
                    tlog,
            record_id
                )
                tlog.add_entry(record_id, Entry(key="verify_image", value={"verify_image":attestation_result}))
                tlog.add_entry(record_id, Entry(key="verify_keys", value={"verify_keys":decryption_key}))

                if attestation_result != "trusted":
                    docker_service.update_launch_status(
                        request.user_id,
                        launch_id,
                        "failed",
                        error_message=f"Attestation failed: {attestation_result}"
                    )
                    logger.debug("Attestation Verity and get keys failed")
                    tlog.add_entry(record_id, Entry(key="verify_image", value={"verify_image":attestation_result}))
                    return
            else:
                logger.info("ENABLE_TDX=false, skipping attestation flow")

        log_proxy_configuration("Launch image pull")

        # 1. Pull and verify image
        logger.info("Get encrypted iamge and decrypt")
        pull_success = docker_service.pull_image(
            tlog, record_id,
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
            tlog.add_entry(record_id, Entry(key="launch_result", value="failed"))
            return
            
        # 2. Verify SBOM if provided
        logger.info("Verify SBOM")
        if request.sbom_url:
            cosign_pubkey = None
            if decryption_key and isinstance(decryption_key, dict):
                cosign_pubkey = decryption_key.get("cosignPub")

            if cosign_pubkey:
                sbom_valid = docker_service.verify_sbom(
                    request.image_url,
                    request.sbom_url,
                    tlog, record_id,
                    cosign_pubkey,
                )
            else:
                logger.info("Skipping SBOM verification because no cosign public key is available for launch")
                sbom_valid = True
            tlog.add_entry(record_id, Entry(key="sbom_verify", value={"sbom_verify": sbom_valid}))
            if not sbom_valid:
                docker_service.update_launch_status(
                    request.user_id,
                    launch_id,
                    "failed",
                    error_message="SBOM verification failed"
                )
                logger.debug("Verify SBOM failed")
                tlog.add_entry(record_id, Entry(key="sbom_verify", value={"sbom_verify": sbom_valid}))
                tlog.add_entry(record_id, Entry(key="launch_result", value="failed"))
                return
        
        # 4. Launch containers on worker nodes
        logger.info("Launch container")
        instance_ids = await docker_service.launch_containers(
            tlog, record_id,
            image_url=request.image_url,
            image_id=request.image_id,
            launch_pth=launch_path,
            workload_id=workload_id,
            launch_id=launch_id,
        )
        tlog.add_entry(record_id, Entry(key="launch_instance_ids", value={"launch_instance_ids": instance_ids}))
        if not instance_ids:
            docker_service.update_launch_status(
                request.user_id,
                launch_id,
                "failed",
                error_message="Container launch failed"
            )
            logger.debug("Launch container failed")
            tlog.add_entry(record_id, Entry(key="launch_result", value={"launch_result": "failed"}))
            return
            
        # 5. Create launch evidence
        evidences = {
            "launch_id": launch_id,
            "workload_id": workload_id,
            "image_id": request.image_id,
            "image_digest": image_digest,
            "launch_config_digest": launch_config_digest,
            "user_id": request.user_id,
            "timestamp": datetime.now().isoformat(),
            "attestation_result": attestation_result,
            "instance_ids": instance_ids
        }

        identity_token = request.identity_token or resolve_sigstore_identity_token(
            "launch", logger=logger, min_ttl_seconds=0
        )
        log_id = None
        if identity_token:
            tlog_status, log_id = docker_service.commit_and_save_receipt("launch", launch_id, tlog, record_id, identity_token)
            docker_service.update_transparencylog_status(request.user_id, str(log_id), "added", launch_id)
            if tlog_status:
                logger.info(f"Save build transparency success.")
            else:
                logger.info(f"Save build transparency failed.")

            # Verify transparencyLog
            logger.info("Verify transparencyLog")
            verify_tlog_status = docker_service.verify_chain_state("launch", tlog, chain_id=transparency_chain_id)
        else:
            verify_tlog_status = "skipped"

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


@app.post("/api/create_lunks", response_model=CreateLunksRespone)
async def create_lunks(request: CreateLunksRequest):
    """create lunks"""
    try:
        tlog = app.state.trusted_log
        ctx = tlog.init_record()
        record_id = ctx.record_id

        logger.info(f"Create Lunks block file for user: {request.user_id}")

        # create encrypted vfs
        tlog.add_entry(record_id, Entry(key="lunks", value={"lunks": "Start creating lunks blocks"}))
        mapdir,loopdevice = docker_service.create_lunks_block(request.user_id, tlog,request.passwd, request.vfs_size, request.vfs_path)
        # Save transparencyLog
        logger.info("Save transparencyLog")
        os.environ['http_proxy'] = "http://child-prc.intel.com:913"
        os.environ['https_proxy'] = "http://child-prc.intel.com:913"

        if "http_proxy" in os.environ:
            print("Proxy is setted.")
        else:
            print("Proxy is unsetted.")

        identity_token = resolve_sigstore_identity_token("create_lunks", logger=logger, allow_interactive=True)
        tlog_id = None
        if identity_token:
            tlog_status, tlog_id = docker_service.commit_and_save_receipt("create_lunks", '', tlog, record_id, identity_token)
            docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "creating lunks block", '')
            if tlog_status:
                logger.info(f"Save create_lunks transparency success.")
            else:
                logger.info(f"Save create_lunks transparency failed.")

            # Verify transparencyLog
            logger.info("Verify transparencyLog")
            verify_tlog_status = docker_service.verify_chain_state("create_lunks", tlog)
        else:
            verify_tlog_status = "skipped"

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
        tlog = app.state.trusted_log
        ctx = tlog.init_record()
        record_id = ctx.record_id
        status = 'failed'
        # mount encrypted vfs
        mountPath = docker_service.mount_lunks_block(request.user_id, tlog, request.mapper_dir, request.passwd, request.mount_path,request.vfs_path,request.loop_device)

        # Save transparencyLog
        logger.info("Save transparencyLog")
        os.environ['http_proxy'] = "http://child-prc.intel.com:913"
        os.environ['https_proxy'] = "http://child-prc.intel.com:913"

        if "http_proxy" in os.environ:
            print("Proxy is setted.")
        else:
            print("Proxy is unsetted.")

        identity_token = resolve_sigstore_identity_token("mount_lunks", logger=logger, allow_interactive=True)
        tlog_id = None
        if identity_token:
            tlog_status, tlog_id = docker_service.commit_and_save_receipt("mount_lunks", '', tlog, record_id, identity_token)
            docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "mount_lunks block", '')
            if tlog_status:
                logger.info(f"Save build transparency success.")
            else:
                logger.info(f"Save build transparency failed.")

            # Verify transparencyLog
            logger.info("Verify transparencyLog")
            verify_tlog_status = docker_service.verify_chain_state("mount_lunks", tlog)
        else:
            verify_tlog_status = "skipped"

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
        tlog = app.state.trusted_log
        ctx = tlog.init_record()
        record_id = ctx.record_id
        status = 'failed'
        # unmount encrypted vfs
        docker_service.unmount_lunks_block(request.user_id, tlog, request.mapper_dir, request.mount_path, request.loop_device)

        # Save transparencyLog
        logger.info("Save transparencyLog")
        #docker_service.update_transparencylog_status(request.user_id, 'LogID', "adding", build_id)
        os.environ['http_proxy'] = "http://child-prc.intel.com:913"
        os.environ['https_proxy'] = "http://child-prc.intel.com:913"

        if "http_proxy" in os.environ:
            print("Proxy is setted.")
        else:
            print("Proxy is unsetted.")

        identity_token = resolve_sigstore_identity_token("unmount_lunks", logger=logger, allow_interactive=True)
        tlog_id = None
        if identity_token:
            tlog_status, tlog_id = docker_service.commit_and_save_receipt("unmount_lunks", '', tlog, record_id, identity_token)
            docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "unmount_lunks block", '')
            if tlog_status:
                logger.info(f"Save build transparency success.")
            else:
                logger.info(f"Save build transparency failed.")

            # Verify transparencyLog
            logger.info("Verify transparencyLog")
            verify_tlog_status = docker_service.verify_chain_state("unmount_lunks", tlog)
        else:
            verify_tlog_status = "skipped"

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

def main() -> None:
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, log_level="debug")


if __name__ == "__main__":
    main()
