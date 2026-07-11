import { describe, expect, it } from 'vitest'

import { buildEmotionLampStyle } from '../src/lib/emotionLamp'

describe('buildEmotionLampStyle', () => {
  it('makes preview softer than final for the same emotion', () => {
    const preview = buildEmotionLampStyle({
      value: 'happy',
      stage: 'preview',
      confidence: 0.8,
      keywords: [],
      reason: '',
      source: 'heuristic',
    })
    const final = buildEmotionLampStyle({
      value: 'happy',
      stage: 'final',
      confidence: 0.8,
      keywords: [],
      reason: '',
      source: 'heuristic',
    })

    expect(preview['--lamp-stage']).toBe('preview')
    expect(final['--lamp-stage']).toBe('final')
    expect(Number(preview['--lamp-glow-alpha'])).toBeLessThan(Number(final['--lamp-glow-alpha']))
    expect(Number(preview['--lamp-shell-opacity'])).toBeLessThan(Number(final['--lamp-shell-opacity']))
  })

  it('keeps excited brighter than sad and thinking slower than happy', () => {
    const excited = buildEmotionLampStyle({
      value: 'excited',
      stage: 'final',
      confidence: 0.9,
      keywords: [],
      reason: '',
      source: 'llm',
    })
    const sad = buildEmotionLampStyle({
      value: 'sad',
      stage: 'final',
      confidence: 0.9,
      keywords: [],
      reason: '',
      source: 'llm',
    })
    const thinking = buildEmotionLampStyle({
      value: 'thinking',
      stage: 'final',
      confidence: 0.9,
      keywords: [],
      reason: '',
      source: 'llm',
    })
    const happy = buildEmotionLampStyle({
      value: 'happy',
      stage: 'final',
      confidence: 0.9,
      keywords: [],
      reason: '',
      source: 'llm',
    })

    expect(Number(excited['--lamp-glow-alpha'])).toBeGreaterThan(Number(sad['--lamp-glow-alpha']))
    expect(parseFloat(thinking['--lamp-wave-duration'])).toBeGreaterThan(
      parseFloat(happy['--lamp-wave-duration']),
    )
    expect(parseFloat(sad['--lamp-float-duration'])).toBeGreaterThan(
      parseFloat(excited['--lamp-float-duration']),
    )
  })
})
