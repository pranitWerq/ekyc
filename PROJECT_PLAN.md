# eKYC Platform - Project Planning Document

## 📋 Project Overview

The eKYC (Electronic Know Your Customer) Platform is a comprehensive identity verification system that enables remote customer onboarding through a multi-step verification process. The platform supports document verification, face matching, liveness detection, and video-based verification with live transcription for enhanced communication.

**Version:** 2.0  
**Last Updated:** February 3, 2026  
**Technology Stack:** Python FastAPI, SQLAlchemy, LiveKit, JavaScript, HTML/CSS

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (HTML/JS)                       │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────────┐ │
│  │  Auth   │ │Document │ │  Face   │ │Liveness │ │Video Call  │ │
│  │  View   │ │ Upload  │ │ Match   │ │  Check  │ │+Transcript │ │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                             │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────────┐ │
│  │  Auth   │ │   KYC   │ │Document │ │  Face   │ │   Video    │ │
│  │ Routes  │ │ Routes  │ │ Routes  │ │ Routes  │ │  Routes    │ │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Services Layer                           │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────────┐ │
│  │  OCR    │ │  Face   │ │Liveness │ │LiveKit  │ │Transcription│ │
│  │Service  │ │Service  │ │ Service │ │ Service │ │  Service   │ │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      External Services                           │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐ │
│  │  LiveKit Cloud  │  │  Google Cloud   │  │     SQLite       │ │
│  │  (Video/Audio)  │  │  Speech-to-Text │  │    Database      │ │
│  └─────────────────┘  └─────────────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✅ Existing Features

### 1. User Authentication
- **Registration**: New users can create accounts with email and password
- **Login**: Secure JWT-based authentication
- **Role-based Access**: Separate flows for regular users and admin agents
- **Session Management**: Token-based session handling with localStorage

### 2. Document Verification (Step 1)
- **Document Upload**: Support for Passport, National ID, Driver's License
- **OCR Processing**: Automatic extraction of:
  - Full Name
  - Date of Birth
  - ID Number
- **File Validation**: Size and type restrictions
- **Secure Storage**: Documents stored with unique identifiers

### 3. Face Verification (Step 2)
- **Selfie Capture**: Real-time camera capture for user selfie
- **Face Matching**: Compare selfie against document photo
- **Match Score**: Configurable threshold (default 60%)
- **Fallback Support**: OpenCV fallback if face_recognition unavailable

### 4. Liveness Detection (Step 3)
- **Action-based Verification**: 
  - Blink Detection
  - Smile Detection
  - Head Turn Detection (optional)
- **Anti-Spoofing**: Prevents photo/video replay attacks
- **MediaPipe Integration**: Advanced facial landmark detection
- **Haar Cascade Fallback**: Works without MediaPipe

### 5. Video Verification (Step 4)
- **Two-way Video Call**: LiveKit-powered video conferencing
- **Room Management**: Automatic room creation per KYC session
- **Agent Assignment**: Admin agents can join pending calls
- **Recording Capability**: Support for call recording
- **Call Controls**: Mute/unmute audio, enable/disable video

### 6. Admin Panel
- **Dashboard Statistics**: Pending, Approved, Rejected counts
- **Session Management**: View and filter all KYC sessions
- **Review Modal**: Detailed view of each verification step
- **Approval Workflow**: Approve/Reject with notes
- **Agent Call Join**: One-click join to video sessions

### 7. Status Tracking
- **Progress Indicators**: Visual stepper showing completion
- **Session Status**: Real-time status updates
- **Verification Milestones**: Track each completed step

---

## 🆕 New Feature: Live Transcription with Translation

### Feature Overview
Enable real-time speech-to-text transcription during video calls, with automatic translation to English. This allows verification agents to understand users speaking in any language while viewing an English transcript.

### User Stories

1. **As a user**, I can speak in my native language during the video verification call, knowing the agent can understand me through live transcription.

2. **As an admin agent**, I can see live English transcription of what the user is saying, regardless of the language they speak.

3. **As an admin**, I can review the full transcript after the call ends for compliance and record-keeping.

### Technical Requirements

#### Frontend Requirements
- Transcription panel in video call UI (agent view)
- Real-time transcript updates via WebSocket
- Auto-scroll with latest messages
- Speaker identification (User/Agent)
- Transcript download option
- Language detection indicator

#### Backend Requirements
- WebSocket endpoint for real-time transcription
- Integration with speech-to-text API (Google Speech-to-Text/Deepgram)
- Translation service integration (Google Translate)
- Transcript storage in database
- Language detection service

#### Database Schema Updates
```sql
-- Add transcription support to video_sessions
ALTER TABLE video_sessions ADD COLUMN transcript TEXT;
ALTER TABLE video_sessions ADD COLUMN detected_language VARCHAR(10);

-- New table for real-time transcript segments
CREATE TABLE transcript_segments (
    id VARCHAR(36) PRIMARY KEY,
    video_session_id VARCHAR(36) REFERENCES video_sessions(id),
    speaker VARCHAR(20),  -- 'user' or 'agent'
    original_text TEXT,
    translated_text TEXT,
    original_language VARCHAR(10),
    timestamp DATETIME,
    confidence FLOAT
);
```

### Implementation Plan

