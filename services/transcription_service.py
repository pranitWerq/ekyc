"""
Transcription Service for real-time speech-to-text with translation
Uses AWS Transcribe and Translate
"""
import asyncio
from typing import Optional, Dict, List, Callable
from datetime import datetime
import json
import uuid
import os
import aiofiles
from functools import partial

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# Try to import amazon-transcribe, handle failure gracefully if not installed
try:
    from amazon_transcribe.client import TranscribeStreamingClient
    from amazon_transcribe.handlers import TranscriptResultStreamHandler
    from amazon_transcribe.model import TranscriptEvent
    AMAZON_TRANSCRIBE_AVAILABLE = True
except ImportError:
    AMAZON_TRANSCRIBE_AVAILABLE = False
    print("amazon-transcribe package not found. Real-time streaming will not work.")

from config import settings

# AWS Configuration
AWS_AVAILABLE = bool(settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY)

class AWSTranscriptHandler(TranscriptResultStreamHandler):
    """Handler for AWS Transcribe streaming events"""
    def __init__(self, callback):
        super().__init__(callback)

    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        results = transcript_event.transcript.results
        for result in results:
            if not result.alternatives:
                continue
            alternative = result.alternatives[0]
            if alternative.transcript:
                # Call the callback with (text, is_partial, is_final)
                # AWS returns IsPartial. If IsPartial is False, it's final-ish for that segment.
                await self.callback(alternative.transcript, result.is_partial)

class AWSService:
    """AWS Services Wrapper for Transcribe and Translate"""
    
    def __init__(self):
        self.aws_region = settings.AWS_REGION
        self.aws_access_key = settings.AWS_ACCESS_KEY_ID
        self.aws_secret_key = settings.AWS_SECRET_ACCESS_KEY
        
        self.translate_client = None
        self.transcribe_client = None # For batch
        self.streaming_client = None # For real-time
        
        if AWS_AVAILABLE:
            try:
                self.translate_client = boto3.client(
                    'translate',
                    region_name=self.aws_region,
                    aws_access_key_id=self.aws_access_key,
                    aws_secret_access_key=self.aws_secret_key
                )
                self.transcribe_client = boto3.client(
                    'transcribe',
                    region_name=self.aws_region,
                    aws_access_key_id=self.aws_access_key,
                    aws_secret_access_key=self.aws_secret_key
                )
                
                if AMAZON_TRANSCRIBE_AVAILABLE:
                    self.streaming_client = TranscribeStreamingClient(region=self.aws_region)
                
                print("AWS Clients initialized locally")
            except Exception as e:
                print(f"Failed to initialize AWS clients: {e}")

    async def translate(self, text: str, source_lang: str = "auto", target_lang: str = "en") -> dict:
        """Translate text using AWS Translate"""
        if not self.translate_client or not text.strip():
            return {
                "translated_text": text,
                "detected_language": source_lang,
                "confidence": 1.0
            }
        
        try:
            # Run blocking boto3 call in a thread
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                partial(
                    self.translate_client.translate_text,
                    Text=text,
                    SourceLanguageCode=source_lang,
                    TargetLanguageCode=target_lang
                )
            )
            
            return {
                "translated_text": response.get('TranslatedText', text),
                "detected_language": response.get('SourceLanguageCode', source_lang),
                "confidence": 1.0
            }
                        
        except (BotoCoreError, ClientError) as e:
            print(f"AWS translation error: {e}")
        
        return {
            "translated_text": text,
            "detected_language": source_lang,
            "confidence": 0.0
        }

    async def start_streaming_transcription(self, audio_generator, callback: Callable):
        """
        Start streaming audio to AWS Transcribe.
        audio_generator: Async iterator yielding bytes
        callback: Async function to handle transcript text
        """
        if not AMAZON_TRANSCRIBE_AVAILABLE or not self.streaming_client:
            print("Streaming client not available")
            return

        try:
            stream = await self.streaming_client.start_stream_transcription(
                language_code="en-US", # Default to English source for now, or make configurable
                media_sample_rate_hz=16000, # Client must provide 16khz
                media_encoding="pcm"
            )

            # Handler for events
            handler = AWSTranscriptHandler(callback)
            
            # Start processing events
            async def write_chunks():
                async for chunk in audio_generator:
                    await stream.input_stream.send_audio_event(audio_chunk=chunk)
                await stream.input_stream.end_stream()

            # Run both writing and reading
            await asyncio.gather(
                write_chunks(),
                handler.handle_events_from_stream(stream.output_stream)
            )
            
        except Exception as e:
            print(f"Streaming transcription error: {e}")


