<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import Live2DStage from './components/Live2DStage.vue'
import { useAudioRecorder } from './composables/useAudioRecorder'
import { useChatSocket } from './composables/useChatSocket'
import { base64ToBlobUrl, base64ToUint8Array } from './lib/base64'
import { EMOTION_VISUALS } from './lib/lipsync'
import {
  DEFAULT_STREAM_AUDIO_POLICY,
  getScheduledLeadMs,
  shouldResetBufferedPlayback,
  shouldStartBufferedPlayback,
} from './lib/streamAudioBuffer'
import type {
  AudioEvent,
  ChatMessage,
  EmotionEvent,
  EmotionTelemetry,
  EmotionValue,
  PhonemeFrame,
  PhonemesEvent,
  ServerSocketMessage,
  TtsAudioChunkEvent,
  TtsVisemeChunkEvent,
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
    content: '欢迎来到景区 AI 数字人演示。你可以直接输入问题，或点击麦克风开始语音对话。当前页面已经接入表情映射与调试面板。',
  }
}

function createDefaultEmotionTelemetry(): EmotionTelemetry {
  return {
    value: 'neutral',
    confidence: 0.45,
    keywords: [],
    reason: '等待新一轮回答时，保持中性待机状态。',
    source: 'heuristic',
  }
}

interface QueuedAudio {
  seq: number
  url: string
}

interface ScheduledSource {
  key: string
  source: AudioBufferSourceNode
}

interface BufferedStreamAudio {
  payload: TtsAudioChunkEvent
  samples: Float32Array
  durationMs: number
}

type AudioContextWindow = Window &
  typeof globalThis & {
    webkitAudioContext?: typeof AudioContext
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
const emotionTelemetry = ref<EmotionTelemetry>(createDefaultEmotionTelemetry())
const playbackError = ref('')
const playbackTelemetry = ref({
  bufferedAudioMs: 0,
  scheduledLeadMs: 0,
  underrunCount: 0,
})

const queuedAudio = ref<QueuedAudio[]>([])
const knownAudioSeqs = new Set<number>()
const pendingPhonemes = new Map<number, PhonemeFrame[]>()
const phonemeFallbackTimers = new Map<number, number>()
const failedAudioSeqs = new Set<number>()
const pendingStreamVisemes = new Map<string, TtsVisemeChunkEvent>()
const streamChunkSchedule = new Map<string, number>()
let currentAudio: HTMLAudioElement | null = null
let currentAudioSeq: number | null = null
let audioPlaying = false
let audioUnlockContext: AudioContext | null = null
let audioUnlocked = false
let activeStreamReplyId: string | null = null
let streamNextStartTime = 0
let scheduledSources: ScheduledSource[] = []
let pendingStreamAudio: BufferedStreamAudio[] = []
let streamPlaybackStarted = false

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
  failedAudioSeqs.clear()
  currentAudio?.pause()
  currentAudio = null
  currentAudioSeq = null
  audioPlaying = false
  activeStreamReplyId = null
  streamNextStartTime = 0
  streamPlaybackStarted = false
  pendingStreamAudio = []
  pendingStreamVisemes.clear()
  streamChunkSchedule.clear()
  scheduledSources.forEach(({ source }) => {
    try {
      source.stop()
    } catch {
      return
    }
  })
  scheduledSources = []
  queuedAudio.value.forEach((item) => URL.revokeObjectURL(item.url))
  queuedAudio.value = []
  playbackError.value = ''
  playbackTelemetry.value = {
    bufferedAudioMs: 0,
    scheduledLeadMs: 0,
    underrunCount: 0,
  }
}

