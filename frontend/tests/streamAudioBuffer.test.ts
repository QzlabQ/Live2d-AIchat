import test from 'node:test'
import assert from 'node:assert/strict'

import {
  DEFAULT_STREAM_AUDIO_POLICY,
  shouldResetBufferedPlayback,
  shouldStartBufferedPlayback,
} from '../src/lib/streamAudioBuffer.ts'

test('does not start buffered playback before enough audio is queued', () => {
  const shouldStart = shouldStartBufferedPlayback(
    {
      bufferedAudioMs: 620,
      pendingChunkCount: 1,
      isFinalChunkBuffered: false,
    },
    DEFAULT_STREAM_AUDIO_POLICY,
  )

  assert.equal(shouldStart, false)
})

test('starts buffered playback when two chunks are already queued', () => {
  const shouldStart = shouldStartBufferedPlayback(
    {
      bufferedAudioMs: 620,
      pendingChunkCount: 2,
      isFinalChunkBuffered: false,
    },
    DEFAULT_STREAM_AUDIO_POLICY,
  )

  assert.equal(shouldStart, true)
})

test('starts buffered playback when buffered audio exceeds the initial threshold', () => {
  const shouldStart = shouldStartBufferedPlayback(
    {
      bufferedAudioMs: 950,
      pendingChunkCount: 1,
      isFinalChunkBuffered: false,
    },
    DEFAULT_STREAM_AUDIO_POLICY,
  )

  assert.equal(shouldStart, true)
})

test('resets buffered playback when scheduled lead has already drained', () => {
  assert.equal(shouldResetBufferedPlayback(0), true)
  assert.equal(shouldResetBufferedPlayback(-15), true)
  assert.equal(shouldResetBufferedPlayback(120), false)
})
