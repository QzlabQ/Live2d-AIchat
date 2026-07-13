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
  if (value === undefined || !Number.isFinite(value)) {
    return fallback
  }

  return Math.min(Math.max(value, min), max)
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
    ...(backendConfig ?? {}),
    ...(localOverride ?? {}),
  })
}

export function buildAvatarDisplayStorageKey(avatarProfileId: number | string) {
  return `ai-chat-live2d.avatar-display.${avatarProfileId}`
}

export function loadAvatarDisplayOverride(
  storage: Storage,
  avatarProfileId: number | string | null | undefined,
): AvatarDisplayConfig | null {
  if (avatarProfileId === null || avatarProfileId === undefined || avatarProfileId === '') {
    return null
  }

  const rawValue = storage.getItem(buildAvatarDisplayStorageKey(avatarProfileId))
  if (!rawValue) {
    return null
  }

  try {
    return clampAvatarDisplayConfig(JSON.parse(rawValue) as AvatarDisplayConfigInput)
  } catch {
    return null
  }
}

export function saveAvatarDisplayOverride(
  storage: Storage,
  avatarProfileId: number | string,
  config: AvatarDisplayConfigInput,
) {
  storage.setItem(buildAvatarDisplayStorageKey(avatarProfileId), JSON.stringify(config ?? {}))
}

export function clearAvatarDisplayOverride(storage: Storage, avatarProfileId: number | string) {
  storage.removeItem(buildAvatarDisplayStorageKey(avatarProfileId))
}

export function buildStageHeightStyle(config: AvatarDisplayConfigInput) {
  return {
    '--avatar-stage-height': `${clampAvatarDisplayConfig(config).stageHeight}px`,
  }
}
