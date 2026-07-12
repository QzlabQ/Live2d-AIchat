# Route Mode Tool Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把路线推荐模式改成 GPT 风格的输入区模式条，并把推荐结果作为结构化工具卡片消息插入聊天流。

**Architecture:** 这次实现只重组前端交互和消息结构，不重写现有推荐接口。`ChatComposer` 负责路线模式条和标签/生成入口，`ChatTranscript` 负责渲染结构化工具结果卡片，`App.vue` 负责把推荐接口结果组装成一条 assistant tool result 消息插入会话流。

**Tech Stack:** Vue 3、TypeScript、Vite、Vitest、现有 `useVisitorRecommendations` / `useVisitorSessions` composables

---

## File Structure

- Modify: `frontend/src/App.vue`
  - 去掉切模式自动生成推荐的副作用
  - 组装路线推荐 tool result 消息并插入 `messages`
  - 只在 composer 处显示路线模式面板，不再在聊天正文顶部挂 `InterestTagPanel`
- Modify: `frontend/src/components/ChatComposer.vue`
  - 加入蓝色路线模式条
  - 在输入区上方承载轻量化 `InterestTagPanel`
  - 新增生成路线、标签切换和面板展开相关 emits
- Modify: `frontend/src/components/InterestTagPanel.vue`
  - 从“顶部常驻大面板”改成“输入区上方轻量模式面板”
  - 去掉推荐结果展示职责，只保留标签与生成入口
- Modify: `frontend/src/components/ChatTranscript.vue`
  - 支持渲染普通文本消息和路线推荐工具卡片消息
- Create: `frontend/src/components/RouteRecommendationCard.vue`
  - 负责路线标题、简介、亮点、已选标签、追问按钮展示
- Create: `frontend/src/components/ToolResultCard.vue`
  - 作为统一工具卡片外壳
- Modify: `frontend/src/types/chat.ts`
  - 为 `ChatMessage` 增加 `toolResult`
- Create: `frontend/src/lib/toolResultMessage.ts`
  - 负责把 `RecommendationCard` 转成结构化 `ChatMessage`
- Modify: `frontend/src/lib/chatComposerMode.ts`
  - 调整路线模式快捷问题生成逻辑，保证它不依赖顶部推荐面板
- Modify: `frontend/src/style.css`
  - 新增模式条、轻量标签面板、工具卡片样式
- Modify: `frontend/src/lib/chatComposerMode.test.ts`
  - 覆盖路线模式快捷问题逻辑
- Create: `frontend/src/lib/toolResultMessage.test.ts`
  - 覆盖推荐结果到 `toolResult` 消息的组装
- Create: `frontend/src/App.routeMode.test.ts`
  - 结构测试，约束不再在聊天正文顶部渲染路线面板，并要求存在 route mode dock 结构

## Task 1: 固定路线模式切换行为

**Files:**
- Modify: `frontend/src/App.vue`
- Test: `frontend/src/App.routeMode.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { readFileSync } from 'node:fs'

import { describe, expect, test } from 'vitest'

const appSource = readFileSync(new URL('./App.vue', import.meta.url), 'utf-8')

describe('App route mode layout', () => {
  test('does not render route tools above transcript and exposes route composer events', () => {
    expect(appSource).not.toContain('<div v-if="composerMode === \'route\'" class="visitor-tools">')
    expect(appSource).toContain('@toggle-route-tag="handleToggleInterestTag"')
    expect(appSource).toContain('@generate-route="handleGenerateRecommendation"')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- --run src/App.routeMode.test.ts`

Expected: FAIL because `App.vue` still contains `visitor-tools` and does not yet expose the new composer events.

- [ ] **Step 3: Write minimal implementation**

在 `frontend/src/App.vue` 中完成这 3 个最小改动：

1. 删除聊天正文顶部的路线面板块：

