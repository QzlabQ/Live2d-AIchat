import { readFileSync } from 'node:fs'

import { describe, expect, test } from 'vitest'

const appSource = readFileSync(new URL('./App.vue', import.meta.url), 'utf-8')
const composerSource = readFileSync(new URL('./components/ChatComposer.vue', import.meta.url), 'utf-8')
const transcriptSource = readFileSync(new URL('./components/ChatTranscript.vue', import.meta.url), 'utf-8')

describe('App route mode layout', () => {
  test('does not render route tools above transcript and exposes route composer events', () => {
    expect(appSource).not.toContain('<div v-if="composerMode === \'route\'" class="visitor-tools">')
    expect(appSource).toContain('@toggle-route-tag="handleToggleInterestTag"')
    expect(appSource).toContain('@generate-route="handleGenerateRecommendation"')
  })

  test('composer source includes route mode panel and generation affordance', () => {
    expect(composerSource).toContain('class="composer-mode-banner"')
    expect(composerSource).toContain('<InterestTagPanel')
    expect(composerSource).toContain("emit('generateRoute')")
  })

  test('transcript source renders route recommendation card branch', () => {
    expect(transcriptSource).toContain('RouteRecommendationCard')
    expect(transcriptSource).toContain("message.toolResult?.kind === 'route_recommendation'")
    expect(transcriptSource).toContain("@ask=\"emit('askToolAction', $event)\"")
  })
})
