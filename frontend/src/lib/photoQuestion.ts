export interface PhotoRecognitionDraft {
  recognizedSpot: string
  recognitionSummary: string
}

export function buildPhotoQuestion(payload: PhotoRecognitionDraft) {
  const spot = payload.recognizedSpot.trim()
  const summary = payload.recognitionSummary.trim()

  if (!summary) {
    return `我拍到的是${spot}吗？可以介绍一下吗？`
  }

  return `我拍到的可能是${spot}。${summary}，可以继续介绍一下吗？`
}
