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
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from ..config import (
    BUILD_DIR,
    DOCKER_CMD,
    SKOPEO_CMD,
)
from ..models import LaunchResult, TransparencyResult
from ..transparency.commit_client import TrustedLogAPI
from ..transparency.events import EventEntryKey
from tlog.types import Entry

logger = logging.getLogger(__name__)


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

    def _build_launch_security_projection(self, launch_id: str, workload_id: str) -> Dict[str, Any]:
        mounts = [
            "/etc/hosts:/etc/hosts",
            "/etc/sgx_default_qcnl.conf:/etc/sgx_default_qcnl.conf",
            "/usr/share/doc/libtdx-attest-dev/examples/:/td-attest/",
            "/etc/tdx-attest.conf:/etc/tdx-attest.conf",
        ]
        devices = ["/dev/tdx_guest"]
        return {
            "launch_id": launch_id,
            "workload_id": workload_id,
            "privileged": True,
            "network_mode": "host",
            "mounts": mounts,
            "devices": devices,
            "capabilities": ["ALL"],
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

    def pull_image(self, tlog: TrustedLogAPI, record_id: str, image_url: str, openssl_key: str, target_dir: str, max_retries: int = 3, retry_delay: int = 5) -> bool:

        source_ref = image_url
        if source_ref and ":" not in source_ref and os.path.isdir(source_ref):
            source_ref = f"oci:{source_ref}"
        source_ref = source_ref.replace("docker.io","docker:/")
        dest_ref = os.path.join('oci:'+target_dir,'encrypted')
        insecure_local_registry = source_ref.startswith("docker://localhost:") or source_ref.startswith("docker://127.0.0.1:")

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

    async def launch_containers(self, tlog, record_id, image_url, image_id, launch_pth, workload_id: Optional[str] = None, launch_id: Optional[str] = None, dockercmd: Optional[str] = None):
        image_dir = 'oci:' + os.path.join(launch_pth,'encrypted')
        if image_id.startswith("oci:"):
            local_tag = launch_id or workload_id or f"local-{uuid.uuid4().hex[:12]}"
            loaded_image_ref = f"tc-api-{local_tag}:latest"
        else:
            loaded_image_ref = image_id if ':' in image_id else f"{image_id}:latest"
        archive_name = loaded_image_ref.replace('/', '_').replace(':', '_')
        archive_path = os.path.join(launch_pth, f"{archive_name}-image.tar")
        archive_ref = f"docker-archive:{archive_path}:{loaded_image_ref}"
        
        try:
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

            # run docker image
            if dockercmd:
                docker_cmd = dockercmd.strip().split(" ")
                docker_gid = subprocess.run(["stat", "-c", "'%g'", "/var/run/docker.sock"], capture_output=True, text=True).stdout.replace('\n', '').strip("'")
                if docker_gid != None:
                    docker_cmd.extend(["--group-add", docker_gid])
                
                # image settings
                # Fix volume ownership
                cmd = [DOCKER_CMD, "run", "--rm", "--user", "root", "-v", "openclaw-config:/home/node/.openclaw", "-v", "openclaw-workspace:/home/node/.openclaw/workspace", "--entrypoint", "sh", loaded_image_ref, "-c"]
                cmd.append('find /home/node/.openclaw -xdev -exec chown node:node {} + 2>/dev/null; [ -d /home/node/.openclaw/workspace/.openclaw ] &&  chown -R node:node /home/node/.openclaw/workspace/.openclaw 2>/dev/null || true')
                fix_vol = subprocess.run(cmd, capture_output=True, text=True)
                if fix_vol.returncode == 0:
                    logger.info(f"Fix volume ownership.")
                    logger.info(" ".join(cmd))
                else:
                    logger.info("Fix volume ownership failed.")
                    logger.info(f"{fix_vol.stderr}")

                # Seed directory structure
                cmd1 = [DOCKER_CMD, "run",  "--rm", "--user", "node", "-v", "openclaw-config:/home/node/.openclaw", "-v", "openclaw-workspace:/home/node/.openclaw/workspace", "--entrypoint", "sh", loaded_image_ref, "-c"]
                cmd1.append('mkdir -p /home/node/.openclaw/identity /home/node/.openclaw/agents/main/agent /home/node/.openclaw/agents/main/sessions')
                makedir = subprocess.run(cmd1, capture_output=True, text=True)
                if makedir.returncode == 0:
                    logger.info(f"Seed directory structure.")
                    logger.info(" ".join(cmd1))
                else:
                    logger.info("Seed directory structure failed.")
                    logger.info(f"{makedir.stderr}")

                # Gateway defaults
                cmd2 = [DOCKER_CMD, "run",  "--rm", "--user", "node", "-v", "openclaw-config:/home/node/.openclaw", "-v", "openclaw-workspace:/home/node/.openclaw/workspace", "--entrypoint", "node", loaded_image_ref, "/app/dist/index.js"]
                for conf in [['config', 'set', 'gateway.mode',  'local'],['config', 'set', 'gateway.bind', 'lan'],['config', 'set', 'agents.defaults.sandbox.mode', 'all'],['config', 'set', 'agents.defaults.sandbox.scope', 'session'],['config', 'set', 'agents.defaults.sandbox.workspaceAccess', 'rw'],['config', 'set', 'agents.defaults.sandbox.backend', 'docker']]:
                    set_res = subprocess.run(cmd2+conf, capture_output=True, text=True)
                    if (set_res.returncode != 0):
                        logger.info(f"Seting failed.")
                        logger.info(" ".join(cmd2+conf))
                        logger.info(f"{set_res.stderr}")
            else:
                docker_cmd = [
                    DOCKER_CMD,
                    "run",
                    "-d",
                    "-it",
                    "--privileged",
                    "-e",
                    "HF_HUB_OFFLINE=1",
                    "-v",
                    "/etc/hosts:/etc/hosts",
                    "--network=host",
                ]
            if workload_id:
                docker_cmd.extend(["--label", f"io.trucon.workload-id={workload_id}"])
            if launch_id:
                docker_cmd.extend(["--label", f"io.trucon.launch-id={launch_id}"])
            docker_cmd.extend([
                "-v",
                "/etc/sgx_default_qcnl.conf:/etc/sgx_default_qcnl.conf",
                "-v",
                "/dev/tdx_guest:/dev/tdx_guest",
                "-v",
                "/usr/share/doc/libtdx-attest-dev/examples/:/td-attest/",
                "-v",
                "/etc/tdx-attest.conf:/etc/tdx-attest.conf",
            ])

            docker_cmd.append(loaded_image_ref)
            logger.info(f"Runcmd : {' '.join(docker_cmd)}")
            dockerRUn = subprocess.run(docker_cmd, capture_output=True, text=True)
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

            # docker ps -q --latest
            getID = [DOCKER_CMD, "ps", "-q", "--latest"]
            getID_res = subprocess.run(getID, capture_output=True, text=True)
            if getID_res.returncode == 0:
                containerID = getID_res.stdout.strip()
                logger.info(f"Success get image ID {containerID}")
                tlog.add_entry(record_id, Entry(key="getContainerID_cmd", value={"getContainerID_cmd": " ".join(getID),
                                     "getContainerID_status": "success",
                                     "getID_stdout": containerID
                                     }))
                tlog.add_entry(record_id, Entry(key=EventEntryKey.instance_id.value, value=containerID))
            else:
                logger.info("Failed get container ID.")
                tlog.add_entry(record_id, Entry(key="getContainerID_status", value={"getContainerID_status": "failed",
                                     "getID_stderr": getID_res.stderr
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
            tlog.add_entry(record_id, Entry(key="container_info", value=container_info))
            return [container_info]

        except Exception as e:
            logger.error(f"Launch contaioner failed: {str(e)}")
            tlog.add_entry(record_id, Entry(key="Deploy_launch status", value="success"))
            return False


__all__ = ['LaunchServiceMixin']
