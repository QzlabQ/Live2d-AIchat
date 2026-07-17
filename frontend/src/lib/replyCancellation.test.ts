import { describe, expect, it } from 'vitest'

import { discardReplyMessages, hasCancellableReplyActivity, shouldIgnoreReplyEventWhileCancelling } from './replyCancellation'

describe('hasCancellableReplyActivity', () => {
  it('returns true while reply generation is still pending', () => {
    expect(
      hasCancellableReplyActivity({
        replyPending: true,
        assistantDraftActive: false,
        avatarSpeechActive: false,
        queuedAudioCount: 0,
        bufferedAudioMs: 0,
        scheduledLeadMs: 0,
        currentAudioActive: false,
        pendingStreamAudioCount: 0,
        scheduledSourceCount: 0,
      }),
    ).toBe(true)
  })

  it('returns true while audio playback is still draining', () => {
    expect(
      hasCancellableReplyActivity({
        replyPending: false,
        assistantDraftActive: false,
        avatarSpeechActive: false,
        queuedAudioCount: 0,
        bufferedAudioMs: 0,
        scheduledLeadMs: 0,
        currentAudioActive: true,
        pendingStreamAudioCount: 0,
        scheduledSourceCount: 0,
      }),
    ).toBe(true)
  })

  it('returns false once reply generation and playback are both idle', () => {
    expect(
      hasCancellableReplyActivity({
        replyPending: false,
        assistantDraftActive: false,
        avatarSpeechActive: false,
        queuedAudioCount: 0,
        bufferedAudioMs: 0,
        scheduledLeadMs: 0,
        currentAudioActive: false,
        pendingStreamAudioCount: 0,
        scheduledSourceCount: 0,
      }),
    ).toBe(false)
  })
})

describe('shouldIgnoreReplyEventWhileCancelling', () => {
  it('ignores streaming reply payloads until cancellation is acknowledged', () => {
    expect(
      shouldIgnoreReplyEventWhileCancelling({
        type: 'text_delta',
        content: 'still arriving',
      }),
    ).toBe(true)

    expect(
      shouldIgnoreReplyEventWhileCancelling({
        type: 'tts_audio_chunk',
        reply_id: 'reply-1',
        segment_id: 0,
        chunk_index: 0,
        sample_rate: 24000,
        channels: 1,
        encoding: 'pcm16le',
        data: '',
        is_final: false,
      }),
    ).toBe(true)
  })

  it('keeps cancellation acknowledgements visible to the client', () => {
    expect(
      shouldIgnoreReplyEventWhileCancelling({
        type: 'reply_cancelled',
        session_id: 'session-1',
        had_active_reply: true,
      }),
    ).toBe(false)
  })
})

describe('discardReplyMessages', () => {
  it('removes the tracked user and assistant messages from the chat transcript', () => {
    const messages = discardReplyMessages(
      [
        { id: 'welcome', role: 'assistant', content: 'hello' },
        { id: 'user-1', role: 'user', content: 'tell me more' },
        { id: 'assistant-1', role: 'assistant', content: 'draft', streaming: true },
      ],
      {
        userMessageId: 'user-1',
        assistantMessageId: 'assistant-1',
      },
    )

    expect(messages).toEqual([{ id: 'welcome', role: 'assistant', content: 'hello' }])
  })
})
