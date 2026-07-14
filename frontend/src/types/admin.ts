export interface AdminLoginResponse {
  accessToken: string
  tokenType: string
  expiresIn: number
}

export interface AdminMe {
  username: string
}

export interface Live2DModelOption {
  path: string
  label: string
}

export interface AvatarConfig {
  id: number
  name: string
  slug: string
  isActive: boolean
  modelPath: string
  voiceId: string
  voiceProfileId: string | null
  responseLanguage: 'zh' | 'en'
  persona: string
  ttsReferenceAudioPath: string
  ttsReferenceText: string
  ttsSpeed: number
  ttsEmotionEnabled: boolean
  displayScale: number
  displayOffsetX: number
  displayOffsetY: number
  stageHeight: number
  createdAt: string
  updatedAt: string
}

export interface AvatarConfigUpdate {
  name?: string
  modelPath?: string
  voiceId?: string
  voiceProfileId?: string | null
  responseLanguage?: 'zh' | 'en'
  persona?: string
  ttsReferenceAudioPath?: string
  ttsReferenceText?: string
  ttsSpeed?: number
  ttsEmotionEnabled?: boolean
  displayScale?: number
  displayOffsetX?: number
  displayOffsetY?: number
  stageHeight?: number
}

export interface AvatarProfileSummary {
  id: number
  name: string
  slug: string
  isActive: boolean
  modelPath: string
  voiceId: string
  responseLanguage: 'zh' | 'en'
  displayScale: number
  displayOffsetX: number
  displayOffsetY: number
  stageHeight: number
  updatedAt: string
}

export interface AvatarProfileListResponse {
  items: AvatarProfileSummary[]
}

export interface AvatarProfileCreatePayload {
  name: string
  modelPath: string
  voiceId: string
  responseLanguage: 'zh' | 'en'
  voiceProfileId?: string | null
  persona: string
  ttsReferenceAudioPath: string
  ttsReferenceText: string
  ttsSpeed: number
  ttsEmotionEnabled: boolean
  displayScale?: number
  displayOffsetX?: number
  displayOffsetY?: number
  stageHeight?: number
  activate?: boolean
}

export interface KnowledgeDocItem {
  id: string
  filename: string
  category: string
  storedPath: string
  chunkCount: number
  uploadedAt: string
  status: string
  errorMessage: string
}

export interface KnowledgeDocListResponse {
  total: number
  items: KnowledgeDocItem[]
}

export interface KnowledgeUploadResult {
  docId: string
  status: string
  message: string
}

export interface VoiceProfile {
  id: string
  name: string
  description: string
  sourceFilename: string
  audioPath: string
  referenceText: string
  durationMs: number
  mimeType: string
  isDefault: boolean
  createdAt: string
  updatedAt: string
}

export interface VoiceProfileUploadResult {
  item: VoiceProfile
  message: string
}

export interface MessageResponse {
  message: string
}

export interface AdminSessionSummary {
  sessionId: string
  createdAt: string
  updatedAt: string
  deviceType: string
  interestTags: string[]
  messageCount: number
  lastMessagePreview: string
}

export interface AdminSessionListResponse {
  items: AdminSessionSummary[]
}

export interface AdminSessionMessage {
  id: number
  role: string
  content: string
  createdAt: string
  emotion: string | null
  latencyMs: number | null
}

export interface AdminSessionDetail {
  sessionId: string
  createdAt: string
  updatedAt: string
  deviceType: string
  interestTags: string[]
  messageCount: number
  items: AdminSessionMessage[]
}

export interface DailyEmotionReport {
  reportDate: string
  status: string
  sessionCount: number
  messageCount: number
  userMessageCount: number
  assistantMessageCount: number
  avgAssistantLatencyMs: number | null
  emotionCounts: Record<string, number>
  topInterestTags: string[]
  topKeywords: string[]
  overallSentiment: string
  summaryText: string
  source: string
  generatedAt: string
  updatedAt: string
}

export interface DailyEmotionReportListResponse {
  items: DailyEmotionReport[]
}

export interface ReportRangeSummary {
  dateFrom: string
  dateTo: string
  reportCount: number
  sessionCount: number
  messageCount: number
  userMessageCount: number
  assistantMessageCount: number
  avgAssistantLatencyMs: number | null
  emotionCounts: Record<string, number>
  topInterestTags: string[]
  topKeywords: string[]
  overallSentiment: string
  summaryText: string
}

export interface DashboardQuestionItem {
  question: string
  count: number
}

export interface DashboardSatisfactionTrendPoint {
  date: string
  sessionCount: number
  messageCount: number
  avgLatencyMs: number | null
  score: number | null
}

export interface DashboardServiceTrendPoint {
  date: string
  serviceCount: number
}

export interface DashboardKeywordCloudItem {
  word: string
  count: number
  weight: number
  source: string
}

export interface DashboardOverview {
  period: string
  dateFrom: string
  dateTo: string
  serviceCount: number
  sessionCount: number
  messageCount: number
  userMessageCount: number
  assistantMessageCount: number
  realtimeOnlineCount: number
  avgSatisfaction: number | null
  avgLatencyMs: number | null
  overallSentiment: string
  topQuestions: DashboardQuestionItem[]
  serviceTrend: DashboardServiceTrendPoint[]
  satisfactionTrend: DashboardSatisfactionTrendPoint[]
  topInterestTags: string[]
  topKeywords: string[]
  keywordCloud: DashboardKeywordCloudItem[]
  emotionCounts: Record<string, number>
  summaryText: string
}

export interface DashboardEmotionPoint {
  date: string
  happy: number
  neutral: number
  negative: number
  total: number
  score: number | null
}

export interface DashboardEmotionSummary {
  dateFrom: string
  dateTo: string
  overallSentiment: string
  emotionCounts: Record<string, number>
  trend: DashboardEmotionPoint[]
  summaryText: string
}
