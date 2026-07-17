import { describe, expect, it } from 'vitest';

import { buildStreamPlaybackTelemetry } from './streamAudioBuffer';

describe('buildStreamPlaybackTelemetry', () => {
  it('keeps scheduled lead while stream audio is still buffered or scheduled', () => {
    expect(
      buildStreamPlaybackTelemetry({
        bufferedAudioMs: 1820,
        pendingChunkCount: 0,
        scheduledSourceCount: 1,
        playbackStarted: true,
        currentTime: 10,
        nextStartTime: 10.96,
        underrunCount: 2,
      }),
    ).toEqual({
      bufferedAudioMs: 1820,
      scheduledLeadMs: 960,
      underrunCount: 2,
    });
  });

  it('clears scheduled lead once buffered playback has fully drained', () => {
    expect(
      buildStreamPlaybackTelemetry({
        bufferedAudioMs: 0,
        pendingChunkCount: 0,
        scheduledSourceCount: 0,
        playbackStarted: true,
        currentTime: 10,
        nextStartTime: 10.96,
        underrunCount: 0,
      }),
    ).toEqual({
      bufferedAudioMs: 0,
      scheduledLeadMs: 0,
      underrunCount: 0,
    });
  });
});
