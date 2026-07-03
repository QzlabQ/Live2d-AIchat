# Phase 2 TTS Upgrade And Lip Sync Redesign

## Background

Phase 2 originally used `CosyVoice-300M-SFT + inference_sft`. That path is now deprecated for this project because:

- audio quality is not good enough for the milestone demo
- `inference_sft` does not support natural language emotion control
- the current emotion system cannot drive voice style in a meaningful way
- the existing lip-sync timing still relies on approximate timing for some engines

The new target is:

- switch to `CosyVoice2-0.5B + inference_instruct2`
- bind TTS reference audio to `avatar_config`
- make `happy / excited / thinking / sad / neutral` affect both facial expression and speech instruction
- improve lip sync timing with structured timing data when available, and high-quality waveform timing fallback when it is not

## User Decisions Already Confirmed

- use a temporary sample reference audio first, then replace it later with the formal guide voice
- bind TTS voice configuration to `avatar_config`, not a global config
- implement full emotion-to-TTS instruction linkage now
- use a dual-path lip-sync design:
  - prefer structured timing or duration data if the active CosyVoice2 runtime exposes it
  - fall back to waveform-envelope-derived timing if the current runtime does not expose stable timing data

## Goals

- replace the current local TTS backend with `CosyVoice2-0.5B + inference_instruct2`
- keep the current WebSocket chat flow intact for frontend integration
- store per-avatar TTS reference audio and related synthesis parameters
- let backend emotion classification affect the generated speech style
- improve lip-sync precision without blocking the milestone on a specific vendor output shape
- preserve compatibility with the current frontend phoneme playback protocol

## Non-Goals

- no full voice asset library in this phase
- no voice upload UI in this phase
- no training, fine-tuning, or voice cloning workflow in this phase
- no admin sound preview page in this phase
- no migration to Alembic in this phase

## Current Constraints

### CosyVoice2 runtime constraint

The checked-in local CosyVoice code confirms that `inference_instruct2` is the correct synthesis entry point for `CosyVoice2-0.5B`:

- [backend/storage/vendor/CosyVoice/cosyvoice/cli/cosyvoice.py](</E:/2026spring/software contest/AI-chat-live2d/backend/storage/vendor/CosyVoice/cosyvoice/cli/cosyvoice.py:177>)

However, the currently inspected local Python generator path visibly yields `tts_speech` data and does not guarantee that `duration`, `alignment`, or `phoneme` fields are always exposed through the same public result shape:

- [backend/storage/vendor/CosyVoice/cosyvoice/cli/model.py](</E:/2026spring/software contest/AI-chat-live2d/backend/storage/vendor/CosyVoice/cosyvoice/cli/model.py:361>)
- [backend/storage/models/CosyVoice2-0.5B/README.md](</E:/2026spring/software contest/AI-chat-live2d/backend/storage/models/CosyVoice2-0.5B/README.md:1>)

Therefore the implementation must not hard-code the assumption that a stable `duration` field is always present in the current local runtime.

### Database migration constraint

The project initializes tables with `Base.metadata.create_all()` and does not use Alembic:

- [backend/app/db/session.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/db/session.py:1>)

That means existing SQLite databases will not gain new columns automatically. This redesign must include a startup-compatible manual migration step for `avatar_config`.

## Proposed Architecture

### End-to-end flow

The runtime flow remains:

`ASR -> chat / RAG -> emotion -> streamed text -> TTS -> audio + phoneme frames -> Live2D`

The key backend change is inside TTS synthesis:

1. fetch `avatar_config`
2. resolve reference audio path and reference transcript from avatar config
3. map detected emotion to a Chinese instruction template
4. call `CosyVoice2.inference_instruct2(...)`
5. convert audio payload to WAV bytes
6. derive lip-sync frames from:
   - structured timing data if available
   - otherwise waveform envelope timing
7. send `audio` and `phonemes` through the existing WebSocket protocol

### Why avatar-bound config

Binding TTS settings to `avatar_config` is the lightest design that supports future work:

- replacing the temporary guide voice later
- per-avatar voice tuning
- frontend or admin voice switching in a later phase

This avoids a second data model redesign when voice selection becomes a user-facing feature.

## Data Model Changes

File:

- [backend/app/db/models.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/db/models.py:1>)

Extend `AvatarConfig` with the following fields:

- `tts_reference_audio_path: str`
  - project-local path to the reference WAV file used by `inference_instruct2`
- `tts_reference_text: str`
  - transcript matching the reference audio
- `tts_speed: float`
  - default `1.0`
- `tts_emotion_enabled: bool`
  - default `true`

Keep existing fields:

- `model_path`
- `voice_id`
- `persona`

### `voice_id` compatibility role

`voice_id` should remain in the schema for compatibility, but its meaning changes:

- short-term: display name or compatibility alias
- not the primary CosyVoice2 synthesis selector anymore

This avoids breaking existing frontend assumptions and old seeded rows immediately.

## API Changes

Files:

- [backend/app/api/routes/avatar.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/api/routes/avatar.py:1>)
- [backend/app/schemas/avatar.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/schemas/avatar.py:1>)

