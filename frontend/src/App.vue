<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import Live2DStage from './components/Live2DStage.vue'
import { useAudioRecorder } from './composables/useAudioRecorder'
import { useChatSocket } from './composables/useChatSocket'
import { base64ToBlobUrl } from './lib/base64'
import type {
  AudioEvent,
  ChatMessage,
  EmotionEvent,
  EmotionValue,
  PhonemeFrame,
  PhonemesEvent,
  ServerSocketMessage,
} from './types/chat'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1'
const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://127.0.0.1:8000'
const MODEL_PATH =
  import.meta.env.VITE_LIVE2D_MODEL_PATH || '/live2d/haru/haru_greeter_t03.model3.json'
const HEARTBEAT_MS = Number(import.meta.env.VITE_HEARTBEAT_MS || 15000)
const RECONNECT_BASE_MS = Number(import.meta.env.VITE_RECONNECT_BASE_MS || 1200)

const QUICK_HINTS = [
  '这里有什么历史故事？',
  '第一次来应该怎么游览？',
  '开放时间是什么时候？',
]

function createWelcomeMessage(): ChatMessage {
  return {
    id: 'welcome',
    role: 'assistant',
    content: '欢迎来到景区 AI 数字人演示。你可以直接输入问题，或点击麦克风开始语音对话。',
  }
}

interface QueuedAudio {
  seq: number
  url: string
}

const live2dRef = ref<InstanceType<typeof Live2DStage> | null>(null)
const chatBodyRef = ref<HTMLDivElement | null>(null)

const sessionId = ref<string | null>(null)
const sessionBooting = ref(false)
const bootError = ref('')
const composer = ref('')
const messages = ref<ChatMessage[]>([createWelcomeMessage()])
const assistantDraftId = ref<string | null>(null)
const lastAsrPreview = ref('')
const latestEmotion = ref<EmotionValue>('neutral')
const playbackError = ref('')

const queuedAudio = ref<QueuedAudio[]>([])
const knownAudioSeqs = new Set<number>()
const pendingPhonemes = new Map<number, PhonemeFrame[]>()
const phonemeFallbackTimers = new Map<number, number>()
let currentAudio: HTMLAudioElement | null = null
let audioPlaying = false

function createMessageId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
}

function resetReplyMediaState() {
  for (const timer of phonemeFallbackTimers.values()) {
    window.clearTimeout(timer)
  }

  phonemeFallbackTimers.clear()
  knownAudioSeqs.clear()
  pendingPhonemes.clear()
  currentAudio?.pause()
  currentAudio = null
  audioPlaying = false
  queuedAudio.value.forEach((item) => URL.revokeObjectURL(item.url))
  queuedAudio.value = []
  playbackError.value = ''
}

function resetConversation() {
  messages.value = [createWelcomeMessage()]
  assistantDraftId.value = null
  lastAsrPreview.value = ''
  latestEmotion.value = 'neutral'
  composer.value = ''
  resetReplyMediaState()
}

function pushSystemMessage(content: string) {
  messages.value.push({
    id: createMessageId('system'),
    role: 'system',
    content,
  })
}

async function scrollChatToEnd() {
  await nextTick()
  const chatBody = chatBodyRef.value
  if (!chatBody) {
    return
  }

  chatBody.scrollTop = chatBody.scrollHeight
}

function ensureAssistantDraft() {
  if (assistantDraftId.value) {
    return assistantDraftId.value
  }

  const id = createMessageId('assistant')
  assistantDraftId.value = id
  messages.value.push({
    id,
    role: 'assistant',
    content: '',
    streaming: true,
  })
  return id
}

function finalizeAssistantDraft() {
  if (!assistantDraftId.value) {
    return
  }

  const target = messages.value.find((message) => message.id === assistantDraftId.value)
  if (target) {
    target.streaming = false
  }

  assistantDraftId.value = null
}

