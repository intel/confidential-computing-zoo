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

import base64
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from threading import Lock
from typing import Optional

from sigstore.oidc import IdentityToken, Issuer


SIGSTORE_IDENTITY_TOKEN_ENV = "TC_API_REAL_REKOR_IDENTITY_TOKEN"
SIGSTORE_IDENTITY_TOKEN_CACHE_ENV = "TC_API_REAL_REKOR_IDENTITY_TOKEN_CACHE"
SIGSTORE_IDENTITY_TOKEN_MIN_TTL_ENV = "TC_API_REAL_REKOR_IDENTITY_TOKEN_MIN_TTL"
SIGSTORE_INTERACTIVE_LOGIN_ENV = "TC_API_SIGSTORE_INTERACTIVE_LOGIN"

DEFAULT_MIN_TTL_SECONDS = 15
DEFAULT_CACHE_PATH = (
    Path("/dev/shm/tc_api_sigstore_identity_token.json")
    if Path("/dev/shm").exists()
    else Path(tempfile.gettempdir()) / "tc_api_sigstore_identity_token.json"
)

_CACHE_LOCK = Lock()
_MEMORY_TOKEN: Optional[str] = None
_MEMORY_EXPIRY: Optional[int] = None


class MissingSigstoreIdentityTokenError(RuntimeError):
    def __init__(self, operation: str, message: Optional[str] = None):
        super().__init__(
            message
            or (
                f"Sigstore identity token is required for {operation}. Provide identity_token in the request, "
                f"set {SIGSTORE_IDENTITY_TOKEN_ENV}, pre-populate {_cache_path()}, or enable "
                f"{SIGSTORE_INTERACTIVE_LOGIN_ENV} for interactive refresh."
            )
        )
        self.operation = operation


def _get_logger(logger: Optional[logging.Logger]) -> logging.Logger:
    return logger or logging.getLogger(__name__)


def _parse_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _has_interactive_stdio() -> bool:
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except Exception:
        return False


def _cache_path() -> Path:
    raw_path = os.environ.get(SIGSTORE_IDENTITY_TOKEN_CACHE_ENV, "").strip()
    if raw_path:
        return Path(raw_path)
    return DEFAULT_CACHE_PATH


def _min_ttl_seconds() -> int:
    raw_value = os.environ.get(SIGSTORE_IDENTITY_TOKEN_MIN_TTL_ENV, "").strip()
    if not raw_value:
        return DEFAULT_MIN_TTL_SECONDS
    try:
        return max(0, int(raw_value))
    except ValueError:
        return DEFAULT_MIN_TTL_SECONDS


def _decode_payload(token: str) -> Optional[dict]:
    parts = token.split(".")
    if len(parts) < 2:
        return None

    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload + padding)
        return json.loads(decoded.decode("utf-8"))
    except Exception:
        return None


def token_expiry_epoch(token: str) -> Optional[int]:
    payload = _decode_payload(token)
    if not payload:
        return None
    exp = payload.get("exp")
    if exp is None:
        return None
    try:
        return int(exp)
    except (TypeError, ValueError):
        return None


def token_seconds_remaining(token: str, now: Optional[int] = None) -> Optional[int]:
    expiry = token_expiry_epoch(token)
    if expiry is None:
        return None
    current_time = int(now if now is not None else time.time())
    return expiry - current_time


def _token_is_usable(token: str, min_ttl_seconds: int) -> bool:
    remaining = token_seconds_remaining(token)
    if remaining is None:
        return True
    return remaining > min_ttl_seconds


def _load_cached_token_from_disk() -> Optional[str]:
    path = _cache_path()
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    token = payload.get("token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    return None


def cache_sigstore_identity_token(token: str, logger: Optional[logging.Logger] = None) -> Optional[int]:
    trimmed = token.strip()
    if not trimmed:
        return None

    expiry = token_expiry_epoch(trimmed)
    path = _cache_path()

    with _CACHE_LOCK:
        global _MEMORY_TOKEN, _MEMORY_EXPIRY
        _MEMORY_TOKEN = trimmed
        _MEMORY_EXPIRY = expiry

        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "token": trimmed,
            "expiry": expiry,
            "cached_at": int(time.time()),
        }
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        os.chmod(path, 0o600)

    remaining = token_seconds_remaining(trimmed)
    if remaining is not None:
        _get_logger(logger).info("Cached Sigstore identity token with %ss remaining", remaining)
    else:
        _get_logger(logger).info("Cached Sigstore identity token with unknown expiry")
    return expiry


