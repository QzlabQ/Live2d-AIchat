import type { ChatMessage, SourceItem, SourcesEvent } from '../types/chat'

export interface AssistantMessageMetaPatch {
  replyKind?: string
  needsFollowup?: boolean
  sources?: SourceItem[]
}

function findAssistantMessage(messages: ChatMessage[], assistantDraftId: string | null) {
  if (assistantDraftId) {
    const draft = messages.find((message) => message.id === assistantDraftId && message.role === 'assistant')
    if (draft) {
      return draft
    }
  }

  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message.role === 'assistant') {
      return message
    }
  }

  return null
}

export function normalizeSources(items: SourcesEvent['items']): SourceItem[] {
  return items.map((item) => ({
    filename: item.filename,
    title: item.title,
    excerpt: item.excerpt,
    category: item.category,
    chunkIndex: item.chunk_index,
    retrievalScore: item.retrieval_score,
    rerankScore: item.rerank_score,
  }))
}

export function attachAssistantMessageMeta(
  messages: ChatMessage[],
  assistantDraftId: string | null,
  patch: AssistantMessageMetaPatch,
) {
  const target = findAssistantMessage(messages, assistantDraftId)
  if (!target) {
    return false
  }

  if (patch.replyKind !== undefined) {
    target.replyKind = patch.replyKind
  }

  if (patch.needsFollowup !== undefined) {
    target.needsFollowup = patch.needsFollowup
  }

  if (patch.sources !== undefined) {
    target.sources = patch.sources
  }

  return true
}
