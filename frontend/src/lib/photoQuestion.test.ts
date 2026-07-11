import { describe, expect, it } from 'vitest'

import { buildPhotoQuestion, shouldEnterThinkingForPhoto } from './photoQuestion'

describe('buildPhotoQuestion', () => {
  it('creates a natural follow-up question from recognition output', () => {
    expect(
      buildPhotoQuestion({
        recognizedSpot: '九龙灌浴',
        recognitionSummary: '这看起来是九龙灌浴表演区域。',
      }),
    ).toContain('九龙灌浴')
  })

  it('prefers the resolved question when the recognizer already provides one', () => {
    expect(
      buildPhotoQuestion({
        recognizedSpot: '梵宫',
        recognitionSummary: '这里看起来是梵宫内部区域。',
        resolvedQuestion: '我拍到的是梵宫吗？它最值得看的部分是什么？',
      }),
    ).toBe('我拍到的是梵宫吗？它最值得看的部分是什么？')
  })
})

describe('shouldEnterThinkingForPhoto', () => {
  it('returns true while upload or recognition is pending', () => {
    expect(shouldEnterThinkingForPhoto({ uploading: true, recognizing: false })).toBe(true)
    expect(shouldEnterThinkingForPhoto({ uploading: false, recognizing: true })).toBe(true)
  })

  it('returns false once photo flow is idle', () => {
    expect(shouldEnterThinkingForPhoto({ uploading: false, recognizing: false })).toBe(false)
  })
})
