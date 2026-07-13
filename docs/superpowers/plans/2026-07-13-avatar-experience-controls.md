# Avatar Experience Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add resizable Live2D avatar display controls for the visitor experience and add an admin emotion/expression preview panel with the same lava-lamp telemetry used by the visitor page.

**Architecture:** Persist avatar display defaults on `avatar_config`, expose them through existing admin and visitor avatar APIs, then layer visitor-local overrides in `localStorage`. Keep Pixi/Live2D runtime changes inside `Live2DStage`, while moving display-parameter merge logic and emotion-lamp rendering into focused, testable frontend modules.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, SQLite compatibility migrations, Vue 3, TypeScript, Vitest, Pixi Live2D.

---

## File Structure

- Modify `backend/app/db/models.py`: add `display_scale`, `display_offset_x`, `display_offset_y`, `stage_height` columns to `AvatarConfig`.
- Modify `backend/app/db/migrations.py`: add `ensure_avatar_config_display_columns()` for legacy SQLite databases.
- Modify `backend/app/db/session.py`: call the new migration during `init_db()`.
- Modify `backend/app/db/seed.py`: seed default display values for new databases.
- Modify `backend/app/schemas/avatar.py`: include display fields in admin config/profile create/update schemas.
- Modify `backend/app/schemas/visitor.py`: include display fields in visitor avatar profile summary.
- Modify `backend/app/api/routes/avatar.py`: apply and serialize display fields.
- Modify `backend/app/api/routes/visitor.py`: expose display fields to visitor clients.
- Modify `backend/tests/test_avatar_config.py`: cover migration, API update, and validation.
- Modify `backend/tests/test_sessions_api.py`: ensure `init_db()` calls the new migration.
- Create `frontend/src/lib/avatarDisplay.ts`: range constants, normalization, default/local override merge, storage helpers, stage style helper.
- Create `frontend/src/lib/avatarDisplay.test.ts`: test display helper behavior.
- Create `frontend/src/components/EmotionLamp.vue`: reusable lava-lamp component.
- Create `frontend/src/components/AvatarDisplayControls.vue`: reusable display control panel.
- Create `frontend/src/components/AdminEmotionPreviewPanel.vue`: admin emotion preview controls, lamp, and parameter summary.
- Modify `frontend/src/components/Live2DStage.vue`: accept model display props and use them when positioning the model.
- Modify `frontend/src/types/admin.ts`: add display fields to admin avatar types.
- Modify `frontend/src/types/visitor.ts`: add display fields to visitor avatar profile type.
- Modify `frontend/src/services/adminApi.ts`: map display fields in admin API payloads.
- Modify `frontend/src/services/visitorApi.ts`: map display fields from visitor avatar API.
- Modify `frontend/src/App.vue`: add visitor display controls, local override state, and pass props to `Live2DStage`.
- Modify `frontend/src/AdminApp.vue`: add display fields to avatar form and add admin emotion preview panel.
- Modify `frontend/src/style.css`: style visitor display controls and resizable stage card.
- Modify `frontend/src/admin.css`: style admin display fields and emotion preview panel.
- Modify `frontend/src/App.chatLayout.test.ts`: assert visitor display controls are present without breaking chat layout.
- Create `frontend/src/AdminApp.avatarExperience.test.ts`: source-level guard for admin emotion preview and display fields.
- Modify `docs/roadmap.md`: mark Phase 4 digital human idle/display/emotion preview polish progress.

---

### Task 1: Backend Display Fields, Migration, And API Validation

**Files:**
- Modify: `backend/app/db/models.py`
- Modify: `backend/app/db/migrations.py`
- Modify: `backend/app/db/session.py`
- Modify: `backend/app/db/seed.py`
- Modify: `backend/app/schemas/avatar.py`
- Modify: `backend/app/schemas/visitor.py`
- Modify: `backend/app/api/routes/avatar.py`
- Modify: `backend/app/api/routes/visitor.py`
- Test: `backend/tests/test_avatar_config.py`
- Test: `backend/tests/test_sessions_api.py`

- [ ] **Step 1: Write failing migration and API tests**

Add these imports to `backend/tests/test_avatar_config.py`:

```python
from app.db.migrations import (
    ensure_avatar_config_admin_columns,
    ensure_avatar_config_display_columns,
    ensure_avatar_config_profile_columns,
    ensure_avatar_config_response_language_column,
    ensure_avatar_config_tts_columns,
)
```

Add this test to `AvatarConfigMigrationTestCase`:

```python
    async def test_sqlite_migration_adds_display_columns_to_old_schema(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / 'old.db'
            engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
            try:
                async with engine.begin() as connection:
                    await connection.execute(text('''CREATE TABLE avatar_config (id INTEGER PRIMARY KEY AUTOINCREMENT, model_path VARCHAR(255) NOT NULL, voice_id VARCHAR(100) NOT NULL, persona TEXT NOT NULL, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)'''))
                    await connection.execute(text('''INSERT INTO avatar_config (model_path, voice_id, persona) VALUES ('model', 'voice', 'persona')'''))

                await ensure_avatar_config_display_columns(engine)

                async with engine.connect() as connection:
                    columns = (await connection.execute(text('PRAGMA table_info(avatar_config)'))).mappings().all()
                    names = {column['name'] for column in columns}
                    row = (await connection.execute(text('SELECT display_scale, display_offset_x, display_offset_y, stage_height FROM avatar_config LIMIT 1'))).mappings().one()

                self.assertIn('display_scale', names)
                self.assertIn('display_offset_x', names)
                self.assertIn('display_offset_y', names)
                self.assertIn('stage_height', names)
                self.assertEqual(row['display_scale'], 1.0)
                self.assertEqual(row['display_offset_x'], 0.0)
                self.assertEqual(row['display_offset_y'], 0.0)
                self.assertEqual(row['stage_height'], 420)
            finally:
                await engine.dispose()
```

Add this test to `AvatarConfigApiTestCase`:

```python
    async def test_avatar_config_api_reads_and_updates_display_fields(self) -> None:
        with TemporaryDirectory() as temp_dir, TemporaryDirectory(dir=BACKEND_ROOT) as prompt_dir:
            db_path = Path(temp_dir) / 'api.db'
            engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            prompt_wav = Path(prompt_dir) / 'prompt.wav'
            prompt_wav.write_bytes(b'fake wav')

            try:
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.create_all)

                async with session_factory() as session:
                    session.add(
                        AvatarConfig(
                            model_path='model',
                            voice_id='voice',
                            persona='persona',
                            tts_reference_audio_path=str(prompt_wav),
                            tts_reference_text='text',
                            display_scale=1.0,
                            display_offset_x=0.0,
                            display_offset_y=0.0,
                            stage_height=420,
                        )
                    )
                    await session.commit()

                    before = await get_avatar_config(session)
                    self.assertEqual(before.display_scale, 1.0)
                    self.assertEqual(before.stage_height, 420)

                    await update_avatar_config(
                        AvatarConfigUpdate(
                            display_scale=1.24,
                            display_offset_x=0.08,
                            display_offset_y=-0.12,
                            stage_height=560,
                        ),
                        db=session,
                    )

                    after = await get_avatar_config(session)
                    self.assertEqual(after.display_scale, 1.24)
                    self.assertEqual(after.display_offset_x, 0.08)
                    self.assertEqual(after.display_offset_y, -0.12)
                    self.assertEqual(after.stage_height, 560)
            finally:
                await engine.dispose()
```

Add this validation test to `AvatarConfigApiTestCase`:

