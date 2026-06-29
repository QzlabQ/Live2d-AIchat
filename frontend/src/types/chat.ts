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
}

export type EmotionValue = 'neutral' | 'happy' | 'thinking' | 'excited' | 'sad'

export interface SocketTextMessage {
  type: 'text'
  content: string
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
  seq: number
}

export interface PhonemesEvent {
  type: 'phonemes'
  seq: number
  data: PhonemeFrame[]
}

export interface EmotionEvent {
  type: 'emotion'
  value: EmotionValue
}

export interface DoneEvent {
  type: 'done'
  session_id: string
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
  | PhonemesEvent
  | EmotionEvent
  | DoneEvent
  | ErrorEvent
  | PongEvent
