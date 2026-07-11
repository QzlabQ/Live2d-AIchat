<script setup lang="ts">
import { ref } from 'vue'

import type { VisionRecognitionResult } from '../types/visitor'

const props = withDefaults(
  defineProps<{
    busy?: boolean
    disabled?: boolean
    error?: string
    result?: VisionRecognitionResult | null
  }>(),
  {
    busy: false,
    disabled: false,
    error: '',
    result: null,
  },
)

const emit = defineEmits<{
  pick: [file: File]
}>()

const fileInputRef = ref<HTMLInputElement | null>(null)

function openFilePicker() {
  fileInputRef.value?.click()
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement | null
  const file = input?.files?.[0]
  if (!file) {
    return
  }

  emit('pick', file)
  input.value = ''
}
</script>

<template>
  <section class="visitor-tool-card photo-panel">
    <div class="tool-card-head">
      <div>
        <p class="panel-kicker">Photo Ask</p>
        <h3>拍照问景点</h3>
      </div>
      <button class="ghost-button" type="button" :disabled="props.disabled || props.busy" @click="openFilePicker">
        {{ props.busy ? '识别中...' : '上传照片' }}
      </button>
      <input
        ref="fileInputRef"
        class="photo-input"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        :disabled="props.disabled || props.busy"
        @change="handleFileChange"
      />
    </div>

    <p class="photo-note">上传游客拍到的景点照片，系统会识别景点并自动生成一个自然追问。</p>
    <p v-if="props.error" class="tool-error">{{ props.error }}</p>

    <div v-if="props.result" class="photo-result">
      <strong>{{ props.result.recognizedSpot }}</strong>
      <p>{{ props.result.recognitionSummary }}</p>
      <span>{{ props.result.resolvedQuestion }}</span>
    </div>
  </section>
</template>
