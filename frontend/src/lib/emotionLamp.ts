import type { EmotionVisualPreset } from './lipsync'
import type { EmotionTelemetry, EmotionValue } from '../types/chat'

type LampStyleValue = string

export type EmotionLampStyle = Record<`--${string}`, LampStyleValue>

interface LampPersonality {
  glowAlpha: number
  shellOpacity: number
  waveDuration: number
  floatDuration: number
  pulseDuration: number
  coreOpacity: number
  waveOffset: number
  waveScale: number
}

const PERSONALITIES: Record<EmotionValue, LampPersonality> = {
  neutral: {
    glowAlpha: 0.4,
    shellOpacity: 0.92,
    waveDuration: 3.8,
    floatDuration: 4.4,
    pulseDuration: 4.8,
    coreOpacity: 0.24,
    waveOffset: 0.24,
    waveScale: 1.05,
  },
  happy: {
    glowAlpha: 0.5,
    shellOpacity: 0.95,
    waveDuration: 3.4,
    floatDuration: 4.0,
    pulseDuration: 4.4,
    coreOpacity: 0.3,
    waveOffset: 0.26,
    waveScale: 1.06,
  },
  thinking: {
    glowAlpha: 0.43,
    shellOpacity: 0.93,
    waveDuration: 4.2,
    floatDuration: 4.7,
    pulseDuration: 5.2,
    coreOpacity: 0.22,
    waveOffset: 0.18,
    waveScale: 1.03,
  },
  excited: {
    glowAlpha: 0.6,
    shellOpacity: 0.98,
    waveDuration: 3.1,
    floatDuration: 3.7,
    pulseDuration: 4.0,
    coreOpacity: 0.34,
    waveOffset: 0.3,
    waveScale: 1.08,
  },
  sad: {
    glowAlpha: 0.34,
    shellOpacity: 0.88,
    waveDuration: 4.7,
    floatDuration: 5.1,
    pulseDuration: 5.6,
    coreOpacity: 0.18,
    waveOffset: 0.14,
    waveScale: 1.02,
  },
}

function formatNumber(value: number): string {
  return value.toFixed(2)
}

export function buildEmotionLampStyle(
  telemetry: EmotionTelemetry,
  visual?: EmotionVisualPreset,
): EmotionLampStyle {
  const personality = PERSONALITIES[telemetry.value] ?? PERSONALITIES.neutral
  const isPreview = telemetry.stage === 'preview'
  const confidenceBoost = Math.min(Math.max(telemetry.confidence ?? 0.45, 0), 1) * 0.04

  const glowAlpha = personality.glowAlpha + confidenceBoost - (isPreview ? 0.12 : 0)
  const shellOpacity = personality.shellOpacity - (isPreview ? 0.09 : 0)
  const coreOpacity = personality.coreOpacity - (isPreview ? 0.06 : 0)
  const pulseDuration = personality.pulseDuration - (isPreview ? 0.4 : 0)
  const waveDuration = personality.waveDuration + (isPreview ? 0.25 : 0)
  const floatDuration = personality.floatDuration + (isPreview ? 0.2 : 0)
  const pulseScale = isPreview ? 1.03 : 1.015

  return {
    '--lamp-stage': telemetry.stage,
    '--lamp-body-background': visual?.color ?? 'linear-gradient(135deg, #7a8ca4 0%, #c0cad8 100%)',
    '--lamp-glow-color': visual?.glow ?? 'rgba(176, 194, 215, 0.38)',
    '--lamp-glow-alpha': formatNumber(glowAlpha),
    '--lamp-shell-opacity': formatNumber(shellOpacity),
    '--lamp-core-opacity': formatNumber(coreOpacity),
    '--lamp-float-duration': `${formatNumber(floatDuration)}s`,
    '--lamp-wave-duration': `${formatNumber(waveDuration)}s`,
    '--lamp-pulse-duration': `${formatNumber(pulseDuration)}s`,
    '--lamp-wave-offset': `${formatNumber(personality.waveOffset)}rem`,
    '--lamp-wave-scale': formatNumber(personality.waveScale),
    '--lamp-pulse-scale': formatNumber(pulseScale),
  }
}
