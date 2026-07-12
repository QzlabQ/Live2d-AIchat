from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import KnowledgeDoc
from app.db.session import AsyncSessionFactory, get_db
from app.schemas.admin import KnowledgeUploadResponse
from app.schemas.avatar import MessageResponse
from app.schemas.knowledge import KnowledgeDocItem, KnowledgeDocListResponse
from app.services.admin_auth import require_admin_auth
from app.services.knowledge_base import KnowledgeDocumentParser, KnowledgeImporter

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/admin/knowledge", dependencies=[Depends(require_admin_auth)])
_knowledge_import_tasks: set[asyncio.Task[None]] = set()


def _build_storage_path(doc_id: str, filename: str) -> Path:
    upload_root = Path(settings.admin_knowledge_upload_dir).expanduser()
    if not upload_root.is_absolute():
        upload_root = Path(__file__).resolve().parents[3] / upload_root
    upload_root.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    return upload_root / f"{doc_id}-{safe_name}"


async def _read_upload_limited(file: UploadFile, max_bytes: int, chunk_size: int = 64 * 1024) -> bytes:
    buffer = bytearray()
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="知识库文件超过大小限制。",
            )
    return bytes(buffer)


def _schedule_knowledge_import(doc_id: str, stored_path: str, filename: str, category: str) -> None:
    async def runner() -> None:
        importer = KnowledgeImporter(AsyncSessionFactory)
        try:
            await importer.import_existing_document(
                doc_id,
                Path(stored_path),
                filename=filename,
                category=category,
            )
        except Exception:
            logger.exception("Knowledge import failed for doc_id=%s path=%s", doc_id, stored_path)

    task = asyncio.create_task(runner())
    _knowledge_import_tasks.add(task)
    task.add_done_callback(_knowledge_import_tasks.discard)


@router.post("/upload", response_model=KnowledgeUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_knowledge_doc(
    file: UploadFile = File(...),
    category: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeUploadResponse:
    filename = Path(file.filename or "upload").name
    if not filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传文件名不能为空。")
    if not KnowledgeDocumentParser.is_supported(Path(filename)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前文件类型不支持导入。")

    try:
        payload = await _read_upload_limited(file, settings.admin_knowledge_max_bytes)
    finally:
        await file.close()

    importer = KnowledgeImporter(AsyncSessionFactory)
    existing_docs = list(
        (
            await db.execute(select(KnowledgeDoc).where(KnowledgeDoc.filename == filename))
        ).scalars()
    )
    for existing in existing_docs:
        await importer.delete_document(existing.id, db)

    doc_id = str(uuid4())
    stored_path = _build_storage_path(doc_id, filename)
    stored_path.write_bytes(payload)

    document = KnowledgeDoc(
        id=doc_id,
        filename=filename,
        category=category,
        stored_path=str(stored_path),
        chunk_count=0,
        status="processing",
        error_message="",
    )
    db.add(document)
    await db.commit()

    _schedule_knowledge_import(doc_id, str(stored_path), filename, category)
    return KnowledgeUploadResponse(
        doc_id=doc_id,
        status="processing",
        message="文档处理中，稍后刷新列表即可查看结果。",
    )


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
