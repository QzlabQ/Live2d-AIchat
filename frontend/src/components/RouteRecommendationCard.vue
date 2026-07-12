<script setup lang="ts">
import type { RouteRecommendationToolResult } from '../types/chat'

const props = defineProps<{
  toolResult: RouteRecommendationToolResult
}>()

const emit = defineEmits<{
  ask: [question: string]
}>()

function askQuestion(question: string) {
  const normalized = question.trim()

  if (!normalized) {
    return
  }

  emit('ask', normalized)
}
</script>

<template>
  <section class="route-card" aria-label="路线推荐卡片">
    <header class="route-card__header">
      <p class="route-card__eyebrow">Route Recommendation</p>
      <h3 class="route-card__title">{{ props.toolResult.routeTitle }}</h3>
    </header>

    <p class="route-card__intro">{{ props.toolResult.intro }}</p>

    <div v-if="props.toolResult.highlights.length" class="route-card__section">
      <p class="route-card__label">路线亮点</p>
      <div class="route-card__pills">
        <span
          v-for="highlight in props.toolResult.highlights"
          :key="highlight"
          class="route-card__pill route-card__pill--highlight"
        >
          {{ highlight }}
        </span>
      </div>
    </div>

    <div v-if="props.toolResult.appliedInterestTags.length" class="route-card__section">
      <p class="route-card__label">匹配兴趣</p>
      <div class="route-card__pills">
        <span
          v-for="tag in props.toolResult.appliedInterestTags"
          :key="tag"
          class="route-card__pill route-card__pill--interest"
        >
          {{ tag }}
        </span>
      </div>
    </div>

    <div v-if="props.toolResult.suggestedQuestions.length" class="route-card__section">
      <p class="route-card__label">建议追问</p>
      <div class="route-card__actions">
        <button
          v-for="question in props.toolResult.suggestedQuestions"
          :key="question"
          class="route-card__question"
          type="button"
          @click="askQuestion(question)"
        >
          {{ question }}
        </button>
      </div>
    </div>
  </section>
</template>
