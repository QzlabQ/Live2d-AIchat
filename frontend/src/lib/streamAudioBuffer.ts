export interface StreamAudioPolicy {
  initialBufferMs: number;
  initialChunkCount: number;
  minScheduledLeadMs: number;
  scheduleLookaheadMs: number;
}

export interface BufferedPlaybackState {
  bufferedAudioMs: number;
  pendingChunkCount: number;
  isFinalChunkBuffered: boolean;
}

// initialChunkCount: 2 — wait for 2 streaming chunks before starting playback.
// On RTX 4060, CosyVoice2-0.5B generates at ~0.8x real-time (≈330ms deficit/chunk).
// Two pre-buffered chunks (~2700ms) sustain gap-free playback for ~8 more chunks
// before the first underrun, covering most scenic-guide responses (8–12 chunks).
// Trade-off: first-audio latency increases by ~1.7 s vs. initialChunkCount: 1.
// A100 版本 (5–8x real-time)：generation always outpaces playback,
// so revert for lowest first-audio latency:
//   initialChunkCount: 1,    // 立刻开播，首包延迟最低
//   minScheduledLeadMs: 150, // 余量充足，阈值可放宽
export const DEFAULT_STREAM_AUDIO_POLICY: StreamAudioPolicy = {
  initialBufferMs: 450,
  initialChunkCount: 2,
  minScheduledLeadMs: 300,
  scheduleLookaheadMs: 30,
};

export function shouldStartBufferedPlayback(
  state: BufferedPlaybackState,
  policy: StreamAudioPolicy = DEFAULT_STREAM_AUDIO_POLICY,
) {
  if (state.pendingChunkCount <= 0) {
    return false;
  }

  if (state.pendingChunkCount >= policy.initialChunkCount) {
    return true;
  }

  if (state.bufferedAudioMs >= policy.initialBufferMs) {
    return true;
  }

  return state.isFinalChunkBuffered;
}

export function shouldResetBufferedPlayback(scheduledLeadMs: number) {
  return scheduledLeadMs <= 0;
}

export function getScheduledLeadMs(currentTime: number, nextStartTime: number) {
  return Math.max(0, Math.round((nextStartTime - currentTime) * 1000));
}
