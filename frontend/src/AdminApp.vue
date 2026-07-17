<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import AdminEmotionPreviewPanel from './components/AdminEmotionPreviewPanel.vue'
import AvatarDisplayControls from './components/AvatarDisplayControls.vue'
import Live2DStage from './components/Live2DStage.vue'
import {
  AVATAR_DISPLAY_DEFAULTS,
  clampAvatarDisplayConfig,
  type AvatarDisplayConfig,
} from './lib/avatarDisplay'
import type { AvatarPresentation } from './lib/avatarPresentation'
import {
  activateAvatarProfile,
  createAvatarProfile,
  deleteKnowledgeDoc,
  deleteAvatarProfile,
  deleteVoiceProfile,
  fetchAdminMe,
  fetchDashboardOverview,
  fetchAdminSessionDetail,
  fetchAdminSessions,
  fetchAvatarConfig,
  fetchAvatarProfiles,
  fetchAvatarConfigByProfile,
  fetchDailyReports,
  fetchKnowledgeGapDetail,
  fetchKnowledgeGapSummary,
  fetchKnowledgeGaps,
  fetchKnowledgeDocs,
  fetchLive2DModels,
  fetchReportSummary,
  fetchVoiceProfileAudioBlobUrl,
  fetchVoiceProfiles,
  generateDailyReport,
  getAdminApiBaseUrl,
  importKnowledgeGap,
  loginAdmin,
  updateKnowledgeGap,
  updateAvatarConfig,
  uploadKnowledgeDoc,
  uploadVoiceProfile,
} from './services/adminApi'
import type {
  AdminReplyTrace,
  AdminSessionDetail,
  AdminSessionSummary,
  AvatarConfig,
  AvatarProfileSummary,
  AvatarConfigUpdate,
  DashboardKeywordCloudItem,
  DashboardOverview,
  DailyEmotionReport,
  KnowledgeGapItem,
  KnowledgeGapSummary,
  KnowledgeGapUpdatePayload,
  KnowledgeDocItem,
  Live2DModelOption,
  ReportRangeSummary,
  VoiceProfile,
} from './types/admin'

type NoticeKind = 'success' | 'error' | 'info'

interface NoticeState {
  kind: NoticeKind
  text: string
}

interface AvatarFormState {
  id: number | null
  name: string
  slug: string
  isActive: boolean
  modelPath: string
  voiceId: string
  voiceProfileId: string
  responseLanguage: 'zh' | 'en'
  persona: string
  ttsReferenceAudioPath: string
  ttsReferenceText: string
  ttsSpeed: number
  ttsEmotionEnabled: boolean
  displayScale: number
  displayOffsetX: number
  displayOffsetY: number
  stageHeight: number
  createdAt: string
  updatedAt: string
}

interface LineChartNode {
  key: string
  x: string
  y: string
  label: string
  valueLabel: string
  ariaLabel: string
}

interface KnowledgeGapEditorState {
  status: string
  adminTitle: string
  adminCategory: string
  adminAnswer: string
  adminNotes: string
  filenamePrefix: string
}

type AdminPageKey =
  | 'overview'
  | 'dashboard'
  | 'avatar'
  | 'voices'
  | 'knowledge'
  | 'knowledge-gaps'
  | 'sessions'
  | 'reports'

interface AdminPageMeta {
  key: AdminPageKey
  label: string
  eyebrow: string
  title: string
  description: string
}

interface SessionTraceMetricDefinition {
  key: string
  label: string
}

interface SessionTraceChunkMetric {
  seq: number
  chunkIndex: number
  tokenOffset: number
  tokenWaitMs: number | null
  token2wavMs: number | null
  audioMs: number | null
  supplyLagMs: number | null
  realRtf: number | null
  readyRatio: number | null
  isFinal: boolean
}

const API_BASE_URL = getAdminApiBaseUrl()
const TOKEN_STORAGE_KEY = 'ai-chat-live2d.admin.token'
const MODEL_FALLBACK = '/live2d/haru/haru_greeter_t03.model3.json'
const KNOWLEDGE_GAP_STATUS_ORDER = [
  'pending',
  'draft',
  'reviewing',
  'resolved',
  'imported',
  'ignored',
] as const
const SESSION_TRACE_METRICS: SessionTraceMetricDefinition[] = [
  { key: 'rag_embed_ms', label: 'Embedding' },
  { key: 'rag_vector_search_ms', label: '向量检索' },
  { key: 'rag_retrieve_ms', label: '召回阶段' },
  { key: 'rag_rerank_ms', label: 'Rerank' },
  { key: 'rag_retrieve_total_ms', label: '检索总计' },
  { key: 'rag_prepare_total_ms', label: 'RAG 准备' },
  { key: 'llm_first_delta_ms', label: '首个文本' },
  { key: 'tts_first_audio_chunk_ms', label: '首包音频' },
  { key: 'audio_done_ms', label: '音频完成' },
] as const
const SESSION_TRACE_CHUNK_LIMIT = 12
const ADMIN_PAGES: AdminPageMeta[] = [
  {
    key: 'overview',
    label: '总览',
    eyebrow: 'Dashboard',
    title: '管理后台总览',
    description: '查看当前数字人配置、知识库状态和音色资源概况。',
  },
  {
    key: 'dashboard',
    label: '数据大屏',
    eyebrow: 'Dashboard',
    title: '数据大屏',
    description: '集中查看服务人次、实时在线、热门问题和情绪趋势。',
  },
  {
    key: 'avatar',
    label: '数字人管理',
    eyebrow: 'Avatar',
    title: '数字人管理',
    description: '维护 Live2D 模型、TTS 参考音频和系统 Prompt。',
  },
  {
    key: 'voices',
    label: '音色资源',
    eyebrow: 'Voice Profiles',
    title: '音色资源管理',
    description: '上传、试听和切换数字人使用的参考音色资源。',
  },
  {
    key: 'knowledge',
    label: '知识库管理',
    eyebrow: 'Knowledge Base',
    title: '知识库管理',
    description: '上传文档、观察处理状态，并清理旧的知识条目。',
  },
  {
    key: 'knowledge-gaps',
    label: '知识缺口',
    eyebrow: 'Knowledge Gaps',
    title: '知识自扩容 / 知识缺口',
    description: '集中查看未命中问题、补充草稿答案，并将整理后的内容一键导入知识库。',
  },
  {
    key: 'sessions',
    label: '会话记录',
    eyebrow: 'Sessions',
    title: '会话记录',
    description: '查看历史会话、消息时间线，以及每条回复的情绪和耗时元数据。',
  },
  {
    key: 'reports',
    label: '感受度报告',
    eyebrow: 'Reports',
    title: '感受度报告',
    description: '查看日报分析、情绪趋势、关注点分析，并手动触发指定日期的报告生成。',
  },
]

const authReady = ref(false)
const adminToken = ref(localStorage.getItem(TOKEN_STORAGE_KEY) || '')
const adminUsername = ref('')
const authError = ref('')
const loginPending = ref(false)
const notice = ref<NoticeState | null>(null)
const activePage = ref<AdminPageKey>('overview')

const loginForm = reactive({
  username: 'admin',
  password: '',
})

const loading = reactive({
  dashboard: false,
  dashboardAnalytics: false,
  avatarProfileCreate: false,
  avatarProfileDelete: false,
  avatarSave: false,
  knowledgeGapDetail: false,
  knowledgeGapImport: false,
  knowledgeGapReload: false,
  knowledgeGapSave: false,
  knowledgeReload: false,
  knowledgeUpload: false,
  sessionDetail: false,
  sessionReload: false,
  reportGenerate: false,
  reportReload: false,
  voiceReload: false,
  voiceUpload: false,
})

const avatarForm = reactive<AvatarFormState>({
  id: null,
  name: '',
  slug: '',
  isActive: false,
  modelPath: MODEL_FALLBACK,
  voiceId: '',
  voiceProfileId: '',
  responseLanguage: 'zh',
  persona: '',
  ttsReferenceAudioPath: '',
  ttsReferenceText: '',
  ttsSpeed: 1,
  ttsEmotionEnabled: true,
  displayScale: AVATAR_DISPLAY_DEFAULTS.displayScale,
  displayOffsetX: AVATAR_DISPLAY_DEFAULTS.displayOffsetX,
  displayOffsetY: AVATAR_DISPLAY_DEFAULTS.displayOffsetY,
  stageHeight: AVATAR_DISPLAY_DEFAULTS.stageHeight,
  createdAt: '',
  updatedAt: '',
})

const knowledgeCategoryFilter = ref('')
const knowledgeFileInput = ref<HTMLInputElement | null>(null)
const voiceFileInput = ref<HTMLInputElement | null>(null)
const adminLive2dRef = ref<InstanceType<typeof Live2DStage> | null>(null)
const knowledgeUploadFile = ref<File | null>(null)
const voiceUploadFile = ref<File | null>(null)

const knowledgeUploadForm = reactive({
  category: 'general',
})

const knowledgeGapFilters = reactive({
  page: 1,
  size: 12,
  status: '',
  search: '',
})
const knowledgeGapSearchInput = ref('')
const knowledgeGapList = ref<KnowledgeGapItem[]>([])
const knowledgeGapTotal = ref(0)
const knowledgeGapSummary = ref<KnowledgeGapSummary | null>(null)
const selectedKnowledgeGapId = ref('')
const selectedKnowledgeGap = ref<KnowledgeGapItem | null>(null)
const knowledgeGapEditor = reactive<KnowledgeGapEditorState>({
  status: '',
  adminTitle: '',
  adminCategory: '',
  adminAnswer: '',
  adminNotes: '',
  filenamePrefix: '',
})
let knowledgeGapDetailRequestId = 0

const sessionSearch = ref('')
const voiceUploadForm = reactive({
  name: '',
  referenceText: '',
  description: '',
})

function formatDateInput(value: Date) {
  return value.toISOString().slice(0, 10)
}

function sentimentScore(value: string) {
  switch (value) {
    case 'positive':
      return 4.6
    case 'negative':
      return 2.5
    default:
      return 3.6
  }
}

function formatScore(score: number | null | undefined) {
  if (typeof score !== 'number' || Number.isNaN(score)) {
    return '--'
  }
  return `${score.toFixed(1)} / 5`
}

function questionBarWidth(count: number) {
  return `${Math.max(14, (count / dashboardTopQuestionMax.value) * 100)}%`
}

function reportEmotionBarWidth(count: number) {
  return `${Math.max(12, (count / reportEmotionMax.value) * 100)}%`
}

