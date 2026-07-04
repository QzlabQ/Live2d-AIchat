<script setup lang="ts">
import * as PIXI from 'pixi.js'
import { Live2DModel } from 'pixi-live2d-display/cubism4'
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { EMOTION_PRESETS, currentPhoneme, finalFrameEnd, mouthPoseFromFrame } from '../lib/lipsync'
import type { EmotionValue, PhonemeFrame } from '../types/chat'

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
    Motions?: Record<string, Array<{ File: string; Sound?: string }>>
  }
}

interface LipSyncState {
  frames: PhonemeFrame[]
  audio: HTMLAudioElement | null
  startedAt: number
  stopAt: number
}

const props = defineProps<{
  modelPath: string
}>()

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
const EMOTION_PARAM_IDS = Array.from(
  new Set(
    Object.values(EMOTION_PRESETS).flatMap((preset) => Object.keys(preset)),
  ),
)
const currentEmotionValues: Record<string, number> = {}
let targetEmotionValues: Record<string, number> = { ...EMOTION_PRESETS.neutral }

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
  const modelWidth = Math.max(bounds.width || 1, 1)
  const modelHeight = Math.max(bounds.height || 1, 1)
  const isCompact = clientWidth < 720
  const widthRatio = isCompact ? 0.82 : 0.74
  const heightRatio = isCompact ? 0.84 : 0.78
  const scale = Math.min((clientWidth * widthRatio) / modelWidth, (clientHeight * heightRatio) / modelHeight)

  model.scale.set(scale)
  model.pivot.set(bounds.x + modelWidth / 2, bounds.y + modelHeight * 0.82)
  model.position.set(clientWidth / 2, clientHeight * (isCompact ? 0.94 : 0.92))
}

function playIdleMotion() {
  if (!model) {
    return
  }

  window.clearInterval(idleTimer)
  idleTimer = window.setInterval(() => {
    if (!model) {
      return
    }

    try {
      model.motion('Idle')
    } catch {
      return
    }
  }, 12000)
}

function startBreathingLoop() {
  pixiApp?.ticker.add(() => {
    if (!model) {
      return
    }

    const t = performance.now() / 1000
    safeSetParameter('ParamBreath', (Math.sin(t * 1.2) + 1) / 2)

    for (const id of EMOTION_PARAM_IDS) {
      const current = currentEmotionValues[id] ?? 0
      const target = targetEmotionValues[id] ?? 0
      const next = current + (target - current) * 0.18
      currentEmotionValues[id] = next
      safeSetParameter(id, next)
    }

    if (lipSyncState) {
      const { frames, audio, startedAt, stopAt } = lipSyncState
      const elapsed =
        audio && Number.isFinite(audio.currentTime) && audio.currentTime > 0
          ? audio.currentTime
          : (performance.now() - startedAt) / 1000
      const frame = currentPhoneme(frames, elapsed)
      const target = mouthPoseFromFrame(frame)
      setMouthPose(target.openY, target.form)

      if (elapsed <= stopAt && !audio?.ended) {
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

  model = (await Live2DModel.from(settings)) as RuntimeLive2DModel
  model.interactive = true
  model.cursor = 'pointer'
  model.on('pointertap', () => {
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

  stageHost.value.appendChild(pixiApp.view as HTMLCanvasElement)
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

function setEmotion(emotion: EmotionValue) {
  const preset = EMOTION_PRESETS[emotion] ?? EMOTION_PRESETS.neutral
  targetEmotionValues = {
    ...EMOTION_PRESETS.neutral,
    ...preset,
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
    startedAt: performance.now(),
    stopAt: finalFrameEnd(frames) + 0.18,
  }
}

defineExpose({
  setEmotion,
  playPhonemes,
})

onMounted(async () => {
  try {
    await createModel()
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : 'Live2D model loading failed.'
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  window.clearInterval(idleTimer)
  lipSyncState = null
  resizeObserver?.disconnect()
  pixiApp?.destroy(true, { children: true })
  pixiApp = null
  model = null
})
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