```python
    def test_avatar_config_update_rejects_out_of_range_display_fields(self) -> None:
        invalid_payloads = [
            {'display_scale': 0.59},
            {'display_scale': 1.81},
            {'display_offset_x': -0.51},
            {'display_offset_x': 0.51},
            {'display_offset_y': -0.51},
            {'display_offset_y': 0.51},
            {'stage_height': 319},
            {'stage_height': 761},
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    AvatarConfigUpdate(**payload)
```

Update `backend/tests/test_sessions_api.py::test_init_db_triggers_session_updated_at_migration` by adding this patch and assertion:

```python
            patch("app.db.session.ensure_avatar_config_display_columns", new=AsyncMock()) as ensure_avatar_display_mock,
```

```python
            ensure_avatar_display_mock.assert_awaited_once_with(engine_mock)
```

- [ ] **Step 2: Run backend tests and verify they fail for missing display support**

Run:

```powershell
cd backend
python -m unittest tests.test_avatar_config tests.test_sessions_api -v
```

Expected: FAIL because `ensure_avatar_config_display_columns`, model fields, and schema fields do not exist.

- [ ] **Step 3: Add model fields**

Add these columns to `AvatarConfig` in `backend/app/db/models.py` after `tts_emotion_enabled`:

```python
    display_scale: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    display_offset_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    display_offset_y: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stage_height: Mapped[int] = mapped_column(Integer, nullable=False, default=420)
```

- [ ] **Step 4: Add SQLite migration**

Add this function to `backend/app/db/migrations.py` after `ensure_avatar_config_response_language_column()`:

```python
async def ensure_avatar_config_display_columns(engine: AsyncEngine) -> None:
    if not engine.url.get_backend_name().startswith('sqlite'):
        return

    async with engine.begin() as connection:
        result = await connection.execute(text('PRAGMA table_info(avatar_config)'))
        existing = {row._mapping['name'] for row in result}
        if not existing:
            return

        column_sql = {
            'display_scale': 'ALTER TABLE avatar_config ADD COLUMN display_scale FLOAT NOT NULL DEFAULT 1.0',
            'display_offset_x': 'ALTER TABLE avatar_config ADD COLUMN display_offset_x FLOAT NOT NULL DEFAULT 0.0',
            'display_offset_y': 'ALTER TABLE avatar_config ADD COLUMN display_offset_y FLOAT NOT NULL DEFAULT 0.0',
            'stage_height': 'ALTER TABLE avatar_config ADD COLUMN stage_height INTEGER NOT NULL DEFAULT 420',
        }

        for column, statement in column_sql.items():
            if column not in existing:
                await connection.execute(text(statement))

        await connection.execute(
            text('UPDATE avatar_config SET display_scale = 1.0 WHERE display_scale IS NULL')
        )
        await connection.execute(
            text('UPDATE avatar_config SET display_offset_x = 0.0 WHERE display_offset_x IS NULL')
        )
        await connection.execute(
            text('UPDATE avatar_config SET display_offset_y = 0.0 WHERE display_offset_y IS NULL')
        )
        await connection.execute(
            text('UPDATE avatar_config SET stage_height = 420 WHERE stage_height IS NULL')
        )
```

Modify `backend/app/db/session.py` imports:

```python
    ensure_avatar_config_display_columns,
```

Call it in `init_db()` after `ensure_avatar_config_response_language_column(engine, settings)`:

```python
    await ensure_avatar_config_display_columns(engine)
```

- [ ] **Step 5: Add schema fields and validation**

In `backend/app/schemas/avatar.py`, add these fields to `AvatarConfigResponse`:

```python
    display_scale: float
    display_offset_x: float
    display_offset_y: float
    stage_height: int
```

Add these fields to `AvatarConfigUpdate`:

```python
    display_scale: float | None = Field(default=None, ge=0.6, le=1.8)
    display_offset_x: float | None = Field(default=None, ge=-0.5, le=0.5)
    display_offset_y: float | None = Field(default=None, ge=-0.5, le=0.5)
    stage_height: int | None = Field(default=None, ge=320, le=760)
```

Add these fields to `AvatarProfileSummary`:

```python
    display_scale: float
    display_offset_x: float
    display_offset_y: float
    stage_height: int
```

Add these fields to `AvatarProfileCreate`:

```python
    display_scale: float = Field(default=1.0, ge=0.6, le=1.8)
    display_offset_x: float = Field(default=0.0, ge=-0.5, le=0.5)
    display_offset_y: float = Field(default=0.0, ge=-0.5, le=0.5)
    stage_height: int = Field(default=420, ge=320, le=760)
```

In `backend/app/schemas/visitor.py`, add these fields to `VisitorAvatarProfileSummary`:

```python
    display_scale: float
    display_offset_x: float
    display_offset_y: float
    stage_height: int
```

- [ ] **Step 6: Apply and serialize display fields in routes**

In `backend/app/api/routes/avatar.py`, add this block to `apply_avatar_payload()` after TTS fields:

```python
    if getattr(payload, "display_scale", None) is not None:
        avatar.display_scale = payload.display_scale
    if getattr(payload, "display_offset_x", None) is not None:
        avatar.display_offset_x = payload.display_offset_x
    if getattr(payload, "display_offset_y", None) is not None:
        avatar.display_offset_y = payload.display_offset_y
    if getattr(payload, "stage_height", None) is not None:
        avatar.stage_height = payload.stage_height
```

Add display fields to `serialize_avatar_profile()`:

```python
        display_scale=profile.display_scale,
        display_offset_x=profile.display_offset_x,
        display_offset_y=profile.display_offset_y,
        stage_height=profile.stage_height,
```

Add display fields when creating `AvatarConfig` in `create_avatar_profile()`:

```python
        display_scale=payload.display_scale,
        display_offset_x=payload.display_offset_x,
        display_offset_y=payload.display_offset_y,
        stage_height=payload.stage_height,
```

In `backend/app/api/routes/visitor.py`, add display fields to `serialize_avatar_profile()`:

```python
        display_scale=profile.display_scale,
        display_offset_x=profile.display_offset_x,
        display_offset_y=profile.display_offset_y,
        stage_height=profile.stage_height,
```

- [ ] **Step 7: Seed display defaults**

In `backend/app/db/seed.py`, add display values to the default `AvatarConfig(...)` creation:

```python
            display_scale=1.0,
            display_offset_x=0.0,
            display_offset_y=0.0,
            stage_height=420,
```

- [ ] **Step 8: Run backend tests and verify they pass**

Run:

```powershell
cd backend
python -m unittest tests.test_avatar_config tests.test_sessions_api -v
```

Expected: PASS.

- [ ] **Step 9: Commit backend display API work**

Run:

```powershell
git add backend/app/db/models.py backend/app/db/migrations.py backend/app/db/session.py backend/app/db/seed.py backend/app/schemas/avatar.py backend/app/schemas/visitor.py backend/app/api/routes/avatar.py backend/app/api/routes/visitor.py backend/tests/test_avatar_config.py backend/tests/test_sessions_api.py
git commit -m "feat: add avatar display configuration fields"
```

---

### Task 2: Frontend Display Domain Helpers And API Mapping

**Files:**
- Create: `frontend/src/lib/avatarDisplay.ts`
- Create: `frontend/src/lib/avatarDisplay.test.ts`
- Modify: `frontend/src/types/admin.ts`
- Modify: `frontend/src/types/visitor.ts`
- Modify: `frontend/src/services/adminApi.ts`
- Modify: `frontend/src/services/visitorApi.ts`

