<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

import InterestTagPanel from './InterestTagPanel.vue'
import type { ComposerMode } from '../lib/chatComposerMode'

const props = withDefaults(
  defineProps<{
    modelValue: string
    quickHints: string[]
    canSend: boolean
    canRecord: boolean
    isRecording: boolean
    composerMode?: ComposerMode
    canAttachPhoto?: boolean
    canToggleRouteMode?: boolean
    photoBusy?: boolean
    photoStatusTitle?: string
    photoStatusDetail?: string
    photoError?: string
    routeSelectedTags?: string[]
    routeLoading?: boolean
    routeSaving?: boolean
    routeError?: string
    routeDisabled?: boolean
  }>(),
  {
    composerMode: 'chat',
    canAttachPhoto: false,
    canToggleRouteMode: false,
    photoBusy: false,
    photoStatusTitle: '',
    photoStatusDetail: '',
    photoError: '',
    routeSelectedTags: () => [],
    routeLoading: false,
    routeSaving: false,
    routeError: '',
    routeDisabled: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  switchMode: [mode: ComposerMode]
  pickPhoto: [file: File]
  send: []
  toggleRecording: []
  toggleRouteTag: [tag: string]
  generateRoute: []
}>()

const attachmentRootRef = ref<HTMLDivElement | null>(null)
const attachmentMenuOpen = ref(false)
const photoInputRef = ref<HTMLInputElement | null>(null)

function updateValue(value: string) {
  emit('update:modelValue', value)
}

function applyHint(hint: string) {
  emit('update:modelValue', hint)
}

function toggleAttachmentMenu() {
  if ((!props.canAttachPhoto && !props.canToggleRouteMode) || props.photoBusy) {
    return
  }

  attachmentMenuOpen.value = !attachmentMenuOpen.value
}

function openPhotoPicker() {
  if (!props.canAttachPhoto || props.photoBusy) {
    return
  }

  attachmentMenuOpen.value = false
  photoInputRef.value?.click()
}

function handlePhotoChange(event: Event) {
  const input = event.target as HTMLInputElement | null
  const file = input?.files?.[0]
  if (!file) {
    return
  }

  emit('pickPhoto', file)
  input.value = ''
}

function switchMode(mode: ComposerMode) {
  attachmentMenuOpen.value = false
  emit('switchMode', mode)
}

function emitGenerateRoute() {
  emit('generateRoute')
}

function closeAttachmentMenuOnOutsidePointer(event: PointerEvent) {
  if (!attachmentMenuOpen.value) {
    return
  }

  const host = attachmentRootRef.value
  if (host && event.target instanceof Node && !host.contains(event.target)) {
    attachmentMenuOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('pointerdown', closeAttachmentMenuOnOutsidePointer)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', closeAttachmentMenuOnOutsidePointer)
})
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

    <div v-if="props.composerMode === 'route'" class="composer-mode-banner" data-mode="route">
      <div class="composer-mode-banner-head">
        <div class="composer-mode-banner-copy">
          <strong>路线推荐模式</strong>
          <p>先选兴趣标签，再手动生成路线；不会自动替你提交请求。</p>
        </div>
        <button type="button" class="ghost-button" @click="switchMode('chat')">退出路线模式</button>
      </div>

      <InterestTagPanel
        :selected-tags="props.routeSelectedTags"
        :recommendation="null"
        :loading="props.routeLoading"
        :saving="props.routeSaving"
        :error="props.routeError"
        :disabled="props.routeDisabled"
        compact
        @toggle-tag="emit('toggleRouteTag', $event)"
        @refresh="emitGenerateRoute"
      />
    </div>

    <div class="composer-panel">
      <div
        v-if="props.photoBusy || props.photoError || props.photoStatusTitle"
        class="composer-attachment-banner"
        :data-tone="props.photoError ? 'error' : props.photoBusy ? 'busy' : 'ready'"
      >
        <strong>{{ props.photoBusy ? '正在识别景点照片' : props.photoError || props.photoStatusTitle }}</strong>
        <span>
          {{
            props.photoBusy
              ? '识别完成后会自动生成追问并发到当前会话。'
              : props.photoError || props.photoStatusDetail
          }}
        </span>
      </div>

      <textarea
        :value="props.modelValue"
        class="composer-input"
        placeholder="输入你想问的问题，按 Enter 发送，Shift + Enter 换行"
        rows="4"
        @input="updateValue(($event.target as HTMLTextAreaElement).value)"
        @keydown.enter.exact.prevent="emit('send')"
      ></textarea>

      <div class="composer-footer">
        <div ref="attachmentRootRef" class="composer-entry-tools">
          <button
            type="button"
            class="attach-button"
            :disabled="(!props.canAttachPhoto && !props.canToggleRouteMode) || props.photoBusy"
            @click="toggleAttachmentMenu"
          >
            +
          </button>

          <transition name="attach-pop">
            <div v-if="attachmentMenuOpen" class="attach-menu">
              <button
                v-if="props.canToggleRouteMode"
                type="button"
                class="attach-menu-item"
                @click="switchMode(props.composerMode === 'route' ? 'chat' : 'route')"
              >
                <span class="attach-menu-title">
                  {{ props.composerMode === 'route' ? '返回普通对话' : '切换路线推荐' }}
                </span>
                <span class="attach-menu-desc">
                  {{ props.composerMode === 'route' ? '恢复常规快捷提问' : '显示兴趣标签与路线快捷问题' }}
                </span>
              </button>

              <button
                v-if="props.canAttachPhoto"
                type="button"
                class="attach-menu-item"
                :disabled="!props.canAttachPhoto || props.photoBusy"
                @click="openPhotoPicker"
              >
                <span class="attach-menu-title">上传景点照片</span>
                <span class="attach-menu-desc">识别景点后自动帮你发问</span>
              </button>
            </div>
          </transition>

          <input
            ref="photoInputRef"
            class="photo-input"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            :disabled="!props.canAttachPhoto || props.photoBusy"
            @change="handlePhotoChange"
          />
        </div>

        <div class="composer-actions">
          <span class="composer-mode-chip" :data-mode="props.composerMode">
            {{ props.composerMode === 'route' ? '路线模式' : '对话模式' }}
          </span>
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