#### Phase 1: Infrastructure Setup
1. Add speech-to-text service integration
2. Add translation service integration
3. Create transcription WebSocket endpoint
4. Update database schema

#### Phase 2: Backend Implementation
1. Create TranscriptionService class
2. Implement audio stream processing
3. Add translation pipeline
4. Store transcripts in database

#### Phase 3: Frontend Implementation
1. Add transcription panel UI
2. Implement WebSocket connection
3. Add real-time transcript display
4. Add transcript download functionality

#### Phase 4: Testing & Polish
1. Test with multiple languages
2. Optimize latency
3. Add error handling
4. UI/UX improvements

---

## 📁 Project Structure

```
ekyc_v2/
├── main.py                    # FastAPI application entry
├── config.py                  # Configuration settings
├── requirements.txt           # Python dependencies
├── PROJECT_PLAN.md           # This document
├── database/
│   ├── database.py           # Database connection
│   ├── models.py             # SQLAlchemy models
│   └── schemas.py            # Pydantic schemas
├── routes/
│   ├── auth.py               # Authentication endpoints
│   ├── kyc.py                # KYC session management
│   ├── documents.py          # Document upload/OCR
│   ├── face.py               # Face/Liveness verification
│   ├── video.py              # Video call management
│   └── transcription.py      # NEW: Transcription endpoints
├── services/
│   ├── ocr_service.py        # OCR processing
│   ├── face_service.py       # Face detection/matching
│   ├── liveness_service.py   # Liveness detection
│   ├── livekit_service.py    # LiveKit integration
│   └── transcription_service.py  # NEW: Transcription service
├── static/
│   ├── index.html            # Main HTML page
│   ├── css/
│   │   └── style.css         # Styles
│   └── js/
│       └── app.js            # Frontend JavaScript
└── uploads/                  # File storage
    ├── documents/
    └── faces/
```

---

## 🔧 Configuration

### Environment Variables (.env)
```bash
# App Settings
APP_NAME=eKYC Platform
DEBUG=true

# Security
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Database
DATABASE_URL=sqlite+aiosqlite:///./ekyc.db

# File Storage
UPLOAD_DIR=uploads
MAX_FILE_SIZE=10485760

# LiveKit
LIVEKIT_URL=wss://your-livekit-server.com
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret

# Face Verification
FACE_MATCH_THRESHOLD=0.6

# NEW: Transcription Settings
DEEPGRAM_API_KEY=your-deepgram-key
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
DEFAULT_TRANSLATION_LANGUAGE=en
```

---

## 🚀 API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | User registration |
| POST | `/auth/login` | User login |
| GET | `/auth/me` | Get current user |

### KYC Sessions
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/kyc/sessions` | Create new session |
| GET | `/kyc/sessions/current` | Get current session |
| GET | `/kyc/admin/sessions` | List all sessions (admin) |
| PUT | `/kyc/admin/sessions/{id}/review` | Review session (admin) |

### Documents
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/documents/upload` | Upload document |
| GET | `/documents/session/{id}` | Get session documents |

### Face Verification
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/face/verify` | Verify face match |
| POST | `/face/liveness/check` | Check liveness |

### Video
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/video/room` | Create/join video room |
| POST | `/video/room/{id}/join-agent` | Agent joins room |
| POST | `/video/room/{id}/end` | End video session |

### NEW: Transcription
| Method | Endpoint | Description |
|--------|----------|-------------|
| WS | `/ws/transcription/{session_id}` | Real-time transcription stream |
| GET | `/transcription/{session_id}` | Get full transcript |
| GET | `/transcription/{session_id}/download` | Download transcript |

---

## 📊 KYC Status Flow

```
PENDING → DOCUMENT_UPLOADED → FACE_VERIFIED → LIVENESS_PASSED → VIDEO_COMPLETED → APPROVED
                                                                              ↘ REJECTED
```

---

## 🎨 UI Components

### Transcription Panel (New)
```
┌─────────────────────────────────────────┐
│  📝 Live Transcription          EN 🌐  │
├─────────────────────────────────────────┤
│                                         │
│  [12:30:15] User (Hindi → EN):          │
│  "Hello, I am here for verification"   │
│                                         │
│  [12:30:22] Agent:                      │
│  "Please show your ID document"        │
│                                         │
│  [12:30:35] User (Hindi → EN):          │
│  "Yes, here is my passport"            │
│                                         │
│  ▼ Auto-scroll enabled                 │
├─────────────────────────────────────────┤
│  [📥 Download] [🔄 Clear]              │
└─────────────────────────────────────────┘
```

---

## 📅 Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| Phase 1 | 1 day | Infrastructure, API setup |
| Phase 2 | 2 days | Backend transcription service |
| Phase 3 | 1 day | Frontend UI integration |
| Phase 4 | 1 day | Testing and polish |

**Total Estimated Time:** 5 days

---

## 🔒 Security Considerations

1. **Data Privacy**: Transcripts contain sensitive conversation data
2. **Encryption**: WebSocket connections must use WSS
3. **Access Control**: Only authenticated agents can view transcripts
4. **Data Retention**: Implement transcript deletion policies
5. **Audit Logging**: Log all transcript access

---

## 📝 Notes

- The transcription feature requires an active internet connection for API calls
- Audio quality affects transcription accuracy
- Translation may introduce slight delays (100-500ms)
- Consider fallback for unsupported languages
