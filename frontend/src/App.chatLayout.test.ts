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
})
