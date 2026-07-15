import { describe, expect, it } from 'vitest'

import {
  DEFAULT_STREAM_AUDIO_POLICY,
  shouldResetBufferedPlayback,
  shouldStartBufferedPlayback,
} from '../src/lib/streamAudioBuffer'

describe('streamAudioBuffer', () => {
  it('uses the stable default stream audio policy', () => {
    expect(DEFAULT_STREAM_AUDIO_POLICY).toEqual({
      initialBufferMs: 3000,
      initialChunkCount: 2,
      minScheduledLeadMs: 1500,
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
        bufferedAudioMs: 2999,
        pendingChunkCount: 1,
        isFinalChunkBuffered: false,
      },
      DEFAULT_STREAM_AUDIO_POLICY,
    )

    expect(shouldStart).toBe(false)
  })

  it('starts buffered playback when two chunks are queued', () => {
    const shouldStart = shouldStartBufferedPlayback(
      {
        bufferedAudioMs: 240,
        pendingChunkCount: 2,
        isFinalChunkBuffered: false,
      },
      DEFAULT_STREAM_AUDIO_POLICY,
    )

    expect(shouldStart).toBe(true)
  })

  it('starts buffered playback when buffered audio exceeds the initial threshold', () => {
    const shouldStart = shouldStartBufferedPlayback(
      {
        bufferedAudioMs: 3000,
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

  it('resets buffered playback when lead is drained and the rebuffer target is not met', () => {
    expect(
      shouldResetBufferedPlayback(
        {
          bufferedAudioMs: 200,
          pendingChunkCount: 1,
          isFinalChunkBuffered: false,
        },
        0,
        DEFAULT_STREAM_AUDIO_POLICY,
      ),
    ).toBe(true)
    expect(
      shouldResetBufferedPlayback(
        {
          bufferedAudioMs: 1600,
          pendingChunkCount: 2,
          isFinalChunkBuffered: false,
        },
        -15,
        DEFAULT_STREAM_AUDIO_POLICY,
      ),
    ).toBe(false)
    expect(
      shouldResetBufferedPlayback(
        {
          bufferedAudioMs: 200,
          pendingChunkCount: 1,
          isFinalChunkBuffered: false,
        },
        120,
        DEFAULT_STREAM_AUDIO_POLICY,
      ),
    ).toBe(false)
  })

  it('does not reset buffered playback for the final chunk even after lead drains', () => {
    expect(
      shouldResetBufferedPlayback(
        {
          bufferedAudioMs: 120,
          pendingChunkCount: 1,
          isFinalChunkBuffered: true,
        },
        0,
        DEFAULT_STREAM_AUDIO_POLICY,
      ),
    ).toBe(false)
  })
})
