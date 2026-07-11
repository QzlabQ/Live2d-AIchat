import type { VisitorRecommendation } from '../types/visitor'

export interface RecommendationCard {
  routeTitle: string
  intro: string
  highlights: string[]
  suggestedQuestions: string[]
  appliedInterestTags: string[]
}

const FALLBACK_QUESTION = '这条路线更适合什么时间段？'

function normalizeInterestTags(interestTags: string[]) {
  return interestTags.map((item) => item.trim()).filter((item) => item.length > 0)
}

export function assertRecommendationInterestTags(interestTags: string[]) {
  const normalized = normalizeInterestTags(interestTags)

  if (normalized.length === 0) {
    throw new Error('At least one non-empty interest tag is required.')
  }

  return normalized
}

export function mergeInterestTags(current: string[], incoming: string[]) {
  const merged = [...normalizeInterestTags(current), ...normalizeInterestTags(incoming)]
  return merged.filter((item, index) => merged.indexOf(item) === index)
}

export function normalizeRecommendationCard(payload: {
  route_title: string
  intro: string
  highlights: string[]
  suggested_questions: string[]
  applied_interest_tags: string[]
}): RecommendationCard
export function normalizeRecommendationCard(payload: VisitorRecommendation): RecommendationCard
export function normalizeRecommendationCard(
  payload:
    | VisitorRecommendation
    | {
        route_title: string
        intro: string
        highlights: string[]
        suggested_questions: string[]
        applied_interest_tags: string[]
      },
): RecommendationCard {
  const routeTitle = 'routeTitle' in payload ? payload.routeTitle : payload.route_title
  const suggestedQuestions =
    'suggestedQuestions' in payload ? payload.suggestedQuestions : payload.suggested_questions
  const appliedInterestTags =
    'appliedInterestTags' in payload ? payload.appliedInterestTags : payload.applied_interest_tags

  return {
    routeTitle,
    intro: payload.intro,
    highlights: payload.highlights,
    suggestedQuestions: suggestedQuestions.length > 0 ? suggestedQuestions : [FALLBACK_QUESTION],
    appliedInterestTags,
  }
}