function isChartValue(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function buildLineChartPoints<T>(
  items: T[],
  valueGetter: (item: T) => number | null | undefined,
  options: {
    min?: number
    max?: number
  } = {},
) {
  const values = items.map((item) => valueGetter(item))
  const validValues = values.filter(isChartValue)
  if (!validValues.length) {
    return ''
  }

  const min = options.min ?? Math.min(...validValues)
  const max = options.max ?? Math.max(...validValues)
  const range = Math.max(1, max - min)
  const lastIndex = Math.max(1, values.length - 1)
  return values
    .map((value, index) => {
      if (!isChartValue(value)) {
        return null
      }
      const x = (index / lastIndex) * 100
      const y = 46 - ((value - min) / range) * 38
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .filter(Boolean)
    .join(' ')
}

function buildLineChartNodes<T>(
  items: T[],
  valueGetter: (item: T) => number | null | undefined,
  labelGetter: (item: T) => string,
  valueLabelGetter: (item: T) => string,
  options: {
    min?: number
    max?: number
  } = {},
): LineChartNode[] {
  const values = items.map((item) => valueGetter(item))
  const validValues = values.filter(isChartValue)
  if (!validValues.length) {
    return []
  }

  const min = options.min ?? Math.min(...validValues)
  const max = options.max ?? Math.max(...validValues)
  const range = Math.max(1, max - min)
  const lastIndex = Math.max(1, values.length - 1)

  return items
    .map((item, index) => {
      const value = values[index]
      if (!isChartValue(value)) {
        return null
      }

      const x = (index / lastIndex) * 100
      const y = 46 - ((value - min) / range) * 38
      const label = labelGetter(item)
      const valueLabel = valueLabelGetter(item)
      return {
        key: `${label}-${index}`,
        x: x.toFixed(2),
        y: ((y / 52) * 100).toFixed(2),
        label,
        valueLabel,
        ariaLabel: `${label}，${valueLabel}`,
      }
    })
    .filter((item): item is LineChartNode => Boolean(item))
}

function wordCloudStyle(item: DashboardKeywordCloudItem) {
  return {
    fontSize: `${Math.max(0.86, Math.min(1.7, item.weight)).toFixed(2)}rem`,
  }
}

function shouldShowTrendLabel(index: number, total: number) {
  if (total <= 8) {
    return true
  }
  const step = Math.ceil(total / 6)
  return index === 0 || index === total - 1 || index % step === 0
}

const today = new Date()
const sevenDaysAgo = new Date(today)
sevenDaysAgo.setDate(today.getDate() - 6)

const reportFilters = reactive({
  dateFrom: formatDateInput(sevenDaysAgo),
  dateTo: formatDateInput(today),
  generateDate: formatDateInput(today),
  forceRegenerate: false,
})
const dashboardPeriod = ref<'today' | 'week' | 'month'>('week')

const modelOptions = ref<Live2DModelOption[]>([])
const avatarProfiles = ref<AvatarProfileSummary[]>([])
const knowledgeDocs = ref<KnowledgeDocItem[]>([])
const knowledgeTotal = ref(0)
const adminSessions = ref<AdminSessionSummary[]>([])
const selectedSessionId = ref('')
const selectedSessionDetail = ref<AdminSessionDetail | null>(null)
const dailyReports = ref<DailyEmotionReport[]>([])
const reportSummary = ref<ReportRangeSummary | null>(null)
const dashboardOverview = ref<DashboardOverview | null>(null)
const voiceProfiles = ref<VoiceProfile[]>([])
const previewLoadingProfileId = ref<string | null>(null)
const playingProfileId = ref<string | null>(null)
const adminPreviewPresentation = ref<AvatarPresentation>({
  phase: 'idle',
  emotion: 'neutral',
  emotionStage: 'final',
  allowIdleMotion: false,
  motionIntensity: 'none',
  lipSyncActive: false,
  activeReplyId: null,
})
const audioPreviewUrls = new Map<string, string>()
let previewAudio: HTMLAudioElement | null = null

const isAuthenticated = computed(() => Boolean(adminToken.value && adminUsername.value))
const selectedAvatarProfile = computed(
  () => avatarProfiles.value.find((item) => item.id === avatarForm.id) || null,
)
const previewModelPath = computed(() => avatarForm.modelPath || modelOptions.value[0]?.path || MODEL_FALLBACK)
const adminPreviewStageStyle = computed(() => ({
  height: `${Math.round(avatarForm.stageHeight)}px`,
  minHeight: `${Math.round(avatarForm.stageHeight)}px`,
}))
const selectedVoiceProfile = computed(
  () => voiceProfiles.value.find((item) => item.id === avatarForm.voiceProfileId) || null,
)
const currentModelLabel = computed(
  () => modelOptions.value.find((item) => item.path === previewModelPath.value)?.label || '未命名模型',
)
const emotionSummaryEntries = computed(() =>
  Object.entries(reportSummary.value?.emotionCounts || {}).sort((left, right) => right[1] - left[1]),
)
const dashboardTopQuestionMax = computed(() =>
  Math.max(1, ...(dashboardOverview.value?.topQuestions.map((item) => item.count) || [])),
)
const reportEmotionMax = computed(() =>
  Math.max(1, ...(emotionSummaryEntries.value.map(([, count]) => count) || [])),
)
const dashboardServiceTrend = computed(() => dashboardOverview.value?.serviceTrend || [])
const dashboardSatisfactionTrend = computed(() => dashboardOverview.value?.satisfactionTrend || [])
const dashboardKeywordCloudItems = computed(() => dashboardOverview.value?.keywordCloud || [])
const dashboardServiceTrendMax = computed(() =>
  Math.max(1, ...(dashboardServiceTrend.value.map((item) => item.serviceCount) || [])),
)
const dashboardPeriodLabel = computed(() => {
  if (dashboardPeriod.value === 'today') {
    return '今日服务人次'
  }
  if (dashboardPeriod.value === 'month') {
    return '近 30 天服务人次'
  }
  return '本周服务人次'
})
const dashboardServiceLinePoints = computed(() =>
  buildLineChartPoints(dashboardServiceTrend.value, (item) => item.serviceCount),
)
const dashboardServiceChartNodes = computed(() =>
  buildLineChartNodes(
    dashboardServiceTrend.value,
    (item) => item.serviceCount,
    (item) => item.date,
    (item) => `${item.serviceCount} 人次`,
  ),
)
const dashboardSatisfactionLinePoints = computed(() =>
  buildLineChartPoints(dashboardSatisfactionTrend.value, (item) => item.score, {
    min: 2,
    max: 5,
  }),
)
const dashboardSatisfactionChartNodes = computed(() =>
  buildLineChartNodes(
    dashboardSatisfactionTrend.value,
    (item) => item.score,
    (item) => item.date,
    (item) => `${formatScore(item.score)}，${item.messageCount} 条消息`,
    {
      min: 2,
      max: 5,
    },
  ),
)
const sortedDailyReports = computed(() =>
  [...dailyReports.value].sort((left, right) => left.reportDate.localeCompare(right.reportDate)),
)
const reportSentimentLinePoints = computed(() =>
  buildLineChartPoints(sortedDailyReports.value, (report) => sentimentScore(report.overallSentiment), {
    min: 2,
    max: 5,
  }),
)
const reportSentimentChartNodes = computed(() =>
  buildLineChartNodes(
    sortedDailyReports.value,
    (report) => sentimentScore(report.overallSentiment),
    (report) => report.reportDate,
    (report) =>
      `${sentimentLabel(report.overallSentiment)}，${report.sessionCount} 会话，平均响应 ${formatLatency(report.avgAssistantLatencyMs)}`,
    {
      min: 2,
      max: 5,
    },
  ),
)
const voiceProfileCount = computed(() => voiceProfiles.value.length)
const recentKnowledgeDocs = computed(() => knowledgeDocs.value.slice(0, 3))
const recentVoiceProfiles = computed(() => voiceProfiles.value.slice(0, 3))
const knowledgeGapTopStatus = computed(() => {
  return [...(knowledgeGapSummary.value?.statusCounts || [])].sort((left, right) => right.count - left.count)[0] ?? null
})
const knowledgeGapTotalPages = computed(() =>
  Math.max(1, Math.ceil(knowledgeGapTotal.value / Math.max(1, knowledgeGapFilters.size))),
)
const knowledgeGapRangeStart = computed(() => {
  if (!knowledgeGapTotal.value) {
    return 0
  }
  return (knowledgeGapFilters.page - 1) * knowledgeGapFilters.size + 1
})
const knowledgeGapRangeEnd = computed(() =>
  Math.min(knowledgeGapTotal.value, knowledgeGapFilters.page * knowledgeGapFilters.size),
)
const knowledgeGapStatusOptions = computed(() => {
  const statuses = new Set<string>()
  KNOWLEDGE_GAP_STATUS_ORDER.forEach((status) => statuses.add(status))
  knowledgeGapSummary.value?.statusCounts.forEach((item) => {
    if (item.status) {
      statuses.add(item.status)
    }
  })
  knowledgeGapList.value.forEach((item) => {
    if (item.status) {
      statuses.add(item.status)
    }
  })
  if (selectedKnowledgeGap.value?.status) {
    statuses.add(selectedKnowledgeGap.value.status)
  }
  return sortKnowledgeGapStatuses(Array.from(statuses))
})
const selectedKnowledgeGapInList = computed(() =>
  knowledgeGapList.value.some((item) => item.id === selectedKnowledgeGapId.value),
)
const knowledgeGapDraftPayload = computed(() => buildKnowledgeGapDraftPayload())
const knowledgeGapEditorDirty = computed(() => Object.keys(knowledgeGapDraftPayload.value).length > 0)
const filteredAdminSessions = computed(() => {
  const keyword = sessionSearch.value.trim().toLowerCase()
  if (!keyword) {
    return adminSessions.value
  }
  return adminSessions.value.filter((item) => {
    const haystacks = [item.sessionId, item.deviceType, item.lastMessagePreview, item.interestTags.join(' ')]
    return haystacks.some((value) => value.toLowerCase().includes(keyword))
  })
})
const selectedSessionSummary = computed(
  () => adminSessions.value.find((item) => item.sessionId === selectedSessionId.value) ?? null,
)
const selectedSessionReplyTraces = computed(() => selectedSessionDetail.value?.replyTraces ?? [])
const selectedSessionReplyTraceSummary = computed(
  () => selectedSessionDetail.value?.replyTraceSummary ?? null,
)
const latestSessionReplyTrace = computed(() => selectedSessionReplyTraces.value[0] ?? null)
const sessionTraceOverviewCards = computed(() => {
  const summary = selectedSessionReplyTraceSummary.value
  const latest = latestSessionReplyTrace.value
  return [
    {
      label: '最近诊断',
      value: String(summary?.traceCount ?? 0),
      detail: summary?.latestCreatedAt ? `最近一次：${formatDateTime(summary.latestCreatedAt)}` : '当前会话还没有 trace',
    },
    {
      label: '平均 Rerank',
      value: formatLatency(readTraceMetric(summary?.avgMetrics, 'rag_rerank_ms')),
      detail: '检索排序阶段平均耗时',
    },
    {
      label: '平均首包音频',
      value: formatLatency(readTraceMetric(summary?.avgMetrics, 'tts_first_audio_chunk_ms')),
      detail: '从请求开始到首个音频块',
    },
    {
      label: '最新 RAG 准备',
      value: formatLatency(readTraceMetric(latest?.metrics, 'rag_prepare_total_ms')),
      detail: latest ? `reply ${shortTraceReplyId(latest.replyId)}` : '等待新回复进入',
    },
  ]
})
const totalSessionMessageCount = computed(() =>
  adminSessions.value.reduce((sum, item) => sum + item.messageCount, 0),
)
const activePageMeta = computed(
  () => ADMIN_PAGES.find((item) => item.key === activePage.value) ?? ADMIN_PAGES[0],
)
const pageUpdatedText = computed(() => {
  if (activePage.value === 'dashboard' && dashboardOverview.value) {
    return `统计区间：${dashboardOverview.value.dateFrom} 至 ${dashboardOverview.value.dateTo}`
  }
  if (activePage.value === 'knowledge-gaps') {
    if (selectedKnowledgeGap.value) {
      return `最近命中：${formatDateTime(selectedKnowledgeGap.value.lastSeenAt)}`
    }
    if (knowledgeGapSummary.value) {
      return `累计问题 ${knowledgeGapSummary.value.totalQuestions}，命中 ${knowledgeGapSummary.value.totalOccurrences} 次`
    }
    return '知识缺口列表待加载'
  }
  if (activePage.value === 'reports' && reportSummary.value) {
    return `报告区间：${reportSummary.value.dateFrom} 至 ${reportSummary.value.dateTo}`
  }
  if (activePage.value === 'sessions') {
    if (selectedSessionDetail.value) {
      return `会话更新时间：${formatDateTime(selectedSessionDetail.value.updatedAt)}`
    }
    return `已加载会话：${adminSessions.value.length}`
  }
  return `配置更新时间：${formatDateTime(avatarForm.updatedAt)}`
})
const knowledgeStatusCounts = computed(() => {
  return knowledgeDocs.value.reduce(
    (counts, item) => {
      const key = item.status || 'unknown'
      counts[key] = (counts[key] || 0) + 1
      return counts
    },
    {} as Record<string, number>,
  )
})

function resolvePageFromHash(hash: string): AdminPageKey {
  const normalized = hash.replace(/^#/, '').trim().toLowerCase()
  return (
    ADMIN_PAGES.find((item) => item.key === normalized)?.key ??
    'overview'
  )
}

async function navigateToPage(page: AdminPageKey, options: { syncHash?: boolean } = {}) {
  activePage.value = page

  if (options.syncHash !== false) {
    const targetHash = `#${page}`
    if (window.location.hash !== targetHash) {
      history.replaceState(null, '', `${window.location.pathname}${window.location.search}${targetHash}`)
    }
  }

  if (page === 'knowledge') {
    await loadKnowledgeList()
    return
  }

  if (page === 'knowledge-gaps') {
    await loadKnowledgeGapWorkspace({ preserveSelection: true })
    return
  }

  if (page === 'voices') {
    await loadVoiceProfileList()
    return
  }

  if (page === 'avatar') {
    await loadDashboardData()
    return
  }

  if (page === 'dashboard') {
    await loadDashboardAnalyticsData()
    return
  }

  if (page === 'reports') {
    await loadReportsData()
    return
  }

  if (page === 'sessions') {
    await loadAdminSessionsData({ preserveSelection: true })
  }
}

watch(
  () => avatarForm.voiceProfileId,
  (profileId) => {
    if (!profileId) {
      return
    }
    syncVoiceProfileToForm(profileId)
  },
)

watch(
  voiceProfiles,
  () => {
    if (!avatarForm.voiceProfileId) {
      return
    }
    syncVoiceProfileToForm(avatarForm.voiceProfileId)
  },
  { deep: false },
)

watch(
  () => knowledgeGapFilters.status,
  async (status, previousStatus) => {
    if (status === previousStatus || activePage.value !== 'knowledge-gaps') {
      return
    }
    knowledgeGapFilters.page = 1
    await loadKnowledgeGapWorkspace({ preserveSelection: true })
  },
)

watch([adminPreviewPresentation, adminLive2dRef], ([presentation, live2d]) => {
  live2d?.setAvatarPresentation(presentation)
})

function setNotice(kind: NoticeKind, text: string) {
  notice.value = { kind, text }
}

function clearAuthSession() {
  adminToken.value = ''
  adminUsername.value = ''
  modelOptions.value = []
  avatarProfiles.value = []
  knowledgeGapList.value = []
  knowledgeGapTotal.value = 0
  knowledgeGapSummary.value = null
  knowledgeDocs.value = []
  knowledgeTotal.value = 0
  adminSessions.value = []
  selectedSessionId.value = ''
  selectedSessionDetail.value = null
  selectedKnowledgeGapId.value = ''
  selectedKnowledgeGap.value = null
  voiceProfiles.value = []
  dailyReports.value = []
  reportSummary.value = null
  dashboardOverview.value = null
  knowledgeGapFilters.page = 1
  knowledgeGapFilters.status = ''
  knowledgeGapFilters.search = ''
  knowledgeGapSearchInput.value = ''
  resetKnowledgeGapEditor()
  localStorage.removeItem(TOKEN_STORAGE_KEY)
}

function normalizeError(error: unknown, fallback: string) {
  if (error instanceof Error && error.message.trim()) {
    return error.message
  }
  return fallback
}

function handleAdminError(error: unknown, fallback: string) {
  const message = normalizeError(error, fallback)
  if (/令牌|认证|401|Unauthorized/i.test(message)) {
    clearAuthSession()
    setNotice('error', '管理员登录已失效，请重新登录。')
    return
  }
  setNotice('error', message)
}

function applyAvatarDisplayConfig(config: AvatarDisplayConfig) {
  avatarForm.displayScale = Number(config.displayScale.toFixed(2))
  avatarForm.displayOffsetX = Number(config.displayOffsetX.toFixed(2))
  avatarForm.displayOffsetY = Number(config.displayOffsetY.toFixed(2))
  avatarForm.stageHeight = Math.round(config.stageHeight)
}

function updateAdminAvatarDisplay(value: AvatarDisplayConfig) {
  applyAvatarDisplayConfig(clampAvatarDisplayConfig(value))
}

function resetAdminAvatarDisplay() {
  applyAvatarDisplayConfig(AVATAR_DISPLAY_DEFAULTS)
}

function applyAvatarConfig(config: AvatarConfig) {
  const displayConfig = clampAvatarDisplayConfig(config)

  avatarForm.id = config.id
  avatarForm.name = config.name
  avatarForm.slug = config.slug
  avatarForm.isActive = config.isActive
  avatarForm.modelPath = config.modelPath
  avatarForm.voiceId = config.voiceId
  avatarForm.voiceProfileId = config.voiceProfileId || ''
  avatarForm.responseLanguage = config.responseLanguage
  avatarForm.persona = config.persona
  avatarForm.ttsReferenceAudioPath = config.ttsReferenceAudioPath
  avatarForm.ttsReferenceText = config.ttsReferenceText
  avatarForm.ttsSpeed = config.ttsSpeed
  avatarForm.ttsEmotionEnabled = config.ttsEmotionEnabled
  applyAvatarDisplayConfig(displayConfig)
  avatarForm.createdAt = config.createdAt
  avatarForm.updatedAt = config.updatedAt
}

function buildAvatarProfilePayload(name: string) {
  return {
    name,
    modelPath: avatarForm.modelPath,
    voiceId: avatarForm.voiceId,
    voiceProfileId: avatarForm.voiceProfileId || null,
    responseLanguage: avatarForm.responseLanguage,
    persona: avatarForm.persona,
    ttsReferenceAudioPath: avatarForm.ttsReferenceAudioPath,
    ttsReferenceText: avatarForm.ttsReferenceText,
    ttsSpeed: Number(avatarForm.ttsSpeed.toFixed(2)),
    ttsEmotionEnabled: avatarForm.ttsEmotionEnabled,
    displayScale: Number(avatarForm.displayScale.toFixed(2)),
    displayOffsetX: Number(avatarForm.displayOffsetX.toFixed(2)),
    displayOffsetY: Number(avatarForm.displayOffsetY.toFixed(2)),
    stageHeight: Math.round(avatarForm.stageHeight),
    activate: true,
  }
}

function syncVoiceProfileToForm(profileId: string) {
  const profile = voiceProfiles.value.find((item) => item.id === profileId)
  if (!profile) {
    return
  }
  avatarForm.voiceId = profile.name
  avatarForm.ttsReferenceAudioPath = profile.audioPath
  avatarForm.ttsReferenceText = profile.referenceText
}

function sortKnowledgeGapStatuses(statuses: string[]) {
  return [...statuses].sort((left, right) => {
    const leftIndex = KNOWLEDGE_GAP_STATUS_ORDER.indexOf(left as (typeof KNOWLEDGE_GAP_STATUS_ORDER)[number])
    const rightIndex = KNOWLEDGE_GAP_STATUS_ORDER.indexOf(right as (typeof KNOWLEDGE_GAP_STATUS_ORDER)[number])

    if (leftIndex === -1 && rightIndex === -1) {
      return left.localeCompare(right)
    }
    if (leftIndex === -1) {
      return 1
    }
    if (rightIndex === -1) {
      return -1
    }
    return leftIndex - rightIndex
  })
}

function normalizeKnowledgeGapText(value: string | null | undefined) {
  return value ?? ''
}

function normalizeKnowledgeGapStatus(status: string) {
  return status.trim().toLowerCase().replace(/\s+/g, '-')
}

function knowledgeGapStatusLabel(status: string) {
  switch (status) {
    case 'pending':
    case 'open':
      return '待处理'
    case 'draft':
      return '草稿中'
    case 'reviewing':
    case 'in_review':
      return '审核中'
    case 'resolved':
    case 'completed':
      return '已解决'
    case 'imported':
      return '已导入'
    case 'ignored':
      return '已忽略'
    default:
      return status || '未知'
  }
}

function resetKnowledgeGapEditor() {
  knowledgeGapEditor.status = ''
  knowledgeGapEditor.adminTitle = ''
  knowledgeGapEditor.adminCategory = ''
  knowledgeGapEditor.adminAnswer = ''
  knowledgeGapEditor.adminNotes = ''
  knowledgeGapEditor.filenamePrefix = ''
}

function applyKnowledgeGapEditor(item: KnowledgeGapItem) {
  knowledgeGapEditor.status = item.status || 'pending'
  knowledgeGapEditor.adminTitle = normalizeKnowledgeGapText(item.adminTitle)
  knowledgeGapEditor.adminCategory = normalizeKnowledgeGapText(item.adminCategory)
  knowledgeGapEditor.adminAnswer = normalizeKnowledgeGapText(item.adminAnswer)
  knowledgeGapEditor.adminNotes = normalizeKnowledgeGapText(item.adminNotes)
  knowledgeGapEditor.filenamePrefix = ''
}

function resetKnowledgeGapSelection() {
  selectedKnowledgeGapId.value = ''
  selectedKnowledgeGap.value = null
  resetKnowledgeGapEditor()
}

function patchKnowledgeGapListItem(item: KnowledgeGapItem) {
  const index = knowledgeGapList.value.findIndex((entry) => entry.id === item.id)
  if (index === -1) {
    return
  }
  knowledgeGapList.value.splice(index, 1, item)
}

function buildKnowledgeGapDraftPayload(): KnowledgeGapUpdatePayload {
  const item = selectedKnowledgeGap.value
  if (!item) {
    return {}
  }

  const payload: KnowledgeGapUpdatePayload = {}
  if (knowledgeGapEditor.status !== (item.status || 'pending')) {
    payload.status = knowledgeGapEditor.status
  }
  if (knowledgeGapEditor.adminTitle !== normalizeKnowledgeGapText(item.adminTitle)) {
    payload.adminTitle = knowledgeGapEditor.adminTitle
  }
  if (knowledgeGapEditor.adminCategory !== normalizeKnowledgeGapText(item.adminCategory)) {
    payload.adminCategory = knowledgeGapEditor.adminCategory
  }
  if (knowledgeGapEditor.adminAnswer !== normalizeKnowledgeGapText(item.adminAnswer)) {
    payload.adminAnswer = knowledgeGapEditor.adminAnswer
  }
  if (knowledgeGapEditor.adminNotes !== normalizeKnowledgeGapText(item.adminNotes)) {
    payload.adminNotes = knowledgeGapEditor.adminNotes
  }
  return payload
}

function buildKnowledgeGapImportPayload() {
  return {
    ...(knowledgeGapEditor.adminTitle.trim()
      ? { adminTitle: knowledgeGapEditor.adminTitle.trim() }
      : {}),
    ...(knowledgeGapEditor.adminCategory.trim()
      ? { adminCategory: knowledgeGapEditor.adminCategory.trim() }
      : {}),
    ...(knowledgeGapEditor.adminAnswer.trim()
      ? { adminAnswer: knowledgeGapEditor.adminAnswer }
      : {}),
    ...(knowledgeGapEditor.adminNotes.trim()
      ? { adminNotes: knowledgeGapEditor.adminNotes }
      : {}),
    ...(knowledgeGapEditor.filenamePrefix.trim()
      ? { filenamePrefix: knowledgeGapEditor.filenamePrefix.trim() }
      : {}),
  }
}

function resetKnowledgeFileInput() {
  knowledgeUploadFile.value = null
  if (knowledgeFileInput.value) {
    knowledgeFileInput.value.value = ''
  }
}

function resetVoiceFileInput() {
  voiceUploadFile.value = null
  if (voiceFileInput.value) {
    voiceFileInput.value.value = ''
  }
}

function revokeAudioPreviewUrl(profileId: string) {
  const url = audioPreviewUrls.get(profileId)
  if (!url) {
    return
  }
  URL.revokeObjectURL(url)
  audioPreviewUrls.delete(profileId)
}

function releaseAudioPreviewCache() {
  for (const profileId of Array.from(audioPreviewUrls.keys())) {
    revokeAudioPreviewUrl(profileId)
  }
}

function stopVoicePreview() {
  if (previewAudio) {
    previewAudio.pause()
    previewAudio.currentTime = 0
  }
  playingProfileId.value = null
}

function formatDateTime(value: string) {
  if (!value) {
    return '未记录'
  }
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function formatDuration(durationMs: number) {
  if (!durationMs) {
    return '未记录'
  }
  return `${(durationMs / 1000).toFixed(2)} 秒`
}

function statusLabel(status: string) {
  switch (status) {
    case 'ready':
      return '已完成'
    case 'processing':
      return '处理中'
    case 'failed':
      return '失败'
    default:
      return status || '未知'
  }
}

function onKnowledgeFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  knowledgeUploadFile.value = input.files?.[0] || null
}

function onVoiceFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  voiceUploadFile.value = input.files?.[0] || null
}

async function openKnowledgeGap(gapId: string) {
  if (!adminToken.value || !gapId) {
    return
  }

  selectedKnowledgeGapId.value = gapId
  const requestId = ++knowledgeGapDetailRequestId
  loading.knowledgeGapDetail = true
  try {
    const item = await fetchKnowledgeGapDetail(API_BASE_URL, adminToken.value, gapId)
    if (requestId !== knowledgeGapDetailRequestId) {
      return
    }
    selectedKnowledgeGap.value = item
    applyKnowledgeGapEditor(item)
    patchKnowledgeGapListItem(item)
  } catch (error) {
    if (requestId !== knowledgeGapDetailRequestId) {
      return
    }
    selectedKnowledgeGap.value = null
    resetKnowledgeGapEditor()
    handleAdminError(error, '加载知识缺口详情失败。')
  } finally {
    if (requestId === knowledgeGapDetailRequestId) {
      loading.knowledgeGapDetail = false
    }
  }
}

async function loadKnowledgeGapWorkspace(
  options: {
    preserveSelection?: boolean
    focusGapId?: string
  } = {},
) {
  if (!adminToken.value) {
    return
  }

  loading.knowledgeGapReload = true
  try {
    const [summary, result] = await Promise.all([
      fetchKnowledgeGapSummary(API_BASE_URL, adminToken.value),
      fetchKnowledgeGaps(API_BASE_URL, adminToken.value, {
        page: knowledgeGapFilters.page,
        size: knowledgeGapFilters.size,
        status: knowledgeGapFilters.status || undefined,
        search: knowledgeGapFilters.search || undefined,
      }),
    ])

    knowledgeGapSummary.value = summary
    knowledgeGapList.value = result.items
    knowledgeGapTotal.value = result.total

    const totalPages = Math.max(1, Math.ceil(result.total / Math.max(1, knowledgeGapFilters.size)))
    if (knowledgeGapFilters.page > totalPages) {
      knowledgeGapFilters.page = totalPages
      await loadKnowledgeGapWorkspace(options)
      return
    }

    const nextGapId =
      options.focusGapId ||
      (options.preserveSelection && selectedKnowledgeGapId.value ? selectedKnowledgeGapId.value : '') ||
      result.items[0]?.id ||
      ''

    if (nextGapId) {
      await openKnowledgeGap(nextGapId)
      return
    }

    resetKnowledgeGapSelection()
  } catch (error) {
    handleAdminError(error, '加载知识缺口数据失败。')
  } finally {
    loading.knowledgeGapReload = false
  }
}

async function applyKnowledgeGapFilters() {
  knowledgeGapFilters.page = 1
  knowledgeGapFilters.search = knowledgeGapSearchInput.value.trim()
  await loadKnowledgeGapWorkspace({ preserveSelection: true })
}

async function clearKnowledgeGapFilters() {
  const statusChanged = knowledgeGapFilters.status !== ''
  knowledgeGapSearchInput.value = ''
  knowledgeGapFilters.page = 1
  knowledgeGapFilters.search = ''
  knowledgeGapFilters.status = ''
  if (statusChanged) {
    return
  }
  await loadKnowledgeGapWorkspace()
}

async function changeKnowledgeGapPage(nextPage: number) {
  if (
    nextPage < 1 ||
    nextPage > knowledgeGapTotalPages.value ||
    nextPage === knowledgeGapFilters.page ||
    loading.knowledgeGapReload
  ) {
    return
  }

  knowledgeGapFilters.page = nextPage
  await loadKnowledgeGapWorkspace({ preserveSelection: true })
}

async function handleKnowledgeGapSave() {
  if (!adminToken.value || !selectedKnowledgeGap.value) {
    setNotice('error', '请先选择一个知识缺口。')
    return
  }

  const payload = knowledgeGapDraftPayload.value
  if (!Object.keys(payload).length) {
    setNotice('info', '当前没有待保存的修改。')
    return
  }

  loading.knowledgeGapSave = true
  try {
    const item = await updateKnowledgeGap(API_BASE_URL, adminToken.value, selectedKnowledgeGap.value.id, payload)
    selectedKnowledgeGap.value = item
    applyKnowledgeGapEditor(item)
    patchKnowledgeGapListItem(item)
    await loadKnowledgeGapWorkspace({ preserveSelection: true, focusGapId: item.id })
    setNotice('success', '知识缺口草稿已保存。')
  } catch (error) {
    handleAdminError(error, '保存知识缺口草稿失败。')
  } finally {
    loading.knowledgeGapSave = false
  }
}

async function handleKnowledgeGapImport() {
  if (!adminToken.value || !selectedKnowledgeGap.value) {
    setNotice('error', '请先选择一个知识缺口。')
    return
  }
  if (!knowledgeGapEditor.adminAnswer.trim()) {
    setNotice('error', '请先补充整理后的答案，再导入知识库。')
    return
  }

  loading.knowledgeGapImport = true
  try {
    const result = await importKnowledgeGap(
      API_BASE_URL,
      adminToken.value,
      selectedKnowledgeGap.value.id,
      buildKnowledgeGapImportPayload(),
    )
    await loadKnowledgeGapWorkspace({ preserveSelection: true, focusGapId: result.item.id })
    setNotice('success', result.message)
  } catch (error) {
    handleAdminError(error, '导入知识库失败。')
  } finally {
    loading.knowledgeGapImport = false
  }
}

async function loadKnowledgeList() {
  if (!adminToken.value) {
    return
  }

  loading.knowledgeReload = true
  try {
    const result = await fetchKnowledgeDocs(API_BASE_URL, adminToken.value, {
      category: knowledgeCategoryFilter.value.trim() || undefined,
    })
    knowledgeDocs.value = result.items
    knowledgeTotal.value = result.total
  } catch (error) {
    handleAdminError(error, '加载知识库列表失败。')
  } finally {
    loading.knowledgeReload = false
  }
}

async function loadAvatarProfileList() {
  if (!adminToken.value) {
    return
  }

  const result = await fetchAvatarProfiles(API_BASE_URL, adminToken.value)
  avatarProfiles.value = result.items
}

async function switchAvatarProfile(profileId: number) {
  if (!adminToken.value) {
    return
  }

  const config = await activateAvatarProfile(API_BASE_URL, adminToken.value, profileId)
  applyAvatarConfig(config)
  await loadAvatarProfileList()
}

async function handleAvatarProfileChange(event: Event) {
  const value = Number((event.target as HTMLSelectElement).value)
  if (!Number.isFinite(value) || !value) {
    return
  }

  try {
    await switchAvatarProfile(value)
    setNotice('success', '已切换到选中的数字人档案。')
  } catch (error) {
    handleAdminError(error, '切换数字人档案失败。')
  }
}

async function handleCreateAvatarProfile() {
  if (!adminToken.value) {
    return
  }

  const suggestedName = avatarForm.name?.trim() ? `${avatarForm.name}-副本` : '新数字人'
  const name = window.prompt('请输入新的数字人档案名称', suggestedName)?.trim()
  if (!name) {
    return
  }

  loading.avatarProfileCreate = true
  try {
    const config = await createAvatarProfile(
      API_BASE_URL,
      adminToken.value,
      buildAvatarProfilePayload(name),
    )
    applyAvatarConfig(config)
    await loadAvatarProfileList()
    setNotice('success', `已新建并切换到档案“${name}”。`)
  } catch (error) {
    handleAdminError(error, '新建数字人档案失败。')
  } finally {
    loading.avatarProfileCreate = false
  }
}

async function handleDeleteCurrentAvatarProfile() {
  if (!adminToken.value || avatarForm.id === null) {
    return
  }
  if (avatarProfiles.value.length <= 1) {
    setNotice('error', '至少要保留一个数字人档案。')
    return
  }
  if (!window.confirm(`确定删除数字人档案“${avatarForm.name || avatarForm.slug}”吗？`)) {
    return
  }

  loading.avatarProfileDelete = true
  try {
    const result = await deleteAvatarProfile(API_BASE_URL, adminToken.value, avatarForm.id)
    await loadAvatarProfileList()
    const activeProfile = avatarProfiles.value.find((item) => item.isActive) ?? avatarProfiles.value[0] ?? null
    if (activeProfile) {
      applyAvatarConfig(await fetchAvatarConfigByProfile(API_BASE_URL, adminToken.value, activeProfile.id))
    }
    setNotice('success', result.message)
  } catch (error) {
    handleAdminError(error, '删除数字人档案失败。')
  } finally {
    loading.avatarProfileDelete = false
  }
}

async function openAdminSession(sessionId: string) {
  if (!adminToken.value || !sessionId) {
    return
  }

  selectedSessionId.value = sessionId
  loading.sessionDetail = true
  try {
    selectedSessionDetail.value = await fetchAdminSessionDetail(API_BASE_URL, adminToken.value, sessionId)
  } catch (error) {
    selectedSessionDetail.value = null
    handleAdminError(error, '加载会话详情失败。')
  } finally {
    loading.sessionDetail = false
  }
}

async function loadAdminSessionsData(options: { preserveSelection?: boolean } = {}) {
  if (!adminToken.value) {
    return
  }

  loading.sessionReload = true
  try {
    const result = await fetchAdminSessions(API_BASE_URL, adminToken.value, { limit: 80 })
    adminSessions.value = result.items

    if (result.items.length === 0) {
      selectedSessionId.value = ''
      selectedSessionDetail.value = null
      return
    }

    const nextSessionId =
      options.preserveSelection &&
      selectedSessionId.value &&
      result.items.some((item) => item.sessionId === selectedSessionId.value)
        ? selectedSessionId.value
        : result.items[0]?.sessionId || ''

    if (nextSessionId) {
      await openAdminSession(nextSessionId)
    }
  } catch (error) {
    handleAdminError(error, '加载会话记录列表失败。')
  } finally {
    loading.sessionReload = false
  }
}

async function loadVoiceProfileList() {
  if (!adminToken.value) {
    return
  }

  loading.voiceReload = true
  try {
    voiceProfiles.value = await fetchVoiceProfiles(API_BASE_URL, adminToken.value)
    if (avatarForm.voiceProfileId && !voiceProfiles.value.some((item) => item.id === avatarForm.voiceProfileId)) {
      avatarForm.voiceProfileId = ''
    }
  } catch (error) {
    handleAdminError(error, '加载音色资源列表失败。')
  } finally {
    loading.voiceReload = false
  }
}

async function loadDashboardAnalyticsData() {
  if (!adminToken.value) {
    return
  }

  loading.dashboardAnalytics = true
  try {
    dashboardOverview.value = await fetchDashboardOverview(API_BASE_URL, adminToken.value, {
      period: dashboardPeriod.value,
    })
  } catch (error) {
    handleAdminError(error, '加载数据大屏失败。')
  } finally {
    loading.dashboardAnalytics = false
  }
}

async function loadReportsData() {
  if (!adminToken.value) {
    return
  }

  loading.reportReload = true
  try {
    const [summary, reports] = await Promise.all([
      fetchReportSummary(API_BASE_URL, adminToken.value, {
        dateFrom: reportFilters.dateFrom,
        dateTo: reportFilters.dateTo,
      }),
      fetchDailyReports(API_BASE_URL, adminToken.value, {
        dateFrom: reportFilters.dateFrom,
        dateTo: reportFilters.dateTo,
        limit: 31,
      }),
    ])
    reportSummary.value = summary
    dailyReports.value = reports.items
  } catch (error) {
    handleAdminError(error, '加载感受度报告失败。')
  } finally {
    loading.reportReload = false
  }
}

async function loadDashboardData() {
  if (!adminToken.value) {
    return
  }

  loading.dashboard = true
  try {
    const [me, config, models, avatarProfileResult, profiles, docs] = await Promise.all([
      fetchAdminMe(API_BASE_URL, adminToken.value),
      fetchAvatarConfig(API_BASE_URL, adminToken.value),
      fetchLive2DModels(API_BASE_URL, adminToken.value),
      fetchAvatarProfiles(API_BASE_URL, adminToken.value),
      fetchVoiceProfiles(API_BASE_URL, adminToken.value),
      fetchKnowledgeDocs(API_BASE_URL, adminToken.value, {
        category: knowledgeCategoryFilter.value.trim() || undefined,
      }),
    ])

    adminUsername.value = me.username
    modelOptions.value = models
    avatarProfiles.value = avatarProfileResult.items
    voiceProfiles.value = profiles
    knowledgeDocs.value = docs.items
    knowledgeTotal.value = docs.total
    applyAvatarConfig(config)
  } catch (error) {
    handleAdminError(error, '初始化管理后台失败。')
  } finally {
    loading.dashboard = false
  }
}

async function bootstrapAuth() {
  if (!adminToken.value) {
    authReady.value = true
    return
  }

  await loadDashboardData()
  if (activePage.value === 'knowledge-gaps') {
    await loadKnowledgeGapWorkspace({ preserveSelection: true })
  }
  if (activePage.value === 'dashboard') {
    await loadDashboardAnalyticsData()
  }
  if (activePage.value === 'sessions') {
    await loadAdminSessionsData()
  }
  if (activePage.value === 'reports') {
    await loadReportsData()
  }
  authReady.value = true
}

async function submitLogin() {
  authError.value = ''
  notice.value = null

  if (!loginForm.username.trim() || !loginForm.password.trim()) {
    authError.value = '请输入管理员账号和密码。'
    return
  }

  loginPending.value = true
  try {
    const result = await loginAdmin(API_BASE_URL, loginForm.username.trim(), loginForm.password)
    adminToken.value = result.accessToken
    localStorage.setItem(TOKEN_STORAGE_KEY, result.accessToken)
    await loadDashboardData()
    if (activePage.value === 'knowledge-gaps') {
      await loadKnowledgeGapWorkspace({ preserveSelection: true })
    }
    if (activePage.value === 'dashboard') {
      await loadDashboardAnalyticsData()
    }
    if (activePage.value === 'sessions') {
      await loadAdminSessionsData()
    }
    if (activePage.value === 'reports') {
      await loadReportsData()
    }
    loginForm.password = ''
    setNotice('success', '管理后台登录成功。')
  } catch (error) {
    authError.value = normalizeError(error, '管理员登录失败。')
  } finally {
    loginPending.value = false
    authReady.value = true
  }
}

function logout() {
  stopVoicePreview()
  releaseAudioPreviewCache()
  clearAuthSession()
  dailyReports.value = []
  reportSummary.value = null
  setNotice('info', '已退出管理后台。')
}

async function saveAvatarSettings() {
  if (!adminToken.value || avatarForm.id === null) {
    setNotice('error', '当前还没有选中的数字人档案。')
    return
  }

  loading.avatarSave = true
  try {
    const payload: AvatarConfigUpdate = {
      name: avatarForm.name.trim(),
      modelPath: avatarForm.modelPath,
      voiceId: avatarForm.voiceId,
      voiceProfileId: avatarForm.voiceProfileId || null,
      responseLanguage: avatarForm.responseLanguage,
      persona: avatarForm.persona,
      ttsReferenceAudioPath: avatarForm.ttsReferenceAudioPath,
      ttsReferenceText: avatarForm.ttsReferenceText,
      ttsSpeed: Number(avatarForm.ttsSpeed.toFixed(2)),
      ttsEmotionEnabled: avatarForm.ttsEmotionEnabled,
      displayScale: Number(avatarForm.displayScale.toFixed(2)),
      displayOffsetX: Number(avatarForm.displayOffsetX.toFixed(2)),
      displayOffsetY: Number(avatarForm.displayOffsetY.toFixed(2)),
      stageHeight: Math.round(avatarForm.stageHeight),
    }
    const result = await updateAvatarConfig(API_BASE_URL, adminToken.value, payload, { profileId: avatarForm.id })
    applyAvatarConfig(await fetchAvatarConfigByProfile(API_BASE_URL, adminToken.value, avatarForm.id))
    await loadAvatarProfileList()
    setNotice('success', result.message)
  } catch (error) {
    handleAdminError(error, '保存数字人配置失败。')
  } finally {
    loading.avatarSave = false
  }
}

async function handleKnowledgeUpload() {
  if (!adminToken.value || !knowledgeUploadFile.value) {
    setNotice('error', '请先选择要上传的知识库文件。')
    return
  }

  loading.knowledgeUpload = true
  try {
    const result = await uploadKnowledgeDoc(API_BASE_URL, adminToken.value, {
      file: knowledgeUploadFile.value,
      category: knowledgeUploadForm.category.trim() || 'general',
    })
    resetKnowledgeFileInput()
    await loadKnowledgeList()
    setNotice('success', result.message)
  } catch (error) {
    handleAdminError(error, '上传知识库文件失败。')
  } finally {
    loading.knowledgeUpload = false
  }
}

async function handleKnowledgeDelete(doc: KnowledgeDocItem) {
  if (!adminToken.value) {
    return
  }

  if (!window.confirm(`确定删除知识库文档“${doc.filename}”吗？`)) {
    return
  }

  try {
    const result = await deleteKnowledgeDoc(API_BASE_URL, adminToken.value, doc.id)
    await loadKnowledgeList()
    setNotice('success', result.message)
  } catch (error) {
    handleAdminError(error, '删除知识库文档失败。')
  }
}

async function handleVoiceUpload() {
  if (!adminToken.value || !voiceUploadFile.value) {
    setNotice('error', '请先选择音频文件。')
    return
  }
  if (!voiceUploadForm.name.trim() || !voiceUploadForm.referenceText.trim()) {
    setNotice('error', '请填写音色名称和参考文本。')
    return
  }

  loading.voiceUpload = true
  try {
    const result = await uploadVoiceProfile(API_BASE_URL, adminToken.value, {
      file: voiceUploadFile.value,
      name: voiceUploadForm.name.trim(),
      referenceText: voiceUploadForm.referenceText.trim(),
      description: voiceUploadForm.description.trim(),
    })
    voiceUploadForm.name = ''
    voiceUploadForm.referenceText = ''
    voiceUploadForm.description = ''
    resetVoiceFileInput()
    await loadVoiceProfileList()
    avatarForm.voiceProfileId = result.item.id
    syncVoiceProfileToForm(result.item.id)
    setNotice('success', result.message)
  } catch (error) {
    handleAdminError(error, '上传音色资源失败。')
  } finally {
    loading.voiceUpload = false
  }
}

async function handleVoiceDelete(profile: VoiceProfile) {
  if (!adminToken.value) {
    return
  }

  if (!window.confirm(`确定删除音色“${profile.name}”吗？`)) {
    return
  }

  try {
    const result = await deleteVoiceProfile(API_BASE_URL, adminToken.value, profile.id)
    if (playingProfileId.value === profile.id) {
      stopVoicePreview()
    }
    revokeAudioPreviewUrl(profile.id)
    await loadVoiceProfileList()
    setNotice('success', result.message)
  } catch (error) {
    handleAdminError(error, '删除音色资源失败。')
  }
}

function selectVoiceProfile(profileId: string) {
  avatarForm.voiceProfileId = profileId
  syncVoiceProfileToForm(profileId)
}

function enableManualVoiceOverride() {
  avatarForm.voiceProfileId = ''
}

async function toggleVoicePreview(profile: VoiceProfile) {
  if (!adminToken.value) {
    return
  }

  if (!previewAudio) {
    previewAudio = new Audio()
    previewAudio.onended = () => {
      playingProfileId.value = null
    }
    previewAudio.onpause = () => {
      if (previewAudio?.currentTime === 0) {
        playingProfileId.value = null
      }
    }
  }

  if (playingProfileId.value === profile.id && !previewAudio.paused) {
    stopVoicePreview()
    return
  }

  previewLoadingProfileId.value = profile.id
  try {
    let objectUrl = audioPreviewUrls.get(profile.id)
    if (!objectUrl) {
      objectUrl = await fetchVoiceProfileAudioBlobUrl(API_BASE_URL, adminToken.value, profile.id)
      audioPreviewUrls.set(profile.id, objectUrl)
    }

    previewAudio.src = objectUrl
    previewAudio.currentTime = 0
    await previewAudio.play()
    playingProfileId.value = profile.id
  } catch (error) {
    handleAdminError(error, '加载音色试听失败。')
  } finally {
    previewLoadingProfileId.value = null
  }
}

async function handleGenerateReport() {
  if (!adminToken.value) {
    return
  }

  loading.reportGenerate = true
  try {
    const report = await generateDailyReport(API_BASE_URL, adminToken.value, {
      reportDate: reportFilters.generateDate,
      force: reportFilters.forceRegenerate,
    })
    await loadReportsData()
    setNotice('success', `已生成 ${report.reportDate} 的日报分析。`)
  } catch (error) {
    handleAdminError(error, '生成日报失败。')
  } finally {
    loading.reportGenerate = false
  }
}

function formatLatency(value: number | null | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '未统计'
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(2)} s`
  }
  return `${value.toFixed(0)} ms`
}

function readTraceMetric(metrics: Record<string, number> | null | undefined, key: string) {
  if (!metrics) {
    return null
  }
  const value = metrics[key]
  return typeof value === 'number' && !Number.isNaN(value) ? value : null
}

function shortTraceReplyId(replyId: string) {
  if (replyId.length <= 24) {
    return replyId
  }
  return `${replyId.slice(0, 14)}...${replyId.slice(-6)}`
}

function sessionTraceMetricEntries(trace: AdminReplyTrace) {
  return SESSION_TRACE_METRICS.map((item) => ({
    key: item.key,
    label: item.label,
    value: readTraceMetric(trace.metrics, item.key),
  })).filter((item) => item.value !== null)
}

function readTraceChunkNumber(
  chunk: Record<string, number | string | boolean | null>,
  key: string,
) {
  const value = chunk[key]
  return typeof value === 'number' && !Number.isNaN(value) ? value : null
}

function readTraceChunkBoolean(
  chunk: Record<string, number | string | boolean | null>,
  key: string,
) {
  const value = chunk[key]
  return typeof value === 'boolean' ? value : false
}

function sessionTraceChunkMetrics(trace: AdminReplyTrace): SessionTraceChunkMetric[] {
  return trace.ttsChunks.slice(0, SESSION_TRACE_CHUNK_LIMIT).map((chunk) => ({
    seq: readTraceChunkNumber(chunk, 'seq') ?? 0,
    chunkIndex: readTraceChunkNumber(chunk, 'chunk_index') ?? 0,
    tokenOffset: readTraceChunkNumber(chunk, 'token_offset') ?? 0,
    tokenWaitMs: readTraceChunkNumber(chunk, 'token_wait_ms'),
    token2wavMs: readTraceChunkNumber(chunk, 'token2wav_ms'),
    audioMs: readTraceChunkNumber(chunk, 'tts_chunk_audio_ms'),
    supplyLagMs: readTraceChunkNumber(chunk, 'chunk_supply_lag_ms'),
    realRtf: readTraceChunkNumber(chunk, 'tts_chunk_real_rtf'),
    readyRatio:
      readTraceChunkNumber(chunk, 'tts_chunk_ready_ratio') ?? readTraceChunkNumber(chunk, 'tts_chunk_rtf'),
    isFinal: readTraceChunkBoolean(chunk, 'is_final'),
  }))
}

function formatRatio(value: number | null | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '--'
  }
  return `${value.toFixed(2)}x`
}

function traceRuntimeBadges(trace: AdminReplyTrace) {
  const badges: string[] = []
  badges.push(trace.streaming ? 'Streaming' : 'Non-streaming')
  if (trace.promptCacheHit === true) {
    badges.push('Prompt 缓存命中')
  } else if (trace.promptCacheHit === false) {
    badges.push(
      trace.promptCacheBuildMs !== null
        ? `Prompt 构建 ${Math.round(trace.promptCacheBuildMs)}ms`
        : 'Prompt 未命中',
    )
  }
  if (trace.torchDeviceName) {
    badges.push(trace.torchDeviceName)
  } else if (trace.torchCudaAvailable) {
    badges.push('CUDA 可用')
  }
  if (trace.requestedOnnxProvider) {
    badges.push(`ONNX ${trace.requestedOnnxProvider}`)
  }
  return badges
}

function sentimentLabel(value: string) {
  switch (value) {
    case 'positive':
      return '积极'
    case 'negative':
      return '需关注'
    case 'neutral':
      return '平稳'
    default:
      return value || '未标注'
  }
}

onMounted(async () => {
  activePage.value = resolvePageFromHash(window.location.hash)
  window.addEventListener('hashchange', handleHashChange)
  await bootstrapAuth()
})

onBeforeUnmount(() => {
  window.removeEventListener('hashchange', handleHashChange)
  stopVoicePreview()
  previewAudio = null
  releaseAudioPreviewCache()
})

async function handleHashChange() {
  await navigateToPage(resolvePageFromHash(window.location.hash), { syncHash: false })
}
</script>

<template>
  <div class="admin-root">
    <div v-if="!authReady" class="admin-login-shell">
      <section class="admin-login-card">
        <p class="admin-eyebrow">AI Chat Live2D</p>
        <h1>管理后台加载中</h1>
      </section>
    </div>

    <div v-else-if="!isAuthenticated" class="admin-login-shell">
      <section class="admin-login-card">
        <p class="admin-eyebrow">AI Chat Live2D</p>
        <h1>管理后台登录</h1>
        <p class="admin-subtitle">使用管理员账号维护知识库、音色资源与数字人配置。</p>

        <form class="admin-login-form" @submit.prevent="submitLogin">
          <label class="admin-field">
            <span>管理员账号</span>
            <input v-model.trim="loginForm.username" type="text" autocomplete="username" />
          </label>

          <label class="admin-field">
            <span>管理员密码</span>
            <input
              v-model="loginForm.password"
              type="password"
              autocomplete="current-password"
              placeholder="请输入密码"
            />
          </label>

          <p v-if="authError" class="admin-inline-error">{{ authError }}</p>
          <button class="admin-primary-button admin-full-width" type="submit" :disabled="loginPending">
            {{ loginPending ? '登录中...' : '登录' }}
          </button>
        </form>
      </section>
    </div>

    <div v-else class="admin-shell">
      <aside class="admin-sidebar">
        <div class="admin-brand">
          <p class="admin-eyebrow">Phase 4</p>
          <h1>管理后台</h1>
          <p class="admin-subtitle">按模块切换管理页面，避免所有能力堆叠在同一长页。</p>
        </div>

        <nav class="admin-nav">
          <button
            v-for="item in ADMIN_PAGES"
            :key="item.key"
            class="admin-nav-button"
            :data-active="activePage === item.key"
            type="button"
            @click="navigateToPage(item.key)"
          >
            <span class="admin-nav-label">{{ item.label }}</span>
            <span class="admin-nav-caption">{{ item.eyebrow }}</span>
          </button>
        </nav>

        <dl class="admin-summary-list">
          <div>
            <dt>当前管理员</dt>
            <dd>{{ adminUsername }}</dd>
          </div>
          <div>
            <dt>知识库文档</dt>
            <dd>{{ knowledgeTotal }}</dd>
          </div>
          <div>
            <dt>音色资源</dt>
            <dd>{{ voiceProfileCount }}</dd>
          </div>
          <div>
            <dt>当前模型</dt>
            <dd>{{ currentModelLabel }}</dd>
          </div>
        </dl>

        <div class="admin-sidebar-actions">
          <button class="admin-secondary-button" type="button" :disabled="loading.dashboard" @click="loadDashboardData">
            {{ loading.dashboard ? '刷新中...' : '刷新后台数据' }}
          </button>
          <button class="admin-ghost-button" type="button" @click="logout">退出登录</button>
        </div>
      </aside>

      <main class="admin-main">
        <header class="admin-page-header">
          <div>
            <p class="admin-section-tag">{{ activePageMeta.eyebrow }}</p>
            <h2>{{ activePageMeta.title }}</h2>
            <p class="admin-subtitle admin-page-summary">{{ activePageMeta.description }}</p>
          </div>
          <p class="admin-updated-at">{{ pageUpdatedText }}</p>
        </header>

        <p v-if="notice" class="admin-notice" :data-kind="notice.kind">{{ notice.text }}</p>

        <div v-if="activePage === 'overview'" class="admin-page-stack">
          <section class="admin-overview-stats">
            <article class="admin-stat-card">
              <span>知识库文档</span>
              <strong>{{ knowledgeTotal }}</strong>
              <p>已完成 {{ knowledgeStatusCounts.ready || 0 }}，处理中 {{ knowledgeStatusCounts.processing || 0 }}</p>
            </article>
            <article class="admin-stat-card">
              <span>音色资源</span>
              <strong>{{ voiceProfileCount }}</strong>
              <p>{{ selectedVoiceProfile ? `当前使用 ${selectedVoiceProfile.name}` : '当前使用自定义参考音频' }}</p>
            </article>
            <article class="admin-stat-card">
              <span>当前模型</span>
              <strong>{{ currentModelLabel }}</strong>
              <p>{{ previewModelPath }}</p>
            </article>
          </section>

          <div class="admin-grid admin-grid-overview">
            <section class="admin-panel admin-preview-panel">
              <div class="admin-panel-header">
                <div>
                  <p class="admin-section-tag">实时预览</p>
                  <h3>Live2D 当前形态</h3>
                </div>
                <span class="admin-badge">{{ currentModelLabel }}</span>
              </div>

              <div class="admin-preview-stage">
                <Live2DStage :model-path="previewModelPath" />
              </div>

              <div class="admin-preview-meta">
                <div>
                  <span>模型路径</span>
                  <strong>{{ previewModelPath }}</strong>
                </div>
                <div>
                  <span>音色模式</span>
                  <strong>{{ selectedVoiceProfile ? selectedVoiceProfile.name : '自定义参考音频' }}</strong>
                </div>
                <div>
                  <span>TTS 语速</span>
                  <strong>{{ avatarForm.ttsSpeed.toFixed(2) }}x</strong>
                </div>
              </div>
            </section>

            <section class="admin-panel">
              <div class="admin-panel-header">
                <div>
                  <p class="admin-section-tag">快捷入口</p>
                  <h3>按模块进入管理页面</h3>
                </div>
              </div>

              <div class="admin-quick-actions">
                <button class="admin-quick-card" type="button" @click="navigateToPage('dashboard')">
                  <strong>数据大屏</strong>
                  <span>查看会话规模、在线人数、热门问题和情绪趋势。</span>
                </button>
                <button class="admin-quick-card" type="button" @click="navigateToPage('avatar')">
                  <strong>数字人管理</strong>
                  <span>调整 Live2D、Prompt、参考音频和情感开关。</span>
                </button>
                <button class="admin-quick-card" type="button" @click="navigateToPage('voices')">
                  <strong>音色资源</strong>
                  <span>上传、试听并切换 voice profile。</span>
                </button>
                <button class="admin-quick-card" type="button" @click="navigateToPage('knowledge')">
                  <strong>知识库管理</strong>
                  <span>上传资料、观察处理状态、删除旧文档。</span>
                </button>
                <button class="admin-quick-card" type="button" @click="navigateToPage('knowledge-gaps')">
                  <strong>知识缺口</strong>
                  <span>查看热点未命中问题、保存草稿答案，并把整理结果导入知识库。</span>
                </button>
                <button class="admin-quick-card" type="button" @click="navigateToPage('sessions')">
                  <strong>会话记录</strong>
                  <span>查看真实 messages 时间线、情绪标签和回复耗时。</span>
                </button>
                <button class="admin-quick-card" type="button" @click="navigateToPage('reports')">
                  <strong>感受度报告</strong>
                  <span>查看情绪趋势、关注点分析、日报摘要和响应延迟概况。</span>
                </button>
              </div>

              <div class="admin-overview-list-grid">
                <div class="admin-overview-list">
                  <h4>最近知识文档</h4>
                  <p v-if="!recentKnowledgeDocs.length" class="admin-empty-hint">暂无知识库文档。</p>
                  <article v-for="doc in recentKnowledgeDocs" :key="doc.id" class="admin-mini-card">
                    <strong>{{ doc.filename }}</strong>
                    <span>{{ doc.category }} · {{ statusLabel(doc.status) }}</span>
                  </article>
                </div>

                <div class="admin-overview-list">
                  <h4>最近音色资源</h4>
                  <p v-if="!recentVoiceProfiles.length" class="admin-empty-hint">暂无音色资源。</p>
                  <article v-for="profile in recentVoiceProfiles" :key="profile.id" class="admin-mini-card">
                    <strong>{{ profile.name }}</strong>
                    <span>{{ formatDuration(profile.durationMs) }}</span>
                  </article>
                </div>
              </div>
            </section>
          </div>
        </div>

        <div v-else-if="activePage === 'dashboard'" class="admin-page-stack">
          <section class="admin-panel admin-panel-wide">
            <div class="admin-panel-header">
              <div>
                <p class="admin-section-tag">Phase 4 数据大屏</p>
                <h3>五项运营指标</h3>
              </div>
              <div class="admin-inline-actions">
                <label class="admin-field admin-dashboard-period">
                  <span>统计范围</span>
                  <select v-model="dashboardPeriod" @change="loadDashboardAnalyticsData">
                    <option value="today">今天</option>
                    <option value="week">近 7 天</option>
                    <option value="month">近 30 天</option>
                  </select>
                </label>
                <button class="admin-secondary-button" type="button" :disabled="loading.dashboardAnalytics" @click="loadDashboardAnalyticsData">
                  {{ loading.dashboardAnalytics ? '刷新中...' : '刷新大屏' }}
                </button>
              </div>
            </div>
            <p class="admin-report-summary-text">
              {{ dashboardOverview?.summaryText || '暂无可展示的数据，先生成几轮会话后再来看大屏会更有感觉。' }}
            </p>
          </section>

          <div class="admin-dashboard-roadmap-grid">
            <section class="admin-panel admin-dashboard-module admin-dashboard-module-wide">
              <div class="admin-panel-header">
                <div>
                  <p class="admin-section-tag">01 折线图</p>
                  <h3>{{ dashboardPeriodLabel }}</h3>
                </div>
                <span class="admin-badge">累计 {{ dashboardOverview?.serviceCount ?? 0 }} 人次</span>
              </div>

              <div class="admin-line-chart" :data-empty="dashboardServiceLinePoints ? 'false' : 'true'">
                <svg viewBox="0 0 100 52" preserveAspectRatio="none" aria-hidden="true">
                  <line x1="0" y1="8" x2="100" y2="8" />
                  <line x1="0" y1="27" x2="100" y2="27" />
                  <line x1="0" y1="46" x2="100" y2="46" />
                  <polyline v-if="dashboardServiceLinePoints" class="admin-line-chart-path" :points="dashboardServiceLinePoints" />
                </svg>
                <div v-if="dashboardServiceChartNodes.length" class="admin-line-chart-node-layer">
                  <button
                    v-for="node in dashboardServiceChartNodes"
                    :key="node.key"
                    class="admin-line-chart-node"
                    type="button"
                    :style="{ left: `${node.x}%`, top: `${node.y}%` }"
                    :aria-label="node.ariaLabel"
                    :title="node.ariaLabel"
                  >
                    <span class="admin-line-chart-dot"></span>
                    <span class="admin-line-chart-tooltip">{{ node.label }}：{{ node.valueLabel }}</span>
                  </button>
                </div>
                <p v-if="!dashboardServiceLinePoints" class="admin-empty-hint">暂无服务趋势数据。</p>
              </div>

              <div class="admin-line-chart-axis">
                <span
                  v-for="(item, index) in dashboardServiceTrend"
                  :key="item.date"
                  :data-visible="shouldShowTrendLabel(index, dashboardServiceTrend.length)"
                >
                  {{ item.date.slice(5) }}
                </span>
              </div>

              <dl class="admin-dashboard-metric-row">
                <div>
                  <dt>峰值</dt>
                  <dd>{{ dashboardServiceTrendMax }} 人次</dd>
                </div>
                <div>
                  <dt>会话</dt>
                  <dd>{{ dashboardOverview?.sessionCount ?? 0 }}</dd>
                </div>
                <div>
                  <dt>消息</dt>
                  <dd>{{ dashboardOverview?.messageCount ?? 0 }}</dd>
                </div>
              </dl>
            </section>

            <section class="admin-panel admin-dashboard-module">
              <div class="admin-panel-header">
                <div>
                  <p class="admin-section-tag">02 条形图</p>
                  <h3>热门问答 Top10</h3>
                </div>
                <span class="admin-badge">{{ dashboardOverview?.topQuestions?.length ?? 0 }} 条</span>
              </div>

              <div class="admin-question-list admin-question-list-compact">
                <article v-for="item in dashboardOverview?.topQuestions || []" :key="item.question" class="admin-question-card">
                  <div class="admin-question-card-row">
                    <div>
                      <h4>{{ item.question }}</h4>
                      <p>{{ item.count }} 次</p>
                    </div>
                    <strong>{{ item.count }}</strong>
                  </div>
                  <div class="admin-question-bar">
                    <i :style="{ width: questionBarWidth(item.count) }"></i>
                  </div>
                </article>
                <p v-if="!(dashboardOverview?.topQuestions?.length)" class="admin-empty-hint">暂无热门问题数据。</p>
              </div>
            </section>

            <section class="admin-panel admin-dashboard-module admin-dashboard-module-wide">
              <div class="admin-panel-header">
                <div>
                  <p class="admin-section-tag">03 情感评分折线</p>
                  <h3>游客满意度趋势</h3>
                </div>
                <span class="admin-badge">均值 {{ formatScore(dashboardOverview?.avgSatisfaction ?? null) }}</span>
              </div>

              <div class="admin-line-chart admin-line-chart-warm" :data-empty="dashboardSatisfactionLinePoints ? 'false' : 'true'">
                <svg viewBox="0 0 100 52" preserveAspectRatio="none" aria-hidden="true">
                  <line x1="0" y1="8" x2="100" y2="8" />
                  <line x1="0" y1="27" x2="100" y2="27" />
                  <line x1="0" y1="46" x2="100" y2="46" />
                  <polyline v-if="dashboardSatisfactionLinePoints" class="admin-line-chart-path" :points="dashboardSatisfactionLinePoints" />
                </svg>
                <div v-if="dashboardSatisfactionChartNodes.length" class="admin-line-chart-node-layer">
                  <button
                    v-for="node in dashboardSatisfactionChartNodes"
                    :key="node.key"
                    class="admin-line-chart-node"
                    type="button"
                    :style="{ left: `${node.x}%`, top: `${node.y}%` }"
                    :aria-label="node.ariaLabel"
                    :title="node.ariaLabel"
                  >
                    <span class="admin-line-chart-dot"></span>
                    <span class="admin-line-chart-tooltip">{{ node.label }}：{{ node.valueLabel }}</span>
                  </button>
                </div>
                <p v-if="!dashboardSatisfactionLinePoints" class="admin-empty-hint">暂无满意度趋势数据。</p>
              </div>

              <div class="admin-line-chart-axis">
                <span
                  v-for="(item, index) in dashboardSatisfactionTrend"
                  :key="item.date"
                  :data-visible="shouldShowTrendLabel(index, dashboardSatisfactionTrend.length)"
                >
                  {{ item.date.slice(5) }}
                </span>
              </div>

              <dl class="admin-dashboard-metric-row">
                <div>
                  <dt>整体情绪</dt>
                  <dd>{{ sentimentLabel(dashboardOverview?.overallSentiment || 'neutral') }}</dd>
                </div>
                <div>
                  <dt>平均响应</dt>
                  <dd>{{ formatLatency(dashboardOverview?.avgLatencyMs ?? null) }}</dd>
                </div>
                <div>
                  <dt>助手消息</dt>
                  <dd>{{ dashboardOverview?.assistantMessageCount ?? 0 }}</dd>
                </div>
              </dl>
            </section>

            <section class="admin-panel admin-dashboard-module">
              <div class="admin-panel-header">
                <div>
                  <p class="admin-section-tag">04 词云</p>
                  <h3>关注点词云</h3>
                </div>
                <span class="admin-badge">高频实体词</span>
              </div>

              <div class="admin-word-cloud">
                <span
                  v-for="item in dashboardKeywordCloudItems"
                  :key="`${item.source}-${item.word}`"
                  class="admin-word-cloud-item"
                  :data-source="item.source"
                  :style="wordCloudStyle(item)"
                >
                  {{ item.word }}
                  <small>{{ item.count }}</small>
                </span>
                <p v-if="!dashboardKeywordCloudItems.length" class="admin-empty-hint">暂无关注点词云数据。</p>
              </div>
            </section>

            <section class="admin-panel admin-dashboard-module admin-realtime-panel">
              <div class="admin-panel-header">
                <div>
                  <p class="admin-section-tag">05 实时</p>
                  <h3>实时在线人数</h3>
                </div>
                <span class="admin-badge">近 10 分钟</span>
              </div>

              <div class="admin-realtime-display">
                <strong>{{ dashboardOverview?.realtimeOnlineCount ?? 0 }}</strong>
                <span>online</span>
              </div>

              <dl class="admin-dashboard-metric-row admin-dashboard-metric-row-compact">
                <div>
                  <dt>游客消息</dt>
                  <dd>{{ dashboardOverview?.userMessageCount ?? 0 }}</dd>
                </div>
                <div>
                  <dt>统计周期</dt>
                  <dd>{{ dashboardOverview?.dateFrom ?? '--' }} 至 {{ dashboardOverview?.dateTo ?? '--' }}</dd>
                </div>
              </dl>
              <p class="admin-report-summary-text">
                在线人数按最近仍有活动的会话估算，用于现场运营和联调观察。
              </p>
            </section>
          </div>
        </div>

        <div v-else-if="activePage === 'avatar'" class="admin-grid">
          <section class="admin-panel admin-preview-panel">
            <div class="admin-panel-header">
              <div>
                <p class="admin-section-tag">实时预览</p>
                <h3>Live2D 当前形态</h3>
              </div>
              <span class="admin-badge">{{ selectedAvatarProfile?.name || currentModelLabel }}</span>
            </div>

            <div class="admin-preview-stage" :style="adminPreviewStageStyle">
              <Live2DStage
                ref="adminLive2dRef"
                :model-path="previewModelPath"
                :model-scale="avatarForm.displayScale"
                :model-offset-x="avatarForm.displayOffsetX"
                :model-offset-y="avatarForm.displayOffsetY"
              />
            </div>

            <div class="admin-preview-meta">
              <div>
                <span>模型路径</span>
                <strong>{{ previewModelPath }}</strong>
              </div>
              <div>
                <span>音色模式</span>
                <strong>{{ selectedVoiceProfile ? selectedVoiceProfile.name : '自定义参考音频' }}</strong>
              </div>
              <div>
                <span>TTS 语速</span>
                <strong>{{ avatarForm.ttsSpeed.toFixed(2) }}x</strong>
              </div>
            </div>

            <AdminEmotionPreviewPanel @preview="adminPreviewPresentation = $event" />
          </section>

          <section class="admin-panel">
            <div class="admin-panel-header">
              <div>
                <p class="admin-section-tag">数字人配置</p>
                <h3>模型 / 声音 / Prompt</h3>
              </div>
            </div>

            <form class="admin-form" @submit.prevent="saveAvatarSettings">
              <div class="admin-avatar-profile-toolbar">
                <label class="admin-field">
                  <span>数字人档案</span>
                  <select :value="avatarForm.id ?? ''" @change="handleAvatarProfileChange">
                    <option v-for="item in avatarProfiles" :key="item.id" :value="item.id">
                      {{ item.name }}{{ item.isActive ? '（当前）' : '' }}
                    </option>
                  </select>
                </label>

                <div class="admin-inline-actions">
                  <button class="admin-secondary-button" type="button" :disabled="loading.avatarProfileCreate" @click="handleCreateAvatarProfile">
                    {{ loading.avatarProfileCreate ? '新建中...' : '另存为新档案' }}
                  </button>
                  <button
                    class="admin-danger-button"
                    type="button"
                    :disabled="loading.avatarProfileDelete || avatarProfiles.length <= 1 || avatarForm.id === null"
                    @click="handleDeleteCurrentAvatarProfile"
                  >
                    {{ loading.avatarProfileDelete ? '删除中...' : '删除当前档案' }}
                  </button>
                </div>
              </div>

              <label class="admin-field">
                <span>档案名称</span>
                <input v-model.trim="avatarForm.name" type="text" placeholder="例如：默认导览 / Neuro 彩蛋" />
              </label>
              <label class="admin-field">
                <span>Live2D 模型</span>
                <select v-model="avatarForm.modelPath">
                  <option v-for="item in modelOptions" :key="item.path" :value="item.path">
                    {{ item.label }} · {{ item.path }}
                  </option>
                </select>
              </label>

              <label class="admin-field">
                <span>音色资源</span>
                <select v-model="avatarForm.voiceProfileId">
                  <option value="">自定义参考音频</option>
                  <option v-for="item in voiceProfiles" :key="item.id" :value="item.id">
                    {{ item.name }}{{ item.isDefault ? '（默认）' : '' }}
                  </option>
                </select>
              </label>

              <div class="admin-inline-actions">
                <button class="admin-secondary-button" type="button" :disabled="!selectedVoiceProfile" @click="enableManualVoiceOverride">
                  切到自定义参考音频
                </button>
                <span v-if="selectedVoiceProfile" class="admin-inline-hint">
                  当前音色：{{ selectedVoiceProfile.name }}，保存后会同步参考音频与文本。
                </span>
              </div>

              <label class="admin-field">
                <span>兼容 voice_id</span>
                <input v-model.trim="avatarForm.voiceId" type="text" placeholder="仅作兼容展示字段" />
              </label>

              <label class="admin-field">
                <span>默认回答语言</span>
                <select v-model="avatarForm.responseLanguage">
                  <option value="zh">中文</option>
                  <option value="en">English</option>
                </select>
              </label>

              <label class="admin-field">
                <span>参考音频路径</span>
                <input
                  v-model.trim="avatarForm.ttsReferenceAudioPath"
                  type="text"
                  :readonly="Boolean(selectedVoiceProfile)"
                  placeholder="./storage/vendor/CosyVoice/asset/zero_shot_prompt.wav"
                />
              </label>

              <label class="admin-field">
                <span>参考文本</span>
                <textarea
                  v-model.trim="avatarForm.ttsReferenceText"
                  rows="3"
                  :readonly="Boolean(selectedVoiceProfile)"
                  placeholder="请输入参考音频对应文本"
                />
              </label>

              <div class="admin-field-grid">
                <label class="admin-field">
                  <span>TTS 语速</span>
                  <input v-model.number="avatarForm.ttsSpeed" type="number" min="0.5" max="1.5" step="0.05" />
                </label>

                <label class="admin-field admin-checkbox-field">
                  <span>情感控制</span>
                  <input v-model="avatarForm.ttsEmotionEnabled" type="checkbox" />
                </label>
              </div>

              <label class="admin-field">
                <span>系统 Prompt</span>
                <textarea v-model.trim="avatarForm.persona" rows="6" placeholder="请输入数字人系统人设 Prompt" />
                <span class="admin-inline-hint">
                  当前语言为 {{ avatarForm.responseLanguage === 'en' ? 'English' : '中文' }}。如需英语数字人，建议在 Prompt 里继续保留英语人设描述。
                </span>
              </label>

              <section class="admin-form-section">
                <div>
                  <p class="admin-section-tag">展示参数</p>
                  <h4>Live2D 缩放 / 偏移</h4>
                </div>
                <AvatarDisplayControls
                  :model-value="{
                    displayScale: avatarForm.displayScale,
                    displayOffsetX: avatarForm.displayOffsetX,
                    displayOffsetY: avatarForm.displayOffsetY,
                    stageHeight: avatarForm.stageHeight
                  }"
                  @update:model-value="updateAdminAvatarDisplay"
                  @reset="resetAdminAvatarDisplay"
                />
              </section>

              <button class="admin-primary-button" type="submit" :disabled="loading.avatarSave">
                {{ loading.avatarSave ? '保存中...' : '保存数字人配置' }}
              </button>
            </form>
          </section>
        </div>

        <div v-else-if="activePage === 'voices'" class="admin-page-stack">
          <section class="admin-panel">
            <div class="admin-panel-header">
              <div>
                <p class="admin-section-tag">音色资源库</p>
                <h3>上传 / 试听 / 绑定音色</h3>
              </div>
              <button class="admin-secondary-button" type="button" :disabled="loading.voiceReload" @click="loadVoiceProfileList">
                {{ loading.voiceReload ? '刷新中...' : '刷新音色列表' }}
              </button>
            </div>

            <form class="admin-form admin-upload-form" @submit.prevent="handleVoiceUpload">
              <label class="admin-field">
                <span>音色名称</span>
                <input v-model.trim="voiceUploadForm.name" type="text" placeholder="例如：亲和女声 / 讲解男声" />
              </label>

              <label class="admin-field">
                <span>参考文本</span>
                <textarea v-model.trim="voiceUploadForm.referenceText" rows="2" placeholder="与音频内容一致的文本" />
              </label>

              <label class="admin-field">
                <span>描述</span>
                <input v-model.trim="voiceUploadForm.description" type="text" placeholder="可选：适合场景、语气风格" />
              </label>

              <label class="admin-field">
                <span>音频文件</span>
                <input ref="voiceFileInput" type="file" accept=".wav,.mp3,.m4a,.flac,.ogg" @change="onVoiceFileSelected" />
              </label>

              <button class="admin-primary-button" type="submit" :disabled="loading.voiceUpload">
                {{ loading.voiceUpload ? '上传中...' : '上传音色资源' }}
              </button>
            </form>
          </section>

          <section class="admin-panel">
            <div class="admin-list">
              <article v-for="profile in voiceProfiles" :key="profile.id" class="admin-list-card">
                <div class="admin-list-card-header">
                  <div>
                    <h4>{{ profile.name }}</h4>
                    <p>{{ profile.description || '未填写描述' }}</p>
                  </div>
                  <div class="admin-chip-row">
                    <span v-if="profile.isDefault" class="admin-badge">默认</span>
                    <span v-if="avatarForm.voiceProfileId === profile.id" class="admin-badge admin-badge-accent">当前选中</span>
                  </div>
                </div>

                <dl class="admin-voice-meta">
                  <div>
                    <dt>文件</dt>
                    <dd>{{ profile.sourceFilename }}</dd>
                  </div>
                  <div>
                    <dt>时长</dt>
                    <dd>{{ formatDuration(profile.durationMs) }}</dd>
                  </div>
                  <div>
                    <dt>参考文本</dt>
                    <dd>{{ profile.referenceText }}</dd>
                  </div>
                </dl>

                <div class="admin-inline-actions">
                  <button class="admin-secondary-button" type="button" @click="selectVoiceProfile(profile.id)">
                    用于当前配置
                  </button>
                  <button
                    class="admin-secondary-button"
                    type="button"
                    :disabled="previewLoadingProfileId === profile.id"
                    @click="toggleVoicePreview(profile)"
                  >
                    {{
                      previewLoadingProfileId === profile.id
                        ? '加载中...'
                        : playingProfileId === profile.id
                          ? '停止试听'
                          : '试听'
                    }}
                  </button>
                  <button class="admin-danger-button" type="button" @click="handleVoiceDelete(profile)">
                    删除
                  </button>
                </div>
              </article>
            </div>
          </section>
        </div>

        <div v-else-if="activePage === 'knowledge'" class="admin-page-stack">
          <section class="admin-panel">
            <div class="admin-panel-header">
              <div>
                <p class="admin-section-tag">知识库管理</p>
                <h3>上传文档、观察处理状态、删除旧文档</h3>
              </div>
              <button class="admin-secondary-button" type="button" :disabled="loading.knowledgeReload" @click="loadKnowledgeList">
                {{ loading.knowledgeReload ? '刷新中...' : '刷新文档列表' }}
              </button>
            </div>

            <div class="admin-knowledge-toolbar">
              <form class="admin-toolbar-form" @submit.prevent="handleKnowledgeUpload">
                <label class="admin-field">
                  <span>分类</span>
                  <input v-model.trim="knowledgeUploadForm.category" type="text" placeholder="history / faq / guide" />
                </label>
                <label class="admin-field">
                  <span>上传文件</span>
                  <input
                    ref="knowledgeFileInput"
                    type="file"
                    accept=".txt,.md,.pdf,.docx,.xlsx"
                    @change="onKnowledgeFileSelected"
                  />
                </label>
                <button class="admin-primary-button" type="submit" :disabled="loading.knowledgeUpload">
                  {{ loading.knowledgeUpload ? '上传中...' : '上传并入库' }}
                </button>
              </form>

              <div class="admin-toolbar-side">
                <label class="admin-field">
                  <span>分类筛选</span>
                  <input v-model.trim="knowledgeCategoryFilter" type="text" placeholder="留空查看全部" />
                </label>
                <button class="admin-secondary-button" type="button" @click="loadKnowledgeList">应用筛选</button>
              </div>
            </div>

            <div class="admin-chip-row admin-chip-row-wrap">
              <span class="admin-badge">总数 {{ knowledgeTotal }}</span>
              <span class="admin-badge">已完成 {{ knowledgeStatusCounts.ready || 0 }}</span>
              <span class="admin-badge">处理中 {{ knowledgeStatusCounts.processing || 0 }}</span>
              <span class="admin-badge">失败 {{ knowledgeStatusCounts.failed || 0 }}</span>
            </div>
          </section>

          <section class="admin-panel">
            <div class="admin-doc-list">
              <article v-for="doc in knowledgeDocs" :key="doc.id" class="admin-doc-card">
                <div class="admin-doc-header">
                  <div>
                    <h4>{{ doc.filename }}</h4>
                    <p>{{ doc.category }} · {{ formatDateTime(doc.uploadedAt) }}</p>
                  </div>
                  <div class="admin-chip-row">
                    <span class="admin-badge" :data-status="doc.status">{{ statusLabel(doc.status) }}</span>
                    <button class="admin-danger-button" type="button" @click="handleKnowledgeDelete(doc)">删除</button>
                  </div>
                </div>

                <dl class="admin-doc-meta">
                  <div>
                    <dt>切片数</dt>
                    <dd>{{ doc.chunkCount }}</dd>
                  </div>
                  <div>
                    <dt>存储路径</dt>
                    <dd>{{ doc.storedPath }}</dd>
                  </div>
                </dl>

                <p v-if="doc.errorMessage" class="admin-inline-error">{{ doc.errorMessage }}</p>
              </article>
            </div>
          </section>
        </div>

        <div v-else-if="activePage === 'knowledge-gaps'" class="admin-page-stack">
          <section class="admin-overview-stats">
            <article class="admin-stat-card">
              <span>问题条目</span>
              <strong>{{ knowledgeGapSummary?.totalQuestions ?? 0 }}</strong>
              <p>当前知识缺口去重后的问题数量。</p>
            </article>
            <article class="admin-stat-card">
              <span>累计命中</span>
              <strong>{{ knowledgeGapSummary?.totalOccurrences ?? 0 }}</strong>
              <p>所有缺口问题在真实会话中累计出现次数。</p>
            </article>
            <article class="admin-stat-card">
              <span>当前主状态</span>
              <strong>{{ knowledgeGapTopStatus ? knowledgeGapStatusLabel(knowledgeGapTopStatus.status) : '待统计' }}</strong>
              <p>
                {{
                  knowledgeGapTopStatus
                    ? `${knowledgeGapTopStatus.count} 条处于该状态`
                    : '进入页面后会自动拉取状态分布。'
                }}
              </p>
            </article>
          </section>

          <section class="admin-panel">
            <div class="admin-panel-header">
              <div>
                <p class="admin-section-tag">Knowledge Gap Summary</p>
                <h3>热点问题与处理概览</h3>
              </div>
              <button
                class="admin-secondary-button"
                type="button"
                :disabled="loading.knowledgeGapReload"
                @click="loadKnowledgeGapWorkspace({ preserveSelection: true })"
              >
                {{ loading.knowledgeGapReload ? '刷新中..' : '刷新缺口数据' }}
              </button>
            </div>

            <div class="admin-gap-summary-grid">
              <div class="admin-overview-list">
                <h4>状态分布</h4>
                <div v-if="knowledgeGapSummary?.statusCounts?.length" class="admin-chip-row admin-chip-row-wrap">
                  <button
                    v-for="item in knowledgeGapSummary?.statusCounts"
                    :key="item.status"
                    class="admin-filter-chip"
                    :data-active="knowledgeGapFilters.status === item.status"
                    type="button"
                    @click="knowledgeGapFilters.status = knowledgeGapFilters.status === item.status ? '' : item.status"
                  >
                    {{ knowledgeGapStatusLabel(item.status) }} · {{ item.count }}
                  </button>
                </div>
                <p v-else class="admin-empty-hint">暂无状态统计。</p>
              </div>

              <div class="admin-overview-list">
                <h4>热点 Highlights</h4>
                <div v-if="knowledgeGapSummary?.highlights?.length" class="admin-gap-highlight-list">
                  <button
                    v-for="highlight in knowledgeGapSummary?.highlights"
                    :key="highlight.id"
                    class="admin-gap-highlight-card"
                    type="button"
                    @click="openKnowledgeGap(highlight.id)"
                  >
                    <div class="admin-gap-highlight-header">
                      <strong>{{ highlight.representativeQuestion }}</strong>
                      <span class="admin-badge" :data-status="normalizeKnowledgeGapStatus(highlight.status)">
                        {{ knowledgeGapStatusLabel(highlight.status) }}
                      </span>
                    </div>
                    <p>{{ highlight.occurrenceCount }} 次命中 · 最近出现 {{ formatDateTime(highlight.lastSeenAt) }}</p>
                  </button>
                </div>
                <p v-else class="admin-empty-hint">暂无热点问题。</p>
              </div>
            </div>
          </section>

          <div class="admin-grid admin-grid-knowledge-gaps">
            <section class="admin-panel">
              <div class="admin-panel-header">
                <div>
                  <p class="admin-section-tag">Gap List</p>
                  <h3>问题列表</h3>
                </div>
                <span class="admin-badge">{{ knowledgeGapTotal }} 条</span>
              </div>

              <form class="admin-gap-filter-grid" @submit.prevent="applyKnowledgeGapFilters">
                <label class="admin-field">
                  <span>状态筛选</span>
                  <select v-model="knowledgeGapFilters.status">
                    <option value="">全部状态</option>
                    <option v-for="status in knowledgeGapStatusOptions" :key="status" :value="status">
                      {{ knowledgeGapStatusLabel(status) }}
                    </option>
                  </select>
                </label>

                <label class="admin-field admin-gap-search-field">
                  <span>关键词搜索</span>
                  <input
                    v-model.trim="knowledgeGapSearchInput"
                    type="text"
                    placeholder="搜索代表问题、用户原问或归一化问法"
                  />
                </label>

                <button class="admin-secondary-button admin-align-end" type="submit">
                  应用筛选
                </button>
                <button class="admin-ghost-button admin-align-end" type="button" @click="clearKnowledgeGapFilters">
                  清空
                </button>
              </form>

              <div class="admin-gap-list">
                <p v-if="loading.knowledgeGapReload && !knowledgeGapList.length" class="admin-empty-hint">
                  正在加载知识缺口列表...
                </p>

                <button
                  v-for="item in knowledgeGapList"
                  :key="item.id"
                  class="admin-gap-card"
                  :data-active="item.id === selectedKnowledgeGapId"
                  type="button"
                  @click="openKnowledgeGap(item.id)"
                >
                  <div class="admin-gap-card-header">
                    <strong>{{ item.representativeQuestion }}</strong>
                    <span class="admin-badge" :data-status="normalizeKnowledgeGapStatus(item.status)">
                      {{ knowledgeGapStatusLabel(item.status) }}
                    </span>
                  </div>
                  <p>{{ item.lastUserQuestion || item.normalizedQuestion || '暂无额外问题文本' }}</p>
                  <div class="admin-chip-row admin-chip-row-wrap">
                    <span class="admin-badge admin-badge-accent">{{ item.occurrenceCount }} 次命中</span>
                    <span class="admin-badge">{{ item.sourceCount }} 个来源片段</span>
                    <span v-if="item.adminAnswer" class="admin-badge">已写草稿</span>
                    <span v-if="item.importedAt" class="admin-badge">已导入</span>
                  </div>
                  <div class="admin-gap-card-meta">
                    <span>最近出现 {{ formatDateTime(item.lastSeenAt) }}</span>
                    <span>{{ item.sampleQuestions.length }} 条样例问法</span>
                  </div>
                </button>

                <p v-if="!knowledgeGapList.length && !loading.knowledgeGapReload" class="admin-empty-hint">
                  当前筛选下没有知识缺口。
                </p>
              </div>

              <div class="admin-gap-pagination">
                <p class="admin-empty-hint">
                  {{
                    knowledgeGapTotal
                      ? `第 ${knowledgeGapRangeStart}-${knowledgeGapRangeEnd} 条，共 ${knowledgeGapTotal} 条`
                      : '暂无分页数据'
                  }}
                </p>
                <div class="admin-inline-actions">
                  <button
                    class="admin-ghost-button"
                    type="button"
                    :disabled="knowledgeGapFilters.page <= 1 || loading.knowledgeGapReload"
                    @click="changeKnowledgeGapPage(knowledgeGapFilters.page - 1)"
                  >
                    上一页
                  </button>
                  <span class="admin-badge">第 {{ knowledgeGapFilters.page }} / {{ knowledgeGapTotalPages }} 页</span>
                  <button
                    class="admin-ghost-button"
                    type="button"
                    :disabled="knowledgeGapFilters.page >= knowledgeGapTotalPages || loading.knowledgeGapReload"
                    @click="changeKnowledgeGapPage(knowledgeGapFilters.page + 1)"
                  >
                    下一页
                  </button>
                </div>
              </div>
            </section>

            <section class="admin-panel admin-gap-detail-panel">
              <div class="admin-panel-header">
                <div>
                  <p class="admin-section-tag">Gap Detail</p>
                  <h3>{{ selectedKnowledgeGap?.representativeQuestion || '知识缺口详情' }}</h3>
                </div>
                <div class="admin-inline-actions">
                  <button
                    class="admin-secondary-button"
                    type="button"
                    :disabled="!selectedKnowledgeGap || !knowledgeGapEditorDirty || loading.knowledgeGapSave || loading.knowledgeGapImport || loading.knowledgeGapDetail"
                    @click="handleKnowledgeGapSave"
                  >
                    {{ loading.knowledgeGapSave ? '保存中..' : '保存草稿' }}
                  </button>
                  <button
                    class="admin-primary-button"
                    type="button"
                    :disabled="!selectedKnowledgeGap || !knowledgeGapEditor.adminAnswer.trim() || loading.knowledgeGapImport || loading.knowledgeGapSave || loading.knowledgeGapDetail"
                    @click="handleKnowledgeGapImport"
                  >
                    {{ loading.knowledgeGapImport ? '导入中..' : '导入知识库' }}
                  </button>
                </div>
              </div>

              <template v-if="selectedKnowledgeGap">
                <p
                  v-if="!selectedKnowledgeGapInList && (knowledgeGapFilters.status || knowledgeGapFilters.search)"
                  class="admin-empty-hint"
                >
                  当前详情不在左侧筛选结果内，可能已被状态或关键词过滤隐藏。
                </p>

                <dl class="admin-doc-meta admin-gap-meta-grid">
                  <div>
                    <dt>归一化问法</dt>
                    <dd>{{ selectedKnowledgeGap.normalizedQuestion || '未记录' }}</dd>
                  </div>
                  <div>
                    <dt>命中次数</dt>
                    <dd>{{ selectedKnowledgeGap.occurrenceCount }}</dd>
                  </div>
                  <div>
                    <dt>首次出现</dt>
                    <dd>{{ formatDateTime(selectedKnowledgeGap.firstSeenAt) }}</dd>
                  </div>
                  <div>
                    <dt>最近出现</dt>
                    <dd>{{ formatDateTime(selectedKnowledgeGap.lastSeenAt) }}</dd>
                  </div>
                  <div>
                    <dt>来源片段数</dt>
                    <dd>{{ selectedKnowledgeGap.sourceCount }}</dd>
                  </div>
                  <div>
                    <dt>最近置信度</dt>
                    <dd>
                      {{
                        typeof selectedKnowledgeGap.lastConfidence === 'number'
                          ? selectedKnowledgeGap.lastConfidence.toFixed(3)
                          : '未记录'
                      }}
                    </dd>
                  </div>
                  <div>
                    <dt>最近会话</dt>
                    <dd>{{ selectedKnowledgeGap.lastSessionId || '未记录' }}</dd>
                  </div>
                  <div>
                    <dt>导入结果</dt>
                    <dd>
                      {{
                        selectedKnowledgeGap.knowledgeDocFilename
                          ? `${selectedKnowledgeGap.knowledgeDocFilename} · ${formatDateTime(selectedKnowledgeGap.importedAt || '')}`
                          : '尚未导入'
                      }}
                    </dd>
                  </div>
                </dl>

                <p v-if="selectedKnowledgeGap.lastConfidenceNote" class="admin-inline-hint">
                  置信度备注：{{ selectedKnowledgeGap.lastConfidenceNote }}
                </p>

                <div class="admin-gap-editor-grid">
                  <label class="admin-field">
                    <span>处理状态</span>
                    <select v-model="knowledgeGapEditor.status">
                      <option v-for="status in knowledgeGapStatusOptions" :key="status" :value="status">
                        {{ knowledgeGapStatusLabel(status) }}
                      </option>
                    </select>
                  </label>

                  <label class="admin-field">
                    <span>导入文件名前缀</span>
                    <input v-model.trim="knowledgeGapEditor.filenamePrefix" type="text" placeholder="可选，如 scenic-faq" />
                  </label>

                  <label class="admin-field">
                    <span>整理标题</span>
                    <input v-model="knowledgeGapEditor.adminTitle" type="text" placeholder="用于沉淀进知识库的标题" />
                  </label>

                  <label class="admin-field">
                    <span>知识分类</span>
                    <input v-model="knowledgeGapEditor.adminCategory" type="text" placeholder="如 faq / ticket / parking" />
                  </label>

                  <label class="admin-field admin-gap-editor-span">
                    <span>标准答案</span>
                    <textarea
                      v-model="knowledgeGapEditor.adminAnswer"
                      rows="9"
                      placeholder="在这里整理成最终可导入知识库的标准回答"
                    />
                  </label>

                  <label class="admin-field admin-gap-editor-span">
                    <span>管理员备注</span>
                    <textarea
                      v-model="knowledgeGapEditor.adminNotes"
                      rows="4"
                      placeholder="记录处理思路、来源确认结果或待补充事项"
                    />
                  </label>
                </div>

                <div class="admin-gap-action-bar">
                  <p class="admin-inline-hint">
                    {{ knowledgeGapEditorDirty ? '当前有未保存修改。' : '草稿内容已与当前详情同步。' }}
                  </p>
                  <div class="admin-chip-row admin-chip-row-wrap">
                    <span class="admin-badge" :data-status="normalizeKnowledgeGapStatus(selectedKnowledgeGap.status)">
                      {{ knowledgeGapStatusLabel(selectedKnowledgeGap.status) }}
                    </span>
                    <span v-if="selectedKnowledgeGap.importedAt" class="admin-badge">已导入 {{ formatDateTime(selectedKnowledgeGap.importedAt) }}</span>
                    <span v-if="selectedKnowledgeGap.lastReplyKind" class="admin-badge">回复类型 {{ selectedKnowledgeGap.lastReplyKind }}</span>
                  </div>
                </div>

                <div class="admin-overview-list">
                  <h4>样例问法</h4>
                  <div v-if="selectedKnowledgeGap.sampleQuestions.length" class="admin-chip-row admin-chip-row-wrap">
                    <span
                      v-for="question in selectedKnowledgeGap.sampleQuestions"
                      :key="`${selectedKnowledgeGap.id}-${question}`"
                      class="admin-badge admin-badge-question"
                    >
                      {{ question }}
                    </span>
                  </div>
                  <p v-else class="admin-empty-hint">暂无样例问法。</p>
                </div>

                <div class="admin-gap-context-grid">
                  <article class="admin-gap-context-card">
                    <span>最近用户问题</span>
                    <p class="admin-message-content">{{ selectedKnowledgeGap.lastUserQuestion || '未记录' }}</p>
                  </article>
                  <article class="admin-gap-context-card">
                    <span>最近检索查询</span>
                    <p class="admin-message-content">{{ selectedKnowledgeGap.lastQueryText || '未记录' }}</p>
                  </article>
                  <article class="admin-gap-context-card">
                    <span>最近助手回复</span>
                    <p class="admin-message-content">{{ selectedKnowledgeGap.lastAssistantReply || '未记录' }}</p>
                  </article>
                </div>

                <div class="admin-overview-list">
                  <h4>检索快照</h4>
                  <div v-if="selectedKnowledgeGap.sourceSnapshot.length" class="admin-gap-source-list">
                    <article
                      v-for="source in selectedKnowledgeGap.sourceSnapshot"
                      :key="`${selectedKnowledgeGap.id}-${source.filename}-${source.chunkIndex ?? 'na'}`"
                      class="admin-gap-source-card"
                    >
                      <div class="admin-gap-source-header">
                        <strong>{{ source.title || source.filename }}</strong>
                        <span class="admin-badge">{{ source.category || '未分类' }}</span>
                      </div>
                      <p class="admin-gap-source-meta">
                        {{ source.filename }} · chunk {{ source.chunkIndex ?? '--' }}
                      </p>
                      <p class="admin-message-content">{{ source.excerpt || '暂无摘录' }}</p>
                      <div class="admin-chip-row admin-chip-row-wrap">
                        <span class="admin-badge">
                          召回 {{ typeof source.retrievalScore === 'number' ? source.retrievalScore.toFixed(3) : '--' }}
                        </span>
                        <span class="admin-badge">
                          重排 {{ typeof source.rerankScore === 'number' ? source.rerankScore.toFixed(3) : '--' }}
                        </span>
                      </div>
                    </article>
                  </div>
                  <p v-else class="admin-empty-hint">暂无检索快照。</p>
                </div>

                <p v-if="selectedKnowledgeGap.lastErrorMessage" class="admin-inline-error">
                  {{ selectedKnowledgeGap.lastErrorMessage }}
                </p>
              </template>

              <p v-else-if="loading.knowledgeGapDetail" class="admin-empty-hint">正在加载知识缺口详情...</p>
              <p v-else class="admin-empty-hint">请先从左侧选择一个问题。</p>
            </section>
          </div>
        </div>

        <div v-else-if="activePage === 'sessions'" class="admin-page-stack">
          <section class="admin-overview-stats">
            <article class="admin-stat-card">
              <span>已加载会话</span>
              <strong>{{ adminSessions.length }}</strong>
              <p>后台当前最多拉取最近 80 个会话用于巡检。</p>
            </article>
            <article class="admin-stat-card">
              <span>消息总数</span>
              <strong>{{ totalSessionMessageCount }}</strong>
              <p>列表内所有会话累计消息数。</p>
            </article>
            <article class="admin-stat-card">
              <span>当前选中</span>
              <strong>{{ selectedSessionDetail?.messageCount ?? 0 }}</strong>
              <p>{{ selectedSessionSummary ? selectedSessionSummary.sessionId : '尚未选中会话' }}</p>
            </article>
          </section>

          <div class="admin-grid admin-grid-sessions">
            <section class="admin-panel">
              <div class="admin-panel-header">
                <div>
                  <p class="admin-section-tag">Session List</p>
                  <h3>会话列表</h3>
                </div>
                <button class="admin-secondary-button" type="button" :disabled="loading.sessionReload" @click="loadAdminSessionsData({ preserveSelection: true })">
                  {{ loading.sessionReload ? '刷新中...' : '刷新会话列表' }}
                </button>
              </div>

              <label class="admin-field">
                <span>筛选</span>
                <input
                  v-model.trim="sessionSearch"
                  type="text"
                  placeholder="按 session id、设备类型、标签或预览文本搜索"
                />
              </label>

              <div class="admin-session-list">
                <button
                  v-for="item in filteredAdminSessions"
                  :key="item.sessionId"
                  class="admin-session-card"
                  :data-active="item.sessionId === selectedSessionId"
                  type="button"
                  @click="openAdminSession(item.sessionId)"
                >
                  <div class="admin-session-card-header">
                    <strong>{{ item.sessionId }}</strong>
                    <span>{{ formatDateTime(item.updatedAt) }}</span>
                  </div>
                  <p>{{ item.lastMessagePreview || '该会话还没有消息。' }}</p>
                  <div class="admin-chip-row admin-chip-row-wrap">
                    <span class="admin-badge">{{ item.deviceType }}</span>
                    <span class="admin-badge">{{ item.messageCount }} 条消息</span>
                    <span v-for="tag in item.interestTags" :key="`${item.sessionId}-${tag}`" class="admin-badge">
                      {{ tag }}
                    </span>
                  </div>
                </button>

                <p v-if="!filteredAdminSessions.length" class="admin-empty-hint">
                  当前没有匹配的会话记录。
                </p>
              </div>
            </section>

            <section class="admin-panel">
              <div class="admin-panel-header">
                <div>
                  <p class="admin-section-tag">Message Timeline</p>
                  <h3>消息时间线</h3>
                </div>
                <span v-if="selectedSessionSummary" class="admin-badge">{{ selectedSessionSummary.deviceType }}</span>
              </div>

              <template v-if="selectedSessionDetail">
                <dl class="admin-doc-meta">
                  <div>
                    <dt>Session ID</dt>
                    <dd>{{ selectedSessionDetail.sessionId }}</dd>
                  </div>
                  <div>
                    <dt>创建时间</dt>
                    <dd>{{ formatDateTime(selectedSessionDetail.createdAt) }}</dd>
                  </div>
                  <div>
                    <dt>最后活跃</dt>
                    <dd>{{ formatDateTime(selectedSessionDetail.updatedAt) }}</dd>
                  </div>
                  <div>
                    <dt>兴趣标签</dt>
                    <dd>{{ selectedSessionDetail.interestTags.join(' / ') || '未设置' }}</dd>
                  </div>
                </dl>

                <section class="admin-form-section admin-session-trace-panel">
                  <div class="admin-panel-header">
                    <div>
                      <p class="admin-section-tag">Reply Trace Diagnostics</p>
                      <h4>回复链路诊断</h4>
                    </div>
                    <span class="admin-badge">{{ selectedSessionReplyTraceSummary?.traceCount ?? 0 }} 条</span>
                  </div>

                  <div class="admin-overview-stats admin-trace-summary-grid">
                    <article v-for="item in sessionTraceOverviewCards" :key="item.label" class="admin-stat-card admin-stat-card-compact">
                      <span>{{ item.label }}</span>
                      <strong>{{ item.value }}</strong>
                      <p>{{ item.detail }}</p>
                    </article>
                  </div>

                  <div v-if="selectedSessionReplyTraces.length" class="admin-trace-list">
                    <article v-for="trace in selectedSessionReplyTraces" :key="trace.replyId" class="admin-trace-card">
                      <div class="admin-trace-card-header">
                        <div class="admin-trace-card-title">
                          <strong>{{ shortTraceReplyId(trace.replyId) }}</strong>
                          <span>{{ formatDateTime(trace.createdAt) }}</span>
                        </div>
                        <div class="admin-chip-row admin-chip-row-wrap">
                          <span v-for="badge in traceRuntimeBadges(trace)" :key="`${trace.replyId}-${badge}`" class="admin-badge">
                            {{ badge }}
                          </span>
                        </div>
                      </div>

                      <dl class="admin-trace-meta-grid">
                        <div>
                          <dt>音频块</dt>
                          <dd>{{ trace.audioChunkCount }}</dd>
                        </div>
                        <div>
                          <dt>文本段</dt>
                          <dd>{{ trace.segmentCount }}</dd>
                        </div>
                        <div>
                          <dt>最大块间隔</dt>
                          <dd>{{ formatLatency(trace.maxChunkGapMs) }}</dd>
                        </div>
                        <div>
                          <dt>TTS 引擎</dt>
                          <dd>{{ trace.ttsEngine }}{{ trace.ttsStreamProfile ? ` / ${trace.ttsStreamProfile}` : '' }}</dd>
                        </div>
                      </dl>

                      <div class="admin-trace-metric-grid">
                        <div
                          v-for="metric in sessionTraceMetricEntries(trace)"
                          :key="`${trace.replyId}-${metric.key}`"
                          class="admin-trace-metric-item"
                        >
                          <span>{{ metric.label }}</span>
                          <strong>{{ formatLatency(metric.value) }}</strong>
                        </div>
                      </div>

                      <div v-if="sessionTraceChunkMetrics(trace).length" class="admin-trace-chunk-panel">
                        <div class="admin-trace-chunk-header">
                          <strong>Chunk 级诊断</strong>
                          <span>优先看 `token_wait_ms`、`token2wav_ms`、`chunk_supply_lag_ms` 和真实 RTF</span>
                        </div>
                        <div class="admin-trace-chunk-table-wrap">
                          <table class="admin-trace-chunk-table">
                            <thead>
                              <tr>
                                <th>seq/chunk</th>
                                <th>offset</th>
                                <th>wait</th>
                                <th>token2wav</th>
                                <th>audio</th>
                                <th>supply lag</th>
                                <th>real RTF</th>
                                <th>ready ratio</th>
                              </tr>
                            </thead>
                            <tbody>
                              <tr
                                v-for="chunk in sessionTraceChunkMetrics(trace)"
                                :key="`${trace.replyId}-${chunk.seq}-${chunk.chunkIndex}`"
                                :data-final="chunk.isFinal"
                              >
                                <td>{{ chunk.seq }} / {{ chunk.chunkIndex }}{{ chunk.isFinal ? ' final' : '' }}</td>
                                <td>{{ chunk.tokenOffset }}</td>
                                <td>{{ formatLatency(chunk.tokenWaitMs) }}</td>
                                <td>{{ formatLatency(chunk.token2wavMs) }}</td>
                                <td>{{ formatLatency(chunk.audioMs) }}</td>
                                <td>{{ formatLatency(chunk.supplyLagMs) }}</td>
                                <td>{{ formatRatio(chunk.realRtf) }}</td>
                                <td>{{ formatRatio(chunk.readyRatio) }}</td>
                              </tr>
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </article>
                  </div>
                  <p v-else class="admin-empty-hint">
                    当前会话还没有记录到 reply trace，通常是旧会话，或者当时后端尚未开启链路诊断日志。
                  </p>
                </section>

                <div class="admin-message-list">
                  <article
                    v-for="message in selectedSessionDetail.items"
                    :key="message.id"
                    class="admin-message-card"
                    :data-role="message.role"
                  >
                    <div class="admin-message-card-header">
                      <div class="admin-chip-row">
                        <span class="admin-badge" :data-role="message.role">
                          {{ message.role === 'assistant' ? '助手' : message.role === 'user' ? '游客' : message.role }}
                        </span>
                        <span v-if="message.emotion" class="admin-badge admin-badge-accent">
                          情绪 {{ message.emotion }}
                        </span>
                        <span v-if="message.latencyMs !== null" class="admin-badge">
                          {{ formatLatency(message.latencyMs) }}
                        </span>
                      </div>
                      <span>{{ formatDateTime(message.createdAt) }}</span>
                    </div>
                    <p class="admin-message-content">{{ message.content }}</p>
                  </article>
                </div>
              </template>

              <p v-else-if="loading.sessionDetail" class="admin-empty-hint">正在加载会话详情...</p>
              <p v-else class="admin-empty-hint">请先从左侧选择一个会话。</p>
            </section>
          </div>
        </div>

        <div v-else-if="activePage === 'reports'" class="admin-page-stack">
          <section class="admin-panel">
            <div class="admin-panel-header">
              <div>
                <p class="admin-section-tag">Phase 4 感受度报告</p>
                <h3>日报生成与体验感知汇总</h3>
              </div>
              <button class="admin-secondary-button" type="button" :disabled="loading.reportReload" @click="loadReportsData">
                {{ loading.reportReload ? '刷新中...' : '刷新报告数据' }}
              </button>
            </div>

            <div class="admin-report-toolbar">
              <div class="admin-report-filter-grid">
                <label class="admin-field">
                  <span>汇总开始日期</span>
                  <input v-model="reportFilters.dateFrom" type="date" />
                </label>
                <label class="admin-field">
                  <span>汇总结束日期</span>
                  <input v-model="reportFilters.dateTo" type="date" />
                </label>
                <button class="admin-secondary-button admin-align-end" type="button" @click="loadReportsData">
                  应用时间范围
                </button>
              </div>

              <div class="admin-report-generate-grid">
                <label class="admin-field">
                  <span>生成日报日期</span>
                  <input v-model="reportFilters.generateDate" type="date" />
                </label>
                <label class="admin-field admin-checkbox-field">
                  <span>强制重算</span>
                  <input v-model="reportFilters.forceRegenerate" type="checkbox" />
                </label>
                <button class="admin-primary-button admin-align-end" type="button" :disabled="loading.reportGenerate" @click="handleGenerateReport">
                  {{ loading.reportGenerate ? '生成中...' : '生成日报' }}
                </button>
              </div>
            </div>
          </section>

          <section class="admin-overview-stats">
            <article class="admin-stat-card">
              <span>覆盖日报</span>
              <strong>{{ reportSummary?.reportCount ?? 0 }}</strong>
              <p>统计区间 {{ reportSummary?.dateFrom ?? reportFilters.dateFrom }} 至 {{ reportSummary?.dateTo ?? reportFilters.dateTo }}</p>
            </article>
            <article class="admin-stat-card">
              <span>累计会话 / 消息</span>
              <strong>{{ reportSummary?.sessionCount ?? 0 }} / {{ reportSummary?.messageCount ?? 0 }}</strong>
              <p>游客消息 {{ reportSummary?.userMessageCount ?? 0 }}，助手消息 {{ reportSummary?.assistantMessageCount ?? 0 }}</p>
            </article>
            <article class="admin-stat-card">
              <span>平均响应耗时</span>
              <strong>{{ formatLatency(reportSummary?.avgAssistantLatencyMs) }}</strong>
              <p>整体情绪倾向：{{ sentimentLabel(reportSummary?.overallSentiment || 'neutral') }}</p>
            </article>
          </section>

          <div class="admin-grid admin-grid-reports">
            <section class="admin-panel">
              <div class="admin-panel-header">
                <div>
                  <p class="admin-section-tag">汇总摘要</p>
                  <h3>当前时间范围观察</h3>
                </div>
                <span class="admin-badge">{{ sentimentLabel(reportSummary?.overallSentiment || 'neutral') }}</span>
              </div>

              <p class="admin-report-summary-text">{{ reportSummary?.summaryText || '当前还没有可展示的感受度摘要。' }}</p>

              <div class="admin-report-trend-grid">
                <div class="admin-overview-list">
                  <h4>情绪趋势</h4>
                  <div class="admin-line-chart admin-line-chart-warm admin-report-line-chart" :data-empty="reportSentimentLinePoints ? 'false' : 'true'">
                    <svg viewBox="0 0 100 52" preserveAspectRatio="none" aria-hidden="true">
                      <line x1="0" y1="8" x2="100" y2="8" />
                      <line x1="0" y1="27" x2="100" y2="27" />
                      <line x1="0" y1="46" x2="100" y2="46" />
                      <polyline v-if="reportSentimentLinePoints" class="admin-line-chart-path" :points="reportSentimentLinePoints" />
                    </svg>
                    <div v-if="reportSentimentChartNodes.length" class="admin-line-chart-node-layer">
                      <button
                        v-for="node in reportSentimentChartNodes"
                        :key="node.key"
                        class="admin-line-chart-node"
                        type="button"
                        :style="{ left: `${node.x}%`, top: `${node.y}%` }"
                        :aria-label="node.ariaLabel"
                        :title="node.ariaLabel"
                      >
                        <span class="admin-line-chart-dot"></span>
                        <span class="admin-line-chart-tooltip">{{ node.label }}：{{ node.valueLabel }}</span>
                      </button>
                    </div>
                    <p v-if="!reportSentimentLinePoints" class="admin-empty-hint">暂无情绪趋势数据。</p>
                  </div>
                  <div class="admin-line-chart-axis">
                    <span
                      v-for="(report, index) in sortedDailyReports"
                      :key="report.reportDate"
                      :data-visible="shouldShowTrendLabel(index, sortedDailyReports.length)"
                    >
                      {{ report.reportDate.slice(5) }}
                    </span>
                  </div>
                </div>

                <div class="admin-overview-list">
                  <h4>关注点概览</h4>
                  <p v-if="!(reportSummary?.topKeywords?.length)" class="admin-empty-hint">暂无关注词。</p>
                  <div class="admin-chip-row admin-chip-row-wrap" v-else>
                    <span v-for="item in reportSummary?.topKeywords" :key="item" class="admin-badge">{{ item }}</span>
                  </div>
                </div>
              </div>

              <div class="admin-overview-list-grid">
                <div class="admin-overview-list">
                  <h4>高频兴趣标签</h4>
                  <p v-if="!(reportSummary?.topInterestTags?.length)" class="admin-empty-hint">暂无数据。</p>
                  <div class="admin-chip-row admin-chip-row-wrap" v-else>
                    <span v-for="item in reportSummary?.topInterestTags" :key="item" class="admin-badge">{{ item }}</span>
                  </div>
                </div>

                <div class="admin-overview-list">
                  <h4>高频关注点</h4>
                  <p v-if="!(reportSummary?.topKeywords?.length)" class="admin-empty-hint">暂无数据。</p>
                  <div class="admin-chip-row admin-chip-row-wrap" v-else>
                    <span v-for="item in reportSummary?.topKeywords" :key="item" class="admin-badge">{{ item }}</span>
                  </div>
                </div>
              </div>

              <div class="admin-overview-list">
                <h4>情绪统计</h4>
                <p v-if="!emotionSummaryEntries.length" class="admin-empty-hint">暂无情绪聚合数据。</p>
                <article v-for="[emotion, count] in emotionSummaryEntries" :key="emotion" class="admin-mini-card">
                  <strong>{{ emotion }}</strong>
                  <div class="admin-question-bar">
                    <i :style="{ width: reportEmotionBarWidth(count) }"></i>
                  </div>
                  <span>{{ count }} 次</span>
                </article>
              </div>
            </section>

            <section class="admin-panel">
              <div class="admin-panel-header">
                <div>
                  <p class="admin-section-tag">日报列表</p>
                  <h3>已生成的每日分析</h3>
                </div>
              </div>

              <div class="admin-list">
                <article v-for="report in sortedDailyReports" :key="report.reportDate" class="admin-list-card">
                  <div class="admin-list-card-header">
                    <div>
                      <h4>{{ report.reportDate }}</h4>
                      <p>{{ sentimentLabel(report.overallSentiment) }} · {{ report.source === 'llm' ? 'LLM 摘要' : '启发式摘要' }}</p>
                    </div>
                    <div class="admin-chip-row">
                      <span class="admin-badge">{{ report.status }}</span>
                      <span class="admin-badge">{{ formatLatency(report.avgAssistantLatencyMs) }}</span>
                    </div>
                  </div>

                  <p class="admin-report-summary-text">{{ report.summaryText }}</p>

                  <dl class="admin-doc-meta">
                    <div>
                      <dt>会话 / 消息</dt>
                      <dd>{{ report.sessionCount }} / {{ report.messageCount }}</dd>
                    </div>
                    <div>
                      <dt>兴趣标签</dt>
                      <dd>{{ report.topInterestTags.join('、') || '暂无' }}</dd>
                    </div>
                    <div>
                      <dt>关注点</dt>
                      <dd>{{ report.topKeywords.join('、') || '暂无' }}</dd>
                    </div>
                    <div>
                      <dt>生成时间</dt>
                      <dd>{{ formatDateTime(report.generatedAt) }}</dd>
                    </div>
                  </dl>
                </article>

                <p v-if="!dailyReports.length" class="admin-empty-hint">当前时间范围内还没有日报，请先手动生成或等待定时任务补跑。</p>
              </div>
            </section>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>
