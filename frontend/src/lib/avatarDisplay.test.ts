import { describe, expect, it } from 'vitest'

import {
  buildAvatarDisplayStorageKey,
  buildStageHeightStyle,
  clampAvatarDisplayConfig,
  computeLive2DPlacement,
  loadAvatarDisplayOverride,
  mergeAvatarDisplayConfig,
  saveAvatarDisplayOverride,
} from './avatarDisplay'

function createMemoryStorage(initialValues: Record<string, string> = {}) {
  const storage = new Map<string, string>(Object.entries(initialValues))

  return {
    get length() {
      return storage.size
    },
    clear: () => storage.clear(),
    getItem: (key) => storage.get(key) ?? null,
    key: (index) => Array.from(storage.keys())[index] ?? null,
    removeItem: (key) => storage.delete(key),
    setItem: (key, value) => storage.set(key, value),
  } satisfies Storage
}

describe('avatarDisplay', () => {
  it('clamps avatar display config to safe limits', () => {
    expect(
      clampAvatarDisplayConfig({
        displayScale: 3,
        displayOffsetX: -2,
        displayOffsetY: 2,
        stageHeight: 1200,
      }),
    ).toEqual({
      displayScale: 1.8,
      displayOffsetX: -0.5,
      displayOffsetY: 0.5,
      stageHeight: 760,
    })
  })

  it('merges backend defaults with local overrides taking precedence', () => {
    expect(
      mergeAvatarDisplayConfig(
        {
          displayScale: 1.1,
          displayOffsetX: 0.2,
          displayOffsetY: -0.2,
          stageHeight: 500,
        },
        {
          displayScale: 1.4,
          stageHeight: 620,
        },
      ),
    ).toEqual({
      displayScale: 1.4,
      displayOffsetX: 0.2,
      displayOffsetY: -0.2,
      stageHeight: 620,
    })
  })

  it('saves and loads avatar-specific display overrides as partial values', () => {
    const storageLike = createMemoryStorage()

    const key = buildAvatarDisplayStorageKey(7)

    expect(key).toBe('ai-chat-live2d.avatar-display.7')

    saveAvatarDisplayOverride(storageLike, 7, {
      displayScale: 1.25,
      stageHeight: 520,
    })

    expect(storageLike.getItem(key)).toBe(
      JSON.stringify({
        displayScale: 1.25,
        stageHeight: 520,
      }),
    )
    const loaded = loadAvatarDisplayOverride(storageLike, 7)

    expect(loaded).toEqual({
      displayScale: 1.25,
      stageHeight: 520,
    })
    expect(mergeAvatarDisplayConfig(null, loaded)).toEqual({
      displayScale: 1.25,
      displayOffsetX: 0,
      displayOffsetY: 0,
      stageHeight: 520,
    })
  })

  it('preserves backend display fields when local storage only overrides scale', () => {
    const storage = createMemoryStorage({
      [buildAvatarDisplayStorageKey(7)]: JSON.stringify({ displayScale: 1.25 }),
    })
    const backendConfig = {
      displayScale: 1.1,
      displayOffsetX: 0.1,
      displayOffsetY: 0.2,
      stageHeight: 560,
    }
    const loaded = loadAvatarDisplayOverride(storage, 7)

    expect(loaded).toEqual({ displayScale: 1.25 })
    expect(mergeAvatarDisplayConfig(backendConfig, loaded)).toEqual({
      displayScale: 1.25,
      displayOffsetX: 0.1,
      displayOffsetY: 0.2,
      stageHeight: 560,
    })
  })

  it('drops invalid parseable local override fields instead of defaulting them', () => {
    const storage = createMemoryStorage({
      [buildAvatarDisplayStorageKey(7)]: JSON.stringify({
        displayScale: null,
        displayOffsetX: 'bad',
        stageHeight: '520',
      }),
    })
    const backendConfig = {
      displayScale: 1.1,
      displayOffsetX: 0.1,
      displayOffsetY: 0.2,
      stageHeight: 560,
    }
    const loaded = loadAvatarDisplayOverride(storage, 7)

    expect(loaded).toEqual({})
    expect(mergeAvatarDisplayConfig(backendConfig, loaded)).toEqual(backendConfig)
  })

  it('ignores corrupt JSON display overrides', () => {
    const storage = createMemoryStorage({
      [buildAvatarDisplayStorageKey(7)]: '{',
    })

    expect(loadAvatarDisplayOverride(storage, 7)).toBeNull()
  })

  it('builds the stage height CSS variable style', () => {
    expect(buildStageHeightStyle({ stageHeight: 512 })).toEqual({
      '--avatar-stage-height': '512px',
    })
  })

  it('computes Live2D placement from stage, model bounds, and display controls', () => {
    const placement = computeLive2DPlacement(
      { width: 800, height: 500 },
      { width: 400, height: 1000 },
      {
        displayScale: 1.2,
        displayOffsetX: 0.1,
        displayOffsetY: -0.2,
        stageHeight: 500,
      },
    )

    expect(placement.scale).toBeCloseTo(0.51)
    expect(placement.x).toBeCloseTo(480)
    expect(placement.y).toBeCloseTo(340)
  })
})
