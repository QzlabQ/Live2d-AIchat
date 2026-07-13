<script setup lang="ts">
import * as PIXI from 'pixi.js'
import { Live2DModel } from 'pixi-live2d-display/cubism4'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import {
  AVATAR_DISPLAY_DEFAULTS,
  computeLive2DPlacement,
} from '../lib/avatarDisplay'
import {
  buildEmotionTarget,
  buildExpressionTarget,
  currentPhoneme,
  EMOTION_PRESETS,
  finalFrameEnd,
  mouthPoseFromFrame,
  resolveModelAssetUrl,
} from '../lib/lipsync'
import type { AvatarPresentation } from '../lib/avatarPresentation'
import type {
  EmotionStage,
  EmotionValue,
  PhonemeFrame,
} from '../types/chat'

type RuntimeLive2DModel = Live2DModel &
  PIXI.Container & {
    width: number
    height: number
    interactive: boolean
    cursor: string
    motion: (group: string) => void
    anchor: {
      set: (x: number, y?: number) => void
    }
    scale: {
      set: (value: number) => void
    }
    position: {
      set: (x: number, y?: number) => void
    }
    pivot: {
      set: (x: number, y?: number) => void
    }
    on: (event: string, handler: () => void) => void
    getLocalBounds: () => PIXI.Rectangle
    internalModel: {
      coreModel: {
        setParameterValueById: (id: string, value: number) => void
      }
    }
  }

interface ModelSettings {
  url?: string
  FileReferences?: {
    DisplayInfo?: string
    Expressions?: Array<{ Name: string; File: string }>
    Motions?: Record<string, Array<{ File: string; Sound?: string }>>
  }
}

interface LipSyncState {
  frames: PhonemeFrame[]
  audio: HTMLAudioElement | null
  audioContext: AudioContext | null
  useAudioContextClock: boolean
  startedAt: number
  stopAt: number
}

const props = withDefaults(defineProps<{
  modelPath: string
  modelScale?: number
  modelOffsetX?: number
  modelOffsetY?: number
}>(), {
  modelScale: AVATAR_DISPLAY_DEFAULTS.displayScale,
  modelOffsetX: AVATAR_DISPLAY_DEFAULTS.displayOffsetX,
  modelOffsetY: AVATAR_DISPLAY_DEFAULTS.displayOffsetY,
})

const stageHost = ref<HTMLDivElement | null>(null)
const loadError = ref('')
const loading = ref(true)

let pixiApp: PIXI.Application | null = null
let model: RuntimeLive2DModel | null = null
let resizeObserver: ResizeObserver | null = null
let idleTimer = 0
let lipSyncState: LipSyncState | null = null
let currentOpen = 0.06
let currentForm = 0
const MOUTH_OPEN_IDS = ['ParamMouthOpenY', 'PARAM_MOUTH_OPEN_Y']
const MOUTH_FORM_IDS = ['ParamMouthForm', 'PARAM_MOUTH_FORM']
const currentEmotionValues: Record<string, number> = {}
const expressionTargets: Record<string, Record<string, number>> = {}
let emotionParamIds = new Set(Object.keys(EMOTION_PRESETS.neutral))
let targetEmotionValues: Record<string, number> = { ...EMOTION_PRESETS.neutral }
let currentEmotion: EmotionValue = 'neutral'
let currentEmotionStage: EmotionStage = 'final'
let currentAvatarPresentation: AvatarPresentation = {
  phase: 'idle',
  emotion: 'neutral',
  emotionStage: 'final',
  allowIdleMotion: true,
  motionIntensity: 'normal',
  lipSyncActive: false,
  activeReplyId: null,
}

function safeSetParameter(id: string, value: number) {
  if (!model) {
    return
  }

  try {
    model.internalModel.coreModel.setParameterValueById(id, value)
  } catch {
    return
  }
}

function safeSetParameterAliases(ids: string[], value: number) {
  for (const id of ids) {
    safeSetParameter(id, value)
  }
}

function rebuildEmotionTarget() {
  targetEmotionValues = buildEmotionTarget(currentEmotion, currentEmotionStage, expressionTargets)
  emotionParamIds = new Set([
    ...Object.keys(currentEmotionValues),
    ...Object.keys(targetEmotionValues),
  ])
}

function setMouthPose(targetOpen: number, targetForm: number) {
  currentOpen += (targetOpen - currentOpen) * 0.35
  currentForm += (targetForm - currentForm) * 0.35

  safeSetParameterAliases(MOUTH_OPEN_IDS, currentOpen)
  safeSetParameterAliases(MOUTH_FORM_IDS, currentForm)
}

function resizeModel() {
  if (!model || !stageHost.value) {
    return
  }

  const { clientWidth, clientHeight } = stageHost.value
  const bounds = model.getLocalBounds()
  const placement = computeLive2DPlacement(
    { width: clientWidth, height: clientHeight },
    {
      width: bounds.width || model.width || 1,
      height: bounds.height || model.height || 1,
    },
    {
      displayScale: props.modelScale,
      displayOffsetX: props.modelOffsetX,
      displayOffsetY: props.modelOffsetY,
      stageHeight: clientHeight,
    },
  )

  model.scale.set(placement.scale)
  model.anchor.set(0.5, 0.88)
  model.position.set(placement.x, placement.y)
}

