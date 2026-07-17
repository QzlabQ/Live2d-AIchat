import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

describe('frontend index bootstrap', () => {
  it('loads Live2D Cubism Core from a local static asset instead of an external CDN', () => {
    const source = readFileSync(new URL('../index.html', import.meta.url), 'utf8')

    expect(source).toContain('/vendor/live2d/live2dcubismcore.min.js')
    expect(source).not.toContain('https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js')
  })
})
