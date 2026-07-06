import test from 'node:test'
import assert from 'node:assert/strict'

import {
  DEFAULT_STREAM_AUDIO_POLICY,
  shouldResetBufferedPlayback,
  shouldStartBufferedPlayback,
} from '../src/lib/streamAudioBuffer.ts'

test('uses the updated default stream audio policy', () => {
  assert.deepEqual(DEFAULT_STREAM_AUDIO_POLICY, {
    initialBufferMs: 450,
    initialChunkCount: 1,
    minScheduledLeadMs: 220,
    scheduleLookaheadMs: 30,
  })
})

test('does not start buffered playback before any audio is queued', () => {
  const shouldStart = shouldStartBufferedPlayback(
    {
      bufferedAudioMs: 440,
      pendingChunkCount: 0,
      isFinalChunkBuffered: false,
    },
    DEFAULT_STREAM_AUDIO_POLICY,
  )

  assert.equal(shouldStart, false)
})

test('starts buffered playback when one chunk is already queued', () => {
  const shouldStart = shouldStartBufferedPlayback(
    {
      bufferedAudioMs: 120,
      pendingChunkCount: 1,
      isFinalChunkBuffered: false,
    },
    DEFAULT_STREAM_AUDIO_POLICY,
  )

  assert.equal(shouldStart, true)
})

test('starts buffered playback when buffered audio exceeds the initial threshold', () => {
  const shouldStart = shouldStartBufferedPlayback(
    {
      bufferedAudioMs: 460,
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
