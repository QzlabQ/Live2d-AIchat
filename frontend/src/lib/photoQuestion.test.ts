import { describe, expect, it } from 'vitest'

import { buildPhotoQuestion } from './photoQuestion'

describe('buildPhotoQuestion', () => {
  it('creates a natural follow-up question from recognition output', () => {
    expect(
      buildPhotoQuestion({
        recognizedSpot: '九龙灌浴',
        recognitionSummary: '这看起来是九龙灌浴表演区域。',
      }),
    ).toContain('九龙灌浴')
  })
})
