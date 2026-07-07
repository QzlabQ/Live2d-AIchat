# Phase 3 Visitor Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the Phase 3 visitor-side features on the existing single-page kiosk by adding session history, personalized route recommendations, real photo recognition that flows back into chat, and clearer “thinking” feedback for the avatar.

**Architecture:** Keep the existing WebSocket chat/TTS/Live2D pipeline intact and add visitor features as thin HTTP APIs plus focused Vue components and composables. Backend owns session summaries, recommendation generation, and vision recognition; frontend composes those services into the current single-page visitor shell without introducing new routes.

**Tech Stack:** FastAPI, SQLAlchemy async, SQLite compatibility migrations, DashScope/Qwen-VL-Max, Vue 3, TypeScript, Vite, Vitest, existing WebSocket/TTS/Live2D pipeline

---

## File Structure

### Backend

- Modify: `backend/app/core/config.py`
  - Add visitor photo upload and VL model settings.
- Modify: `backend/app/db/models.py`
  - Add `Session.updated_at` for activity ordering.
- Modify: `backend/app/db/migrations.py`
  - Add SQLite compatibility migration for `sessions.updated_at`.
- Modify: `backend/app/db/session.py`
  - Run the new session migration during startup.
- Modify: `backend/app/api/router.py`
  - Register the new visitor route module.
- Modify: `backend/app/api/routes/sessions.py`
  - Expand to list sessions, fetch session messages, and patch interest tags.
- Create: `backend/app/api/routes/visitor.py`
  - Add recommendation and vision recognition endpoints under `/sessions/{session_id}/recommendations` and `/sessions/{session_id}/vision/recognize`.
- Modify: `backend/app/schemas/session.py`
  - Add session list/detail/update payloads and message item schemas.
- Create: `backend/app/schemas/visitor.py`
  - Add recommendation and vision request/response schemas.
- Create: `backend/app/services/visitor_sessions.py`
  - Build session summary/detail loaders and session tag updater.
- Create: `backend/app/services/recommendations.py`
  - Build structured route recommendation service on top of the existing LLM/RAG stack.
- Create: `backend/app/services/vision.py`
  - Handle image validation, storage, DashScope VL call, and `resolved_question` generation.
- Modify: `backend/.env.example`
  - Document visitor vision settings.

### Backend Tests

- Create: `backend/tests/test_sessions_api.py`
  - Cover session list/detail/interest tag update behavior.
- Create: `backend/tests/test_recommendations_api.py`
  - Cover structured recommendation output and fallback behavior.
- Create: `backend/tests/test_vision_api.py`
  - Cover image validation, storage path resolution, VL result parsing, and missing-config errors.

### Frontend

- Modify: `frontend/package.json`
  - Add `test` script and Vitest dependencies.
- Create: `frontend/vitest.config.ts`
  - Enable frontend unit tests.
- Create: `frontend/src/types/visitor.ts`
  - Hold visitor session, recommendation, and photo recognition types.
- Modify: `frontend/src/types/chat.ts`
  - Add optional message metadata for restored history and photo-origin messages if needed.
- Create: `frontend/src/services/visitorApi.ts`
  - Centralize REST calls for sessions, recommendations, and vision recognition.
- Create: `frontend/src/composables/useVisitorSessions.ts`
  - Manage session list, active session loading, and interest tag updates.
- Create: `frontend/src/composables/useVisitorRecommendations.ts`
  - Manage recommendation loading and card state.
- Create: `frontend/src/composables/usePhotoRecognition.ts`
  - Manage upload state and `resolved_question` generation.
- Create: `frontend/src/lib/visitorSessionState.ts`
  - Pure helpers for sorting summaries, mapping history messages, and switch guards.
- Create: `frontend/src/lib/visitorSessionState.test.ts`
  - Frontend unit tests for session sorting and history mapping.
- Create: `frontend/src/lib/recommendationState.ts`
  - Pure helpers for card normalization and tag merging.
- Create: `frontend/src/lib/recommendationState.test.ts`
  - Frontend unit tests for recommendation normalization.
- Create: `frontend/src/lib/photoQuestion.ts`
  - Pure helpers for building auto-chat text from recognized photo results.
- Create: `frontend/src/lib/photoQuestion.test.ts`
  - Frontend unit tests for photo-to-question conversion.
- Create: `frontend/src/components/SessionHistoryRail.vue`
  - Visitor history list UI.
- Create: `frontend/src/components/InterestTagPanel.vue`
  - Tag picker and recommendation cards UI.
- Create: `frontend/src/components/PhotoAskPanel.vue`
  - Photo upload/recognition entry UI.
