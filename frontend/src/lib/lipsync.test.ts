import { describe, expect, it } from 'vitest'

import { buildExpressionTarget } from './lipsync'

describe('lipsync mouth parameter guards', () => {
  it('ignores mouth parameters when building expression targets', () => {
    const target = buildExpressionTarget([
      { Id: 'ParamAngleX', Value: 0.4, Blend: 'Overwrite' },
      { Id: 'ParamMouthOpenY', Value: 1, Blend: 'Overwrite' },
      { Id: 'ParamMouthForm', Value: -1, Blend: 'Overwrite' },
    ])

    expect(target).toEqual({
      ParamAngleX: 0.4,
    })
  })
})
