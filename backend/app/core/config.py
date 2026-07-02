from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AI Chat Live2D Backend"
    app_env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    database_url: str = "sqlite+aiosqlite:///./phase1.db"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    default_avatar_model_path: str = "/live2d/models/guide/guide.model3.json"
    default_avatar_voice_id: str = "zh-CN-XiaoxiaoNeural"
    default_avatar_persona: str = (
        "你是一名景区 AI 数字导览员，回答要友好、简洁，优先帮助游客完成参观与问路。"
    )

    dashscope_api_key: str | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen-plus"

    asr_engine: str = "mock"
    asr_model_name: str = "small"
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"
    asr_language: str = "zh"
    asr_mock_transcript: str = "你好，请介绍一下这个景区。"

    tts_engine: str = "mock"
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    tts_rate: str = "+0%"
    tts_pitch: str = "+0Hz"

    chat_mode: str = "template"
    websocket_chunk_size: int = 24
    request_timeout_seconds: float = 10.0

    knowledge_base_dir: str = "./storage/knowledge"
    knowledge_collection_name: str = "phase1_scenic_knowledge"
    knowledge_embedding_engine: str = "bge-m3"
    knowledge_embedding_model: str = "BAAI/bge-m3"
    knowledge_embedding_device: str = "cpu"
    knowledge_embedding_batch_size: int = 8
    knowledge_chunk_size: int = 512
    knowledge_chunk_overlap: int = 64

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug_flag(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
                return False
        return value

    @field_validator(
        "knowledge_embedding_batch_size",
        "knowledge_chunk_size",
        "knowledge_chunk_overlap",
        mode="after",
    )
    @classmethod
    def ensure_positive_knowledge_numbers(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Knowledge configuration values must be positive integers.")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
