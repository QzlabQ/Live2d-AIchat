import { describe, expect, it } from 'vitest'

import {
  AVATAR_DISPLAY_DEFAULTS,
  buildAvatarDisplayStorageKey,
  buildStageHeightStyle,
  clampAvatarDisplayConfig,
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

  it('saves and loads avatar-specific display overrides with defaults filled in', () => {
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
    expect(loadAvatarDisplayOverride(storageLike, 7)).toEqual({
      ...AVATAR_DISPLAY_DEFAULTS,
      displayScale: 1.25,
      stageHeight: 520,
    })
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
})