```vue
<div v-if="composerMode === 'route'" class="visitor-tools">
  <InterestTagPanel
    :selected-tags="recommendationState.selectedInterestTags.value"
    :recommendation="recommendationState.recommendation.value"
    :loading="recommendationState.loading.value"
    :saving="recommendationState.saving.value"
    :error="recommendationState.error.value"
    :disabled="visitorToolsDisabled"
    @toggle-tag="handleToggleInterestTag"
    @refresh="handleGenerateRecommendation"
    @ask-question="handleRecommendationQuestion"
  />
</div>
```

2. 把 `ChatComposer` 调整为承接路线模式交互：

```vue
<ChatComposer
  v-model="composer"
  :quick-hints="quickHints"
  :can-send="canSend"
  :can-record="canRecord"
  :composer-mode="composerMode"
  :can-attach-photo="!photoAttachmentDisabled"
  :can-toggle-route-mode="!!sessionId"
  :is-recording="recorder.isRecording.value"
  :photo-busy="photoRecognition.uploading.value || photoRecognition.recognizing.value"
  :photo-status-title="photoStatusTitle"
  :photo-status-detail="photoStatusDetail"
  :photo-error="photoRecognition.error.value"
  :route-selected-tags="recommendationState.selectedInterestTags.value"
  :route-loading="recommendationState.loading.value"
  :route-saving="recommendationState.saving.value"
  :route-error="recommendationState.error.value"
  :route-disabled="visitorToolsDisabled"
  @switch-mode="switchComposerMode"
  @toggle-route-tag="handleToggleInterestTag"
  @generate-route="handleGenerateRecommendation"
  @pick-photo="handlePhotoPicked"
  @send="sendText"
  @toggle-recording="toggleRecording"
/>
```

3. 去掉 `switchComposerMode()` 中切到路线模式就自动请求推荐的逻辑，保留纯模式切换：

