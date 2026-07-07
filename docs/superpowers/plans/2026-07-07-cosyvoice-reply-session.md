# CosyVoice Reply Session Implementation Plan

## Goal

Implement the second-stage TTS optimization by replacing per-segment CosyVoice streaming calls with a reply-scoped continuous session, while keeping the existing frontend protocol intact.

## Tasks

- [x] Add a tracked vendor-runtime patch path in `backend/app/services/tts.py`
  - expose `iter_text_normalize(...)`
  - expose `inference_instruct2_reply(...)`

- [x] Add reply-scoped synthesis in `backend/app/services/tts.py`
  - keep `stream_synthesize_segment(...)` as fallback/compat path
  - add `stream_synthesize_reply(...)`
  - reuse prompt cache binding and audio trimming logic

- [x] Update `backend/app/api/ws_router.py`
  - enqueue `tts_segment` with stable `segment_id`
  - prefer `stream_synthesize_reply(...)` when reply streaming is supported
  - keep non-streaming and per-segment fallback behavior

- [x] Add backend tests
  - reply session reuses one vendor call across multiple segments
  - first audio chunk can arrive before later segments finish feeding
  - WebSocket path prefers reply-scoped streaming when available

- [ ] Run integrated manual latency validation with real CosyVoice and inspect `avatar_trace`

## Verification

- `conda run -n ai-chat-gpu python -m unittest tests.test_tts`
- `conda run -n ai-chat-gpu python -m unittest tests.test_chat_streaming`
- `conda run -n ai-chat-gpu python -m unittest tests.test_chat_streaming tests.test_tts`
