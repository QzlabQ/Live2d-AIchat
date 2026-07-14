from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import KnowledgeGap
from app.db.session import AsyncSessionFactory
from app.services.knowledge_base import KnowledgeImporter
from app.services.rag import is_out_of_domain_question, normalize_question

VALID_KNOWLEDGE_GAP_STATUSES = {"pending", "draft", "imported", "ignored"}
MANUAL_KNOWLEDGE_GAP_STATUSES = {"pending", "draft", "ignored"}
MAX_SAMPLE_QUESTIONS = 6


def utc_now() -> datetime:
    return datetime.now(UTC)


def trim_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().split())


def build_excerpt(text: str, limit: int = 140) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def merge_sample_questions(existing: list[str], candidates: list[str]) -> list[str]:
    merged: list[str] = []
    for item in [*existing, *candidates]:
        cleaned = trim_text(item)
        if not cleaned or cleaned in merged:
            continue
        merged.append(cleaned)
    return merged[-MAX_SAMPLE_QUESTIONS:]


def sanitize_status(value: str | None, *, allow_imported: bool = False) -> str:
    normalized = trim_text(value).lower()
    allowed = VALID_KNOWLEDGE_GAP_STATUSES if allow_imported else MANUAL_KNOWLEDGE_GAP_STATUSES
    if normalized not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"不支持的知识缺口状态：{value}",
        )
    return normalized


def should_record_knowledge_gap(
    *,
    mode: str,
    query_text: str,
    reply_kind: str,
    confidence_note: str,
    confidence: float,
    source_count: int,
    needs_followup: bool,
) -> bool:
    if mode != "rag":
        return False

    normalized_query = normalize_question(query_text)
    if not normalized_query or is_out_of_domain_question(normalized_query):
        return False

    if reply_kind == "refuse":
        return True
    if confidence_note == "uncertain":
        return True
    if source_count == 0 and not needs_followup and confidence < 0.35:
        return True
    return False


def build_source_snapshot(sources: list[object]) -> list[dict[str, str | int | float | bool | None]]:
    snapshot: list[dict[str, str | int | float | bool | None]] = []
    for item in sources[:5]:
        snapshot.append(
            {
                "filename": str(getattr(item, "filename", "")),
                "title": str(getattr(item, "title", "")),
                "category": str(getattr(item, "category", "")),
                "chunk_index": int(getattr(item, "chunk_index", 0) or 0),
                "retrieval_score": float(getattr(item, "retrieval_score", 0.0) or 0.0),
                "rerank_score": float(getattr(item, "rerank_score", 0.0) or 0.0),
                "excerpt": build_excerpt(str(getattr(item, "text", ""))),
            }
        )
    return snapshot


def build_generated_markdown(gap: KnowledgeGap, *, title: str, answer: str, notes: str) -> str:
    lines = [
        f"# {title}",
        "",
        f"分类：{gap.admin_category}",
        "",
        "## 用户问题",
        gap.representative_question,
        "",
        "## 标准回答",
        answer.strip(),
    ]
    if gap.sample_questions:
        lines.extend(["", "## 常见问法"])
        lines.extend([f"- {item}" for item in gap.sample_questions])
    if notes.strip():
        lines.extend(["", "## 管理员备注", notes.strip()])
    return "\n".join(lines).strip() + "\n"


def sanitize_filename_prefix(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip())
    cleaned = cleaned.strip("-_")
    return cleaned or "knowledge-gap"


def build_generated_filename(gap_id: int, prefix: str, now: datetime) -> str:
    return f"{sanitize_filename_prefix(prefix)}-{gap_id:05d}-{now.strftime('%Y%m%d-%H%M%S')}.md"


def resolve_generated_doc_path(settings: Settings, filename: str) -> Path:
    upload_root = Path(settings.admin_knowledge_upload_dir).expanduser()
    if not upload_root.is_absolute():
        upload_root = Path(__file__).resolve().parents[2] / upload_root
    target_dir = upload_root / "generated"
    target_dir.mkdir(parents=True, exist_ok=True)
    return (target_dir / filename).resolve()


