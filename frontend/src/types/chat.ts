export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  streaming?: boolean
  meta?: string
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

export type ClientSocketMessage =
  | SocketHelloMessage
  | SocketTextMessage
  | SocketAudioChunkMessage
  | SocketAudioEndMessage
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
  | TextDoneEvent
  | AudioDoneEvent
  | DoneEvent
  | ErrorEvent
  | PongEvent
