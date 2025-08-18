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

class BuildPackageResponse(BaseModel):
    build_id: str
    status: str
    estimated_time: str

class PublishPackageRequest(BaseModel):
    image_id: str
    user_id: str
    log_evidence: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        arbitrary_types_allowed = True

class PublishPackageResponse(BaseModel):
    status: str
    image_url: str
    sbom_url: Optional[str] = None
    log_id: Optional[str] = None
    published_at: datetime = Field(default_factory=datetime.now)



class BuildResult(BaseModel):
    build_id: str
    status: str = "pending"  # pending, building, success, failed
    image_id: Optional[str] = None
    sbom_url: Optional[str] = None
    image_url: Optional[str] = None  
    cert_url: Optional[str] = None
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
    created_at: datetime = Field(default_factory=datetime.now)

class LaunchResult(BaseModel):
    launch_id: str
    status: str
    validation: Optional[str]
    attestation: Optional[str]
    log_id: Optional[str]
    instance_ids: List[str] = []
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime = Field(default_factory=datetime.now)
