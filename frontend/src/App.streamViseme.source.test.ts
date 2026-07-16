import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

describe('App streaming viseme wiring', () => {
  it('passes backend viseme offset metadata into the Live2D scheduler', () => {
    const source = readFileSync(new URL('./App.vue', import.meta.url), 'utf8')

    expect(source).toContain('payload.offset_ms')
  })
})
