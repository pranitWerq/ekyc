from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import os
import uuid
import base64

from database.database import get_db
from database.models import User, KYCSession, Document, FaceVerification, LivenessCheck, KYCStatus
from database.schemas import FaceVerificationResponse, LivenessCheckResponse, LivenessActionRequest
from routes.auth import get_current_user
from services.face_service import FaceService
from services.liveness_service import LivenessService
from config import settings

router = APIRouter(prefix="/face", tags=["Face Verification"])

face_service = FaceService()
liveness_service = LivenessService()

@router.post("/verify", response_model=FaceVerificationResponse)
async def verify_face(
    selfie: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Verify selfie against uploaded document photo"""
    # Get current session with documents
    result = await db.execute(
        select(KYCSession).where(
            KYCSession.user_id == current_user.id,
            KYCSession.status.notin_([KYCStatus.APPROVED, KYCStatus.REJECTED])
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="No active KYC session")
    
    # Get document
    doc_result = await db.execute(
        select(Document).where(Document.kyc_session_id == session.id)
    )
    document = doc_result.scalars().first()
    
    if not document:
        raise HTTPException(status_code=400, detail="Please upload a document first")
    
    # Save selfie
    contents = await selfie.read()
    filename = f"{uuid.uuid4()}.jpg"
    selfie_path = os.path.join(settings.UPLOAD_DIR, "faces", filename)
    
    with open(selfie_path, "wb") as f:
        f.write(contents)
    
    # Perform face verification
    try:
        match_result = await face_service.compare_faces(
            selfie_path, 
            document.file_path
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Face verification failed: {str(e)}")
    
    # Create or update face verification record
    result = await db.execute(
        select(FaceVerification).where(FaceVerification.kyc_session_id == session.id)
    )
    face_record = result.scalar_one_or_none()
    
    if face_record:
        face_record.selfie_path = selfie_path
        face_record.match_score = match_result["score"]
        face_record.is_match = match_result["is_match"]
    else:
        face_record = FaceVerification(
            kyc_session_id=session.id,
            selfie_path=selfie_path,
            document_face_path=document.file_path,
            match_score=match_result["score"],
            is_match=match_result["is_match"]
        )
        db.add(face_record)
    
    # Update session status if match
    if match_result["is_match"]:
        session.status = KYCStatus.FACE_VERIFIED
    
    await db.commit()
    await db.refresh(face_record)
    return face_record

@router.post("/liveness/check", response_model=LivenessCheckResponse)
async def check_liveness(
    request: LivenessActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Process liveness detection action (blink, smile, head_turn)"""
    # Get current session
    result = await db.execute(
        select(KYCSession).where(
            KYCSession.user_id == current_user.id,
            KYCSession.status.notin_([KYCStatus.APPROVED, KYCStatus.REJECTED])
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="No active KYC session")
    
    # Decode base64 image
    try:
        image_data = base64.b64decode(request.image_data)
    except:
        raise HTTPException(status_code=400, detail="Invalid image data")
    
    # Get or create liveness record
    result = await db.execute(
        select(LivenessCheck).where(LivenessCheck.kyc_session_id == session.id)
    )
    liveness_record = result.scalar_one_or_none()
    
    if not liveness_record:
        liveness_record = LivenessCheck(kyc_session_id=session.id)
        db.add(liveness_record)
        await db.flush()
    
    # Perform action check
    action_result = await liveness_service.check_action(
        image_data, 
        request.action
    )
    
    # Update record based on action
    if request.action == "blink":
        liveness_record.blink_detected = action_result["detected"]
    elif request.action == "smile":
        liveness_record.smile_detected = action_result["detected"]
    elif request.action == "head_turn":
        liveness_record.head_turn_detected = action_result["detected"]
    
    # Check if all actions passed (now only blink and smile)
    if (liveness_record.blink_detected and 
        liveness_record.smile_detected):
        liveness_record.is_live = True
        liveness_record.confidence_score = action_result.get("confidence", 0.9)
        session.status = KYCStatus.LIVENESS_PASSED
    
    await db.commit()
    await db.refresh(liveness_record)
    return liveness_record

@router.get("/liveness/status", response_model=LivenessCheckResponse)
async def get_liveness_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get current liveness check status"""
    result = await db.execute(
        select(KYCSession).where(
            KYCSession.user_id == current_user.id,
            KYCSession.status.notin_([KYCStatus.APPROVED, KYCStatus.REJECTED])
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="No active KYC session")
    
    result = await db.execute(
        select(LivenessCheck).where(LivenessCheck.kyc_session_id == session.id)
    )
    liveness_record = result.scalar_one_or_none()
    
    if not liveness_record:
        raise HTTPException(status_code=404, detail="No liveness check started")
    
    return liveness_record
