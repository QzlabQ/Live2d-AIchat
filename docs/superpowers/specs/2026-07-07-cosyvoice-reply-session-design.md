# CosyVoice Reply Session Design

## Summary

Phase 2 upgrades the TTS path from per-segment CosyVoice calls to a reply-scoped streaming session. The public WebSocket protocol stays unchanged. The backend still receives `tts_segment` boundaries from `chat.py`, but those boundaries now feed a single reply-level CosyVoice stream instead of restarting TTS for every segment.

## Problem

The Phase 1 pipeline already streams LLM deltas into `tts_segment` events, but the TTS layer still calls `inference_instruct2(..., stream=True)` once per segment. That recreates CosyVoice session state for every chunk, which increases segment gaps and resets local prosody/cache behavior inside the model runtime.

## Constraints

- Do not change the WebSocket wire protocol.
- Keep the producer/consumer queue shape in `ws_router.py`.
- Do not edit model weights.
- `backend/storage/**` is gitignored in this repository, so direct vendor source edits there are not commit-safe.

## Design

### Reply-scoped TTS session

- `chat.py` still emits `tts_segment`.
- `ws_router.py` now assigns a stable `segment_id` when enqueueing those segments.
- `TTSService.stream_synthesize_reply(...)` consumes the full async segment stream once per reply.
- For CosyVoice, the service opens one background inference thread and feeds all segment text into a single streaming generator.

### Vendor-level behavior exposure

CosyVoice already contains the necessary internals:

- generator-aware text token extraction in `CosyVoiceFrontEnd`
- bidirectional text streaming in `Qwen2LM.inference_bistream()`
- reply-scoped cache/state inside `CosyVoice2Model.tts()`

The missing piece is an explicit public entrypoint. Because the vendor directory is gitignored, this round exposes that behavior through a tracked runtime patch in `backend/app/services/tts.py`:

- add `iter_text_normalize(...)` to `CosyVoiceFrontEnd` if missing
- add `inference_instruct2_reply(...)` to `CosyVoice2` / `CosyVoice3` if missing

This keeps the implementation reproducible and committable while still changing the effective vendor-layer API used by the app.

### Segment identity

The frontend still receives `segment_id` and `chunk_index`. In reply-scoped mode:

- `segment_id` is assigned when `tts_segment` is enqueued
- `chunk_index` is global within the reply-scoped audio stream

This preserves compatibility for audio/viseme chunk matching without requiring the frontend to understand reply sessions.

## Non-goals

- No AudioWorklet migration
- No protocol changes
- No retuning of `TTSSegmenter` thresholds in this round

## Risks

- The first chunk is force-tagged to the first queued segment to avoid losing segment `0` when CosyVoice consumes text ahead of audio emission.
- Prompt feature monkey-patching remains process-global and is still a concurrency risk for future multi-session GPU load.
- Final chunk `is_final` semantics are still object-mutation based and should be revisited separately if frontend behavior starts depending on that bit alone.
