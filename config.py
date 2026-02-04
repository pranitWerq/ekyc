from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os

class Settings(BaseSettings):
    # App settings
    APP_NAME: str = "eKYC Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # Security
    SECRET_KEY: str = "your-default-secret-key-for-dev"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Database
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./ekyc.db"
    
    @property
    def async_database_url(self) -> str:
        """Convert postgres:// to postgresql+asyncpg:// for SQLAlchemy"""
        url = self.DATABASE_URL
        if url and url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url and url.startswith("postgresql://") and "+asyncpg" not in url:
             url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    
    # File storage
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    
    # LiveKit
    LIVEKIT_URL: str = "wss://your-livekit-server.com"
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""

    # Azure Cognitive Services
    AZURE_SPEECH_KEY: Optional[str] = None
    AZURE_SPEECH_REGION: str = "eastus"
    AZURE_TRANSLATOR_KEY: Optional[str] = None
    AZURE_TRANSLATOR_REGION: str = "global"

    # AWS Configuration
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"

    # Face verification threshold
    FACE_MATCH_THRESHOLD: float = 0.6
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

# Create upload directory if it doesn't exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_DIR, "documents"), exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_DIR, "faces"), exist_ok=True)