Continue to use:

- `GET /api/v1/admin/avatar/config`
- `PUT /api/v1/admin/avatar/config`

Add the new TTS fields to both response and update payloads:

- `tts_reference_audio_path`
- `tts_reference_text`
- `tts_speed`
- `tts_emotion_enabled`

### Validation rules

- `tts_reference_audio_path` must not be empty when `TTS_ENGINE=cosyvoice`
- `tts_speed` must be positive and bounded to a safe range such as `0.5 <= speed <= 1.5`
- `tts_reference_audio_path` should resolve under the backend workspace or storage directory
- if `tts_reference_audio_path` does not exist, the API should reject the update clearly

## Configuration Changes

File:

- [backend/app/core/config.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/core/config.py:1>)

Environment configuration should move from SFT assumptions to CosyVoice2 assumptions:

- `TTS_ENGINE=cosyvoice`
- `TTS_COSYVOICE_MODEL_PATH=./storage/models/CosyVoice2-0.5B`
- `TTS_COSYVOICE_CODE_PATH=./storage/vendor/CosyVoice`
- `TTS_COSYVOICE_DEVICE=cuda`
- `TTS_COSYVOICE_SAMPLE_RATE` should follow the active model sample rate

Add backend defaults for avatar seeding:

- default temporary reference audio path
- default temporary reference text
- default `tts_speed=1.0`
- default `tts_emotion_enabled=true`

The `.env` file remains the place for engine-level defaults, but per-avatar voice behavior comes from the database row.

## TTS Service Redesign

File:

- [backend/app/services/tts.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/services/tts.py:1>)

### Service responsibilities

The TTS service should be expanded to:

- load `CosyVoice2` instead of relying on `inference_sft`
- synthesize from `inference_instruct2`
- build Chinese instruction prompts from emotion labels
- resolve avatar-specific reference audio
- extract or derive lip-sync timing
- preserve fallback behavior if local CosyVoice fails

### Emotion instruction mapping

Recommended mapping:

- `happy` -> `用愉快、亲切、自然的语气介绍这段内容。<|endofprompt|>`
- `excited` -> `用热情、兴奋、感染力强的语气介绍这段内容。<|endofprompt|>`
- `thinking` -> `用平静、思考感更强、略带停顿的语气介绍这段内容。<|endofprompt|>`
- `sad` -> `用温和、克制、略低沉的语气介绍这段内容。<|endofprompt|>`
- `neutral` -> `用自然、友好、清晰的语气介绍这段内容。<|endofprompt|>`

If `tts_emotion_enabled` is false, always use the neutral instruction.

### Method signature changes

`synthesize_chunk(...)` should accept enough context to synthesize per-avatar speech:

- `text`
- `seq`
- `emotion`
- `voice_id` for compatibility
- `reference_audio_path`
- `reference_text`
- `speed`

The WebSocket route may either pass the full avatar config or pass extracted fields to the service. Passing explicit values is preferred to keep the TTS service decoupled from ORM objects.

### CosyVoice runtime loading

Model loading should still:

- import `cosyvoice.cli.cosyvoice`
- instantiate `CosyVoice2`
- resolve device from config
- fail clearly when CUDA is requested but unavailable

This is consistent with the current local loading pattern and avoids introducing a separate runtime wrapper prematurely.

## Lip-Sync Timing Design

### Protocol compatibility

The frontend currently consumes:

- `audio`
- `phonemes`

and binds lip sync to real `audio.currentTime`:

- [frontend/src/App.vue](</E:/2026spring/software contest/AI-chat-live2d/frontend/src/App.vue:1>)
- [frontend/src/components/Live2DStage.vue](</E:/2026spring/software contest/AI-chat-live2d/frontend/src/components/Live2DStage.vue:1>)

This is already the correct playback model. The redesign should keep the same `phonemes` event shape:

- `ph`
- `start`
- `end`
- `openY`
- `form`

### Timing source priority

Priority order:

1. structured timing returned by the active CosyVoice2 runtime
2. waveform-envelope-derived timing generated from the synthesized audio
3. current text-driven fallback only as the final degradation path

### Structured timing path

If a runtime result contains stable structured timing fields, the backend should:

- normalize vendor-specific keys into an internal list of timed units
- convert each unit into a mouth shape
- emit `phonemes` with direct `start/end`

Possible keys to probe safely:

- `duration`
- `alignment`
- `alignments`
- `phonemes`
- `phoneme_alignment`

The implementation must treat these as optional and version-dependent.

### Waveform-envelope fallback

If structured timing is not exposed in the current runtime, generate timing frames from the synthesized waveform:

1. decode audio to mono PCM
2. compute short-window RMS or energy envelope
3. normalize and smooth the curve
4. segment the curve into fixed-timestep frames, such as 25 Hz or 50 Hz
5. map energy levels to mouth openness
6. emit short `phonemes` frames using generic shapes such as:
   - energetic frame -> `a`
   - medium frame -> `e`
   - low frame -> `N`
7. preserve `openY/form` directly in each frame

