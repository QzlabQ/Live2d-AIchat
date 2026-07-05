# Phase 2 Emotion System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Phase 2's emotion system so the backend emits a quick preview emotion and a final answer-based emotion, and the frontend drives Live2D with model expressions plus smooth parameter overlays.

**Architecture:** Keep the existing low-latency preview emotion path for first-frame responsiveness, then run a second formal emotion analysis after the reply text is finalized and emit a final emotion event. On the frontend, load Haru expression assets from the model manifest, convert them into parameter targets, and blend them with the existing mouth/lipsync and micro-expression overlays.

**Tech Stack:** FastAPI, Python unittest, Vue 3, TypeScript, Pixi Live2D, Vite

---

### Task 1: Define the final emotion event contract

**Files:**
- Modify: `backend/app/api/ws_router.py`
- Modify: `frontend/src/types/chat.ts`
- Test: `backend/tests/test_chat_streaming.py`

- [ ] Add a second-stage emotion payload in the WebSocket flow with a `stage` field (`preview` or `final`).
- [ ] Extend the server reply result object to carry the finalized emotion analysis.
- [ ] Extend the frontend socket type definitions so the final emotion event is strongly typed.
- [ ] Verify with `python -m unittest tests.test_chat_streaming`.

### Task 2: Add backend final-answer emotion analysis

**Files:**
- Modify: `backend/app/api/ws_router.py`
- Modify: `backend/app/services/chat.py`
- Test: `backend/tests/test_chat_streaming.py`
- Test: `backend/tests/test_emotion.py`

- [ ] Write a failing test proving the backend emits `preview` first and `final` after the final reply text is known.
- [ ] Update the streaming reply pipeline to call `chat_service.analyze_emotion(user_text, final_reply_text)` after text generation finishes.
- [ ] Persist the assistant message with the final emotion label instead of the quick preview label.
- [ ] Verify with `python -m unittest tests.test_emotion tests.test_chat_streaming`.

### Task 3: Add Haru expression-based Live2D emotion driving

**Files:**
- Modify: `frontend/src/lib/lipsync.ts`
- Modify: `frontend/src/components/Live2DStage.vue`
- Test target: `frontend/src/components/Live2DStage.vue` via `npm run build`

- [ ] Add an emotion-to-expression mapping for Haru and a helper that loads expression parameter definitions from `haru_greeter_t03.model3.json`.
- [ ] Blend base expression parameters with the existing emotion overlay parameters and keep mouth parameters owned by lipsync.
- [ ] Keep transitions smoothed so the avatar changes mood naturally instead of snapping.
- [ ] Verify with `npm run build`.

### Task 4: Polish frontend emotion consumption and fallback behavior

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/types/chat.ts`
- Modify: `frontend/src/lib/lipsync.ts`
- Test target: `frontend/src/App.vue` via `npm run build`

- [ ] Update the UI to treat `preview` as a temporary mood and replace it with `final` when the backend emits the answer-based emotion.
- [ ] Keep the existing lava-lamp panel in sync with the latest stage and source details for debugging.
- [ ] Ensure replay/reset logic clears both expression state and telemetry cleanly between turns.
- [ ] Verify with `npm run build`.

### Task 5: Final verification

**Files:**
- Modify: `backend/README.md` only if behavior notes need to change

- [ ] Run `python -m unittest tests.test_emotion tests.test_chat_streaming` in `backend`.
- [ ] Run `npm run build` in `frontend`.
- [ ] Summarize any environment-specific blockers if local dependencies are still missing in this worktree.