- [ ] **Step 1: Write failing helper tests**

Create `frontend/src/lib/avatarDisplay.test.ts`:

```typescript
import { describe, expect, it, vi } from 'vitest'

import {
  AVATAR_DISPLAY_DEFAULTS,
  buildAvatarDisplayStorageKey,
  buildStageHeightStyle,
  clampAvatarDisplayConfig,
  loadAvatarDisplayOverride,
  mergeAvatarDisplayConfig,
  saveAvatarDisplayOverride,
} from './avatarDisplay'

describe('avatar display config', () => {
  it('clamps display values into safe ranges', () => {
    const config = clampAvatarDisplayConfig({
      displayScale: 3,
      displayOffsetX: -2,
      displayOffsetY: 2,
      stageHeight: 1200,
    })

    expect(config).toEqual({
      displayScale: 1.8,
      displayOffsetX: -0.5,
      displayOffsetY: 0.5,
      stageHeight: 760,
    })
  })

  it('merges defaults, backend values, and local overrides in priority order', () => {
    const merged = mergeAvatarDisplayConfig(
      {
        displayScale: 1.1,
        displayOffsetX: 0.1,
        displayOffsetY: 0.2,
        stageHeight: 430,
      },
      {
        displayScale: 1.3,
        displayOffsetY: -0.1,
      },
    )

    expect(merged).toEqual({
      displayScale: 1.3,
      displayOffsetX: 0.1,
      displayOffsetY: -0.1,
      stageHeight: 430,
    })
  })

  it('stores visitor overrides under an avatar-specific key', () => {
    const storage = {
      data: new Map<string, string>(),
      getItem: vi.fn((key: string) => storage.data.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => {
        storage.data.set(key, value)
      }),
      removeItem: vi.fn((key: string) => {
        storage.data.delete(key)
      }),
    } as unknown as Storage

    saveAvatarDisplayOverride(storage, 7, { displayScale: 1.25, stageHeight: 520 })

    expect(storage.setItem).toHaveBeenCalledWith(
      buildAvatarDisplayStorageKey(7),
      JSON.stringify({ displayScale: 1.25, stageHeight: 520 }),
    )
    expect(loadAvatarDisplayOverride(storage, 7)).toEqual({
      ...AVATAR_DISPLAY_DEFAULTS,
      displayScale: 1.25,
      stageHeight: 520,
    })
  })

  it('ignores corrupt localStorage payloads', () => {
    const storage = {
      getItem: vi.fn(() => '{not json'),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    } as unknown as Storage

    expect(loadAvatarDisplayOverride(storage, 2)).toBeNull()
  })

  it('builds a CSS height style for the stage card', () => {
    expect(buildStageHeightStyle({ stageHeight: 512 })).toEqual({
      '--avatar-stage-height': '512px',
    })
  })
})
```

- [ ] **Step 2: Run helper tests and verify they fail**

Run:

```powershell
cd frontend
npm run test -- src/lib/avatarDisplay.test.ts
```

Expected: FAIL because `avatarDisplay.ts` does not exist.

- [ ] **Step 3: Implement display helper module**

Create `frontend/src/lib/avatarDisplay.ts`:

```typescript
export interface AvatarDisplayConfig {
  displayScale: number
  displayOffsetX: number
  displayOffsetY: number
  stageHeight: number
}

export type AvatarDisplayConfigInput = Partial<AvatarDisplayConfig> | null | undefined

export const AVATAR_DISPLAY_DEFAULTS: AvatarDisplayConfig = {
  displayScale: 1,
  displayOffsetX: 0,
  displayOffsetY: 0,
  stageHeight: 420,
}

export const AVATAR_DISPLAY_LIMITS = {
  displayScale: { min: 0.6, max: 1.8 },
  displayOffsetX: { min: -0.5, max: 0.5 },
  displayOffsetY: { min: -0.5, max: 0.5 },
  stageHeight: { min: 320, max: 760 },
} as const

function clamp(value: number | undefined, min: number, max: number, fallback: number) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return fallback
  }
  return Math.min(max, Math.max(min, value))
}

export function clampAvatarDisplayConfig(input: AvatarDisplayConfigInput): AvatarDisplayConfig {
  return {
    displayScale: clamp(
      input?.displayScale,
      AVATAR_DISPLAY_LIMITS.displayScale.min,
      AVATAR_DISPLAY_LIMITS.displayScale.max,
      AVATAR_DISPLAY_DEFAULTS.displayScale,
    ),
    displayOffsetX: clamp(
      input?.displayOffsetX,
      AVATAR_DISPLAY_LIMITS.displayOffsetX.min,
      AVATAR_DISPLAY_LIMITS.displayOffsetX.max,
      AVATAR_DISPLAY_DEFAULTS.displayOffsetX,
    ),
    displayOffsetY: clamp(
      input?.displayOffsetY,
      AVATAR_DISPLAY_LIMITS.displayOffsetY.min,
      AVATAR_DISPLAY_LIMITS.displayOffsetY.max,
      AVATAR_DISPLAY_DEFAULTS.displayOffsetY,
    ),
    stageHeight: Math.round(
      clamp(
        input?.stageHeight,
        AVATAR_DISPLAY_LIMITS.stageHeight.min,
        AVATAR_DISPLAY_LIMITS.stageHeight.max,
        AVATAR_DISPLAY_DEFAULTS.stageHeight,
      ),
    ),
  }
}

export function mergeAvatarDisplayConfig(
  backendConfig: AvatarDisplayConfigInput,
  localOverride: AvatarDisplayConfigInput,
): AvatarDisplayConfig {
  return clampAvatarDisplayConfig({
    ...AVATAR_DISPLAY_DEFAULTS,
    ...backendConfig,
    ...localOverride,
  })
}

export function buildAvatarDisplayStorageKey(avatarProfileId: number | string) {
  return `ai-chat-live2d.avatar-display.${avatarProfileId}`
}

export function loadAvatarDisplayOverride(
  storage: Pick<Storage, 'getItem'>,
  avatarProfileId: number | string | null | undefined,
): AvatarDisplayConfig | null {
  if (avatarProfileId === null || avatarProfileId === undefined || avatarProfileId === '') {
    return null
  }

  const raw = storage.getItem(buildAvatarDisplayStorageKey(avatarProfileId))
  if (!raw) {
    return null
  }

  try {
    return clampAvatarDisplayConfig(JSON.parse(raw) as AvatarDisplayConfigInput)
  } catch {
    return null
  }
}

export function saveAvatarDisplayOverride(
  storage: Pick<Storage, 'setItem'>,
  avatarProfileId: number | string,
  config: AvatarDisplayConfigInput,
) {
  storage.setItem(buildAvatarDisplayStorageKey(avatarProfileId), JSON.stringify(config ?? {}))
}

export function clearAvatarDisplayOverride(
  storage: Pick<Storage, 'removeItem'>,
  avatarProfileId: number | string,
) {
  storage.removeItem(buildAvatarDisplayStorageKey(avatarProfileId))
}

export function buildStageHeightStyle(config: Pick<AvatarDisplayConfig, 'stageHeight'>) {
  return {
    '--avatar-stage-height': `${clampAvatarDisplayConfig(config).stageHeight}px`,
  }
}
```

- [ ] **Step 4: Run helper tests and verify they pass**

Run:

```powershell
cd frontend
npm run test -- src/lib/avatarDisplay.test.ts
```

Expected: PASS.

- [ ] **Step 5: Add display fields to frontend types**

In `frontend/src/types/admin.ts`, add these fields to the avatar config/profile interfaces used by `AdminApp.vue`:

