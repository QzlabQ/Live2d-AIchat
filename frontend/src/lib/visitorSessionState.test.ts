import { describe, expect, it } from 'vitest'

import {
  canToggleRecording,
  canSwitchSessionWhileIdle,
  isReplyFlowActiveForSessionSwitch,
  mapHistoryMessagesToChatMessages,
  normalizeVisitorMessageRole,
  sortSessionSummaries,
} from './visitorSessionState'

describe('sortSessionSummaries', () => {
  it('sorts sessions by updatedAt descending', () => {
    const items = sortSessionSummaries([
      { sessionId: 'a', updatedAt: '2026-07-07T10:00:00Z' },
      { sessionId: 'b', updatedAt: '2026-07-07T11:00:00Z' },
    ])

    expect(items[0].sessionId).toBe('b')
  })
})

describe('normalizeVisitorMessageRole', () => {
  it('accepts supported history message roles', () => {
    expect(normalizeVisitorMessageRole('assistant')).toBe('assistant')
    expect(normalizeVisitorMessageRole('user')).toBe('user')
    expect(normalizeVisitorMessageRole('system')).toBe('system')
  })

  it('rejects unsupported history message roles', () => {
    expect(() => normalizeVisitorMessageRole('moderator')).toThrow(
      'Unsupported visitor session message role: moderator',
    )
  })
})

describe('mapHistoryMessagesToChatMessages', () => {
  it('maps backend session messages into chat bubbles', () => {
    const messages = mapHistoryMessagesToChatMessages([
      {
        id: 1,
        role: 'user',
        content: '开放时间是什么时候？',
        createdAt: '2026-07-07T10:00:00Z',
        attachments: [],
      },
      {
        id: 2,
        role: 'assistant',
        content: '景区整体一般是 9:00-21:30。',
        createdAt: '2026-07-07T10:00:01Z',
        attachments: [],
      },
    ])

    expect(messages[0].role).toBe('user')
    expect(messages[1].role).toBe('assistant')
    expect(messages[1].content).toContain('9:00-21:30')
  })
})

describe('canSwitchSessionWhileIdle', () => {
  it('blocks switching when a reply is still streaming', () => {
    expect(canSwitchSessionWhileIdle({ isStreaming: true, isRecording: false })).toBe(false)
  })

  it('allows switching when streaming and recording are both idle', () => {
    expect(canSwitchSessionWhileIdle({ isStreaming: false, isRecording: false })).toBe(true)
  })
})

describe('canToggleRecording', () => {
  it('keeps the record button enabled while recording so the user can stop manually', () => {
    expect(
      canToggleRecording({
        isSupported: true,
        isConnected: true,
        sessionBooting: false,
        canCancelReply: true,
        replyCanceling: false,
        isRecording: true,
      }),
    ).toBe(true)
  })

  it('blocks starting a new recording while a cancellable reply is active', () => {
    expect(
      canToggleRecording({
        isSupported: true,
        isConnected: true,
        sessionBooting: false,
        canCancelReply: true,
        replyCanceling: false,
        isRecording: false,
      }),
    ).toBe(false)
  })
})

describe('isReplyFlowActiveForSessionSwitch', () => {
  it('blocks switching while a reply is pending even before audio or text arrives', () => {
    expect(
      isReplyFlowActiveForSessionSwitch({
        replyPending: true,
        isPhotoPending: false,
        assistantDraftActive: false,
        avatarSpeechActive: false,
        queuedAudioCount: 0,
        bufferedAudioMs: 0,
        scheduledLeadMs: 0,
      }),
    ).toBe(true)
  })

  it('allows switching again once no reply or photo work remains', () => {
    expect(
      isReplyFlowActiveForSessionSwitch({
        replyPending: false,
        isPhotoPending: false,
        assistantDraftActive: false,
        avatarSpeechActive: false,
        queuedAudioCount: 0,
        bufferedAudioMs: 0,
        scheduledLeadMs: 0,
      }),
    ).toBe(false)
  })
})