function playIdleMotion() {
  if (!model) {
    return
  }

  window.clearInterval(idleTimer)
  idleTimer = window.setInterval(() => {
    if (!model || !currentAvatarPresentation.allowIdleMotion) {
      return
    }

    try {
      model.motion('Idle')
    } catch {
      return
    }
  }, 12000)
}

function applyLightPhaseMotion(t: number) {
  if (currentAvatarPresentation.motionIntensity !== 'light') {
    return
  }

  const speakingScale = currentAvatarPresentation.phase === 'speaking' ? 1 : 0.55
  const angleBase = currentEmotionValues.ParamAngleX ?? targetEmotionValues.ParamAngleX ?? 0
  const bodyBase = currentEmotionValues.ParamBodyAngleX ?? targetEmotionValues.ParamBodyAngleX ?? 0
  const eyeBase = currentEmotionValues.ParamEyeBallY ?? targetEmotionValues.ParamEyeBallY ?? 0

  safeSetParameter('ParamAngleX', angleBase + Math.sin(t * 1.6) * 0.38 * speakingScale)
  safeSetParameter('ParamBodyAngleX', bodyBase + Math.sin(t * 1.2 + 0.4) * 0.28 * speakingScale)
  safeSetParameter('ParamEyeBallY', eyeBase + Math.sin(t * 0.9) * 0.025 * speakingScale)
}

function startBreathingLoop() {
  pixiApp?.ticker.add(() => {
    if (!model) {
      return
    }

    const t = performance.now() / 1000
    safeSetParameter('ParamBreath', (Math.sin(t * 1.2) + 1) / 2)

    for (const id of emotionParamIds) {
      const current = currentEmotionValues[id] ?? 0
      const target = targetEmotionValues[id] ?? 0
      const next = current + (target - current) * 0.18
      currentEmotionValues[id] = next
      safeSetParameter(id, next)
    }
    applyLightPhaseMotion(t)

    if (lipSyncState) {
      const { frames, audio, audioContext, startedAt, stopAt, useAudioContextClock } = lipSyncState
      const elapsed = useAudioContextClock && audioContext
        ? audioContext.currentTime
        : audio && Number.isFinite(audio.currentTime) && audio.currentTime > 0
          ? audio.currentTime
          : (performance.now() - startedAt) / 1000
      const frame = currentPhoneme(frames, elapsed)
      const target = mouthPoseFromFrame(frame)
      setMouthPose(target.openY, target.form)

      if (elapsed <= stopAt && (useAudioContextClock || !audio?.ended)) {
        return
      }

      lipSyncState = null
      setMouthPose(0.06, 0)
      return
    }

    setMouthPose(0.06 + Math.sin(t * 2.3) * 0.01, currentForm * 0.85)
  })
}

async function createModel() {
  if (!stageHost.value) {
    return
  }

  if (!window.Live2DCubismCore) {
    throw new Error('Live2D Cubism Core runtime not found. Check index.html script loading.')
  }

  window.PIXI = PIXI
  const response = await fetch(props.modelPath)
  if (!response.ok) {
    throw new Error(`Unable to load model settings: ${response.status}`)
  }

  const settings = (await response.json()) as ModelSettings
  settings.url = props.modelPath

  if (settings.FileReferences?.DisplayInfo) {
    delete settings.FileReferences.DisplayInfo
  }

  for (const motions of Object.values(settings.FileReferences?.Motions ?? {})) {
    for (const motion of motions) {
      if (motion.Sound) {
        delete motion.Sound
      }
    }
  }

  for (const expression of settings.FileReferences?.Expressions ?? []) {
    const url = resolveModelAssetUrl(props.modelPath, expression.File)
    const expressionResponse = await fetch(url)
    if (!expressionResponse.ok) {
      continue
    }

    const expressionData = await expressionResponse.json() as { Parameters?: Array<{ Id: string; Value: number; Blend?: string }> }
    expressionTargets[expression.Name.toLowerCase()] = buildExpressionTarget(expressionData.Parameters ?? [])
  }
  rebuildEmotionTarget()

  model = (await Live2DModel.from(settings)) as RuntimeLive2DModel
  model.interactive = true
  model.cursor = 'pointer'
  model.on('pointertap', () => {
    if (currentAvatarPresentation.motionIntensity !== 'normal') {
      return
    }

    try {
      model?.motion('Tap')
    } catch {
      return
    }
  })

  pixiApp = new PIXI.Application({
    width: stageHost.value.clientWidth,
    height: stageHost.value.clientHeight,
    autoDensity: true,
    antialias: true,
    backgroundAlpha: 0,
    resolution: window.devicePixelRatio || 1,
  })

  const canvas = pixiApp.view as HTMLCanvasElement
  canvas.style.display = 'block'
  canvas.style.width = '100%'
  canvas.style.height = '100%'
  stageHost.value.appendChild(canvas)
  pixiApp.stage.addChild(model as unknown as PIXI.DisplayObject)
  resizeModel()
  playIdleMotion()
  startBreathingLoop()

  resizeObserver = new ResizeObserver(() => {
    if (!stageHost.value || !pixiApp) {
      return
    }

    pixiApp.renderer.resize(stageHost.value.clientWidth, stageHost.value.clientHeight)
    resizeModel()
  })

  resizeObserver.observe(stageHost.value)
}

