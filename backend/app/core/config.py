import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(PROJECT_DIR / ".env", override=False)


class Settings(BaseModel):
    PROJECT_NAME: str = "PYQVERSE API"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str = Field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    AI_API_KEY: str = Field(default_factory=lambda: os.getenv("AI_API_KEY", ""))
    OLLAMA_BASE_URL: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    FRONTEND_URL: str = Field(
        default_factory=lambda: os.getenv("FRONTEND_URL", "http://localhost:5173")
    )
    APP_ENV: str = Field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    APP_DEBUG: bool = Field(default_factory=lambda: os.getenv("APP_DEBUG", "true").lower() == "true")
    APP_SECRET_KEY: str = Field(default_factory=lambda: os.getenv("APP_SECRET_KEY", ""))
    SUPABASE_URL: str = Field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    SUPABASE_ANON_KEY: str = Field(default_factory=lambda: os.getenv("SUPABASE_ANON_KEY", ""))
    SUPABASE_SERVICE_ROLE_KEY: str = Field(default_factory=lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value:
            raise ValueError("DATABASE_URL is required")
        parsed = urlparse(value)
        if parsed.scheme != "postgresql+psycopg":
            raise ValueError("DATABASE_URL must use the postgresql+psycopg driver")
        if not parsed.hostname or not parsed.path.lstrip("/") or parsed.password is None:
            raise ValueError("DATABASE_URL must include host, database, user and password")
        return value

    @field_validator("FRONTEND_URL", "OLLAMA_BASE_URL")
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Configuration URL must use http or https")
        return value


settings = Settings()
