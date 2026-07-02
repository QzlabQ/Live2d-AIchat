from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KnowledgeDocItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    category: str
    chunk_count: int
    uploaded_at: datetime
    status: str


class KnowledgeDocListResponse(BaseModel):
    total: int
    items: list[KnowledgeDocItem]
