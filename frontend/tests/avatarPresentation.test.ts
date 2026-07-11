import { describe, expect, it } from 'vitest'

import {
  computeAvatarPresentation,
  createDefaultConversationPhaseState,
  reduceAvatarPhaseEvent,
} from '../src/lib/avatarPresentation'

describe('avatarPresentation', () => {
  it('thinking phase suppresses idle motion and forces thinking baseline', () => {
    const state = reduceAvatarPhaseEvent(createDefaultConversationPhaseState(), {
      type: 'avatar_phase',
      phase: 'thinking',
      reply_id: 'reply-1',
      at_ms: 1000,
      reason: 'reply_started',
    })

    const presentation = computeAvatarPresentation(state, {
      emotion: 'happy',
      emotionStage: 'final',
      nowMs: 1100,
    })

    expect(presentation.phase).toBe('thinking')
    expect(presentation.emotion).toBe('thinking')
    expect(presentation.allowIdleMotion).toBe(false)
    expect(presentation.motionIntensity).toBe('none')
  })

  it('speaking phase keeps final emotion but only allows light action', () => {
    const state = reduceAvatarPhaseEvent(createDefaultConversationPhaseState(), {
      type: 'avatar_phase',
      phase: 'speaking',
      reply_id: 'reply-1',
      at_ms: 1000,
      reason: 'first_audio_chunk',
    })

    const presentation = computeAvatarPresentation(state, {
      emotion: 'excited',
      emotionStage: 'final',
      nowMs: 1100,
    })

    expect(presentation.phase).toBe('speaking')
    expect(presentation.emotion).toBe('excited')
    expect(presentation.emotionStage).toBe('final')
    expect(presentation.allowIdleMotion).toBe(false)
    expect(presentation.motionIntensity).toBe('light')
  })

  it('ignores stale idle events from an older reply', () => {
    const firstReplyThinking = reduceAvatarPhaseEvent(createDefaultConversationPhaseState(), {
      type: 'avatar_phase',
      phase: 'thinking',
      reply_id: 'reply-old',
      at_ms: 1000,
      reason: 'reply_started',
    })
    const secondReplyThinking = reduceAvatarPhaseEvent(firstReplyThinking, {
      type: 'avatar_phase',
      phase: 'thinking',
      reply_id: 'reply-new',
      at_ms: 1200,
      reason: 'reply_started',
    })
    const afterStaleIdle = reduceAvatarPhaseEvent(secondReplyThinking, {
      type: 'avatar_phase',
      phase: 'idle',
      reply_id: 'reply-old',
      at_ms: 1300,
      reason: 'reply_done',
    })

    expect(afterStaleIdle.phase).toBe('thinking')
    expect(afterStaleIdle.activeReplyId).toBe('reply-new')
  })

  it('uses backend at_ms when deciding cooldown expiry', () => {
    const cooldownState = reduceAvatarPhaseEvent(createDefaultConversationPhaseState(), {
      type: 'avatar_phase',
      phase: 'cooldown',
      reply_id: 'reply-1',
      at_ms: 1000,
      reason: 'audio_done',
    })

    const stillCooling = computeAvatarPresentation(cooldownState, {
      emotion: 'neutral',
      emotionStage: 'final',
      nowMs: 1500,
    })
    const cooledDown = computeAvatarPresentation(cooldownState, {
      emotion: 'neutral',
      emotionStage: 'final',
      nowMs: 2200,
    })

    expect(stillCooling.phase).toBe('cooldown')
    expect(cooledDown.phase).toBe('idle')
  })
})
