import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

describe('Admin knowledge gap dashboard source contract', () => {
  const adminSource = readFileSync(new URL('./AdminApp.vue', import.meta.url), 'utf-8')

  it('renders a visual status distribution chart instead of only plain chips', () => {
    expect(adminSource).toContain('admin-gap-distribution-chart')
    expect(adminSource).toContain('knowledgeGapStatusDistribution')
  })

  it('keeps the knowledge gap page refreshed on an interval without overwriting active edits', () => {
    expect(adminSource).toContain('KNOWLEDGE_GAP_AUTO_REFRESH_MS')
    expect(adminSource).toContain('window.setInterval')
    expect(adminSource).toContain('knowledgeGapEditorDirty')
  })
})
