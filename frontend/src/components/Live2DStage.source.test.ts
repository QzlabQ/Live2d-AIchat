import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

describe('Live2DStage source contracts', () => {
  it('resets expression targets and emotion parameter cache when model runtime is rebuilt', () => {
    const source = readFileSync(new URL('./Live2DStage.vue', import.meta.url), 'utf8')

    expect(source).toContain('function resetExpressionState()')
    expect(source).toContain('Object.keys(expressionTargets)')
    expect(source).toContain('delete expressionTargets[key]')
    expect(source).toContain('Object.keys(currentEmotionValues)')
    expect(source).toContain('delete currentEmotionValues[key]')
    expect(source).toContain('resetExpressionState()')
  })

  it('gives mouth ownership to active local lip sync playback', () => {
    const source = readFileSync(new URL('./Live2DStage.vue', import.meta.url), 'utf8')

    expect(source).toContain('isLipSyncPlaybackActive(lipSyncState)')
    expect(source).toContain('beforeModelUpdate')
    expect(source).toContain('applyCurrentMouthPose()')
    expect(source).not.toContain('function isSpeakingLipSyncActive()')
    expect(source).not.toContain('currentAvatarPresentation.lipSyncActive')
  })

  it('does not keep overriding mouth pose while lip sync is inactive', () => {
    const source = readFileSync(new URL('./Live2DStage.vue', import.meta.url), 'utf8')

    expect(source).not.toContain('setMouthPose(0.06 + Math.sin')
  })

  it('does not globally freeze live2d motions to protect lip sync', () => {
    const source = readFileSync(new URL('./Live2DStage.vue', import.meta.url), 'utf8')

    expect(source).not.toContain('stopAllMotions()')
    expect(source).not.toContain('groups.idle')
  })

  it('surfaces a friendly error when model settings resolve to html or invalid json', () => {
    const source = readFileSync(new URL('./Live2DStage.vue', import.meta.url), 'utf8')

    expect(source).toContain("contentType.includes('text/html')")
    expect(source).toContain('返回了 HTML 页面，请检查模型路径或 nginx 的 /live2d/ 静态映射')
    expect(source).toContain('模型配置不是有效的 JSON 文件')
  })
})
