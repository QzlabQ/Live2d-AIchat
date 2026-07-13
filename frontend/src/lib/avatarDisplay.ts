export interface AvatarDisplayConfig {
  displayScale: number
  displayOffsetX: number
  displayOffsetY: number
  stageHeight: number
}

export type AvatarDisplayConfigInput = Partial<AvatarDisplayConfig> | null | undefined

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

function hasOwnValue(input: object, key: keyof AvatarDisplayConfig) {
  return Object.prototype.hasOwnProperty.call(input, key)
}

function getFiniteNumberValue(
  input: Partial<Record<keyof AvatarDisplayConfig, unknown>>,
  key: keyof AvatarDisplayConfig,
) {
  const value = input[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
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

export function sanitizeAvatarDisplayOverride(
  input: AvatarDisplayConfigInput,
): Partial<AvatarDisplayConfig> {
  if (!input || typeof input !== 'object') {
    return {}
  }

  const sanitized: Partial<AvatarDisplayConfig> = {}
  const overrideInput = input as Partial<Record<keyof AvatarDisplayConfig, unknown>>

  if (hasOwnValue(input, 'displayScale')) {
    const value = getFiniteNumberValue(overrideInput, 'displayScale')
    if (value !== null) {
      sanitized.displayScale = clamp(
        value,
        AVATAR_DISPLAY_LIMITS.displayScale.min,
        AVATAR_DISPLAY_LIMITS.displayScale.max,
        AVATAR_DISPLAY_DEFAULTS.displayScale,
      )
    }
  }
  if (hasOwnValue(input, 'displayOffsetX')) {
    const value = getFiniteNumberValue(overrideInput, 'displayOffsetX')
    if (value !== null) {
      sanitized.displayOffsetX = clamp(
        value,
        AVATAR_DISPLAY_LIMITS.displayOffsetX.min,
        AVATAR_DISPLAY_LIMITS.displayOffsetX.max,
        AVATAR_DISPLAY_DEFAULTS.displayOffsetX,
      )
    }
  }
  if (hasOwnValue(input, 'displayOffsetY')) {
    const value = getFiniteNumberValue(overrideInput, 'displayOffsetY')
    if (value !== null) {
      sanitized.displayOffsetY = clamp(
        value,
        AVATAR_DISPLAY_LIMITS.displayOffsetY.min,
        AVATAR_DISPLAY_LIMITS.displayOffsetY.max,
        AVATAR_DISPLAY_DEFAULTS.displayOffsetY,
      )
    }
  }
  if (hasOwnValue(input, 'stageHeight')) {
    const value = getFiniteNumberValue(overrideInput, 'stageHeight')
    if (value !== null) {
      sanitized.stageHeight = Math.round(
        clamp(
          value,
          AVATAR_DISPLAY_LIMITS.stageHeight.min,
          AVATAR_DISPLAY_LIMITS.stageHeight.max,
          AVATAR_DISPLAY_DEFAULTS.stageHeight,
        ),
      )
    }
  }

  return sanitized
}

export function buildAvatarDisplayOverridePatch(
  defaults: AvatarDisplayConfigInput,
  next: AvatarDisplayConfigInput,
): Partial<AvatarDisplayConfig> {
  const normalizedDefaults = clampAvatarDisplayConfig(defaults)
  const normalizedNext = clampAvatarDisplayConfig(next)
  const patch: Partial<AvatarDisplayConfig> = {}

  if (normalizedNext.displayScale !== normalizedDefaults.displayScale) {
    patch.displayScale = normalizedNext.displayScale
  }
  if (normalizedNext.displayOffsetX !== normalizedDefaults.displayOffsetX) {
    patch.displayOffsetX = normalizedNext.displayOffsetX
  }
  if (normalizedNext.displayOffsetY !== normalizedDefaults.displayOffsetY) {
    patch.displayOffsetY = normalizedNext.displayOffsetY
  }
  if (normalizedNext.stageHeight !== normalizedDefaults.stageHeight) {
    patch.stageHeight = normalizedNext.stageHeight
  }

  return patch
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

export function computeLive2DPlacement(
  stage: StageSize,
  bounds: ModelBounds,
  config: AvatarDisplayConfigInput,
): Live2DPlacement {
  const displayConfig = clampAvatarDisplayConfig(config)
  const stageWidth = Math.max(stage.width || 1, 1)
  const stageHeight = Math.max(stage.height || 1, 1)
  const modelWidth = Math.max(bounds.width || 1, 1)
  const modelHeight = Math.max(bounds.height || 1, 1)
  const baseScale = Math.min(stageWidth / modelWidth, stageHeight / modelHeight) * 0.85

  return {
    scale: baseScale * displayConfig.displayScale,
    x: stageWidth * (0.5 + displayConfig.displayOffsetX),
    y: stageHeight * (0.88 + displayConfig.displayOffsetY),
  }
}

export function buildAvatarDisplayStorageKey(avatarProfileId: number | string) {
  return `ai-chat-live2d.avatar-display.${avatarProfileId}`
}

export function loadAvatarDisplayOverride(
  storage: Storage,
  avatarProfileId: number | string | null | undefined,
): Partial<AvatarDisplayConfig> | null {
  if (avatarProfileId === null || avatarProfileId === undefined || avatarProfileId === '') {
    return null
  }

  const rawValue = storage.getItem(buildAvatarDisplayStorageKey(avatarProfileId))
  if (!rawValue) {
    return null
  }

  try {
    return sanitizeAvatarDisplayOverride(JSON.parse(rawValue) as AvatarDisplayConfigInput)
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
