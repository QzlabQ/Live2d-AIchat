import { describe, expect, it } from 'vitest'

describe('streaming viseme timing helpers', () => {
  it('normalizes scheduled frames when chunk timing is relative to the chunk start', async () => {
    const module = await import('../src/lib/lipsync')

    expect(typeof module.resolveScheduledPhonemeFrames).toBe('function')

    const frames = module.resolveScheduledPhonemeFrames?.(
      [
        { ph: 'a', start: 0, end: 0.18 },
        { ph: 'e', start: 0.18, end: 0.34 },
      ],
      12.5,
      1520,
    )

    expect(frames).toEqual([
      { ph: 'a', start: 12.5, end: 12.68 },
      { ph: 'e', start: 12.68, end: 12.84 },
    ])
  })

  it('normalizes scheduled frames when chunk timing is already offset within the segment', async () => {
    const module = await import('../src/lib/lipsync')

    expect(typeof module.resolveScheduledPhonemeFrames).toBe('function')

    const frames = module.resolveScheduledPhonemeFrames?.(
      [
        { ph: 'a', start: 1.52, end: 1.7 },
        { ph: 'e', start: 1.7, end: 1.86 },
      ],
      12.5,
      1520,
    )

    expect(frames).toEqual([
      { ph: 'a', start: 12.5, end: 12.68 },
      { ph: 'e', start: 12.68, end: 12.84 },
    ])
  })
})
