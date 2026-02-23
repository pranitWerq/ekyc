"""
Transcription Service for real-time speech-to-text with translation
Uses Sarvam AI for real-time transcription and translation to English
"""
import asyncio
from typing import Optional, Dict, List, Callable
from datetime import datetime
import json
import uuid
import os
import aiofiles
import logging
import websockets
import base64
from config import settings

logger = logging.getLogger(__name__)

# Sarvam AI Configuration
SARVAM_AVAILABLE = bool(settings.SARVAM_API_KEY)

class SarvamService:
    """Sarvam AI Services Wrapper for Streaming STT and Text Translation"""
    
    def __init__(self):
        self.api_key = settings.SARVAM_API_KEY
        self.ws_url = "wss://api.sarvam.ai/speech-to-text-translate/ws"
        
        if not SARVAM_AVAILABLE:
            logger.warning("Sarvam API Key not found in settings. Real-time transcription will be disabled.")

    async def start_streaming_transcription(self, audio_generator, callback: Callable, language_code: str = "hi-IN"):
        """
        Start streaming audio to Sarvam AI STT via WebSocket.
        
        Args:
            audio_generator: Async iterator yielding PCM audio bytes (16kHz, 16-bit)
            callback: Async function(text: str, is_partial: bool) to handle transcripts
            language_code: Language code for transcription (e.g., 'hi-IN', 'en-IN')
        """
        if not self.api_key:
            logger.error("Sarvam API Key not configured")
            raise RuntimeError("Sarvam API Key not initialized")

        # speech-to-text-translate/ws endpoint handles translation to English automatically
        params = [
            f"api-subscription-key={self.api_key}",
            "model=saaras:v2.5",
            f"language_code={language_code}",
            "input_audio_codec=pcm_s16le" # Specify codec for PCM audio
        ]
        url = f"{self.ws_url}?{'&'.join(params)}"

        logger.info(f"Connecting to Sarvam AI STT-Translate WebSocket (lang={language_code})")
        
        try:
            async with websockets.connect(url) as ws:
                logger.info("Sarvam AI WebSocket connection established")

                async def send_audio():
                    try:
                        chunk_count = 0
                        async for chunk in audio_generator:
                            if chunk and len(chunk) > 0:
                                # Sarvam Translate WebSocket expects JSON with base64 audio
                                base64_audio = base64.b64encode(chunk).decode('utf-8')
                                audio_message = {
                                    "audio": {
                                        "data": base64_audio,
                                        "sample_rate": "16000",
                                        "encoding": "pcm_s16le"
                                    }
                                }
                                await ws.send(json.dumps(audio_message))
                                chunk_count += 1
                                if chunk_count % 50 == 0:
                                    logger.debug(f"Sent {chunk_count} audio chunks to Sarvam")
                    except Exception as e:
                        logger.error(f"Error sending audio to Sarvam: {e}")

                async def receive_results():
                    try:
                        async for message in ws:
                            data = json.loads(message)
                            
                            # Sarvam response structure is usually: {"type": "data", "data": {"transcript": "..."}}
                            if data.get("type") == "data":
                                result_data = data.get("data", {})
                                transcript = result_data.get("transcript", "")
                                
                                # Note: Streaming typically returns partials. 
                                # Some Sarvam versions use separate partial/final fields.
                                # For now, we assume if it's in the 'data' event, it's a valid transcript segment.
                                if transcript and transcript.strip():
                                    # Sarvam STTT often provides is_final inside the data object
                                    is_final = result_data.get("is_final", False)
                                    # callback expects (text, is_partial)
                                    await callback(transcript, not is_final)
                    except Exception as e:
                        logger.debug(f"Sarvam receiver closed: {e}")

                # Run concurrently
                await asyncio.gather(send_audio(), receive_results())
                logger.info("Sarvam AI streaming completed")

        except Exception as e:
            logger.error(f"Sarvam AI WebSocket error: {e}", exc_info=True)
            raise


