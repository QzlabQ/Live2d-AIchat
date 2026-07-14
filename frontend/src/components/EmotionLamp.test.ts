import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

describe('EmotionLamp source contract', () => {
  const source = readFileSync(new URL('./EmotionLamp.vue', import.meta.url), 'utf-8')

  it('reuses the shared emotion lamp style and telemetry fields', () => {
    expect(source).toContain('buildEmotionLampStyle')
    expect(source).toContain('class="emotion-lamp-shell"')
    expect(source).toContain('class="emotion-lamp"')
    expect(source).toContain('emotionTelemetry.reason')
    expect(source).toContain('emotionTelemetry.keywords')
  })
})
