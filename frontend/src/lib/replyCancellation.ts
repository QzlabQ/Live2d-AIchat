import type { ChatMessage, ServerSocketMessage } from '../types/chat'

export function hasCancellableReplyActivity(state: {
  replyPending: boolean
  assistantDraftActive: boolean
  avatarSpeechActive: boolean
  queuedAudioCount: number
  bufferedAudioMs: number
  scheduledLeadMs: number
  currentAudioActive: boolean
  pendingStreamAudioCount: number
  scheduledSourceCount: number
}) {
  return (
    state.replyPending ||
    state.assistantDraftActive ||
    state.avatarSpeechActive ||
    state.queuedAudioCount > 0 ||
    state.bufferedAudioMs > 0 ||
    state.scheduledLeadMs > 0 ||
    state.currentAudioActive ||
    state.pendingStreamAudioCount > 0 ||
    state.scheduledSourceCount > 0
  )
}

const CANCEL_IGNORED_EVENT_TYPES = new Set<ServerSocketMessage['type']>([
  'text_delta',
  'asr_result',
  'audio',
  'tts_audio_chunk',
  'tts_viseme_chunk',
  'phonemes',
  'emotion',
  'avatar_phase',
  'reply_meta',
  'sources',
  'text_done',
  'audio_done',
  'done',
])

export function shouldIgnoreReplyEventWhileCancelling(payload: ServerSocketMessage) {
  return CANCEL_IGNORED_EVENT_TYPES.has(payload.type)
}

export function discardReplyMessages(
  messages: ChatMessage[],
  tracked: {
    userMessageId: string | null
    assistantMessageId: string | null
  },
) {
  return messages.filter(
    (message) =>
      message.id !== tracked.userMessageId &&
      message.id !== tracked.assistantMessageId,
  )
}