class TranscriptionService:
    """Service for handling real-time transcription and translation using Sarvam AI"""
    
    def __init__(self):
        self.active_sessions: Dict[str, List[dict]] = {}
        self.subscribers: Dict[str, List[Callable]] = {}
        self.session_metadata: Dict[str, dict] = {} 
        self.default_target_language = "en"
        self.sarvam_service = None
        self.transcription_dir = "transcription"
        
        # Create transcription directory
        if not os.path.exists(self.transcription_dir):
            os.makedirs(self.transcription_dir)
        
        # Initialize Sarvam service
        self.sarvam_service = SarvamService()
        logger.info(f"TranscriptionService initialized - Sarvam Available: {SARVAM_AVAILABLE}")
    
    async def start_session(self, session_id: str, metadata: dict = None) -> bool:
        """Initialize a new transcription session"""
        if session_id not in self.active_sessions:
            self.active_sessions[session_id] = []
            self.subscribers[session_id] = []
            self.session_metadata[session_id] = metadata or {}
            logger.info(f"Transcription session started: {session_id}")
            return True
        logger.warning(f"Session {session_id} already exists")
        return False
    
    async def end_session(self, session_id: str) -> Optional[List[dict]]:
        """End a transcription session, save to file, and return transcripts"""
        if session_id in self.active_sessions:
            transcripts = self.active_sessions.pop(session_id)
            self.subscribers.pop(session_id, None)
            metadata = self.session_metadata.pop(session_id, {})
            
            await self._save_transcription_to_file(session_id, transcripts, metadata)
            
            logger.info(f"Transcription session ended: {session_id} ({len(transcripts)} transcripts)")
            return transcripts
        logger.warning(f"Session {session_id} not found")
        return None
    
    async def _save_transcription_to_file(self, session_id: str, transcripts: List[dict], metadata: dict):
        """Save transcripts to a JSON file"""
        try:
            timestamp = int(datetime.utcnow().timestamp())
            filename = f"{self.transcription_dir}/{session_id}_{timestamp}.json"
            
            data = {
                "session_id": session_id,
                "metadata": metadata,
                "transcripts": transcripts,
                "saved_at": datetime.utcnow().isoformat()
            }
            
            async with aiofiles.open(filename, "w") as f:
                await f.write(json.dumps(data, indent=2))
                
            logger.info(f"Transcription saved to {filename}")
        except Exception as e:
            logger.error(f"Error saving transcription file: {e}", exc_info=True)

    async def add_transcript(
        self,
        session_id: str,
        speaker: str,
        text: str,
        source_language: str = "hi-IN",
        is_final: bool = True,
        metadata: dict = None,
        skip_translation: bool = False
    ) -> Optional[dict]:
        """Add a transcript entry, translate if needed, and broadcast to subscribers"""
        
        # Auto-create session if it doesn't exist
        if session_id not in self.active_sessions:
            await self.start_session(session_id, metadata)
            logger.info(f"Auto-created session {session_id}")
        
        # Metadata update
        if metadata and session_id in self.session_metadata:
            self.session_metadata[session_id].update(metadata)
        
        # In this version, translation ONLY happens via the WebSocket audio stream.
        # Text-based transcripts added here are stored as-is since REST translation is disabled.
        translated_text = text
        detected_language = source_language
        confidence = 1.0
        
        if skip_translation:
            # If skipping translation, it means text is already translated (to English) by the WebSocket
            source_language = "en-IN"
            detected_language = "en-IN"
        
        # Create transcript entry
        transcript_entry = {
            "type": "transcript",
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "speaker": speaker,
            "original_text": text,
            "translated_text": translated_text,
            "source_language": detected_language,
            "target_language": self.default_target_language,
            "confidence": confidence,
            "timestamp": datetime.utcnow().isoformat(),
            "is_final": is_final
        }
        
        # Only store final transcripts to avoid duplicates
        if is_final:
            self.active_sessions[session_id].append(transcript_entry)
            logger.debug(f"Added final transcript to session {session_id}: {text[:50]}...")
        
        # Notify all subscribers (both partial and final)
        await self._notify_subscribers(session_id, transcript_entry)
        
        return transcript_entry
    
    async def process_audio_stream(
        self, 
        session_id: str, 
        audio_generator, 
        speaker: str = "User",
        source_language: str = "auto"
    ):
        """
        Process audio stream from a generator (e.g., WebSocket).
        Audio must be PCM format, 16kHz sample rate, 16-bit depth.
        """
        if not self.sarvam_service:
            logger.error("Sarvam service not available - cannot process audio stream")
            raise RuntimeError("Sarvam service not initialized")
        
        # Ensure session exists
        if session_id not in self.active_sessions:
            await self.start_session(session_id)
            logger.info(f"Auto-started session for audio stream: {session_id}")
        
        logger.info(f"Starting audio stream processing for session {session_id}, language: {source_language}")
        
        # Map common language codes for Sarvam
        # For 'auto' we'll default to 'hi-IN' but Sarvam model supports auto-detection
        # If we pass hi-IN, it often works as a baseline for other Indic languages too
        language_code = "hi-IN" 
        if source_language and source_language != "auto":
            language_code = source_language
        
        async def handle_transcript_text(text: str, is_partial: bool):
            """Callback for handling transcribed text"""
            if not text or not text.strip():
                return
            
            try:
                # Add transcript
                # Note: In translate mode, Sarvam's 'text' is already English
                await self.add_transcript(
                    session_id=session_id,
                    speaker=speaker,
                    text=text,
                    source_language=source_language,
                    is_final=not is_partial,
                    skip_translation=True # Already translated by the STT-Translate endpoint
                )
                
                logger.info(
                    f"[{session_id}] {'PARTIAL' if is_partial else 'FINAL'}: {text}"
                )
                
            except Exception as e:
                logger.error(f"Error adding transcript: {e}", exc_info=True)
        
        # Start streaming transcription
        try:
            await self.sarvam_service.start_streaming_transcription(
                audio_generator, 
                handle_transcript_text,
                language_code=language_code
            )
            logger.info(f"Audio stream processing completed for session {session_id}")
        except Exception as e:
            logger.error(f"Audio stream processing failed: {e}", exc_info=True)
            raise

    async def _notify_subscribers(self, session_id: str, transcript: dict):
        """Notify all subscribers of a new transcript"""
        if session_id in self.subscribers:
            for callback in self.subscribers[session_id]:
                try:
                    await callback(transcript)
                except Exception as e:
                    logger.error(f"Error notifying subscriber: {e}", exc_info=True)
    
    def subscribe(self, session_id: str, callback: Callable):
        """Subscribe to transcription updates for a session"""
        if session_id not in self.subscribers:
            self.subscribers[session_id] = []
        self.subscribers[session_id].append(callback)
        logger.info(f"Added subscriber to session {session_id}")
    
    def unsubscribe(self, session_id: str, callback: Callable):
        """Unsubscribe from transcription updates"""
        if session_id in self.subscribers:
            try:
                self.subscribers[session_id].remove(callback)
                logger.info(f"Removed subscriber from session {session_id}")
            except ValueError:
                logger.warning(f"Subscriber not found in session {session_id}")

    def get_transcripts(self, session_id: str) -> List[dict]:
        """Get all transcripts for a session"""
        return self.active_sessions.get(session_id, [])

