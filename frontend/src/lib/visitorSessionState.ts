import type { ChatMessage } from '../types/chat'
import type {
  VisitorSessionMessage,
  VisitorSessionMessageRole,
  VisitorSessionSummary,
} from '../types/visitor'

function toTimestamp(value: string | undefined) {
  const parsed = Date.parse(value ?? '')
  return Number.isNaN(parsed) ? 0 : parsed
}

export function sortSessionSummaries<T extends Pick<VisitorSessionSummary, 'sessionId' | 'updatedAt'>>(
  items: T[],
) {
  return [...items].sort((left, right) => {
    const delta = toTimestamp(right.updatedAt) - toTimestamp(left.updatedAt)
    if (delta !== 0) {
      return delta
    }

    return left.sessionId.localeCompare(right.sessionId)
  })
}

export function normalizeVisitorMessageRole(role: string): VisitorSessionMessageRole {
  if (role === 'user' || role === 'assistant' || role === 'system') {
    return role
  }

  throw new Error(`Unsupported visitor session message role: ${role}`)
}

export function mapHistoryMessagesToChatMessages(items: VisitorSessionMessage[]): ChatMessage[] {
  return items.map((item) => ({
    id: `history-${item.id}`,
    role: normalizeVisitorMessageRole(item.role),
    content: item.content,
    meta: '历史记录',
    streaming: false,
  }))
}

export function canSwitchSessionWhileIdle(state: {
  isStreaming: boolean
  isRecording: boolean
}) {
  return !state.isStreaming && !state.isRecording
}

export function canToggleRecording(state: {
  isSupported: boolean
  isConnected: boolean
  sessionBooting: boolean
  canCancelReply: boolean
  replyCanceling: boolean
  isRecording: boolean
}) {
  if (state.isRecording) {
    return true
  }

  return (
    state.isSupported &&
    state.isConnected &&
    !state.sessionBooting &&
    !state.canCancelReply &&
    !state.replyCanceling
  )
}

export function isReplyFlowActiveForSessionSwitch(state: {
  replyPending: boolean
  isPhotoPending: boolean
  assistantDraftActive: boolean
  avatarSpeechActive: boolean
  queuedAudioCount: number
  bufferedAudioMs: number
  scheduledLeadMs: number
}) {
  return (
    state.replyPending ||
    state.isPhotoPending ||
    state.assistantDraftActive ||
    state.avatarSpeechActive ||
    state.queuedAudioCount > 0 ||
    state.bufferedAudioMs > 0 ||
    state.scheduledLeadMs > 0
  )
}
