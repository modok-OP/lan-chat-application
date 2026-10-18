from pathlib import Path
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Project Root is 3 levels up from backend/app/core:
# backend/app/core -> backend/app -> backend -> root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_UPLOAD_DIR = DEFAULT_DATA_DIR / "uploads"
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "lan_chat.db"


class Settings(BaseSettings):
    """Application configuration settings."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "LAN Chat Application"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # Host & Port
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # API Prefix
    API_PREFIX: str = "/api"

    # Security
    SECRET_KEY: str = "lan-chat-development-secret-key-change-in-production"
    SESSION_COOKIE_NAME: str = "lan_chat_session"
    SESSION_MAX_AGE_SECONDS: int = 86400 * 7  # 7 days
    SESSION_COOKIE_SECURE: bool = False
    SESSION_COOKIE_SAMESITE: str = "lax"

    # File Storage
    DATA_DIR: Path = DEFAULT_DATA_DIR
    UPLOAD_DIR: Path = DEFAULT_UPLOAD_DIR
    MAX_UPLOAD_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB

    # Database
    DATABASE_URL: str = ""

    # CORS
    CORS_ORIGINS: Union[str, List[str]] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_url(cls, v: str) -> str:
        if v and v.strip():
            return v.strip()
        # Default to aiosqlite in project data folder
        DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
        # Use as_posix() to ensure forward slashes on Windows for SQLite URI
        return f"sqlite+aiosqlite:///{DEFAULT_DB_PATH.as_posix()}"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.strip() == "*":
                return ["*"]
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


settings = Settings()