This does not provide true phoneme identity, but it materially improves visible audio-mouth alignment and is robust against vendor output variation.

### Final fallback

Keep the existing text-driven fallback as the final degradation path in case:

- audio synthesis fails but text still exists
- runtime timing extraction fails unexpectedly

This preserves current resilience behavior.

## WebSocket Changes

File:

- [backend/app/api/ws_router.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/api/ws_router.py:1>)

Changes required:

- pass avatar TTS config into `synthesize_chunk(...)`
- pass `generated.emotion` into TTS synthesis
- preserve the existing `audio` and `phonemes` message types

No protocol-breaking frontend message redesign is needed for this phase.

## Startup Migration Strategy

Files:

- [backend/app/db/session.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/db/session.py:1>)
- new small DB compatibility helper if needed

Implement a lightweight startup migration step for SQLite:

- inspect `avatar_config` columns
- if missing:
  - `tts_reference_audio_path`
  - `tts_reference_text`
  - `tts_speed`
  - `tts_emotion_enabled`
- issue `ALTER TABLE` statements to add them
- backfill default values for existing rows

This keeps existing `phase1.db` usable without asking the user to rebuild the database.

## Frontend Scope For This Phase

Files likely touched later:

- [frontend/src/App.vue](</E:/2026spring/software contest/AI-chat-live2d/frontend/src/App.vue:1>)
- [frontend/src/components/Live2DStage.vue](</E:/2026spring/software contest/AI-chat-live2d/frontend/src/components/Live2DStage.vue:1>)

Required frontend work should stay minimal:

- keep current `phonemes` playback handling
- if needed, make the fallback smoother for denser frame streams
- optionally expose small debug telemetry later, but not required for this redesign

Because the current frontend already binds mouth animation to actual audio playback time, backend timing improvements should immediately translate into better sync without a protocol rewrite.

## Error Handling

### Invalid reference audio

If the avatar reference audio path is missing or unreadable:

- TTS should fail clearly in logs
- the websocket response should still degrade gracefully
- if possible, fall back to edge TTS or mock fallback depending on the configured engine path

### CosyVoice runtime failure

If local CosyVoice2 throws at runtime:

- preserve current service degradation strategy
- emit fallback lip-sync frames when audio cannot be produced
- do not crash the WebSocket session

### Unsupported timing output

If a runtime output contains no structured timing data:

- log that the service is using waveform-envelope fallback
- continue producing `phonemes`

This is an expected operational path, not an error.

## Acceptance Criteria

### Functional

- text chat produces local CosyVoice2 audio
- audio style changes when emotion changes
- avatar reference audio is read from `avatar_config`
- admin avatar config API can read and update the new TTS fields
- existing database upgrades automatically on startup

### Lip sync

- frontend still receives `audio` and `phonemes`
- mouth movement is visibly aligned to audio playback
- target sync error remains under `80 ms` during manual verification

### Resilience

- if structured timing is unavailable, waveform-envelope fallback still drives the mouth
- if local TTS fails, the session does not hard-crash

## Testing Strategy

### Backend automated tests

Extend:

- [backend/tests/test_tts.py](</E:/2026spring/software contest/AI-chat-live2d/backend/tests/test_tts.py:1>)

Add tests for:

- emotion label to instruction text mapping
- `inference_instruct2` call signature and argument ordering
- avatar reference path resolution
- structured timing normalization when timing keys are present
- waveform-envelope fallback generation when timing keys are absent
- migration helper adding new `avatar_config` columns for an old SQLite schema

### API tests

Add coverage for:

- `GET /admin/avatar/config` includes new fields
- `PUT /admin/avatar/config` validates and persists them

### Manual verification

Manual acceptance script:

1. start backend with `CosyVoice2-0.5B` on GPU
2. seed avatar config with temporary reference audio
3. ask prompts likely to generate each target emotion
4. confirm:
   - audio is generated
   - emotion changes both expression and voice style
   - lip sync follows audio without obvious drift
5. verify existing DB upgrades without deleting `phase1.db`

## Future Extension Path

This design intentionally sets up the next TTS tasks without implementing them now:

- replace the temporary sample audio with the formal guide voice
- add admin-managed voice profiles
- add frontend or admin dropdown voice switching
- add richer TTS control such as style, emotion intensity, and speaking mode
- add audio preview and validation tooling for reference assets

## Implementation Impact Summary

Primary backend files expected to change in implementation:

- [backend/app/core/config.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/core/config.py:1>)
- [backend/app/db/models.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/db/models.py:1>)
- [backend/app/db/session.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/db/session.py:1>)
- [backend/app/schemas/avatar.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/schemas/avatar.py:1>)
- [backend/app/api/routes/avatar.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/api/routes/avatar.py:1>)
- [backend/app/api/ws_router.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/api/ws_router.py:1>)
- [backend/app/services/tts.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/services/tts.py:1>)
- [backend/tests/test_tts.py](</E:/2026spring/software contest/AI-chat-live2d/backend/tests/test_tts.py:1>)

Frontend changes should likely remain limited unless runtime testing shows the denser lip-sync frame stream needs playback smoothing adjustments.
