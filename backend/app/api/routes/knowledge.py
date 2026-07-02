from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeDoc
from app.db.session import AsyncSessionFactory, get_db
from app.schemas.avatar import MessageResponse
from app.schemas.knowledge import KnowledgeDocItem, KnowledgeDocListResponse
from app.services.knowledge_base import KnowledgeImporter

router = APIRouter(prefix="/admin/knowledge")


@router.get("", response_model=KnowledgeDocListResponse)
async def list_knowledge_docs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    category: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeDocListResponse:
    filters = []
    if category:
        filters.append(KnowledgeDoc.category == category)

    total_stmt = select(func.count()).select_from(KnowledgeDoc)
    if filters:
        total_stmt = total_stmt.where(*filters)
    total = int((await db.execute(total_stmt)).scalar_one())

    stmt = select(KnowledgeDoc).order_by(KnowledgeDoc.uploaded_at.desc())
    if filters:
        stmt = stmt.where(*filters)

    offset = (page - 1) * size
    items = list((await db.execute(stmt.offset(offset).limit(size))).scalars())
    return KnowledgeDocListResponse(total=total, items=[KnowledgeDocItem.model_validate(item) for item in items])


@router.delete("/{doc_id}", response_model=MessageResponse)
async def delete_knowledge_doc(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    importer = KnowledgeImporter(AsyncSessionFactory)
    document = await importer.delete_document(doc_id, db)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge document not found.")
    return MessageResponse(message="知识库文档及其向量数据已删除。")
