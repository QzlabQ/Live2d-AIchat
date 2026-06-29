import type { EmotionValue, PhonemeFrame } from '../types/chat'

export interface MouthPose {
  openY: number
  form: number
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
    ParamEyeLOpen: 1,
    ParamEyeROpen: 1,
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
    ParamBrowLAngle: -0.35,
    ParamBrowRAngle: -0.15,
    ParamEyeBallX: -0.2,
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

export function phonemeToMouth(ph: string): MouthPose {
  if (PHONEME_TO_MOUTH[ph]) {
    return PHONEME_TO_MOUTH[ph]
  }

  const short = ph.slice(0, 1)
  return PHONEME_TO_MOUTH[short] ?? FALLBACK_POSE
}

export function currentPhoneme(frames: PhonemeFrame[], elapsedSeconds: number): PhonemeFrame | null {
  return frames.find((frame) => elapsedSeconds >= frame.start && elapsedSeconds < frame.end) ?? null
}

export function finalFrameEnd(frames: PhonemeFrame[]): number {
  return frames.at(-1)?.end ?? 0
}
