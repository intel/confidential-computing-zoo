import base64
import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, HTTPException, Request

from tlog.types import Entry

from ..identity.sigstore_identity import resolve_sigstore_identity_token
from ..models import (
    BuildPackageRequest,
    BuildPackageResponse,
    BuildResult,
    LaunchRequest,
    LaunchResponse,
    LaunchResult,
    PublishPackageRequest,
    PublishPackageResponse,
    PublishResult,
    _validate_runtime_id,
)
from ..transparency.commit_client import TrustedLogAPI
from ..transparency.events import EventEntryKey, launch_security_entries
from .request_auth import add_authenticated_identity_entries, get_authenticated_caller, require_authenticated_owner
from . import runtime


docker_service = runtime.docker_service
logger = runtime.logger

BUILD_DIR = runtime.BUILD_DIR
DOCKER_REPOSITORY = runtime.DOCKER_REPOSITORY
TRANSPARENCY_SERVICE_CHAIN_ID = runtime.TRANSPARENCY_SERVICE_CHAIN_ID


def workload_transparency_chain_id(workload_id: str) -> str:
    return runtime.workload_transparency_chain_id(workload_id)


def _normalize_local_oci_reference(image_ref: Optional[str]) -> Optional[str]:
    if not image_ref:
        return image_ref
    if image_ref.startswith("oci:"):
        return image_ref
    if ":" not in image_ref and os.path.isdir(image_ref):
        return f"oci:{image_ref}"
    return image_ref


def log_proxy_configuration(operation: str) -> None:
    runtime.log_proxy_configuration(operation)


