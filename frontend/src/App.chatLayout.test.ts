import { readFileSync } from 'node:fs'

import { describe, expect, test } from 'vitest'

const appSource = readFileSync(new URL('./App.vue', import.meta.url), 'utf-8')

describe('App chat layout', () => {
  test('keeps transcript scroll region separate from bottom composer dock', () => {
    expect(appSource).toContain('class="chat-panel-body"')
    expect(appSource).toContain('class="chat-panel-scroll"')
    expect(appSource).toContain('class="chat-panel-dock"')

    expect(appSource).toMatch(
      /<div class="chat-panel-body">[\s\S]*<div class="chat-panel-scroll">[\s\S]*<ChatTranscript[\s\S]*<\/div>[\s\S]*<div class="chat-panel-dock">[\s\S]*<ChatComposer/s,
    )
  })

  test('visitor stage exposes display controls without moving the composer dock', () => {
    expect(appSource).toContain('<AvatarDisplayControls')
    expect(appSource).toContain('visitorDisplayControlsOpen')
    expect(appSource).toContain("if (avatarProfilesLoading.value && avatarProfiles.value.length === 0)")
    expect(appSource).toContain(':key="currentModelPath"')
    expect(appSource).toContain('v-if="currentModelPath"')
    expect(appSource).toContain(':model-scale="avatarDisplayConfig.displayScale"')
    expect(appSource).toContain(':show-offset-x="false"')
    expect(appSource).toContain(':show-offset-y="false"')
    expect(appSource).toContain(':show-stage-height="false"')
    expect(appSource).toContain(':style="stageCardStyle"')
    expect(appSource).toContain('chat-panel-dock')
  })
})
