import assert from 'node:assert/strict'
import test from 'node:test'

import {
  computeAvatarPresentation,
  createDefaultConversationPhaseState,
  reduceAvatarPhaseEvent,
} from '../src/lib/avatarPresentation.ts'

test('thinking phase suppresses idle motion and forces thinking baseline', () => {
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

  assert.equal(presentation.phase, 'thinking')
  assert.equal(presentation.emotion, 'thinking')
  assert.equal(presentation.allowIdleMotion, false)
  assert.equal(presentation.motionIntensity, 'none')
})

test('speaking phase keeps final emotion but only allows light action', () => {
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

  assert.equal(presentation.phase, 'speaking')
  assert.equal(presentation.emotion, 'excited')
  assert.equal(presentation.emotionStage, 'final')
  assert.equal(presentation.allowIdleMotion, false)
  assert.equal(presentation.motionIntensity, 'light')
})

test('stale reply idle event is ignored after a newer reply is active', () => {
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

  assert.equal(afterStaleIdle.phase, 'thinking')
  assert.equal(afterStaleIdle.activeReplyId, 'reply-new')
})

test('cooldown expiry uses backend at_ms instead of local wall clock fallback', () => {
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

  assert.equal(stillCooling.phase, 'cooldown')
  assert.equal(cooledDown.phase, 'idle')
})
