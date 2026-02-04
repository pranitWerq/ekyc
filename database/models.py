from sqlalchemy import Column, String, DateTime, Float, Boolean, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from database.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class KYCStatus(str, enum.Enum):
    PENDING = "pending"
    DOCUMENT_UPLOADED = "document_uploaded"
    FACE_VERIFIED = "face_verified"
    LIVENESS_PASSED = "liveness_passed"
    VIDEO_COMPLETED = "video_completed"
    APPROVED = "approved"
    REJECTED = "rejected"

class DocumentType(str, enum.Enum):
    PASSPORT = "passport"
    DRIVERS_LICENSE = "drivers_license"
    NATIONAL_ID = "national_id"
    OTHER = "other"

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    kyc_sessions = relationship("KYCSession", back_populates="user", foreign_keys="KYCSession.user_id")

class KYCSession(Base):
    __tablename__ = "kyc_sessions"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    status = Column(Enum(KYCStatus), default=KYCStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(Text, nullable=True)
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True)
    
    user = relationship("User", back_populates="kyc_sessions", foreign_keys=[user_id])
    documents = relationship("Document", back_populates="kyc_session")
    face_verification = relationship("FaceVerification", back_populates="kyc_session", uselist=False)
    liveness_check = relationship("LivenessCheck", back_populates="kyc_session", uselist=False)
    video_session = relationship("VideoSession", back_populates="kyc_session", uselist=False)

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    kyc_session_id = Column(String, ForeignKey("kyc_sessions.id"), nullable=False)
    document_type = Column(Enum(DocumentType), nullable=False)
    file_path = Column(String, nullable=False)
    ocr_data = Column(Text, nullable=True)  # JSON string
    extracted_name = Column(String, nullable=True)
    extracted_dob = Column(String, nullable=True)
    extracted_id_number = Column(String, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    kyc_session = relationship("KYCSession", back_populates="documents")

class FaceVerification(Base):
    __tablename__ = "face_verifications"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    kyc_session_id = Column(String, ForeignKey("kyc_sessions.id"), nullable=False)
    selfie_path = Column(String, nullable=False)
    document_face_path = Column(String, nullable=True)
    match_score = Column(Float, nullable=True)
    is_match = Column(Boolean, default=False)
    verified_at = Column(DateTime, default=datetime.utcnow)
    
    kyc_session = relationship("KYCSession", back_populates="face_verification")

class LivenessCheck(Base):
    __tablename__ = "liveness_checks"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    kyc_session_id = Column(String, ForeignKey("kyc_sessions.id"), nullable=False)
    blink_detected = Column(Boolean, default=False)
    smile_detected = Column(Boolean, default=False)
    head_turn_detected = Column(Boolean, default=False)
    is_live = Column(Boolean, default=False)
    confidence_score = Column(Float, nullable=True)
    checked_at = Column(DateTime, default=datetime.utcnow)
    
    kyc_session = relationship("KYCSession", back_populates="liveness_check")

class VideoSession(Base):
    __tablename__ = "video_sessions"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    kyc_session_id = Column(String, ForeignKey("kyc_sessions.id"), nullable=False)
    room_name = Column(String, nullable=False)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    agent_id = Column(String, ForeignKey("users.id"), nullable=True)
    recording_url = Column(String, nullable=True)
    transcript = Column(Text, nullable=True)
    agent_notes = Column(Text, nullable=True)
    
    kyc_session = relationship("KYCSession", back_populates="video_session")
