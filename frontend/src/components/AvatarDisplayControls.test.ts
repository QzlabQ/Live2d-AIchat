import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

describe('AvatarDisplayControls source contract', () => {
  const source = readFileSync(new URL('./AvatarDisplayControls.vue', import.meta.url), 'utf-8')

  it('exposes avatar display fields and reset event', () => {
    expect(source).toContain('modelValue')
    expect(source).toContain('displayScale')
    expect(source).toContain('displayOffsetX')
    expect(source).toContain('displayOffsetY')
    expect(source).toContain('stageHeight')
    expect(source).toContain("emit('reset')")
  })
})