```ts
async function switchComposerMode(mode: ComposerMode) {
  composerMode.value = mode
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- --run src/App.routeMode.test.ts`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.vue frontend/src/App.routeMode.test.ts
git commit -m "refactor: decouple route mode switch from route generation"
```

## Task 2: 在 Composer 中加入路线模式条和轻量标签面板

**Files:**
- Modify: `frontend/src/components/ChatComposer.vue`
- Modify: `frontend/src/components/InterestTagPanel.vue`
- Modify: `frontend/src/style.css`
- Test: `frontend/src/App.routeMode.test.ts`

- [ ] **Step 1: Write the failing test**

把 `frontend/src/App.routeMode.test.ts` 增加第二个测试：

```ts
test('composer source includes route mode panel and generation affordance', () => {
  const composerSource = readFileSync(new URL('./components/ChatComposer.vue', import.meta.url), 'utf-8')
  expect(composerSource).toContain('class="composer-mode-banner"')
  expect(composerSource).toContain('<InterestTagPanel')
  expect(composerSource).toContain("emit('generateRoute')")
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- --run src/App.routeMode.test.ts`

Expected: FAIL because `ChatComposer.vue` still lacks the route mode banner and embedded `InterestTagPanel`.

- [ ] **Step 3: Write minimal implementation**

1. 给 `ChatComposer.vue` 增加 props 和 emits：

```ts
import InterestTagPanel from './InterestTagPanel.vue'

defineProps<{
  // existing props...
  routeSelectedTags?: string[]
  routeLoading?: boolean
  routeSaving?: boolean
  routeError?: string
  routeDisabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  switchMode: [mode: ComposerMode]
  pickPhoto: [file: File]
  send: []
  toggleRecording: []
  toggleRouteTag: [tag: string]
  generateRoute: []
  askRouteQuestion: [question: string]
}>()
```

2. 在 `composer-panel` 之前插入路线模式条和轻量面板：

```vue
<div v-if="props.composerMode === 'route'" class="composer-mode-banner" data-mode="route">
  <div class="composer-mode-banner-head">
    <strong>路线推荐模式</strong>
    <button type="button" class="ghost-button" @click="switchMode('chat')">退出路线模式</button>
  </div>
  <p>先选择兴趣标签，再手动生成路线；不会自动替你提交请求。</p>
  <InterestTagPanel
    :selected-tags="props.routeSelectedTags || []"
    :recommendation="null"
    :loading="props.routeLoading"
    :saving="props.routeSaving"
    :error="props.routeError"
    :disabled="props.routeDisabled"
    compact
    @toggle-tag="emit('toggleRouteTag', $event)"
    @refresh="emit('generateRoute')"
  />
</div>
```

3. 给 `InterestTagPanel.vue` 增加 `compact` 模式，删除推荐结果卡片展示块，保留标签与“生成路线”按钮：

```ts
const props = withDefaults(
  defineProps<{
    selectedTags: string[]
    recommendation: RecommendationCard | null
    loading?: boolean
    saving?: boolean
    error?: string
    disabled?: boolean
    compact?: boolean
  }>(),
  {
    loading: false,
    saving: false,
    error: '',
    disabled: false,
    compact: false,
  },
)
```

并删除模板中这段：

```vue
<div v-if="props.recommendation" class="recommendation-card">
  ...
</div>
```

4. 在 `style.css` 中加入必要样式：

```css
.composer-mode-banner {
  margin-bottom: 0.9rem;
  padding: 0.95rem 1rem;
  border-radius: 1.1rem;
  border: 1px solid rgba(40, 98, 188, 0.18);
  background: linear-gradient(180deg, rgba(225, 238, 255, 0.92), rgba(242, 247, 255, 0.98));
}

.composer-mode-banner-head {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  align-items: center;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- --run src/App.routeMode.test.ts`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ChatComposer.vue frontend/src/components/InterestTagPanel.vue frontend/src/style.css frontend/src/App.routeMode.test.ts
git commit -m "feat: add route mode banner and inline tag panel"
```

## Task 3: 为聊天消息增加工具结果结构

**Files:**
- Modify: `frontend/src/types/chat.ts`
- Create: `frontend/src/lib/toolResultMessage.ts`
- Create: `frontend/src/lib/toolResultMessage.test.ts`

- [ ] **Step 1: Write the failing test**

创建 `frontend/src/lib/toolResultMessage.test.ts`：

```ts
import { describe, expect, it } from 'vitest'

import { buildRouteRecommendationMessage } from './toolResultMessage'

describe('buildRouteRecommendationMessage', () => {
  it('builds a route recommendation tool result message', () => {
    const message = buildRouteRecommendationMessage({
      routeTitle: '亲子半日路线',
      intro: '先看核心演出，再安排轻松互动点位。',
      highlights: ['九龙灌浴', '佛手广场'],
      suggestedQuestions: ['这条路线适合几点开始？'],
      appliedInterestTags: ['亲子', '轻松'],
    })

    expect(message.role).toBe('assistant')
    expect(message.content).toBe('我帮你整理了一条路线推荐，可以继续点卡片里的问题细问。')
    expect(message.toolResult?.toolName).toBe('route_recommendation')
    expect(message.toolResult?.actions).toEqual(['这条路线适合几点开始？'])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- --run src/lib/toolResultMessage.test.ts`

Expected: FAIL because `toolResultMessage.ts` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

1. 在 `frontend/src/types/chat.ts` 中扩展类型：

```ts
export interface ToolResultPayload {
  toolName: 'route_recommendation'
  title: string
  intro: string
  highlights: string[]
  appliedInterestTags: string[]
  actions: string[]
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  streaming?: boolean
  meta?: string
  sources?: SourceItem[]
  replyKind?: string
  needsFollowup?: boolean
  toolResult?: ToolResultPayload
}
```

2. 创建 `frontend/src/lib/toolResultMessage.ts`：

```ts
import type { RecommendationCard } from './recommendationState'
import type { ChatMessage } from '../types/chat'

function createMessageId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
}

export function buildRouteRecommendationMessage(recommendation: RecommendationCard): ChatMessage {
  return {
    id: createMessageId('route-tool'),
    role: 'assistant',
    content: '我帮你整理了一条路线推荐，可以继续点卡片里的问题细问。',
    meta: '路线推荐',
    toolResult: {
      toolName: 'route_recommendation',
      title: recommendation.routeTitle,
      intro: recommendation.intro,
      highlights: recommendation.highlights,
      appliedInterestTags: recommendation.appliedInterestTags,
      actions: recommendation.suggestedQuestions,
    },
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- --run src/lib/toolResultMessage.test.ts`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/chat.ts frontend/src/lib/toolResultMessage.ts frontend/src/lib/toolResultMessage.test.ts
git commit -m "feat: add route recommendation tool result message model"
```

## Task 4: 渲染路线推荐工具卡片消息

**Files:**
- Modify: `frontend/src/components/ChatTranscript.vue`
- Create: `frontend/src/components/ToolResultCard.vue`
- Create: `frontend/src/components/RouteRecommendationCard.vue`
- Modify: `frontend/src/style.css`
- Test: `frontend/src/App.routeMode.test.ts`

- [ ] **Step 1: Write the failing test**

把 `frontend/src/App.routeMode.test.ts` 增加第三个测试：

```ts
test('transcript source renders route recommendation card branch', () => {
  const transcriptSource = readFileSync(new URL('./components/ChatTranscript.vue', import.meta.url), 'utf-8')
  expect(transcriptSource).toContain('RouteRecommendationCard')
  expect(transcriptSource).toContain("message.toolResult?.toolName === 'route_recommendation'")
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- --run src/App.routeMode.test.ts`

Expected: FAIL because `ChatTranscript.vue` does not yet render a route recommendation card branch.

- [ ] **Step 3: Write minimal implementation**

1. 创建 `frontend/src/components/ToolResultCard.vue`：

```vue
<script setup lang="ts">
defineProps<{
  title: string
}>()
</script>

<template>
  <section class="tool-result-card">
    <header class="tool-result-card-head">
      <p class="bubble-subsection-title">工具结果</p>
      <strong>{{ title }}</strong>
    </header>
    <div class="tool-result-card-body">
      <slot />
    </div>
  </section>
</template>
```

2. 创建 `frontend/src/components/RouteRecommendationCard.vue`：

```vue
<script setup lang="ts">
import ToolResultCard from './ToolResultCard.vue'

defineProps<{
  title: string
  intro: string
  highlights: string[]
  appliedInterestTags: string[]
  actions: string[]
}>()

const emit = defineEmits<{
  ask: [question: string]
}>()
</script>

<template>
  <ToolResultCard :title="title">
    <p class="route-card-intro">{{ intro }}</p>
    <div class="highlight-list">
      <span v-for="highlight in highlights" :key="highlight" class="highlight-pill">{{ highlight }}</span>
    </div>
    <p class="route-card-tags">{{ appliedInterestTags.join(' / ') }}</p>
    <div class="suggestion-list">
      <button
        v-for="question in actions"
        :key="question"
        type="button"
        class="suggestion-chip"
        @click="emit('ask', question)"
      >
        {{ question }}
      </button>
    </div>
  </ToolResultCard>
</template>
```

3. 修改 `ChatTranscript.vue`，为工具结果加入分支：

```vue
<script setup lang="ts">
import RouteRecommendationCard from './RouteRecommendationCard.vue'

const emit = defineEmits<{
  askToolAction: [question: string]
}>()
</script>
```

并在模板中替换正文显示为：

```vue
<template>
  <div ref="scrollHostRef" class="chat-body">
    <article
      v-for="message in messages"
      :key="message.id"
      class="bubble"
      :class="`bubble-${message.role}`"
    >
      <header class="bubble-head">
        <span>{{ resolveRoleLabel(message.role) }}</span>
        <span v-if="message.meta">{{ message.meta }}</span>
      </header>

      <RouteRecommendationCard
        v-if="message.toolResult?.toolName === 'route_recommendation'"
        :title="message.toolResult.title"
        :intro="message.toolResult.intro"
        :highlights="message.toolResult.highlights"
        :applied-interest-tags="message.toolResult.appliedInterestTags"
        :actions="message.toolResult.actions"
        @ask="emit('askToolAction', $event)"
      />

      <p v-else class="bubble-content">
        {{ message.content }}
        <span v-if="message.streaming" class="cursor">|</span>
      </p>
      ...
    </article>
  </div>
</template>
```

4. 在 `style.css` 中加入：

```css
.tool-result-card {
  margin-top: 0.35rem;
  padding: 0.9rem;
  border-radius: 1rem;
  background: rgba(25, 74, 103, 0.05);
  border: 1px solid rgba(25, 74, 103, 0.1);
}

.tool-result-card-head strong,
.route-card-tags {
  color: var(--ink-strong);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- --run src/App.routeMode.test.ts`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ChatTranscript.vue frontend/src/components/ToolResultCard.vue frontend/src/components/RouteRecommendationCard.vue frontend/src/style.css frontend/src/App.routeMode.test.ts
git commit -m "feat: render route recommendation tool cards in transcript"
```

## Task 5: 把推荐接口结果插入聊天流并支持卡片追问

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/ChatTranscript.vue`
- Modify: `frontend/src/lib/chatComposerMode.ts`
- Modify: `frontend/src/lib/chatComposerMode.test.ts`
- Modify: `frontend/src/composables/useVisitorRecommendations.ts`
- Modify: `frontend/src/components/ChatComposer.vue`
- Test: `frontend/src/lib/chatComposerMode.test.ts`
- Test: `frontend/src/lib/toolResultMessage.test.ts`

- [ ] **Step 1: Write the failing test**

先为路线模式快捷问题固定“只依赖标签，不依赖顶部 recommendation 面板”行为，在 `frontend/src/lib/chatComposerMode.test.ts` 增加一条：

```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- --run src/lib/chatComposerMode.test.ts`

Expected: FAIL if当前实现字符串模板或中文文案与目标不一致。

- [ ] **Step 3: Write minimal implementation**

1. 调整 `frontend/src/lib/chatComposerMode.ts`：

```ts
const DEFAULT_ROUTE_HINTS = [
  '第一次来适合先去哪里？',
  '半天路线怎么走更顺？',
  '晚上适合重点看什么？',
]

export function buildComposerQuickHints(
  mode: ComposerMode,
  options: {
    selectedTags: string[]
    recommendation: RecommendationCard | null
  },
) {
  if (mode === 'chat') {
    return DEFAULT_CHAT_HINTS
  }

  if (options.recommendation?.suggestedQuestions?.length) {
    return options.recommendation.suggestedQuestions
  }

  const tags = options.selectedTags.map((item) => item.trim()).filter((item) => item.length > 0)
  if (tags.length === 0) {
    return DEFAULT_ROUTE_HINTS
  }

  return [
    `按${tags.slice(0, 2).join(' / ')}偏好怎么安排路线？`,
    '第一次来适合先去哪里？',
    '半天路线怎么走更顺？',
  ]
}
```

2. 在 `App.vue` 中引入 `buildRouteRecommendationMessage`：

```ts
import { buildRouteRecommendationMessage } from './lib/toolResultMessage'
```

3. 修改 `handleGenerateRecommendation()`：

```ts
async function handleGenerateRecommendation() {
  if (!sessionId.value) {
    return
  }

  if (recommendationState.selectedInterestTags.value.length === 0) {
    recommendationState.error.value = '先选择至少一个兴趣标签，我再帮你规划路线。'
    return
  }

  try {
    const recommendation = await recommendationState.refreshRecommendations()
    if (!recommendation) {
      return
    }

    messages.value.push(buildRouteRecommendationMessage(recommendation))
    await scrollChatToEnd()
  } catch {
    return
  }
}
```

4. 让 `ChatTranscript` 把工具卡片动作抛回 `App.vue`：

```vue
<ChatTranscript
  ref="transcriptRef"
  :messages="messages"
  @ask-tool-action="handleRecommendationQuestion"
/>
```

5. 确保 `handleRecommendationQuestion()` 继续发送普通文本，并保留 `meta: '路线推荐'`。

- [ ] **Step 4: Run test to verify it passes**

Run:

- `npm run test -- --run src/lib/chatComposerMode.test.ts src/lib/toolResultMessage.test.ts`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.vue frontend/src/components/ChatTranscript.vue frontend/src/lib/chatComposerMode.ts frontend/src/lib/chatComposerMode.test.ts frontend/src/lib/toolResultMessage.ts frontend/src/components/ChatComposer.vue
git commit -m "feat: insert route recommendation results into chat flow"
```

## Task 6: 完整回归验证

**Files:**
- Verify only: `frontend/src/App.vue`
- Verify only: `frontend/src/components/ChatComposer.vue`
- Verify only: `frontend/src/components/ChatTranscript.vue`
- Verify only: `frontend/src/components/InterestTagPanel.vue`
- Verify only: `frontend/src/components/RouteRecommendationCard.vue`
- Verify only: `frontend/src/lib/toolResultMessage.ts`

- [ ] **Step 1: Run focused frontend tests**

Run:

```bash
npm run test -- --run src/App.chatLayout.test.ts src/App.routeMode.test.ts src/lib/chatComposerMode.test.ts src/lib/toolResultMessage.test.ts src/lib/photoQuestion.test.ts src/lib/visitorSessionState.test.ts src/lib/recommendationState.test.ts src/composables/useVisitorSessions.test.ts
```

Expected:

- 所有测试 PASS
- 不出现新的 route mode regression

- [ ] **Step 2: Run production build**

Run:

```bash
npm run build
```

Expected:

- build 成功
- 允许保留已有的大 bundle warning，不应新增类型错误或模板编译错误

- [ ] **Step 3: Manual verification checklist**

手工验证：

```text
1. 点击 + 菜单切到路线模式，不会自动生成路线
2. 蓝色模式条出现在输入区上方，聊天区仍然能正常滚动
3. 选择标签后点击“生成路线”，结果以卡片消息进入聊天流
4. 卡片中的追问按钮可继续发问，并带有“路线推荐” meta
5. 生成完后仍停留在路线模式，手动切换才退出
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.vue frontend/src/components/ChatComposer.vue frontend/src/components/ChatTranscript.vue frontend/src/components/InterestTagPanel.vue frontend/src/components/RouteRecommendationCard.vue frontend/src/components/ToolResultCard.vue frontend/src/style.css frontend/src/types/chat.ts frontend/src/lib/toolResultMessage.ts frontend/src/lib/toolResultMessage.test.ts frontend/src/App.routeMode.test.ts frontend/src/lib/chatComposerMode.ts frontend/src/lib/chatComposerMode.test.ts
git commit -m "feat: add route mode tool card chat flow"
```

## Self-Review

### Spec coverage

- 去掉自动生成：Task 1
- 输入区蓝色模式条与标签面板：Task 2
- 结构化工具消息：Task 3
- 卡片渲染：Task 4
- 推荐结果进入聊天流：Task 5
- 测试与回归：Task 6

无缺口。

### Placeholder scan

- 未使用占位符
- 每个任务都给出了明确文件、测试命令和最小代码方向
- 无“自行补充错误处理”这类空泛描述

### Type consistency

- `toolResult` 统一使用 `toolName = 'route_recommendation'`
- 卡片动作统一为 `actions: string[]`
- `ChatTranscript` 统一向上抛出 `askToolAction`
- `ChatComposer` 统一使用 `generateRoute` / `toggleRouteTag`

无命名冲突。
