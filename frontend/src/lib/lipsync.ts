import type { EmotionStage, EmotionValue, PhonemeFrame } from '../types/chat'

export interface MouthPose {
  openY: number
  form: number
}

export interface EmotionVisualPreset {
  label: string
  color: string
  glow: string
}

export interface Live2DExpressionParameter {
  Id: string
  Value: number
  Blend?: 'Add' | 'Multiply' | 'Overwrite' | string
}

export interface Live2DExpressionFile {
  Parameters?: Live2DExpressionParameter[]
}

export interface Live2DExpressionManifestEntry {
  Name: string
  File: string
}

const FALLBACK_POSE: MouthPose = { openY: 0.06, form: 0 }
const PREVIEW_EMOTION_STRENGTH = 0.72
const MOUTH_PARAMETER_IDS = new Set(['ParamMouthOpenY', 'PARAM_MOUTH_OPEN_Y', 'ParamMouthForm', 'PARAM_MOUTH_FORM'])

const PHONEME_TO_MOUTH: Record<string, MouthPose> = {
  a: { openY: 0.92, form: 0.04 },
  i: { openY: 0.42, form: 0.82 },
  u: { openY: 0.62, form: -0.72 },
  e: { openY: 0.52, form: 0.25 },
  o: { openY: 0.72, form: -0.45 },
  N: FALLBACK_POSE,
}

export const EMOTION_PRESETS: Record<EmotionValue, Record<string, number>> = {
  neutral: {
    ParamAngleX: 0,
    ParamAngleY: 0,
    ParamBodyAngleX: 0,
    ParamBrowLY: 0,
    ParamBrowRY: 0,
    ParamBrowLAngle: 0,
    ParamBrowRAngle: 0,
    ParamEyeBallX: 0,
    ParamEyeBallY: 0,
    ParamEyeLOpen: 1,
    ParamEyeROpen: 1,
    ParamEyeLSmile: 0,
    ParamEyeRSmile: 0,
  },
  happy: {
    ParamAngleY: -1.4,
    ParamBodyAngleX: 1,
    ParamAngleX: 1.2,
    ParamBrowLY: 0.22,
    ParamBrowRY: 0.22,
  },
  thinking: {
    ParamAngleX: -3.6,
    ParamAngleY: 0.8,
    ParamBodyAngleX: -0.6,
    ParamBrowLAngle: -0.35,
    ParamBrowRAngle: -0.15,
    ParamEyeBallX: -0.18,
    ParamEyeBallY: -0.05,
  },
  excited: {
    ParamAngleX: 2.6,
    ParamAngleY: -0.8,
    ParamBodyAngleX: 2.8,
    ParamBrowLY: 0.35,
    ParamBrowRY: 0.35,
  },
  sad: {
    ParamAngleY: 1.6,
    ParamBodyAngleX: -0.8,
    ParamBrowLY: -0.12,
    ParamBrowRY: -0.12,
    ParamEyeBallY: 0.2,
  },
}

export const EMOTION_EXPRESSION_MAP: Record<EmotionValue, string | null> = {
  neutral: null,
  happy: 'f04',
  thinking: 'f07',
  excited: 'f05',
  sad: 'f03',
}

export const EMOTION_VISUALS: Record<EmotionValue, EmotionVisualPreset> = {
  neutral: {
    label: '中性',
    color: 'linear-gradient(135deg, #7a8ca4 0%, #c0cad8 100%)',
    glow: 'rgba(176, 194, 215, 0.38)',
  },
  happy: {
    label: '愉快',
    color: 'linear-gradient(135deg, #ffb75e 0%, #ffdd78 100%)',
    glow: 'rgba(255, 208, 111, 0.48)',
  },
  thinking: {
    label: '思考',
    color: 'linear-gradient(135deg, #59a0ff 0%, #8ed7ff 100%)',
    glow: 'rgba(111, 185, 255, 0.44)',
  },
  excited: {
    label: '兴奋',
    color: 'linear-gradient(135deg, #ff6b6b 0%, #ff9f68 100%)',
    glow: 'rgba(255, 127, 103, 0.5)',
  },
  sad: {
    label: '克制',
    color: 'linear-gradient(135deg, #677a9c 0%, #8f9bb6 100%)',
    glow: 'rgba(123, 144, 178, 0.42)',
  },
}

export function resolveModelAssetUrl(modelPath: string, assetPath: string): string {
  return new URL(assetPath, new URL(modelPath, window.location.origin)).toString()
}

export function buildExpressionTarget(parameters: Live2DExpressionParameter[] = []): Record<string, number> {
  const target: Record<string, number> = {}

  for (const parameter of parameters) {
    const id = parameter.Id
    if (!id || MOUTH_PARAMETER_IDS.has(id)) {
      continue
    }

    const baseValue = EMOTION_PRESETS.neutral[id] ?? (parameter.Blend === 'Multiply' ? 1 : 0)
    if (parameter.Blend === 'Multiply') {
      target[id] = baseValue * parameter.Value
      continue
    }

    if (parameter.Blend === 'Overwrite') {
      target[id] = parameter.Value
      continue
    }

    target[id] = baseValue + parameter.Value
  }

  return target
}

export function buildEmotionTarget(
  emotion: EmotionValue,
  stage: EmotionStage,
  expressionTargets: Record<string, Record<string, number>>,
): Record<string, number> {
  const neutral = EMOTION_PRESETS.neutral
  const expressionName = EMOTION_EXPRESSION_MAP[emotion]
  const expression = expressionName ? expressionTargets[expressionName] ?? {} : {}
  const overlay = EMOTION_PRESETS[emotion] ?? neutral
  const merged = {
    ...neutral,
    ...expression,
    ...overlay,
  }

  if (stage === 'final') {
    return merged
  }

  const scaled: Record<string, number> = {}
  for (const [id, value] of Object.entries(merged)) {
    const base = neutral[id] ?? 0
    scaled[id] = base + (value - base) * PREVIEW_EMOTION_STRENGTH
  }
  return scaled
}

export function phonemeToMouth(ph: string): MouthPose {
  if (PHONEME_TO_MOUTH[ph]) {
    return PHONEME_TO_MOUTH[ph]
  }

  const short = ph.slice(0, 1)
  return PHONEME_TO_MOUTH[short] ?? FALLBACK_POSE
}

export function mouthPoseFromFrame(frame: PhonemeFrame | null | undefined): MouthPose {
  if (!frame) {
    return FALLBACK_POSE
  }

  if (typeof frame.openY === 'number' && typeof frame.form === 'number') {
    return {
      openY: frame.openY,
      form: frame.form,
    }
  }

  return phonemeToMouth(frame.ph)
}

export function currentPhoneme(frames: PhonemeFrame[], elapsedSeconds: number): PhonemeFrame | null {
  return frames.find((frame) => elapsedSeconds >= frame.start && elapsedSeconds < frame.end) ?? null
}

export function finalFrameEnd(frames: PhonemeFrame[]): number {
  return frames.at(-1)?.end ?? 0
}
