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

from enum import Enum
from pathlib import Path
import re
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime

from .config import LUKS_MOUNT_BASE_DIR, LUKS_VFS_BASE_DIR
from .utils.registry import validate_external_image_reference


_LOOP_DEVICE_RE = re.compile(r"^/dev/loop\d+$")
_MAPPER_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_RUNTIME_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}$")


def _normalize_path_in_base(path_value: str, base_dir: str, field_name: str) -> str:
    path = Path(path_value)
    if not path.is_absolute():
        raise ValueError(f"{field_name} must be an absolute path")
    resolved_path = path.resolve(strict=False)
    resolved_base = Path(base_dir).resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError(f"{field_name} must stay under {resolved_base}") from exc
    return str(resolved_path)


def _validate_mapper_name(value: str) -> str:
    if not _MAPPER_NAME_RE.fullmatch(value):
        raise ValueError("mapper_dir must contain only letters, numbers, dot, dash, or underscore")
    return value


def _validate_loop_device(value: str) -> str:
    if not _LOOP_DEVICE_RE.fullmatch(value):
        raise ValueError("loop_device must be a /dev/loopN path")
    return value


def _validate_runtime_id(value: str, field_name: str) -> str:
    if not _RUNTIME_ID_RE.fullmatch(value):
        raise ValueError(f"{field_name} must contain only letters, numbers, and dashes")
    return value


class BuildStatus(str, Enum):
    pending = "pending"
    submitted = "submitted"
    preparing = "preparing"
    building = "building"
    generating_sbom = "generating_sbom"
    encrypting = "encrypting"
    pushing = "pushing"
    signing = "signing"
    success = "success"
    failed = "failed"


class PublishStatus(str, Enum):
    publishing = "publishing"
    pushing = "pushing"
    signing = "signing"
    success = "success"
    failed = "failed"


class LaunchStatus(str, Enum):
    pending = "pending"
    launching = "launching"
    signing = "signing"
    success = "success"
    failed = "failed"


class EncryptedVfsStatus(str, Enum):
    creating = "creating"
    mounting = "mounting"
    unmounting = "unmounting"
    success = "success"
    failed = "failed"


class BaseResult(BaseModel):
    """Common fields shared by all operation result models."""
    user_id: str
    status: str
    log_id: Optional[str] = None
    transparencyLog_verify: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class BuildPackageRequest(BaseModel):
    dockerfile: str  
    app_binary: Optional[str] = None  # Base64 encoded binary
    configs: Optional[List[str]] = None  # List of Base64 encoded config files
    data: Optional[List[str]] = None  # List of Base64 encoded data files
    sign_key: Optional[str] = None
    cert: Optional[str] = None
    encrypt: bool = False
    user_id: Optional[str] = None
    identity_token: Optional[str] = None
    luks_path: Optional[str] = None


class BuildCommitRequest(BaseModel):
    identity_token: Optional[str] = None


class PublishCommitRequest(BaseModel):
    identity_token: Optional[str] = None

class BuildPackageResponse(BaseModel):
    build_id: str
    status: str
    estimated_time: str
    user_id: str
    transparencyLog_verify: Optional[str] = None
    luks_path: Optional[str] = None

class PublishPackageRequest(BaseModel):
    build_id: str
    sbom_url: str
    image_id: str
    user_id: Optional[str] = None
    log_evidence: bool = True
    image_url: Optional[str] = None
    identity_token: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    luks_path: Optional[str] = None
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator("build_id")
    @classmethod
    def validate_build_id(cls, value: str) -> str:
        return _validate_runtime_id(value, "build_id")

    @field_validator("image_id")
    @classmethod
    def validate_publish_image_id(cls, value: str) -> str:
        if not value.startswith("oci:"):
            raise ValueError("image_id must use the oci: transport for publish requests")
        return value

class PublishPackageResponse(BaseModel):
    build_id: str
    status: str
    image_url: str
    user_id: str
    image_id: str
    sbom_url: Optional[str] = None
    log_id: Optional[str] = None
    transparencyLog_verify: str
    published_at: datetime = Field(default_factory=datetime.now)
    luks_path: Optional[str] = None


