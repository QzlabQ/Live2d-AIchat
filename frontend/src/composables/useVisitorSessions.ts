import { ref } from 'vue'

import { mapHistoryMessagesToChatMessages, sortSessionSummaries } from '../lib/visitorSessionState'
import { listVisitorSessions, loadVisitorSessionMessages } from '../services/visitorApi'
import type { ChatMessage } from '../types/chat'
import type { VisitorSessionSummary } from '../types/visitor'

function cloneChatMessages(messages: ChatMessage[]) {
  return messages.map((message) => ({
    ...message,
    attachments: message.attachments?.map((attachment) => ({ ...attachment })),
    sources: message.sources?.map((source) => ({ ...source })),
  }))
}

export function useVisitorSessions(apiBaseUrl: string) {
  const sessionList = ref<VisitorSessionSummary[]>([])
  const activeSessionId = ref<string | null>(null)
  const activeMessages = ref<ChatMessage[]>([])
  const loading = ref(false)
  const refreshing = ref(false)
  const error = ref('')
  let latestOpenSessionRequestId = 0

  async function refreshSessions() {
    refreshing.value = true
    error.value = ''

    try {
      const payload = await listVisitorSessions(apiBaseUrl)
      sessionList.value = sortSessionSummaries(payload.items)
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : '加载历史会话失败'
      throw caught
    } finally {
      refreshing.value = false
    }
  }

  async function openSession(sessionId: string) {
    const requestId = ++latestOpenSessionRequestId
    loading.value = true
    error.value = ''

    try {
      const detail = await loadVisitorSessionMessages(apiBaseUrl, sessionId)
      if (requestId !== latestOpenSessionRequestId) {
        return
      }

      activeSessionId.value = sessionId
      activeMessages.value = mapHistoryMessagesToChatMessages(detail.items)
    } catch (caught) {
      if (requestId !== latestOpenSessionRequestId) {
        return
      }

      error.value = caught instanceof Error ? caught.message : '加载会话内容失败'
      throw caught
    } finally {
      if (requestId === latestOpenSessionRequestId) {
        loading.value = false
      }
    }
  }

  function setActiveSession(sessionId: string | null, messages: ChatMessage[] = []) {
    activeSessionId.value = sessionId
    activeMessages.value = cloneChatMessages(messages)
  }

  function replaceActiveMessages(messages: ChatMessage[]) {
    activeMessages.value = cloneChatMessages(messages)
  }

  return {
    sessionList,
    activeSessionId,
    activeMessages,
    loading,
    refreshing,
    error,
    refreshSessions,
    openSession,
    setActiveSession,
    replaceActiveMessages,
  }
}
