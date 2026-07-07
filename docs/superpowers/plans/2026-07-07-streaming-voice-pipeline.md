# Streaming Voice Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace pseudo-streaming RAG text emission with real LLM delta streaming and reduce frontend audio startup buffering without changing the wire protocol.

**Architecture:** The backend keeps the existing WebSocket producer/consumer queue and TTS streaming transport, but `RAGGuideChatService.stream_reply()` switches to consuming LLM deltas directly when an LLM-backed prepared answer is available. The frontend keeps its current scheduled `AudioContext` playback model and only adjusts the default buffering thresholds.

**Tech Stack:** FastAPI, asyncio, Python unittest, Vue 3, TypeScript, Node test runner.

---

### Task 1: Lock spec and baseline in the isolated worktree

**Files:**
- Create: `docs/superpowers/specs/2026-07-07-streaming-voice-pipeline-design.md`
- Create: `docs/superpowers/plans/2026-07-07-streaming-voice-pipeline.md`

- [ ] Confirm worktree is clean before feature edits

Run: `git status --short`
Expected: no output

- [ ] Record the current implementation shape

Run: `rg -n "stream_reply\\(|stream_complete|DEFAULT_STREAM_AUDIO_POLICY" backend frontend`
Expected: current backend path shows fallback replay logic and frontend policy shows `900/2/450/50`

### Task 2: Add failing backend tests for true streaming reply generation

**Files:**
- Modify: `backend/tests/test_chat_streaming.py`
- Modify: `backend/app/services/chat.py`

- [ ] Add a test that expects streamed LLM deltas to produce early `text_delta` and `tts_segment`

Add a test case that:
- patches `get_rag_service()` to return a fake service
- returns a `PreparedRAGAnswer` with `llm_messages`
- yields multiple chunks from `llm.stream_complete(...)`
- asserts at least one `text_delta` and one `tts_segment` arrive before the single `final`

- [ ] Run the backend streaming test to verify it fails first

Run: `python -m unittest backend.tests.test_chat_streaming.RAGGuideChatServiceFallbackTestCase`
Expected: failure because current implementation only replays fallback text after preparation

- [ ] Add a second failing test for stream failure fallback

Test should:
- return `PreparedRAGAnswer` with `llm_messages` and `fallback_text`
- make `llm.stream_complete(...)` raise after partial or immediate failure
- assert the resulting stream still ends with a valid `final` containing fallback text

- [ ] Implement minimal backend streaming support

Change `backend/app/services/chat.py` so that:
- a new async iterator path consumes `prepared.llm_messages` from `get_rag_service().llm.stream_complete(...)`
- streamed deltas feed `_stream_from_pieces()` directly
- failures fall back once to `prepared.answer_text or prepared.fallback_text or prepared.spoken_text`
- final metadata still comes from `PreparedRAGAnswer`

- [ ] Re-run the focused backend tests

Run: `python -m unittest backend.tests.test_chat_streaming`
Expected: the new streaming tests and existing streaming tests pass

### Task 3: Add failing frontend policy tests, then tighten buffered playback defaults

**Files:**
- Modify: `frontend/tests/streamAudioBuffer.test.ts`
- Modify: `frontend/src/lib/streamAudioBuffer.ts`

- [ ] Add failing tests that encode the new defaults

Update or add tests so they expect:
- one chunk can start playback
- `450ms` is enough for single-chunk startup
- the exported default policy equals `450 / 1 / 220 / 30`

- [ ] Run the focused frontend tests to verify failure

Run: `node --test --experimental-strip-types frontend/tests/streamAudioBuffer.test.ts`
Expected: failures because the current defaults remain `900 / 2 / 450 / 50`

- [ ] Implement the minimal policy change

Update `DEFAULT_STREAM_AUDIO_POLICY` to:
- `initialBufferMs = 450`
- `initialChunkCount = 1`
- `minScheduledLeadMs = 220`
- `scheduleLookaheadMs = 30`

- [ ] Re-run the focused frontend tests

Run: `node --test --experimental-strip-types frontend/tests/streamAudioBuffer.test.ts`
Expected: all tests pass

### Task 4: Verify the integrated backend/frontend behavior

**Files:**
- Modify only if verification reveals a concrete regression

- [ ] Run backend verification

Run: `python -m unittest backend.tests.test_chat_streaming backend.tests.test_tts`
Expected: all selected backend tests pass

- [ ] Run frontend verification

Run: `node --test --experimental-strip-types frontend/tests/streamAudioBuffer.test.ts`
Expected: pass

- [ ] Run a frontend production build

Run: `npm run build`
Working directory: `frontend`
Expected: successful build with exit code `0`

- [ ] Check final diff

Run: `git status --short`
Expected: only the spec, plan, backend streaming files, and frontend buffering files are modified
