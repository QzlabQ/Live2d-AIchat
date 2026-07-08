import { describe, expect, it } from 'vitest'

import { assertRecommendationInterestTags, normalizeRecommendationCard } from './recommendationState'

describe('normalizeRecommendationCard', () => {
  it('creates a stable fallback question list when the API returns none', () => {
    const card = normalizeRecommendationCard({
      route_title: '夜游路线',
      intro: '晚上适合先看亮灯再散步。',
      highlights: [],
      suggested_questions: [],
      applied_interest_tags: ['夜游'],
    })

    expect(card.suggestedQuestions.length).toBeGreaterThan(0)
  })
})

describe('assertRecommendationInterestTags', () => {
  it('keeps trimmed non-empty tags', () => {
    expect(assertRecommendationInterestTags([' 夜游 ', '亲子'])).toEqual(['夜游', '亲子'])
  })

  it('rejects empty or blank tag lists', () => {
    expect(() => assertRecommendationInterestTags([])).toThrow(
      'At least one non-empty interest tag is required.',
    )
    expect(() => assertRecommendationInterestTags(['   '])).toThrow(
      'At least one non-empty interest tag is required.',
    )
  })
})
