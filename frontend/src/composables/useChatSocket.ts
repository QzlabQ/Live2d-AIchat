import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'

import type { ClientSocketMessage, ServerSocketMessage } from '../types/chat'

export type ConnectionState =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'disconnected'
  | 'error'

interface UseChatSocketOptions {
  sessionId: Ref<string | null>
  baseUrl: string
  heartbeatMs: number
  reconnectBaseMs: number
  onOpen?: () => void
  onMessage: (payload: ServerSocketMessage) => void
  onError: (message: string) => void
}

function normalizeWsBaseUrl(baseUrl: string): string {
  if (baseUrl.startsWith('ws://') || baseUrl.startsWith('wss://')) {
    return baseUrl.replace(/\/+$/, '')
  }

  if (baseUrl.startsWith('http://')) {
    return `ws://${baseUrl.slice('http://'.length).replace(/\/+$/, '')}`
  }

  if (baseUrl.startsWith('https://')) {
    return `wss://${baseUrl.slice('https://'.length).replace(/\/+$/, '')}`
  }

  return `ws://${baseUrl.replace(/\/+$/, '')}`
}

export function useChatSocket(options: UseChatSocketOptions) {
  const state = ref<ConnectionState>('idle')
  const socket = ref<WebSocket | null>(null)
  const reconnectAttempt = ref(0)
  const closeManually = ref(false)
  const lastError = ref<string>('')
  const lastPongAt = ref<number | null>(null)

  let heartbeatTimer: number | null = null
  let reconnectTimer: number | null = null
  let activeSessionId: string | null = null

  const socketUrl = computed(() => {
    if (!options.sessionId.value) {
      return null
    }

    return `${normalizeWsBaseUrl(options.baseUrl)}/ws/chat/${options.sessionId.value}`
  })

  function clearTimers() {
    if (heartbeatTimer !== null) {
      window.clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }

    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  function startHeartbeat() {
    clearTimers()
    heartbeatTimer = window.setInterval(() => {
      send({ type: 'ping' })
    }, options.heartbeatMs)
  }

  function scheduleReconnect() {
    if (closeManually.value || !options.sessionId.value) {
      state.value = 'disconnected'
      return
    }

    clearTimers()
    state.value = 'reconnecting'
    const delay = Math.min(options.reconnectBaseMs * 2 ** reconnectAttempt.value, 8000)
    reconnectAttempt.value += 1

    reconnectTimer = window.setTimeout(() => {
      void connect()
    }, delay)
  }

  async function connect() {
    if (!socketUrl.value) {
      return
    }

    if (
      socket.value &&
      (socket.value.readyState === WebSocket.OPEN || socket.value.readyState === WebSocket.CONNECTING)
    ) {
      return
    }

    closeManually.value = false
    state.value = reconnectAttempt.value > 0 ? 'reconnecting' : 'connecting'

    try {
      const ws = new WebSocket(socketUrl.value)
      socket.value = ws

      ws.onopen = () => {
        state.value = 'connected'
        reconnectAttempt.value = 0
        lastError.value = ''
        startHeartbeat()
        options.onOpen?.()
      }

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as ServerSocketMessage
          if (payload.type === 'pong') {
            lastPongAt.value = Date.now()
            return
          }

          if (payload.type === 'error') {
            lastError.value = payload.message
            options.onError(`${payload.code}: ${payload.message}`)
            return
          }

          options.onMessage(payload)
        } catch (error) {
          const message = error instanceof Error ? error.message : 'WebSocket message parse failed.'
          lastError.value = message
          options.onError(message)
        }
      }

      ws.onerror = () => {
        state.value = 'error'
        lastError.value = 'WebSocket connection failed.'
      }

      ws.onclose = () => {
        socket.value = null
        clearTimers()
        scheduleReconnect()
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'WebSocket initialization failed.'
      state.value = 'error'
      lastError.value = message
      options.onError(message)
      scheduleReconnect()
    }
  }

  function disconnect() {
    closeManually.value = true
    clearTimers()
    socket.value?.close()
    socket.value = null
    state.value = 'disconnected'
  }

  function send(payload: ClientSocketMessage): boolean {
    if (!socket.value || socket.value.readyState !== WebSocket.OPEN) {
      return false
    }

    socket.value.send(JSON.stringify(payload))
    return true
  }

  watch(
    () => options.sessionId.value,
    (sessionId) => {
      if (!sessionId) {
        disconnect()
        return
      }

      if (activeSessionId && activeSessionId !== sessionId) {
        disconnect()
        closeManually.value = false
      }

      activeSessionId = sessionId
      void connect()
    },
    { immediate: true },
  )

  onBeforeUnmount(() => {
    disconnect()
  })

  return {
    state,
    lastError,
    lastPongAt,
    connect,
    disconnect,
    send,
  }
}