async def record_knowledge_gap(
    db: AsyncSession,
    *,
    session_id: str,
    user_question: str,
    query_text: str,
    assistant_reply: str,
    reply_kind: str,
    confidence_note: str,
    confidence: float,
    sources: list[object],
) -> KnowledgeGap:
    normalized_query = normalize_question(query_text or user_question)
    if not normalized_query:
        raise ValueError("normalized query cannot be empty")

    now = utc_now()
    representative_question = trim_text(user_question or query_text or normalized_query)
    result = await db.execute(
        select(KnowledgeGap).where(KnowledgeGap.normalized_question == normalized_query).limit(1)
    )
    gap = result.scalar_one_or_none()
    if gap is None:
        gap = KnowledgeGap(
            normalized_question=normalized_query,
            representative_question=representative_question,
            sample_questions=merge_sample_questions([], [representative_question, query_text]),
            occurrence_count=1,
            status="pending",
            source_count=len(sources),
            source_snapshot=build_source_snapshot(sources),
            last_session_id=session_id,
            last_user_question=representative_question,
            last_query_text=trim_text(query_text or representative_question),
            last_assistant_reply=trim_text(assistant_reply),
            last_reply_kind=trim_text(reply_kind),
            last_confidence_note=trim_text(confidence_note),
            last_confidence=float(confidence),
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(gap)
    else:
        gap.occurrence_count += 1
        gap.source_count = len(sources)
        gap.source_snapshot = build_source_snapshot(sources)
        gap.last_session_id = session_id
        gap.last_user_question = representative_question
        gap.last_query_text = trim_text(query_text or representative_question)
        gap.last_assistant_reply = trim_text(assistant_reply)
        gap.last_reply_kind = trim_text(reply_kind)
        gap.last_confidence_note = trim_text(confidence_note)
        gap.last_confidence = float(confidence)
        gap.last_seen_at = now
        gap.updated_at = now
        gap.sample_questions = merge_sample_questions(
            list(gap.sample_questions or []),
            [representative_question, query_text],
        )
        if gap.status == "imported":
            gap.status = "pending"
            gap.last_error_message = "该问题在补录入库后再次出现，已自动重新打开。"

    await db.commit()
    await db.refresh(gap)
    return gap


async def list_knowledge_gaps(
    db: AsyncSession,
    *,
    page: int = 1,
    size: int = 20,
    status_filter: str | None = None,
    search: str | None = None,
) -> tuple[int, list[KnowledgeGap]]:
    filters = []
    if status_filter:
        filters.append(KnowledgeGap.status == sanitize_status(status_filter, allow_imported=True))

    keyword = trim_text(search)
    if keyword:
        pattern = f"%{keyword}%"
        filters.append(
            or_(
                KnowledgeGap.representative_question.ilike(pattern),
                KnowledgeGap.last_user_question.ilike(pattern),
                KnowledgeGap.admin_title.ilike(pattern),
                KnowledgeGap.admin_answer.ilike(pattern),
            )
        )

    total_stmt = select(func.count()).select_from(KnowledgeGap)
    stmt = select(KnowledgeGap).order_by(
        KnowledgeGap.occurrence_count.desc(),
        KnowledgeGap.last_seen_at.desc(),
        KnowledgeGap.id.desc(),
    )
    if filters:
        total_stmt = total_stmt.where(*filters)
        stmt = stmt.where(*filters)

    total = int((await db.execute(total_stmt)).scalar_one())
    offset = (page - 1) * size
    items = list((await db.execute(stmt.offset(offset).limit(size))).scalars())
    return total, items


async def summarize_knowledge_gaps(db: AsyncSession) -> dict[str, object]:
    counts_result = await db.execute(
        select(KnowledgeGap.status, func.count(), func.sum(KnowledgeGap.occurrence_count))
        .group_by(KnowledgeGap.status)
    )
    status_counts: list[dict[str, object]] = []
    total_questions = 0
    total_occurrences = 0
    for status_value, count_value, occurrence_sum in counts_result.all():
        count = int(count_value or 0)
        occurrences = int(occurrence_sum or 0)
        total_questions += count
        total_occurrences += occurrences
        status_counts.append({"status": str(status_value or "pending"), "count": count})

    highlight_rows = list(
        (
            await db.execute(
                select(KnowledgeGap)
                .where(KnowledgeGap.status.in_(("pending", "draft")))
                .order_by(
                    KnowledgeGap.occurrence_count.desc(),
                    KnowledgeGap.last_seen_at.desc(),
                    KnowledgeGap.id.desc(),
                )
                .limit(6)
            )
        ).scalars()
    )
    highlights = [
        {
            "id": item.id,
            "representative_question": item.representative_question,
            "occurrence_count": item.occurrence_count,
            "status": item.status,
            "last_seen_at": item.last_seen_at,
        }
        for item in highlight_rows
    ]
    return {
        "total_questions": total_questions,
        "total_occurrences": total_occurrences,
        "status_counts": status_counts,
        "highlights": highlights,
    }


async def get_knowledge_gap_or_404(db: AsyncSession, gap_id: int) -> KnowledgeGap:
    gap = await db.get(KnowledgeGap, gap_id)
    if gap is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识缺口记录不存在。")
    return gap


async def update_knowledge_gap(
    db: AsyncSession,
    *,
    gap_id: int,
    status_value: str | None = None,
    admin_title: str | None = None,
    admin_category: str | None = None,
    admin_answer: str | None = None,
    admin_notes: str | None = None,
) -> KnowledgeGap:
    gap = await get_knowledge_gap_or_404(db, gap_id)
    draft_fields_changed = False

    if status_value is not None:
        gap.status = sanitize_status(status_value)
    if admin_title is not None:
        gap.admin_title = trim_text(admin_title)
        draft_fields_changed = True
    if admin_category is not None:
        gap.admin_category = trim_text(admin_category) or "faq"
        draft_fields_changed = True
    if admin_answer is not None:
        gap.admin_answer = str(admin_answer or "").strip()
        draft_fields_changed = True
    if admin_notes is not None:
        gap.admin_notes = str(admin_notes or "").strip()
        draft_fields_changed = True

    if draft_fields_changed and status_value is None:
        gap.status = "draft"

    gap.updated_at = utc_now()
    await db.commit()
    await db.refresh(gap)
    return gap


async def import_knowledge_gap(
    db: AsyncSession,
    *,
    gap_id: int,
    filename_prefix: str,
    admin_title: str | None = None,
    admin_category: str | None = None,
    admin_answer: str | None = None,
    admin_notes: str | None = None,
    settings: Settings | None = None,
) -> KnowledgeGap:
    settings = settings or get_settings()
    gap = await update_knowledge_gap(
        db,
        gap_id=gap_id,
        admin_title=admin_title,
        admin_category=admin_category,
        admin_answer=admin_answer,
        admin_notes=admin_notes,
    )

    title = trim_text(gap.admin_title) or trim_text(gap.representative_question)
    answer = str(gap.admin_answer or "").strip()
    if not answer:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请先填写管理员标准回答，再导入知识库。",
        )

    gap.admin_title = title
    gap.admin_category = trim_text(gap.admin_category) or "faq"
    importer = KnowledgeImporter(session_factory=AsyncSessionFactory, settings=settings)
    if gap.knowledge_doc_id:
        await importer.delete_document(gap.knowledge_doc_id, db)
        gap.knowledge_doc_id = None
        gap.knowledge_doc_filename = None

    now = utc_now()
    filename = build_generated_filename(gap.id, filename_prefix, now)
    stored_path = resolve_generated_doc_path(settings, filename)
    markdown_text = build_generated_markdown(
        gap,
        title=title,
        answer=answer,
        notes=str(gap.admin_notes or ""),
    )
    stored_path.write_text(markdown_text, encoding="utf-8")

    try:
        imported = await importer.import_generated_markdown(
            db,
            filename=filename,
            category=gap.admin_category,
            title=title,
            markdown_text=markdown_text,
            stored_path=stored_path,
        )
    except Exception as exc:
        gap.status = "draft"
        gap.last_error_message = str(exc)
        gap.updated_at = now
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"自动补录入库失败：{exc}",
        ) from exc

    gap.status = "imported"
    gap.knowledge_doc_id = imported.doc_id
    gap.knowledge_doc_filename = imported.filename
    gap.imported_at = now
    gap.last_error_message = ""
    gap.updated_at = now
    await db.commit()
    await db.refresh(gap)
    return gap
