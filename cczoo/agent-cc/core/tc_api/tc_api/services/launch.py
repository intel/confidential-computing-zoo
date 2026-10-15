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
import tempfile
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from ..config import (
    BUILD_DIR,
    DOCKER_CMD,
    SKOPEO_CMD,
)
from ..docktap.workload_store import WorkloadStore
from . import workload_profile
from ..models import LaunchResult, TransparencyResult
from ..transparency.commit_client import TrustedLogAPI
from ..transparency.events import EventEntryKey
from tlog.types import Entry

logger = logging.getLogger(__name__)

def _is_insecure_local_registry_ref(image_ref: str) -> bool:
    if not image_ref.startswith("docker://"):
        return False

    registry = image_ref[len("docker://"):].split("/", 1)[0]
    if registry.startswith(("localhost:", "127.0.0.1:")):
        return True

    configured_registry = os.getenv("DOCKER_REGISTRY", "").strip()
    if configured_registry and registry == configured_registry:
        return True

    return registry == "registry:5000"


def _load_transparency_artifact(build_path: str) -> dict:
    if not os.path.isdir(build_path):
        return {}

    candidate_suffixes = (
        "-commit-receipt.json",
        "-transparency.json",
    )
    for suffix in candidate_suffixes:
        for name in sorted(os.listdir(build_path)):
            if not name.endswith(suffix):
                continue
            artifact_path = os.path.join(build_path, name)
            if not os.path.isfile(artifact_path):
                continue
            with open(artifact_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    return {}


class LaunchServiceMixin:
    def normalize_workload_id(self, user_id: str, image_id: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        metadata = metadata or {}
        workload_id = metadata.get("workload_id")
        if isinstance(workload_id, str) and workload_id.strip():
            return workload_id.strip()
        if image_id:
            return image_id.split(":", 1)[0]
        return user_id

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

    def _build_launch_security_projection(self, launch_id: str, workload_id: str, metadata=None, settings=None) -> Dict[str, Any]:
        if settings is None:
            settings = workload_profile.profile_settings(metadata, workload_id)
        if settings is not None:
            projection = workload_profile.security_projection(settings, launch_id, workload_id)
            projection["launch_env_digest"] = self._json_sha384_digest(workload_profile.launch_environment(settings))
            return projection
        mounts = [
            "/etc/hosts:/etc/hosts:ro",
            "/etc/sgx_default_qcnl.conf:/etc/sgx_default_qcnl.conf:ro",
            "/usr/share/doc/libtdx-attest-dev/examples/:/td-attest/:ro",
            "/etc/tdx-attest.conf:/etc/tdx-attest.conf:ro",
        ]
        devices = ["/dev/tdx_guest"]
        return {
            "launch_id": launch_id,
            "workload_id": workload_id,
            "privileged": False,
            "network_mode": "host",
            "mounts": mounts,
            "devices": devices,
            "capabilities": [],
            "launch_env_keys": ["HF_HUB_OFFLINE"],
            "launch_env_digest": self._json_sha384_digest({"HF_HUB_OFFLINE": "1"}),
        }

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

    def image_archive_refs(self, image_id: str, launch_pth: str, launch_id: Optional[str] = None, workload_id: Optional[str] = None):
        """
        Compute the docker-archive destination and the image reference it must
        load as. Shared by the pull step (which may write the archive directly)
        and the launch step (which consumes it), so both agree on the naming.
        """
        if image_id.startswith("oci:"):
            local_tag = launch_id or workload_id or f"local-{uuid.uuid4().hex[:12]}"
            loaded_image_ref = f"tc-api-{local_tag}:latest"
        else:
            loaded_image_ref = image_id if ':' in image_id else f"{image_id}:latest"
        archive_name = loaded_image_ref.replace('/', '_').replace(':', '_')
        archive_path = os.path.join(launch_pth, f"{archive_name}-image.tar")
        archive_ref = f"docker-archive:{archive_path}:{loaded_image_ref}"
        return loaded_image_ref, archive_path, archive_ref

    def pull_image(self, tlog: TrustedLogAPI, record_id: str, image_url: str, openssl_key: str, target_dir: str, max_retries: int = 3, retry_delay: int = 5, dest_ref: Optional[str] = None) -> bool:

        source_ref = image_url
        if source_ref and ":" not in source_ref and os.path.isdir(source_ref):
            source_ref = f"oci:{source_ref}"
        source_ref = source_ref.replace("docker.io","docker:/")
        # Preserve the image config bytes for non-encrypted registry pulls by
        # writing the docker-archive destination directly. The docker->oci copy
        # deterministically rewrites the config JSON, which would change the
        # loaded image config digest and fail the strict approval comparison.
        dest_ref = dest_ref or os.path.join('oci:'+target_dir,'encrypted')
        insecure_local_registry = _is_insecure_local_registry_ref(source_ref)

        attempt = 0
        while attempt < max_retries:
            try:
                attempt += 1
                logger.info(f"Pulling image (attempt {attempt}/{max_retries}): {source_ref}")

                if openssl_key:
                    cmd = [SKOPEO_CMD, "copy", "--decryption-key", openssl_key, source_ref, dest_ref]
                else:
                    cmd = [SKOPEO_CMD, "copy", source_ref, dest_ref]
                if insecure_local_registry:
                    cmd.insert(2, "--src-tls-verify=false")
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
            if launch_id in self.launches:
                launch_result = self.launches[launch_id]
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
                self.launches[launch_id] = LaunchResult(
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
            if log_id in self.transparency_logs:
                tlog_result = self.transparency_logs[log_id]
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
                tlog_path = os.path.join(BUILD_DIR, build_id)
                data = _load_transparency_artifact(tlog_path)
                if not data:
                    logger.debug("Transparency artifact not found under %s", tlog_path)
                self.transparency_logs[log_id] = TransparencyResult(
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
        return self.transparency_logs.get(log_id)

    def get_launch_status(self, launch_id: str) -> Optional[LaunchResult]:
        """Get launch status by launch_id"""
        return self.launches.get(launch_id)

    async def launch_containers(
        self,
        tlog,
        record_id,
        image_url,
        image_id,
        launch_pth,
        workload_id: Optional[str] = None,
        launch_id: Optional[str] = None,
        image_digest: Optional[str] = None,
        service_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        attested_settings: Optional[Dict[str, Any]] = None,
        pulled_archive_ref: Optional[str] = None,
    ):
        if attested_settings is None:
            attested_settings = workload_profile.profile_settings(metadata, workload_id)
        loaded_image_ref, archive_path, archive_ref = self.image_archive_refs(
            image_id, launch_pth, launch_id=launch_id, workload_id=workload_id)

        try:
            # When the pull step already wrote the docker-archive directly (no
            # encrypted oci intermediate), there is nothing to export. The pull
            # step must have produced exactly the archive this launch step expects.
            if pulled_archive_ref is not None:
                if pulled_archive_ref != archive_ref:
                    raise ValueError(
                        f"pulled archive {pulled_archive_ref} does not match expected archive {archive_ref}")
                tlog.add_entry(record_id, Entry(key="export_skipped", value={
                    "export_skipped": True,
                    "reason": "pull_image wrote the docker-archive destination directly",
                    "archive_ref": archive_ref,
                }))
            else:
                image_dir = 'oci:' + os.path.join(launch_pth,'encrypted')
                cmd = [SKOPEO_CMD, "copy", image_dir, archive_ref]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

                if res.returncode == 0:
                    logger.info(f"Success export {loaded_image_ref} archive.")
                    logger.debug(f"CMD: {' '.join(cmd)}")
                    tlog.add_entry(record_id, Entry(key="pullImage", value={"pullImage_cmd": " ".join(cmd), "pullImage_status": "success"}))
                else:
                    logger.info("Failed add image.")
                    logger.debug(f"CMD: {' '.join(cmd)}")
                    tlog.add_entry(record_id, Entry(key="pullImage_status", value="failed"))
                    return False

            load_cmd = [DOCKER_CMD, "load", "-i", archive_path]
            load_res = subprocess.run(load_cmd, capture_output=True, text=True, timeout=600)
            if load_res.returncode == 0:
                logger.info(f"Success load image {loaded_image_ref}.")
                tlog.add_entry(record_id, Entry(key="docker_load", value={
                    "docker_load_cmd": " ".join(load_cmd),
                    "docker_load_status": "success",
                    "docker_load_stdout": load_res.stdout,
                    "docker_load_stderr": load_res.stderr,
                }))
            else:
                logger.info("Failed load image archive.")
                logger.debug(f"CMD: {' '.join(load_cmd)}")
                tlog.add_entry(record_id, Entry(key="docker_load", value={
                    "docker_load_cmd": " ".join(load_cmd),
                    "docker_load_status": "failed",
                    "docker_load_stdout": load_res.stdout,
                    "docker_load_stderr": load_res.stderr,
                }))
                return False

            if attested_settings is not None:
                docker_cmd = workload_profile.docker_command(DOCKER_CMD, attested_settings)
            else:
                docker_cmd = [
                    DOCKER_CMD,
                    "run",
                    "-d",
                    "-it",
                    "--device",
                    "/dev/tdx_guest:/dev/tdx_guest",
                    "-e",
                    "HF_HUB_OFFLINE=1",
                    "-v",
                    "/etc/hosts:/etc/hosts:ro",
                    "--network=host",
                ]
            if workload_id:
                docker_cmd.extend(["--label", f"io.trucon.workload-id={workload_id}"])
            if launch_id:
                docker_cmd.extend(["--label", f"io.trucon.launch-id={launch_id}"])
            if attested_settings is None:
                docker_cmd.extend([
                    "-v",
                    "/etc/sgx_default_qcnl.conf:/etc/sgx_default_qcnl.conf:ro",
                    "-v",
                    "/usr/share/doc/libtdx-attest-dev/examples/:/td-attest/:ro",
                    "-v",
                    "/etc/tdx-attest.conf:/etc/tdx-attest.conf:ro",
                ])

            # Keep application environment values out of argv and launch logs.
            environment_file = None
            try:
                if attested_settings is not None:
                    # mkstemp creates a private file. Docker consumes it during
                    # this call; finally removes it on both success and failure.
                    fd, environment_file = tempfile.mkstemp(prefix="argus-workload-env-")
                    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
                        for key, value in workload_profile.launch_environment(attested_settings).items():
                            output.write(f"{key}={value}\n")
                    docker_cmd.extend(["--env-file", environment_file])
                docker_cmd.append(loaded_image_ref)
                logger.info(f"Runcmd : {' '.join(docker_cmd)}")
                dockerRUn = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=120)
            finally:
                if environment_file is not None:
                    os.unlink(environment_file)
            if dockerRUn.returncode == 0:
                logger.info(f"Success run image {image_id}.")
                tlog.add_entry(record_id, Entry(key="launch_cmd", value={"launch_cmd": " ".join(docker_cmd),
                                     "launch_status": "success",
                                     "launch_stdout": dockerRUn.stdout,
                                     }))
                tlog.add_entry(record_id, Entry(key=EventEntryKey.launch_result.value, value="success"))
            else:
                logger.info("Failed run image.")
                logger.debug(f"CMD: {' '.join(docker_cmd)}")
                tlog.add_entry(record_id, Entry(key="launch_status", value={"launch_status": "failed",
                                     "launch_stderr": dockerRUn.stderr}))
                tlog.add_entry(record_id, Entry(key=EventEntryKey.launch_result.value, value="failed"))
                return False

            # Use this invocation's returned ID. A global "latest container"
            # query could select another concurrent launch.
            containerID = dockerRUn.stdout.strip()
            if containerID:
                logger.info(f"Success get image ID {containerID}")
                tlog.add_entry(record_id, Entry(key="getContainerID_cmd", value={"getContainerID_cmd": " ".join(docker_cmd),
                                     "getContainerID_status": "success",
                                     "getID_stdout": containerID
                                     }))
                tlog.add_entry(record_id, Entry(key=EventEntryKey.instance_id.value, value=containerID))
            else:
                logger.info("Docker run returned an empty container ID.")
                tlog.add_entry(record_id, Entry(key="getContainerID_status", value={"getContainerID_status": "failed",
                                     "getID_stderr": "docker run returned an empty container ID"
                                     }))
                return False
            
            #docker inspect ID --format '{{.State.Status}}'
            getStatus = [DOCKER_CMD, "inspect", "--format", "{{.State.Status}}", containerID]
            getStatus_res = subprocess.run(getStatus, capture_output=True, text=True)
            if getStatus_res.returncode == 0:
                status_text = getStatus_res.stdout.strip()
                logger.info(f"Success get container {containerID} status: {status_text}")
                tlog.add_entry(record_id, Entry(key="getStatus_cmd", value={"getStatus_cmd": " ".join(getStatus),
                                     "get_status": status_text}))
            else:
                logger.info("Failed get container status.")
                logger.error(f"get container status cmd: {' '.join(getStatus)}")
                tlog.add_entry(record_id, Entry(key="get_status", value={"get_status": "failed",
                                     "getStatus_stderr": getStatus_res.stderr
                                     }))
                return False
            
            container_info = {"container_ID": containerID, "container_Status": status_text}
            if attested_settings is not None:
                # Record Docker's actual content identifiers and launch labels;
                # requested image names/digests alone do not identify the running instance.
                inspect_result = subprocess.run([DOCKER_CMD, "inspect", containerID], capture_output=True, text=True, timeout=30, check=True)
                inspected = json.loads(inspect_result.stdout)
                if len(inspected) != 1:
                    raise ValueError("expected exactly one launched container")
                container_info = workload_profile.observed_container(inspected[0], launch_id, workload_id)
            tlog.add_entry(record_id, Entry(key="container_info", value=container_info))
            if workload_id:
                workload_store = WorkloadStore()
                workload_store.init_db()
                workload_store.put(
                    containerID,
                    workload_id,
                    launch_id=launch_id,
                    operation="create",
                    image_digest=image_digest,
                    service_name=service_name,
                )
            return [container_info]

        except Exception as e:
            logger.exception("Container launch failed")
            tlog.add_entry(
                record_id,
                Entry(
                    key="Deploy_launch status",
                    value={"status": "failed", "error_type": type(e).__name__},
                ),
            )
            tlog.add_entry(record_id, Entry(key=EventEntryKey.launch_result.value, value="failed"))
            return False


__all__ = ['LaunchServiceMixin']
