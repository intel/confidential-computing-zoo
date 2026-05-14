from enum import Enum
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field
from datetime import datetime


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
    dockerfile: str  # Base64 encoded or file content
    app_binary: Optional[str] = None  # Base64 encoded binary
    configs: Optional[List[str]] = None  # List of Base64 encoded config files
    data: Optional[List[str]] = None  # List of Base64 encoded data files
    sign_key: Optional[str] = None
    cert: Optional[str] = None
    encrypt: bool = False
    user_id: str
    identity_token: Optional[str] = None

class BuildPackageResponse(BaseModel):
    build_id: str
    status: str
    estimated_time: str
    user_id: str
    transparencyLog_verify: Optional[str] = None

class PublishPackageRequest(BaseModel):
    build_id: str
    sbom_url: str
    image_id: str
    user_id: str
    log_evidence: bool = True
    image_url: Optional[str] = None
    identity_token: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True

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



class BuildResult(BaseResult):
    build_id: str
    status: str = "pending"
    current_step: Optional[str] = None
    image_id: Optional[str] = None
    sbom_url: Optional[str] = None
    image_url: Optional[str] = None
    cert_url: Optional[str] = None

class LaunchRequest(BaseModel):
    image_id: str
    user_id: str
    image_url: Optional[str] = None
    sbom_url: Optional[str] = None
    attestation_required: bool = True
    identity_token: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class LaunchResponse(BaseModel):
    launch_id: str
    status: str
    user_id: str
    log_id: Optional[str] = None
    transparencyLog_verify: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)

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

class CreateLuksRequest(BaseModel):
    user_id: str
    vfs_path: str
    vfs_size: str
    passwd: str


class CreateLuksResponse(BaseModel):
    user_id: str
    passwd: str
    vfs_path: str
    vfs_size: str
    mapper_dir: str
    loop_device: str


class LuksResult(BaseResult):
    status: str = "creating"
    step: Optional[str] = None
    passwd: Optional[str] = None
    mapper_dir: Optional[str] = None
    vfs_path: Optional[str] = None
    vfs_size: Optional[str] = None
    loop_device: Optional[str] = None
    mount_path: Optional[str] = None

class MountLuksRequest(BaseModel):
    user_id: str
    passwd: str
    vfs_path: str
    mapper_dir: str
    loop_device: str
    mount_path: str


class MountLuksResponse(BaseModel):
    user_id: str
    passwd: str
    vfs_path: str
    loop_device: str
    mapper_dir: str
    mount_path: str


class UnmountLuksRequest(BaseModel):
    user_id: str
    mapper_dir: str
    loop_device: str
    mount_path: str

class UnmountLuksResponse(BaseModel):
    user_id: str
    mapper_dir: str
    loop_device: str
    mount_path: str