function destroyModelRuntime() {
  window.clearInterval(idleTimer)
  idleTimer = 0
  lipSyncState = null
  resizeObserver?.disconnect()
  resizeObserver = null
  if (pixiApp) {
    pixiApp.destroy(true, { children: true })
  }
  pixiApp = null
  model = null
  currentOpen = 0.06
  currentForm = 0
}

async function loadModel() {
  loading.value = true
  loadError.value = ''
  destroyModelRuntime()

  try {
    await createModel()
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : 'Live2D model loading failed.'
  } finally {
    loading.value = false
  }
}

function setEmotion(emotion: EmotionValue, stage: EmotionStage = 'final') {
  currentEmotion = emotion
  currentEmotionStage = stage
  rebuildEmotionTarget()
}

function setAvatarPresentation(presentation: AvatarPresentation) {
  const wasIdleMotionAllowed = currentAvatarPresentation.allowIdleMotion
  currentAvatarPresentation = presentation
  setEmotion(presentation.emotion, presentation.emotionStage)

  if (!wasIdleMotionAllowed && presentation.allowIdleMotion && model) {
    try {
      model.motion('Idle')
    } catch {
      return
    }
  }
}

function playPhonemes(frames: PhonemeFrame[], audio?: HTMLAudioElement | null) {
  if (!frames.length) {
    lipSyncState = null
    setMouthPose(0.06, 0)
    return
  }

  lipSyncState = {
    frames,
    audio: audio ?? null,
    audioContext: null,
    useAudioContextClock: false,
    startedAt: performance.now(),
    stopAt: finalFrameEnd(frames) + 0.18,
  }
}

function queueScheduledPhonemes(
  frames: PhonemeFrame[],
  audioContext: AudioContext,
  scheduledAt: number,
) {
  if (!frames.length) {
    return
  }

  const absoluteFrames = frames.map((frame) => ({
    ...frame,
    start: frame.start + scheduledAt,
    end: frame.end + scheduledAt,
  }))

  if (
    lipSyncState &&
    lipSyncState.useAudioContextClock &&
    lipSyncState.audioContext === audioContext
  ) {
    lipSyncState.frames = [...lipSyncState.frames, ...absoluteFrames].sort((left, right) => left.start - right.start)
    lipSyncState.stopAt = Math.max(lipSyncState.stopAt, finalFrameEnd(absoluteFrames) + 0.18)
    return
  }

  lipSyncState = {
    frames: absoluteFrames,
    audio: null,
    audioContext,
    useAudioContextClock: true,
    startedAt: performance.now(),
    stopAt: finalFrameEnd(absoluteFrames) + 0.18,
  }
}

defineExpose({
  setEmotion,
  setAvatarPresentation,
  playPhonemes,
  queueScheduledPhonemes,
})

onMounted(async () => {
  await loadModel()
})

onBeforeUnmount(() => {
  destroyModelRuntime()
})

watch(
  () => props.modelPath,
  async (next, previous) => {
    if (!next || next === previous) {
      return
    }
    await loadModel()
  },
)

watch(
  () => [props.modelScale, props.modelOffsetX, props.modelOffsetY],
  () => {
    resizeModel()
  },
)
</script>

<template>
  <div class="live2d-shell">
    <div ref="stageHost" class="live2d-stage"></div>
    <div v-if="loading" class="stage-overlay">
      <span class="stage-badge">Live2D 加载中</span>
    </div>
    <div v-else-if="loadError" class="stage-overlay stage-overlay-error">
      <p>{{ loadError }}</p>
    </div>
  </div>
</template>

<style scoped>
.live2d-shell {
  position: relative;
  width: 100%;
  height: 100%;
}

.live2d-stage {
  width: 100%;
  height: 100%;
}

.stage-overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background:
    radial-gradient(circle at 20% 20%, rgba(255, 238, 206, 0.36), transparent 45%),
    rgba(18, 30, 43, 0.28);
  color: #fff8eb;
  font-size: 0.95rem;
}

.stage-overlay-error {
  padding: 1.5rem;
  text-align: center;
  color: #ffe2d9;
}

.stage-badge {
  padding: 0.65rem 1rem;
  border-radius: 999px;
  background: rgba(8, 20, 31, 0.66);
  border: 1px solid rgba(255, 241, 219, 0.26);
  letter-spacing: 0.08em;
}
</style>