async def build_package(
    http_request: Request,
    request: BuildPackageRequest,
    background_tasks: BackgroundTasks,
):
    """Build and package a container image."""
    try:
        caller = get_authenticated_caller(
            "build",
            request=http_request,
            user_id=request.user_id,
            identity_token=request.identity_token,
        )
        request.user_id = caller.user_id
        request.identity_token = caller.identity_token
        logger.info("Build package request received for user: %s", request.user_id)

        build_id = docker_service.generate_uuid(prefix="bld")
        logger.debug("Generated build ID: %s", build_id)

        tlog = http_request.app.state.trusted_log
        ctx = tlog.init_record(context={"chain_ref": TRANSPARENCY_SERVICE_CHAIN_ID})
        record_id = ctx.record_id
        add_authenticated_identity_entries(tlog, record_id, caller)
        tlog.add_entry(record_id, Entry(key="build_id", value=build_id))

        if os.path.exists(os.path.join(BUILD_DIR, "luks")):
            build_path = os.path.join((os.path.join(BUILD_DIR, "luks")), build_id)
        else:
            build_path = os.path.join(BUILD_DIR, build_id)
            logger.info("NOW build not in luks file.")
        logger.info(f"check path: {build_path}")
        os.makedirs(build_path, exist_ok=True)
        logger.debug("Created build directory: %s", build_path)
        tlog.add_entry(record_id, Entry(key="build_path", value=build_path))

        dockerfile_path = os.path.join(build_path, "Dockerfile")
        with open(dockerfile_path, "w") as file_handle:
            file_handle.write(request.dockerfile)
        logger.debug("Saved Dockerfile to: %s", dockerfile_path)

        if request.app_binary:
            binary_path = os.path.join(build_path, "app.bin")
            binary_bytes = base64.b64decode(request.app_binary)
            with open(binary_path, "wb") as file_handle:
                file_handle.write(binary_bytes)
            logger.debug("Saved app binary to: %s", binary_path)
            binary_hash = hashlib.sha256(binary_bytes).hexdigest()
            tlog.add_entry(
                record_id,
                Entry(
                    key="app_binary",
                    value={
                        "app_binary_path": binary_path,
                        "app_binary_hash": binary_hash,
                    },
                ),
            )

        if request.configs:
            config_dir = os.path.join(build_path, "configs")
            os.makedirs(config_dir, exist_ok=True)
            for index, config in enumerate(request.configs):
                config_path = os.path.join(config_dir, f"config_{index}")
                with open(config_path, "wb") as file_handle:
                    file_handle.write(base64.b64decode(config))
            logger.debug("Saved %s config files", len(request.configs))
            config_hashes = [hashlib.sha256(base64.b64decode(config)).hexdigest() for config in request.configs]
            tlog.add_entry(
                record_id,
                Entry(
                    key="config",
                    value={
                        "config_dir": config_dir,
                        "config_count": len(request.configs),
                        "config_hashes": config_hashes,
                    },
                ),
            )

        if request.data:
            data_dir = os.path.join(build_path, "data")
            os.makedirs(data_dir, exist_ok=True)
            for index, data in enumerate(request.data):
                data_path = os.path.join(data_dir, f"data_{index}")
                with open(data_path, "wb") as file_handle:
                    file_handle.write(base64.b64decode(data))
            logger.debug("Saved %s data files", len(request.data))
            data_hashes = [hashlib.sha256(base64.b64decode(data)).hexdigest() for data in request.data]
            tlog.add_entry(
                record_id,
                Entry(
                    key="data",
                    value={
                        "data_dir": data_dir,
                        "data_count": len(request.data),
                        "data_hashes": data_hashes,
                    },
                ),
            )

        docker_service.update_build_status(request.user_id, build_id, "submitted")
        logger.info(f"Starting synchronous build process for build ID: {build_id}")
        build_result = build_container_sync(request, build_id, tlog, record_id)
        if build_result is None:
            build_result = {
                "success": False,
                "error_message": "Build failed before producing a result",
            }
        
        # Return result based on build outcome
        if build_result["success"]:
            return BuildPackageResponse(
                build_id=build_id,
                status="success",
                user_id=request.user_id,
                estimated_time="120s",
                transparencyLog_verify=build_result.get("transparencyLog_verify")
            )
        else:
            return BuildPackageResponse(
                build_id=build_id,
                status="failed",
                user_id=request.user_id,
                error_message=build_result.get("error_message")
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Build package request failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to start build: {exc}") from exc


def build_container_sync(request: BuildPackageRequest, build_id: str, tlog: TrustedLogAPI, record_id: str):
    """Build a container in the background with detailed status tracking."""
    tlog_id = None
    try:
        docker_service.update_build_status(request.user_id, build_id, "preparing", step="Initializing build process")
        image_name = docker_service.local_build_image_ref(build_id)
        tlog.add_entry(record_id, Entry(key="image_name", value=image_name))
        docker_service.update_build_status(request.user_id, build_id, "building", step="Building container image")
        build_success = docker_service.build_image(request.dockerfile, build_id, request.user_id, tlog, record_id)

        if not build_success:
            docker_service.update_build_status(request.user_id, build_id, "failed", step="Container build failed")
            return {"success": False, "error_message": "Container build failed"}

        decryption_key = None
        encryption_key_source = "generated"
        if not request.sign_key or not request.cert:
            docker_service.update_build_status(request.user_id, build_id, "preparing", step="Get signing and encryption keys")
            attestation_result, decryption_key = docker_service.get_pubKey_from_KBS(tlog, record_id)
            if attestation_result != "trusted":
                docker_service.update_build_status(
                    request.user_id,
                    build_id,
                    "failed",
                    error_message="Attestation failed: get key failed.",
                )
                return {"success": False, "error_message": "Attestation failed: get key failed."}
            encryption_key_source = "kbs"

            docker_service.update_build_status(
                request.user_id,
                build_id,
                "preparing",
                step="Generating signing and encryption keys",
            )
            sign_key, cert, private_encryption_key, public_encryption_key = docker_service.generate_key(build_id, tlog, record_id)
            if not sign_key or not cert or not private_encryption_key or not public_encryption_key:
                docker_service.update_build_status(
                    request.user_id,
                    build_id,
                    "failed",
                    step="Key generation failed",
                    error_message="Failed to generate keys",
                )
                return {"success": False, "error_message": "Failed to generate keys"}

            request.sign_key = sign_key
            request.cert = cert
            if not decryption_key:
                decryption_key = {"opensslPub": public_encryption_key}
                encryption_key_source = "generated"

            docker_service.update_build_status(
                request.user_id,
                build_id,
                "preparing",
                step="Keys generated successfully",
                cert_url=f"/api/artifacts/{build_id}/{os.path.basename(cert)}",
            )

        try:
            docker_service.update_build_status(request.user_id, build_id, "generating_sbom", step="Generating SBOM")
            sbom_path = docker_service.generate_sbom(image_name, build_id, tlog, record_id)
            if not sbom_path:
                raise Exception("SBOM generation failed")

            if request.encrypt:
                if not decryption_key:
                    raise Exception("Encryption requested, but no encryption key available")

                docker_service.update_build_status(request.user_id, build_id, "encrypting", step="Encrypting container image")
                logger.info(
                    "Encrypting image %s with key source=%s path=%s",
                    image_name,
                    encryption_key_source,
                    decryption_key.get("opensslPub"),
                )
                encrypted_image_name = docker_service.encrypt_image(
                    image_name,
                    build_id,
                    decryption_key["opensslPub"],
                    tlog,
                    record_id,
                )
                if not encrypted_image_name:
                    raise Exception("Image encryption failed")
                image_name = encrypted_image_name
            else:
                exported_image_name = docker_service.export_image_to_oci(image_name, build_id, tlog, record_id)
                if not exported_image_name:
                    raise Exception("Image export failed")
                image_name = exported_image_name
        except Exception as exc:
            docker_service.update_build_status(
                request.user_id,
                build_id,
                "failed",
                step="SBOM/Encryption failed",
                error_message=f"Image encryption or SBOM generation failed: {exc}",
            )
            return {
                "success": False,
                "error_message": f"Image encryption or SBOM generation failed: {exc}",
            }

        identity_token = request.identity_token
        if identity_token:
            log_proxy_configuration("Build transparency log")
            tlog_status, tlog_id = docker_service.commit_and_save_receipt("build", build_id, tlog, record_id, identity_token)
            if tlog_id is not None:
                docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "added", build_id)
            if not tlog_status:
                docker_service.update_build_status(
                    request.user_id,
                    build_id,
                    "failed",
                    step="Transparency log commit failed",
                    image_id=image_name,
                    image_url=image_name,
                    sbom_url=sbom_path,
                    cert_url=f"/api/artifacts/{build_id}/cosign.crt",
                    transparencyLog_verify="failed",
                    error_message="Build transparency log commit failed",
                )
                return {"success": False, "error_message": "Build transparency log commit failed"}

            verify_tlog_status = docker_service.verify_chain_state("build", tlog, chain_id=TRANSPARENCY_SERVICE_CHAIN_ID)
        else:
            verify_tlog_status = "skipped"

        if image_name.startswith("oci:"):
            published_image_id = image_name
            published_image_url = image_name
            published_sbom_url = sbom_path
        else:
            published_image_id = image_name
            published_image_url = image_name
            published_sbom_url = sbom_path

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
            cert_url=f"/api/artifacts/{build_id}/cosign.crt",
        )
        return {
            "success": True,
            "image_id": published_image_id,
            "image_url": published_image_url,
            "sbom_url": published_sbom_url,
            "cert_url": f"/api/artifacts/{build_id}/cosign.crt",
            "log_id": tlog_id,
            "transparencyLog_verify": verify_tlog_status
        }
    except Exception as exc:
        logger.error("Build failed for build ID %s: %s", build_id, exc)
        docker_service.update_build_status(
            request.user_id,
            build_id,
            "failed",
            step="Unexpected error",
            log_id=f"{tlog_id}" if tlog_id else f"uuid-{uuid.uuid4()}",
            error_message=str(exc),
        )
        return {"success": False, "error_message": str(exc)}


