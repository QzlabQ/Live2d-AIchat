import { ref, type Ref } from 'vue'

import { recognizeVisitorPhoto } from '../services/visitorApi'
import type { VisionRecognitionResult } from '../types/visitor'

export function usePhotoRecognition(apiBaseUrl: string, sessionId: Ref<string | null>) {
  const uploading = ref(false)
  const recognizing = ref(false)
  const error = ref('')
  const lastResult = ref<VisionRecognitionResult | null>(null)

  async function recognize(file: File, interestTags: string[], userPrompt?: string) {
    if (!sessionId.value) {
      throw new Error('No active session.')
    }

    uploading.value = true
    recognizing.value = true
    error.value = ''

    try {
      const result = await recognizeVisitorPhoto(apiBaseUrl, sessionId.value, file, interestTags, userPrompt)
      lastResult.value = result
      return result
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : '图片识别失败'
      throw caught
    } finally {
      uploading.value = false
      recognizing.value = false
    }
  }

  function clearResult() {
    lastResult.value = null
    error.value = ''
  }

  return {
    uploading,
    recognizing,
    error,
    lastResult,
    recognize,
    clearResult,
  }
}
