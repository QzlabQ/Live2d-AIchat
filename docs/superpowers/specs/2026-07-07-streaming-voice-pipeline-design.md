# Streaming Voice Pipeline Design

## Summary

Phase 1 of this optimization keeps the existing WebSocket protocol and TTS transport model, but replaces the pseudo-streaming text path with a real LLM streaming path. The backend should consume LLM deltas as they arrive, feed them into the existing display and TTS chunkers, and keep the TTS consumer queue model unchanged. The frontend should keep the current `AudioContext` scheduling model, but start playback with a smaller initial buffer so the first audio chunk can be heard earlier without changing the audio message schema.

This phase explicitly avoids deep changes to vendored CosyVoice or model weights. If the first phase reduces first-audio latency but sentence-boundary stalls remain unacceptable, a second phase may expose a reply-scoped continuous TTS session in vendored CosyVoice.

## Current State

- `RAGGuideChatService.stream_reply()` currently calls `prepare_stream_answer()` and then replays a completed fallback text through `DisplayChunker` and `TTSSegmenter`.
- `ws_router.stream_assistant_reply()` already has a producer/consumer split with `segment_queue`, `text_delta`, `tts_segment`, `tts_audio_chunk`, `tts_viseme_chunk`, `text_done`, `audio_done`, and `done`.
- `TTSService.stream_synthesize_segment()` already streams PCM chunks for a single text segment, but each segment starts a new `inference_instruct2(..., stream=True)` call.
- Frontend playback already uses scheduled `AudioBufferSourceNode` playback with a conservative start policy of `900ms`, `2 chunks`, `450ms` lead, and `50ms` lookahead.

## Goal

Reduce time from the first usable LLM delta to the first emitted TTS audio chunk, while keeping the protocol stable and preserving current emotion, viseme, and trace behavior.

Success criteria for this phase:

- `RAGGuideChatService.stream_reply()` emits `text_delta` and `tts_segment` incrementally from LLM stream deltas when `PreparedRAGAnswer.llm_messages` is present.
- If LLM streaming fails mid-reply, the service falls back to the prepared retrieval text and still produces a valid `final` event.
- `ws_router.stream_assistant_reply()` keeps the current message schema and queue model.
- Trace metrics make it easy to compare `llm_first_delta_ms`, `tts_first_segment_ms`, `tts_first_audio_chunk_ms`, and `text_done_ms`.
- Frontend playback starts sooner with a smaller initial buffer and still avoids underruns in validation runs.

## Design

### Backend reply generation

- Keep `BaseGuideChatService._stream_from_pieces()` as the shared chunking primitive.
- Add a code path in `RAGGuideChatService.stream_reply()` that consumes `get_rag_service().llm.stream_complete(prepared.llm_messages)` when `prepared.llm_messages` exists.
- Feed the async delta stream directly into `_stream_from_pieces()` instead of waiting for a completed answer string.
- Accumulate all streamed pieces into the final answer text and preserve the existing `final` event payload fields.
- If `stream_complete()` raises, fall back once to `prepared.answer_text or prepared.fallback_text or prepared.spoken_text`.

### Backend transport and tracing

- Keep `segment_queue` and the concurrent producer/consumer architecture in `ws_router`.
- Keep all WebSocket message types and payload fields unchanged.
- Continue to mark `llm_first_delta_ms` on the first emitted `text_delta` and `tts_first_segment_ms` on the first emitted `tts_segment`.
- Do not change `TTSService.stream_synthesize_segment()` behavior in this phase.

### Frontend playback policy

- Keep the `AudioContext` plus scheduled buffer playback approach.
- Reduce the default stream start policy to:
  - `initialBufferMs = 450`
  - `initialChunkCount = 1`
  - `minScheduledLeadMs = 220`
  - `scheduleLookaheadMs = 30`
- Keep the existing reset behavior and telemetry fields.

## Out of Scope

- No changes to the WebSocket public schema.
- No deep changes to `backend/storage/vendor/CosyVoice/...`.
- No changes to TTS segmentation thresholds in this phase.
- No switch to `AudioWorklet`.

## Tests

- Backend unit tests for real incremental LLM streaming.
- Backend unit tests for LLM stream failure fallback.
- Existing WebSocket streaming tests updated to confirm event ordering and trace coverage still hold.
- Frontend unit tests updated for the new buffering policy.

## Follow-up Trigger

Start phase 2 only if phase 1 is complete and either:

- median `max_chunk_gap_ms > 1500`, or
- median `tts_first_audio_chunk_ms - llm_first_delta_ms > 2500`

In phase 2, the only allowed deep dependency changes are in `backend/storage/vendor/CosyVoice/...`.
