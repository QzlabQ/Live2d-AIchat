import { afterEach, describe, expect, it, vi } from 'vitest'

import { recognizeVisitorPhoto } from './visitorApi'

const originalFetch = globalThis.fetch

afterEach(() => {
  vi.restoreAllMocks()
  globalThis.fetch = originalFetch
})

describe('recognizeVisitorPhoto', () => {
  it('omits empty interest tags so the backend can fall back to session defaults', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = init?.body
      expect(body).toBeInstanceOf(FormData)
      const formData = body as FormData
      expect(formData.get('interest_tags')).toBeNull()

      return new Response(
        JSON.stringify({
          recognized_spot: 'Main Gate',
          recognition_summary: 'A stone gate at the scenic area entrance.',
          resolved_question: 'Can you introduce the Main Gate first?',
          stored_image_path: 'session-1/main-gate.jpg',
        }),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        },
      )
    })
    globalThis.fetch = fetchMock as typeof fetch

    const result = await recognizeVisitorPhoto(
      'http://testserver/api/v1',
      'session-1',
      new File(['mock'], 'gate.jpg', { type: 'image/jpeg' }),
      [],
    )

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(result.recognizedSpot).toBe('Main Gate')
  })

  it('surfaces backend detail text when recognition fails', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'Image file is empty.' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      }),
    ) as typeof fetch

    await expect(
      recognizeVisitorPhoto(
        'http://testserver/api/v1',
        'session-1',
        new File([''], 'empty.jpg', { type: 'image/jpeg' }),
        [],
      ),
    ).rejects.toThrow('Failed to recognize photo: Image file is empty.')
  })
})
