import logging
import random
import subprocess
from datetime import datetime
from typing import Optional

from ..models import LuksResult
from ..transparency.commit_client import TrustedLogAPI
from tlog.types import Entry

logger = logging.getLogger(__name__)


class LuksServiceMixin:
    def create_luks_block(self, user_id, tlog: TrustedLogAPI, record_id: str, passwd, vfs_size, vfs_path):
        loop_device = subprocess.run(["losetup", "-f"], capture_output=True, text=True, timeout=600).stdout.strip()
        mapper_dir = f"{random.randint(0, 32767)}{random.randint(0, 32767)}{random.randint(0, 32767)}{random.randint(0, 32767)}"
        cmd = ["./scripts/create_encrypted_vfs.sh", vfs_path, vfs_size, passwd, mapper_dir, loop_device]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            logger.info(result.stdout)
            if result.returncode == 0:
                self.update_luks_status(user_id, "creating", step="create_encrypted_vfs: success", passwd=passwd, vfs_size=vfs_size, vfs_path=vfs_path, mapper_dir=mapper_dir, loop_device=loop_device)
                tlog.add_entry(record_id, Entry(key="create_encrypted_vfs", value="completed"))
                return mapper_dir, loop_device
            else:
                logger.debug("create_encrypted_vfs failed: %s", result.stderr or result.stdout)
                self.update_luks_status(user_id, "creating", step="create_encrypted_vfs: failed")
                tlog.add_entry(record_id, Entry(key="create_encrypted_vfs", value="failed"))
                return
        except Exception as exc:
            logger.debug("create luks failed: %s", exc)
            tlog.add_entry(record_id, Entry(key="create_luks_failed", value=str(exc)))
            return

    def mount_luks_block(self, user_id, tlog: TrustedLogAPI, record_id: str, mapper_dir, passwd, mount_path, vfs_path, loop_device):
        cmd = ["./scripts/mount_encrypted_vfs.sh", vfs_path, mount_path, mapper_dir, passwd, loop_device]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            logger.info(result.stdout)
            if result.returncode == 0:
                self.update_luks_status(user_id, "mounting", step="mount_encrypted_vfs: success", mount_path=mount_path, vfs_path=vfs_path)
                tlog.add_entry(record_id, Entry(key="mount_encrypted_vfs", value="completed"))
                return mount_path
            else:
                logger.debug("mount_encrypted_vfs failed: %s", result.stderr or result.stdout)
                self.update_luks_status(user_id, "mounting", step="mount_encrypted_vfs: failed")
                tlog.add_entry(record_id, Entry(key="mount_encrypted_vfs", value="failed"))
                return
        except Exception as exc:
            logger.debug("mount luks failed: %s", exc)
            tlog.add_entry(record_id, Entry(key="mount_luks_failed", value=str(exc)))
            return

    def unmount_luks_block(self, user_id, tlog: TrustedLogAPI, record_id: str, mapper_dir, mount_path, loop_device):
        mapper_path = f"/dev/mapper/{mapper_dir}"
        cmd = ["./scripts/unmount_encrypted_vfs.sh", mount_path, mapper_path, loop_device]
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
