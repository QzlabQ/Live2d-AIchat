from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class KnowledgeGapSourceSnapshot(BaseModel):
    filename: str
    title: str
    category: str
    chunk_index: int
    retrieval_score: float
    rerank_score: float
    excerpt: str


class KnowledgeGapItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    normalized_question: str
    representative_question: str
    sample_questions: list[str]
    occurrence_count: int
    status: str
    source_count: int
    source_snapshot: list[KnowledgeGapSourceSnapshot]
    last_session_id: str | None
    last_user_question: str
    last_query_text: str
    last_assistant_reply: str
    last_reply_kind: str
    last_confidence_note: str
    last_confidence: float | None
    admin_title: str
    admin_category: str
    admin_answer: str
    admin_notes: str
    knowledge_doc_id: str | None
    knowledge_doc_filename: str | None
    last_error_message: str
    first_seen_at: datetime
    last_seen_at: datetime
    imported_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def stringify_id(cls, value: object) -> str:
        return str(value)


class KnowledgeGapListResponse(BaseModel):
    total: int
    items: list[KnowledgeGapItem]


class KnowledgeGapStatusSummaryItem(BaseModel):
    status: str
    count: int


class KnowledgeGapSummaryHighlight(BaseModel):
    id: str
    representative_question: str
    occurrence_count: int
    status: str
    last_seen_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def stringify_id(cls, value: object) -> str:
        return str(value)


class KnowledgeGapSummaryResponse(BaseModel):
    total_questions: int
    total_occurrences: int
    status_counts: list[KnowledgeGapStatusSummaryItem]
    highlights: list[KnowledgeGapSummaryHighlight]


class KnowledgeGapUpdateRequest(BaseModel):
    status: str | None = None
    admin_title: str | None = None
    admin_category: str | None = None
    admin_answer: str | None = None
    admin_notes: str | None = None


class KnowledgeGapImportRequest(BaseModel):
    admin_title: str | None = None
    admin_category: str | None = None
    admin_answer: str | None = None
    admin_notes: str | None = None
    filename_prefix: str = Field(default="knowledge-gap")


class KnowledgeGapImportResponse(BaseModel):
    item: KnowledgeGapItem
    message: str
