import { describe, expect, it } from 'vitest'

import { attachAssistantMessageMeta } from '../src/lib/chatMessageMeta'
import type { ChatMessage, SourceItem } from '../src/types/chat'

function createAssistantMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: overrides.id ?? 'assistant-1',
    role: 'assistant',
    content: overrides.content ?? 'hello',
    ...overrides,
  }
}

const sampleSources: SourceItem[] = [
  {
    title: 'West Lake Overview',
    filename: 'west-lake.pdf',
    excerpt: 'West Lake is a freshwater lake in Hangzhou.',
  },
]

describe('attachAssistantMessageMeta', () => {
  it('prefers the active assistant draft when attaching reply metadata', () => {
    const messages: ChatMessage[] = [
      createAssistantMessage({ id: 'assistant-old', content: 'previous answer' }),
      createAssistantMessage({ id: 'assistant-draft', content: 'draft answer', streaming: true }),
    ]

    const attached = attachAssistantMessageMeta(messages, 'assistant-draft', {
      replyKind: 'rag',
      needsFollowup: true,
      sources: sampleSources,
    })

    expect(attached).toBe(true)
    expect(messages[1].sources).toEqual(sampleSources)
    expect(messages[1].replyKind).toBe('rag')
    expect(messages[1].needsFollowup).toBe(true)
    expect(messages[0].sources).toBeUndefined()
  })

  it('falls back to the most recent assistant message after draft finalize', () => {
    const messages: ChatMessage[] = [
      { id: 'user-1', role: 'user', content: 'question' },
      createAssistantMessage({ id: 'assistant-final', content: 'final answer', streaming: false }),
    ]

    const attached = attachAssistantMessageMeta(messages, null, {
      sources: sampleSources,
      needsFollowup: false,
    })

    expect(attached).toBe(true)
    expect(messages[1].sources).toEqual(sampleSources)
    expect(messages[1].needsFollowup).toBe(false)
  })

  it('returns false when there is no assistant message to update', () => {
    const messages: ChatMessage[] = [{ id: 'user-1', role: 'user', content: 'question' }]

    const attached = attachAssistantMessageMeta(messages, null, {
      replyKind: 'rag',
    })

    expect(attached).toBe(false)
  })
})
