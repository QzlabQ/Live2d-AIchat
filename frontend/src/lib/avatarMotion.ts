import type { AvatarPresentation } from './avatarPresentation'

export interface AvatarMotionProfile {
  breathSpeed: number
  angleXOffset: number
  angleXAmplitude: number
  angleXSpeed: number
  angleYOffset: number
  angleYAmplitude: number
  angleYSpeed: number
  bodyXOffset: number
  bodyXAmplitude: number
  bodyXSpeed: number
  eyeXOffset: number
  eyeXAmplitude: number
  eyeXSpeed: number
  eyeYOffset: number
  eyeYAmplitude: number
  eyeYSpeed: number
  mouthIdleAmplitude: number
  mouthIdleSpeed: number
}

const NEUTRAL_PROFILE: AvatarMotionProfile = {
  breathSpeed: 1.15,
  angleXOffset: 0,
  angleXAmplitude: 0.14,
  angleXSpeed: 0.72,
  angleYOffset: 0,
  angleYAmplitude: 0.08,
  angleYSpeed: 0.64,
  bodyXOffset: 0,
  bodyXAmplitude: 0.12,
  bodyXSpeed: 0.56,
  eyeXOffset: 0,
  eyeXAmplitude: 0.02,
  eyeXSpeed: 0.52,
  eyeYOffset: 0,
  eyeYAmplitude: 0.016,
  eyeYSpeed: 0.48,
  mouthIdleAmplitude: 0.01,
  mouthIdleSpeed: 2.3,
}

export function pickAvailableMotion(
  availableGroups: Iterable<string>,
  candidates: readonly string[],
): string | null {
  const available = new Set(availableGroups)
  for (const candidate of candidates) {
    if (available.has(candidate)) {
      return candidate
    }
  }
  return null
}

export function resolveEmotionMotionCandidates(
  presentation: AvatarPresentation,
): readonly string[] {
  if (presentation.phase === 'thinking') {
    return ['FlickDown', 'Flick']
  }

  if (presentation.phase === 'speaking') {
    switch (presentation.emotion) {
      case 'excited':
        return ['Tap@Body', 'FlickUp', 'Tap', 'Flick']
      case 'happy':
        return ['Flick', 'Tap@Body', 'Tap']
      case 'thinking':
        return ['FlickDown', 'Flick']
      case 'sad':
        return ['FlickDown', 'Flick@Body']
      case 'neutral':
      default:
        return ['Flick']
    }
  }

  return []
}

export function shouldTriggerEmotionMotion(
  previous: AvatarPresentation | null,
  next: AvatarPresentation,
): boolean {
  if (next.phase === 'idle' || next.phase === 'cooldown') {
    return false
  }

  if (!previous) {
    return true
  }

  if (next.phase !== previous.phase) {
    return true
  }

  return next.phase === 'speaking' && next.emotion !== previous.emotion
}

export function buildEmotionMotionProfile(
  presentation: AvatarPresentation,
): AvatarMotionProfile {
  if (presentation.phase === 'thinking') {
    return {
      breathSpeed: 0.92,
      angleXOffset: -0.48,
      angleXAmplitude: 0.22,
      angleXSpeed: 0.46,
      angleYOffset: 0.2,
      angleYAmplitude: 0.12,
      angleYSpeed: 0.38,
      bodyXOffset: -0.16,
      bodyXAmplitude: 0.18,
      bodyXSpeed: 0.34,
      eyeXOffset: -0.05,
      eyeXAmplitude: 0.035,
      eyeXSpeed: 0.42,
      eyeYOffset: -0.04,
      eyeYAmplitude: 0.018,
      eyeYSpeed: 0.36,
      mouthIdleAmplitude: 0.006,
      mouthIdleSpeed: 1.8,
    }
  }

  if (presentation.phase === 'speaking') {
    if (presentation.emotion === 'excited') {
      return {
        breathSpeed: 1.42,
        angleXOffset: 0.22,
        angleXAmplitude: 0.48,
        angleXSpeed: 1.65,
        angleYOffset: -0.08,
        angleYAmplitude: 0.18,
        angleYSpeed: 1.24,
        bodyXOffset: 0.14,
        bodyXAmplitude: 0.34,
        bodyXSpeed: 1.16,
        eyeXOffset: 0.03,
        eyeXAmplitude: 0.03,
        eyeXSpeed: 0.96,
        eyeYOffset: 0,
        eyeYAmplitude: 0.02,
        eyeYSpeed: 0.88,
        mouthIdleAmplitude: 0.012,
        mouthIdleSpeed: 2.8,
      }
    }

    if (presentation.emotion === 'happy') {
      return {
        breathSpeed: 1.28,
        angleXOffset: 0.14,
        angleXAmplitude: 0.36,
        angleXSpeed: 1.34,
        angleYOffset: -0.05,
        angleYAmplitude: 0.14,
        angleYSpeed: 1.02,
        bodyXOffset: 0.08,
        bodyXAmplitude: 0.26,
        bodyXSpeed: 0.92,
        eyeXOffset: 0.02,
        eyeXAmplitude: 0.024,
        eyeXSpeed: 0.82,
        eyeYOffset: 0,
        eyeYAmplitude: 0.016,
        eyeYSpeed: 0.74,
        mouthIdleAmplitude: 0.011,
        mouthIdleSpeed: 2.55,
      }
    }

    if (presentation.emotion === 'sad') {
      return {
        breathSpeed: 0.98,
        angleXOffset: -0.12,
        angleXAmplitude: 0.18,
        angleXSpeed: 0.84,
        angleYOffset: 0.18,
        angleYAmplitude: 0.09,
        angleYSpeed: 0.72,
        bodyXOffset: -0.08,
        bodyXAmplitude: 0.12,
        bodyXSpeed: 0.62,
        eyeXOffset: -0.01,
        eyeXAmplitude: 0.016,
        eyeXSpeed: 0.54,
        eyeYOffset: 0.03,
        eyeYAmplitude: 0.016,
        eyeYSpeed: 0.48,
        mouthIdleAmplitude: 0.008,
        mouthIdleSpeed: 2.1,
      }
    }

    return {
      breathSpeed: 1.12,
      angleXOffset: 0,
      angleXAmplitude: 0.26,
      angleXSpeed: 1.08,
      angleYOffset: 0,
      angleYAmplitude: 0.11,
      angleYSpeed: 0.88,
      bodyXOffset: 0,
      bodyXAmplitude: 0.18,
      bodyXSpeed: 0.76,
      eyeXOffset: 0,
      eyeXAmplitude: 0.018,
      eyeXSpeed: 0.66,
      eyeYOffset: 0,
      eyeYAmplitude: 0.016,
      eyeYSpeed: 0.58,
      mouthIdleAmplitude: 0.009,
      mouthIdleSpeed: 2.35,
    }
  }

  if (presentation.phase === 'cooldown') {
    return {
      breathSpeed: 1.02,
      angleXOffset: 0,
      angleXAmplitude: 0.16,
      angleXSpeed: 0.7,
      angleYOffset: 0.04,
      angleYAmplitude: 0.08,
      angleYSpeed: 0.62,
      bodyXOffset: 0,
      bodyXAmplitude: 0.12,
      bodyXSpeed: 0.54,
      eyeXOffset: 0,
      eyeXAmplitude: 0.016,
      eyeXSpeed: 0.5,
      eyeYOffset: 0,
      eyeYAmplitude: 0.012,
      eyeYSpeed: 0.44,
      mouthIdleAmplitude: 0.008,
      mouthIdleSpeed: 2.1,
    }
  }

  return NEUTRAL_PROFILE
}