- Create: `frontend/src/components/ChatTranscript.vue`
  - Message list and source card UI extracted from `App.vue`.
- Create: `frontend/src/components/ChatComposer.vue`
  - Text, record, and photo entry UI extracted from `App.vue`.
- Modify: `frontend/src/App.vue`
  - Turn into the page orchestration layer.
- Modify: `frontend/src/style.css`
  - Add layout and component styles for the visitor shell.

### Documentation

- Modify: `docs/roadmap.md`
  - Mark completed visitor-side Phase 3 items and note the chosen single-page implementation.

---

### Task 1: Session Activity Model And Visitor Session APIs

**Files:**
- Modify: `backend/app/db/models.py`
- Modify: `backend/app/db/migrations.py`
- Modify: `backend/app/db/session.py`
- Modify: `backend/app/api/routes/sessions.py`
- Modify: `backend/app/schemas/session.py`
- Create: `backend/app/services/visitor_sessions.py`
- Test: `backend/tests/test_sessions_api.py`

- [ ] **Step 1: Write the failing backend tests for session list/detail/tag update**

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Message, Session
from app.services.visitor_sessions import (
    list_visitor_sessions,
    load_session_messages,
    update_session_interest_tags,
)


class VisitorSessionsApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_list_sessions_returns_latest_preview_sorted_by_activity(self) -> None:
        with TemporaryDirectory() as temp_dir:
            engine = create_async_engine(f"sqlite+aiosqlite:///{Path(temp_dir) / 'sessions.db'}")
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            async with session_factory() as db:
                newer = Session(interest_tags=["night-tour"], device_type="mobile")
                older = Session(interest_tags=["history"], device_type="mobile")
                db.add_all([older, newer])
                await db.flush()
                db.add_all(
                    [
                        Message(session_id=older.id, role="user", content="先问历史故事"),
                        Message(session_id=newer.id, role="user", content="夜游几点开始？"),
                    ]
                )
                await db.commit()

                items = await list_visitor_sessions(db, limit=10)

            self.assertEqual(items[0].last_message_preview, "夜游几点开始？")
            self.assertEqual(items[0].interest_tags, ["night-tour"])
            await engine.dispose()

    async def test_load_session_messages_returns_chat_timeline(self) -> None:
        with TemporaryDirectory() as temp_dir:
            engine = create_async_engine(f"sqlite+aiosqlite:///{Path(temp_dir) / 'timeline.db'}")
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            async with session_factory() as db:
                session_obj = Session(interest_tags=["history"], device_type="mobile")
                db.add(session_obj)
                await db.flush()
                db.add_all(
                    [
                        Message(session_id=session_obj.id, role="user", content="开放时间是什么时候？"),
                        Message(session_id=session_obj.id, role="assistant", content="景区整体一般 9:00-21:30。"),
                    ]
                )
                await db.commit()

                items = await load_session_messages(db, session_obj.id)

            self.assertEqual([item.role for item in items], ["user", "assistant"])
            self.assertEqual(items[1].content, "景区整体一般 9:00-21:30。")
            await engine.dispose()

    async def test_update_session_interest_tags_persists_new_tags(self) -> None:
        with TemporaryDirectory() as temp_dir:
            engine = create_async_engine(f"sqlite+aiosqlite:///{Path(temp_dir) / 'update.db'}")
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            async with session_factory() as db:
                session_obj = Session(interest_tags=["history"], device_type="mobile")
                db.add(session_obj)
                await db.commit()
                await db.refresh(session_obj)

                updated = await update_session_interest_tags(db, session_obj.id, ["亲子", "轻松"])

            self.assertEqual(updated.interest_tags, ["亲子", "轻松"])
            await engine.dispose()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
Set-Location backend
python -m unittest tests.test_sessions_api -v
```

Expected: FAIL with `ModuleNotFoundError` for `app.services.visitor_sessions` and missing schemas/fields.

- [ ] **Step 3: Write the minimal backend implementation**

```python
# backend/app/db/models.py
class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    interest_tags: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), default=list, nullable=False)
    device_type: Mapped[str] = mapped_column(String(20), default="mobile", nullable=False)


# backend/app/services/visitor_sessions.py
@dataclass(slots=True)
class VisitorSessionSummary:
    session_id: str
    created_at: datetime
    updated_at: datetime
    interest_tags: list[str]
    message_count: int
    last_message_preview: str


