import type { RecommendationCard } from './recommendationState'

export type ComposerMode = 'chat' | 'route'

const DEFAULT_CHAT_HINTS = [
  '这里有什么历史故事？',
  '第一次来应该怎么逛？',
  '开放时间是什么时候？',
]

const DEFAULT_ROUTE_HINTS = [
  '第一次来适合先去哪里？',
  '半天路线怎么走更顺？',
  '晚上适合重点看什么？',
]

export function buildComposerQuickHints(
  mode: ComposerMode,
  options: {
    selectedTags: string[]
    recommendation: RecommendationCard | null
  },
) {
  if (mode === 'chat') {
    return DEFAULT_CHAT_HINTS
  }

  if (options.recommendation?.suggestedQuestions?.length) {
    return options.recommendation.suggestedQuestions
  }

  const tags = options.selectedTags.map((item) => item.trim()).filter((item) => item.length > 0)
  if (tags.length === 0) {
    return DEFAULT_ROUTE_HINTS
  }

  return [
    `按${tags.slice(0, 2).join(' / ')}偏好怎么安排路线？`,
    '第一次来适合先去哪里？',
    '半天路线怎么走更顺？',
  ]
}
