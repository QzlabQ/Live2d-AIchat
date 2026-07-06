import assert from 'node:assert/strict'
import test from 'node:test'

import { attachAssistantMessageMeta } from '../src/lib/chatMessageMeta.ts'
import type { ChatMessage, SourceItem } from '../src/types/chat.ts'

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

test('prefers the active assistant draft when attaching reply metadata', () => {
  const messages: ChatMessage[] = [
    createAssistantMessage({ id: 'assistant-old', content: 'previous answer' }),
    createAssistantMessage({ id: 'assistant-draft', content: 'draft answer', streaming: true }),
  ]

  const attached = attachAssistantMessageMeta(messages, 'assistant-draft', {
    replyKind: 'rag',
    needsFollowup: true,
    sources: sampleSources,
  })

  assert.equal(attached, true)
  assert.deepEqual(messages[1].sources, sampleSources)
  assert.equal(messages[1].replyKind, 'rag')
  assert.equal(messages[1].needsFollowup, true)
  assert.equal(messages[0].sources, undefined)
})

test('falls back to the most recent assistant message after draft finalize', () => {
  const messages: ChatMessage[] = [
    { id: 'user-1', role: 'user', content: 'question' },
    createAssistantMessage({ id: 'assistant-final', content: 'final answer', streaming: false }),
  ]

  const attached = attachAssistantMessageMeta(messages, null, {
    sources: sampleSources,
    needsFollowup: false,
  })

  assert.equal(attached, true)
  assert.deepEqual(messages[1].sources, sampleSources)
  assert.equal(messages[1].needsFollowup, false)
})

test('returns false when there is no assistant message to update', () => {
  const messages: ChatMessage[] = [{ id: 'user-1', role: 'user', content: 'question' }]

  const attached = attachAssistantMessageMeta(messages, null, {
    replyKind: 'rag',
  })

  assert.equal(attached, false)
})
