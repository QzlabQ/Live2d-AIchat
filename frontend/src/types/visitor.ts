export interface VisitorSessionSummary {
  sessionId: string
  createdAt: string
  updatedAt: string
  interestTags: string[]
  messageCount: number
  lastMessagePreview: string
}

export interface VisitorSessionListResponse {
  items: VisitorSessionSummary[]
}

export type VisitorSessionMessageRole = 'user' | 'assistant' | 'system'

export interface VisitorSessionMessage {
  id: number
  role: VisitorSessionMessageRole
  content: string
  createdAt: string
  attachments: VisitorPhotoAttachment[]
}

export interface VisitorSessionMessageListResponse {
  items: VisitorSessionMessage[]
}

export interface VisitorRecommendation {
  routeTitle: string
  intro: string
  highlights: string[]
  suggestedQuestions: string[]
  appliedInterestTags: string[]
}

export interface VisionRecognitionResult {
  recognizedSpot: string
  recognitionSummary: string
  resolvedQuestion: string
  storedImagePath: string
}

export interface VisitorPhotoAttachment {
  kind: 'photo'
  storedImagePath: string
  filename: string
  mimeType: string
  previewUrl: string
  recognizedSpot?: string | null
  recognitionSummary?: string | null
}

export interface VisitorAvatarProfileSummary {
  id: number
  name: string
  slug: string
  isActive: boolean
  modelPath: string
  displayScale: number
  displayOffsetX: number
  displayOffsetY: number
  stageHeight: number
  updatedAt: string
}

export interface VisitorAvatarProfileListResponse {
  items: VisitorAvatarProfileSummary[]
}
