import { afterEach, describe, expect, it, vi } from 'vitest'

import { useVisitorSessions } from './useVisitorSessions'

vi.mock('../services/visitorApi', () => ({
  listVisitorSessions: vi.fn(),
  loadVisitorSessionMessages: vi.fn(),
}))

import { loadVisitorSessionMessages } from '../services/visitorApi'

function createDeferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void

  const promise = new Promise<T>((innerResolve, innerReject) => {
    resolve = innerResolve
    reject = innerReject
  })

  return { promise, resolve, reject }
}

describe('useVisitorSessions', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('ignores stale openSession responses when a newer request finishes later', async () => {
    const older = createDeferred<{
      items: Array<{ id: number; role: 'user'; content: string; createdAt: string }>
    }>()
    const newer = createDeferred<{
      items: Array<{ id: number; role: 'user'; content: string; createdAt: string }>
    }>()

    vi.mocked(loadVisitorSessionMessages)
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise)

    const sessions = useVisitorSessions('http://example.com/api')
    const olderTask = sessions.openSession('session-old')
    const newerTask = sessions.openSession('session-new')

    newer.resolve({
      items: [{ id: 2, role: 'user', content: 'newer', createdAt: '2026-07-08T10:00:01Z' }],
    })
    await newerTask

    older.resolve({
      items: [{ id: 1, role: 'user', content: 'older', createdAt: '2026-07-08T10:00:00Z' }],
    })
    await olderTask

    expect(sessions.activeSessionId.value).toBe('session-new')
    expect(sessions.activeMessages.value).toHaveLength(1)
    expect(sessions.activeMessages.value[0]?.content).toBe('newer')
    expect(sessions.loading.value).toBe(false)
  })
})
