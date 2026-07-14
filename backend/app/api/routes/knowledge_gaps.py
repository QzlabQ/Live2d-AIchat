from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.knowledge_gap import (
    KnowledgeGapImportRequest,
    KnowledgeGapImportResponse,
    KnowledgeGapItem,
    KnowledgeGapListResponse,
    KnowledgeGapSummaryResponse,
    KnowledgeGapUpdateRequest,
)
from app.services.admin_auth import require_admin_auth
from app.services.knowledge_gaps import (
    get_knowledge_gap_or_404,
    import_knowledge_gap,
    list_knowledge_gaps,
    summarize_knowledge_gaps,
    update_knowledge_gap,
)

router = APIRouter(prefix="/admin/knowledge/gaps", dependencies=[Depends(require_admin_auth)])


@router.get("", response_model=KnowledgeGapListResponse)
async def list_admin_knowledge_gaps(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeGapListResponse:
    total, items = await list_knowledge_gaps(
        db,
        page=page,
        size=size,
        status_filter=status,
        search=search,
    )
    return KnowledgeGapListResponse(
        total=total,
        items=[KnowledgeGapItem.model_validate(item) for item in items],
    )


@router.get("/summary", response_model=KnowledgeGapSummaryResponse)
async def get_admin_knowledge_gap_summary(
    db: AsyncSession = Depends(get_db),
) -> KnowledgeGapSummaryResponse:
    payload = await summarize_knowledge_gaps(db)
    return KnowledgeGapSummaryResponse.model_validate(payload)


@router.get("/{gap_id}", response_model=KnowledgeGapItem)
async def get_admin_knowledge_gap_detail(
    gap_id: int,
    db: AsyncSession = Depends(get_db),
) -> KnowledgeGapItem:
    item = await get_knowledge_gap_or_404(db, gap_id)
    return KnowledgeGapItem.model_validate(item)


@router.put("/{gap_id}", response_model=KnowledgeGapItem)
async def update_admin_knowledge_gap(
    gap_id: int,
    payload: KnowledgeGapUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> KnowledgeGapItem:
    item = await update_knowledge_gap(
        db,
        gap_id=gap_id,
        status_value=payload.status,
        admin_title=payload.admin_title,
        admin_category=payload.admin_category,
        admin_answer=payload.admin_answer,
        admin_notes=payload.admin_notes,
    )
    return KnowledgeGapItem.model_validate(item)


@router.post("/{gap_id}/import", response_model=KnowledgeGapImportResponse)
async def import_admin_knowledge_gap(
    gap_id: int,
    payload: KnowledgeGapImportRequest,
    db: AsyncSession = Depends(get_db),
) -> KnowledgeGapImportResponse:
    item = await import_knowledge_gap(
        db,
        gap_id=gap_id,
        filename_prefix=payload.filename_prefix,
        admin_title=payload.admin_title,
        admin_category=payload.admin_category,
        admin_answer=payload.admin_answer,
        admin_notes=payload.admin_notes,
    )
    return KnowledgeGapImportResponse(
        item=KnowledgeGapItem.model_validate(item),
        message="知识缺口答案已生成文档并写入知识库。",
    )
