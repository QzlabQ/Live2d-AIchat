export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  streaming?: boolean
  meta?: string
  attachments?: ChatPhotoAttachment[]
  sources?: SourceItem[]
  replyKind?: string
  needsFollowup?: boolean
  toolResult?: ChatToolResult
}

export interface ChatPhotoAttachment {
  kind: 'photo'
  storedImagePath: string
  filename: string
  mimeType: string
  previewUrl: string
  recognizedSpot?: string | null
  recognitionSummary?: string | null
}

export interface RouteRecommendationToolResult {
  kind: 'route_recommendation'
  routeTitle: string
  intro: string
  highlights: string[]
  suggestedQuestions: string[]
  appliedInterestTags: string[]
}

export type ChatToolResult = RouteRecommendationToolResult

export interface SourceItem {
  filename: string
  title: string
  excerpt: string
  category?: string
  chunkIndex?: number
  retrievalScore?: number | null
  rerankScore?: number | null
}

export interface PhonemeFrame {
  ph: string
  start: number
  end: number
  openY?: number
  form?: number
}

export type EmotionValue = 'neutral' | 'happy' | 'thinking' | 'excited' | 'sad'
export type EmotionStage = 'preview' | 'final'
export type ConversationPhase = 'idle' | 'thinking' | 'speaking' | 'cooldown'

export interface EmotionTelemetry {
  value: EmotionValue
  stage: EmotionStage
  confidence: number
  keywords: string[]
  reason: string
  source: 'heuristic' | 'llm'
}

export interface SocketTextMessage {
  type: 'text'
  content: string
  attachments?: SocketPhotoAttachment[]
}

export interface SocketPhotoAttachment {
  kind: 'photo'
  stored_image_path: string
  filename: string
  mime_type: string
}

export interface SocketHelloMessage {
  type: 'hello'
  tts_streaming: boolean
  audio_format: 'pcm16le'
}

export interface SocketAudioChunkMessage {
  type: 'audio_chunk'
  data: string
  is_final?: boolean
}

export interface SocketAudioEndMessage {
  type: 'audio_end'
}

export interface SocketPingMessage {
  type: 'ping'
}

export interface SocketCancelReplyMessage {
  type: 'cancel_reply'
}

export type ClientSocketMessage =
  | SocketHelloMessage
  | SocketTextMessage
  | SocketAudioChunkMessage
  | SocketAudioEndMessage
  | SocketCancelReplyMessage
  | SocketPingMessage

export interface TextDeltaEvent {
  type: 'text_delta'
  content: string
}

export interface AsrResultEvent {
  type: 'asr_result'
  content: string
}

export interface AudioEvent {
  type: 'audio'
  data: string
  mime_type?: string
  seq: number
}

export interface TtsAudioChunkEvent {
  type: 'tts_audio_chunk'
  reply_id: string
  segment_id: number
  chunk_index: number
  sample_rate: number
  channels: number
  encoding: 'pcm16le'
  data: string
  is_final: boolean
}

export interface TtsVisemeChunkEvent {
  type: 'tts_viseme_chunk'
  reply_id: string
  segment_id: number
  chunk_index: number
  offset_ms: number
  frames: PhonemeFrame[]
}

export interface PhonemesEvent {
  type: 'phonemes'
  seq: number
  data: PhonemeFrame[]
}

export interface EmotionEvent {
  type: 'emotion'
  value: EmotionValue
  stage?: EmotionStage
  confidence?: number
  keywords?: string[]
  reason?: string
  source?: 'heuristic' | 'llm'
}

export interface AvatarPhaseEvent {
  type: 'avatar_phase'
  phase: ConversationPhase
  reply_id?: string
  at_ms?: number
  reason?: string
}

export interface ReplyMetaEvent {
  type: 'reply_meta'
  reply_id: string
  reply_kind: string
  needs_followup: boolean
  missing_slots?: string[]
  confidence_note?: string
}

export interface SourcesEvent {
  type: 'sources'
  reply_id: string
  mode?: string
  items: Array<{
    filename: string
    title: string
    excerpt: string
    category?: string
    chunk_index?: number
    retrieval_score?: number | null
    rerank_score?: number | null
  }>
}

export interface DoneEvent {
  type: 'done'
  session_id: string
}

export interface TextDoneEvent {
  type: 'text_done'
  reply_id: string
}

export interface AudioDoneEvent {
  type: 'audio_done'
  reply_id: string
}

export interface ReplyCancelledEvent {
  type: 'reply_cancelled'
  session_id: string
  had_active_reply: boolean
  reason?: string
}

export interface ErrorEvent {
  type: 'error'
  code: string
  message: string
}

export interface PongEvent {
  type: 'pong'
}

export type ServerSocketMessage =
  | TextDeltaEvent
  | AsrResultEvent
  | AudioEvent
  | TtsAudioChunkEvent
  | TtsVisemeChunkEvent
  | PhonemesEvent
  | EmotionEvent
  | AvatarPhaseEvent
  | ReplyMetaEvent
  | SourcesEvent
  | TextDoneEvent
  | AudioDoneEvent
  | ReplyCancelledEvent
  | DoneEvent
  | ErrorEvent
  | PongEvent