# Global singleton instance
transcription_service = TranscriptionService()


# Claude bkp 

"""
Transcription Service for real-time speech-to-text with automatic translation to English
Uses Sarvam AI with automatic language detection - supports ANY language input
Optimized for LiveKit audio streams with automatic resampling
"""
import asyncio
from typing import Optional, Dict, List, Callable
from datetime import datetime
import json
import uuid
import os
import aiofiles
import logging
import websockets
import base64
import audioop
from config import settings

logger = logging.getLogger(__name__)

# Sarvam AI Configuration
SARVAM_AVAILABLE = bool(settings.SARVAM_API_KEY)

class SarvamService:
    """
    Sarvam AI Services Wrapper for Streaming STT with Automatic Language Detection and Translation to English
    
    Key Features:
    - Automatic language detection (no need to specify language)
    - Automatic translation to English
    - Supports 11+ Indian languages + code-mixed speech
    - Real-time streaming via WebSocket
    """
    
    def __init__(self):
        self.api_key = settings.SARVAM_API_KEY
        self.ws_url = "wss://api.sarvam.ai/speech-to-text-translate/ws"
        
        if not SARVAM_AVAILABLE:
            logger.warning("Sarvam API Key not found in settings. Real-time transcription will be disabled.")

    async def start_streaming_transcription(
        self, 
        audio_generator, 
        callback: Callable,
        input_sample_rate: int = 48000,
        high_vad_sensitivity: bool = True,
        flush_signal: bool = False
    ):
        """
        Start streaming audio to Sarvam AI STT-Translate with AUTOMATIC language detection.
        
        Features:
        - Automatically detects ANY spoken language
        - Automatically translates to English
        - Handles LiveKit audio (resamples from 48kHz to 16kHz)
        - Supports code-mixed speech (multiple languages in same audio)
        
        Args:
            audio_generator: Async iterator yielding PCM audio bytes
            callback: Async function(text: str, is_partial: bool, detected_language: str) to handle transcripts
            input_sample_rate: Sample rate of input audio (default: 48000 for LiveKit)
            high_vad_sensitivity: Enable high VAD sensitivity for better speech detection
            flush_signal: Force immediate processing without waiting for silence
        """
        if not self.api_key:
            logger.error("Sarvam API Key not configured")
            raise RuntimeError("Sarvam API Key not initialized")

        # Sarvam requires 16kHz PCM audio
        # The speech-to-text-translate endpoint automatically detects language and translates to English
        params = [
            f"api-subscription-key={self.api_key}",
            "model=saaras:v2.5",  # Latest Saaras model with best auto-detection
            "input_audio_codec=pcm_s16le",  # Required for PCM audio
            "sample_rate=16000"  # Sarvam requires 16kHz
        ]
        
        # Add optional parameters
        if high_vad_sensitivity:
            params.append("high_vad_sensitivity=true")
        if flush_signal:
            params.append("flush_signal=true")
        
        # NOTE: We do NOT pass language_code parameter
        # When language_code is omitted, Saaras automatically detects the language
        # and translates to English
        
        url = f"{self.ws_url}?{'&'.join(params)}"

        logger.info(
            f"Connecting to Sarvam AI STT-Translate WebSocket\n"
            f"  Mode: Automatic language detection + translation to English\n"
            f"  Input sample rate: {input_sample_rate}Hz\n"
            f"  Sarvam sample rate: 16000Hz\n"
            f"  VAD sensitivity: {'High' if high_vad_sensitivity else 'Normal'}"
        )
        
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=10
                ) as ws:
                    logger.info("Sarvam AI WebSocket connection established")
                    
                    # Track connection state
                    is_running = True
                    send_task = None
                    receive_task = None

                    async def send_audio():
                        """Send audio chunks to Sarvam WebSocket with automatic resampling"""
                        nonlocal is_running
                        try:
                            chunk_count = 0
                            async for chunk in audio_generator:
                                if not is_running:
                                    break
                                    
                                if chunk and len(chunk) > 0:
                                    # Resample audio if needed (LiveKit typically sends 48kHz)
                                    if input_sample_rate != 16000:
                                        try:
                                            # audioop.ratecv: (fragment, width, nchannels, inrate, outrate, state)
                                            # Resample from input_sample_rate to 16000Hz
                                            resampled_chunk, _ = audioop.ratecv(
                                                chunk, 
                                                2,  # 2 bytes per sample (16-bit)
                                                1,  # mono
                                                input_sample_rate,
                                                16000,  # Target: 16kHz for Sarvam
                                                None  # state
                                            )
                                            chunk = resampled_chunk
                                        except Exception as e:
                                            logger.error(f"Error resampling audio: {e}")
                                            # Use original chunk if resampling fails
                                    
                                    # Sarvam expects JSON with base64-encoded audio
                                    base64_audio = base64.b64encode(chunk).decode('utf-8')
                                    audio_message = {
                                        "audio": {
                                            "data": base64_audio,
                                            "sample_rate": "16000",  # Always 16kHz after resampling
                                            "encoding": "pcm_s16le"
                                        }
                                    }
                                    
                                    try:
                                        await ws.send(json.dumps(audio_message))
                                        chunk_count += 1
                                        
                                        if chunk_count % 50 == 0:
                                            logger.debug(f"Sent {chunk_count} audio chunks to Sarvam")
                                    except websockets.exceptions.ConnectionClosed:
                                        logger.warning("WebSocket closed while sending audio")
                                        is_running = False
                                        break
                                        
                            logger.info(f"Audio sending completed. Total chunks: {chunk_count}")
                            
                        except asyncio.CancelledError:
                            logger.info("Audio sender task cancelled")
                            raise
                        except Exception as e:
                            logger.error(f"Error sending audio to Sarvam: {e}", exc_info=True)
                            is_running = False

                    async def receive_results():
                        """Receive transcription results from Sarvam WebSocket"""
                        nonlocal is_running
                        try:
                            async for message in ws:
                                if not is_running:
                                    break
                                
                                try:
                                    data = json.loads(message)
                                    msg_type = data.get("type")
                                    
                                    if msg_type == "data":
                                        # Transcription data (already translated to English)
                                        result_data = data.get("data", {})
                                        transcript = result_data.get("transcript", "").strip()
                                        
                                        if transcript:
                                            # Check if this is a final transcript
                                            is_final = result_data.get("is_final", True)
                                            
                                            # Get detected language if available
                                            detected_language = result_data.get("language_code", "auto")
                                            
                                            # Log metrics if available
                                            metrics = result_data.get("metrics", {})
                                            if metrics:
                                                logger.debug(
                                                    f"Metrics - Audio Duration: {metrics.get('audio_duration', 'N/A')}s, "
                                                    f"Processing Latency: {metrics.get('processing_latency', 'N/A')}s"
                                                )
                                            
                                            # Callback expects (text, is_partial, detected_language)
                                            is_partial = not is_final
                                            await callback(transcript, is_partial, detected_language)
                                    
                                    elif msg_type == "vad_start":
                                        # Voice activity started
                                        logger.debug("VAD: Speech detected")
                                    
                                    elif msg_type == "vad_end":
                                        # Voice activity ended
                                        logger.debug("VAD: Speech ended")
                                    
                                    elif msg_type == "error":
                                        # Error from Sarvam
                                        error_msg = data.get("message", "Unknown error")
                                        logger.error(f"Sarvam API error: {error_msg}")
                                        is_running = False
                                        break
                                    
                                    else:
                                        logger.debug(f"Received unknown message type: {msg_type}")
                                        
                                except json.JSONDecodeError as e:
                                    logger.error(f"Failed to parse WebSocket message: {e}")
                                except Exception as e:
                                    logger.error(f"Error processing WebSocket message: {e}", exc_info=True)
                                    
                        except websockets.exceptions.ConnectionClosed:
                            logger.info("WebSocket connection closed by server")
                            is_running = False
                        except asyncio.CancelledError:
                            logger.info("Receiver task cancelled")
                            raise
                        except Exception as e:
                            logger.error(f"Unexpected error in receiver: {e}", exc_info=True)
                            is_running = False

                    # Run sender and receiver concurrently
                    try:
                        send_task = asyncio.create_task(send_audio())
                        receive_task = asyncio.create_task(receive_results())
                        
                        # Wait for both tasks
                        await asyncio.gather(send_task, receive_task, return_exceptions=True)
                        
                        logger.info("Sarvam AI streaming completed successfully")
                        return  # Success, exit retry loop
                        
                    except Exception as e:
                        logger.error(f"Error during WebSocket communication: {e}", exc_info=True)
                        is_running = False
                        
                    finally:
                        # Clean up tasks
                        is_running = False
                        if send_task and not send_task.done():
                            send_task.cancel()
                            try:
                                await send_task
                            except asyncio.CancelledError:
                                pass
                        if receive_task and not receive_task.done():
                            receive_task.cancel()
                            try:
                                await receive_task
                            except asyncio.CancelledError:
                                pass

            except websockets.exceptions.WebSocketException as e:
                retry_count += 1
                logger.error(f"WebSocket error (attempt {retry_count}/{max_retries}): {e}")
                
                if retry_count < max_retries:
                    wait_time = 2 ** retry_count  # Exponential backoff
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("Max retries reached. Giving up.")
                    raise
                    
            except Exception as e:
                logger.error(f"Unexpected error in Sarvam streaming: {e}", exc_info=True)
                raise


