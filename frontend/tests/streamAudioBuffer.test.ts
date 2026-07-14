import { describe, expect, it } from 'vitest'

import {
  DEFAULT_STREAM_AUDIO_POLICY,
  shouldResetBufferedPlayback,
  shouldStartBufferedPlayback,
} from '../src/lib/streamAudioBuffer'

describe('streamAudioBuffer', () => {
  it('uses the stable default stream audio policy', () => {
    expect(DEFAULT_STREAM_AUDIO_POLICY).toEqual({
      initialBufferMs: 1800,
      initialChunkCount: 3,
      minScheduledLeadMs: 1000,
      scheduleLookaheadMs: 30,
    })
  })

  it('does not start buffered playback before any audio is queued', () => {
    const shouldStart = shouldStartBufferedPlayback(
      {
        bufferedAudioMs: 440,
        pendingChunkCount: 0,
        isFinalChunkBuffered: false,
      },
      DEFAULT_STREAM_AUDIO_POLICY,
    )

    expect(shouldStart).toBe(false)
  })

  it('does not start early when the stable thresholds are not met', () => {
    const shouldStart = shouldStartBufferedPlayback(
      {
        bufferedAudioMs: 1799,
        pendingChunkCount: 2,
        isFinalChunkBuffered: false,
      },
      DEFAULT_STREAM_AUDIO_POLICY,
    )

    expect(shouldStart).toBe(false)
  })

  it('starts buffered playback when three chunks are queued', () => {
    const shouldStart = shouldStartBufferedPlayback(
      {
        bufferedAudioMs: 240,
        pendingChunkCount: 3,
        isFinalChunkBuffered: false,
      },
      DEFAULT_STREAM_AUDIO_POLICY,
    )

    expect(shouldStart).toBe(true)
  })

  it('starts buffered playback when buffered audio exceeds the initial threshold', () => {
    const shouldStart = shouldStartBufferedPlayback(
      {
        bufferedAudioMs: 1800,
        pendingChunkCount: 1,
        isFinalChunkBuffered: false,
      },
      DEFAULT_STREAM_AUDIO_POLICY,
    )

    expect(shouldStart).toBe(true)
  })

  it('starts buffered playback for the final chunk even below the stable thresholds', () => {
    const shouldStart = shouldStartBufferedPlayback(
      {
        bufferedAudioMs: 120,
        pendingChunkCount: 1,
        isFinalChunkBuffered: true,
      },
      DEFAULT_STREAM_AUDIO_POLICY,
    )

    expect(shouldStart).toBe(true)
  })

  it('resets buffered playback when scheduled lead has already drained', () => {
    expect(shouldResetBufferedPlayback(0)).toBe(true)
    expect(shouldResetBufferedPlayback(-15)).toBe(true)
    expect(shouldResetBufferedPlayback(120)).toBe(false)
  })
})
