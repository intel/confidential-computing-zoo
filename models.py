from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field
from datetime import datetime

class BuildPackageRequest(BaseModel):
    dockerfile: str  # Base64 encoded or file content
    app_binary: Optional[str] = None  # Base64 encoded binary
    configs: Optional[List[str]] = None  # List of Base64 encoded config files
    data: Optional[List[str]] = None  # List of Base64 encoded data files
    sign_key: Optional[str] = None
    cert: Optional[str] = None
    encrypt: bool = False
    user_id: str
    #identity_token: Optional[str] = None

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
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True

class PublishPackageResponse(BaseModel):
    build_id: str
    status: str
    image_url: str
    user_id: str
    sbom_url: Optional[str] = None
    log_id: Optional[str] = None
    transparencyLog_verify: str
    published_at: datetime = Field(default_factory=datetime.now)



class BuildResult(BaseModel):
    user_id: str
    build_id: str
    status: str = "pending"  # pending, preparing, building, generating_sbom, encrypting, pushing, signing, success, failed
    current_step: Optional[str] = None  # Detailed description of current operation
    image_id: Optional[str] = None
    sbom_url: Optional[str] = None
    image_url: Optional[str] = None
    cert_url: Optional[str] = None
    log_id: Optional[str] = None
    transparencyLog_verify: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class LaunchRequest(BaseModel):
    image_id: str
    user_id: str
    image_url: Optional[str] = None
    sbom_url: Optional[str] = None
    attestation_required: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)

class LaunchResponse(BaseModel):
    launch_id: str
    status: str
    user_id: str
    log_id: Optional[str] = None
    transparencyLog_verify: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)

class LaunchResult(BaseModel):
    user_id: str
    launch_id: str
    status: str
    validation: Optional[str] = None
    attestation: Optional[str] = None
    log_id: Optional[str] = None
    instance_ids: List[str] = []
    transparencyLog_verify: Optional[str] = None
    evidence: Dict[str, Any] = {}
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime = Field(default_factory=datetime.now)

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

class SummaryTransparencyRespone(BaseModel):
    build_id: str
    launch_id: str
    log_id: Dict[str, str]
    transparencylog: Dict[str, str]


class GetTransparencyRequest(BaseModel):
    build_id: str
    launch_id: str

