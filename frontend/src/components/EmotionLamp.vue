<script setup lang="ts">
import { computed } from 'vue'

import { buildEmotionLampStyle } from '../lib/emotionLamp'
import { EMOTION_VISUALS } from '../lib/lipsync'
import type { EmotionTelemetry } from '../types/chat'

const props = defineProps<{
  emotionTelemetry: EmotionTelemetry
  stageLabel: string
  confidenceLabel: string
}>()

const emotionVisual = computed(
  () => EMOTION_VISUALS[props.emotionTelemetry.value] ?? EMOTION_VISUALS.neutral,
)

const emotionLampStyle = computed(() =>
  buildEmotionLampStyle(props.emotionTelemetry, emotionVisual.value),
)
</script>

<template>
  <div class="emotion-lamp-shell">
    <div
      class="emotion-lamp"
      :data-stage="emotionTelemetry.stage"
      :data-emotion="emotionTelemetry.value"
      :style="emotionLampStyle"
    >
      <span class="emotion-lamp-core"></span>
    </div>
    <div class="emotion-meta">
      <strong>{{ emotionVisual.label }}</strong>
      <span>阶段 {{ stageLabel }}</span>
      <span>置信度 {{ confidenceLabel }}</span>
      <span>来源 {{ emotionTelemetry.source }}</span>
    </div>
  </div>
  <p class="emotion-reason">{{ emotionTelemetry.reason }}</p>
  <p class="emotion-keywords">
    {{
      emotionTelemetry.keywords.length
        ? emotionTelemetry.keywords.join(' / ')
        : '暂无显著情绪关键词'
    }}
  </p>
</template>