class TranscriptionService:
    """Service for handling real-time transcription and translation using AWS"""
    
    def __init__(self):
        self.active_sessions: Dict[str, List[dict]] = {}
        self.subscribers: Dict[str, List[Callable]] = {}
        self.session_metadata: Dict[str, dict] = {} 
        self.default_target_language = "en"
        self.aws_service = AWSService()
        self.transcription_dir = "transcription"
        
        if not os.path.exists(self.transcription_dir):
            os.makedirs(self.transcription_dir)
            
        print(f"TranscriptionService initialized - AWS Available: {AWS_AVAILABLE}")
    
    async def start_session(self, session_id: str, metadata: dict = None) -> bool:
        """Initialize a new transcription session"""
        if session_id not in self.active_sessions:
            self.active_sessions[session_id] = []
            self.subscribers[session_id] = []
            if metadata:
                self.session_metadata[session_id] = metadata
            print(f"Transcription session started: {session_id}")
            return True
        return False
    
    async def end_session(self, session_id: str) -> Optional[List[dict]]:
        """End a transcription session, save to file, and return transcripts"""
        if session_id in self.active_sessions:
            transcripts = self.active_sessions.pop(session_id)
            self.subscribers.pop(session_id, None)
            metadata = self.session_metadata.pop(session_id, {})
            
            await self._save_transcription_to_file(session_id, transcripts, metadata)
            
            print(f"Transcription session ended: {session_id}")
            return transcripts
        return None
    
    async def _save_transcription_to_file(self, session_id: str, transcripts: List[dict], metadata: dict):
        """Save transcripts to a file"""
        try:
            filename = f"{self.transcription_dir}/{session_id}_{int(datetime.utcnow().timestamp())}.json"
            data = {
                "session_id": session_id,
                "metadata": metadata,
                "transcripts": transcripts,
                "saved_at": datetime.utcnow().isoformat()
            }
            async with aiofiles.open(filename, "w") as f:
                await f.write(json.dumps(data, indent=2))
        except Exception as e:
            print(f"Error saving transcription file: {e}")

    async def add_transcript(
        self,
        session_id: str,
        speaker: str,
        text: str,
        source_language: str = "auto",
        is_final: bool = True,
        metadata: dict = None
    ) -> Optional[dict]:
        """Add a transcript entry, translate, and broadcast"""
        if session_id not in self.active_sessions:
            await self.start_session(session_id, metadata)
        
        if metadata and session_id in self.session_metadata:
            self.session_metadata[session_id].update(metadata)
        
        # Translate
        translation_result = await self.aws_service.translate(
            text=text,
            source_lang=source_language,
            target_lang=self.default_target_language
        )
        
        transcript_entry = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "speaker": speaker,
            "original_text": text,
            "translated_text": translation_result["translated_text"],
            "source_language": translation_result["detected_language"],
            "target_language": self.default_target_language,
            "confidence": translation_result["confidence"],
            "timestamp": datetime.utcnow().isoformat(),
            "is_final": is_final
        }
        
        if is_final:
            self.active_sessions[session_id].append(transcript_entry)
        
        await self._notify_subscribers(session_id, transcript_entry)
        
        return transcript_entry
    
    async def process_audio_stream(self, session_id: str, audio_generator, speaker: str = "User"):
        """
        Process audio stream from a generator (e.g. WebSocket).
        Sends to AWS Transcribe -> Translates -> Broadcasts.
        """
        async def handle_transcript_text(transcript_obj, is_partial: bool):
            text = transcript_obj.content
            # We only really want to translate/broadcast significant updates or final ones to save quota/noise
            # But "realtime" needs partials.
            if not text:
                return

            if is_partial:
                 # Optional: broadcast partials without translation or simple translation
                 pass
            
            # For this implementation, let's treat chunks as they come.
            # AWS streaming returns incremental updates.
            # 'is_partial' means the sentence isn't done.
            
            # Broadcast the partial/final result
            # Ideally we only translate 'final' segments to save cost/latency, or translate partials if required.
            # Let's simple translate everything for the "Agent can see" requirement.
            
            await self.add_transcript(
                session_id=session_id,
                speaker=speaker,
                text=text,
                source_language="en", # Assuming we told AWS to expect english, or auto if configured
                is_final=not is_partial
            )

        await self.aws_service.start_streaming_transcription(audio_generator, handle_transcript_text)

    async def _notify_subscribers(self, session_id: str, transcript: dict):
        if session_id in self.subscribers:
            for callback in self.subscribers[session_id]:
                try:
                    await callback(transcript)
                except Exception as e:
                    print(f"Error notifying subscriber: {e}")
    
    def subscribe(self, session_id: str, callback: Callable):
        if session_id not in self.subscribers:
            self.subscribers[session_id] = []
        self.subscribers[session_id].append(callback)
    
    def unsubscribe(self, session_id: str, callback: Callable):
        if session_id in self.subscribers:
            try:
                self.subscribers[session_id].remove(callback)
            except ValueError:
                pass

    def get_transcripts(self, session_id: str) -> List[dict]:
        return self.active_sessions.get(session_id, [])

transcription_service = TranscriptionService()