```typescript
  displayScale: number
  displayOffsetX: number
  displayOffsetY: number
  stageHeight: number
```

In `frontend/src/types/visitor.ts`, add the same fields to `VisitorAvatarProfileSummary`:

```typescript
  displayScale: number
  displayOffsetX: number
  displayOffsetY: number
  stageHeight: number
```

- [ ] **Step 6: Map display fields in admin API service**

In `frontend/src/services/adminApi.ts`, add these API fields to `AvatarConfigApi` and `AvatarProfileSummaryApi`:

```typescript
  display_scale: number
  display_offset_x: number
  display_offset_y: number
  stage_height: number
```

In the admin mapper, add:

```typescript
    displayScale: payload.display_scale,
    displayOffsetX: payload.display_offset_x,
    displayOffsetY: payload.display_offset_y,
    stageHeight: payload.stage_height,
```

When sending create/update payloads, add:

```typescript
      display_scale: payload.displayScale,
      display_offset_x: payload.displayOffsetX,
      display_offset_y: payload.displayOffsetY,
      stage_height: payload.stageHeight,
```

- [ ] **Step 7: Map display fields in visitor API service**

In `frontend/src/services/visitorApi.ts`, add these fields to `VisitorAvatarProfileSummaryApi`:

```typescript
  display_scale: number
  display_offset_x: number
  display_offset_y: number
  stage_height: number
```

Update `mapVisitorAvatarProfile()`:

```typescript
    displayScale: payload.display_scale,
    displayOffsetX: payload.display_offset_x,
    displayOffsetY: payload.display_offset_y,
    stageHeight: payload.stage_height,
```

- [ ] **Step 8: Run frontend tests**

Run:

```powershell
cd frontend
npm run test -- src/lib/avatarDisplay.test.ts
npm run build
```

Expected: both commands pass.

- [ ] **Step 9: Commit frontend display helper and API mapping**

Run:

```powershell
git add frontend/src/lib/avatarDisplay.ts frontend/src/lib/avatarDisplay.test.ts frontend/src/types/admin.ts frontend/src/types/visitor.ts frontend/src/services/adminApi.ts frontend/src/services/visitorApi.ts
git commit -m "feat: add avatar display config helpers"
```

---

### Task 3: Live2DStage Display Transform Props

**Files:**
- Modify: `frontend/src/components/Live2DStage.vue`
- Test: `frontend/src/lib/avatarDisplay.test.ts`

- [ ] **Step 1: Extend helper tests for model transform math**

Add this test to `frontend/src/lib/avatarDisplay.test.ts`:

```typescript
import { computeLive2DPlacement } from './avatarDisplay'
```

```typescript
  it('computes Live2D placement from stage size, model bounds, and display config', () => {
    const placement = computeLive2DPlacement(
      { width: 800, height: 500 },
      { width: 400, height: 1000 },
      { displayScale: 1.2, displayOffsetX: 0.1, displayOffsetY: -0.2, stageHeight: 500 },
    )

    expect(placement.scale).toBeCloseTo(0.51, 2)
    expect(placement.x).toBeCloseTo(480, 0)
    expect(placement.y).toBeCloseTo(400, 0)
  })
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
cd frontend
npm run test -- src/lib/avatarDisplay.test.ts
```

Expected: FAIL because `computeLive2DPlacement` does not exist.

- [ ] **Step 3: Implement placement helper**

Add these interfaces and function to `frontend/src/lib/avatarDisplay.ts`:

```typescript
export interface StageSize {
  width: number
  height: number
}

export interface ModelBounds {
  width: number
  height: number
}

export interface Live2DPlacement {
  scale: number
  x: number
  y: number
}

export function computeLive2DPlacement(
  stage: StageSize,
  bounds: ModelBounds,
  config: AvatarDisplayConfigInput,
): Live2DPlacement {
  const safeConfig = clampAvatarDisplayConfig(config)
  const stageWidth = Math.max(1, stage.width)
  const stageHeight = Math.max(1, stage.height)
  const modelWidth = Math.max(1, bounds.width)
  const modelHeight = Math.max(1, bounds.height)
  const baseScale = Math.min(stageWidth / modelWidth, stageHeight / modelHeight) * 0.85

  return {
    scale: baseScale * safeConfig.displayScale,
    x: stageWidth * (0.5 + safeConfig.displayOffsetX),
    y: stageHeight * (0.88 + safeConfig.displayOffsetY),
  }
}
```

- [ ] **Step 4: Run placement helper test and verify it passes**

Run:

```powershell
cd frontend
npm run test -- src/lib/avatarDisplay.test.ts
```

Expected: PASS.

- [ ] **Step 5: Wire display props into Live2DStage**

In `frontend/src/components/Live2DStage.vue`, import:

```typescript
import {
  AVATAR_DISPLAY_DEFAULTS,
  computeLive2DPlacement,
} from '../lib/avatarDisplay'
```

Change props:

```typescript
const props = withDefaults(defineProps<{
  modelPath: string
  modelScale?: number
  modelOffsetX?: number
  modelOffsetY?: number
}>(), {
  modelScale: AVATAR_DISPLAY_DEFAULTS.displayScale,
  modelOffsetX: AVATAR_DISPLAY_DEFAULTS.displayOffsetX,
  modelOffsetY: AVATAR_DISPLAY_DEFAULTS.displayOffsetY,
})
```

Update `resizeModel()` so it uses the helper:

```typescript
function resizeModel() {
  if (!stageHost.value || !model) {
    return
  }

  const bounds = model.getLocalBounds()
  const placement = computeLive2DPlacement(
    {
      width: stageHost.value.clientWidth,
      height: stageHost.value.clientHeight,
    },
    {
      width: bounds.width || model.width || 1,
      height: bounds.height || model.height || 1,
    },
    {
      displayScale: props.modelScale,
      displayOffsetX: props.modelOffsetX,
      displayOffsetY: props.modelOffsetY,
      stageHeight: stageHost.value.clientHeight,
    },
  )

  model.scale.set(placement.scale)
  model.anchor.set(0.5, 0.88)
  model.position.set(placement.x, placement.y)
}
```

Add a watcher after the existing `modelPath` watcher:

```typescript
watch(
  () => [props.modelScale, props.modelOffsetX, props.modelOffsetY],
  () => resizeModel(),
)
```

- [ ] **Step 6: Build frontend**

Run:

```powershell
cd frontend
npm run build
```

Expected: PASS. The existing Vite chunk-size warning is acceptable if it remains unchanged.

- [ ] **Step 7: Commit Live2D transform props**

Run:

```powershell
git add frontend/src/components/Live2DStage.vue frontend/src/lib/avatarDisplay.ts frontend/src/lib/avatarDisplay.test.ts
git commit -m "feat: support live2d display transforms"
```

---

### Task 4: Reusable Emotion Lamp And Display Controls Components

**Files:**
- Create: `frontend/src/components/EmotionLamp.vue`
- Create: `frontend/src/components/AvatarDisplayControls.vue`
- Modify: `frontend/src/style.css`
- Modify: `frontend/src/admin.css`
- Test: `frontend/src/components/EmotionLamp.test.ts`
- Test: `frontend/src/components/AvatarDisplayControls.test.ts`

- [ ] **Step 1: Write failing EmotionLamp source test**

Create `frontend/src/components/EmotionLamp.test.ts`:

