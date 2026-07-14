import { describe, expect, it } from 'vitest'

import type { AvatarPresentation } from './avatarPresentation'
import {
  buildEmotionMotionProfile,
  pickAvailableMotion,
  resolveEmotionMotionCandidates,
  shouldTriggerEmotionMotion,
} from './avatarMotion'

function createPresentation(
  overrides: Partial<AvatarPresentation> = {},
): AvatarPresentation {
  return {
    phase: 'idle',
    emotion: 'neutral',
    emotionStage: 'final',
    allowIdleMotion: true,
    motionIntensity: 'normal',
    lipSyncActive: false,
    activeReplyId: null,
    ...overrides,
  }
}

describe('avatarMotion', () => {
  it('prefers body and upward motions for excited speaking', () => {
    const candidates = resolveEmotionMotionCandidates(
      createPresentation({ phase: 'speaking', emotion: 'excited', allowIdleMotion: false }),
    )

    expect(candidates).toEqual(['Tap@Body', 'FlickUp', 'Tap', 'Flick'])
  })

  it('matches the first available motion candidate', () => {
    const picked = pickAvailableMotion(['Idle', 'FlickUp', 'Tap'], ['Tap@Body', 'FlickUp', 'Tap'])
    expect(picked).toBe('FlickUp')
  })

  it('triggers a motion when entering thinking or changing speaking emotion', () => {
    const previous = createPresentation({ phase: 'speaking', emotion: 'happy', allowIdleMotion: false })
    const nextThinking = createPresentation({ phase: 'thinking', emotion: 'thinking', allowIdleMotion: false })
    const nextExcited = createPresentation({ phase: 'speaking', emotion: 'excited', allowIdleMotion: false })
    const stableIdle = createPresentation()

    expect(shouldTriggerEmotionMotion(previous, nextThinking)).toBe(true)
    expect(shouldTriggerEmotionMotion(previous, nextExcited)).toBe(true)
    expect(shouldTriggerEmotionMotion(previous, stableIdle)).toBe(false)
  })

  it('keeps thinking motions slower and smaller than excited speaking', () => {
    const thinking = buildEmotionMotionProfile(
      createPresentation({ phase: 'thinking', emotion: 'thinking', allowIdleMotion: false }),
    )
    const excited = buildEmotionMotionProfile(
      createPresentation({ phase: 'speaking', emotion: 'excited', allowIdleMotion: false }),
    )

    expect(thinking.breathSpeed).toBeLessThan(excited.breathSpeed)
    expect(thinking.angleXAmplitude).toBeLessThan(excited.angleXAmplitude)
    expect(thinking.bodyXAmplitude).toBeLessThan(excited.bodyXAmplitude)
  })
})
