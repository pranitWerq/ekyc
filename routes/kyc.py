from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List

from database.database import get_db
from database.models import User, KYCSession, KYCStatus
from database.schemas import KYCSessionCreate, KYCSessionResponse, KYCSessionDetail, KYCReviewRequest
from routes.auth import get_current_user, get_current_admin

router = APIRouter(prefix="/kyc", tags=["KYC"])

@router.post("/sessions", response_model=KYCSessionResponse)
async def create_kyc_session(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new KYC verification session"""
    # Check if user already has any session
    result = await db.execute(
        select(KYCSession).where(
            KYCSession.user_id == current_user.id
        ).order_by(KYCSession.created_at.desc())
    )
    existing = result.scalars().first()
    
    # If user has an active, completed or approved session, return it
    if existing and existing.status != KYCStatus.REJECTED:
        return existing
    
    # Create new session if no session exists or previous was rejected
    session = KYCSession(user_id=current_user.id)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session

@router.get("/sessions/current", response_model=KYCSessionDetail)
async def get_current_session(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get current user's active KYC session with all details"""
    result = await db.execute(
        select(KYCSession)
        .options(
            selectinload(KYCSession.documents),
            selectinload(KYCSession.face_verification),
            selectinload(KYCSession.liveness_check),
            selectinload(KYCSession.video_session)
        )
        .where(KYCSession.user_id == current_user.id)
        .order_by(KYCSession.created_at.desc())
    )
    session = result.scalars().first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active KYC session found"
        )
    return session

@router.get("/sessions/{session_id}", response_model=KYCSessionDetail)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific KYC session"""
    result = await db.execute(
        select(KYCSession)
        .options(
            selectinload(KYCSession.documents),
            selectinload(KYCSession.face_verification),
            selectinload(KYCSession.liveness_check),
            selectinload(KYCSession.video_session)
        )
        .where(KYCSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Only owner or admin can view
    if session.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return session

@router.get("/admin/sessions", response_model=List[KYCSessionResponse])
async def list_all_sessions(
    status_filter: KYCStatus = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Admin: List all KYC sessions"""
    query = select(KYCSession).order_by(KYCSession.created_at.desc())
    if status_filter:
        query = query.where(KYCSession.status == status_filter)
    
    result = await db.execute(query)
    return result.scalars().all()

@router.put("/admin/sessions/{session_id}/review", response_model=KYCSessionResponse)
async def review_session(
    session_id: str,
    review: KYCReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Admin: Review and update KYC session status"""
    result = await db.execute(select(KYCSession).where(KYCSession.id == session_id))
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session.status = review.status
    session.notes = review.notes
    session.reviewed_by = current_user.id
    
    await db.commit()
    await db.refresh(session)
    return session
