<script setup lang="ts">
const props = defineProps<{
  modelValue: string
  quickHints: string[]
  canSend: boolean
  canRecord: boolean
  isRecording: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: []
  toggleRecording: []
}>()

function updateValue(value: string) {
  emit('update:modelValue', value)
}

function applyHint(hint: string) {
  emit('update:modelValue', hint)
}
</script>

<template>
  <div class="composer-shell">
    <div class="quick-hints">
      <button
        v-for="hint in props.quickHints"
        :key="hint"
        type="button"
        class="hint-chip"
        @click="applyHint(hint)"
      >
        {{ hint }}
      </button>
    </div>

    <div class="composer-panel">
      <textarea
        :value="props.modelValue"
        class="composer-input"
        placeholder="输入你想问的问题，按 Enter 发送，Shift + Enter 换行"
        rows="4"
        @input="updateValue(($event.target as HTMLTextAreaElement).value)"
        @keydown.enter.exact.prevent="emit('send')"
      ></textarea>

      <div class="composer-footer">
        <div class="composer-actions">
          <button
            type="button"
            class="record-button"
            :class="{ active: props.isRecording }"
            :disabled="!props.canRecord"
            @click="emit('toggleRecording')"
          >
            {{ props.isRecording ? '停止录音' : '开始录音' }}
          </button>
          <button type="button" class="send-button" :disabled="!props.canSend" @click="emit('send')">
            发送文本
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