def clear_sigstore_identity_token_cache(logger: Optional[logging.Logger] = None) -> None:
    path = _cache_path()
    with _CACHE_LOCK:
        global _MEMORY_TOKEN, _MEMORY_EXPIRY
        _MEMORY_TOKEN = None
        _MEMORY_EXPIRY = None
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            _get_logger(logger).warning("Failed to remove cached Sigstore identity token %s: %s", path, exc)


def resolve_sigstore_identity_token(
    operation: str,
    logger: Optional[logging.Logger] = None,
    allow_interactive: Optional[bool] = None,
    min_ttl_seconds: Optional[int] = None,
    require_token: bool = False,
    force_refresh: bool = False,
    suppress_warning: bool = False,
) -> Optional[str]:
    log = _get_logger(logger)
    min_ttl = _min_ttl_seconds() if min_ttl_seconds is None else max(0, min_ttl_seconds)

    if not force_refresh:
        env_token = os.environ.get(SIGSTORE_IDENTITY_TOKEN_ENV, "").strip()
        if env_token:
            if _token_is_usable(env_token, min_ttl):
                cache_sigstore_identity_token(env_token, logger=log)
                return env_token
            remaining = token_seconds_remaining(env_token)
            log.warning(
                "Ignoring %s for %s because it expires too soon (%ss remaining, min ttl %ss)",
                SIGSTORE_IDENTITY_TOKEN_ENV,
                operation,
                remaining if remaining is not None else -1,
                min_ttl,
            )

        with _CACHE_LOCK:
            memory_token = _MEMORY_TOKEN
            memory_expiry = _MEMORY_EXPIRY

        if memory_token:
            if memory_expiry is None or _token_is_usable(memory_token, min_ttl):
                return memory_token

        disk_token = _load_cached_token_from_disk()
        if disk_token and _token_is_usable(disk_token, min_ttl):
            cache_sigstore_identity_token(disk_token, logger=log)
            return disk_token

    if allow_interactive is None:
        allow_interactive = _parse_bool(os.environ.get(SIGSTORE_INTERACTIVE_LOGIN_ENV), default=False)

    if not allow_interactive:
        if require_token:
            raise MissingSigstoreIdentityTokenError(operation)
        if not suppress_warning:
            log.warning(
                "Skipping Sigstore identity acquisition for %s because no reusable token is available. "
                "Set %s, pre-populate %s, or enable %s for interactive refresh.",
                operation,
                SIGSTORE_IDENTITY_TOKEN_ENV,
                _cache_path(),
                SIGSTORE_INTERACTIVE_LOGIN_ENV,
            )
        return None

    if not _has_interactive_stdio():
        hint = (
            f"Sigstore identity token is required for {operation}, but no interactive terminal is available in the "
            f"current tc_api process. Deferring Sigstore login to the client-side challenge flow; retry this operation "
            f"with a fresh identity_token once the client completes login."
        )
        if require_token:
            raise MissingSigstoreIdentityTokenError(operation, message=hint)
        if not suppress_warning:
            log.warning(hint)
        return None

    log.info("Acquiring fresh Sigstore identity token for %s", operation)
    from ..cli.oidc_verification_code import acquire_sigstore_token_via_oob

    raw_token = acquire_sigstore_token_via_oob(operation=operation, cache_token=True)
    return raw_token


def resolve_sigstore_identity_token_object(
    operation: str,
    logger: Optional[logging.Logger] = None,
    allow_interactive: Optional[bool] = None,
    min_ttl_seconds: Optional[int] = None,
    force_refresh: bool = False,
    suppress_warning: bool = False,
) -> Optional[IdentityToken]:
    raw_token = resolve_sigstore_identity_token(
        operation=operation,
        logger=logger,
        allow_interactive=allow_interactive,
        min_ttl_seconds=min_ttl_seconds,
        force_refresh=force_refresh,
        suppress_warning=suppress_warning,
    )
    if not raw_token:
        return None
    return IdentityToken(raw_token)