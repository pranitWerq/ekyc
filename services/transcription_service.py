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
import audioop
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
            logger.warning("Sarvam API Key not found. Real-time transcription disabled.")

    async def start_streaming_transcription(
        self, 
        audio_generator, 
        on_transcript: Callable,
        on_utterance_end: Callable,
        language_code: str = "auto",
        input_sample_rate: int = 48000
    ):
        """
        Stream audio to Sarvam AI STT-Translate WebSocket.
        
        Args:
            audio_generator: Async iterator yielding PCM audio bytes
            on_transcript: Async function(text, is_partial, lang, original) for transcript updates
            on_utterance_end: Async function() called when VAD detects end of speech
            language_code: Language code for transcription 
            input_sample_rate: Sample rate of input audio (browser is usually 48000)
        """
        if not self.api_key:
            logger.error("Sarvam API Key not configured")
            raise RuntimeError("Sarvam API Key not initialized")

        params = ["model=saaras:v2.5"]
        
        if language_code and language_code != "auto":
            params.append(f"language-code={language_code}")
        else:
            params.append("language-code=unknown")
        
        url = f"{self.ws_url}?{'&'.join(params)}"
        logger.info(f"Connecting to Sarvam STT (lang={language_code}, rate={input_sample_rate})")
        
        subprotocols = [f"api-subscription-key.{self.api_key}"]
        
        last_chunk = None

        # Reconnection loop
        while True: 
            try:
                # Setup connection
                async with websockets.connect(url, subprotocols=subprotocols) as ws:
                    logger.info("Sarvam WebSocket connected")
                    
                    # Reset cancellation event for new connection
                    stop_event = asyncio.Event()

                    async def send_audio():
                        nonlocal last_chunk
                        state = None
                        chunk_count = 0
                        
                        try:
                            # If we have a leftover chunk from previous failed send, try sending it first
                            if last_chunk:
                                encoded = base64.b64encode(last_chunk).decode('utf-8')
                                await ws.send(json.dumps({
                                    "audio": {"data": encoded, "encoding": "audio/wav", "sample_rate": 16000}
                                }))
                                last_chunk = None
                            
                            # Resume consuming the generator
                            async for chunk in audio_generator:
                                if stop_event.is_set():
                                    break
                                    
                                if chunk and len(chunk) > 0:
                                    last_chunk = chunk # Store in case send fails
                                    
                                    # Resample
                                    if input_sample_rate != 16000:
                                        try:
                                            resampled, state = audioop.ratecv(
                                                chunk, 2, 1, input_sample_rate, 16000, state
                                            )
                                            chunk = resampled
                                        except Exception as e:
                                            logger.error(f"Resample error: {e}")
                                    
                                    base64_audio = base64.b64encode(chunk).decode('utf-8')
                                    await ws.send(json.dumps({
                                        "audio": {"data": base64_audio, "encoding": "audio/wav", "sample_rate": 16000}
                                    }))
                                    last_chunk = None # Clear after successful send
                                    chunk_count += 1
                                    
                            # If loop finishes naturally, we are done
                            return True
                                    
                        except websockets.exceptions.ConnectionClosed:
                            logger.warn("Sarvam connection closed during send")
                            return False # Need reconnect
                        except Exception as e:
                            logger.error(f"Error sending audio: {e}")
                            return False # Need reconnect
                        finally:
                            # Signal receiver to stop
                            stop_event.set()

                    async def receive_results():
                        try:
                            async for message in ws:
                                data = json.loads(message)
                                if data.get("type") == "data":
                                    result_data = data.get("data", {})
                                    transcript = result_data.get("transcript", "")
                                    if transcript and transcript.strip():
                                        is_final = result_data.get("is_final", False)
                                        detected_lang = result_data.get("language_code", "auto")
                                        original = result_data.get("original_transcript")
                                        
                                        logger.info(f"Sarvam: '{transcript[:60]}' (final={is_final})")
                                        await on_transcript(transcript, not is_final, detected_lang, original)
                                
                                elif data.get("type") == "events":
                                    signal = data.get("data", {}).get("signal_type", "")
                                    if "end" in signal.lower():
                                        await on_utterance_end()

                        except Exception as e:
                            logger.debug(f"Sarvam receiver closed: {e}")
                        finally:
                            stop_event.set()

                    # Run concurrently
                    send_task = asyncio.create_task(send_audio())
                    recv_task = asyncio.create_task(receive_results())
                    
                    done, pending = await asyncio.wait(
                        [send_task, recv_task], 
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    # If send_audio finished ensuring complete stream consumption
                    if send_task in done:
                        result = send_task.result()
                        if result: # Generator exhausted successfully
                            logger.info("Audio stream finished normally")
                            for task in pending: task.cancel()
                            return # Exit the main loop completely
                    
                    # If we are here, it means either recv failed or send failed (connection drop)
                    # Cancel pending tasks and Loop to reconnect
                    for task in pending: task.cancel()
            
            except asyncio.CancelledError:
                logger.info("Streaming cancelled by client")
                return
            except Exception as e:
                logger.error(f"Sarvam connect error: {e} - Retrying in 1s...")
                await asyncio.sleep(1)


class TranscriptionService:
    """Service for handling real-time transcription and translation using Sarvam AI"""
    
    def __init__(self):
        self.active_sessions: Dict[str, List[dict]] = {}
        self.subscribers: Dict[str, List[Callable]] = {}
        self.session_metadata: Dict[str, dict] = {} 
        self.default_target_language = "en"
        self.sarvam_service = None
        self.transcription_dir = "transcription"
        self.pending_partials: Dict[str, Dict[str, dict]] = {}  # session_id -> {speaker: last_partial}
        self.session_files: Dict[str, str] = {} # session_id -> filename
        
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
            self.pending_partials[session_id] = {}
            
            # Assign a persistent filename for this session
            timestamp = int(datetime.utcnow().timestamp())
            filename = f"{self.transcription_dir}/{session_id}_{timestamp}.json"
            self.session_files[session_id] = filename
            
            logger.info(f"Transcription session started: {session_id} (File: {filename})")
            return True
        return False
    
    async def end_session(self, session_id: str) -> Optional[List[dict]]:
        """End a transcription session, save to file, and return transcripts"""
        if session_id in self.active_sessions:
            # Commit any pending partials as final entries
            await self._commit_all_partials(session_id)

            # Retrieve data before popping
            transcripts = self.active_sessions.get(session_id, [])
            metadata = self.session_metadata.get(session_id, {})
            
            # Final save
            await self._save_transcription_to_file(session_id, transcripts, metadata)
            
            # Clean up
            self.active_sessions.pop(session_id, None)
            self.subscribers.pop(session_id, None)
            metadata = self.session_metadata.pop(session_id, None)
            self.pending_partials.pop(session_id, None)
            self.session_files.pop(session_id, None)
            
            logger.info(f"Session ended: {session_id} ({len(transcripts)} transcripts saved)")
            return transcripts
        logger.warning(f"Session {session_id} not found for ending")
        return None
    
    async def _commit_all_partials(self, session_id: str):
        """Commit all pending partials as final transcripts"""
        pending = self.pending_partials.get(session_id, {})
        for speaker, partial in list(pending.items()):
            if partial:
                partial["is_final"] = True
                self.active_sessions[session_id].append(partial)
                logger.info(f"Committed partial for {speaker}: '{partial.get('original_text', '')[:50]}'")
        # Clear all partials for this session
        if session_id in self.pending_partials:
            self.pending_partials[session_id] = {}

    async def commit_speaker_partial(self, session_id: str, speaker: str):
        """
        Commit the pending partial for a specific speaker as a final transcript.
        Called when VAD detects end of speech (utterance boundary).
        """
        if session_id not in self.pending_partials:
            return
        
        partial = self.pending_partials[session_id].get(speaker)
        if partial and partial.get("original_text", "").strip():
            # Mark as final and store permanently
            partial["is_final"] = True
            self.active_sessions[session_id].append(partial)
            self.pending_partials[session_id].pop(speaker, None)
            
            logger.info(f"[VAD] Committed utterance for {speaker}: '{partial['original_text'][:60]}'")
            
            # Broadcast final version
            await self._notify_subscribers(session_id, partial)
            
            # IMMEDIATE SAVE to prevent data loss
            await self._save_transcription_to_file(session_id)


    async def _save_transcription_to_file(self, session_id: str, transcripts: List[dict] = None, metadata: dict = None):
        """Save transcripts to a JSON file. If args not provided, fetches current state."""
        try:
            # Determine filename
            filename = self.session_files.get(session_id)
            if not filename:
                # Fallback if somehow missing
                timestamp = int(datetime.utcnow().timestamp())
                filename = f"{self.transcription_dir}/{session_id}_{timestamp}.json"
                self.session_files[session_id] = filename

            # Fetch data if not provided (Incremental Save Mode)
            if transcripts is None:
                transcripts = self.active_sessions.get(session_id, [])
            if metadata is None:
                metadata = self.session_metadata.get(session_id, {})

            data = {
                "session_id": session_id,
                "metadata": metadata,
                "transcripts": transcripts,
                "saved_at": datetime.utcnow().isoformat()
            }
            
            async with aiofiles.open(filename, "w") as f:
                await f.write(json.dumps(data, indent=2))
                
            # logger.debug(f"Transcription incrementally saved to {filename}")
        except Exception as e:
            logger.error(f"Error saving transcription file: {e}", exc_info=True)

    async def add_transcript(
        self,
        session_id: str,
        speaker: str,
        text: str,
        source_language: str = "auto",
        is_final: bool = True,
        metadata: dict = None,
        skip_translation: bool = False,
        original_text: str = None
    ) -> Optional[dict]:
        """Add a transcript entry, translate if needed, and broadcast to subscribers"""
        
        # Clean text
        text = text.strip()
        if not text:
            return None
        
        # Ensure source_language is not None
        if not source_language:
            source_language = "auto"
            
        # Auto-create session if it doesn't exist
        if session_id not in self.active_sessions:
            await self.start_session(session_id, metadata)
        
        # Metadata update
        if metadata and session_id in self.session_metadata:
            self.session_metadata[session_id].update(metadata)
        
        # Handle translation status
        translated_text = text
        if skip_translation:
            if not original_text:
                original_text = text
        else:
            original_text = text
        
        # Create transcript entry
        transcript_entry = {
            "type": "transcript",
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "speaker": speaker,
            "original_text": original_text,
            "translated_text": translated_text,
            "source_language": source_language,
            "target_language": self.default_target_language,
            "confidence": 1.0,
            "timestamp": datetime.utcnow().isoformat(),
            "is_final": is_final
        }
        
        if is_final:
            # Final transcript: remove pending partial, store permanently
            if session_id in self.pending_partials:
                self.pending_partials[session_id].pop(speaker, None)
            
            self.active_sessions[session_id].append(transcript_entry)
            
            # IMMEDIATE SAVE
            await self._save_transcription_to_file(session_id)
        else:
            # Partial: update in pending_partials (overwrite previous partial for this speaker)
            if session_id in self.pending_partials:
                self.pending_partials[session_id][speaker] = transcript_entry
        
        # Broadcast to UI (both partials and finals)
        await self._notify_subscribers(session_id, transcript_entry)
        
        return transcript_entry
    
    async def process_audio_stream(
        self, 
        session_id: str, 
        audio_generator, 
        speaker: str = "User",
        source_language: str = "auto",
        input_sample_rate: int = 48000
    ):
        """
        Process audio stream from a generator (e.g., WebSocket).
        Audio is PCM format at 48kHz from browser.
        """
        if not self.sarvam_service:
            logger.error("Sarvam service not available")
            raise RuntimeError("Sarvam service not initialized")
        
        # Ensure session exists
        if session_id not in self.active_sessions:
            await self.start_session(session_id)
        
        logger.info(f"Starting audio processing for {speaker} in session {session_id}")
        
        language_code = source_language if source_language else "auto"
        
        async def handle_transcript(text: str, is_partial: bool, detected_lang: str = "auto", original: str = None):
            """Callback for handling transcribed text from Sarvam"""
            if not text or not text.strip():
                return
            
            try:
                await self.add_transcript(
                    session_id=session_id,
                    speaker=speaker,
                    text=text,
                    source_language=detected_lang,
                    is_final=not is_partial,
                    skip_translation=True,
                    original_text=original
                )
            except Exception as e:
                logger.error(f"Error adding transcript: {e}")
        
        async def handle_utterance_end():
            """Called when VAD detects end of speech — commit the current partial as final"""
            await self.commit_speaker_partial(session_id, speaker)
        
        # Start streaming transcription
        try:
            await self.sarvam_service.start_streaming_transcription(
                audio_generator, 
                on_transcript=handle_transcript,
                on_utterance_end=handle_utterance_end,
                language_code=language_code,
                input_sample_rate=input_sample_rate
            )
            logger.info(f"Audio stream completed for {speaker} in session {session_id}")
        except asyncio.CancelledError:
            logger.info(f"Audio stream cancelled for {speaker} in session {session_id}")
        except Exception as e:
            logger.error(f"Audio stream error for {speaker}: {e}")

    async def _notify_subscribers(self, session_id: str, transcript: dict):
        """Notify all subscribers of a new transcript"""
        if session_id in self.subscribers:
            for callback in self.subscribers[session_id]:
                try:
                    await callback(transcript)
                except Exception as e:
                    logger.error(f"Error notifying subscriber: {e}")
    
    def subscribe(self, session_id: str, callback: Callable):
        """Subscribe to transcription updates for a session"""
        if session_id not in self.subscribers:
            self.subscribers[session_id] = []
        self.subscribers[session_id].append(callback)
    
    def unsubscribe(self, session_id: str, callback: Callable):
        """Unsubscribe from transcription updates"""
        if session_id in self.subscribers:
            try:
                self.subscribers[session_id].remove(callback)
            except ValueError:
                pass

    def get_transcripts(self, session_id: str) -> List[dict]:
        """Get all transcripts for a session"""
        return self.active_sessions.get(session_id, [])

# Global singleton instance
transcription_service = TranscriptionService()