function resetConversation() {
  messages.value = [createWelcomeMessage()]
  assistantDraftId.value = null
  lastAsrPreview.value = ''
  latestEmotion.value = 'neutral'
  emotionTelemetry.value = createDefaultEmotionTelemetry()
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

async function unlockAudioPlayback() {
  if (audioUnlocked) {
    return
  }

  const AudioContextCtor = window.AudioContext ?? (window as AudioContextWindow).webkitAudioContext
  if (!AudioContextCtor) {
    return
  }

  try {
    const context = audioUnlockContext ?? new AudioContextCtor()
    audioUnlockContext = context
    if (context.state === 'suspended') {
      await context.resume()
    }

    const source = context.createBufferSource()
    const gain = context.createGain()
    gain.gain.value = 0
    source.buffer = context.createBuffer(1, 1, context.sampleRate)
    source.connect(gain).connect(context.destination)
    source.start(0)
    audioUnlocked = true
  } catch {
    audioUnlocked = false
  }
}

async function getAudioContext(): Promise<AudioContext | null> {
  await unlockAudioPlayback()
  if (!audioUnlockContext) {
    const AudioContextCtor = window.AudioContext ?? (window as AudioContextWindow).webkitAudioContext
    if (!AudioContextCtor) {
      return null
    }
    audioUnlockContext = new AudioContextCtor()
  }
  if (audioUnlockContext.state === 'suspended') {
    await audioUnlockContext.resume()
  }
  return audioUnlockContext
}

function playPhonemeFallbackNow(seq: number) {
  knownAudioSeqs.delete(seq)
  const frames = pendingPhonemes.get(seq)
  if (!frames) {
    failedAudioSeqs.add(seq)
    return
  }

  live2dRef.value?.playPhonemes(frames)
  pendingPhonemes.delete(seq)
  failedAudioSeqs.delete(seq)
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
  currentAudio = new Audio(nextAudio.url)
  currentAudioSeq = nextAudio.seq
  currentAudio.preload = 'auto'
  currentAudio.volume = 1
  currentAudio.setAttribute('playsinline', 'true')

  const release = () => {
    URL.revokeObjectURL(nextAudio.url)
    currentAudio = null
    currentAudioSeq = null
    audioPlaying = false
    void playNextAudio()
  }

  currentAudio.onended = release
  currentAudio.onerror = () => {
    playbackError.value = '音频播放失败，已降级为口型动画。'
    playPhonemeFallbackNow(nextAudio.seq)
    release()
  }

  try {
    currentAudio.load()
    await currentAudio.play()
    const latestPhonemes = pendingPhonemes.get(nextAudio.seq) ?? phonemes
    if (latestPhonemes) {
      live2dRef.value?.playPhonemes(latestPhonemes, currentAudio)
      pendingPhonemes.delete(nextAudio.seq)
    }
  } catch (error) {
    playbackError.value =
      error instanceof Error ? error.message : '浏览器阻止了自动播放，请先进行一次页面交互。'
    playPhonemeFallbackNow(nextAudio.seq)
    release()
  }
}

function handleAudio(payload: AudioEvent) {
  knownAudioSeqs.add(payload.seq)
  failedAudioSeqs.delete(payload.seq)
  queuedAudio.value.push({
    seq: payload.seq,
    url: base64ToBlobUrl(payload.data, payload.mime_type || 'audio/mpeg'),
  })
  void playNextAudio()
}

function handlePhonemes(payload: PhonemesEvent) {
  pendingPhonemes.set(payload.seq, payload.data)
  if (failedAudioSeqs.has(payload.seq)) {
    playPhonemeFallbackNow(payload.seq)
    return
  }

  if (currentAudio && currentAudioSeq === payload.seq) {
    live2dRef.value?.playPhonemes(payload.data, currentAudio)
    return
  }
  queueFallbackLipSync(payload.seq, payload.data)
}

function streamChunkKey(payload: { reply_id: string; segment_id: number; chunk_index: number }) {
  return `${payload.reply_id}:${payload.segment_id}:${payload.chunk_index}`
}

function pcm16ToFloat32(bytes: Uint8Array) {
  const sampleCount = Math.floor(bytes.byteLength / 2)
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const samples = new Float32Array(sampleCount)

  for (let index = 0; index < sampleCount; index += 1) {
    samples[index] = view.getInt16(index * 2, true) / 32768
  }

  return samples
}

function removeScheduledSource(key: string) {
  scheduledSources = scheduledSources.filter((item) => item.key !== key)
}

function updateStreamPlaybackTelemetry(context: AudioContext | null) {
  playbackTelemetry.value = {
    bufferedAudioMs: Math.round(pendingStreamAudio.reduce((sum, chunk) => sum + chunk.durationMs, 0)),
    scheduledLeadMs:
      context && streamPlaybackStarted ? getScheduledLeadMs(context.currentTime, streamNextStartTime) : 0,
    underrunCount: playbackTelemetry.value.underrunCount,
  }
}

function applyStreamVisemes(payload: TtsVisemeChunkEvent, scheduledAt: number, context: AudioContext) {
  live2dRef.value?.queueScheduledPhonemes?.(payload.frames, context, scheduledAt)
}

function flushBufferedStreamAudio(context: AudioContext) {
  while (pendingStreamAudio.length > 0) {
    const nextChunk = pendingStreamAudio.shift()
    if (!nextChunk) {
      break
    }

    const { payload, samples } = nextChunk
    const key = streamChunkKey(payload)
    const scheduledAt = Math.max(
      context.currentTime + 0.03,
      streamNextStartTime > 0
        ? streamNextStartTime
        : context.currentTime + DEFAULT_STREAM_AUDIO_POLICY.scheduleLookaheadMs / 1000,
    )
    const buffer = context.createBuffer(1, samples.length, payload.sample_rate)
    buffer.copyToChannel(new Float32Array(samples), 0)

    const source = context.createBufferSource()
    const gain = context.createGain()
    const ramp = 0.01
    source.buffer = buffer
    source.connect(gain).connect(context.destination)
    gain.gain.setValueAtTime(0.0001, scheduledAt)
    gain.gain.linearRampToValueAtTime(1, scheduledAt + ramp)
    gain.gain.setValueAtTime(1, Math.max(scheduledAt + ramp, scheduledAt + buffer.duration - ramp))
    gain.gain.linearRampToValueAtTime(0.0001, scheduledAt + buffer.duration)
    source.start(scheduledAt)

    streamChunkSchedule.set(key, scheduledAt)
    scheduledSources.push({ key, source })
    source.onended = () => removeScheduledSource(key)
    streamNextStartTime = scheduledAt + buffer.duration

    const pending = pendingStreamVisemes.get(key)
    if (pending) {
      applyStreamVisemes(pending, scheduledAt, context)
      pendingStreamVisemes.delete(key)
    }
  }

  updateStreamPlaybackTelemetry(context)
}

async function handleStreamingAudio(payload: TtsAudioChunkEvent) {
  try {
    const context = await getAudioContext()
    if (!context) {
      playbackError.value = '当前浏览器不支持流式音频播放。'
      return
    }

    if (activeStreamReplyId !== payload.reply_id) {
      activeStreamReplyId = payload.reply_id
      streamNextStartTime = 0
      streamPlaybackStarted = false
      pendingStreamAudio = []
      pendingStreamVisemes.clear()
      streamChunkSchedule.clear()
      scheduledSources.forEach(({ source }) => {
        try {
          source.stop()
        } catch {
          return
        }
      })
      scheduledSources = []
      updateStreamPlaybackTelemetry(context)
    }

    const bytes = base64ToUint8Array(payload.data)
    const samples = pcm16ToFloat32(bytes)
    if (!samples.length) {
      return
    }

    const scheduledLeadMs = streamPlaybackStarted
      ? getScheduledLeadMs(context.currentTime, streamNextStartTime)
      : 0
    if (streamPlaybackStarted && shouldResetBufferedPlayback(scheduledLeadMs)) {
      streamPlaybackStarted = false
      streamNextStartTime = 0
      playbackTelemetry.value.underrunCount += 1
    }

    pendingStreamAudio.push({
      payload,
      samples,
      durationMs: (samples.length / payload.sample_rate) * 1000,
    })
    updateStreamPlaybackTelemetry(context)

    if (
      !streamPlaybackStarted &&
      !shouldStartBufferedPlayback(
        {
          bufferedAudioMs: playbackTelemetry.value.bufferedAudioMs,
          pendingChunkCount: pendingStreamAudio.length,
          isFinalChunkBuffered: payload.is_final,
        },
        DEFAULT_STREAM_AUDIO_POLICY,
      )
    ) {
      return
    }

    streamPlaybackStarted = true
    flushBufferedStreamAudio(context)
  } catch (error) {
    playbackError.value = error instanceof Error ? error.message : '流式音频播放失败。'
  }
}

function handleStreamingVisemes(payload: TtsVisemeChunkEvent) {
  const key = streamChunkKey(payload)
  const scheduledAt = streamChunkSchedule.get(key)
  const context = audioUnlockContext
  if (scheduledAt !== undefined && context) {
    applyStreamVisemes(payload, scheduledAt, context)
    return
  }
  pendingStreamVisemes.set(key, payload)
}

function handleEmotion(payload: EmotionEvent) {
  latestEmotion.value = payload.value
  emotionTelemetry.value = {
    value: payload.value,
    confidence: payload.confidence ?? 0.45,
    keywords: payload.keywords ?? [],
    reason: payload.reason ?? '当前回答未附带更多情绪说明。',
    source: payload.source ?? 'heuristic',
  }
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

  if (payload.type === 'tts_audio_chunk') {
    void handleStreamingAudio(payload)
    return
  }

  if (payload.type === 'tts_viseme_chunk') {
    handleStreamingVisemes(payload)
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

  if (payload.type === 'text_done') {
    finalizeAssistantDraft()
    void scrollChatToEnd()
    return
  }

  if (payload.type === 'audio_done') {
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
  onOpen: () => {
    socket.send({
      type: 'hello',
      tts_streaming: true,
      audio_format: 'pcm16le',
    })
  },
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
const emotionVisual = computed(() => EMOTION_VISUALS[emotionTelemetry.value.value] ?? EMOTION_VISUALS.neutral)
const emotionConfidenceLabel = computed(
  () => `${Math.round((emotionTelemetry.value.confidence || 0) * 100)}%`,
)

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

  void unlockAudioPlayback()

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

  void unlockAudioPlayback()
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
  void audioUnlockContext?.close()
})
</script>

<template>
  <div class="app-shell">
    <div class="aurora aurora-left"></div>
    <div class="aurora aurora-right"></div>

    <header class="topbar">
      <div>
        <p class="eyebrow">Phase 2 Visitor Demo</p>
        <h1>景区 AI 数字人导览台</h1>
        <p class="subtitle">
          已接入示例 Live2D 模型、文本与语音输入、WebSocket 流式对话、口型同步，以及表情识别与调试链路。
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
              <strong>{{ emotionVisual.label }} / {{ latestEmotion }}</strong>
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
          <article class="telemetry-card telemetry-card-lamp">
            <span class="telemetry-label">情绪熔岩灯</span>
            <div class="emotion-lamp-shell">
              <div
                class="emotion-lamp"
                :style="{
                  background: emotionVisual.color,
                  boxShadow: `0 0 28px ${emotionVisual.glow}`,
                }"
              >
                <span class="emotion-lamp-core"></span>
              </div>
              <div class="emotion-meta">
                <strong>{{ emotionVisual.label }}</strong>
                <span>置信度 {{ emotionConfidenceLabel }}</span>
                <span>来源 {{ emotionTelemetry.source }}</span>
              </div>
            </div>
            <p class="emotion-reason">{{ emotionTelemetry.reason }}</p>
            <p class="emotion-keywords">
              {{ emotionTelemetry.keywords.length ? emotionTelemetry.keywords.join(' / ') : '暂无显著情绪关键词' }}
            </p>
          </article>
          <article class="telemetry-card">
            <span class="telemetry-label">识别回显</span>
            <p>{{ lastAsrPreview || '开始录音后会在这里显示 ASR 文本。' }}</p>
          </article>
          <article class="telemetry-card">
            <span class="telemetry-label">流式缓冲</span>
            <p>缓冲 {{ playbackTelemetry.bufferedAudioMs }} ms</p>
            <p>排程余量 {{ playbackTelemetry.scheduledLeadMs }} ms</p>
            <p>断流次数 {{ playbackTelemetry.underrunCount }}</p>
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