class TranscriptionService:
    """
    Service for handling real-time transcription and automatic translation to English
    
    Features:
    - Automatic language detection (supports 11+ languages)
    - Automatic translation to English
    - Real-time streaming from LiveKit audio
    - Handles code-mixed speech
    """
    
    def __init__(self):
        self.active_sessions: Dict[str, List[dict]] = {}
        self.subscribers: Dict[str, List[Callable]] = {}
        self.session_metadata: Dict[str, dict] = {} 
        self.default_target_language = "en"
        self.sarvam_service = None
        self.transcription_dir = "transcription"
        
        # Create transcription directory
        if not os.path.exists(self.transcription_dir):
            os.makedirs(self.transcription_dir)
        
        # Initialize Sarvam service
        self.sarvam_service = SarvamService()
        logger.info(f"TranscriptionService initialized - Sarvam Available: {SARVAM_AVAILABLE}")
    
    async def start_session(self, session_id: str, metadata: dict = None) -> bool:
        """Initialize a new transcription session"""
        if session_id not in self.active_sessions:
            self.active_sessions[session_id] = []
            self.subscribers[session_id] = []
            self.session_metadata[session_id] = metadata or {}
            logger.info(f"Transcription session started: {session_id}")
            return True
        logger.warning(f"Session {session_id} already exists")
        return False
    
    async def end_session(self, session_id: str) -> Optional[List[dict]]:
        """End a transcription session, save to file, and return transcripts"""
        if session_id in self.active_sessions:
            transcripts = self.active_sessions.pop(session_id)
            self.subscribers.pop(session_id, None)
            metadata = self.session_metadata.pop(session_id, {})
            
            await self._save_transcription_to_file(session_id, transcripts, metadata)
            
            logger.info(f"Transcription session ended: {session_id} ({len(transcripts)} transcripts)")
            return transcripts
        logger.warning(f"Session {session_id} not found")
        return None
    
    async def _save_transcription_to_file(self, session_id: str, transcripts: List[dict], metadata: dict):
        """Save transcripts to a JSON file"""
        try:
            timestamp = int(datetime.utcnow().timestamp())
            filename = f"{self.transcription_dir}/{session_id}_{timestamp}.json"
            
            data = {
                "session_id": session_id,
                "metadata": metadata,
                "transcripts": transcripts,
                "saved_at": datetime.utcnow().isoformat()
            }
            
            async with aiofiles.open(filename, "w") as f:
                await f.write(json.dumps(data, indent=2))
                
            logger.info(f"Transcription saved to {filename}")
        except Exception as e:
            logger.error(f"Error saving transcription file: {e}", exc_info=True)

    async def add_transcript(
        self,
        session_id: str,
        speaker: str,
        text: str,
        detected_language: str = "auto",
        is_final: bool = True,
        metadata: dict = None
    ) -> Optional[dict]:
        """Add a transcript entry (already translated to English) and broadcast to subscribers"""
        
        # Auto-create session if it doesn't exist
        if session_id not in self.active_sessions:
            await self.start_session(session_id, metadata)
            logger.info(f"Auto-created session {session_id}")
        
        # Metadata update
        if metadata and session_id in self.session_metadata:
            self.session_metadata[session_id].update(metadata)
        
        # Text is already in English from Sarvam's speech-to-text-translate API
        # detected_language tells us what language was spoken
        
        # Create transcript entry
        transcript_entry = {
            "type": "transcript",
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "speaker": speaker,
            "text": text,  # Already in English
            "detected_language": detected_language,  # Original language that was auto-detected
            "target_language": "en",  # Always English
            "timestamp": datetime.utcnow().isoformat(),
            "is_final": is_final
        }
        
        # Only store final transcripts to avoid duplicates
        if is_final:
            self.active_sessions[session_id].append(transcript_entry)
            logger.debug(f"Added final transcript to session {session_id}: {text[:50]}...")
        
        # Notify all subscribers (both partial and final)
        await self._notify_subscribers(session_id, transcript_entry)
        
        return transcript_entry
    
    async def process_audio_stream(
        self, 
        session_id: str, 
        audio_generator, 
        speaker: str = "User",
        input_sample_rate: int = 48000,
        high_vad_sensitivity: bool = True,
        flush_signal: bool = False
    ):
        """
        Process audio stream from LiveKit or any other source with AUTOMATIC language detection.
        
        The audio will be:
        1. Automatically detected for language (supports 11+ languages + code-mixed)
        2. Transcribed in real-time
        3. Automatically translated to English
        
        Args:
            session_id: Unique session identifier
            audio_generator: Async iterator yielding PCM audio chunks
            speaker: Speaker name for attribution
            input_sample_rate: Sample rate of input audio (48000 for LiveKit, 16000 for others)
            high_vad_sensitivity: Enable high VAD sensitivity for better speech detection
            flush_signal: Force immediate processing without waiting for silence
        """
        if not self.sarvam_service:
            logger.error("Sarvam service not available - cannot process audio stream")
            raise RuntimeError("Sarvam service not initialized")
        
        # Ensure session exists
        if session_id not in self.active_sessions:
            await self.start_session(session_id)
            logger.info(f"Auto-started session for audio stream: {session_id}")
        
        logger.info(
            f"Starting audio stream processing for session {session_id}\n"
            f"  Mode: Automatic language detection → English translation\n"
            f"  Input sample rate: {input_sample_rate}Hz\n"
            f"  VAD: {high_vad_sensitivity}, Flush: {flush_signal}"
        )
        
        # Deduplicate transcripts
        last_transcript = ""
        
        async def handle_transcript_text(text: str, is_partial: bool, detected_language: str):
            """Callback for handling transcribed and translated text"""
            nonlocal last_transcript
            
            if not text or not text.strip():
                return
            
            # Skip if it's the same as the last transcript (deduplication)
            if is_partial and text == last_transcript:
                return
            
            last_transcript = text
            
            try:
                # Add transcript - text is already in English from STT-Translate endpoint
                await self.add_transcript(
                    session_id=session_id,
                    speaker=speaker,
                    text=text,  # Already in English
                    detected_language=detected_language,  # Original detected language
                    is_final=not is_partial
                )
                
                status = "PARTIAL" if is_partial else "FINAL"
                lang_info = f"[{detected_language}]" if detected_language != "auto" else ""
                logger.info(f"[{session_id}] {status} {lang_info}: {text}")
                
            except Exception as e:
                logger.error(f"Error adding transcript: {e}", exc_info=True)
        
        # Start streaming transcription with automatic language detection
        try:
            await self.sarvam_service.start_streaming_transcription(
                audio_generator, 
                handle_transcript_text,
                input_sample_rate=input_sample_rate,
                high_vad_sensitivity=high_vad_sensitivity,
                flush_signal=flush_signal
            )
            logger.info(f"Audio stream processing completed for session {session_id}")
            
        except Exception as e:
            logger.error(f"Audio stream processing failed: {e}", exc_info=True)
            raise

    async def _notify_subscribers(self, session_id: str, transcript: dict):
        """Notify all subscribers of a new transcript"""
        if session_id in self.subscribers:
            for callback in self.subscribers[session_id]:
                try:
                    await callback(transcript)
                except Exception as e:
                    logger.error(f"Error notifying subscriber: {e}", exc_info=True)
    
    def subscribe(self, session_id: str, callback: Callable):
        """Subscribe to transcription updates for a session"""
        if session_id not in self.subscribers:
            self.subscribers[session_id] = []
        self.subscribers[session_id].append(callback)
        logger.info(f"Added subscriber to session {session_id}")
    
    def unsubscribe(self, session_id: str, callback: Callable):
        """Unsubscribe from transcription updates"""
        if session_id in self.subscribers:
            try:
                self.subscribers[session_id].remove(callback)
                logger.info(f"Removed subscriber from session {session_id}")
            except ValueError:
                logger.warning(f"Subscriber not found in session {session_id}")

    def get_transcripts(self, session_id: str) -> List[dict]:
        """Get all transcripts for a session"""
        return self.active_sessions.get(session_id, [])

# Global singleton instance
transcription_service = TranscriptionService()