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
  fetchAdminSessionDetail,
  fetchAdminSessions,
  fetchAvatarConfig,
  fetchAvatarProfiles,
  fetchAvatarConfigByProfile,
  fetchDailyReports,
  fetchKnowledgeDocs,
  fetchLive2DModels,
  fetchReportSummary,
  fetchVoiceProfileAudioBlobUrl,
  fetchVoiceProfiles,
  generateDailyReport,
  getAdminApiBaseUrl,
  loginAdmin,
  updateAvatarConfig,
  uploadKnowledgeDoc,
  uploadVoiceProfile,
} from './services/adminApi'
import type {
  AdminSessionDetail,
  AdminSessionSummary,
  AvatarConfig,
  AvatarProfileSummary,
  AvatarConfigUpdate,
  DailyEmotionReport,
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

type AdminPageKey = 'overview' | 'avatar' | 'voices' | 'knowledge' | 'sessions' | 'reports'

interface AdminPageMeta {
  key: AdminPageKey
  label: string
  eyebrow: string
  title: string
  description: string
}

const API_BASE_URL = getAdminApiBaseUrl()
const TOKEN_STORAGE_KEY = 'ai-chat-live2d.admin.token'
const MODEL_FALLBACK = '/live2d/haru/haru_greeter_t03.model3.json'
const ADMIN_PAGES: AdminPageMeta[] = [
  {
    key: 'overview',
    label: '总览',
    eyebrow: 'Dashboard',
    title: '管理后台总览',
    description: '查看当前数字人配置、知识库状态和音色资源概况。',
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
    key: 'sessions',
    label: '会话记录',
    eyebrow: 'Sessions',
    title: '会话记录',
    description: '查看历史会话、消息时间线，以及每条回复的情绪和耗时元数据。',
  },
  {
    key: 'reports',
    label: '运营报告',
    eyebrow: 'Reports',
    title: '运营报告',
    description: '查看日报分析、时间范围汇总，并手动触发指定日期的分析生成。',
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
  avatarProfileCreate: false,
  avatarProfileDelete: false,
  avatarSave: false,
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

const sessionSearch = ref('')
const voiceUploadForm = reactive({
  name: '',
  referenceText: '',
  description: '',
})

function formatDateInput(value: Date) {
  return value.toISOString().slice(0, 10)
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

const modelOptions = ref<Live2DModelOption[]>([])
const avatarProfiles = ref<AvatarProfileSummary[]>([])
const knowledgeDocs = ref<KnowledgeDocItem[]>([])
const knowledgeTotal = ref(0)
const adminSessions = ref<AdminSessionSummary[]>([])
const selectedSessionId = ref('')
const selectedSessionDetail = ref<AdminSessionDetail | null>(null)
const dailyReports = ref<DailyEmotionReport[]>([])
const reportSummary = ref<ReportRangeSummary | null>(null)
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
const voiceProfileCount = computed(() => voiceProfiles.value.length)
const recentKnowledgeDocs = computed(() => knowledgeDocs.value.slice(0, 3))
const recentVoiceProfiles = computed(() => voiceProfiles.value.slice(0, 3))
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
const totalSessionMessageCount = computed(() =>
  adminSessions.value.reduce((sum, item) => sum + item.messageCount, 0),
)
const activePageMeta = computed(
  () => ADMIN_PAGES.find((item) => item.key === activePage.value) ?? ADMIN_PAGES[0],
)
const pageUpdatedText = computed(() => {
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

  if (page === 'voices') {
    await loadVoiceProfileList()
    return
  }

  if (page === 'avatar') {
    await loadDashboardData()
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
  knowledgeDocs.value = []
  knowledgeTotal.value = 0
  adminSessions.value = []
  selectedSessionId.value = ''
  selectedSessionDetail.value = null
  voiceProfiles.value = []
  dailyReports.value = []
  reportSummary.value = null
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
    handleAdminError(error, '加载运营报告失败。')
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
          <p class="admin-eyebrow">Phase 3</p>
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
                <button class="admin-quick-card" type="button" @click="navigateToPage('sessions')">
                  <strong>会话记录</strong>
                  <span>查看真实 messages 时间线、情绪标签和回复耗时。</span>
                </button>
                <button class="admin-quick-card" type="button" @click="navigateToPage('reports')">
                  <strong>运营报告</strong>
                  <span>查看日报分析、时间范围汇总和响应延迟概况。</span>
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
                <p class="admin-section-tag">Phase 3 后端能力</p>
                <h3>日报生成与感受度汇总</h3>
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

              <p class="admin-report-summary-text">{{ reportSummary?.summaryText || '当前还没有可展示的运营摘要。' }}</p>

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
                <article v-for="report in dailyReports" :key="report.reportDate" class="admin-list-card">
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
