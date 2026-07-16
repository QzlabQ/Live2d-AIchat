import { describe, expect, it } from 'vitest'

import { canUsePhotoAttachment, extractClipboardImageFile } from './photoAttachment'

function createClipboardItem(options: {
  kind?: string
  type?: string
  file?: File | null
}) {
  return {
    kind: options.kind,
    type: options.type,
    getAsFile: () => options.file ?? null,
  }
}

describe('canUsePhotoAttachment', () => {
  it('allows photo attachment when the visitor session UI is idle', () => {
    expect(
      canUsePhotoAttachment({
        sessionBooting: false,
        sessionsLoading: false,
      }),
    ).toBe(true)
  })

  it('blocks photo attachment while the session UI is still booting or refreshing', () => {
    expect(
      canUsePhotoAttachment({
        sessionBooting: true,
        sessionsLoading: false,
      }),
    ).toBe(false)

    expect(
      canUsePhotoAttachment({
        sessionBooting: false,
        sessionsLoading: true,
      }),
    ).toBe(false)
  })
})

describe('extractClipboardImageFile', () => {
  it('returns the first supported clipboard image file', () => {
    const file = new File(['mock'], 'gate.png', { type: 'image/png' })

    expect(
      extractClipboardImageFile([
        createClipboardItem({ kind: 'string', type: 'text/plain' }),
        createClipboardItem({ kind: 'file', type: 'image/png', file }),
      ]),
    ).toBe(file)
  })

  it('uses the clipboard item mime type when browsers omit the file mime type', () => {
    const file = new File(['mock'], 'gate', { type: '' })

    expect(
      extractClipboardImageFile([
        createClipboardItem({ kind: 'file', type: 'image/webp', file }),
      ]),
    ).toBe(file)
  })

  it('ignores unsupported image types and empty clipboard files', () => {
    expect(
      extractClipboardImageFile([
        createClipboardItem({
          kind: 'file',
          type: 'image/gif',
          file: new File(['gif'], 'gate.gif', { type: 'image/gif' }),
        }),
        createClipboardItem({
          kind: 'file',
          type: 'image/png',
          file: null,
        }),
      ]),
    ).toBeNull()
  })
})
