<script setup lang="ts">
import type { VisitorSessionSummary } from '../types/visitor'

const props = withDefaults(
  defineProps<{
    sessions: VisitorSessionSummary[]
    activeSessionId: string | null
    open?: boolean
    loading?: boolean
    disabled?: boolean
    disabledReason?: string
  }>(),
  {
    open: false,
    loading: false,
    disabled: false,
    disabledReason: '',
  },
)

const emit = defineEmits<{
  close: []
  create: []
  open: [sessionId: string]
}>()

function formatUpdatedAt(value: string) {
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) {
    return '刚刚'
  }

  return new Date(parsed).toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function resolvePreview(session: VisitorSessionSummary) {
  return session.lastMessagePreview.trim() || '还没有对话，点击继续'
}

function resolveTagSummary(session: VisitorSessionSummary) {
  return session.interestTags.length > 0 ? session.interestTags.join(' / ') : '未设置偏好'
}

function handleOpenSession(sessionId: string) {
  emit('open', sessionId)
  emit('close')
}
</script>

<template>
  <aside class="history-drawer" :class="{ open: props.open }" :aria-hidden="!props.open">
    <button v-if="props.open" class="history-backdrop" type="button" @click="emit('close')"></button>

    <section class="history-panel panel">
      <div class="panel-header history-header">
        <div>
          <p class="panel-kicker">Visitor Sessions</p>
          <h2>历史会话</h2>
        </div>
        <div class="history-actions">
          <button class="ghost-button" type="button" :disabled="loading || props.disabled" @click="emit('create')">
            新建会话
          </button>
          <button class="ghost-button history-close" type="button" @click="emit('close')">
            收起
          </button>
        </div>
      </div>

      <p v-if="disabledReason" class="history-hint">{{ disabledReason }}</p>

      <div v-if="props.sessions.length === 0" class="history-empty">
        <strong>还没有历史记录</strong>
        <span>先发起一次对话，之后这里会保留最近会话。</span>
      </div>

      <div v-else class="history-list">
        <button
          v-for="session in props.sessions"
          :key="session.sessionId"
          class="history-card"
          :class="{ active: session.sessionId === props.activeSessionId }"
          :disabled="props.disabled || props.loading"
          type="button"
          @click="handleOpenSession(session.sessionId)"
        >
          <div class="history-card-meta">
            <span>{{ formatUpdatedAt(session.updatedAt) }}</span>
            <span>{{ session.messageCount }} 条消息</span>
          </div>
          <strong>{{ resolvePreview(session) }}</strong>
          <span class="history-card-tags">{{ resolveTagSummary(session) }}</span>
        </button>
      </div>
    </section>
  </aside>
</template>
