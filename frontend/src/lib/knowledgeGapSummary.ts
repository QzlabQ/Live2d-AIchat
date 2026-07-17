import type { KnowledgeGapSummaryStatusCount } from '../types/admin'

const STATUS_COLORS: Record<string, string> = {
  pending: '#7fb4ff',
  draft: '#f2c572',
  reviewing: '#f29e73',
  resolved: '#5cbf9a',
  imported: '#6fcf97',
  ignored: '#c3ccd8',
}

const FALLBACK_COLOR = '#9db9d6'

export interface KnowledgeGapStatusDistributionSegment {
  status: string
  count: number
  percent: number
  percentLabel: string
  color: string
  startDeg: number
  endDeg: number
  sweepDeg: number
}

export interface KnowledgeGapStatusDistribution {
  totalCount: number
  gradient: string
  segments: KnowledgeGapStatusDistributionSegment[]
}

function resolveStatusColor(status: string) {
  return STATUS_COLORS[status] || FALLBACK_COLOR
}

export function buildKnowledgeGapStatusDistribution(
  items: KnowledgeGapSummaryStatusCount[],
): KnowledgeGapStatusDistribution | null {
  const normalizedItems = items
    .filter((item) => item.count > 0)
    .map((item) => ({
      ...item,
      status: item.status.trim().toLowerCase(),
    }))

  if (!normalizedItems.length) {
    return null
  }

  const totalCount = normalizedItems.reduce((sum, item) => sum + item.count, 0)
  if (totalCount <= 0) {
    return null
  }

  let currentDeg = 0
  const segments = normalizedItems.map((item, index) => {
    const rawSweepDeg = (item.count / totalCount) * 360
    const isLastSegment = index === normalizedItems.length - 1
    const startDeg = currentDeg
    const endDeg = isLastSegment ? 360 : Number((currentDeg + rawSweepDeg).toFixed(2))
    currentDeg = endDeg
    const percent = Math.round((item.count / totalCount) * 100)

    return {
      status: item.status,
      count: item.count,
      percent,
      percentLabel: `${percent}%`,
      color: resolveStatusColor(item.status),
      startDeg,
      endDeg,
      sweepDeg: Number((endDeg - startDeg).toFixed(2)),
    }
  })

  const gradient = `conic-gradient(${segments
    .map((segment) => `${segment.color} ${segment.startDeg}deg ${segment.endDeg}deg`)
    .join(', ')})`

  return {
    totalCount,
    gradient,
    segments,
  }
}
