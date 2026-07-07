export interface StreamAudioPolicy {
  initialBufferMs: number
  initialChunkCount: number
  minScheduledLeadMs: number
  scheduleLookaheadMs: number
}

export interface BufferedPlaybackState {
  bufferedAudioMs: number
  pendingChunkCount: number
  isFinalChunkBuffered: boolean
}

export const DEFAULT_STREAM_AUDIO_POLICY: StreamAudioPolicy = {
  initialBufferMs: 450,
  initialChunkCount: 1,
  minScheduledLeadMs: 220,
  scheduleLookaheadMs: 30,
}

export function shouldStartBufferedPlayback(
  state: BufferedPlaybackState,
  policy: StreamAudioPolicy = DEFAULT_STREAM_AUDIO_POLICY,
) {
  if (state.pendingChunkCount <= 0) {
    return false
  }

  if (state.pendingChunkCount >= policy.initialChunkCount) {
    return true
  }

  if (state.bufferedAudioMs >= policy.initialBufferMs) {
    return true
  }

  return state.isFinalChunkBuffered
}

export function shouldResetBufferedPlayback(scheduledLeadMs: number) {
  return scheduledLeadMs <= 0
}

export function getScheduledLeadMs(currentTime: number, nextStartTime: number) {
  return Math.max(0, Math.round((nextStartTime - currentTime) * 1000))
}
