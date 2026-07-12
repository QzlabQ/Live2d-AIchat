<script setup lang="ts">
import { nextTick, ref } from 'vue'

import RouteRecommendationCard from './RouteRecommendationCard.vue'
import type { ChatMessage } from '../types/chat'

defineProps<{
  messages: ChatMessage[]
}>()

const emit = defineEmits<{
  askToolAction: [question: string]
}>()

const scrollHostRef = ref<HTMLDivElement | null>(null)

function resolveRoleLabel(role: ChatMessage['role']) {
  if (role === 'assistant') {
    return '导览助手'
  }

  if (role === 'user') {
    return '游客'
  }

  return '系统'
}

async function scrollToEnd() {
  await nextTick()
  const host = scrollHostRef.value
  if (!host) {
    return
  }

  host.scrollTop = host.scrollHeight
}

defineExpose({
  scrollToEnd,
})
</script>

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
        v-if="message.toolResult?.kind === 'route_recommendation'"
        :tool-result="message.toolResult"
        @ask="emit('askToolAction', $event)"
      />

      <p v-else class="bubble-content">
        {{ message.content }}
        <span v-if="message.streaming" class="cursor">|</span>
      </p>

      <section v-if="message.sources?.length" class="bubble-sources">
        <p class="bubble-subsection-title">资料依据</p>
        <article
          v-for="(source, index) in message.sources"
          :key="`${message.id}-source-${index}`"
          class="source-card"
        >
          <div class="source-card-head">
            <strong>{{ source.title || '未命名资料' }}</strong>
            <span>{{ source.filename }}</span>
          </div>
          <p class="source-excerpt">{{ source.excerpt }}</p>
        </article>
      </section>

      <p v-if="message.needsFollowup" class="followup-hint">
        还可以补充范围，我再帮你细看。
      </p>
    </article>
  </div>
</template>
