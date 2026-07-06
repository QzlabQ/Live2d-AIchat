import type { AvatarPhaseEvent, ConversationPhase, EmotionStage, EmotionValue } from '../types/chat'

export type { AvatarPhaseEvent, ConversationPhase }

export interface ConversationPhaseState {
  phase: ConversationPhase
  activeReplyId: string | null
  lastUpdatedAtMs: number
  cooldownUntilMs: number | null
}

export type AvatarMotionIntensity = 'none' | 'light' | 'normal'

export interface AvatarPresentation {
  phase: ConversationPhase
  emotion: EmotionValue
  emotionStage: EmotionStage
  allowIdleMotion: boolean
  motionIntensity: AvatarMotionIntensity
  lipSyncActive: boolean
  activeReplyId: string | null
}

export interface AvatarPresentationInput {
  emotion: EmotionValue
  emotionStage: EmotionStage
  lipSyncActive?: boolean
  nowMs?: number
}

const DEFAULT_COOLDOWN_MS = 900

export function createDefaultConversationPhaseState(): ConversationPhaseState {
  return {
    phase: 'idle',
    activeReplyId: null,
    lastUpdatedAtMs: 0,
    cooldownUntilMs: null,
  }
}

function isStaleSettlingEvent(state: ConversationPhaseState, event: AvatarPhaseEvent) {
  if (event.phase !== 'idle' && event.phase !== 'cooldown') {
    return false
  }

  return Boolean(
    state.activeReplyId &&
      event.reply_id &&
      event.reply_id !== state.activeReplyId,
  )
}

export function reduceAvatarPhaseEvent(
  state: ConversationPhaseState,
  event: AvatarPhaseEvent,
): ConversationPhaseState {
  if (isStaleSettlingEvent(state, event)) {
    return state
  }

  const timestampMs = event.timestamp_ms ?? Date.now()
  const activeReplyId =
    event.phase === 'idle' ? null : event.reply_id ?? state.activeReplyId

  return {
    phase: event.phase,
    activeReplyId,
    lastUpdatedAtMs: timestampMs,
    cooldownUntilMs:
      event.phase === 'cooldown'
        ? timestampMs + DEFAULT_COOLDOWN_MS
        : null,
  }
}

function resolvePhase(state: ConversationPhaseState, nowMs: number): ConversationPhase {
  if (
    state.phase === 'cooldown' &&
    state.cooldownUntilMs !== null &&
    nowMs >= state.cooldownUntilMs
  ) {
    return 'idle'
  }

  return state.phase
}

export function computeAvatarPresentation(
  state: ConversationPhaseState,
  input: AvatarPresentationInput,
): AvatarPresentation {
  const phase = resolvePhase(state, input.nowMs ?? Date.now())

  if (phase === 'thinking') {
    return {
      phase,
      emotion: 'thinking',
      emotionStage: 'final',
      allowIdleMotion: false,
      motionIntensity: 'none',
      lipSyncActive: input.lipSyncActive ?? false,
      activeReplyId: state.activeReplyId,
    }
  }

  if (phase === 'speaking') {
    return {
      phase,
      emotion: input.emotion,
      emotionStage: 'final',
      allowIdleMotion: false,
      motionIntensity: 'light',
      lipSyncActive: input.lipSyncActive ?? false,
      activeReplyId: state.activeReplyId,
    }
  }

  if (phase === 'cooldown') {
    return {
      phase,
      emotion: input.emotion,
      emotionStage: input.emotionStage,
      allowIdleMotion: false,
      motionIntensity: 'light',
      lipSyncActive: input.lipSyncActive ?? false,
      activeReplyId: state.activeReplyId,
    }
  }

  return {
    phase,
    emotion: input.emotion,
    emotionStage: input.emotionStage,
    allowIdleMotion: true,
    motionIntensity: 'normal',
    lipSyncActive: input.lipSyncActive ?? false,
    activeReplyId: null,
  }
}
