import { describe, expect, it } from 'vitest'

import { buildComposerQuickHints } from './chatComposerMode'

describe('buildComposerQuickHints', () => {
  it('returns default chat hints in normal chat mode', () => {
    expect(
      buildComposerQuickHints('chat', {
        selectedTags: [],
        recommendation: null,
      }),
    ).toEqual([
      '这里有什么历史故事？',
      '第一次来应该怎么逛？',
      '开放时间是什么时候？',
    ])
  })

  it('prefers recommendation suggested questions in route mode', () => {
    expect(
      buildComposerQuickHints('route', {
        selectedTags: ['亲子', '轻松'],
        recommendation: {
          routeTitle: '亲子轻松路线',
          intro: '先看核心演出，再去轻松互动点位。',
          highlights: ['九龙灌浴'],
          suggestedQuestions: ['亲子半天路线怎么走？', '晚上还适合继续逛吗？'],
          appliedInterestTags: ['亲子', '轻松'],
        },
      }),
    ).toEqual(['亲子半天路线怎么走？', '晚上还适合继续逛吗？'])
  })

  it('builds route-oriented fallback hints from selected tags when no recommendation exists', () => {
    expect(
      buildComposerQuickHints('route', {
        selectedTags: ['亲子', '夜游'],
        recommendation: null,
      }),
    ).toEqual([
      '按亲子 / 夜游偏好怎么安排路线？',
      '第一次来适合先去哪里？',
      '半天路线怎么走更顺？',
    ])
  })

  it('keeps route mode fallback hints when no recommendation card is pinned above transcript', () => {
    expect(
      buildComposerQuickHints('route', {
        selectedTags: ['亲子'],
        recommendation: null,
      }),
    ).toEqual([
      '按亲子偏好怎么安排路线？',
      '第一次来适合先去哪里？',
      '半天路线怎么走更顺？',
    ])
  })
})
