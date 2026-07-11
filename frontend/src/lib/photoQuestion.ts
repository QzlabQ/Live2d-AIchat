export interface PhotoRecognitionDraft {
  recognizedSpot: string
  recognitionSummary: string
  resolvedQuestion?: string
}

export function buildPhotoQuestion(payload: PhotoRecognitionDraft) {
  if (payload.resolvedQuestion?.trim()) {
    return payload.resolvedQuestion.trim()
  }

  const spot = payload.recognizedSpot.trim()
  const summary = payload.recognitionSummary.trim()

  if (!summary) {
    return `我拍到的是${spot}吗？可以介绍一下吗？`
  }

  return `我拍到的可能是${spot}。${summary}，可以继续介绍一下吗？`
}

export function shouldEnterThinkingForPhoto(state: {
  uploading: boolean
  recognizing: boolean
}) {
  return state.uploading || state.recognizing
}
