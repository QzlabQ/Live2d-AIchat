import type { EmotionValue, PhonemeFrame } from '../types/chat'

export interface MouthPose {
  openY: number
  form: number
}

export interface EmotionVisualPreset {
  label: string
  color: string
  glow: string
}

const FALLBACK_POSE: MouthPose = { openY: 0.06, form: 0 }

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
    ParamAngleY: -2,
    ParamBodyAngleX: 1.2,
    ParamBrowLY: 0.35,
    ParamBrowRY: 0.35,
    ParamEyeLSmile: 1,
    ParamEyeRSmile: 1,
  },
  thinking: {
    ParamAngleX: -4,
    ParamAngleY: 1,
    ParamBrowLAngle: -0.35,
    ParamBrowRAngle: -0.15,
    ParamEyeBallX: -0.2,
    ParamEyeBallY: -0.08,
  },
  excited: {
    ParamAngleX: 3,
    ParamBodyAngleX: 3,
    ParamBrowLY: 0.45,
    ParamBrowRY: 0.45,
    ParamEyeLOpen: 1.2,
    ParamEyeROpen: 1.2,
  },
  sad: {
    ParamAngleY: 2,
    ParamBrowLY: -0.2,
    ParamBrowRY: -0.2,
    ParamEyeBallY: 0.2,
  },
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
