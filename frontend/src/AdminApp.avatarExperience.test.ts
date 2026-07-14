import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

describe('Admin avatar experience source contract', () => {
  const adminSource = readFileSync(new URL('./AdminApp.vue', import.meta.url), 'utf-8')
  const panelSource = readFileSync(
    new URL('./components/AdminEmotionPreviewPanel.vue', import.meta.url),
    'utf-8',
  )

  it('wires avatar display controls and admin preview presentation into AdminApp', () => {
    expect(adminSource).toContain('<AvatarDisplayControls')
    expect(adminSource).toContain('<AdminEmotionPreviewPanel')
    expect(adminSource).toContain('adminPreviewPresentation')
    expect(adminSource).toContain(':model-scale="avatarForm.displayScale"')
  })

  it('offers emotion preview presets in the admin panel', () => {
    expect(panelSource).toContain('neutral')
    expect(panelSource).toContain('happy')
    expect(panelSource).toContain('thinking')
    expect(panelSource).toContain('excited')
    expect(panelSource).toContain('sad')
    expect(panelSource).toContain('<EmotionLamp')
    expect(panelSource).toContain('EMOTION_PRESETS')
  })
})
