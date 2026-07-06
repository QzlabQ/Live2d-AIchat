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
    timestamp_ms: 1000,
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
    timestamp_ms: 1000,
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
    timestamp_ms: 1000,
  })
  const secondReplyThinking = reduceAvatarPhaseEvent(firstReplyThinking, {
    type: 'avatar_phase',
    phase: 'thinking',
    reply_id: 'reply-new',
    timestamp_ms: 1200,
  })
  const afterStaleIdle = reduceAvatarPhaseEvent(secondReplyThinking, {
    type: 'avatar_phase',
    phase: 'idle',
    reply_id: 'reply-old',
    timestamp_ms: 1300,
  })

  assert.equal(afterStaleIdle.phase, 'thinking')
  assert.equal(afterStaleIdle.activeReplyId, 'reply-new')
})
