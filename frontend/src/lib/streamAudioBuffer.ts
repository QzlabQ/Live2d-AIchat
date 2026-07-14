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

export type StreamAudioPolicyProfile = 'low-latency' | 'balanced' | 'stable';

export const STREAM_AUDIO_POLICIES: Record<StreamAudioPolicyProfile, StreamAudioPolicy> = {
  'low-latency': {
    initialBufferMs: 450,
    initialChunkCount: 1,
    minScheduledLeadMs: 150,
    scheduleLookaheadMs: 30,
  },
  balanced: {
    initialBufferMs: 450,
    initialChunkCount: 2,
    minScheduledLeadMs: 300,
    scheduleLookaheadMs: 30,
  },
  stable: {
    initialBufferMs: 1800,
    initialChunkCount: 3,
    minScheduledLeadMs: 1000,
    scheduleLookaheadMs: 30,
  },
};

// Default to the stability-focused RTX 4060 profile; callers can opt into
// lower latency later without changing the playback decision helpers.
export const DEFAULT_STREAM_AUDIO_POLICY: StreamAudioPolicy = STREAM_AUDIO_POLICIES.stable;

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
