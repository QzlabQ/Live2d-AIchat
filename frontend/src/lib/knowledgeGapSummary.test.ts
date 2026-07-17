import { describe, expect, it } from 'vitest'

import { buildKnowledgeGapStatusDistribution } from './knowledgeGapSummary'

describe('knowledgeGapSummary', () => {
  it('returns null when there are no status counts', () => {
    expect(buildKnowledgeGapStatusDistribution([])).toBeNull()
  })

  it('builds status distribution segments and a conic gradient from aggregate counts', () => {
    const distribution = buildKnowledgeGapStatusDistribution([
      { status: 'pending', count: 5 },
      { status: 'draft', count: 3 },
      { status: 'imported', count: 2 },
    ])

    expect(distribution).not.toBeNull()
    expect(distribution?.totalCount).toBe(10)
    expect(distribution?.segments).toHaveLength(3)
    expect(distribution?.segments[0]).toMatchObject({
      status: 'pending',
      count: 5,
      percent: 50,
      sweepDeg: 180,
    })
    expect(distribution?.segments[2]?.endDeg).toBe(360)
    expect(distribution?.gradient).toContain('conic-gradient(')
    expect(distribution?.gradient).toContain('#7fb4ff')
    expect(distribution?.gradient).toContain('#f2c572')
    expect(distribution?.gradient).toContain('#6fcf97')
  })
})
