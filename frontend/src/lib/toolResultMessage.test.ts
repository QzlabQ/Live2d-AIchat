import { describe, expect, it, vi } from 'vitest'

import { buildRouteRecommendationMessage } from './toolResultMessage'

describe('buildRouteRecommendationMessage', () => {
  it('builds an assistant tool result message from a recommendation card', () => {
    vi.spyOn(Date, 'now').mockReturnValue(1700000000000)
    vi.spyOn(Math, 'random').mockReturnValue(0.5)

    const message = buildRouteRecommendationMessage({
      routeTitle: '亲子轻松路线',
      intro: '先看核心演出，再去互动展区。',
      highlights: ['主秀舞台', '亲子互动区'],
      suggestedQuestions: ['这条路线适合玩多久？', '晚上还能继续逛吗？'],
      appliedInterestTags: ['亲子', '轻松'],
    })

    expect(message).toEqual({
      id: 'tool-route-recommendation-1700000000000-8',
      role: 'assistant',
      content: [
        '亲子轻松路线',
        '先看核心演出，再去互动展区。',
        '推荐亮点：主秀舞台；亲子互动区',
        '你还可以继续问：这条路线适合玩多久？；晚上还能继续逛吗？',
      ].join('\n'),
      meta: '路线推荐',
      toolResult: {
        kind: 'route_recommendation',
        routeTitle: '亲子轻松路线',
        intro: '先看核心演出，再去互动展区。',
        highlights: ['主秀舞台', '亲子互动区'],
        suggestedQuestions: ['这条路线适合玩多久？', '晚上还能继续逛吗？'],
        appliedInterestTags: ['亲子', '轻松'],
      },
    })
  })

  it('copies arrays so the message payload stays stable after source mutation', () => {
    const recommendation = {
      routeTitle: '夜游路线',
      intro: '先看灯光秀，再散步拍照。',
      highlights: ['灯光秀'],
      suggestedQuestions: ['几点开始比较合适？'],
      appliedInterestTags: ['夜游'],
    }

    const message = buildRouteRecommendationMessage(recommendation)
    recommendation.highlights.push('观景平台')
    recommendation.suggestedQuestions.push('适合老人吗？')
    recommendation.appliedInterestTags.push('拍照')

    expect(message.toolResult).toEqual({
      kind: 'route_recommendation',
      routeTitle: '夜游路线',
      intro: '先看灯光秀，再散步拍照。',
      highlights: ['灯光秀'],
      suggestedQuestions: ['几点开始比较合适？'],
      appliedInterestTags: ['夜游'],
    })
  })
})
