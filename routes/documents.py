from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import os
import uuid
from datetime import datetime

from database.database import get_db
from database.models import User, KYCSession, Document, KYCStatus, DocumentType
from database.schemas import DocumentResponse, DocumentUpload
from routes.auth import get_current_user
from services.ocr_service import OCRService
from config import settings

router = APIRouter(prefix="/documents", tags=["Documents"])

ocr_service = OCRService()

@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    document_type: DocumentType = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a document for verification"""
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
    
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/jpg", "application/pdf"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    # Validate file size
    contents = await file.read()
    if len(contents) > settings.MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large")
    
    # Save file
    file_ext = file.filename.split(".")[-1] if file.filename else "jpg"
    filename = f"{uuid.uuid4()}.{file_ext}"
    file_path = os.path.join(settings.UPLOAD_DIR, "documents", filename)
    
    with open(file_path, "wb") as f:
        f.write(contents)
    
    # Perform OCR
    ocr_result = await ocr_service.extract_document_data(file_path, document_type)
    
    # Create document record
    document = Document(
        kyc_session_id=session.id,
        document_type=document_type,
        file_path=file_path,
        ocr_data=str(ocr_result),
        extracted_name=ocr_result.get("name"),
        extracted_dob=ocr_result.get("dob"),
        extracted_id_number=ocr_result.get("id_number")
    )
    db.add(document)
    
    # Update session status
    session.status = KYCStatus.DOCUMENT_UPLOADED
    
    await db.commit()
    await db.refresh(document)
    return document

@router.get("/session/{session_id}", response_model=list[DocumentResponse])
async def get_session_documents(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all documents for a KYC session"""
    # Verify access
    result = await db.execute(select(KYCSession).where(KYCSession.id == session_id))
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    result = await db.execute(
        select(Document).where(Document.kyc_session_id == session_id)
    )
    return result.scalars().all()