async def list_visitor_sessions(db: AsyncSession, limit: int = 20) -> list[VisitorSessionSummary]:
    stmt = (
        select(Session, func.count(Message.id).label("message_count"), func.max(Message.created_at).label("last_at"))
        .outerjoin(Message, Message.session_id == Session.id)
        .group_by(Session.id)
        .order_by(desc(func.coalesce(func.max(Message.created_at), Session.updated_at)))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    summaries: list[VisitorSessionSummary] = []
    for session_obj, message_count, _last_at in rows:
        preview_stmt = (
            select(Message.content)
            .where(Message.session_id == session_obj.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
        preview = (await db.execute(preview_stmt)).scalar_one_or_none() or ""
        summaries.append(
            VisitorSessionSummary(
                session_id=session_obj.id,
                created_at=session_obj.created_at,
                updated_at=session_obj.updated_at,
                interest_tags=list(session_obj.interest_tags),
                message_count=int(message_count or 0),
                last_message_preview=preview,
            )
        )
    return summaries
```

- [ ] **Step 4: Run the backend tests to verify they pass**

Run:

```powershell
Set-Location backend
python -m unittest tests.test_sessions_api -v
```

Expected: PASS for all three session API tests.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/db/models.py backend/app/db/migrations.py backend/app/db/session.py backend/app/api/routes/sessions.py backend/app/schemas/session.py backend/app/services/visitor_sessions.py backend/tests/test_sessions_api.py
git commit -m "feat: add visitor session history APIs"
```

---

### Task 2: Structured Route Recommendation API

**Files:**
- Create: `backend/app/api/routes/visitor.py`
- Create: `backend/app/schemas/visitor.py`
- Create: `backend/app/services/recommendations.py`
- Modify: `backend/app/api/router.py`
- Test: `backend/tests/test_recommendations_api.py`

- [ ] **Step 1: Write the failing tests for recommendation generation**

```python
import unittest
from unittest.mock import AsyncMock, patch

from app.services.recommendations import RecommendationRequest, VisitorRecommendationService


class VisitorRecommendationServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_generates_structured_recommendation_from_interest_tags(self) -> None:
        service = VisitorRecommendationService(settings=Settings())
        fake_answer = {
            "route_title": "亲子轻松半日路线",
            "intro": "先看核心演出，再走轻松互动点位。",
            "highlights": ["九龙灌浴", "佛手广场", "百子戏弥勒"],
            "suggested_questions": ["孩子五岁怎么安排？", "夜景值得等吗？"],
            "applied_interest_tags": ["亲子", "轻松"],
        }

        with patch.object(service, "_complete_structured", AsyncMock(return_value=fake_answer)):
            result = await service.recommend(
                RecommendationRequest(session_id="session-1", interest_tags=["亲子", "轻松"])
            )

        self.assertEqual(result.route_title, "亲子轻松半日路线")
        self.assertEqual(result.applied_interest_tags, ["亲子", "轻松"])
        self.assertEqual(result.suggested_questions[0], "孩子五岁怎么安排？")

    async def test_falls_back_to_default_questions_when_llm_fails(self) -> None:
        service = VisitorRecommendationService(settings=Settings())

        with patch.object(service, "_complete_structured", AsyncMock(side_effect=RuntimeError("llm down"))):
            result = await service.recommend(
                RecommendationRequest(session_id="session-2", interest_tags=["夜游"], visitor_profile="night-tour")
            )

        self.assertEqual(result.applied_interest_tags, ["夜游"])
        self.assertGreaterEqual(len(result.suggested_questions), 1)
        self.assertIn("夜", result.route_title)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
Set-Location backend
python -m unittest tests.test_recommendations_api -v
```

Expected: FAIL because the recommendation service and schemas do not exist yet.

- [ ] **Step 3: Implement the recommendation service and route**

```python
# backend/app/services/recommendations.py
@dataclass(slots=True)
class RecommendationRequest:
    session_id: str
    interest_tags: list[str]
    visitor_profile: str | None = None


@dataclass(slots=True)
class RecommendationResult:
    route_title: str
    intro: str
    highlights: list[str]
    suggested_questions: list[str]
    applied_interest_tags: list[str]


class VisitorRecommendationService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.llm = DashScopeChatCompletionsClient(self.settings)

    async def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        try:
            payload = await self._complete_structured(request)
        except Exception:
            payload = self._fallback_payload(request)
        return RecommendationResult(**payload)
```

```python
# backend/app/api/routes/visitor.py
router = APIRouter(prefix="/sessions")


@router.post("/{session_id}/recommendations", response_model=RecommendationResponse)
async def recommend_route(
    session_id: str,
    payload: RecommendationRequestPayload,
    db: AsyncSession = Depends(get_db),
) -> RecommendationResponse:
    await ensure_session_exists(db, session_id)
    result = await get_visitor_recommendation_service().recommend(
        RecommendationRequest(
            session_id=session_id,
            interest_tags=payload.interest_tags,
            visitor_profile=payload.visitor_profile,
        )
    )
    return RecommendationResponse.model_validate(result)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
Set-Location backend
python -m unittest tests.test_recommendations_api -v
```

Expected: PASS for structured recommendation output and fallback behavior.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/api/router.py backend/app/api/routes/visitor.py backend/app/schemas/visitor.py backend/app/services/recommendations.py backend/tests/test_recommendations_api.py
git commit -m "feat: add visitor recommendation API"
```

---

### Task 3: Vision Recognition API And Image Storage Flow

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Create: `backend/app/services/vision.py`
- Modify: `backend/app/api/routes/visitor.py`
- Modify: `backend/app/schemas/visitor.py`
- Test: `backend/tests/test_vision_api.py`

- [ ] **Step 1: Write the failing tests for image recognition and config errors**

```python
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from app.core.config import Settings
from app.services.vision import VisitorVisionService


class VisitorVisionServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_recognize_image_returns_resolved_question_and_stored_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            settings = Settings(
                dashscope_api_key="test-key",
                dashscope_vl_model="qwen-vl-max",
                visitor_upload_dir=temp_dir,
            )
            service = VisitorVisionService(settings=settings)

            with patch.object(
                service,
                "_complete_recognition",
                AsyncMock(
                    return_value={
                        "recognized_spot": "九龙灌浴",
                        "recognition_summary": "这看起来是九龙灌浴表演区域。",
                        "resolved_question": "我拍到的是九龙灌浴吗？它讲的是什么故事？",
                    }
                ),
            ):
                result = await service.recognize(
                    session_id="session-1",
                    filename="spot.jpg",
                    content_type="image/jpeg",
                    data=b"fake-bytes",
                    interest_tags=["历史文化"],
                )

            self.assertEqual(result.recognized_spot, "九龙灌浴")
            self.assertTrue(Path(result.stored_image_path).exists())

    async def test_missing_dashscope_key_raises_runtime_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = VisitorVisionService(
                settings=Settings(
                    dashscope_api_key=None,
                    dashscope_vl_model="qwen-vl-max",
                    visitor_upload_dir=temp_dir,
                )
            )

            with self.assertRaises(RuntimeError) as raised:
                await service.recognize(
                    session_id="session-2",
                    filename="spot.jpg",
                    content_type="image/jpeg",
                    data=b"fake-bytes",
                    interest_tags=["历史文化"],
                )

        self.assertIn("DASHSCOPE_API_KEY", str(raised.exception))
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
Set-Location backend
python -m unittest tests.test_vision_api -v
```

Expected: FAIL because the vision service, settings, and route do not exist yet.

- [ ] **Step 3: Implement the vision service, settings, and endpoint**

```python
# backend/app/core/config.py
dashscope_vl_model: str = "qwen-vl-max"
visitor_upload_dir: str = "./storage/uploads/visitor"
visitor_image_max_bytes: int = 6 * 1024 * 1024


# backend/app/services/vision.py
@dataclass(slots=True)
class VisitorVisionResult:
    recognized_spot: str
    recognition_summary: str
    resolved_question: str
    stored_image_path: str


class VisitorVisionService:
    async def recognize(
        self,
        *,
        session_id: str,
        filename: str,
        content_type: str,
        data: bytes,
        interest_tags: list[str],
        user_prompt: str | None = None,
    ) -> VisitorVisionResult:
        self._validate_image(filename, content_type, data)
        stored_path = self._store_image(session_id=session_id, filename=filename, data=data)
        payload = await self._complete_recognition(stored_path, interest_tags, user_prompt)
        return VisitorVisionResult(stored_image_path=str(stored_path), **payload)
```

```python
# backend/app/api/routes/visitor.py
@router.post("/{session_id}/vision/recognize", response_model=VisionRecognitionResponse)
async def recognize_visitor_photo(
    session_id: str,
    file: UploadFile,
    interest_tags: str | None = Form(default=None),
    user_prompt: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> VisionRecognitionResponse:
    await ensure_session_exists(db, session_id)
    payload_tags = json.loads(interest_tags) if interest_tags else []
    data = await file.read()
    result = await get_visitor_vision_service().recognize(
        session_id=session_id,
        filename=file.filename or "upload.jpg",
        content_type=file.content_type or "application/octet-stream",
        data=data,
        interest_tags=payload_tags,
        user_prompt=user_prompt,
    )
    return VisionRecognitionResponse.model_validate(result)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
Set-Location backend
python -m unittest tests.test_vision_api -v
```

Expected: PASS for both successful recognition and missing-config failure paths.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/core/config.py backend/.env.example backend/app/services/vision.py backend/app/api/routes/visitor.py backend/app/schemas/visitor.py backend/tests/test_vision_api.py
git commit -m "feat: add visitor vision recognition API"
```

---

### Task 4: Frontend Test Tooling And Visitor API Foundations

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/types/visitor.ts`
- Create: `frontend/src/services/visitorApi.ts`
- Create: `frontend/src/lib/visitorSessionState.ts`
- Create: `frontend/src/lib/visitorSessionState.test.ts`
- Create: `frontend/src/lib/recommendationState.ts`
- Create: `frontend/src/lib/recommendationState.test.ts`
- Create: `frontend/src/lib/photoQuestion.ts`
- Create: `frontend/src/lib/photoQuestion.test.ts`

- [ ] **Step 1: Write the failing frontend unit tests**

```ts
// frontend/src/lib/visitorSessionState.test.ts
import { describe, expect, it } from 'vitest'

import { sortSessionSummaries } from './visitorSessionState'

describe('sortSessionSummaries', () => {
  it('sorts sessions by updatedAt descending', () => {
    const items = sortSessionSummaries([
      { sessionId: 'a', updatedAt: '2026-07-07T10:00:00Z' },
      { sessionId: 'b', updatedAt: '2026-07-07T11:00:00Z' },
    ])

    expect(items[0].sessionId).toBe('b')
  })
})
```

```ts
// frontend/src/lib/recommendationState.test.ts
import { describe, expect, it } from 'vitest'

import { normalizeRecommendationCard } from './recommendationState'

describe('normalizeRecommendationCard', () => {
  it('creates a stable fallback question list when the API returns none', () => {
    const card = normalizeRecommendationCard({
      route_title: '夜游路线',
      intro: '晚上适合先看亮灯再散步。',
      highlights: [],
      suggested_questions: [],
      applied_interest_tags: ['夜游'],
    })

    expect(card.suggestedQuestions.length).toBeGreaterThan(0)
  })
})
```

```ts
// frontend/src/lib/photoQuestion.test.ts
import { describe, expect, it } from 'vitest'

import { buildPhotoQuestion } from './photoQuestion'

describe('buildPhotoQuestion', () => {
  it('creates a natural follow-up question from recognition output', () => {
    expect(
      buildPhotoQuestion({
        recognizedSpot: '九龙灌浴',
        recognitionSummary: '这看起来是九龙灌浴表演区域。',
      }),
    ).toContain('九龙灌浴')
  })
})
```

- [ ] **Step 2: Run the frontend tests to verify they fail**

Run:

```powershell
Set-Location frontend
npm install
npm run test -- --run src/lib/visitorSessionState.test.ts src/lib/recommendationState.test.ts src/lib/photoQuestion.test.ts
```

Expected: FAIL because the test runner, helpers, and visitor API types do not exist yet.

- [ ] **Step 3: Implement the test runner and visitor API foundation**

```json
{
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest"
  },
  "devDependencies": {
    "vitest": "^3.2.4"
  }
}
```

```ts
// frontend/src/services/visitorApi.ts
export async function listVisitorSessions(apiBaseUrl: string) {
  const response = await fetch(`${apiBaseUrl}/sessions`)
  if (!response.ok) {
    throw new Error(`Failed to load sessions: ${response.status}`)
  }
  return (await response.json()) as VisitorSessionListResponse
}

export async function recognizeVisitorPhoto(
  apiBaseUrl: string,
  sessionId: string,
  file: File,
  interestTags: string[],
) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('interest_tags', JSON.stringify(interestTags))
  const response = await fetch(`${apiBaseUrl}/sessions/${sessionId}/vision/recognize`, {
    method: 'POST',
    body: formData,
  })
  if (!response.ok) {
    throw new Error(`Failed to recognize photo: ${response.status}`)
  }
  return (await response.json()) as VisionRecognitionResponse
}
```

- [ ] **Step 4: Run the frontend tests to verify they pass**

Run:

```powershell
Set-Location frontend
npm run test -- --run src/lib/visitorSessionState.test.ts src/lib/recommendationState.test.ts src/lib/photoQuestion.test.ts
```

Expected: PASS for the visitor helper unit tests.

- [ ] **Step 5: Commit**

```powershell
git add frontend/package.json frontend/vitest.config.ts frontend/src/types/visitor.ts frontend/src/services/visitorApi.ts frontend/src/lib/visitorSessionState.ts frontend/src/lib/visitorSessionState.test.ts frontend/src/lib/recommendationState.ts frontend/src/lib/recommendationState.test.ts frontend/src/lib/photoQuestion.ts frontend/src/lib/photoQuestion.test.ts
git commit -m "test: add visitor frontend test foundation"
```

---

### Task 5: History Rail And Session Switching UI

**Files:**
- Create: `frontend/src/composables/useVisitorSessions.ts`
- Create: `frontend/src/components/SessionHistoryRail.vue`
- Create: `frontend/src/components/ChatTranscript.vue`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`
- Test: `frontend/src/lib/visitorSessionState.test.ts`

- [ ] **Step 1: Extend the failing frontend tests for history mapping and switch safety**

```ts
import { describe, expect, it } from 'vitest'

import { canSwitchSessionWhileIdle, mapHistoryMessagesToChatMessages } from './visitorSessionState'

describe('mapHistoryMessagesToChatMessages', () => {
  it('maps backend session messages into chat bubbles', () => {
    const messages = mapHistoryMessagesToChatMessages([
      { id: 1, role: 'user', content: '开放时间是什么时候？', createdAt: '2026-07-07T10:00:00Z' },
      { id: 2, role: 'assistant', content: '景区整体一般 9:00-21:30。', createdAt: '2026-07-07T10:00:01Z' },
    ])

    expect(messages[0].role).toBe('user')
    expect(messages[1].role).toBe('assistant')
  })
})

describe('canSwitchSessionWhileIdle', () => {
  it('blocks switching when a reply is still streaming', () => {
    expect(canSwitchSessionWhileIdle({ isStreaming: true, isRecording: false })).toBe(false)
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
Set-Location frontend
npm run test -- --run src/lib/visitorSessionState.test.ts
```

Expected: FAIL because the new mapping and guard helpers do not exist yet.

- [ ] **Step 3: Implement session composable and UI extraction**

```ts
// frontend/src/composables/useVisitorSessions.ts
export function useVisitorSessions(apiBaseUrl: string) {
  const sessionList = ref<VisitorSessionSummary[]>([])
  const activeSessionId = ref<string | null>(null)
  const activeMessages = ref<ChatMessage[]>([])
  const loading = ref(false)

  async function refreshSessions() {
    const payload = await listVisitorSessions(apiBaseUrl)
    sessionList.value = sortSessionSummaries(payload.items)
  }

  async function openSession(sessionId: string) {
    loading.value = true
    try {
      const detail = await loadVisitorSessionMessages(apiBaseUrl, sessionId)
      activeSessionId.value = sessionId
      activeMessages.value = mapHistoryMessagesToChatMessages(detail.items)
    } finally {
      loading.value = false
    }
  }

  return { sessionList, activeSessionId, activeMessages, loading, refreshSessions, openSession }
}
```

```vue
<!-- frontend/src/components/SessionHistoryRail.vue -->
<script setup lang="ts">
defineProps<{
  sessions: VisitorSessionSummary[]
  activeSessionId: string | null
  loading?: boolean
}>()

const emit = defineEmits<{
  open: [sessionId: string]
}>()
</script>

<template>
  <aside class="session-rail">
    <header class="session-rail-head">
      <h2>历史会话</h2>
      <span v-if="loading">加载中...</span>
    </header>
    <button
      v-for="session in sessions"
      :key="session.sessionId"
      class="session-card"
      :data-active="session.sessionId === activeSessionId"
      @click="emit('open', session.sessionId)"
    >
      <strong>{{ session.lastMessagePreview || '新会话' }}</strong>
      <span>{{ session.interestTags.join(' / ') || '未设置偏好' }}</span>
    </button>
  </aside>
</template>
```

- [ ] **Step 4: Run the tests and build to verify they pass**

Run:

```powershell
Set-Location frontend
npm run test -- --run src/lib/visitorSessionState.test.ts
npm run build
```

Expected: PASS for the session-state tests and a successful Vite build.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/composables/useVisitorSessions.ts frontend/src/components/SessionHistoryRail.vue frontend/src/components/ChatTranscript.vue frontend/src/App.vue frontend/src/style.css frontend/src/lib/visitorSessionState.ts frontend/src/lib/visitorSessionState.test.ts
git commit -m "feat: add visitor session history rail"
```

---

### Task 6: Interest Tags And Recommendation Card Flow

**Files:**
- Create: `frontend/src/composables/useVisitorRecommendations.ts`
- Create: `frontend/src/components/InterestTagPanel.vue`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`
- Test: `frontend/src/lib/recommendationState.test.ts`

- [ ] **Step 1: Extend the failing recommendation tests**

```ts
import { describe, expect, it } from 'vitest'

import { mergeInterestTags, normalizeRecommendationCard } from './recommendationState'

describe('mergeInterestTags', () => {
  it('keeps stable unique interest tag ordering', () => {
    expect(mergeInterestTags(['亲子', '轻松'], ['轻松', '夜游'])).toEqual(['亲子', '轻松', '夜游'])
  })
})

describe('normalizeRecommendationCard', () => {
  it('keeps at least one suggested question for fallback rendering', () => {
    const card = normalizeRecommendationCard({
      route_title: '夜游路线',
      intro: '晚上适合先看亮灯再散步。',
      highlights: [],
      suggested_questions: [],
      applied_interest_tags: ['夜游'],
    })

    expect(card.suggestedQuestions.length).toBeGreaterThan(0)
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
Set-Location frontend
npm run test -- --run src/lib/recommendationState.test.ts
```

Expected: FAIL because the normalization helpers and card logic are not complete yet.

- [ ] **Step 3: Implement recommendation state and panel**

```ts
// frontend/src/composables/useVisitorRecommendations.ts
export function useVisitorRecommendations(apiBaseUrl: string, sessionId: Ref<string | null>) {
  const selectedInterestTags = ref<string[]>([])
  const recommendation = ref<RecommendationCard | null>(null)
  const loading = ref(false)

  async function refreshRecommendations() {
    if (!sessionId.value) return
    loading.value = true
    try {
      const payload = await fetchVisitorRecommendations(apiBaseUrl, sessionId.value, selectedInterestTags.value)
      recommendation.value = normalizeRecommendationCard(payload)
    } finally {
      loading.value = false
    }
  }

  return { selectedInterestTags, recommendation, loading, refreshRecommendations }
}
```

```vue
<!-- frontend/src/components/InterestTagPanel.vue -->
<script setup lang="ts">
const props = defineProps<{
  selectedTags: string[]
  recommendation: RecommendationCard | null
  loading?: boolean
}>()

const emit = defineEmits<{
  toggleTag: [tag: string]
  askQuestion: [question: string]
  refresh: []
}>()

const TAGS = ['历史文化', '亲子', '夜游', '轻松', '拍照打卡', '省力']
</script>
```

- [ ] **Step 4: Run the tests and build to verify they pass**

Run:

```powershell
Set-Location frontend
npm run test -- --run src/lib/recommendationState.test.ts
npm run build
```

Expected: PASS for recommendation helpers and a successful production build.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/composables/useVisitorRecommendations.ts frontend/src/components/InterestTagPanel.vue frontend/src/App.vue frontend/src/style.css frontend/src/lib/recommendationState.ts frontend/src/lib/recommendationState.test.ts
git commit -m "feat: add visitor interest tags and recommendations"
```

---

### Task 7: Photo Recognition Entry, Auto-Ask Flow, And Thinking-State Integration

**Files:**
- Create: `frontend/src/composables/usePhotoRecognition.ts`
- Create: `frontend/src/components/PhotoAskPanel.vue`
- Create: `frontend/src/components/ChatComposer.vue`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`
- Modify: `docs/roadmap.md`
- Test: `frontend/src/lib/photoQuestion.test.ts`

- [ ] **Step 1: Extend the failing photo-question tests**

```ts
import { describe, expect, it } from 'vitest'

import { buildPhotoQuestion, shouldEnterThinkingForPhoto } from './photoQuestion'

describe('buildPhotoQuestion', () => {
  it('combines recognized spot and summary into a natural auto-ask sentence', () => {
    const text = buildPhotoQuestion({
      recognizedSpot: '梵宫',
      recognitionSummary: '这看起来是梵宫内部区域。',
    })

    expect(text).toContain('梵宫')
    expect(text).toContain('想了解')
  })
})

describe('shouldEnterThinkingForPhoto', () => {
  it('returns true while upload or recognition is pending', () => {
    expect(shouldEnterThinkingForPhoto({ uploading: true, recognizing: false })).toBe(true)
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
Set-Location frontend
npm run test -- --run src/lib/photoQuestion.test.ts
```

Expected: FAIL because the new helper logic and photo composable do not exist yet.

- [ ] **Step 3: Implement photo recognition flow and wire it back into chat**

```ts
// frontend/src/composables/usePhotoRecognition.ts
export function usePhotoRecognition(apiBaseUrl: string, sessionId: Ref<string | null>) {
  const uploading = ref(false)
  const recognizing = ref(false)
  const error = ref('')

  async function recognize(file: File, interestTags: string[]) {
    if (!sessionId.value) throw new Error('No active session.')
    uploading.value = true
    recognizing.value = true
    error.value = ''
    try {
      return await recognizeVisitorPhoto(apiBaseUrl, sessionId.value, file, interestTags)
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : '图片识别失败'
      throw caught
    } finally {
      uploading.value = false
      recognizing.value = false
    }
  }

  return { uploading, recognizing, error, recognize }
}
```

```ts
// frontend/src/App.vue
async function handleRecognizedPhoto(file: File) {
  if (!sessionId.value) return
  resetReplyMediaState()
  beginLocalThinkingPhase()
  const result = await photoRecognition.recognize(file, recommendationState.selectedInterestTags.value)
  const autoQuestion = buildPhotoQuestion(result)
  messages.value.push({
    id: createMessageId('user-photo'),
    role: 'user',
    content: autoQuestion,
    meta: '图片识别',
  })
  socket.send({ type: 'text', content: autoQuestion })
}
```

- [ ] **Step 4: Run the tests and build to verify they pass**

Run:

```powershell
Set-Location frontend
npm run test -- --run src/lib/photoQuestion.test.ts
npm run build
```

Expected: PASS for the photo helper tests and a successful build with the new photo flow.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/composables/usePhotoRecognition.ts frontend/src/components/PhotoAskPanel.vue frontend/src/components/ChatComposer.vue frontend/src/App.vue frontend/src/style.css frontend/src/lib/photoQuestion.ts frontend/src/lib/photoQuestion.test.ts docs/roadmap.md
git commit -m "feat: add visitor photo recognition flow"
```

---

### Task 8: Full Verification And Visitor-Side Acceptance Pass

**Files:**
- Verify: `backend/tests/test_sessions_api.py`
- Verify: `backend/tests/test_recommendations_api.py`
- Verify: `backend/tests/test_vision_api.py`
- Verify: `frontend/src/lib/visitorSessionState.test.ts`
- Verify: `frontend/src/lib/recommendationState.test.ts`
- Verify: `frontend/src/lib/photoQuestion.test.ts`
- Verify: `frontend/src/App.vue`
- Verify: `docs/roadmap.md`

- [ ] **Step 1: Run the backend visitor feature test suite**

Run:

```powershell
Set-Location backend
python -m unittest tests.test_sessions_api tests.test_recommendations_api tests.test_vision_api -v
```

Expected: PASS for all visitor-facing backend tests.

- [ ] **Step 2: Run the frontend visitor unit tests and production build**

Run:

```powershell
Set-Location frontend
npm run test -- --run src/lib/visitorSessionState.test.ts src/lib/recommendationState.test.ts src/lib/photoQuestion.test.ts
npm run build
```

Expected: PASS for all frontend visitor tests and a successful production build.

- [ ] **Step 3: Perform the manual acceptance flow**

Run:

```powershell
Set-Location backend
python -m uvicorn app.main:app --reload
```

```powershell
Set-Location frontend
npm run dev
```

Expected manual results:

- Selecting `亲子 + 轻松` updates the recommendation card.
- Asking “第一次来怎么逛” reflects the selected interests.
- Uploading a scenic photo produces a recognized result and immediately injects a natural photo question into the current chat.
- The history rail shows multiple sessions and can switch between them.
- The avatar clearly enters `thinking` before text/audio arrives.

- [ ] **Step 4: Commit the final integration pass**

```powershell
git add backend frontend docs/roadmap.md
git commit -m "feat: complete phase3 visitor experience"
```

---

## Self-Review

### Spec Coverage

- Single-page visitor shell: covered in Tasks 5, 6, and 7.
- Session history sidebar with switching: covered in Tasks 1 and 5.
- Personalized recommendations from interest tags: covered in Tasks 2 and 6.
- Real image upload and Qwen-VL recognition: covered in Tasks 3 and 7.
- Stronger thinking-state feedback: covered in Task 7 and verified in Task 8.
- Roadmap synchronization: covered in Task 7.

### Placeholder Scan

- No `TODO`, `TBD`, or “implement later” placeholders remain.
- Each task names exact files, concrete tests, concrete commands, and a specific commit message.

### Type Consistency

- Backend uses `session_id`, `interest_tags`, `resolved_question`, and `stored_image_path` consistently across tasks.
- Frontend uses `sessionId`, `selectedInterestTags`, and `buildPhotoQuestion` consistently across helpers and composables.