```typescript
import { readFileSync } from 'node:fs'

import { describe, expect, test } from 'vitest'

const source = readFileSync(new URL('./EmotionLamp.vue', import.meta.url), 'utf-8')

describe('EmotionLamp component', () => {
  test('renders reusable lava lamp markup and telemetry fields', () => {
    expect(source).toContain('buildEmotionLampStyle')
    expect(source).toContain('class="emotion-lamp-shell"')
    expect(source).toContain('class="emotion-lamp"')
    expect(source).toContain('emotionTelemetry.reason')
    expect(source).toContain('emotionTelemetry.keywords')
  })
})
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
cd frontend
npm run test -- src/components/EmotionLamp.test.ts
```

Expected: FAIL because `EmotionLamp.vue` does not exist.

- [ ] **Step 3: Create EmotionLamp component**

Create `frontend/src/components/EmotionLamp.vue`:

```vue
<script setup lang="ts">
import { computed } from 'vue'

import { buildEmotionLampStyle } from '../lib/emotionLamp'
import { EMOTION_VISUALS } from '../lib/lipsync'
import type { EmotionTelemetry } from '../types/chat'

const props = defineProps<{
  emotionTelemetry: EmotionTelemetry
  stageLabel: string
  confidenceLabel: string
}>()

const emotionVisual = computed(
  () => EMOTION_VISUALS[props.emotionTelemetry.value] ?? EMOTION_VISUALS.neutral,
)
const emotionLampStyle = computed(() =>
  buildEmotionLampStyle(props.emotionTelemetry, emotionVisual.value),
)
</script>

<template>
  <div class="emotion-lamp-shell">
    <div
      class="emotion-lamp"
      :data-stage="emotionTelemetry.stage"
      :data-emotion="emotionTelemetry.value"
      :style="emotionLampStyle"
    >
      <span class="emotion-lamp-core"></span>
    </div>
    <div class="emotion-meta">
      <strong>{{ emotionVisual.label }}</strong>
      <span>阶段 {{ stageLabel }}</span>
      <span>置信度 {{ confidenceLabel }}</span>
      <span>来源 {{ emotionTelemetry.source }}</span>
    </div>
  </div>
  <p class="emotion-reason">{{ emotionTelemetry.reason }}</p>
  <p class="emotion-keywords">
    {{ emotionTelemetry.keywords.length ? emotionTelemetry.keywords.join(' / ') : '暂无显著情绪关键词' }}
  </p>
</template>
```

- [ ] **Step 4: Write failing AvatarDisplayControls source test**

Create `frontend/src/components/AvatarDisplayControls.test.ts`:

```typescript
import { readFileSync } from 'node:fs'

import { describe, expect, test } from 'vitest'

const source = readFileSync(new URL('./AvatarDisplayControls.vue', import.meta.url), 'utf-8')

describe('AvatarDisplayControls component', () => {
  test('exposes scale, offset, stage height, and reset controls', () => {
    expect(source).toContain('modelValue')
    expect(source).toContain('displayScale')
    expect(source).toContain('displayOffsetX')
    expect(source).toContain('displayOffsetY')
    expect(source).toContain('stageHeight')
    expect(source).toContain("emit('reset')")
  })
})
```

- [ ] **Step 5: Run test and verify it fails**

Run:

```powershell
cd frontend
npm run test -- src/components/AvatarDisplayControls.test.ts
```

Expected: FAIL because `AvatarDisplayControls.vue` does not exist.

- [ ] **Step 6: Create AvatarDisplayControls component**

Create `frontend/src/components/AvatarDisplayControls.vue`:

```vue
<script setup lang="ts">
import {
  AVATAR_DISPLAY_LIMITS,
  clampAvatarDisplayConfig,
  type AvatarDisplayConfig,
} from '../lib/avatarDisplay'

const props = defineProps<{
  modelValue: AvatarDisplayConfig
  compact?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: AvatarDisplayConfig]
  reset: []
}>()

function updateField(key: keyof AvatarDisplayConfig, rawValue: string | number) {
  const next = clampAvatarDisplayConfig({
    ...props.modelValue,
    [key]: Number(rawValue),
  })
  emit('update:modelValue', next)
}
</script>

<template>
  <div class="avatar-display-controls" :data-compact="compact ? 'true' : 'false'">
    <label>
      <span>模型缩放</span>
      <input
        type="range"
        :min="AVATAR_DISPLAY_LIMITS.displayScale.min"
        :max="AVATAR_DISPLAY_LIMITS.displayScale.max"
        step="0.01"
        :value="modelValue.displayScale"
        @input="updateField('displayScale', ($event.target as HTMLInputElement).value)"
      />
      <strong>{{ modelValue.displayScale.toFixed(2) }}x</strong>
    </label>
    <label>
      <span>水平偏移</span>
      <input
        type="range"
        :min="AVATAR_DISPLAY_LIMITS.displayOffsetX.min"
        :max="AVATAR_DISPLAY_LIMITS.displayOffsetX.max"
        step="0.01"
        :value="modelValue.displayOffsetX"
        @input="updateField('displayOffsetX', ($event.target as HTMLInputElement).value)"
      />
      <strong>{{ modelValue.displayOffsetX.toFixed(2) }}</strong>
    </label>
    <label>
      <span>垂直偏移</span>
      <input
        type="range"
        :min="AVATAR_DISPLAY_LIMITS.displayOffsetY.min"
        :max="AVATAR_DISPLAY_LIMITS.displayOffsetY.max"
        step="0.01"
        :value="modelValue.displayOffsetY"
        @input="updateField('displayOffsetY', ($event.target as HTMLInputElement).value)"
      />
      <strong>{{ modelValue.displayOffsetY.toFixed(2) }}</strong>
    </label>
    <label>
      <span>舞台高度</span>
      <input
        type="range"
        :min="AVATAR_DISPLAY_LIMITS.stageHeight.min"
        :max="AVATAR_DISPLAY_LIMITS.stageHeight.max"
        step="10"
        :value="modelValue.stageHeight"
        @input="updateField('stageHeight', ($event.target as HTMLInputElement).value)"
      />
      <strong>{{ modelValue.stageHeight }}px</strong>
    </label>
    <button class="avatar-display-reset" type="button" @click="emit('reset')">重置显示</button>
  </div>
</template>
```

- [ ] **Step 7: Move shared lamp CSS into global styles**

Keep the existing visitor lamp classes in `frontend/src/style.css`. Add matching admin-safe styles to `frontend/src/admin.css` so the shared `EmotionLamp` component renders correctly in admin:

```css
.emotion-lamp-shell {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 0.85rem;
}

.emotion-lamp {
  position: relative;
  width: 4.8rem;
  height: 6.4rem;
  border-radius: 2.4rem 2.4rem 2rem 2rem;
  border: 1px solid rgba(255, 255, 255, 0.46);
  overflow: hidden;
  isolation: isolate;
  background: var(--lamp-body-background);
  opacity: var(--lamp-shell-opacity, 0.92);
  box-shadow:
    0 0 calc(12px + var(--lamp-glow-alpha, 0.4) * 28px) var(--lamp-glow-color),
    inset 0 1px 0 rgba(255, 255, 255, 0.28);
  animation:
    lamp-float var(--lamp-float-duration, 4.4s) ease-in-out infinite,
    lamp-pulse var(--lamp-pulse-duration, 4.8s) ease-in-out infinite;
}

.emotion-lamp-core {
  position: absolute;
  inset: auto 1rem 1.2rem 1rem;
  height: 2.3rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.25);
  filter: blur(3px);
  opacity: var(--lamp-core-opacity, 0.24);
}

.emotion-meta {
  display: flex;
  flex-direction: column;
  gap: 0.16rem;
}

.emotion-reason,
.emotion-keywords {
  color: #60788e;
  font-size: 0.86rem;
}
```

