import type { VisitorSessionMessageRole, VisitorSessionSummary } from '../types/visitor'

function toTimestamp(value: string | undefined) {
  const parsed = Date.parse(value ?? '')
  return Number.isNaN(parsed) ? 0 : parsed
}

export function sortSessionSummaries(items: Array<Pick<VisitorSessionSummary, 'sessionId' | 'updatedAt'>>) {
  return [...items].sort((left, right) => {
    const delta = toTimestamp(right.updatedAt) - toTimestamp(left.updatedAt)
    if (delta !== 0) {
      return delta
    }

    return left.sessionId.localeCompare(right.sessionId)
  })
}

export function normalizeVisitorMessageRole(role: string): VisitorSessionMessageRole {
  if (role === 'user' || role === 'assistant' || role === 'system') {
    return role
  }

  throw new Error(`Unsupported visitor session message role: ${role}`)
}
