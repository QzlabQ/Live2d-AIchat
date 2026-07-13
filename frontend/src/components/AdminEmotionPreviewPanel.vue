<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import EmotionLamp from './EmotionLamp.vue'
import {
  EMOTION_EXPRESSION_MAP,
  EMOTION_PRESETS,
  EMOTION_VISUALS,
} from '../lib/lipsync'
import type { AvatarPresentation } from '../lib/avatarPresentation'
import type { EmotionStage, EmotionTelemetry, EmotionValue } from '../types/chat'

const emit = defineEmits<{
  preview: [presentation: AvatarPresentation]
}>()

const emotionOptions: Array<{
  value: EmotionValue
  label: string
  hint: string
}> = [
  { value: 'neutral', label: '中性', hint: '稳定、自然的默认待机状态。' },
  { value: 'happy', label: '愉快', hint: '适合欢迎、肯定和轻松讲解。' },
  { value: 'thinking', label: '思考', hint: '用于检索、组织答案和等待生成。' },
  { value: 'excited', label: '兴奋', hint: '强调亮点、彩蛋和强烈推荐。' },
  { value: 'sad', label: '克制', hint: '适合遗憾、限制说明和温和安抚。' },
]

const selectedEmotion = ref<EmotionValue>('neutral')
const selectedStage = ref<EmotionStage>('final')

const currentOption = computed(
  () => emotionOptions.find((option) => option.value === selectedEmotion.value) ?? emotionOptions[0],
)

const telemetry = computed<EmotionTelemetry>(() => ({
  value: selectedEmotion.value,
  stage: selectedStage.value,
  confidence: selectedStage.value === 'final' ? 0.92 : 0.68,
  keywords: [currentOption.value.label],
  reason: currentOption.value.hint,
  source: 'heuristic',
}))

const stageLabel = computed(() => (selectedStage.value === 'final' ? '最终' : '预览'))
const confidenceLabel = computed(() => `${Math.round(telemetry.value.confidence * 100)}%`)
const visual = computed(() => EMOTION_VISUALS[selectedEmotion.value] ?? EMOTION_VISUALS.neutral)
const expressionName = computed(() => EMOTION_EXPRESSION_MAP[selectedEmotion.value] ?? '默认参数')
const parameterEntries = computed(() => Object.entries(EMOTION_PRESETS[selectedEmotion.value] ?? {}))

watch(
  [selectedEmotion, selectedStage],
  ([emotion, emotionStage]) => {
    emit('preview', {
      phase: emotion === 'thinking' ? 'thinking' : 'idle',
      emotion,
      emotionStage,
      allowIdleMotion: false,
      motionIntensity: emotion === 'excited' ? 'light' : 'none',
      lipSyncActive: false,
      activeReplyId: null,
    })
  },
  { immediate: true },
)
</script>

<template>
  <section class="admin-emotion-preview">
    <div class="admin-panel-header">
      <div>
        <p class="admin-section-tag">情绪预览</p>
        <h3>表情 / 参数快速检查</h3>
      </div>
      <span class="admin-badge">{{ visual.label }}</span>
    </div>

    <div class="admin-emotion-preview-controls" aria-label="选择情绪">
      <button
        v-for="option in emotionOptions"
        :key="option.value"
        class="admin-emotion-chip"
        :class="{ active: selectedEmotion === option.value }"
        type="button"
        @click="selectedEmotion = option.value"
      >
        <strong>{{ option.label }}</strong>
        <span>{{ option.hint }}</span>
      </button>
    </div>

    <div class="admin-emotion-preview-controls" aria-label="选择阶段">
      <button
        class="admin-emotion-chip"
        :class="{ active: selectedStage === 'preview' }"
        type="button"
        @click="selectedStage = 'preview'"
      >
        <strong>预览</strong>
        <span>低置信度过渡态</span>
      </button>
      <button
        class="admin-emotion-chip"
        :class="{ active: selectedStage === 'final' }"
        type="button"
        @click="selectedStage = 'final'"
      >
        <strong>最终</strong>
        <span>稳定表情参数</span>
      </button>
    </div>

    <EmotionLamp
      :emotion-telemetry="telemetry"
      :stage-label="stageLabel"
      :confidence-label="confidenceLabel"
    />

    <div class="admin-emotion-preview-meta">
      <div>
        <span>Expression</span>
        <strong>{{ expressionName }}</strong>
      </div>
      <div>
        <span>Motion</span>
        <strong>{{ selectedEmotion === 'excited' ? 'light' : 'none' }}</strong>
      </div>
      <div>
        <span>Phase</span>
        <strong>{{ selectedEmotion === 'thinking' ? 'thinking' : 'idle' }}</strong>
      </div>
    </div>

    <dl class="admin-emotion-param-list">
      <div v-for="[name, value] in parameterEntries" :key="name">
        <dt>{{ name }}</dt>
        <dd>{{ Number(value).toFixed(2) }}</dd>
      </div>
    </dl>
  </section>
</template>
