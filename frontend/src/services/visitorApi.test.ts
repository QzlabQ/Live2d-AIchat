import { afterEach, describe, expect, it, vi } from 'vitest'

import { listVisitorAvatarProfiles, recognizeVisitorPhoto, uploadVisitorPhotoAttachment } from './visitorApi'

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

describe('uploadVisitorPhotoAttachment', () => {
  it('maps preview URLs against the API host so the pending thumbnail can render before send', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({
          stored_image_path: 'session-1/uploaded.jpg',
          filename: 'uploaded.jpg',
          mime_type: 'image/jpeg',
          preview_url: '/api/v1/sessions/session-1/photos/uploaded.jpg',
        }),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    ) as typeof fetch

    const result = await uploadVisitorPhotoAttachment(
      'http://testserver/api/v1',
      'session-1',
      new File(['mock'], 'gate.jpg', { type: 'image/jpeg' }),
    )

    expect(result.storedImagePath).toBe('session-1/uploaded.jpg')
    expect(result.previewUrl).toBe('http://testserver/api/v1/sessions/session-1/photos/uploaded.jpg')
  })

  it('surfaces backend detail text when upload fails', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'Unsupported image content type.' }), {
        status: 415,
        headers: { 'Content-Type': 'application/json' },
      }),
    ) as typeof fetch

    await expect(
      uploadVisitorPhotoAttachment(
        'http://testserver/api/v1',
        'session-1',
        new File(['mock'], 'gate.gif', { type: 'image/gif' }),
      ),
    ).rejects.toThrow('Failed to upload photo: Unsupported image content type.')
  })
})

describe('listVisitorAvatarProfiles', () => {
  it('falls back to Haru when the backend still returns the legacy broken guide path', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({
          items: [
            {
              id: 1,
              name: '默认数字人',
              slug: 'default-avatar',
              is_active: true,
              model_path: '/live2d/models/guide/guide.model3.json',
              display_scale: 1,
              display_offset_x: 0,
              display_offset_y: 0,
              stage_height: 420,
              updated_at: '2026-07-17T05:39:12',
            },
          ],
        }),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    ) as typeof fetch

    const response = await listVisitorAvatarProfiles('http://testserver/api/v1')

    expect(response.items[0]?.modelPath).toBe('/live2d/haru/haru_greeter_t03.model3.json')
  })
})