async function createSession() {
  if (sessionBooting.value) {
    return
  }

  sessionBooting.value = true
  bootError.value = ''

  try {
    const response = await fetch(`${API_BASE_URL}/sessions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        interest_tags: ['history', 'nature'],
        device_type: 'mobile',
      }),
    })

    if (!response.ok) {
      throw new Error(`Session create failed: ${response.status}`)
    }

    const payload = (await response.json()) as { session_id: string }
    resetConversation()
    sessionId.value = payload.session_id
    pushSystemMessage(`已创建新会话：${payload.session_id}`)
  } catch (error) {
    bootError.value = error instanceof Error ? error.message : '创建会话失败。'
  } finally {
    sessionBooting.value = false
  }
}

function clearPhonemeFallback(seq: number) {
  const timer = phonemeFallbackTimers.get(seq)
  if (timer !== undefined) {
    window.clearTimeout(timer)
    phonemeFallbackTimers.delete(seq)
  }
}

function queueFallbackLipSync(seq: number, frames: PhonemeFrame[]) {
  clearPhonemeFallback(seq)
  const timer = window.setTimeout(() => {
    if (!knownAudioSeqs.has(seq)) {
      live2dRef.value?.playPhonemes(frames)
    }
  }, 140)

  phonemeFallbackTimers.set(seq, timer)
}

async function playNextAudio() {
  if (audioPlaying || queuedAudio.value.length === 0) {
    return
  }

  const nextAudio = queuedAudio.value.shift()
  if (!nextAudio) {
    return
  }

  audioPlaying = true
  clearPhonemeFallback(nextAudio.seq)

  const phonemes = pendingPhonemes.get(nextAudio.seq)
  if (phonemes) {
    live2dRef.value?.playPhonemes(phonemes)
    pendingPhonemes.delete(nextAudio.seq)
  }

  currentAudio = new Audio(nextAudio.url)
  currentAudio.preload = 'auto'

  const release = () => {
    URL.revokeObjectURL(nextAudio.url)
    currentAudio = null
    audioPlaying = false
    void playNextAudio()
  }

  currentAudio.onended = release
  currentAudio.onerror = () => {
    playbackError.value = '音频播放失败，已降级为口型动画。'
    release()
  }

  try {
    await currentAudio.play()
  } catch (error) {
    playbackError.value =
      error instanceof Error ? error.message : '浏览器阻止了自动播放，请先进行一次页面交互。'
    release()
  }
}

function handleAudio(payload: AudioEvent) {
  knownAudioSeqs.add(payload.seq)
  queuedAudio.value.push({
    seq: payload.seq,
    url: base64ToBlobUrl(payload.data, 'audio/mpeg'),
  })
  void playNextAudio()
}

function handlePhonemes(payload: PhonemesEvent) {
  pendingPhonemes.set(payload.seq, payload.data)
  queueFallbackLipSync(payload.seq, payload.data)
}

function handleEmotion(payload: EmotionEvent) {
  latestEmotion.value = payload.value
}

function handleSocketMessage(payload: ServerSocketMessage) {
  if (payload.type === 'text_delta') {
    const draftId = ensureAssistantDraft()
    const target = messages.value.find((message) => message.id === draftId)
    if (target) {
      target.content += payload.content
    }
    void scrollChatToEnd()
    return
  }

  if (payload.type === 'asr_result') {
    lastAsrPreview.value = payload.content
    messages.value.push({
      id: createMessageId('user-voice'),
      role: 'user',
      content: payload.content,
      meta: '语音识别',
    })
    void scrollChatToEnd()
    return
  }

  if (payload.type === 'audio') {
    handleAudio(payload)
    return
  }

  if (payload.type === 'phonemes') {
    handlePhonemes(payload)
    return
  }

  if (payload.type === 'emotion') {
    handleEmotion(payload)
    return
  }

  if (payload.type === 'done') {
    finalizeAssistantDraft()
    void scrollChatToEnd()
  }
}

function handleSocketError(message: string) {
  pushSystemMessage(message)
  finalizeAssistantDraft()
  void scrollChatToEnd()
}

const socket = useChatSocket({
  sessionId,
  baseUrl: WS_BASE_URL,
  heartbeatMs: HEARTBEAT_MS,
  reconnectBaseMs: RECONNECT_BASE_MS,
  onMessage: handleSocketMessage,
  onError: handleSocketError,
})

const recorder = useAudioRecorder({
  onChunk: ({ data, isFinal }) => {
    const sent = socket.send({
      type: 'audio_chunk',
      data,
      is_final: isFinal,
    })

    if (!sent) {
      handleSocketError('语音分片发送失败，当前连接不可用。')
    }
  },
  onAudioEnd: () => {
    const sent = socket.send({ type: 'audio_end' })
    if (!sent) {
      handleSocketError('语音结束信号发送失败，当前连接不可用。')
    }
  },
  onError: handleSocketError,
})

const canSend = computed(
  () => socket.state.value === 'connected' && composer.value.trim().length > 0 && !sessionBooting.value,
)
const canRecord = computed(
  () => recorder.isSupported.value && socket.state.value === 'connected' && !sessionBooting.value,
)
const meterScale = computed(() => Math.max(0.05, recorder.level.value))

const connectionLabel = computed(() => {
  switch (socket.state.value) {
    case 'connected':
      return '已连接'
    case 'connecting':
      return '连接中'
    case 'reconnecting':
      return '重连中'
    case 'error':
      return '连接异常'
    case 'disconnected':
      return '已断开'
    default:
      return '待连接'
  }
})

async function sendText() {
  const content = composer.value.trim()
  if (!content) {
    return
  }

  if (socket.state.value !== 'connected') {
    handleSocketError('当前 WebSocket 尚未连接，暂时无法发送消息。')
    return
  }

  messages.value.push({
    id: createMessageId('user'),
    role: 'user',
    content,
  })

  resetReplyMediaState()
  composer.value = ''
  finalizeAssistantDraft()

  const sent = socket.send({ type: 'text', content })
  if (!sent) {
    handleSocketError('文本消息发送失败，请稍后重试。')
  }

  await scrollChatToEnd()
}

async function toggleRecording() {
  if (recorder.isRecording.value) {
    recorder.stop()
    return
  }

  if (socket.state.value !== 'connected') {
    handleSocketError('连接尚未就绪，请稍后再开始录音。')
    return
  }

  resetReplyMediaState()
  finalizeAssistantDraft()
  await recorder.start()
}

async function reconnectNow() {
  if (!sessionId.value) {
    await createSession()
    return
  }

  socket.disconnect()
  await nextTick()
  await socket.connect()
}

watch([latestEmotion, live2dRef], ([emotion, stage]) => {
  stage?.setEmotion(emotion)
}, { immediate: true })

onMounted(async () => {
  await createSession()
  await scrollChatToEnd()
})

onBeforeUnmount(() => {
  resetReplyMediaState()
})
</script>

<template>
  <div class="app-shell">
    <div class="aurora aurora-left"></div>
    <div class="aurora aurora-right"></div>

    <header class="topbar">
      <div>
        <p class="eyebrow">Phase 1 Visitor Demo</p>
        <h1>景区 AI 数字人导览台</h1>
        <p class="subtitle">
          已接入示例 Live2D 模型、文本与语音输入、WebSocket 流式对话，以及基础口型驱动链路。
        </p>
      </div>
      <div class="topbar-meta">
        <div class="meta-chip">
          <span class="meta-label">会话</span>
          <strong>{{ sessionId ?? '准备中...' }}</strong>
        </div>
        <div class="meta-chip">
          <span class="meta-label">连接</span>
          <strong>{{ connectionLabel }}</strong>
        </div>
      </div>
    </header>

    <main class="workspace">
      <section class="stage-panel panel">
        <div class="panel-header">
          <div>
            <p class="panel-kicker">Live2D Avatar</p>
            <h2>数字人舞台</h2>
          </div>
          <div class="panel-statuses">
            <span class="status-pill" :data-tone="socket.state.value">{{ connectionLabel }}</span>
            <span class="status-pill" :data-tone="recorder.isRecording.value ? 'recording' : 'idle'">
              {{ recorder.isRecording.value ? '录音中' : '待命' }}
            </span>
          </div>
        </div>

        <div class="stage-card">
          <Live2DStage ref="live2dRef" :model-path="MODEL_PATH" />
          <div class="stage-caption">
            <div>
              <span class="caption-label">情绪映射</span>
              <strong>{{ latestEmotion }}</strong>
            </div>
            <div>
              <span class="caption-label">模型路径</span>
              <strong class="mono">{{ MODEL_PATH }}</strong>
            </div>
          </div>
        </div>

        <div class="telemetry-grid">
          <article class="telemetry-card">
            <span class="telemetry-label">麦克风电平</span>
            <div class="meter">
              <span class="meter-fill" :style="{ transform: `scaleX(${meterScale})` }"></span>
            </div>
          </article>
          <article class="telemetry-card">
            <span class="telemetry-label">识别回显</span>
            <p>{{ lastAsrPreview || '开始录音后会在这里显示 ASR 文本。' }}</p>
          </article>
        </div>
      </section>

      <section class="chat-panel panel">
        <div class="panel-header">
          <div>
            <p class="panel-kicker">Realtime Channel</p>
            <h2>游客对话台</h2>
          </div>
          <div class="header-actions">
            <button class="ghost-button" type="button" @click="reconnectNow">手动重连</button>
            <button class="ghost-button" type="button" @click="createSession">新建会话</button>
          </div>
        </div>

        <p v-if="bootError" class="banner banner-error">{{ bootError }}</p>
        <p v-else-if="playbackError" class="banner banner-warn">{{ playbackError }}</p>

        <div ref="chatBodyRef" class="chat-body">
          <article
            v-for="message in messages"
            :key="message.id"
            class="bubble"
            :class="`bubble-${message.role}`"
          >
            <header class="bubble-head">
              <span>{{
                message.role === 'assistant' ? '导览助手' : message.role === 'user' ? '游客' : '系统'
              }}</span>
              <span v-if="message.meta">{{ message.meta }}</span>
            </header>
            <p class="bubble-content">
              {{ message.content }}
              <span v-if="message.streaming" class="cursor">|</span>
            </p>
          </article>
        </div>

        <div class="quick-hints">
          <button
            v-for="hint in QUICK_HINTS"
            :key="hint"
            type="button"
            class="hint-chip"
            @click="composer = hint"
          >
            {{ hint }}
          </button>
        </div>

        <div class="composer-panel">
          <textarea
            v-model="composer"
            class="composer-input"
            placeholder="输入你想问的问题，按 Enter 发送，Shift + Enter 换行"
            rows="4"
            @keydown.enter.exact.prevent="sendText"
          ></textarea>

          <div class="composer-footer">
            <div class="support-text">
              <span>后端接口：{{ API_BASE_URL }}</span>
              <span>WebSocket：{{ WS_BASE_URL }}</span>
            </div>

            <div class="composer-actions">
              <button
                type="button"
                class="record-button"
                :class="{ active: recorder.isRecording.value }"
                :disabled="!canRecord"
                @click="toggleRecording"
              >
                {{ recorder.isRecording.value ? '停止录音' : '开始录音' }}
              </button>
              <button type="button" class="send-button" :disabled="!canSend" @click="sendText">
                发送文本
              </button>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>
