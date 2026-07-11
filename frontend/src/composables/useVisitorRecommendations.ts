import { ref, type Ref } from 'vue'

import { normalizeRecommendationCard, mergeInterestTags } from '../lib/recommendationState'
import { fetchVisitorRecommendations, updateVisitorSessionInterestTags } from '../services/visitorApi'
import type { RecommendationCard } from '../lib/recommendationState'

export function useVisitorRecommendations(apiBaseUrl: string, sessionId: Ref<string | null>) {
  const selectedInterestTags = ref<string[]>([])
  const recommendation = ref<RecommendationCard | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')

  function setSelectedTags(tags: string[]) {
    selectedInterestTags.value = [...tags]
  }

  function clearRecommendation() {
    recommendation.value = null
  }

  async function toggleTag(tag: string) {
    if (!sessionId.value) {
      throw new Error('No active session.')
    }

    const previous = [...selectedInterestTags.value]
    const exists = previous.includes(tag)
    const next = exists ? previous.filter((item) => item !== tag) : mergeInterestTags(previous, [tag])

    saving.value = true
    error.value = ''
    selectedInterestTags.value = next
    recommendation.value = null

    try {
      await updateVisitorSessionInterestTags(apiBaseUrl, sessionId.value, next)
    } catch (caught) {
      selectedInterestTags.value = previous
      error.value = caught instanceof Error ? caught.message : '保存兴趣标签失败'
      throw caught
    } finally {
      saving.value = false
    }
  }

  async function refreshRecommendations(visitorProfile?: string) {
    if (!sessionId.value) {
      throw new Error('No active session.')
    }

    loading.value = true
    error.value = ''

    try {
      const payload = await fetchVisitorRecommendations(
        apiBaseUrl,
        sessionId.value,
        selectedInterestTags.value,
        visitorProfile,
      )
      recommendation.value = normalizeRecommendationCard(payload)
      return recommendation.value
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : '生成路线推荐失败'
      throw caught
    } finally {
      loading.value = false
    }
  }

  return {
    selectedInterestTags,
    recommendation,
    loading,
    saving,
    error,
    setSelectedTags,
    clearRecommendation,
    toggleTag,
    refreshRecommendations,
  }
}
