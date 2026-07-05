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
    dashscope_model: str = "qwen3.7-plus"

    asr_engine: str = "mock"
    asr_model_name: str = "small"
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"
    asr_language: str = "zh"
    asr_mock_transcript: str = "你好，请介绍一下这个景区。"

    tts_engine: str = "cosyvoice"
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    tts_rate: str = "+0%"
    tts_pitch: str = "+0Hz"
    tts_cosyvoice_model_path: str = "./storage/models/CosyVoice2-0.5B"
    tts_cosyvoice_code_path: str = "./storage/vendor/CosyVoice"
    tts_cosyvoice_device: str = "cuda"
    tts_cosyvoice_onnx_provider: str = "cpu"
    tts_cosyvoice_sample_rate: int = 24000
    tts_cosyvoice_fp16: bool = True
    tts_cosyvoice_load_jit: bool = False
    tts_segment_soft_min_chars: int = 12
    tts_segment_soft_max_chars: int = 20
    tts_segment_hard_max_chars: int = 28

    chat_mode: str = "template"
    rag_retrieval_top_k: int = 8
    rag_rerank_top_n: int = 4
    rag_context_docs: int = 3
    rag_context_chars_per_chunk: int = 520
    rag_min_retrieval_score: float = 0.08
    rag_generation_temperature: float = 0.2
    rag_generation_max_tokens: int = 360
    rag_reranker_engine: str = "bge-reranker-v2-m3"
    rag_reranker_model: str = "BAAI/bge-reranker-v2-m3"
    rag_reranker_device: str = "cpu"
    rag_reranker_batch_size: int = 4
    websocket_chunk_size: int = 24
    request_timeout_seconds: float = 10.0

    default_tts_reference_audio_path: str = './storage/vendor/CosyVoice/asset/zero_shot_prompt.wav'
    default_tts_reference_text: str = '\u5e0c\u671b\u4f60\u4ee5\u540e\u80fd\u591f\u505a\u5f97\u6bd4\u6211\u8fd8\u597d\u3002'
    default_tts_speed: float = Field(default=1.0, ge=0.5, le=1.5)
    default_tts_emotion_enabled: bool = True

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
        "rag_retrieval_top_k",
        "rag_rerank_top_n",
        "rag_context_docs",
        "rag_context_chars_per_chunk",
        "rag_generation_max_tokens",
        "rag_reranker_batch_size",
        "tts_cosyvoice_sample_rate",
        "tts_segment_soft_min_chars",
        "tts_segment_soft_max_chars",
        "tts_segment_hard_max_chars",
        mode="after",
    )
    @classmethod
    def ensure_positive_knowledge_numbers(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Knowledge configuration values must be positive integers.")
        return value

    @field_validator("rag_generation_temperature", "rag_min_retrieval_score", mode="after")
    @classmethod
    def ensure_non_negative_rag_numbers(cls, value: float) -> float:
        if value < 0:
            raise ValueError("RAG configuration values must be non-negative.")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
