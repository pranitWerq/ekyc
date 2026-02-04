from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from database.models import KYCStatus, DocumentType

# Auth Schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    is_active: bool
    is_admin: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: Optional[str] = None

# KYC Schemas
class KYCSessionCreate(BaseModel):
    pass

class KYCSessionResponse(BaseModel):
    id: str
    user_id: str
    status: KYCStatus
    created_at: datetime
    updated_at: datetime
    notes: Optional[str]
    
    class Config:
        from_attributes = True

class KYCSessionDetail(KYCSessionResponse):
    documents: List["DocumentResponse"] = []
    face_verification: Optional["FaceVerificationResponse"] = None
    liveness_check: Optional["LivenessCheckResponse"] = None
    video_session: Optional["VideoSessionResponse"] = None

# Document Schemas
class DocumentUpload(BaseModel):
    document_type: DocumentType

class DocumentResponse(BaseModel):
    id: str
    document_type: DocumentType
    file_path: str
    extracted_name: Optional[str]
    extracted_dob: Optional[str]
    extracted_id_number: Optional[str]
    uploaded_at: datetime
    
    class Config:
        from_attributes = True

# Face Verification Schemas
class FaceVerificationResponse(BaseModel):
    id: str
    selfie_path: str
    match_score: Optional[float]
    is_match: bool
    verified_at: datetime
    
    class Config:
        from_attributes = True

# Liveness Check Schemas
class LivenessCheckResponse(BaseModel):
    id: str
    blink_detected: bool
    smile_detected: bool
    head_turn_detected: bool
    is_live: bool
    confidence_score: Optional[float]
    checked_at: datetime
    
    class Config:
        from_attributes = True

class LivenessActionRequest(BaseModel):
    action: str  # "blink", "smile", "head_turn"
    image_data: str  # Base64 encoded image

# Video Session Schemas
class VideoSessionResponse(BaseModel):
    id: str
    room_name: str
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    agent_notes: Optional[str]
    
    class Config:
        from_attributes = True

class VideoRoomCreate(BaseModel):
    pass

class VideoTokenResponse(BaseModel):
    token: str
    room_name: str
    participant_name: str
    livekit_url: Optional[str] = None

# Admin Schemas
class KYCReviewRequest(BaseModel):
    status: KYCStatus
    notes: Optional[str] = None

# Update forward references
KYCSessionDetail.model_rebuild()
