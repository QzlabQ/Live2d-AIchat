from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KnowledgeDocItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    category: str
    stored_path: str
    chunk_count: int
    uploaded_at: datetime
    status: str
    error_message: str


class KnowledgeDocListResponse(BaseModel):
    total: int
    items: list[KnowledgeDocItem]
