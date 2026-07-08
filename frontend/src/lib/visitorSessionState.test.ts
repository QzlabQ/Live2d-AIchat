import { describe, expect, it } from 'vitest'

import { normalizeVisitorMessageRole, sortSessionSummaries } from './visitorSessionState'

describe('sortSessionSummaries', () => {
  it('sorts sessions by updatedAt descending', () => {
    const items = sortSessionSummaries([
      { sessionId: 'a', updatedAt: '2026-07-07T10:00:00Z' },
      { sessionId: 'b', updatedAt: '2026-07-07T11:00:00Z' },
    ])

    expect(items[0].sessionId).toBe('b')
  })
})

describe('normalizeVisitorMessageRole', () => {
  it('accepts supported history message roles', () => {
    expect(normalizeVisitorMessageRole('assistant')).toBe('assistant')
    expect(normalizeVisitorMessageRole('user')).toBe('user')
    expect(normalizeVisitorMessageRole('system')).toBe('system')
  })

  it('rejects unsupported history message roles', () => {
    expect(() => normalizeVisitorMessageRole('moderator')).toThrow(
      'Unsupported visitor session message role: moderator',
    )
  })
})