If `@keyframes lamp-float` and `@keyframes lamp-pulse` are not available in `admin.css`, copy the existing keyframes from `frontend/src/style.css`.

- [ ] **Step 8: Run component tests and build**

Run:

```powershell
cd frontend
npm run test -- src/components/EmotionLamp.test.ts src/components/AvatarDisplayControls.test.ts
npm run build
```

Expected: PASS.

- [ ] **Step 9: Commit reusable components**

Run:

```powershell
git add frontend/src/components/EmotionLamp.vue frontend/src/components/EmotionLamp.test.ts frontend/src/components/AvatarDisplayControls.vue frontend/src/components/AvatarDisplayControls.test.ts frontend/src/style.css frontend/src/admin.css
git commit -m "feat: add avatar display and emotion preview components"
```

---

### Task 5: Visitor Stage Resizing And Local Overrides

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`
- Modify: `frontend/src/App.chatLayout.test.ts`

- [ ] **Step 1: Write failing visitor layout test**

Add these assertions to `frontend/src/App.chatLayout.test.ts`:

```typescript
  test('visitor stage exposes display controls without moving the composer dock', () => {
    expect(appSource).toContain('<AvatarDisplayControls')
    expect(appSource).toContain('visitorDisplayControlsOpen')
    expect(appSource).toContain(':model-scale="avatarDisplayConfig.displayScale"')
    expect(appSource).toContain(':style="stageCardStyle"')
    expect(appSource).toContain('chat-panel-dock')
  })
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
cd frontend
npm run test -- src/App.chatLayout.test.ts
```

Expected: FAIL because the visitor page does not yet use `AvatarDisplayControls`.

- [ ] **Step 3: Import display controls and helpers in `App.vue`**

Add imports:

```typescript
import AvatarDisplayControls from './components/AvatarDisplayControls.vue'
import EmotionLamp from './components/EmotionLamp.vue'
import {
  AVATAR_DISPLAY_DEFAULTS,
  buildStageHeightStyle,
  clearAvatarDisplayOverride,
  loadAvatarDisplayOverride,
  mergeAvatarDisplayConfig,
  saveAvatarDisplayOverride,
  type AvatarDisplayConfig,
} from './lib/avatarDisplay'
```

- [ ] **Step 4: Add visitor display state in `App.vue`**

Add state near existing avatar refs:

```typescript
const visitorDisplayControlsOpen = ref(false)
const localAvatarDisplayOverride = ref<AvatarDisplayConfig | null>(null)

const activeAvatarDisplayDefaults = computed<AvatarDisplayConfig>(() =>
  mergeAvatarDisplayConfig(activeAvatarProfile.value ?? AVATAR_DISPLAY_DEFAULTS, null),
)

const avatarDisplayConfig = computed<AvatarDisplayConfig>(() =>
  mergeAvatarDisplayConfig(activeAvatarDisplayDefaults.value, localAvatarDisplayOverride.value),
)

const stageCardStyle = computed(() => buildStageHeightStyle(avatarDisplayConfig.value))
```

Add methods:

```typescript
function refreshAvatarDisplayOverride() {
  const profileId = activeAvatarProfile.value?.id
  if (!profileId || typeof window === 'undefined') {
    localAvatarDisplayOverride.value = null
    return
  }
  localAvatarDisplayOverride.value = loadAvatarDisplayOverride(window.localStorage, profileId)
}

function updateVisitorAvatarDisplay(value: AvatarDisplayConfig) {
  const profileId = activeAvatarProfile.value?.id
  localAvatarDisplayOverride.value = value
  if (profileId && typeof window !== 'undefined') {
    saveAvatarDisplayOverride(window.localStorage, profileId, value)
  }
}

function resetVisitorAvatarDisplay() {
  const profileId = activeAvatarProfile.value?.id
  if (profileId && typeof window !== 'undefined') {
    clearAvatarDisplayOverride(window.localStorage, profileId)
  }
  localAvatarDisplayOverride.value = null
}
```

Add watcher:

```typescript
watch(
  () => activeAvatarProfile.value?.id,
  () => refreshAvatarDisplayOverride(),
  { immediate: true },
)
```

- [ ] **Step 5: Pass display props to Live2DStage**

Replace the visitor `Live2DStage` usage:

```vue
<Live2DStage
  ref="live2dRef"
  :model-path="currentModelPath"
  :model-scale="avatarDisplayConfig.displayScale"
  :model-offset-x="avatarDisplayConfig.displayOffsetX"
  :model-offset-y="avatarDisplayConfig.displayOffsetY"
/>
```

Set style on the stage card:

```vue
<div class="stage-card" :style="stageCardStyle">
```

- [ ] **Step 6: Add visitor display controls UI**

Inside `.stage-card`, after `Live2DStage`, add:

```vue
<button
  class="stage-display-toggle"
  type="button"
  :aria-expanded="visitorDisplayControlsOpen"
  @click="visitorDisplayControlsOpen = !visitorDisplayControlsOpen"
>
  显示调节
</button>
<div v-if="visitorDisplayControlsOpen" class="stage-display-popover">
  <AvatarDisplayControls
    compact
    :model-value="avatarDisplayConfig"
    @update:model-value="updateVisitorAvatarDisplay"
    @reset="resetVisitorAvatarDisplay"
  />
</div>
```

Replace the inline visitor lamp markup with:

```vue
<EmotionLamp
  :emotion-telemetry="emotionTelemetry"
  :stage-label="emotionStageLabel"
  :confidence-label="emotionConfidenceLabel"
/>
```

- [ ] **Step 7: Add visitor CSS**

In `frontend/src/style.css`, change `.stage-card` height:

```css
.stage-card {
  position: relative;
  height: var(--avatar-stage-height, clamp(20rem, 45vh, 26rem));
  min-height: 20rem;
  resize: vertical;
  overflow: auto;
}
```

Add styles:

```css
.stage-display-toggle {
  position: absolute;
  z-index: 5;
  top: 0.9rem;
  right: 0.9rem;
  border: 0;
  border-radius: 999px;
  padding: 0.48rem 0.78rem;
  background: rgba(8, 20, 31, 0.68);
  color: #fff8eb;
  backdrop-filter: blur(12px);
}

.stage-display-popover {
  position: absolute;
  z-index: 6;
  top: 3.25rem;
  right: 0.9rem;
  width: min(20rem, calc(100% - 1.8rem));
  padding: 0.9rem;
  border-radius: 18px;
  background: rgba(255, 251, 244, 0.94);
  box-shadow: 0 20px 40px rgba(8, 20, 31, 0.22);
}

.avatar-display-controls {
  display: grid;
  gap: 0.72rem;
}

.avatar-display-controls label {
  display: grid;
  grid-template-columns: 5rem 1fr 3.8rem;
  gap: 0.6rem;
  align-items: center;
  color: var(--ink-soft);
  font-size: 0.84rem;
}

.avatar-display-controls input[type="range"] {
  width: 100%;
}

