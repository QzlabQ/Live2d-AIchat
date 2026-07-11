<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import ChatComposer from './components/ChatComposer.vue'
import ChatTranscript from './components/ChatTranscript.vue'
import InterestTagPanel from './components/InterestTagPanel.vue'
import Live2DStage from './components/Live2DStage.vue'
import PhotoAskPanel from './components/PhotoAskPanel.vue'
import SessionHistoryRail from './components/SessionHistoryRail.vue'
import { useAudioRecorder } from './composables/useAudioRecorder'
import { useChatSocket } from './composables/useChatSocket'
import { usePhotoRecognition } from './composables/usePhotoRecognition'
import { useVisitorRecommendations } from './composables/useVisitorRecommendations'
import { useVisitorSessions } from './composables/useVisitorSessions'
import { base64ToBlobUrl, base64ToUint8Array } from './lib/base64'
import { attachAssistantMessageMeta, normalizeSources } from './lib/chatMessageMeta'
import { buildEmotionLampStyle } from './lib/emotionLamp'
import { EMOTION_VISUALS } from './lib/lipsync'
import { buildPhotoQuestion, shouldEnterThinkingForPhoto } from './lib/photoQuestion'
import {
  computeAvatarPresentation,
  createDefaultConversationPhaseState,
  reduceAvatarPhaseEvent,
} from './lib/avatarPresentation'
import {
  DEFAULT_STREAM_AUDIO_POLICY,
  getScheduledLeadMs,
  shouldResetBufferedPlayback,
  shouldStartBufferedPlayback,
} from './lib/streamAudioBuffer'
import {
  canSwitchSessionWhileIdle,
  isReplyFlowActiveForSessionSwitch,
} from './lib/visitorSessionState'
import { createVisitorSession } from './services/visitorApi'
import type {
  AudioEvent,
  AvatarPhaseEvent,
  ChatMessage,
  EmotionEvent,
  EmotionStage,
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
  '第一次来应该怎么逛？',
  '开放时间是什么时候？',
]

function createWelcomeMessage(): ChatMessage {
  return {
    id: 'welcome',
    role: 'assistant',
    content:
      '欢迎来到景区 AI 数字人导览台。你可以直接提问，也可以选择兴趣标签、上传照片或点击推荐问题继续对话。',
  }
}

