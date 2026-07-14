import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

describe('Live2DStage source contracts', () => {
  it('resets expression targets and emotion parameter cache when model runtime is rebuilt', () => {
    const source = readFileSync(new URL('./Live2DStage.vue', import.meta.url), 'utf8')

    expect(source).toContain('function resetExpressionState()')
    expect(source).toContain('Object.keys(expressionTargets)')
    expect(source).toContain('delete expressionTargets[key]')
    expect(source).toContain('Object.keys(currentEmotionValues)')
    expect(source).toContain('delete currentEmotionValues[key]')
    expect(source).toContain('resetExpressionState()')
  })
})
