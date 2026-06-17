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

import logging
import secrets
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..models import LuksResult
from ..transparency.commit_client import TrustedLogAPI
from tlog.types import Entry
from ..config import KBS_URL
import os

logger = logging.getLogger(__name__)
SCRIPT_DIR = Path(__file__).resolve().parents[3] / "config"


def _command_error_message(result, fallback: str) -> str:
    details = []
    stderr = (result.stderr or "").strip()
    stdout = (result.stdout or "").strip()
    if stderr:
        details.append(stderr)
    if stdout:
        details.append(stdout)
    return " | ".join(details) or fallback


def _prepare_vfs_file(vfs_path: str, vfs_size: str) -> None:
    path = Path(vfs_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["truncate", "-s", vfs_size, vfs_path],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Failed to prepare VFS file")


def _attach_loop_device(vfs_path: str) -> str:
    result = subprocess.run(
        ["losetup", "--find", "--show", vfs_path],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Failed to allocate loop device")
    loop_device = result.stdout.strip()
    if not loop_device:
        raise RuntimeError("Failed to allocate loop device")
    return loop_device


def _detach_loop_device(loop_device: str) -> None:
    subprocess.run(["losetup", "-d", loop_device], capture_output=True, text=True, timeout=600, check=False)


class LuksServiceMixin:
    def create_luks_block(self, user_id, tlog: TrustedLogAPI, record_id: str, passwd, vfs_size, vfs_path):
        _prepare_vfs_file(vfs_path, vfs_size)
        loop_device = _attach_loop_device(vfs_path)
        mapper_dir = secrets.token_hex(16)
        luks_cmd = ["curl", "-fsSL", KBS_URL+os.path.basename(passwd), "-o", passwd]
        res = subprocess.run(luks_cmd, capture_output=True, text=True, timeout=600)
        if res.returncode == 0 and os.path.exists(passwd):
            logger.info("Get luks-key success.")
        else:
            logger.info(" ".join(luks_cmd))
            error_message = _command_error_message(res, "Get luks-key failed")
            logger.error("Get luks-key failed. %s", error_message)
            _detach_loop_device(loop_device)
            raise RuntimeError(error_message)

        cmd = [str(SCRIPT_DIR / "create_encrypted_vfs.sh"), vfs_path, vfs_size, passwd, mapper_dir, loop_device]
        try:
            logger.info(' '.join(cmd))
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.stdout:
                logger.info(result.stdout)
            if result.returncode == 0:
                self.update_luks_status(user_id, "creating", step="create_encrypted_vfs: success", vfs_size=vfs_size, vfs_path=vfs_path, mapper_dir=mapper_dir, loop_device=loop_device)
                tlog.add_entry(record_id, Entry(key="create_encrypted_vfs", value="completed"))
                return mapper_dir, loop_device
            else:
                error_message = _command_error_message(result, "create_encrypted_vfs failed")
                logger.error("create_encrypted_vfs failed: %s", error_message)
                self.update_luks_status(user_id, "creating", step="create_encrypted_vfs: failed")
                tlog.add_entry(record_id, Entry(key="create_encrypted_vfs", value="failed"))
                raise RuntimeError(error_message)
        except Exception as exc:
            logger.debug("create luks failed: %s", exc)
            tlog.add_entry(record_id, Entry(key="create_luks_failed", value=str(exc)))
            _detach_loop_device(loop_device)
            raise

    def mount_luks_block(self, user_id, tlog: TrustedLogAPI, record_id: str, mapper_dir, passwd, mount_path, vfs_path, loop_device):
        loop_device = _attach_loop_device(vfs_path)
        cmd = ["bash", str(SCRIPT_DIR / "mount_encrypted_vfs.sh"), vfs_path, mount_path, mapper_dir, passwd, loop_device]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            logger.info(result.stdout)
            if result.returncode == 0:
                self.update_luks_status(user_id, "mounting", step="mount_encrypted_vfs: success", mount_path=mount_path, vfs_path=vfs_path, loop_device=loop_device)
                tlog.add_entry(record_id, Entry(key="mount_encrypted_vfs", value="completed"))
                return mount_path, loop_device
            else:
                logger.debug("mount_encrypted_vfs failed: %s", result.stderr or result.stdout)
                self.update_luks_status(user_id, "mounting", step="mount_encrypted_vfs: failed")
                tlog.add_entry(record_id, Entry(key="mount_encrypted_vfs", value="failed"))
                _detach_loop_device(loop_device)
                return
        except Exception as exc:
            logger.debug("mount luks failed: %s", exc)
            tlog.add_entry(record_id, Entry(key="mount_luks_failed", value=str(exc)))
            _detach_loop_device(loop_device)
            return

    def unmount_luks_block(self, user_id, tlog: TrustedLogAPI, record_id: str, mapper_dir, mount_path, loop_device):
        mapper_path = f"/dev/mapper/{mapper_dir}"
        cmd = ["bash", str(SCRIPT_DIR / "unmount_encrypted_vfs.sh"), mount_path, mapper_path, loop_device]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                logger.info(result.stdout)
                self.update_luks_status(user_id, "unmounting", step="unmount_encrypted_vfs: success")
                tlog.add_entry(record_id, Entry(key="unmount_encrypted_vfs", value="completed"))
            else:
                logger.debug("unmount_encrypted_vfs failed: %s", result.stderr or result.stdout)
                self.update_luks_status(user_id, "unmounting", step="unmount_encrypted_vfs: failed")
                tlog.add_entry(record_id, Entry(key="unmount_encrypted_vfs", value="failed"))
        except Exception as exc:
            logger.debug("unmount luks failed: %s", exc)
            tlog.add_entry(record_id, Entry(key="unmount_luks_failed", value=str(exc)))
            return

    def get_luks_status(self, user_id: str) -> Optional[LuksResult]:
        """Get LUKS status by user_id"""
        return self.luks.get(user_id)

    def update_luks_status(self, user_id: str, status: str, step: str = None, **kwargs):

        try:
            if user_id in self.luks:
                luks_result = self.luks[user_id]
                old_status = luks_result.status
                luks_result.status = status
                luks_result.updated_at = datetime.now()

                if step:
                    luks_result.step = step

                # Log status changes
                if old_status != status:
                    logger.info("LUKS %s status: %s -> %s", user_id, old_status, status)

                # Update additional fields
                for key, value in kwargs.items():
                    if hasattr(luks_result, key):
                        setattr(luks_result, key, value)
                        logger.debug(f"Updated {key} for build {user_id}")

                # Trigger cleanup for completed builds
                if status in ['success', 'failed'] and status != old_status:
                    # Clean up in background (keep logs for failed builds)
                    try:
                        keep_logs = (status == 'failed')
                        self.cleanup_build_artifacts('', keep_logs=keep_logs)
                    except Exception as e:
                        logger.warning(f"Cleanup failed for luks {user_id}: {e}")

            else:
                # Create new build result
                logger.info("Creating new LUKS status for %s: %s", user_id, status)
                self.luks[user_id] = LuksResult(
                    user_id=user_id,
                    status=status,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    **kwargs
                )

        except Exception as e:
            logger.error(f"Error updating luks status for {user_id}: {str(e)}")


__all__ = ['LuksServiceMixin']