function createDefaultEmotionTelemetry(): EmotionTelemetry {
  return {
    value: 'neutral',
    stage: 'final',
    confidence: 0.45,
    keywords: [],
    reason: '等待新一轮问题时，保持中性待机状态。',
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
const transcriptRef = ref<{ scrollToEnd: () => Promise<void> } | null>(null)

const visitorSessions = useVisitorSessions(API_BASE_URL)
const sessionId = visitorSessions.activeSessionId
const recommendationState = useVisitorRecommendations(API_BASE_URL, sessionId)
const photoRecognition = usePhotoRecognition(API_BASE_URL, sessionId)

const sessionBooting = ref(false)
const bootError = ref('')
const composer = ref('')
const messages = visitorSessions.activeMessages
const assistantDraftId = ref<string | null>(null)
const replyPending = ref(false)
const lastAsrPreview = ref('')
const latestEmotion = ref<EmotionValue>('neutral')
const emotionTelemetry = ref<EmotionTelemetry>(createDefaultEmotionTelemetry())
const conversationPhaseState = ref(createDefaultConversationPhaseState())
const avatarPresentationNowMs = ref(Date.now())
const avatarSpeechActive = ref(false)
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
let avatarCooldownTimer = 0

function createMessageId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
}

function clearAvatarCooldownTimer() {
  if (avatarCooldownTimer) {
    window.clearTimeout(avatarCooldownTimer)
    avatarCooldownTimer = 0
  }
}

function syncSessionTools(interestTags: string[]) {
  recommendationState.setSelectedTags(interestTags)
  recommendationState.clearRecommendation()
  photoRecognition.clearResult()
}

function getSessionTagsById(targetSessionId: string | null) {
  if (!targetSessionId) {
    return []
  }

  return (
    visitorSessions.sessionList.value.find((item) => item.sessionId === targetSessionId)?.interestTags ?? []
  )
}

function applyAvatarPhase(event: AvatarPhaseEvent) {
  const previous = conversationPhaseState.value
  const next = reduceAvatarPhaseEvent(previous, event)
  if (next === previous) {
    return
  }

  conversationPhaseState.value = next
  avatarPresentationNowMs.value = event.at_ms ?? Date.now()

  if (event.phase === 'speaking') {
    avatarSpeechActive.value = true
  } else if (event.phase === 'idle' || event.phase === 'cooldown') {
    avatarSpeechActive.value = false
  }

  clearAvatarCooldownTimer()
  if (next.phase !== 'cooldown' || next.cooldownUntilMs === null) {
    return
  }

  const delayMs = Math.max(0, next.cooldownUntilMs - avatarPresentationNowMs.value)
  avatarCooldownTimer = window.setTimeout(() => {
    const nowMs = Date.now()
    avatarPresentationNowMs.value = nowMs
    conversationPhaseState.value = reduceAvatarPhaseEvent(conversationPhaseState.value, {
      type: 'avatar_phase',
      phase: 'idle',
      reply_id: next.activeReplyId ?? undefined,
      at_ms: nowMs,
      reason: 'cooldown_elapsed',
    })
    avatarSpeechActive.value = false
    avatarCooldownTimer = 0
  }, delayMs)
}

function resetAvatarPresentationState() {
  clearAvatarCooldownTimer()
  avatarSpeechActive.value = false
  avatarPresentationNowMs.value = Date.now()
  conversationPhaseState.value = createDefaultConversationPhaseState()
}

function beginLocalThinkingPhase(reason = 'local_reply_started') {
  applyAvatarPhase({
    type: 'avatar_phase',
    phase: 'thinking',
    reply_id: createMessageId('local-reply'),
    at_ms: Date.now(),
    reason,
  })
}

function resetReplyMediaState() {
  replyPending.value = false
  resetAvatarPresentationState()
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
  visitorSessions.replaceActiveMessages([createWelcomeMessage()])
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
  await transcriptRef.value?.scrollToEnd()
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

function patchLatestAssistantMessage(patch: Parameters<typeof attachAssistantMessageMeta>[2]) {
  return attachAssistantMessageMeta(messages.value, assistantDraftId.value, patch)
}

async function refreshSessionsQuietly() {
  try {
    await visitorSessions.refreshSessions()
  } catch {
    return
  }
}

async function createSession() {
  if (sessionBooting.value) {
    return
  }

  if (isSessionSwitchBlocked.value) {
    pushSystemMessage(sessionSwitchBlockedReason.value)
    await scrollChatToEnd()
    return
  }

  sessionBooting.value = true
  bootError.value = ''

  try {
    const payload = await createVisitorSession(API_BASE_URL, {
      deviceType: 'mobile',
    })
    resetConversation()
    visitorSessions.setActiveSession(payload.sessionId, [createWelcomeMessage()])
    syncSessionTools([])
    await visitorSessions.refreshSessions()
  } catch (error) {
    bootError.value = error instanceof Error ? error.message : '创建会话失败。'
  } finally {
    sessionBooting.value = false
    await scrollChatToEnd()
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
      error instanceof Error ? error.message : '浏览器阻止了自动播放，请先与页面进行一次交互。'
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
    const previousNextStartTime = streamNextStartTime
    const hadScheduledAudio = previousNextStartTime > 0
    const scheduledAt = Math.max(
      context.currentTime + 0.03,
      hadScheduledAudio
        ? previousNextStartTime
        : context.currentTime + DEFAULT_STREAM_AUDIO_POLICY.scheduleLookaheadMs / 1000,
    )
    const buffer = context.createBuffer(1, samples.length, payload.sample_rate)
    buffer.copyToChannel(new Float32Array(samples), 0)

    const source = context.createBufferSource()
    const gain = context.createGain()
    const ramp = 0.01
    source.buffer = buffer
    source.connect(gain).connect(context.destination)

    const isReplyStart = !hadScheduledAudio
    const hadUnderrun = hadScheduledAudio && scheduledAt > previousNextStartTime + 0.001
    if (isReplyStart || hadUnderrun) {
      gain.gain.setValueAtTime(0.0001, scheduledAt)
      gain.gain.linearRampToValueAtTime(1, scheduledAt + ramp)
    } else {
      gain.gain.setValueAtTime(1, scheduledAt)
    }
    if (payload.is_final) {
      gain.gain.setValueAtTime(1, Math.max(scheduledAt + ramp, scheduledAt + buffer.duration - ramp))
      gain.gain.linearRampToValueAtTime(0.0001, scheduledAt + buffer.duration)
    }
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
      applyAvatarPhase({
        type: 'avatar_phase',
        phase: 'speaking',
        reply_id: payload.reply_id,
        at_ms: Date.now(),
        reason: 'stream_audio_started',
      })
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
  avatarSpeechActive.value = true
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
    stage: payload.stage ?? 'final',
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

  if (payload.type === 'avatar_phase') {
    applyAvatarPhase(payload)
    return
  }

  if (payload.type === 'reply_meta') {
    patchLatestAssistantMessage({
      replyKind: payload.reply_kind,
      needsFollowup: payload.needs_followup,
    })
    void scrollChatToEnd()
    return
  }

  if (payload.type === 'sources') {
    patchLatestAssistantMessage({
      sources: normalizeSources(payload.items),
    })
    void scrollChatToEnd()
    return
  }

  if (payload.type === 'text_done') {
    finalizeAssistantDraft()
    void scrollChatToEnd()
    return
  }

  if (payload.type === 'audio_done') {
    applyAvatarPhase({
      type: 'avatar_phase',
      phase: 'cooldown',
      reply_id: payload.reply_id,
      at_ms: Date.now(),
      reason: 'audio_done_fallback',
    })
    return
  }

  if (payload.type === 'done') {
    replyPending.value = false
    finalizeAssistantDraft()
    applyAvatarPhase({
      type: 'avatar_phase',
      phase: 'idle',
      at_ms: Date.now(),
      reason: 'reply_done_fallback',
    })
    void refreshSessionsQuietly()
    void scrollChatToEnd()
  }
}

function handleSocketError(message: string) {
  replyPending.value = false
  pushSystemMessage(message)
  finalizeAssistantDraft()
  applyAvatarPhase({
    type: 'avatar_phase',
    phase: 'idle',
    at_ms: Date.now(),
    reason: 'socket_error',
  })
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

const isPhotoThinking = computed(() =>
  shouldEnterThinkingForPhoto({
    uploading: photoRecognition.uploading.value,
    recognizing: photoRecognition.recognizing.value,
  }),
)
const isReplyStreaming = computed(
  () =>
    isReplyFlowActiveForSessionSwitch({
      replyPending: replyPending.value,
      isPhotoPending: isPhotoThinking.value,
      assistantDraftActive: assistantDraftId.value !== null,
      avatarSpeechActive: avatarSpeechActive.value,
      queuedAudioCount: queuedAudio.value.length,
      bufferedAudioMs: playbackTelemetry.value.bufferedAudioMs,
      scheduledLeadMs: playbackTelemetry.value.scheduledLeadMs,
    }),
)
const isSessionSwitchBlocked = computed(
  () =>
    !canSwitchSessionWhileIdle({
      isStreaming: isReplyStreaming.value,
      isRecording: recorder.isRecording.value,
    }),
)
const sessionSwitchBlockedReason = computed(() => {
  if (recorder.isRecording.value) {
    return '录音进行中，暂时不能切换会话。'
  }

  if (isPhotoThinking.value) {
    return '图片识别进行中，等识别完成后再切换会话。'
  }

  if (isReplyStreaming.value) {
    return '导览助手还在回复，等这一轮结束后再切换。'
  }

  return ''
})
const canSend = computed(
  () => socket.state.value === 'connected' && composer.value.trim().length > 0 && !sessionBooting.value,
)
const canRecord = computed(
  () => recorder.isSupported.value && socket.state.value === 'connected' && !sessionBooting.value,
)
const meterScale = computed(() => Math.max(0.05, recorder.level.value))
const emotionVisual = computed(() => EMOTION_VISUALS[emotionTelemetry.value.value] ?? EMOTION_VISUALS.neutral)
const avatarPresentation = computed(() =>
  computeAvatarPresentation(conversationPhaseState.value, {
    emotion: latestEmotion.value,
    emotionStage: emotionTelemetry.value.stage,
    lipSyncActive: avatarSpeechActive.value,
    nowMs: avatarPresentationNowMs.value,
  }),
)
const emotionLampStyle = computed(() =>
  buildEmotionLampStyle(emotionTelemetry.value, emotionVisual.value),
)
const emotionConfidenceLabel = computed(
  () => `${Math.round((emotionTelemetry.value.confidence || 0) * 100)}%`,
)
const emotionStageLabel = computed(() => {
  const labels: Record<EmotionStage, string> = {
    preview: '预判',
    final: '正式',
  }
  return labels[emotionTelemetry.value.stage]
})
const activeInterestSummary = computed(() => {
  const tags = recommendationState.selectedInterestTags.value
  return tags.length > 0 ? tags.join(' / ') : '未设置偏好'
})
const visitorToolsDisabled = computed(
  () => !sessionId.value || sessionBooting.value || visitorSessions.loading.value,
)
const historyRailDisabled = computed(
  () => sessionBooting.value || visitorSessions.loading.value || isSessionSwitchBlocked.value,
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

async function sendOutgoingText(
  content: string,
  options: {
    meta?: string
    resetTurn?: boolean
    clearComposer?: boolean
  } = {},
) {
  const normalized = content.trim()
  if (!normalized) {
    return false
  }

  if (socket.state.value !== 'connected') {
    handleSocketError('当前 WebSocket 尚未连接，暂时无法发送消息。')
    return false
  }

  void unlockAudioPlayback()

  messages.value.push({
    id: createMessageId(options.meta ? 'user-meta' : 'user'),
    role: 'user',
    content: normalized,
    meta: options.meta,
  })

  if (options.resetTurn ?? true) {
    resetReplyMediaState()
    beginLocalThinkingPhase()
    finalizeAssistantDraft()
  }

  if (options.clearComposer) {
    composer.value = ''
  }

  const sent = socket.send({ type: 'text', content: normalized })
  if (!sent) {
    handleSocketError('文本消息发送失败，请稍后重试。')
    return false
  }

  replyPending.value = true
  await scrollChatToEnd()
  return sent
}

async function sendText() {
  await sendOutgoingText(composer.value, {
    clearComposer: true,
    resetTurn: true,
  })
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
  beginLocalThinkingPhase('voice_recording_started')
  finalizeAssistantDraft()
  replyPending.value = true
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

async function openSession(targetSessionId: string) {
  if (sessionId.value === targetSessionId) {
    return
  }

  if (isSessionSwitchBlocked.value) {
    pushSystemMessage(sessionSwitchBlockedReason.value)
    await scrollChatToEnd()
    return
  }

  bootError.value = ''
  composer.value = ''
  finalizeAssistantDraft()
  resetReplyMediaState()
  latestEmotion.value = 'neutral'
  emotionTelemetry.value = createDefaultEmotionTelemetry()
  lastAsrPreview.value = ''
  syncSessionTools(getSessionTagsById(targetSessionId))

  try {
    await visitorSessions.openSession(targetSessionId)
    if (messages.value.length === 0) {
      visitorSessions.replaceActiveMessages([createWelcomeMessage()])
    }
    await visitorSessions.refreshSessions()
  } catch (error) {
    bootError.value = error instanceof Error ? error.message : '加载会话失败。'
  } finally {
    await scrollChatToEnd()
  }
}

async function bootstrapSessions() {
  bootError.value = ''

  try {
    await visitorSessions.refreshSessions()
    const latest = visitorSessions.sessionList.value[0]
    if (latest) {
      syncSessionTools(latest.interestTags)
      await visitorSessions.openSession(latest.sessionId)
      if (messages.value.length === 0) {
        visitorSessions.replaceActiveMessages([createWelcomeMessage()])
      }
      return
    }
  } catch (error) {
    bootError.value = error instanceof Error ? error.message : '加载历史会话失败。'
  }

  await createSession()
}

async function handleToggleInterestTag(tag: string) {
  try {
    await recommendationState.toggleTag(tag)
    await refreshSessionsQuietly()
  } catch {
    return
  }
}

async function handleGenerateRecommendation() {
  if (!sessionId.value) {
    return
  }

  if (recommendationState.selectedInterestTags.value.length === 0) {
    pushSystemMessage('先选择至少一个兴趣标签，我再帮你规划路线。')
    await scrollChatToEnd()
    return
  }

  try {
    await recommendationState.refreshRecommendations()
  } catch {
    return
  }
}

async function handleRecommendationQuestion(question: string) {
  await sendOutgoingText(question, {
    meta: '路线推荐',
    resetTurn: true,
  })
}

async function handlePhotoPicked(file: File) {
  if (!sessionId.value) {
    await createSession()
    if (!sessionId.value) {
      return
    }
  }

  try {
    photoRecognition.clearResult()
    resetReplyMediaState()
    beginLocalThinkingPhase('photo_recognition_started')

    const result = await photoRecognition.recognize(
      file,
      recommendationState.selectedInterestTags.value,
    )
    const autoQuestion = buildPhotoQuestion({
      recognizedSpot: result.recognizedSpot,
      recognitionSummary: result.recognitionSummary,
      resolvedQuestion: result.resolvedQuestion,
    })
    await sendOutgoingText(autoQuestion, {
      meta: '图片识别',
      resetTurn: false,
    })
  } catch {
    applyAvatarPhase({
      type: 'avatar_phase',
      phase: 'idle',
      at_ms: Date.now(),
      reason: 'photo_recognition_error',
    })
    await scrollChatToEnd()
  }
}

watch([avatarPresentation, live2dRef], ([presentation, live2d]) => {
  live2d?.setAvatarPresentation(presentation)
}, { immediate: true })

onMounted(async () => {
  await bootstrapSessions()
  await scrollChatToEnd()
})

onBeforeUnmount(() => {
  clearAvatarCooldownTimer()
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
        <p class="eyebrow">Phase 3 Visitor Experience</p>
        <h1>景区 AI 数字人导览台</h1>
        <p class="subtitle">
          当前页面整合了历史会话、个性化路线推荐、拍照问景点、流式语音回复和 Live2D 口型同步，
          方便在同一个游客端完成完整体验。
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
        <div class="meta-chip">
          <span class="meta-label">偏好</span>
          <strong>{{ activeInterestSummary }}</strong>
        </div>
      </div>
    </header>

    <main class="workspace">
      <SessionHistoryRail
        :sessions="visitorSessions.sessionList.value"
        :active-session-id="sessionId"
        :loading="sessionBooting || visitorSessions.loading.value || visitorSessions.refreshing.value"
        :disabled="historyRailDisabled"
        :disabled-reason="visitorSessions.error.value || sessionSwitchBlockedReason"
        @create="createSession"
        @open="openSession"
      />

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
              <strong>{{ emotionVisual.label }} / {{ latestEmotion }} / {{ emotionStageLabel }}</strong>
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
                :data-stage="emotionTelemetry.stage"
                :data-emotion="emotionTelemetry.value"
                :style="emotionLampStyle"
              >
                <span class="emotion-lamp-core"></span>
              </div>
              <div class="emotion-meta">
                <strong>{{ emotionVisual.label }}</strong>
                <span>阶段 {{ emotionStageLabel }}</span>
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
            <p>{{ lastAsrPreview || '开始录音后，会在这里显示语音识别文本。' }}</p>
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
            <p class="panel-kicker">Visitor Channel</p>
            <h2>游客对话台</h2>
          </div>
          <div class="header-actions">
            <button class="ghost-button" type="button" @click="reconnectNow">手动重连</button>
          </div>
        </div>

        <p v-if="bootError" class="banner banner-error">{{ bootError }}</p>
        <p v-else-if="playbackError" class="banner banner-warn">{{ playbackError }}</p>

        <div class="visitor-tools">
          <InterestTagPanel
            :selected-tags="recommendationState.selectedInterestTags.value"
            :recommendation="recommendationState.recommendation.value"
            :loading="recommendationState.loading.value"
            :saving="recommendationState.saving.value"
            :error="recommendationState.error.value"
            :disabled="visitorToolsDisabled"
            @toggle-tag="handleToggleInterestTag"
            @refresh="handleGenerateRecommendation"
            @ask-question="handleRecommendationQuestion"
          />

          <PhotoAskPanel
            :busy="photoRecognition.uploading.value || photoRecognition.recognizing.value"
            :disabled="visitorToolsDisabled"
            :error="photoRecognition.error.value"
            :result="photoRecognition.lastResult.value"
            @pick="handlePhotoPicked"
          />
        </div>

        <ChatTranscript ref="transcriptRef" :messages="messages" />

        <ChatComposer
          v-model="composer"
          :quick-hints="QUICK_HINTS"
          :can-send="canSend"
          :can-record="canRecord"
          :is-recording="recorder.isRecording.value"
          @send="sendText"
          @toggle-recording="toggleRecording"
        />
      </section>
    </main>
  </div>
</template>
