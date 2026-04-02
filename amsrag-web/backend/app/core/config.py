"""Application settings management."""

import os
import secrets
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_ROOT / "data"
DATABASE_DIR = DATA_DIR / "database"
UPLOAD_DIR = DATA_DIR / "uploads"
RAG_WORKSPACE_DIR = DATA_DIR / "rag_workspaces"
LOG_DIR = BACKEND_ROOT / "logs"
SECRET_FILE = BACKEND_ROOT / ".secret_key"


def _sqlite_url(db_path: Path) -> str:
    return f"sqlite:///{db_path.resolve().as_posix()}"


def _load_or_create_secret_key(secret_file: Path) -> str:
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    if secret_file.exists():
        secret_value = secret_file.read_text(encoding="utf-8").strip()
        if secret_value:
            return secret_value

    secret_value = secrets.token_urlsafe(48)
    secret_file.write_text(secret_value, encoding="utf-8")
    return secret_value


class Settings(BaseSettings):
    """Application settings."""

    APP_NAME: str = "AMSRAG Web"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    DATABASE_URL: str = _sqlite_url(DATABASE_DIR / "amsrag_web.db")

    SECRET_KEY: str = Field(
        default_factory=lambda: _load_or_create_secret_key(SECRET_FILE)
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080

    BACKEND_CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    MAX_UPLOAD_SIZE: int = 52_428_800
    UPLOAD_DIR: str = str(UPLOAD_DIR)
    ALLOWED_EXTENSIONS: str = ".txt,.md,.json,.csv,.pdf,.docx,.xlsx,.xls,.html,.htm"

    RAG_WORKSPACE_DIR: str = str(RAG_WORKSPACE_DIR)
    RAG_BEST_MODEL: str = "qwen-plus"
    RAG_CHEAP_MODEL: str = "qwen-flash"
    RAG_ENTITY_EXTRACTION_MODEL: str = "qwen-flash"
    RAG_GRAPH_BACKEND: str = "networkx"
    NEO4J_URL: str = ""
    NEO4J_USERNAME: str = ""
    NEO4J_PASSWORD: str = ""

    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = str(LOG_DIR / "app.log")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("DEBUG", mode="before")
    @classmethod
    def normalize_debug(cls, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "development"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "production"}:
                return False
        return value

    @field_validator("RAG_GRAPH_BACKEND", mode="before")
    @classmethod
    def normalize_graph_backend(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"neo4j", "networkx"}:
                return normalized
        return value

    @field_validator("NEO4J_URL", mode="before")
    @classmethod
    def normalize_neo4j_url(cls, value):
        if isinstance(value, str) and value.strip():
            return value.strip()
        fallback = os.getenv("NEO4J_URI", "").strip()
        return fallback or value

    @field_validator("NEO4J_USERNAME", mode="before")
    @classmethod
    def normalize_neo4j_username(cls, value):
        if isinstance(value, str) and value.strip():
            return value.strip()
        fallback = os.getenv("NEO4J_USER", "").strip()
        if fallback:
            return fallback
        if os.getenv("NEO4J_URL", "").strip() or os.getenv("NEO4J_URI", "").strip():
            return "neo4j"
        return value

    def get_cors_origins(self) -> List[str]:
        if not self.BACKEND_CORS_ORIGINS:
            return ["http://localhost:3000", "http://localhost:5173"]
        return [
            origin.strip()
            for origin in self.BACKEND_CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    def get_allowed_extensions(self) -> List[str]:
        if not self.ALLOWED_EXTENSIONS:
            return [".txt", ".md", ".json", ".csv"]
        return [
            ext.strip()
            for ext in self.ALLOWED_EXTENSIONS.split(",")
            if ext.strip()
        ]

    def get_rag_workspace_path(self, user_id: int, kb_id: int) -> Path:
        path = Path(self.RAG_WORKSPACE_DIR) / f"user_{user_id}" / f"kb_{kb_id}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_upload_path(self, user_id: int) -> Path:
        path = Path(self.UPLOAD_DIR) / f"user_{user_id}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_neo4j_auth(self) -> tuple[str, str] | None:
        if not self.NEO4J_URL or not self.NEO4J_USERNAME or not self.NEO4J_PASSWORD:
            return None
        return (self.NEO4J_USERNAME, self.NEO4J_PASSWORD)


try:
    settings = Settings()

    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.RAG_WORKSPACE_DIR).mkdir(parents=True, exist_ok=True)
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception as exc:
    print(f"Failed to load settings: {exc}")
    print("Please check the backend .env configuration.")
    raise