.avatar-display-reset {
  justify-self: end;
  border: 0;
  border-radius: 999px;
  padding: 0.5rem 0.78rem;
  background: rgba(25, 74, 103, 0.1);
  color: var(--ink-strong);
}
```

- [ ] **Step 8: Run visitor tests and build**

Run:

```powershell
cd frontend
npm run test -- src/App.chatLayout.test.ts src/lib/avatarDisplay.test.ts
npm run build
```

Expected: PASS.

- [ ] **Step 9: Commit visitor display controls**

Run:

```powershell
git add frontend/src/App.vue frontend/src/style.css frontend/src/App.chatLayout.test.ts
git commit -m "feat: add visitor avatar display controls"
```

---

### Task 6: Admin Display Fields And Emotion Preview Panel

**Files:**
- Create: `frontend/src/components/AdminEmotionPreviewPanel.vue`
- Create: `frontend/src/AdminApp.avatarExperience.test.ts`
- Modify: `frontend/src/AdminApp.vue`
- Modify: `frontend/src/admin.css`

- [ ] **Step 1: Write failing admin source test**

Create `frontend/src/AdminApp.avatarExperience.test.ts`:

```typescript
import { readFileSync } from 'node:fs'

import { describe, expect, test } from 'vitest'

const adminSource = readFileSync(new URL('./AdminApp.vue', import.meta.url), 'utf-8')
const panelSource = readFileSync(new URL('./components/AdminEmotionPreviewPanel.vue', import.meta.url), 'utf-8')

describe('admin avatar experience controls', () => {
  test('admin avatar page exposes display fields and emotion preview panel', () => {
    expect(adminSource).toContain('<AvatarDisplayControls')
    expect(adminSource).toContain('<AdminEmotionPreviewPanel')
    expect(adminSource).toContain('adminPreviewPresentation')
    expect(adminSource).toContain(':model-scale="avatarForm.displayScale"')
  })

  test('emotion preview panel supports five emotion presets and lava lamp preview', () => {
    expect(panelSource).toContain('neutral')
    expect(panelSource).toContain('happy')
    expect(panelSource).toContain('thinking')
    expect(panelSource).toContain('excited')
    expect(panelSource).toContain('sad')
    expect(panelSource).toContain('<EmotionLamp')
    expect(panelSource).toContain('EMOTION_PRESETS')
  })
})
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
cd frontend
npm run test -- src/AdminApp.avatarExperience.test.ts
```

Expected: FAIL because `AdminEmotionPreviewPanel.vue` does not exist and `AdminApp.vue` is not wired.

- [ ] **Step 3: Create admin emotion preview panel**

Create `frontend/src/components/AdminEmotionPreviewPanel.vue`:

```vue
<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import EmotionLamp from './EmotionLamp.vue'
import { EMOTION_EXPRESSION_MAP, EMOTION_PRESETS, EMOTION_VISUALS } from '../lib/lipsync'
import type { AvatarPresentation } from '../lib/avatarPresentation'
import type { EmotionStage, EmotionTelemetry, EmotionValue } from '../types/chat'

const emit = defineEmits<{
  preview: [presentation: AvatarPresentation]
}>()

const emotionOptions: Array<{ value: EmotionValue; label: string; hint: string }> = [
  { value: 'neutral', label: '中性', hint: '默认信息讲解状态。' },
  { value: 'happy', label: '愉快', hint: '适合欢迎、推荐和正向反馈。' },
  { value: 'thinking', label: '思考', hint: '适合等待、检索和文化讲解。' },
  { value: 'excited', label: '兴奋', hint: '适合路线亮点和强推荐。' },
  { value: 'sad', label: '克制', hint: '适合无法确认、遗憾或提醒。' },
]

const selectedEmotion = ref<EmotionValue>('neutral')
const selectedStage = ref<EmotionStage>('final')

const telemetry = computed<EmotionTelemetry>(() => ({
  value: selectedEmotion.value,
  stage: selectedStage.value,
  confidence: selectedStage.value === 'final' ? 0.92 : 0.68,
  keywords: [emotionOptions.find((item) => item.value === selectedEmotion.value)?.label ?? selectedEmotion.value],
  reason: emotionOptions.find((item) => item.value === selectedEmotion.value)?.hint ?? '当前情绪用于后台预览。',
  source: 'heuristic',
}))

const stageLabel = computed(() => selectedStage.value === 'final' ? '最终表情' : '预览表情')
const confidenceLabel = computed(() => `${Math.round(telemetry.value.confidence * 100)}%`)
const visual = computed(() => EMOTION_VISUALS[selectedEmotion.value] ?? EMOTION_VISUALS.neutral)
const expressionName = computed(() => EMOTION_EXPRESSION_MAP[selectedEmotion.value] ?? '参数叠加')
const parameterEntries = computed(() =>
  Object.entries(EMOTION_PRESETS[selectedEmotion.value] ?? {}).slice(0, 8),
)

watch(
  [selectedEmotion, selectedStage],
  () => {
    emit('preview', {
      phase: selectedEmotion.value === 'thinking' ? 'thinking' : 'idle',
      emotion: selectedEmotion.value,
      emotionStage: selectedStage.value,
      allowIdleMotion: false,
      motionIntensity: selectedEmotion.value === 'excited' ? 'light' : 'none',
      lipSyncActive: false,
      activeReplyId: null,
    })
  },
  { immediate: true },
)
</script>

<template>
  <div class="admin-emotion-preview">
    <div class="admin-emotion-preview-controls">
      <button
        v-for="item in emotionOptions"
        :key="item.value"
        class="admin-emotion-chip"
        type="button"
        :data-active="selectedEmotion === item.value"
        @click="selectedEmotion = item.value"
      >
        <strong>{{ item.label }}</strong>
        <span>{{ item.value }}</span>
      </button>
    </div>

    <div class="admin-chip-row">
      <button
        class="admin-secondary-button"
        type="button"
        :data-active="selectedStage === 'preview'"
        @click="selectedStage = 'preview'"
      >
        preview
      </button>
      <button
        class="admin-secondary-button"
        type="button"
        :data-active="selectedStage === 'final'"
        @click="selectedStage = 'final'"
      >
        final
      </button>
    </div>

    <EmotionLamp
      :emotion-telemetry="telemetry"
      :stage-label="stageLabel"
      :confidence-label="confidenceLabel"
    />

    <div class="admin-emotion-preview-meta">
      <div>
        <span>视觉主题</span>
        <strong>{{ visual.label }}</strong>
      </div>
      <div>
        <span>表达式映射</span>
        <strong>{{ expressionName }}</strong>
      </div>
    </div>

    <div class="admin-emotion-param-list">
      <article v-for="[name, value] in parameterEntries" :key="name">
        <span>{{ name }}</span>
        <strong>{{ Number(value).toFixed(2) }}</strong>
      </article>
    </div>
  </div>
</template>
```

- [ ] **Step 4: Add admin imports and form fields**

In `frontend/src/AdminApp.vue`, add imports:

```typescript
import AdminEmotionPreviewPanel from './components/AdminEmotionPreviewPanel.vue'
import AvatarDisplayControls from './components/AvatarDisplayControls.vue'
import EmotionLamp from './components/EmotionLamp.vue'
import {
  AVATAR_DISPLAY_DEFAULTS,
  clampAvatarDisplayConfig,
  type AvatarDisplayConfig,
} from './lib/avatarDisplay'
import type { AvatarPresentation } from './lib/avatarPresentation'
```

Extend `avatarForm` reactive initialization:

```typescript
  displayScale: AVATAR_DISPLAY_DEFAULTS.displayScale,
  displayOffsetX: AVATAR_DISPLAY_DEFAULTS.displayOffsetX,
  displayOffsetY: AVATAR_DISPLAY_DEFAULTS.displayOffsetY,
  stageHeight: AVATAR_DISPLAY_DEFAULTS.stageHeight,
