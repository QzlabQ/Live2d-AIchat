import type { RecommendationCard } from './recommendationState'
import type { ChatMessage, RouteRecommendationToolResult } from '../types/chat'

function buildRouteRecommendationContent(recommendation: RecommendationCard) {
  const sections = [
    recommendation.routeTitle,
    recommendation.intro,
    recommendation.highlights.length > 0
      ? `推荐亮点：${recommendation.highlights.join('；')}`
      : '',
    recommendation.suggestedQuestions.length > 0
      ? `你还可以继续问：${recommendation.suggestedQuestions.join('；')}`
      : '',
  ]

  return sections.filter((section) => section.trim().length > 0).join('\n')
}

function createRouteRecommendationToolResult(
  recommendation: RecommendationCard,
): RouteRecommendationToolResult {
  return {
    kind: 'route_recommendation',
    routeTitle: recommendation.routeTitle,
    intro: recommendation.intro,
    highlights: [...recommendation.highlights],
    suggestedQuestions: [...recommendation.suggestedQuestions],
    appliedInterestTags: [...recommendation.appliedInterestTags],
  }
}

export function buildRouteRecommendationMessage(recommendation: RecommendationCard): ChatMessage {
  return {
    id: `tool-route-recommendation-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    role: 'assistant',
    content: buildRouteRecommendationContent(recommendation),
    meta: '路线推荐',
    toolResult: createRouteRecommendationToolResult(recommendation),
  }
}
