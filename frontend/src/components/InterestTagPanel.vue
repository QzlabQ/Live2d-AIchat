<script setup lang="ts">
import type { RecommendationCard } from '../lib/recommendationState'

const TAG_OPTIONS = ['历史文化', '亲子', '夜游', '轻松', '拍照打卡', '省力']

const props = withDefaults(
  defineProps<{
    selectedTags: string[]
    recommendation: RecommendationCard | null
    loading?: boolean
    saving?: boolean
    error?: string
    disabled?: boolean
    compact?: boolean
  }>(),
  {
    loading: false,
    saving: false,
    error: '',
    disabled: false,
    compact: false,
  },
)

const emit = defineEmits<{
  askQuestion: [question: string]
  refresh: []
  toggleTag: [tag: string]
}>()
</script>

<template>
  <section class="visitor-tool-card tag-panel" :class="{ 'tag-panel-compact': props.compact }">
    <div class="tool-card-head">
      <div>
        <p class="panel-kicker">Personalized Route</p>
        <h3>兴趣标签</h3>
      </div>
      <button
        class="ghost-button"
        type="button"
        :disabled="props.disabled || props.loading || props.saving"
        @click="emit('refresh')"
      >
        {{ props.loading ? '生成中...' : '生成路线' }}
      </button>
    </div>

    <div class="tag-grid">
      <button
        v-for="tag in TAG_OPTIONS"
        :key="tag"
        class="tag-chip"
        :class="{ active: props.selectedTags.includes(tag) }"
        type="button"
        :disabled="props.disabled || props.loading || props.saving"
        @click="emit('toggleTag', tag)"
      >
        {{ tag }}
      </button>
    </div>

    <p v-if="props.error" class="tool-error">{{ props.error }}</p>
  </section>
</template>
