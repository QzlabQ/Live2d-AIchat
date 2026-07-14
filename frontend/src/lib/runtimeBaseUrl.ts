export interface RuntimeBaseUrlEnvLike {
  PROD: boolean
  VITE_API_BASE_URL?: string
  VITE_WS_BASE_URL?: string
}

export interface RuntimeLocationLike {
  protocol: string
  host: string
  origin?: string
}

const LOCAL_API_BASE_URL = 'http://127.0.0.1:8000/api/v1'
const LOCAL_WS_BASE_URL = 'ws://127.0.0.1:8000'
const PRODUCTION_API_BASE_PATH = '/api/v1'

function normalizeConfiguredValue(value: string | undefined): string {
  return (value || '').trim().replace(/\/+$/, '')
}

function isAbsoluteUrl(value: string): boolean {
  return /^(?:https?|wss?):\/\//.test(value)
}

function buildSameOriginWsBaseUrl(location: RuntimeLocationLike): string {
  const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${wsProtocol}//${location.host}`
}

export function getRuntimeApiBaseUrl(env: RuntimeBaseUrlEnvLike): string {
  const configured = normalizeConfiguredValue(env.VITE_API_BASE_URL)
  if (configured) {
    return configured
  }

  if (env.PROD) {
    return PRODUCTION_API_BASE_PATH
  }

  return LOCAL_API_BASE_URL
}

export function getRuntimeWsBaseUrl(
  env: RuntimeBaseUrlEnvLike,
  location: RuntimeLocationLike,
): string {
  const configured = normalizeConfiguredValue(env.VITE_WS_BASE_URL)
  if (configured) {
    return configured
  }

  const configuredApiBaseUrl = normalizeConfiguredValue(env.VITE_API_BASE_URL)
  if (env.PROD) {
    if (configuredApiBaseUrl && isAbsoluteUrl(configuredApiBaseUrl)) {
      return buildSameOriginWsBaseUrl(location)
    }
    return buildSameOriginWsBaseUrl(location)
  }

  return LOCAL_WS_BASE_URL
}
