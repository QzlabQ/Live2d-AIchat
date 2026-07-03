import { computed, onBeforeUnmount, ref } from 'vue'

import { arrayBufferToBase64 } from '../lib/base64'

interface UseAudioRecorderOptions {
  onChunk: (payload: { data: string; isFinal: boolean }) => void
  onAudioEnd: () => void
  onError: (message: string) => void
}

type Float32Buffer = Float32Array<ArrayBufferLike>
type Int16Buffer = Int16Array<ArrayBufferLike>

function mergeFloat32Arrays(left: Float32Buffer, right: Float32Buffer): Float32Buffer {
  const merged = new Float32Array(left.length + right.length)
  merged.set(left)
  merged.set(right, left.length)
  return merged
}

function downsampleBuffer(buffer: Float32Buffer, inputRate: number, targetRate: number): Int16Buffer {
  if (inputRate === targetRate) {
    const result = new Int16Array(buffer.length)
    for (let index = 0; index < buffer.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, buffer[index]))
      result[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
    }
    return result
  }

  const ratio = inputRate / targetRate
  const outputLength = Math.max(1, Math.round(buffer.length / ratio))
  const output = new Int16Array(outputLength)
  let offsetBuffer = 0

  for (let index = 0; index < outputLength; index += 1) {
    const nextOffsetBuffer = Math.round((index + 1) * ratio)
    let accumulator = 0
    let count = 0

    for (
      let sampleIndex = offsetBuffer;
      sampleIndex < nextOffsetBuffer && sampleIndex < buffer.length;
      sampleIndex += 1
    ) {
      accumulator += buffer[sampleIndex]
      count += 1
    }

    const sample = Math.max(-1, Math.min(1, accumulator / Math.max(count, 1)))
    output[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
    offsetBuffer = nextOffsetBuffer
  }

  return output
}

export function useAudioRecorder(options: UseAudioRecorderOptions) {
  const isRecording = ref(false)
  const isSupported = computed(
    () =>
      typeof navigator !== 'undefined' &&
      !!navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === 'function' &&
      typeof window.AudioContext !== 'undefined',
  )
  const level = ref(0)

  let stream: MediaStream | null = null
  let audioContext: AudioContext | null = null
  let sourceNode: MediaStreamAudioSourceNode | null = null
  let processorNode: ScriptProcessorNode | null = null
  let sinkNode: GainNode | null = null
  let sourceRemainder: Float32Buffer = new Float32Array(0)
  let pcmRemainder: Int16Buffer = new Int16Array(0)
  let hasCapturedSamples = false

  function cleanupGraph() {
    processorNode?.disconnect()
    sourceNode?.disconnect()
    sinkNode?.disconnect()

    processorNode = null
    sourceNode = null
    sinkNode = null

    stream?.getTracks().forEach((track) => track.stop())
    stream = null

    if (audioContext) {
      void audioContext.close()
      audioContext = null
    }

    sourceRemainder = new Float32Array(0)
    pcmRemainder = new Int16Array(0)
    hasCapturedSamples = false
    level.value = 0
  }

  function flushPcm(finalFlush: boolean) {
    if (!audioContext) {
      return
    }

    const frameSize = 1600
    while (pcmRemainder.length >= frameSize) {
      const frame = pcmRemainder.slice(0, frameSize)
      pcmRemainder = pcmRemainder.slice(frameSize)
      options.onChunk({ data: arrayBufferToBase64(frame.buffer), isFinal: false })
    }

    if (finalFlush) {
      if (pcmRemainder.length > 0) {
        options.onChunk({ data: arrayBufferToBase64(pcmRemainder.buffer), isFinal: true })
        pcmRemainder = new Int16Array(0)
        return
      }

      options.onAudioEnd()
    }
  }

  function stop() {
    if (!isRecording.value) {
      return
    }

    isRecording.value = false

    if (sourceRemainder.length > 0 && audioContext) {
      const downsampled = downsampleBuffer(sourceRemainder, audioContext.sampleRate, 16000)
      const combined = new Int16Array(pcmRemainder.length + downsampled.length)
      combined.set(pcmRemainder)
      combined.set(downsampled, pcmRemainder.length)
      pcmRemainder = combined
      sourceRemainder = new Float32Array(0)
    }

    if (!hasCapturedSamples && pcmRemainder.length === 0) {
      cleanupGraph()
      options.onError('未采集到有效音频，请检查麦克风权限或系统输入设备设置。')
      return
    }

    flushPcm(true)
    cleanupGraph()
  }

  async function start() {
    if (!isSupported.value) {
      options.onError('当前浏览器不支持 MediaRecorder 或麦克风采集。')
      return
    }

    if (isRecording.value) {
      return
    }

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      })

      audioContext = new AudioContext()
      sourceNode = audioContext.createMediaStreamSource(stream)
      processorNode = audioContext.createScriptProcessor(4096, 1, 1)
      sinkNode = audioContext.createGain()
      sinkNode.gain.value = 0

      sourceNode.connect(processorNode)
      processorNode.connect(sinkNode)
      sinkNode.connect(audioContext.destination)

      if (audioContext.state === 'suspended') {
        await audioContext.resume()
      }

      processorNode.onaudioprocess = (event) => {
        if (!isRecording.value || !audioContext) {
          return
        }

        const channelData = event.inputBuffer.getChannelData(0)
        const sampleCopy: Float32Buffer = new Float32Array(channelData.length)
        sampleCopy.set(channelData)
        sourceRemainder = mergeFloat32Arrays(sourceRemainder, sampleCopy)
        hasCapturedSamples = true

        let energy = 0
        for (const value of sampleCopy) {
          energy += value * value
        }
        level.value = Math.min(1, Math.sqrt(energy / sampleCopy.length) * 2.8)

        const sourceFrameSize = Math.max(1, Math.round(audioContext.sampleRate * 0.1))
        while (sourceRemainder.length >= sourceFrameSize) {
          const sourceFrame = sourceRemainder.slice(0, sourceFrameSize)
          sourceRemainder = sourceRemainder.slice(sourceFrameSize)
          const downsampled = downsampleBuffer(sourceFrame, audioContext.sampleRate, 16000)
          const combined = new Int16Array(pcmRemainder.length + downsampled.length)
          combined.set(pcmRemainder)
          combined.set(downsampled, pcmRemainder.length)
          pcmRemainder = combined
          flushPcm(false)
        }
      }

      isRecording.value = true
    } catch (error) {
      const message = error instanceof Error ? error.message : '麦克风启动失败。'
      cleanupGraph()
      options.onError(message)
    }
  }

  onBeforeUnmount(() => {
    stop()
  })

  return {
    isRecording,
    isSupported,
    level,
    start,
    stop,
  }
}