async def publish_package(http_request: Request, request: PublishPackageRequest):
    """Publish image and SBOM to the registry with logging."""
    try:
        caller = get_authenticated_caller(
            "publish",
            request=http_request,
            user_id=request.user_id,
            identity_token=request.identity_token,
        )
        request.user_id = caller.user_id
        request.identity_token = caller.identity_token
        publish_id = "pub-" + request.build_id.split("-")[-1]

        build_result = docker_service.get_build_status(request.build_id)
        if build_result is None:
            raise HTTPException(status_code=404, detail=f"Build {request.build_id} not found")
        if build_result.user_id and build_result.user_id != caller.user_id:
            raise HTTPException(status_code=403, detail="Publish request does not own the referenced build artifact")

        if os.path.exists(os.path.join(BUILD_DIR, "luks")):
            expected_build_dir = (Path(os.path.join(BUILD_DIR, "luks")) / request.build_id).resolve(strict=False)
        else:
            expected_build_dir = (Path(BUILD_DIR) / request.build_id).resolve(strict=False)
        logger.info(f"CHECK statu: {expected_build_dir}")
        stored_image_ref = _normalize_local_oci_reference(build_result.image_id)
        requested_image_ref = _normalize_local_oci_reference(request.image_id)
        actual_image_ref = stored_image_ref or requested_image_ref
        if requested_image_ref and requested_image_ref.startswith("oci:"):
            requested_image_path = Path(requested_image_ref[4:]).resolve(strict=False)
            if requested_image_path.exists():
                actual_image_ref = requested_image_ref
        if not actual_image_ref:
            raise HTTPException(status_code=400, detail="Publish request could not resolve a build OCI artifact")

        request.image_id = actual_image_ref
        image_name = request.image_id.split("/")[-1].split(":")[0]
        registry_repo = f"{DOCKER_REPOSITORY}/{image_name}:latest-encrypted"
        actual_image_path = None
        if actual_image_ref and actual_image_ref.startswith("oci:"):
            actual_image_path = Path(actual_image_ref[4:]).resolve(strict=False)
            try:
                actual_image_path.relative_to(expected_build_dir)
            except ValueError as exc:
                raise HTTPException(
                    status_code=403,
                    detail="Publish request image_id must reference the caller-owned OCI artifact for the specified build",
                ) from exc
            if not actual_image_path.exists():
                raise HTTPException(status_code=404, detail="Publish request OCI artifact was not found on disk")

        tlog = http_request.app.state.trusted_log
        ctx = tlog.init_record(context={"chain_ref": TRANSPARENCY_SERVICE_CHAIN_ID})
        record_id = ctx.record_id
        add_authenticated_identity_entries(tlog, record_id, caller)

        try:
            tlog.add_entry(record_id, Entry(key="publishID", value={"publishID": publish_id}))
            docker_service.update_publish_status(request.user_id, request.build_id, "pushing", publish_id, step="Pushing image to registry")

            if request.image_id.startswith("oci:"):
                source_ref = request.image_id
            else:
                source_ref = f"docker-daemon:{request.image_id}"
            dest_ref = f"docker://{registry_repo}"

            log_proxy_configuration("Publish image push")
            push_success = docker_service.push_image(source_ref, dest_ref, tlog, record_id)
            if not push_success:
                raise Exception("Image push failed")
            tlog.add_entry(
                record_id,
                Entry(
                    key="log",
                    value={
                        "publish_source": source_ref,
                        "publish_dest": dest_ref,
                        "publishImage_status": push_success,
                    },
                ),
            )
        except Exception as exc:
            tlog.add_entry(record_id, Entry(key="publish_status", value={"publish_status": "failed", "error": str(exc)}))
            docker_service.update_publish_status(
                request.user_id,
                request.build_id,
                "failed",
                publish_id,
                step="Image push failed",
                error_message=f"Image push failed: {exc}",
            )
            raise HTTPException(status_code=400, detail=f"Image push failed: {exc}") from exc

        attestation_result, decryption_key = docker_service.get_pubKey_from_KBS(tlog, record_id)
        if decryption_key:
            try:
                docker_service.update_publish_status(request.user_id, request.build_id, "signing", publish_id, step="Signing image and SBOM")
                sign_success = docker_service.sign_image(request.image_id, decryption_key["cosignKey"], tlog, record_id)
                if not sign_success:
                    raise Exception("Image signing failed")
                tlog.add_entry(record_id, Entry(key="publish_sbom", value={"publish_sbom": sign_success}))

                sbom_attestation_success = docker_service.create_sbom_attestation(
                    request.image_id,
                    request.sbom_url,
                    decryption_key["cosignKey"],
                    tlog,
                    record_id,
                )
                tlog.add_entry(
                    record_id,
                    Entry(key="verify_sbom_status", value={"verify_sbom_status": sbom_attestation_success}),
                )
                if not sbom_attestation_success:
                    raise Exception("SBOM attestation failed")
            except Exception as exc:
                tlog.add_entry(record_id, Entry(key="publish_error", value={"error": str(exc)}))
                docker_service.update_publish_status(
                    request.user_id,
                    request.build_id,
                    "failed",
                    publish_id,
                    step="Signing failed",
                    error_message=f"Image signing or SBOM attestation failed: {exc}",
                )
                raise HTTPException(status_code=500, detail=f"Image signing or SBOM attestation failed: {exc}") from exc

        tlog_status, tlog_id = docker_service.commit_and_save_receipt("publish", request.build_id, tlog, record_id, request.identity_token)
        docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "added", request.build_id)
        verify_tlog_status = docker_service.verify_chain_state("publish", tlog, chain_id=TRANSPARENCY_SERVICE_CHAIN_ID)

        docker_service.update_publish_status(
            request.user_id,
            request.build_id,
            "success",
            publish_id,
            step="complete publish verify",
            transparencyLog_verify=verify_tlog_status,
            log_id=tlog_id,
            image_id=request.image_id.split("/")[-1],
            sbom_url=request.sbom_url,
            image_url=f"docker.io/{registry_repo}",
        )
        return PublishPackageResponse(
            build_id=request.build_id,
            publish_id=publish_id,
            status="success",
            image_id=request.image_id.split("/")[-1],
            sbom_url=request.sbom_url,
            image_url=f"docker.io/{registry_repo}",
            user_id=request.user_id,
            transparencyLog_verify=verify_tlog_status,
            log_id=f"{tlog_id}" if tlog_id else f"uuid-{uuid.uuid4()}",
            published_at=datetime.now(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to publish package: {exc}") from exc


async def get_publish_result(http_request: Request, build_id: str):
    try:
        build_id = _validate_runtime_id(build_id, "build_id")
        publish_result = docker_service.get_publish_status(build_id)
        if not publish_result:
            raise HTTPException(status_code=404, detail="Publish not found")
        return publish_result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to get publish result: {exc}") from exc


async def get_build_result(http_request: Request, build_id: str):
    try:
        build_id = _validate_runtime_id(build_id, "build_id")
        build_result = docker_service.get_build_status(build_id)
        if not build_result:
            raise HTTPException(status_code=404, detail="Build not found")
        return build_result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to get build result: {exc}") from exc


async def deploy_launch(
    http_request: Request,
    request: LaunchRequest,
    background_tasks: BackgroundTasks,
):
    """Deploy and launch a container on worker nodes."""
    try:
        caller = get_authenticated_caller(
            "launch",
            request=http_request,
            user_id=request.user_id,
            identity_token=request.identity_token,
        )
        request.user_id = caller.user_id
        request.identity_token = caller.identity_token
        tlog = http_request.app.state.trusted_log
        workload_id = docker_service.normalize_workload_id(request.user_id, request.image_id, request.metadata)
        transparency_chain_id = workload_transparency_chain_id(workload_id)
        ctx = tlog.init_record(context={"chain_ref": transparency_chain_id})
        record_id = ctx.record_id
        add_authenticated_identity_entries(tlog, record_id, caller)

        launch_id = docker_service.generate_uuid(prefix="launch")
        tlog.add_entry(record_id, Entry(key="launch_id", value={"launch_id": launch_id}))
        tlog.add_entry(record_id, Entry(key="workload_id", value=workload_id))

        launch_path = os.path.join(BUILD_DIR, launch_id)
        tlog.add_entry(record_id, Entry(key="launch_path", value={"launch_path": launch_path}))
        os.makedirs(launch_path, exist_ok=True)

        config_path = os.path.join(launch_path, "launch_config.json")
        with open(config_path, "w") as file_handle:
            json.dump(request.model_dump(), file_handle, indent=2)

        docker_service.update_launch_status(
            user_id=request.user_id,
            launch_id=launch_id,
            status="initiated",
            created_at=datetime.now(),
        )
        background_tasks.add_task(
            launch_container_async,
            request,
            launch_id,
            workload_id,
            transparency_chain_id,
            launch_path,
            tlog,
            record_id,
        )
        return LaunchResponse(launch_id=launch_id, status="initiated", user_id=request.user_id)
    except HTTPException:
        raise
    except Exception as exc:
        if "launch_path" in locals():
            shutil.rmtree(launch_path, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Failed to initiate launch: {exc}") from exc


async def launch_container_async(
    request: LaunchRequest,
    launch_id: str,
    workload_id: str,
    transparency_chain_id: str,
    launch_path: str,
    tlog: TrustedLogAPI,
    record_id: str,
):
    """Launch a container in the background."""
    try:
        docker_service.update_launch_status(request.user_id, launch_id, "launching")

        log_file = os.path.join(launch_path, "launch.log")
        with open(log_file, "w") as file_handle:
            file_handle.write(f"Launch started at {datetime.now().isoformat()}\n")
        tlog.add_entry(record_id, Entry(key="launch-log", value={"launch-log": log_file}))
        tlog.add_entry(record_id, Entry(key="workload_id", value=workload_id))

        image_digest = docker_service._resolve_image_digest(request.image_url or request.image_id)
        security_projection = docker_service._build_launch_security_projection(launch_id, workload_id)
        launch_config_digest = docker_service._json_sha384_digest(
            {
                "request": request.model_dump(),
                "security_projection": security_projection,
            }
        )
        for entry in launch_security_entries(
            security_projection,
            image_digest=image_digest,
            launch_config_digest=launch_config_digest,
        ):
            tlog.add_entry(record_id, entry)

        attestation_result = "trusted"
        decryption_key = None
        if request.attestation_required:
            attestation_result, decryption_key = await docker_service.verify_attestation(
                request.image_id,
                request.user_id,
                tlog,
                record_id,
            )
            tlog.add_entry(record_id, Entry(key="verify_image", value={"verify_image": attestation_result}))
            tlog.add_entry(record_id, Entry(key="verify_keys", value={"verify_keys": decryption_key}))
            if attestation_result != "trusted":
                docker_service.update_launch_status(
                    request.user_id,
                    launch_id,
                    "failed",
                    error_message=f"Attestation failed: {attestation_result}",
                )
                tlog.add_entry(record_id, Entry(key="verify_image", value={"verify_image": attestation_result}))
                return

        log_proxy_configuration("Launch image pull")
        pull_success = docker_service.pull_image(
            tlog,
            record_id,
            image_url=request.image_url,
            target_dir=launch_path,
            openssl_key=decryption_key["opensslKey"] if decryption_key else None,
        )
        if not pull_success:
            docker_service.update_launch_status(request.user_id, launch_id, "failed", error_message="Image pull failed")
            tlog.add_entry(record_id, Entry(key=EventEntryKey.launch_result.value, value="failed"))
            return

        if request.sbom_url:
            cosign_pubkey = None
            if decryption_key and isinstance(decryption_key, dict):
                cosign_pubkey = decryption_key.get("cosignPub")
            verify_image_ref = _normalize_local_oci_reference(request.image_url)
            if cosign_pubkey:
                sbom_valid = docker_service.verify_sbom(
                    verify_image_ref,
                    request.sbom_url,
                    tlog,
                    record_id,
                    cosign_pubkey,
                )
            else:
                sbom_valid = True
            tlog.add_entry(record_id, Entry(key="sbom_verify", value={"sbom_verify": sbom_valid}))
            if not sbom_valid:
                docker_service.update_launch_status(request.user_id, launch_id, "failed", error_message="SBOM verification failed")
                tlog.add_entry(record_id, Entry(key="sbom_verify", value={"sbom_verify": sbom_valid}))
                tlog.add_entry(record_id, Entry(key=EventEntryKey.launch_result.value, value="failed"))
                return

        instance_ids = await docker_service.launch_containers(
            tlog,
            record_id,
            image_url=request.image_url,
            image_id=request.image_id,
            launch_pth=launch_path,
            workload_id=workload_id,
            launch_id=launch_id,
        )
        tlog.add_entry(record_id, Entry(key="launch_instance_ids", value={"launch_instance_ids": instance_ids}))
        if not instance_ids:
            docker_service.update_launch_status(request.user_id, launch_id, "failed", error_message="Container launch failed")
            tlog.add_entry(record_id, Entry(key=EventEntryKey.launch_result.value, value={EventEntryKey.launch_result.value: "failed"}))
            return

        evidences = {
            "launch_id": launch_id,
            "workload_id": workload_id,
            "image_id": request.image_id,
            "image_digest": image_digest,
            "launch_config_digest": launch_config_digest,
            "user_id": request.user_id,
            "timestamp": datetime.now().isoformat(),
            "attestation_result": attestation_result,
            "instance_ids": instance_ids,
        }

        tlog_status, log_id = docker_service.commit_and_save_receipt(
            "launch",
            launch_id,
            tlog,
            record_id,
            request.identity_token,
        )
        docker_service.update_transparencylog_status(request.user_id, str(log_id), "added", launch_id)
        verify_tlog_status = docker_service.verify_chain_state("launch", tlog, chain_id=transparency_chain_id)

        docker_service.update_launch_status(
            request.user_id,
            launch_id=launch_id,
            status="success",
            validation="passed",
            attestation=attestation_result,
            evidence=evidences,
            transparencyLog_verify=verify_tlog_status,
            log_id=f"{log_id}" if log_id else f"uuid-{uuid.uuid4()}",
            instance_ids=instance_ids,
        )
    except Exception as exc:
        docker_service.update_launch_status(request.user_id, launch_id, "failed", error_message=str(exc))
        with open(os.path.join(launch_path, "launch.log"), "a") as file_handle:
            file_handle.write(f"Error: {exc}\n")


async def get_launch_result(http_request: Request, launch_id: str):
    try:
        launch_result = docker_service.get_launch_status(launch_id)
        if not launch_result:
            raise HTTPException(status_code=404, detail="Launch not found")
        return launch_result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to get launch result: {exc}") from exc


__all__ = [
    "BuildPackageRequest",
    "BuildPackageResponse",
    "BuildResult",
    "LaunchRequest",
    "LaunchResponse",
    "LaunchResult",
    "PublishPackageRequest",
    "PublishPackageResponse",
    "PublishResult",
    "_normalize_local_oci_reference",
    "build_container_async",
    "build_package",
    "deploy_launch",
    "docker_service",
    "get_build_result",
    "get_launch_result",
    "get_publish_result",
    "launch_container_async",
    "publish_package",
    "workload_transparency_chain_id",
]