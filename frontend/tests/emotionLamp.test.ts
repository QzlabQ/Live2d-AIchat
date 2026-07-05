import assert from 'node:assert/strict'
import test from 'node:test'

import { buildEmotionLampStyle } from '../src/lib/emotionLamp.ts'

test('preview is softer than final for the same emotion', () => {
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

  assert.equal(preview['--lamp-stage'], 'preview')
  assert.equal(final['--lamp-stage'], 'final')
  assert.ok(Number(preview['--lamp-glow-alpha']) < Number(final['--lamp-glow-alpha']))
  assert.ok(Number(preview['--lamp-shell-opacity']) < Number(final['--lamp-shell-opacity']))
})

test('excited is brighter than sad and thinking moves slower than happy', () => {
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

  assert.ok(Number(excited['--lamp-glow-alpha']) > Number(sad['--lamp-glow-alpha']))
  assert.ok(parseFloat(thinking['--lamp-wave-duration']) > parseFloat(happy['--lamp-wave-duration']))
  assert.ok(parseFloat(sad['--lamp-float-duration']) > parseFloat(excited['--lamp-float-duration']))
})
