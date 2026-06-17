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

import hashlib
import json
import logging
import os
import re
import subprocess
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from ..config import (
    BUILD_DIR,
    DOCKER_CMD,
    KBS_FETCH_RETRIES,
    KBS_FETCH_RETRY_DELAY_SECONDS,
    KBS_URL,
)
from ..identity.oidc_preflight import inspect_identity_token
from ..identity.sigstore_identity import MissingSigstoreIdentityTokenError, resolve_sigstore_identity_token
from ..models import BuildResult, LaunchResult, LuksResult, PublishResult, TransparencyResult
from ..transparency.commit_client import TrustedLogAPI
from tlog.types import Entry

logger = logging.getLogger(__name__)


def _exception_message(error: BaseException) -> str:
    message = str(error).strip()
    if message:
        return message
    rendered = repr(error).strip()
    if rendered and rendered != f"{type(error).__name__}()":
        return rendered
    return type(error).__name__


class BaseDockerService:
    def __init__(self):
        self.builds: Dict[str, BuildResult] = {}
        self.launches: Dict[str, LaunchResult] = {}
        self.publish_results: Dict[str, PublishResult] = {}
        self.transparency_logs: Dict[str, TransparencyResult] = {}
        self.luks: Dict[str, LuksResult] = {}
        self.commit_errors: Dict[str, str] = {}
        self.pending_build_commits: Dict[str, Dict[str, str]] = {}
        self.pending_publish_commits: Dict[str, Dict[str, str]] = {}
        self.pending_launch_commits: Dict[str, Dict[str, str]] = {}

    def generate_uuid(self, prefix: str = "bld") -> str:
        """
        Generate a unique ID with specified prefix
        
        Args:
            prefix: Prefix for the ID ("bld" for build, "launch" for launch)
            
        Returns:
            str: Generated ID in format "{prefix}-{uuid}"
        """
        return f"{prefix}-{uuid.uuid4().hex[:7]}"

    def _syft_environment(self) -> Dict[str, str]:
        env = os.environ.copy()
        if env.get("DOCKER_API_VERSION"):
            return env

        try:
            result = subprocess.run(
                [DOCKER_CMD, "version", "--format", "{{.Server.MinAPIVersion}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                min_api_version = result.stdout.strip()
                if min_api_version:
                    env["DOCKER_API_VERSION"] = min_api_version
        except Exception:
            pass
        return env

    def _validate_public_encryption_key(self, public_key_path: str) -> Tuple[bool, str]:
        cmd = ["openssl", "pkey", "-pubin", "-in", public_key_path, "-noout"]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as exc:
            return False, f"OpenSSL key validation failed to run: {exc}"

        if result.returncode == 0:
            return True, result.stdout.strip() or "public key validated"

        failure_detail = result.stderr.strip() or result.stdout.strip() or "OpenSSL rejected the public key"
        return False, failure_detail

    def _derive_public_key_from_private_key(self, private_key_path: str, public_key_path: str) -> Tuple[bool, str]:
        cmd = ["openssl", "pkey", "-in", private_key_path, "-pubout", "-out", public_key_path]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as exc:
            return False, f"OpenSSL public key derivation failed to run: {exc}"

        if result.returncode == 0 and os.path.exists(public_key_path):
            return True, result.stdout.strip() or "public key derived"

        failure_detail = result.stderr.strip() or result.stdout.strip() or "OpenSSL failed to derive a public key"
        return False, failure_detail

    def _should_retry_kbs_download(self, failure_detail: str) -> bool:
        transient_markers = [
            "failed to connect",
            "connection refused",
            "connection reset",
            "timed out",
            "empty reply from server",
            "could not resolve host",
            "recv failure",
            "returned error: 502",
            "returned error: 503",
            "returned error: 504",
        ]
        lowered = failure_detail.lower()
        return any(marker in lowered for marker in transient_markers)

    def _download_kbs_artifact(self, url: str, destination_path: str) -> Tuple[bool, str]:
        cmd = ["curl", "-fsSL", url, "-o", destination_path]
        attempts = max(1, KBS_FETCH_RETRIES)

        for attempt in range(1, attempts + 1):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except Exception as exc:
                failure_detail = f"curl failed to run for {url}: {exc}"
            else:
                if result.returncode == 0 and os.path.exists(destination_path):
                    detail = result.stdout.strip() or f"downloaded {url}"
                    if attempt > 1:
                        detail = f"{detail} after {attempt} attempts"
                    return True, detail
                failure_detail = result.stderr.strip() or result.stdout.strip() or f"curl failed for {url}"

            if os.path.exists(destination_path):
                try:
                    os.remove(destination_path)
                except OSError:
                    pass

            is_last_attempt = attempt == attempts
            if is_last_attempt or not self._should_retry_kbs_download(failure_detail):
                if attempt > 1:
                    failure_detail = f"{failure_detail} after {attempt} attempts"
                return False, failure_detail

            logger.info(
                "KBS artifact fetch failed for %s (attempt %s/%s): %s. Retrying in %.1fs.",
                url,
                attempt,
                attempts,
                failure_detail,
                KBS_FETCH_RETRY_DELAY_SECONDS,
            )
            time.sleep(KBS_FETCH_RETRY_DELAY_SECONDS)

    def _download_first_available_kbs_artifact(self, destination_path: str, candidate_names: list[str]) -> Tuple[bool, Optional[str], str]:
        attempts = []
        for candidate_name in candidate_names:
            ok, detail = self._download_kbs_artifact(f"{KBS_URL}{candidate_name}", destination_path)
            if ok:
                return True, candidate_name, detail
            attempts.append(f"{candidate_name}: {detail}")
        return False, None, "; ".join(attempts)

    def _sha384_digest(self, payload: str) -> str:
        return "sha384:" + hashlib.sha384(payload.encode("utf-8")).hexdigest()

    def local_build_image_ref(self, build_id: str) -> str:
        safe_build_id = re.sub(r"[^a-z0-9._-]+", "-", build_id.lower()).strip(".-")
        if not safe_build_id:
            safe_build_id = "build"
        return f"tc-api-build-{safe_build_id}:latest"

    def _json_sha384_digest(self, payload: Any) -> str:
        return self._sha384_digest(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))

    def add_tlog_entries(self, tlog: TrustedLogAPI, record_id: str, entries) -> None:
        for entry in entries:
            tlog.add_entry(record_id, entry)

    def _file_sha384_digest(self, file_path: str) -> str:
        with open(file_path, "rb") as handle:
            return "sha384:" + hashlib.sha384(handle.read()).hexdigest()

    def _directory_sha384_digest(self, directory: str) -> str:
        digest = hashlib.sha384()
        for root, _, files in os.walk(directory):
            for file_name in sorted(files):
                file_path = os.path.join(root, file_name)
                rel_path = os.path.relpath(file_path, directory)
                digest.update(rel_path.encode("utf-8"))
                with open(file_path, "rb") as handle:
                    digest.update(handle.read())
        return "sha384:" + digest.hexdigest()

    def _build_status_path(self, build_id: str, luks_path: str) -> str:
        if luks_path:
            if os.path.exists(luks_path):
                return os.path.join(luks_path, build_id, "build-status.json")
            else:
                return os.path.join(BUILD_DIR, build_id, "build-status.json")
        else:
            return os.path.join(BUILD_DIR, build_id, "build-status.json")

    def _persist_build_status(self, build_result: BuildResult) -> None:
        if os.path.exists(build_result.luks_path):
            build_path = os.path.join(build_result.luks_path, build_result.build_id)
        else:
            build_path = os.path.join(BUILD_DIR, build_result.build_id)
        os.makedirs(build_path, exist_ok=True)
        status_path = self._build_status_path(build_result.build_id, build_result.luks_path)
        with open(status_path, "w", encoding="utf-8") as handle:
            json.dump(build_result.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)

    def _load_persisted_build_status(self, build_id: str, luks_path: str) -> Optional[BuildResult]:
        status_path = self._build_status_path(build_id, luks_path)
        if not os.path.exists(status_path):
            return None
        try:
            with open(status_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return BuildResult.model_validate(payload)
        except Exception as exc:
            logger.warning("Failed to load persisted build status for %s: %s", build_id, exc)
            return None

    def _recover_legacy_build_status(self, build_id: str, luks_path: str = '') -> Optional[BuildResult]:
        if os.path.exists(luks_path):
            build_path = os.path.join(luks_path, build_id)
        else:
            build_path = os.path.join(BUILD_DIR, build_id)
        if not os.path.isdir(build_path):
            return None

        created_epoch = os.path.getmtime(build_path)
        created_at = datetime.fromtimestamp(created_epoch)
        image_id = None
        candidate_dirs = []
        for entry in sorted(os.listdir(build_path)):
            entry_path = os.path.join(build_path, entry)
            if not os.path.isdir(entry_path):
                continue
            if os.path.exists(os.path.join(entry_path, "index.json")) and os.path.exists(os.path.join(entry_path, "oci-layout")):
                candidate_dirs.append(entry_path)

        if os.path.isdir(os.path.join(build_path, "plain")):
            image_id = f"oci:{os.path.join(build_path, 'plain')}"
        elif candidate_dirs:
            image_id = f"oci:{candidate_dirs[0]}"

        sbom_url = None
        for entry in sorted(os.listdir(build_path)):
            if entry.endswith("-sbom.json"):
                sbom_url = os.path.join(build_path, entry)
                break

        status = "success"
        current_step = "Build completed successfully"
        error_message = None
        transparency_verify = None
        log_id = None

        receipt_path = os.path.join(build_path, "build-commit-receipt.json")
        if os.path.exists(receipt_path):
            try:
                with open(receipt_path, "r", encoding="utf-8") as handle:
                    receipt = json.load(handle)
                log_id = receipt.get("record_id")
                transparency_verify = "pending"
            except Exception:
                pass

        error_logs = [entry for entry in os.listdir(build_path) if entry.endswith("-error.log")]
        if error_logs:
            status = "failed"
            current_step = "Build failed"
            error_message = f"Recovered from {error_logs[0]}"

        if image_id is None and status == "success":
            status = "failed"
            current_step = "Build artifact missing"
            error_message = "Recovered build directory does not contain an OCI artifact"

        return BuildResult(
            user_id="",
            build_id=build_id,
            status=status,
            current_step=current_step,
            image_id=image_id,
            image_url=image_id,
            sbom_url=sbom_url,
            log_id=log_id,
            luks_path=luks_path,
            transparencyLog_verify=transparency_verify,
            error_message=error_message,
            created_at=created_at,
            updated_at=created_at,
        )

    def get_build_status(self, build_id: str, luks_path: str) -> Optional[BuildResult]:
        """Get build status by build_id"""
        build_result = self.builds.get(build_id)
        if build_result is not None:
            return build_result

        build_result = self._load_persisted_build_status(build_id, luks_path)
        if build_result is not None:
            self.builds[build_id] = build_result
            return build_result

        build_result = self._recover_legacy_build_status(build_id, luks_path)
        if build_result is not None:
            self.builds[build_id] = build_result
            try:
                self._persist_build_status(build_result)
            except Exception as exc:
                logger.warning("Failed to persist recovered build status for %s: %s", build_id, exc)
            return build_result
        return None

    def update_build_status(self,user_id: str, build_id: str, status: str, luks_path: str = '', step: str = None, **kwargs):
        """
        Update build status with enhanced tracking and step information
        
        Status can be one of:
        - submitted: Initial build request received
        - preparing: Setting up build environment
        - building: Building container image
        - generating_sbom: Generating SBOM
        - encrypting: Encrypting image (if requested)
        - pushing: Pushing to registry
        - signing: Signing image and SBOM
        - success: Build completed successfully
        - failed: Build failed
        """
        try:
            if build_id in self.builds:
                build_result = self.builds[build_id]
                old_status = build_result.status
                build_result.status = status
                build_result.updated_at = datetime.now()
                
                if step:
                    build_result.current_step = step
                
                # Log status changes
                if old_status != status:
                    logger.info(f"Build {build_id} status: {old_status} -> {status}")
                
                # Update additional fields
                for key, value in kwargs.items():
                    if hasattr(build_result, key):
                        setattr(build_result, key, value)
                        logger.debug(f"Updated {key} for build {build_id}")
                
                # Successful builds must keep OCI artifacts available for later publish/deploy.
                if status == 'failed' and status != old_status:
                    try:
                        self.cleanup_build_artifacts(build_id, luks_path, keep_logs=True)
                    except Exception as e:
                        logger.warning(f"Cleanup failed for build {build_id}: {e}")
                self._persist_build_status(build_result)
                        
            else:
                # Create new build result
                logger.info(f"Creating new build status for {build_id}: {status}")
                self.builds[build_id] = BuildResult(
                    user_id=user_id,
                    build_id=build_id,
                    status=status,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    luks_path=luks_path,
                    **kwargs
                )
                self._persist_build_status(self.builds[build_id])
                
        except Exception as e:
            logger.error(f"Error updating build status for {build_id}: {str(e)}")

    def cleanup_build_artifacts(self, build_id: str, luks_path: str, keep_logs: bool = True) -> bool:
        """Clean up temporary build artifacts to save disk space"""
        try:
            if luks_path:
                if os.path.exists(luks_path):
                    build_path = os.path.join(luks_path, build_id)
                else:
                    build_path = os.path.join(BUILD_DIR, build_id)
                    logger.info(f"NOW not in luks files.")
            else:
                build_path = os.path.join(BUILD_DIR, build_id)
                logger.info(f"NOW not in luks files.")
            
            if not os.path.exists(build_path):
                logger.warning(f"Build directory not found: {build_path}")
                return True
            
            logger.info(f"Cleaning up build artifacts for: {build_id}")
            
            # List of files/directories to clean up
            cleanup_items = [
                "encryption",  # Encryption working directory
                "plain",       # OCI plain format (if using old method)
                "encrypted",   # OCI encrypted format (if using old method)
            ]
            
            # Optionally keep logs
            if not keep_logs:
                cleanup_items.extend([
                    f"{build_id}-build.log",
                    f"{build_id}-error.log"
                ])
            
            for item in cleanup_items:
                item_path = os.path.join(build_path, item)
                try:
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                        logger.debug(f"Removed file: {item}")
                    elif os.path.isdir(item_path):
                        import shutil
                        shutil.rmtree(item_path)
                        logger.debug(f"Removed directory: {item}")
                except Exception as e:
                    logger.warning(f"Failed to remove {item}: {e}")
            
            logger.info(f"Cleanup completed for build: {build_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            return False

    def get_image_info(self, image_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a Docker image"""
        try:
            cmd = [DOCKER_CMD, "inspect", image_name]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                import json
                image_info = json.loads(result.stdout)[0]
                
                # Extract useful information
                info = {
                    "id": image_info.get("Id", ""),
                    "created": image_info.get("Created", ""),
                    "size": image_info.get("Size", 0),
                    "architecture": image_info.get("Architecture", ""),
                    "os": image_info.get("Os", ""),
                    "config": {
                        "env": image_info.get("Config", {}).get("Env", []),
                        "cmd": image_info.get("Config", {}).get("Cmd", []),
                        "exposed_ports": list(image_info.get("Config", {}).get("ExposedPorts", {}).keys())
                    }
                }
                
                return info
            else:
                logger.error(f"Failed to inspect image {image_name}: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"Image inspection timed out: {image_name}")
            return None
        except Exception as e:
            logger.error(f"Error inspecting image: {str(e)}")
            return None

    def get_pubKey_from_KBS(self, luks_path: str = '', tlog: TrustedLogAPI = None, record_id: str = None):
        try:
            if luks_path:
                if os.path.exists(luks_path):
                    kbs_key_dir = os.path.join(luks_path, "_kbs_keys", record_id or uuid.uuid4().hex[:8])
                else:
                    kbs_key_dir = os.path.join(BUILD_DIR, "_kbs_keys", record_id or uuid.uuid4().hex[:8])
                    logger.info("NOW get pubkey not in luks file.")
            else:
                kbs_key_dir = os.path.join(BUILD_DIR, "_kbs_keys", record_id or uuid.uuid4().hex[:8])
                logger.info("NOW get pubkey not in luks file.")
            os.makedirs(kbs_key_dir, exist_ok=True)

            key_dict = {
                "opensslKey": os.path.join(kbs_key_dir, "openssl.key"),
                "cosignKey": os.path.join(kbs_key_dir, "cosign.key"),
                "opensslPub": os.path.join(kbs_key_dir, "openssl.pub"),
                "cosignPub": os.path.join(kbs_key_dir, "cosign.pub"),
            }

            openssl_key_ok, openssl_key_source, openssl_key_detail = self._download_first_available_kbs_artifact(
                key_dict["opensslKey"],
                ["openssl.key", "key.pem"],
            )
            cosign_key_ok, cosign_key_source, cosign_key_detail = self._download_first_available_kbs_artifact(
                key_dict["cosignKey"],
                ["cosign.key"],
            )
            cosign_pub_ok, cosign_pub_source, cosign_pub_detail = self._download_first_available_kbs_artifact(
                key_dict["cosignPub"],
                ["cosign.pub"],
            )

            openssl_pub_ok, openssl_pub_source, openssl_pub_detail = self._download_first_available_kbs_artifact(
                key_dict["opensslPub"],
                ["openssl.pub", "pub.pem"],
            )
            if openssl_pub_ok:
                key_valid, key_validation_detail = self._validate_public_encryption_key(key_dict["opensslPub"])
                if not key_valid:
                    logger.warning(
                        "Downloaded KBS public key %s failed validation: %s. Will try deriving from private key.",
                        openssl_pub_source,
                        key_validation_detail,
                    )
                    openssl_pub_ok = False
                    openssl_pub_detail = key_validation_detail

            if not openssl_pub_ok and openssl_key_ok:
                derived, derive_detail = self._derive_public_key_from_private_key(
                    key_dict["opensslKey"],
                    key_dict["opensslPub"],
                )
                if derived:
                    openssl_pub_ok = True
                    openssl_pub_source = f"derived-from:{openssl_key_source}"
                    openssl_pub_detail = derive_detail
                else:
                    openssl_pub_detail = f"{openssl_pub_detail}; {derive_detail}" if openssl_pub_detail else derive_detail

            required_failures = []
            if not openssl_key_ok:
                required_failures.append(f"opensslKey: {openssl_key_detail}")
            if not cosign_key_ok:
                required_failures.append(f"cosignKey: {cosign_key_detail}")
            if not openssl_pub_ok:
                required_failures.append(f"opensslPub: {openssl_pub_detail}")

            if required_failures:
                failure_detail = "; ".join(required_failures)
                logger.error("Failed to retrieve valid keys from KBS: %s", failure_detail)
                if tlog and record_id:
                    tlog.add_entry(record_id, Entry(key="get_key", value={"status": "failed", "error": failure_detail}))
                return False, None

            key_dict = {key: os.path.realpath(value) for key, value in key_dict.items() if os.path.exists(value)}
            logger.info(
                "Retrieved KBS keys: opensslKey=%s opensslPub=%s cosignKey=%s cosignPub=%s",
                openssl_key_source,
                openssl_pub_source,
                cosign_key_source,
                cosign_pub_source,
            )
            if tlog and record_id:
                tlog.add_entry(
                    record_id,
                    Entry(
                        key="key",
                        value={
                            **key_dict,
                            "sources": {
                                "opensslKey": openssl_key_source,
                                "opensslPub": openssl_pub_source,
                                "cosignKey": cosign_key_source,
                                "cosignPub": cosign_pub_source,
                            },
                        },
                    ),
                )
            return 'trusted', key_dict

        except Exception as e:
            logger.error(f"Get Keys failed: {str(e)}")
            if tlog and record_id:
                tlog.add_entry(record_id, Entry(key="key", value=f"Get key failed: {e}"))
            return False, None

    def commit_and_save_receipt(
        self,
        api_type,
        build_id,
        tlog: TrustedLogAPI,
        record_id: str,
        identity_token_str: str,
        luks_path: str = '',
        expected_identity: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ):
        """Commit the accumulated entries via TrustedLogAPI and save a receipt file."""
        commit_error_key = self._commit_error_key(api_type, build_id, record_id)
        self.commit_errors.pop(commit_error_key, None)
        try:
            identity_token_str = self._resolve_commit_identity_token(api_type,identity_token_str,expected_identity=expected_identity)
            result = tlog.commit_record(
                record_id=record_id,
                event_type=api_type,
                commit_options={
                    "identity_token": identity_token_str,
                    "idempotency_key": idempotency_key,
                },
            )
            receipt = {
                "record_id": result.record_id,
                "event_id": result.event_id,
                "queue_status": result.queue_status.value if result.queue_status else None,
                "mr_value": result.mr_value,
            }
            if luks_path:
                if os.path.exists(luks_path):
                    receipt_path = os.path.join(luks_path, build_id, f"{api_type}-commit-receipt.json")
                else:
                    receipt_path = os.path.join(BUILD_DIR, build_id, f"{api_type}-commit-receipt.json")
                    logger.info("NOW receipt file not in luks file.")
            else:
                receipt_path = os.path.join(BUILD_DIR, build_id, f"{api_type}-commit-receipt.json")
                logger.info("NOW receipt file not in luks file.")
            os.makedirs(os.path.dirname(receipt_path), exist_ok=True)
            with open(receipt_path, "w", encoding="utf-8") as f:
                json.dump(receipt, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved {api_type} commit receipt to {receipt_path}")
            return True, result.record_id
        except Exception as e:
            error_message = self._describe_commit_failure(
                api_type,
                e,
                identity_token_str=identity_token_str,
                expected_identity=expected_identity,
            )
            self.commit_errors[commit_error_key] = error_message
            logger.error("Commit failed for %s: %s", api_type, error_message)
            return False, None

    def _describe_commit_failure(
        self,
        operation: str,
        error: BaseException,
        *,
        identity_token_str: Optional[str],
        expected_identity: Optional[str],
    ) -> str:
        if isinstance(error, MissingSigstoreIdentityTokenError):
            return str(error)

        error_message = _exception_message(error)
        token = (identity_token_str or "").strip()
        if not token:
            return error_message

        try:
            token_report = inspect_identity_token(token, expected_identity=expected_identity)
        except Exception:
            token_report = None

        token_errors = token_report.get("errors") or [] if token_report else []
        if token_errors:
            combined_errors = "; ".join(str(item) for item in token_errors)
            lower_errors = combined_errors.lower()
            if (
                "expired" in lower_errors
                or "not within its validity period" in lower_errors
                or "not valid for sigstore" in lower_errors
            ):
                return str(
                    MissingSigstoreIdentityTokenError(
                        operation,
                        message=(
                            f"Sigstore identity token is required for {operation}. The previously supplied token expired or "
                            f"could not be used for signing in the current tc_api process. Defer login to the client-side "
                            f"challenge flow and retry with a fresh identity_token."
                        ),
                    )
                )
            if error_message in {type(error).__name__, type(error).__name__ + "()"}:
                return f"Sigstore identity token for {operation} is invalid for commit: {combined_errors}"

        return error_message

    def _commit_error_key(self, api_type: str, build_id: str, record_id: str) -> str:
        return f"{api_type}:{build_id or record_id}"

    def get_commit_error(self, api_type: str, build_id: str, record_id: Optional[str] = None) -> Optional[str]:
        if build_id:
            error = self.commit_errors.get(f"{api_type}:{build_id}")
            if error:
                return error
        if record_id:
            return self.commit_errors.get(f"{api_type}:{record_id}")
        return None

    def register_pending_build_commit(self, build_id: str, record_id: str, user_id: str, luks_path: str = "") -> None:
        self.pending_build_commits[build_id] = {
            "record_id": record_id,
            "user_id": user_id,
            "luks_path": luks_path or "",
        }

    def get_pending_build_commit(self, build_id: str) -> Optional[Dict[str, str]]:
        return self.pending_build_commits.get(build_id)

    def clear_pending_build_commit(self, build_id: str) -> None:
        self.pending_build_commits.pop(build_id, None)

    def register_pending_publish_commit(
        self,
        build_id: str,
        record_id: str,
        user_id: str,
        luks_path: str = "",
        idempotency_key: str = "",
    ) -> None:
        self.pending_publish_commits[build_id] = {
            "record_id": record_id,
            "user_id": user_id,
            "luks_path": luks_path or "",
            "idempotency_key": idempotency_key or "",
        }

    def get_pending_publish_commit(self, build_id: str) -> Optional[Dict[str, str]]:
        return self.pending_publish_commits.get(build_id)

    def clear_pending_publish_commit(self, build_id: str) -> None:
        self.pending_publish_commits.pop(build_id, None)

    def register_pending_launch_commit(self, launch_id: str, record_id: str, user_id: str, chain_id: str) -> None:
        self.pending_launch_commits[launch_id] = {
            "record_id": record_id,
            "user_id": user_id,
            "chain_id": chain_id,
        }

    def get_pending_launch_commit(self, launch_id: str) -> Optional[Dict[str, str]]:
        return self.pending_launch_commits.get(launch_id)

    def clear_pending_launch_commit(self, launch_id: str) -> None:
        self.pending_launch_commits.pop(launch_id, None)

    def _resolve_commit_identity_token(
            self,
            operation: str,
            identity_token_str: Optional[str],
            expected_identity: Optional[str] = None,
        ) -> str:
            """Prefer a fresh cached token for commit, but never switch caller identity."""
            explicit_token = (identity_token_str or "").strip()
            cached_token = resolve_sigstore_identity_token(
                operation,
                allow_interactive=True,
                require_token=not bool(explicit_token),
            )
            candidates = []
            if cached_token:
                candidates.append(("cached", cached_token))
            if explicit_token and explicit_token != cached_token:
                candidates.append(("request", explicit_token))

            if not candidates:
                raise MissingSigstoreIdentityTokenError(operation)

            invalid_reasons = []
            refreshable_token_failure = False
            for source, candidate_token in candidates:
                token_report = inspect_identity_token(candidate_token, expected_identity=expected_identity)
                errors = token_report.get("errors") or []
                if token_report.get("valid_for_sigstore") and not errors:
                    if source == "cached" and explicit_token and cached_token != explicit_token:
                        logger.info("Using refreshed cached Sigstore token for %s commit", operation)
                    return candidate_token

                reason = "; ".join(str(error) for error in errors) or "token is not valid for Sigstore"
                invalid_reasons.append(f"{source} token: {reason}")
                if "Token has already expired." in reason or "no interactive terminal is available" in reason:
                    refreshable_token_failure = True
                logger.warning("Ignoring %s Sigstore token for %s commit: %s", source, operation, reason)

            if refreshable_token_failure:
                raise MissingSigstoreIdentityTokenError(
                    operation,
                    message=(
                        f"Sigstore identity token is required for {operation}. The previously supplied token expired or "
                        f"could not be refreshed in the current tc_api process. Defer login to the client-side challenge "
                        f"flow and retry with a fresh identity_token."
                    ),
                )

            raise ValueError(
                f"Sigstore identity token for {operation} is invalid for commit: "
                + " | ".join(invalid_reasons)
            )

    def verify_chain_state(self, api_type, tlog: TrustedLogAPI, chain_id: str = "default"):
        """Lightweight verification: query TruCon chain-state and check head."""
        logger.info("Verifying chain state via TruCon...")
        try:
            from ..trucon.internal_transport import request_json

            data = request_json(
                "GET",
                "/chain-state",
                caller_service="tc_api",
                timeout=10,
                trucon_url=tlog._trucon_url,
            )
            if data.get("head_record_id"):
                logger.info(f"Chain '{chain_id}' head at record {data['head_record_id']}, seq={data.get('sequence_num')}")
                return "success"
            else:
                logger.warning(f"Chain '{chain_id}' has no head record yet")
                return "pending"
        except Exception as e:
            logger.warning(f"TruCon chain-state query failed: {e}")
            return "degraded"

    async def get_summaryTransparencylog(self, build_id, launch_id):
        """"
        get all transparency log
        """
        try:
            build_path = os.path.join(BUILD_DIR, build_id)
            logger.info(f"Get build_path: {build_path}")
            launch_path = os.path.join(BUILD_DIR, launch_id)
            logger.info(f"Get launch_path: {launch_path}")
            
            def get_log(path,api):
                try:
                    logid = ''
                    content = ''
                    for i in [os.path.join(j) for j in os.listdir(path) if j.startswith(api)]:
                        if f"{api}-transparency_log" in i:
                            logid = i.split("-")[-1][:9]
                            logger.info(f"Get {api}_logId: {api}_{logid}")

                        if f"{api}-transparency.json" == i:
                            log_path = os.path.join(path,i)
                            logger.info(f"Get {api}_log for: {i}")
                            with open(log_path, 'r', encoding='utf-8') as f:
                                content = json.load(f)
                            if not content:
                                logger.error(f"get {api}-transparency log failed")
                    
                    if (not logid) or (not content):
                        logger.debug("Get transparency log failed.")
                        return None, None
                    else:
                        return logid, content
                
                except Exception as e:
                    logger.debug(f"Get transparency log failed. {e}")
                    return None, None

            # get build transparency log
            #build_log = [os.path.join(i) for i in os.listdir(build_path) if i.startswith('build')]
            build_logId, build_content = get_log(build_path,"build")
            #publish_log = [os.path.join(i) for i in os.listdir(build_path) if i.startswith('publish')]
            publish_logId, publish_content = get_log(build_path,"publish")
            #launch_log = [os.path.join(i) for i in os.listdir(launch_path) if i.startswith('launch')]
            launch_logId, launch_content = get_log(launch_path,"launch")
            
            # get log id
            logids = {"build": build_logId,
                      "publish": publish_logId,
                      "launch": launch_logId
                      }

            summary = {"build": f"{json.dumps(build_content,indent=2)}",
                       "publish": f"{json.dumps(publish_content,indent=2)}",
                       "launch": f"{json.dumps(launch_content,indent=2)}"
                       }
            #logger.info(f"Workflow transparency log: {json.dumps(summary, indent=2)}")
            response = {"build_id": build_id, "launch_id": launch_id, "log_id": logids, "transparencylog": summary}

            #logger.info(f"Workflow transparency log: {json.dumps(response, indent=2)}")
            return response
        except Exception as e:
            logger.error(f"Get Workflow transparency log failed")
            return None


__all__ = ['BaseDockerService']