class BuildResult(BaseResult):
    build_id: str
    status: str = "pending"
    current_step: Optional[str] = None
    image_id: Optional[str] = None
    sbom_url: Optional[str] = None
    image_url: Optional[str] = None
    cert_url: Optional[str] = None
    luks_path: Optional[str] = None

class LaunchRequest(BaseModel):
    image_id: str
    user_id: Optional[str] = None
    image_url: Optional[str] = None
    sbom_url: Optional[str] = None
    attestation_required: bool = True
    identity_token: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    dockercmd: Optional[str] = None
    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return validate_external_image_reference(value, "image_url")

class LaunchResponse(BaseModel):
    launch_id: str
    status: str
    user_id: str
    log_id: Optional[str] = None
    transparencyLog_verify: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    dockercmd: Optional[str] = None

class LaunchCommitRequest(BaseModel):
    identity_token: Optional[str] = None

class PublishResult(BaseResult):
    publish_id: str
    build_id: str
    status: str = "publishing"
    current_step: Optional[str] = None
    image_id: Optional[str] = None
    sbom_url: Optional[str] = None
    image_url: Optional[str] = None
    cert_url: Optional[str] = None

class LaunchResult(BaseResult):
    launch_id: str
    validation: Optional[str] = None
    attestation: Optional[str] = None
    instance_ids: List[Any] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)

class VerifyTlogRequest(BaseModel):
    raw_file: Dict[str, str]
    bundle_file: Dict[str, str]
    chain_file: Dict[str, str]
    email_addr: str
    identity_token: Optional[str] = None

class VerificationSummaryResponse(BaseModel):
    success: bool
    summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class TransparencyResult(BaseModel):
    user_id: str
    build_id: str
    log_id: Optional[str] = None
    status: str = "add" # add / save / verify
    transparency_log: str
    transparencyLog_verify: Optional[str] = None
    error_message: Optional[str] = None

class SummaryTransparencyResponse(BaseModel):
    build_id: str
    launch_id: str
    log_id: Dict[str, str]
    transparencylog: Dict[str, str]


class GetTransparencyRequest(BaseModel):
    build_id: str
    launch_id: str

    @field_validator("build_id")
    @classmethod
    def validate_build_id(cls, value: str) -> str:
        return _validate_runtime_id(value, "build_id")

    @field_validator("launch_id")
    @classmethod
    def validate_launch_id(cls, value: str) -> str:
        return _validate_runtime_id(value, "launch_id")

class CreateLuksRequest(BaseModel):
    user_id: Optional[str] = None
    vfs_path: str
    vfs_size: str
    passwd: str
    identity_token: Optional[str] = None


class CreateLuksResponse(BaseModel):
    user_id: str
    vfs_path: str
    vfs_size: str
    mapper_dir: str
    loop_device: str


class LuksResult(BaseResult):
    status: str = "creating"
    step: Optional[str] = None
    mapper_dir: Optional[str] = None
    vfs_path: Optional[str] = None
    vfs_size: Optional[str] = None
    loop_device: Optional[str] = None
    mount_path: Optional[str] = None

class MountLuksRequest(BaseModel):
    user_id: Optional[str] = None
    passwd: str
    vfs_path: str
    mapper_dir: str
    loop_device: str
    mount_path: str
    identity_token: Optional[str] = None



class MountLuksResponse(BaseModel):
    user_id: str
    vfs_path: str
    loop_device: str
    mapper_dir: str
    mount_path: str


class UnmountLuksRequest(BaseModel):
    user_id: Optional[str] = None
    mapper_dir: str
    loop_device: str
    mount_path: str
    identity_token: Optional[str] = None
    @field_validator("mapper_dir")
    @classmethod
    def validate_mapper_dir(cls, value: str) -> str:
        return _validate_mapper_name(value)

    @field_validator("loop_device")
    @classmethod
    def validate_loop_device(cls, value: str) -> str:
        return _validate_loop_device(value)

class UnmountLuksResponse(BaseModel):
    user_id: str
    mapper_dir: str
    loop_device: str
    mount_path: str

