# Lava Lamp Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine the existing emotion lava lamp so `preview` reads softer than `final`, while each emotion keeps a stable but distinct visual personality.

**Architecture:** Extract lamp visual decisions into a small pure helper that maps `emotion + stage` to CSS variables. Keep the existing card markup, bind those variables from `App.vue`, and let `style.css` drive the motion and glow with CSS animations.

**Tech Stack:** Vue 3, TypeScript, Node built-in test runner, Vite

---

### Task 1: Add a testable lamp visual helper

**Files:**
- Create: `frontend/src/lib/emotionLamp.ts`
- Create: `frontend/tests/emotionLamp.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import test from 'node:test'
import assert from 'node:assert/strict'

import { buildEmotionLampStyle } from '../src/lib/emotionLamp.ts'

test('preview is softer than final for the same emotion', () => {
  const preview = buildEmotionLampStyle({
    value: 'happy',
    stage: 'preview',
    confidence: 0.8,
    keywords: [],
    reason: '',
    source: 'heuristic',
  })
  const final = buildEmotionLampStyle({
    value: 'happy',
    stage: 'final',
    confidence: 0.8,
    keywords: [],
    reason: '',
    source: 'heuristic',
  })

  assert.equal(preview['--lamp-stage'], 'preview')
  assert.equal(final['--lamp-stage'], 'final')
  assert.ok(Number(preview['--lamp-glow-alpha']) < Number(final['--lamp-glow-alpha']))
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test --experimental-strip-types frontend/tests/emotionLamp.test.ts`
Expected: FAIL because `buildEmotionLampStyle` does not exist yet

- [ ] **Step 3: Write minimal implementation**

```ts
export function buildEmotionLampStyle(telemetry) {
  return {
    '--lamp-stage': telemetry.stage,
    '--lamp-glow-alpha': telemetry.stage === 'preview' ? '0.38' : '0.52',
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test --experimental-strip-types frontend/tests/emotionLamp.test.ts`
Expected: PASS

### Task 2: Bind lamp variables into the Vue view

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/types/chat.ts`
- Modify: `frontend/src/lib/lipsync.ts`
- Create/Modify: `frontend/src/lib/emotionLamp.ts`

- [ ] **Step 1: Write the failing test for emotion personalities**

```ts
test('excited is brighter than sad and thinking moves slower than happy', () => {
  const excited = buildEmotionLampStyle({
    value: 'excited',
    stage: 'final',
    confidence: 0.9,
    keywords: [],
    reason: '',
    source: 'llm',
  })
  const sad = buildEmotionLampStyle({
    value: 'sad',
    stage: 'final',
    confidence: 0.9,
    keywords: [],
    reason: '',
    source: 'llm',
  })
  const thinking = buildEmotionLampStyle({
    value: 'thinking',
    stage: 'final',
    confidence: 0.9,
    keywords: [],
    reason: '',
    source: 'llm',
  })
  const happy = buildEmotionLampStyle({
    value: 'happy',
    stage: 'final',
    confidence: 0.9,
    keywords: [],
    reason: '',
    source: 'llm',
  })

  assert.ok(Number(excited['--lamp-glow-alpha']) > Number(sad['--lamp-glow-alpha']))
  assert.ok(parseFloat(thinking['--lamp-wave-duration']) > parseFloat(happy['--lamp-wave-duration']))
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test --experimental-strip-types frontend/tests/emotionLamp.test.ts`
Expected: FAIL because the helper does not yet encode the full personality rules

- [ ] **Step 3: Write minimal implementation**

```ts
const PERSONALITIES = {
  happy: { glow: 0.5, wave: 3.4 },
  thinking: { glow: 0.42, wave: 4.1 },
  excited: { glow: 0.6, wave: 3.0 },
  sad: { glow: 0.34, wave: 4.6 },
  neutral: { glow: 0.4, wave: 3.8 },
}
```

- [ ] **Step 4: Bind the helper into `App.vue`**

```ts
const emotionLampStyle = computed(() => buildEmotionLampStyle(emotionTelemetry.value))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `node --test --experimental-strip-types frontend/tests/emotionLamp.test.ts`
Expected: PASS

### Task 3: Update CSS animations to consume the new variables

**Files:**
- Modify: `frontend/src/style.css`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Keep markup stable and add stage attribute**

```vue
<div class="emotion-lamp" :data-stage="emotionTelemetry.stage" :style="emotionLampStyle">
```

- [ ] **Step 2: Add CSS variable-driven animation tuning**

```css
.emotion-lamp {
  opacity: var(--lamp-shell-opacity);
  animation:
    lamp-float var(--lamp-float-duration) ease-in-out infinite,
    lamp-pulse var(--lamp-pulse-duration) ease-in-out infinite;
}
```

- [ ] **Step 3: Run build verification**

Run: `npm run build`
Expected: PASS

### Task 4: Final verification

**Files:**
- No additional file requirements

- [ ] **Step 1: Run focused helper tests**

Run: `node --test --experimental-strip-types frontend/tests/emotionLamp.test.ts`
Expected: PASS

- [ ] **Step 2: Run full frontend build**

Run: `npm run build`
Expected: PASS
