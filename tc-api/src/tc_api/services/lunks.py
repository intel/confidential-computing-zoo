from ._shared import *


class LunksServiceMixin:
    def create_lunks_block(self, user_id, tlog: TrustedLogAPI, record_id: str, passwd, VFS_SIZE, VFS_PATH):
        LOOP_DEVICE = subprocess.run(['losetup', '-f'], capture_output=True, text=True, timeout=600).stdout.strip()
        MAPPER_DIR = f"{random.randint(0, 32767)}{random.randint(0, 32767)}{random.randint(0, 32767)}{random.randint(0, 32767)}"
        cmd = "./scripts/create_encrypted_vfs.sh "+VFS_PATH+" "+VFS_SIZE+" "+passwd+" "+MAPPER_DIR+" "+LOOP_DEVICE
        try:
            result = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,text=True)
            logger.info(result.stdout.read())
            if result.wait() == 0:
                logger.info(result.stdout.read())
                self.update_lunks_status(user_id, "creating", step="create_encrypted_vfs: success",passwd=passwd,vfs_size=VFS_SIZE,vfs_path=VFS_PATH,mapper_dir=MAPPER_DIR,loop_device=LOOP_DEVICE)
                tlog.add_entry(record_id, Entry(key="create_encrypted_vfs", value="completed"))
                return MAPPER_DIR,LOOP_DEVICE
            else:
                logger.debug(f"create_encrypted_vfs failed: {cmd}")
                self.update_lunks_status(user_id, "creating", step="create_encrypted_vfs: failed")
                tlog.add_entry(record_id, Entry(key="createLunks", value="create_encrypted_vfs failed"))
                return
        except Exception as e:
            logger.debug(f"crate lunks failed.{e}")
            tlog.add_entry(record_id, Entry(key="create_lunks_failed", value=f"e"))
            return

    def mount_lunks_block(self, user_id, tlog: TrustedLogAPI, record_id: str, MAPPER_DIR, passwd, MOUNT_PATH, VFS_PATH,LOOP_DEVICE):
        cmd = "./scripts/mount_encrypted_vfs.sh "+VFS_PATH+" "+MOUNT_PATH+" "+MAPPER_DIR+" "+passwd+" "+LOOP_DEVICE
        try:
            result = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,text=True)
            logger.info(result.stdout.read())
            if result.wait() == 0:
                logger.info(result.stdout.read())
                self.update_lunks_status(user_id, "mounting", step="mount_encrypted_vfs: success",mount_path=MOUNT_PATH,vfs_path=VFS_PATH)
                tlog.add_entry(record_id, Entry(key="mount_encrypted_vfs", value="completed"))
                return MOUNT_PATH
            else:
                logger.debug(f"mount_encrypted_vfs failed: {cmd}")
                self.update_lunks_status(user_id, "mounting", step="mount_encrypted_vfs: failed")
                tlog.add_entry(record_id, Entry(key="mountLunks", value="mount_encrypted_vfs failed"))
                return
        except Exception as e:
            logger.debug(f"mount lunks failed.{e}")
            tlog.add_entry(record_id, Entry(key="mount_lunks_failed", value=f"e"))
            return

    def unmount_lunks_block(self, user_id, tlog: TrustedLogAPI, record_id: str, MAPPER_DIR, MOUNT_PATH, LOOP_DEVICE):
        MAPPER_PATH=f'/dev/mapper/{MAPPER_DIR}'
        cmd = "./scripts/unmount_encrypted_vfs.sh "+" "+MOUNT_PATH+" "+MAPPER_PATH+" "+LOOP_DEVICE
        try:
            result = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,text=True)
            if result.wait() == 0:
                logger.info(result.stdout.read())
                self.update_lunks_status(user_id, "umounting", step="unmount_encrypted_vfs: success")
                tlog.add_entry(record_id, Entry(key="unmount_encrypted_vfs", value="completed"))
            else:
                logger.debug(f"unmount_encrypted_vfs failed: {cmd}")
                self.update_lunks_status(user_id, "umounting", step="unmount_encrypted_vfs: failed")
                tlog.add_entry(record_id, Entry(key="unmountLunks", value="unmount_encrypted_vfs failed"))
        except Exception as e:
            logger.debug(f"unmount lunks failed.{e}")
            tlog.add_entry(record_id, Entry(key="unmount_lunks_failed", value=f"e"))
            return

    def get_lunks_status(self, user_id: str) -> Optional[LunksResult]:
        """Get lunks status by user_id"""
        return self.lunks.get(user_id)

    def update_lunks_status(self,user_id: str, status: str, step: str = None, **kwargs):

        try:
            if user_id in self.lunks:
                lunks_result = self.lunks[user_id]
                old_status = lunks_result.status
                lunks_result.status = status
                lunks_result.updated_at = datetime.now()

                if step:
                    lunks_result.step = step

                # Log status changes
                if old_status != status:
                    logger.info(f"Lunks {user_id} status: {old_status} -> {status}")

                # Update additional fields
                for key, value in kwargs.items():
                    if hasattr(lunks_result, key):
                        setattr(lunks_result, key, value)
                        logger.debug(f"Updated {key} for build {user_id}")

                # Trigger cleanup for completed builds
                if status in ['success', 'failed'] and status != old_status:
                    # Clean up in background (keep logs for failed builds)
                    try:
                        keep_logs = (status == 'failed')
                        self.cleanup_build_artifacts('', keep_logs=keep_logs)
                    except Exception as e:
                        logger.warning(f"Cleanup failed for lunks {user_id}: {e}")

            else:
                # Create new build result
                logger.info(f"Creating new lunks status for {user_id}: {status}")
                self.lunks[user_id] = LunksResult(
                    user_id=user_id,
                    status=status,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    **kwargs
                )

        except Exception as e:
            logger.error(f"Error updating lunks status for {user_id}: {str(e)}")


__all__ = ['LunksServiceMixin']