```

Add state:

```typescript
const adminPreviewPresentation = ref<AvatarPresentation>({
  phase: 'idle',
  emotion: 'neutral',
  emotionStage: 'final',
  allowIdleMotion: true,
  motionIntensity: 'normal',
  lipSyncActive: false,
  activeReplyId: null,
})

function updateAdminAvatarDisplay(value: AvatarDisplayConfig) {
  const next = clampAvatarDisplayConfig(value)
  avatarForm.displayScale = next.displayScale
  avatarForm.displayOffsetX = next.displayOffsetX
  avatarForm.displayOffsetY = next.displayOffsetY
  avatarForm.stageHeight = next.stageHeight
}

function resetAdminAvatarDisplay() {
  updateAdminAvatarDisplay(AVATAR_DISPLAY_DEFAULTS)
}
```

- [ ] **Step 5: Map admin config into form and payload**

In `applyAvatarConfig(config)`, add:

```typescript
  avatarForm.displayScale = config.displayScale
  avatarForm.displayOffsetX = config.displayOffsetX
  avatarForm.displayOffsetY = config.displayOffsetY
  avatarForm.stageHeight = config.stageHeight
```

In `buildAvatarCreatePayload()` and `saveAvatarSettings()` payloads, add:

```typescript
    displayScale: Number(avatarForm.displayScale.toFixed(2)),
    displayOffsetX: Number(avatarForm.displayOffsetX.toFixed(2)),
    displayOffsetY: Number(avatarForm.displayOffsetY.toFixed(2)),
    stageHeight: Math.round(avatarForm.stageHeight),
```

- [ ] **Step 6: Wire admin Live2D preview and panels**

Change admin preview `Live2DStage`:

```vue
<Live2DStage
  :model-path="previewModelPath"
  :model-scale="avatarForm.displayScale"
  :model-offset-x="avatarForm.displayOffsetX"
  :model-offset-y="avatarForm.displayOffsetY"
  ref="adminLive2dRef"
/>
```

If `Live2DStage` does not accept `presentation` as a prop, keep the existing exposed method pattern and add a watcher:

```typescript
const adminLive2dRef = ref<InstanceType<typeof Live2DStage> | null>(null)

watch([adminPreviewPresentation, adminLive2dRef], ([presentation, live2d]) => {
  live2d?.setAvatarPresentation(presentation)
})
```

Add a display section inside the avatar form before Prompt:

```vue
<section class="admin-form-section">
  <div class="admin-panel-header">
    <div>
      <p class="admin-section-tag">展示参数</p>
      <h3>舞台尺寸 / 模型站位</h3>
    </div>
  </div>
  <AvatarDisplayControls
    :model-value="{
      displayScale: avatarForm.displayScale,
      displayOffsetX: avatarForm.displayOffsetX,
      displayOffsetY: avatarForm.displayOffsetY,
      stageHeight: avatarForm.stageHeight,
    }"
    @update:model-value="updateAdminAvatarDisplay"
    @reset="resetAdminAvatarDisplay"
  />
</section>
```

Add an emotion preview panel below the preview stage or beside the form:

```vue
<section class="admin-panel admin-panel-wide">
  <div class="admin-panel-header">
    <div>
      <p class="admin-section-tag">情绪与表情</p>
      <h3>表情映射调试</h3>
    </div>
  </div>
  <AdminEmotionPreviewPanel @preview="adminPreviewPresentation = $event" />
</section>
```

- [ ] **Step 7: Add admin CSS**

Add to `frontend/src/admin.css`:

```css
.admin-form-section {
  display: grid;
  gap: 1rem;
  padding: 1rem;
  border-radius: 18px;
  background: #f8fbfe;
  border: 1px solid rgba(71, 98, 124, 0.12);
}

.admin-emotion-preview {
  display: grid;
  gap: 1rem;
}

.admin-emotion-preview-controls {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(7rem, 1fr));
  gap: 0.75rem;
}

.admin-emotion-chip {
  display: grid;
  gap: 0.2rem;
  text-align: left;
  border: 1px solid rgba(71, 98, 124, 0.14);
  border-radius: 16px;
  padding: 0.8rem;
  background: #fff;
  color: #17324a;
}

.admin-emotion-chip[data-active="true"],
.admin-secondary-button[data-active="true"] {
  border-color: rgba(23, 97, 165, 0.42);
  background: #eaf4ff;
}

.admin-emotion-preview-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: 0.8rem;
}

.admin-emotion-param-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: 0.65rem;
}

.admin-emotion-param-list article {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.65rem 0.75rem;
  border-radius: 14px;
  background: #f8fbfe;
  border: 1px solid rgba(71, 98, 124, 0.12);
}
```

- [ ] **Step 8: Run admin tests and build**

Run:

```powershell
cd frontend
npm run test -- src/AdminApp.avatarExperience.test.ts src/components/EmotionLamp.test.ts src/components/AvatarDisplayControls.test.ts
npm run build
```

Expected: PASS.

- [ ] **Step 9: Commit admin avatar experience panel**

Run:

```powershell
git add frontend/src/AdminApp.vue frontend/src/AdminApp.avatarExperience.test.ts frontend/src/components/AdminEmotionPreviewPanel.vue frontend/src/admin.css
git commit -m "feat: add admin avatar emotion preview"
```

---

### Task 7: Roadmap, Full Verification, And Cleanup

**Files:**
- Modify: `docs/roadmap.md`

- [ ] **Step 1: Update roadmap**

In `docs/roadmap.md`, under Phase 4 experience optimization, mark or add:

```markdown
- [x] 数字人舞台自由缩放：游客端支持舞台高度调整、模型缩放和 X/Y 偏移，本机偏好通过 localStorage 保存；后台数字人档案保存默认展示参数。
- [x] 后台情绪与表情预览：数字人管理页支持 neutral/happy/thinking/excited/sad 五种情绪预览，并复用游客端情感熔岩灯。
```

- [ ] **Step 2: Run backend verification**

Run:

```powershell
cd backend
python -m unittest tests.test_avatar_config tests.test_sessions_api -v
python -m compileall app
```

Expected: both commands pass.

- [ ] **Step 3: Run frontend verification**

Run:

```powershell
cd frontend
npm run test -- src/lib/avatarDisplay.test.ts src/components/EmotionLamp.test.ts src/components/AvatarDisplayControls.test.ts src/App.chatLayout.test.ts src/AdminApp.avatarExperience.test.ts
npm run build
```

Expected: tests pass and build passes. Existing Vite chunk-size warning is acceptable if unchanged.

- [ ] **Step 4: Check git diff**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors. `git status --short` should show only intentional changes if previous tasks were committed; existing unrelated dirty files from earlier Phase 4 work may still appear and must not be reverted.

- [ ] **Step 5: Commit docs and final polish**

Run:

```powershell
git add docs/roadmap.md
git commit -m "docs: update roadmap for avatar experience controls"
```

---

## Self-Review

- Spec coverage: backend defaults, visitor local overrides, `Live2DStage` model transform props, admin emotion/expression preview, shared lava lamp, validation, rollback, and roadmap updates are covered by Tasks 1-7.
- Placeholder scan: no unresolved markers or vague test instructions remain.
- Type consistency: display fields consistently use camelCase in frontend (`displayScale`, `displayOffsetX`, `displayOffsetY`, `stageHeight`) and snake_case in backend/API (`display_scale`, `display_offset_x`, `display_offset_y`, `stage_height`).
- Risk note: current worktree already contains unrelated Phase 4 dashboard/report changes. Execution must stage only files listed in each task unless the user explicitly asks to include previous dirty work.
