import { describe, expect, it } from 'vitest'

import {
  getRuntimeApiBaseUrl,
  getRuntimeWsBaseUrl,
  type RuntimeBaseUrlEnvLike,
  type RuntimeLocationLike,
} from './runtimeBaseUrl'

function createEnv(overrides: Partial<RuntimeBaseUrlEnvLike> = {}): RuntimeBaseUrlEnvLike {
  return {
    PROD: false,
    VITE_API_BASE_URL: '',
    VITE_WS_BASE_URL: '',
    ...overrides,
  }
}

function createLocation(overrides: Partial<RuntimeLocationLike> = {}): RuntimeLocationLike {
  return {
    protocol: 'http:',
    host: 'localhost:5173',
    origin: 'http://localhost:5173',
    ...overrides,
  }
}

describe('runtimeBaseUrl', () => {
  it('uses localhost defaults outside production when env vars are missing', () => {
    expect(getRuntimeApiBaseUrl(createEnv())).toBe('http://127.0.0.1:8000/api/v1')
    expect(getRuntimeWsBaseUrl(createEnv(), createLocation())).toBe('ws://127.0.0.1:8000')
  })

  it('uses same-origin production defaults when env vars are missing', () => {
    const env = createEnv({ PROD: true })
    const location = createLocation({
      protocol: 'https:',
      host: 'contest.example.com',
      origin: 'https://contest.example.com',
    })

    expect(getRuntimeApiBaseUrl(env)).toBe('/api/v1')
    expect(getRuntimeWsBaseUrl(env, location)).toBe('wss://contest.example.com')
  })

  it('preserves explicitly configured absolute API and WS base URLs', () => {
    const env = createEnv({
      PROD: true,
      VITE_API_BASE_URL: 'https://api.example.com/api/v1/',
      VITE_WS_BASE_URL: 'wss://ws.example.com/',
    })

    expect(getRuntimeApiBaseUrl(env)).toBe('https://api.example.com/api/v1')
    expect(getRuntimeWsBaseUrl(env, createLocation())).toBe('wss://ws.example.com')
  })

  it('treats blank explicit values as missing and falls back to production defaults', () => {
    const env = createEnv({
      PROD: true,
      VITE_API_BASE_URL: '   ',
      VITE_WS_BASE_URL: '   ',
    })
    const location = createLocation({
      protocol: 'http:',
      host: 'localhost:8080',
      origin: 'http://localhost:8080',
    })

    expect(getRuntimeApiBaseUrl(env)).toBe('/api/v1')
    expect(getRuntimeWsBaseUrl(env, location)).toBe('ws://localhost:8080')
  })
})
