from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

from database.database import get_db
from database.models import User, KYCSession, VideoSession, KYCStatus
from database.schemas import VideoSessionResponse, VideoTokenResponse
from routes.auth import get_current_user, get_current_admin
from services.livekit_service import LiveKitService
from services.transcription_service import transcription_service
from config import settings

router = APIRouter(prefix="/video", tags=["Video Verification"])

livekit_service = LiveKitService()

@router.post("/room", response_model=VideoTokenResponse)
async def create_video_room(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a video room for KYC verification"""
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
    
    # Create or get video session
    result = await db.execute(
        select(VideoSession).where(VideoSession.kyc_session_id == session.id)
    )
    video_session = result.scalar_one_or_none()
    
    room_name = f"kyc-{session.id}"
    
    if not video_session:
        video_session = VideoSession(
            kyc_session_id=session.id,
            room_name=room_name
        )
        db.add(video_session)
        await db.commit()
        await db.refresh(video_session)
    
    # Generate token for user
    token = await livekit_service.create_token(
        room_name=room_name,
        participant_name=current_user.full_name or current_user.email,
        is_admin=False
    )
    
    return VideoTokenResponse(
        token=token,
        room_name=room_name,
        participant_name=current_user.full_name or current_user.email,
        livekit_url=settings.LIVEKIT_URL
    )

@router.post("/room/{session_id}/join-agent", response_model=VideoTokenResponse)
async def join_as_agent(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Admin: Join a video room as verification agent"""
    result = await db.execute(
        select(VideoSession).where(VideoSession.kyc_session_id == session_id)
    )
    video_session = result.scalar_one_or_none()
    
    if not video_session:
        raise HTTPException(status_code=404, detail="Video session not found")
    
    # Update agent info
    video_session.agent_id = current_user.id
    if not video_session.started_at:
        video_session.started_at = datetime.utcnow()
    
    await db.commit()
    
    # Generate token for agent
    token = await livekit_service.create_token(
        room_name=video_session.room_name,
        participant_name=f"Agent: {current_user.full_name or current_user.email}",
        is_admin=True
    )
    
    return VideoTokenResponse(
        token=token,
        room_name=video_session.room_name,
        participant_name=f"Agent: {current_user.full_name or current_user.email}",
        livekit_url=settings.LIVEKIT_URL
    )

@router.post("/room/{session_id}/end")
async def end_video_session(
    session_id: str,
    notes: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Admin: End a video session"""
    result = await db.execute(
        select(VideoSession).where(VideoSession.kyc_session_id == session_id)
    )
    video_session = result.scalar_one_or_none()
    
    if not video_session:
        raise HTTPException(status_code=404, detail="Video session not found")
    
    video_session.ended_at = datetime.utcnow()
    video_session.agent_notes = notes

    # Simulate saving recording file
    recording_filename = f"recording_{session_id}_{int(video_session.ended_at.timestamp())}.mp4"
    recording_path = f"recordings/{recording_filename}"
    
    try:
        with open(recording_path, "w") as f:
            f.write("DUMMY VIDEO DATA - SIMULATED RECORDING")
        video_session.recording_url = f"/recordings/{recording_filename}"
    except Exception as e:
        logger.error(f"Failed to save simulated recording: {e}")

    # Update KYC session status
    result = await db.execute(
        select(KYCSession).where(KYCSession.id == session_id)
    )
    kyc_session = result.scalar_one_or_none()
    if kyc_session:
        kyc_session.status = KYCStatus.VIDEO_COMPLETED
    
    await db.commit()
    
    return {
        "status": "ended", 
        "session_id": session_id,
        "recording_url": video_session.recording_url
    }

@router.get("/pending-rooms")
async def list_pending_rooms(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Admin: List all pending video rooms waiting for an agent"""
    result = await db.execute(
        select(VideoSession).where(
            VideoSession.agent_id == None,
            VideoSession.ended_at == None
        )
    )
    sessions = result.scalars().all()
    
    return [
        {
            "kyc_session_id": s.kyc_session_id,
            "room_name": s.room_name,
            "created_at": s.id
        }
        for s in sessions
    ]

@router.websocket("/ws/{session_id}")
async def websocket_transcription_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time transcription.
    
    Both user and agent stream audio bytes for Sarvam AI transcription.
    Transcripts are broadcast to ALL subscribers in real-time.
    
    Query Params:
    - role: 'user' or 'agent' (default: user)
    - sample_rate: audio sample rate (default: 48000)
    """
    await websocket.accept()
    role = websocket.query_params.get("role", "user")
    speaker_name = "Agent" if role == "agent" else "User"
    
    # Session metadata
    metadata = {
        "role": role,
        "connected_at": datetime.utcnow().isoformat(),
        "client_ip": websocket.client.host if websocket.client else "unknown"
    }

    # Audio sample rate from query params
    try:
        input_sample_rate = int(websocket.query_params.get("sample_rate", 48000))
    except ValueError:
        input_sample_rate = 48000
    
    logger.info(f"[WS] {speaker_name} connected to session {session_id} (rate={input_sample_rate})")

    # Subscriber callback for this websocket
    async def on_transcript(transcript_data: dict):
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json(transcript_data)
        except Exception as e:
            logger.error(f"[WS] Error sending transcript to {speaker_name}: {e}")

    try:
        # Start/join session
        await transcription_service.start_session(session_id, metadata=metadata)
        
        # Subscribe to receive transcripts from all speakers
        transcription_service.subscribe(session_id, on_transcript)
        
        # Send existing history immediately
        history = transcription_service.get_transcripts(session_id)
        if history:
            logger.info(f"[WS] Sending {len(history)} historical transcripts to {speaker_name}")
            for entry in history:
                await websocket.send_json(entry)
        
        # Audio generator reads binary audio from this WebSocket
        async def audio_generator():
            try:
                while True:
                    message = await websocket.receive()
                    if "bytes" in message:
                        yield message["bytes"]
                    elif "text" in message:
                        # Browser speech API fallback sends JSON text
                        try:
                            data = json.loads(message["text"])
                            if data.get("type") == "transcript":
                                await transcription_service.add_transcript(
                                    session_id=session_id,
                                    speaker=speaker_name,
                                    text=data.get("text", ""),
                                    source_language=data.get("language") or "auto",
                                    is_final=data.get("is_final", True)
                                )
                        except Exception as e:
                            logger.error(f"[WS] Error processing text message: {e}")
            except WebSocketDisconnect:
                return
            except Exception as e:
                logger.error(f"[WS] Audio generator error ({speaker_name}): {e}")
                return
        
        # Stream audio to Sarvam AI for transcription
        await transcription_service.process_audio_stream(
            session_id=session_id, 
            audio_generator=audio_generator(),
            speaker=speaker_name,
            input_sample_rate=input_sample_rate
        )

    except WebSocketDisconnect:
        logger.info(f"[WS] {speaker_name} disconnected from session {session_id}")
    except Exception as e:
        logger.error(f"[WS] Error for {speaker_name}: {e}")
    finally:
        transcription_service.unsubscribe(session_id, on_transcript)
        # Only the user's disconnect triggers session save
        if role == "user":
            await transcription_service.end_session(session_id)
