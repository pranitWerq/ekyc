from typing import Optional
import time
from datetime import timedelta

try:
    from livekit import api
    LIVEKIT_AVAILABLE = True
except ImportError:
    LIVEKIT_AVAILABLE = False

from config import settings

class LiveKitService:
    """Service for LiveKit video room management"""
    
    def __init__(self):
        self.api_key = settings.LIVEKIT_API_KEY
        self.api_secret = settings.LIVEKIT_API_SECRET
        self.livekit_url = settings.LIVEKIT_URL
        print(f"LiveKit Service initialized - Available: {LIVEKIT_AVAILABLE}")
        print(f"LiveKit URL: {self.livekit_url}")
    
    async def create_token(
        self,
        room_name: str,
        participant_name: str,
        is_admin: bool = False
    ) -> str:
        """Generate a LiveKit access token for a participant"""
        if not LIVEKIT_AVAILABLE or not self.api_key or not self.api_secret:
            print(f"LiveKit not available or credentials missing. Returning mock token.")
            return f"mock_token_{room_name}_{participant_name}_{int(time.time())}"
        
        try:
            # Create token with appropriate permissions
            token = api.AccessToken(self.api_key, self.api_secret)
            token.with_identity(participant_name.replace(" ", "_"))  # Identity should be URL-safe
            token.with_name(participant_name)
            
            # Set room permissions - use keyword args for clarity
            grant = api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
                room_admin=is_admin,
                room_record=is_admin
            )
            
            token.with_grants(grant)
            
            # Token expires in 6 hours
            token.with_ttl(timedelta(hours=6))
            
            jwt_token = token.to_jwt()
            print(f"Generated LiveKit token for {participant_name} in room {room_name}")
            return jwt_token
        except Exception as e:
            print(f"Error generating LiveKit token: {e}")
            # Return a mock token as fallback
            return f"mock_token_{room_name}_{participant_name}_{int(time.time())}"
    
    async def create_room(self, room_name: str) -> dict:
        """Create a new LiveKit room"""
        if not LIVEKIT_AVAILABLE:
            return {
                "name": room_name,
                "status": "mock_created",
                "message": "LiveKit not available - using mock mode"
            }
        
        try:
            room_service = api.RoomServiceClient(
                self.livekit_url,
                self.api_key,
                self.api_secret
            )
            
            room = await room_service.create_room(
                api.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=60 * 10,  # 10 minutes
                    max_participants=2
                )
            )
            
            return {
                "name": room.name,
                "sid": room.sid,
                "status": "created"
            }
        except Exception as e:
            return {
                "name": room_name,
                "status": "error",
                "error": str(e)
            }
    
    async def list_participants(self, room_name: str) -> list:
        """List participants in a room"""
        if not LIVEKIT_AVAILABLE:
            return []
        
        try:
            room_service = api.RoomServiceClient(
                self.livekit_url,
                self.api_key,
                self.api_secret
            )
            
            response = await room_service.list_participants(
                api.ListParticipantsRequest(room=room_name)
            )
            
            return [
                {
                    "sid": p.sid,
                    "identity": p.identity,
                    "name": p.name,
                    "state": p.state
                }
                for p in response.participants
            ]
        except Exception as e:
            return []
    
    async def remove_participant(
        self, 
        room_name: str, 
        participant_identity: str
    ) -> bool:
        """Remove a participant from a room"""
        if not LIVEKIT_AVAILABLE:
            return True
        
        try:
            room_service = api.RoomServiceClient(
                self.livekit_url,
                self.api_key,
                self.api_secret
            )
            
            await room_service.remove_participant(
                api.RoomParticipantIdentity(
                    room=room_name,
                    identity=participant_identity
                )
            )
            return True
        except Exception as e:
            return False
    
    async def delete_room(self, room_name: str) -> bool:
        """Delete a LiveKit room"""
        if not LIVEKIT_AVAILABLE:
            return True
        
        try:
            room_service = api.RoomServiceClient(
                self.livekit_url,
                self.api_key,
                self.api_secret
            )
            
            await room_service.delete_room(
                api.DeleteRoomRequest(room=room_name)
            )
            return True
        except Exception as e:
            return False
    
    async def start_recording(self, room_name: str) -> Optional[str]:
        """Start recording a room session"""
        if not LIVEKIT_AVAILABLE:
            return "mock_recording_id"
        
        # Implementation depends on LiveKit Egress setup
        # This is a placeholder for the actual implementation
        return None
    
    async def stop_recording(self, egress_id: str) -> bool:
        """Stop an active recording"""
        if not LIVEKIT_AVAILABLE:
            return True
        
        # Implementation depends on LiveKit Egress setup
        return True
