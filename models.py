from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class BuildPackageRequest(BaseModel):
    dockerfile: str
    app_binary: Optional[str] = None
    configs: List[str] = []
    data: List[str] = []
    sign_key: str
    cert: str
    encrypt: bool = False
    user_id: str

class BuildPackageResponse(BaseModel):
    build_id: str
    status: str
    estimated_time: str

class PublishPackageRequest(BaseModel):
    image_tar: str
    sbom: str
    image_id: str
    user_id: str
    metadata: Dict[str, Any]

class PolicyModel(BaseModel):
    usage: str
    expiry: str

class RegisterKeyRequest(BaseModel):
    image_id: str
    user_id: str
    public_key: str
    cert: str
    policy: PolicyModel

class BuildResult(BaseModel):
    build_id: str
    status: str
    image_id: Optional[str] = None
    sbom_url: Optional[str] = None
    image_url: Optional[str] = None
    cert_url: Optional[str] = None
    log_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None
