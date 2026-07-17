import type {
  AdminReplyTrace,
  AdminReplyTraceSummary,
  AdminSessionDetail,
  AdminSessionListResponse,
  AdminSessionMessage,
  AdminSessionSummary,
  AdminLoginResponse,
  AdminMe,
  AvatarConfig,
  AvatarProfileCreatePayload,
  AvatarProfileListResponse,
  AvatarProfileSummary,
  AvatarConfigUpdate,
  DashboardEmotionSummary,
  DashboardOverview,
  DailyEmotionReport,
  DailyEmotionReportListResponse,
  KnowledgeGapImportPayload,
  KnowledgeGapImportResult,
  KnowledgeGapItem,
  KnowledgeGapListResponse,
  KnowledgeGapSummary,
  KnowledgeGapUpdatePayload,
  KnowledgeDocListResponse,
  KnowledgeUploadResult,
  Live2DModelOption,
  MessageResponse,
  ReportRangeSummary,
  VoiceProfile,
  VoiceProfileUploadResult,
} from '../types/admin'
import { getRuntimeApiBaseUrl } from '../lib/runtimeBaseUrl'

interface AdminLoginResponseApi {
  access_token: string
  token_type: string
  expires_in: number
}

interface AdminMeApi {
  username: string
}

interface Live2DModelOptionApi {
  path: string
  label: string
}

interface Live2DModelListResponseApi {
  items: Live2DModelOptionApi[]
}

interface AvatarConfigApi {
  id: number
  name: string
  slug: string
  is_active: boolean
  model_path: string
  voice_id: string
  voice_profile_id: string | null
  response_language: 'zh' | 'en'
  persona: string
  tts_reference_audio_path: string
  tts_reference_text: string
  tts_speed: number
  tts_emotion_enabled: boolean
  display_scale: number
  display_offset_x: number
  display_offset_y: number
  stage_height: number
  created_at: string
  updated_at: string
}

interface AvatarProfileSummaryApi {
  id: number
  name: string
  slug: string
  is_active: boolean
  model_path: string
  voice_id: string
  response_language: 'zh' | 'en'
  display_scale: number
  display_offset_x: number
  display_offset_y: number
  stage_height: number
  updated_at: string
}

interface AvatarProfileListResponseApi {
  items: AvatarProfileSummaryApi[]
}

interface KnowledgeDocItemApi {
  id: string
  filename: string
  category: string
  stored_path: string
  chunk_count: number
  uploaded_at: string
  status: string
  error_message: string
}

interface KnowledgeDocListResponseApi {
  total: number
  items: KnowledgeDocItemApi[]
}

interface KnowledgeUploadResultApi {
  doc_id: string
  status: string
  message: string
}

interface KnowledgeGapSourceSnapshotItemApi {
  filename: string
  title: string | null
  category: string | null
  chunk_index: number | null
  retrieval_score: number | null
  rerank_score: number | null
  excerpt: string
}

interface KnowledgeGapItemApi {
  id: string
  normalized_question: string
  representative_question: string
  sample_questions: string[]
  occurrence_count: number
  status: string
  source_count: number
  source_snapshot: KnowledgeGapSourceSnapshotItemApi[]
  last_session_id: string | null
  last_user_question: string | null
  last_query_text: string | null
  last_assistant_reply: string | null
  last_reply_kind: string | null
  last_confidence_note: string | null
  last_confidence: number | null
  admin_title: string | null
  admin_category: string | null
  admin_answer: string | null
  admin_notes: string | null
  knowledge_doc_id: string | null
  knowledge_doc_filename: string | null
  last_error_message: string | null
  first_seen_at: string
  last_seen_at: string
  imported_at: string | null
  created_at: string
  updated_at: string
}

interface KnowledgeGapListResponseApi {
  total: number
  items: KnowledgeGapItemApi[]
}

interface KnowledgeGapSummaryStatusCountApi {
  status: string
  count: number
}

interface KnowledgeGapHighlightItemApi {
  id: string
  representative_question: string
  occurrence_count: number
  status: string
  last_seen_at: string
}

interface KnowledgeGapSummaryApi {
  total_questions: number
  total_occurrences: number
  status_counts: KnowledgeGapSummaryStatusCountApi[]
  highlights: KnowledgeGapHighlightItemApi[]
}

interface KnowledgeGapImportResultApi {
  item: KnowledgeGapItemApi
  message: string
}

interface VoiceProfileApi {
  id: string
  name: string
  description: string
  source_filename: string
  audio_path: string
  reference_text: string
  duration_ms: number
  mime_type: string
  is_default: boolean
  created_at: string
  updated_at: string
}

interface VoiceProfileListResponseApi {
  items: VoiceProfileApi[]
}

interface VoiceProfileUploadResultApi {
  item: VoiceProfileApi
  message: string
}

interface DailyEmotionReportApi {
  report_date: string
  status: string
  session_count: number
  message_count: number
  user_message_count: number
  assistant_message_count: number
  avg_assistant_latency_ms: number | null
  emotion_counts: Record<string, number>
  top_interest_tags: string[]
  top_keywords: string[]
  overall_sentiment: string
  summary_text: string
  source: string
  generated_at: string
  updated_at: string
}

interface DailyEmotionReportListResponseApi {
  items: DailyEmotionReportApi[]
}

interface ReportRangeSummaryApi {
  date_from: string
  date_to: string
  report_count: number
  session_count: number
  message_count: number
  user_message_count: number
  assistant_message_count: number
  avg_assistant_latency_ms: number | null
  emotion_counts: Record<string, number>
  top_interest_tags: string[]
  top_keywords: string[]
  overall_sentiment: string
  summary_text: string
}

interface DashboardQuestionItemApi {
  question: string
  count: number
}

interface DashboardSatisfactionTrendPointApi {
  date: string
  session_count: number
  message_count: number
  avg_latency_ms: number | null
  score: number | null
}

interface DashboardServiceTrendPointApi {
  date: string
  service_count: number
}

interface DashboardKeywordCloudItemApi {
  word: string
  count: number
  weight: number
  source: string
}

interface DashboardOverviewApi {
  period: string
  date_from: string
  date_to: string
  service_count: number
  session_count: number
  message_count: number
  user_message_count: number
  assistant_message_count: number
  realtime_online_count: number
  avg_satisfaction: number | null
  avg_latency_ms: number | null
  overall_sentiment: string
  top_questions: DashboardQuestionItemApi[]
  service_trend: DashboardServiceTrendPointApi[]
  satisfaction_trend: DashboardSatisfactionTrendPointApi[]
  top_interest_tags: string[]
  top_keywords: string[]
  keyword_cloud: DashboardKeywordCloudItemApi[]
  emotion_counts: Record<string, number>
  summary_text: string
}

interface DashboardEmotionPointApi {
  date: string
  happy: number
  neutral: number
  negative: number
  total: number
  score: number | null
}

interface DashboardEmotionSummaryApi {
  date_from: string
  date_to: string
  overall_sentiment: string
  emotion_counts: Record<string, number>
  trend: DashboardEmotionPointApi[]
  summary_text: string
}

interface AdminSessionSummaryApi {
  session_id: string
  created_at: string
  updated_at: string
  device_type: string
  interest_tags: string[]
  message_count: number
  last_message_preview: string
}

interface AdminSessionListResponseApi {
  items: AdminSessionSummaryApi[]
}

interface AdminSessionMessageApi {
  id: number
  role: string
  content: string
  created_at: string
  emotion: string | null
  latency_ms: number | null
}

interface AdminReplyTraceApi {
  reply_id: string
  created_at: string
  streaming: boolean
  chat_mode: string
  tts_engine: string
  tts_stream_profile: string | null
  prompt_cache_hit: boolean | null
  prompt_cache_build_ms: number | null
  torch_cuda_available: boolean | null
  torch_device_name: string | null
  requested_onnx_provider: string | null
  tts_cosyvoice_fp16: boolean | null
  tts_cosyvoice_load_jit: boolean | null
  tts_ar_backend: string | null
  tts_flow_backend: string | null
  audio_chunk_count: number
  segment_count: number
  max_chunk_gap_ms: number
  metrics: Record<string, number>
  tts_chunks: Record<string, number | string | boolean | null>[]
}

interface AdminReplyTraceSummaryApi {
  trace_count: number
  latest_created_at: string | null
  avg_metrics: Record<string, number>
  max_metrics: Record<string, number>
}

interface AdminSessionDetailApi {
  session_id: string
  created_at: string
  updated_at: string
  device_type: string
  interest_tags: string[]
  message_count: number
  items: AdminSessionMessageApi[]
  reply_traces: AdminReplyTraceApi[]
  reply_trace_summary: AdminReplyTraceSummaryApi
}

const API_BASE_URL = getRuntimeApiBaseUrl(import.meta.env)

function trimApiBaseUrl(apiBaseUrl: string) {
  return apiBaseUrl.replace(/\/+$/, '')
}

async function readErrorMessage(response: Response, fallback: string) {
  const contentType = response.headers.get('content-type') || ''

  if (contentType.includes('application/json')) {
    const payload = (await response.json()) as { detail?: string; message?: string }
    return payload.detail || payload.message || fallback
  }

  const text = await response.text()
  return text || fallback
}

async function readJson<T>(response: Response, fallback: string) {
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, fallback))
  }

  return (await response.json()) as T
}

function buildAuthHeaders(token: string, contentType = 'application/json') {
  return {
    Authorization: `Bearer ${token}`,
    ...(contentType ? { 'Content-Type': contentType } : {}),
  }
}

function mapAvatarConfig(payload: AvatarConfigApi): AvatarConfig {
  return {
    id: payload.id,
    name: payload.name,
    slug: payload.slug,
    isActive: payload.is_active,
    modelPath: payload.model_path,
    voiceId: payload.voice_id,
    voiceProfileId: payload.voice_profile_id,
    responseLanguage: payload.response_language,
    persona: payload.persona,
    ttsReferenceAudioPath: payload.tts_reference_audio_path,
    ttsReferenceText: payload.tts_reference_text,
    ttsSpeed: payload.tts_speed,
    ttsEmotionEnabled: payload.tts_emotion_enabled,
    displayScale: payload.display_scale,
    displayOffsetX: payload.display_offset_x,
    displayOffsetY: payload.display_offset_y,
    stageHeight: payload.stage_height,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at,
  }
}

function mapAvatarProfileSummary(payload: AvatarProfileSummaryApi): AvatarProfileSummary {
  return {
    id: payload.id,
    name: payload.name,
    slug: payload.slug,
    isActive: payload.is_active,
    modelPath: payload.model_path,
    voiceId: payload.voice_id,
    responseLanguage: payload.response_language,
    displayScale: payload.display_scale,
    displayOffsetX: payload.display_offset_x,
    displayOffsetY: payload.display_offset_y,
    stageHeight: payload.stage_height,
    updatedAt: payload.updated_at,
  }
}

function mapVoiceProfile(payload: VoiceProfileApi): VoiceProfile {
  return {
    id: payload.id,
    name: payload.name,
    description: payload.description,
    sourceFilename: payload.source_filename,
    audioPath: payload.audio_path,
    referenceText: payload.reference_text,
    durationMs: payload.duration_ms,
    mimeType: payload.mime_type,
    isDefault: payload.is_default,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at,
  }
}

function mapKnowledgeGapItem(payload: KnowledgeGapItemApi): KnowledgeGapItem {
  return {
    id: payload.id,
    normalizedQuestion: payload.normalized_question,
    representativeQuestion: payload.representative_question,
    sampleQuestions: payload.sample_questions || [],
    occurrenceCount: payload.occurrence_count,
    status: payload.status,
    sourceCount: payload.source_count,
    sourceSnapshot: (payload.source_snapshot || []).map((item) => ({
      filename: item.filename,
      title: item.title,
      category: item.category,
      chunkIndex: item.chunk_index,
      retrievalScore: item.retrieval_score,
      rerankScore: item.rerank_score,
      excerpt: item.excerpt,
    })),
    lastSessionId: payload.last_session_id,
    lastUserQuestion: payload.last_user_question,
    lastQueryText: payload.last_query_text,
    lastAssistantReply: payload.last_assistant_reply,
    lastReplyKind: payload.last_reply_kind,
    lastConfidenceNote: payload.last_confidence_note,
    lastConfidence: payload.last_confidence,
    adminTitle: payload.admin_title,
    adminCategory: payload.admin_category,
    adminAnswer: payload.admin_answer,
    adminNotes: payload.admin_notes,
    knowledgeDocId: payload.knowledge_doc_id,
    knowledgeDocFilename: payload.knowledge_doc_filename,
    lastErrorMessage: payload.last_error_message,
    firstSeenAt: payload.first_seen_at,
    lastSeenAt: payload.last_seen_at,
    importedAt: payload.imported_at,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at,
  }
}

function mapDailyEmotionReport(payload: DailyEmotionReportApi): DailyEmotionReport {
  return {
    reportDate: payload.report_date,
    status: payload.status,
    sessionCount: payload.session_count,
    messageCount: payload.message_count,
    userMessageCount: payload.user_message_count,
    assistantMessageCount: payload.assistant_message_count,
    avgAssistantLatencyMs: payload.avg_assistant_latency_ms,
    emotionCounts: payload.emotion_counts,
    topInterestTags: payload.top_interest_tags,
    topKeywords: payload.top_keywords,
    overallSentiment: payload.overall_sentiment,
    summaryText: payload.summary_text,
    source: payload.source,
    generatedAt: payload.generated_at,
    updatedAt: payload.updated_at,
  }
}

function mapAdminSessionSummary(payload: AdminSessionSummaryApi): AdminSessionSummary {
  return {
    sessionId: payload.session_id,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at,
    deviceType: payload.device_type,
    interestTags: payload.interest_tags,
    messageCount: payload.message_count,
    lastMessagePreview: payload.last_message_preview,
  }
}

function mapAdminSessionMessage(payload: AdminSessionMessageApi): AdminSessionMessage {
  return {
    id: payload.id,
    role: payload.role,
    content: payload.content,
    createdAt: payload.created_at,
    emotion: payload.emotion,
    latencyMs: payload.latency_ms,
  }
}

function mapAdminReplyTrace(payload: AdminReplyTraceApi): AdminReplyTrace {
  return {
    replyId: payload.reply_id,
    createdAt: payload.created_at,
    streaming: payload.streaming,
    chatMode: payload.chat_mode,
    ttsEngine: payload.tts_engine,
    ttsStreamProfile: payload.tts_stream_profile,
    promptCacheHit: payload.prompt_cache_hit,
    promptCacheBuildMs: payload.prompt_cache_build_ms,
    torchCudaAvailable: payload.torch_cuda_available,
    torchDeviceName: payload.torch_device_name,
    requestedOnnxProvider: payload.requested_onnx_provider,
    ttsCosyvoiceFp16: payload.tts_cosyvoice_fp16,
    ttsCosyvoiceLoadJit: payload.tts_cosyvoice_load_jit,
    ttsArBackend: payload.tts_ar_backend,
    ttsFlowBackend: payload.tts_flow_backend,
    audioChunkCount: payload.audio_chunk_count,
    segmentCount: payload.segment_count,
    maxChunkGapMs: payload.max_chunk_gap_ms,
    metrics: payload.metrics ?? {},
    ttsChunks: payload.tts_chunks ?? [],
  }
}

function mapAdminReplyTraceSummary(payload: AdminReplyTraceSummaryApi): AdminReplyTraceSummary {
  return {
    traceCount: payload.trace_count,
    latestCreatedAt: payload.latest_created_at,
    avgMetrics: payload.avg_metrics ?? {},
    maxMetrics: payload.max_metrics ?? {},
  }
}

function mapDashboardOverview(payload: DashboardOverviewApi): DashboardOverview {
  return {
    period: payload.period,
    dateFrom: payload.date_from,
    dateTo: payload.date_to,
    serviceCount: payload.service_count,
    sessionCount: payload.session_count,
    messageCount: payload.message_count,
    userMessageCount: payload.user_message_count,
    assistantMessageCount: payload.assistant_message_count,
    realtimeOnlineCount: payload.realtime_online_count,
    avgSatisfaction: payload.avg_satisfaction,
    avgLatencyMs: payload.avg_latency_ms,
    overallSentiment: payload.overall_sentiment,
    topQuestions: payload.top_questions.map((item) => ({
      question: item.question,
      count: item.count,
    })),
    serviceTrend: payload.service_trend.map((item) => ({
      date: item.date,
      serviceCount: item.service_count,
    })),
    satisfactionTrend: payload.satisfaction_trend.map((item) => ({
      date: item.date,
      sessionCount: item.session_count,
      messageCount: item.message_count,
      avgLatencyMs: item.avg_latency_ms,
      score: item.score,
    })),
    topInterestTags: payload.top_interest_tags,
    topKeywords: payload.top_keywords,
    keywordCloud: payload.keyword_cloud.map((item) => ({
      word: item.word,
      count: item.count,
      weight: item.weight,
      source: item.source,
    })),
    emotionCounts: payload.emotion_counts,
    summaryText: payload.summary_text,
  }
}

function mapDashboardEmotionSummary(payload: DashboardEmotionSummaryApi): DashboardEmotionSummary {
  return {
    dateFrom: payload.date_from,
    dateTo: payload.date_to,
    overallSentiment: payload.overall_sentiment,
    emotionCounts: payload.emotion_counts,
    trend: payload.trend.map((item) => ({
      date: item.date,
      happy: item.happy,
      neutral: item.neutral,
      negative: item.negative,
      total: item.total,
      score: item.score,
    })),
    summaryText: payload.summary_text,
  }
}

export function getAdminApiBaseUrl() {
  return API_BASE_URL
}

export async function loginAdmin(
  apiBaseUrl: string,
  username: string,
  password: string,
): Promise<AdminLoginResponse> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ username, password }),
  })
  const payload = await readJson<AdminLoginResponseApi>(response, '管理员登录失败。')

  return {
    accessToken: payload.access_token,
    tokenType: payload.token_type,
    expiresIn: payload.expires_in,
  }
}

export async function fetchAdminMe(apiBaseUrl: string, token: string): Promise<AdminMe> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/auth/me`, {
    headers: buildAuthHeaders(token, ''),
  })
  const payload = await readJson<AdminMeApi>(response, '管理员认证失败。')
  return {
    username: payload.username,
  }
}

export async function fetchLive2DModels(apiBaseUrl: string, token: string): Promise<Live2DModelOption[]> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/avatar/models`, {
    headers: buildAuthHeaders(token, ''),
  })
  const payload = await readJson<Live2DModelListResponseApi>(response, '加载 Live2D 模型列表失败。')
  return payload.items
}

export async function fetchAvatarConfig(apiBaseUrl: string, token: string): Promise<AvatarConfig> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/avatar/config`, {
    headers: buildAuthHeaders(token, ''),
  })
  const payload = await readJson<AvatarConfigApi>(response, '加载数字人配置失败。')
  return mapAvatarConfig(payload)
}

export async function fetchAvatarConfigByProfile(
  apiBaseUrl: string,
  token: string,
  profileId: number,
): Promise<AvatarConfig> {
  const query = new URLSearchParams()
  query.set('profile_id', String(profileId))
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/avatar/config?${query.toString()}`, {
    headers: buildAuthHeaders(token, ''),
  })
  const payload = await readJson<AvatarConfigApi>(response, '加载数字人档案失败。')
  return mapAvatarConfig(payload)
}

export async function fetchAvatarProfiles(
  apiBaseUrl: string,
  token: string,
): Promise<AvatarProfileListResponse> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/avatar/profiles`, {
    headers: buildAuthHeaders(token, ''),
  })
  const payload = await readJson<AvatarProfileListResponseApi>(response, '加载数字人档案列表失败。')
  return {
    items: payload.items.map(mapAvatarProfileSummary),
  }
}

export async function createAvatarProfile(
  apiBaseUrl: string,
  token: string,
  payload: AvatarProfileCreatePayload,
): Promise<AvatarConfig> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/avatar/profiles`, {
    method: 'POST',
    headers: buildAuthHeaders(token),
    body: JSON.stringify({
      name: payload.name,
      model_path: payload.modelPath,
      voice_id: payload.voiceId,
      response_language: payload.responseLanguage,
      voice_profile_id: payload.voiceProfileId ?? null,
      persona: payload.persona,
      tts_reference_audio_path: payload.ttsReferenceAudioPath,
      tts_reference_text: payload.ttsReferenceText,
      tts_speed: payload.ttsSpeed,
      tts_emotion_enabled: payload.ttsEmotionEnabled,
      display_scale: payload.displayScale,
      display_offset_x: payload.displayOffsetX,
      display_offset_y: payload.displayOffsetY,
      stage_height: payload.stageHeight,
      activate: payload.activate ?? true,
    }),
  })
  const result = await readJson<AvatarConfigApi>(response, '新建数字人档案失败。')
  return mapAvatarConfig(result)
}

export async function activateAvatarProfile(
  apiBaseUrl: string,
  token: string,
  profileId: number,
): Promise<AvatarConfig> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/avatar/profiles/${profileId}/activate`, {
    method: 'POST',
    headers: buildAuthHeaders(token, ''),
  })
  const result = await readJson<AvatarConfigApi>(response, '切换数字人档案失败。')
  return mapAvatarConfig(result)
}

export async function deleteAvatarProfile(
  apiBaseUrl: string,
  token: string,
  profileId: number,
): Promise<MessageResponse> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/avatar/profiles/${profileId}`, {
    method: 'DELETE',
    headers: buildAuthHeaders(token, ''),
  })
  return await readJson<MessageResponse>(response, '删除数字人档案失败。')
}

export async function updateAvatarConfig(
  apiBaseUrl: string,
  token: string,
  payload: AvatarConfigUpdate,
  options: {
    profileId?: number
  } = {},
): Promise<MessageResponse> {
  const requestPayload = {
    ...(payload.name !== undefined ? { name: payload.name } : {}),
    ...(payload.modelPath !== undefined ? { model_path: payload.modelPath } : {}),
    ...(payload.voiceId !== undefined ? { voice_id: payload.voiceId } : {}),
    ...(payload.voiceProfileId !== undefined ? { voice_profile_id: payload.voiceProfileId } : {}),
    ...(payload.responseLanguage !== undefined ? { response_language: payload.responseLanguage } : {}),
    ...(payload.persona !== undefined ? { persona: payload.persona } : {}),
    ...(payload.ttsReferenceAudioPath !== undefined
      ? { tts_reference_audio_path: payload.ttsReferenceAudioPath }
      : {}),
    ...(payload.ttsReferenceText !== undefined ? { tts_reference_text: payload.ttsReferenceText } : {}),
    ...(payload.ttsSpeed !== undefined ? { tts_speed: payload.ttsSpeed } : {}),
    ...(payload.ttsEmotionEnabled !== undefined
      ? { tts_emotion_enabled: payload.ttsEmotionEnabled }
      : {}),
    ...(payload.displayScale !== undefined ? { display_scale: payload.displayScale } : {}),
    ...(payload.displayOffsetX !== undefined ? { display_offset_x: payload.displayOffsetX } : {}),
    ...(payload.displayOffsetY !== undefined ? { display_offset_y: payload.displayOffsetY } : {}),
    ...(payload.stageHeight !== undefined ? { stage_height: payload.stageHeight } : {}),
  }

  const query = new URLSearchParams()
  if (options.profileId !== undefined) {
    query.set('profile_id', String(options.profileId))
  }

  const response = await fetch(
    `${trimApiBaseUrl(apiBaseUrl)}/admin/avatar/config${query.size ? `?${query.toString()}` : ''}`,
    {
      method: 'PUT',
      headers: buildAuthHeaders(token),
      body: JSON.stringify(requestPayload),
    },
  )

  return await readJson<MessageResponse>(response, '保存数字人配置失败。')
}

export async function fetchKnowledgeDocs(
  apiBaseUrl: string,
  token: string,
  options: {
    page?: number
    size?: number
    category?: string
  } = {},
): Promise<KnowledgeDocListResponse> {
  const query = new URLSearchParams()
  query.set('page', String(options.page ?? 1))
  query.set('size', String(options.size ?? 100))
  if (options.category) {
    query.set('category', options.category)
  }

  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/knowledge?${query.toString()}`, {
    headers: buildAuthHeaders(token, ''),
  })
  const payload = await readJson<KnowledgeDocListResponseApi>(response, '加载知识库列表失败。')
  return {
    total: payload.total,
    items: payload.items.map((item) => ({
      id: item.id,
      filename: item.filename,
      category: item.category,
      storedPath: item.stored_path,
      chunkCount: item.chunk_count,
      uploadedAt: item.uploaded_at,
      status: item.status,
      errorMessage: item.error_message,
    })),
  }
}

export async function uploadKnowledgeDoc(
  apiBaseUrl: string,
  token: string,
  payload: {
    file: File
    category: string
  },
): Promise<KnowledgeUploadResult> {
  const formData = new FormData()
  formData.append('file', payload.file)
  formData.append('category', payload.category)

  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/knowledge/upload`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  })

  const result = await readJson<KnowledgeUploadResultApi>(response, '上传知识库文件失败。')
  return {
    docId: result.doc_id,
    status: result.status,
    message: result.message,
  }
}

export async function deleteKnowledgeDoc(apiBaseUrl: string, token: string, docId: string) {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/knowledge/${docId}`, {
    method: 'DELETE',
    headers: buildAuthHeaders(token, ''),
  })
  return await readJson<MessageResponse>(response, '删除知识库文档失败。')
}

export async function fetchKnowledgeGaps(
  apiBaseUrl: string,
  token: string,
  options: {
    page?: number
    size?: number
    status?: string
    search?: string
  } = {},
): Promise<KnowledgeGapListResponse> {
  const query = new URLSearchParams()
  query.set('page', String(options.page ?? 1))
  query.set('size', String(options.size ?? 12))
  if (options.status) {
    query.set('status', options.status)
  }
  if (options.search) {
    query.set('search', options.search)
  }

  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/knowledge/gaps?${query.toString()}`, {
    headers: buildAuthHeaders(token, ''),
  })
  const payload = await readJson<KnowledgeGapListResponseApi>(response, '加载知识缺口列表失败。')
  return {
    total: payload.total,
    items: payload.items.map(mapKnowledgeGapItem),
  }
}

export async function fetchKnowledgeGapSummary(
  apiBaseUrl: string,
  token: string,
): Promise<KnowledgeGapSummary> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/knowledge/gaps/summary`, {
    headers: buildAuthHeaders(token, ''),
  })
  const payload = await readJson<KnowledgeGapSummaryApi>(response, '加载知识缺口统计失败。')
  return {
    totalQuestions: payload.total_questions,
    totalOccurrences: payload.total_occurrences,
    statusCounts: (payload.status_counts || []).map((item) => ({
      status: item.status,
      count: item.count,
    })),
    highlights: (payload.highlights || []).map((item) => ({
      id: item.id,
      representativeQuestion: item.representative_question,
      occurrenceCount: item.occurrence_count,
      status: item.status,
      lastSeenAt: item.last_seen_at,
    })),
  }
}

export async function fetchKnowledgeGapDetail(
  apiBaseUrl: string,
  token: string,
  gapId: string,
): Promise<KnowledgeGapItem> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/knowledge/gaps/${gapId}`, {
    headers: buildAuthHeaders(token, ''),
  })
  const payload = await readJson<KnowledgeGapItemApi>(response, '加载知识缺口详情失败。')
  return mapKnowledgeGapItem(payload)
}

export async function updateKnowledgeGap(
  apiBaseUrl: string,
  token: string,
  gapId: string,
  payload: KnowledgeGapUpdatePayload,
): Promise<KnowledgeGapItem> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/knowledge/gaps/${gapId}`, {
    method: 'PUT',
    headers: buildAuthHeaders(token),
    body: JSON.stringify({
      ...(payload.status !== undefined ? { status: payload.status } : {}),
      ...(payload.adminTitle !== undefined ? { admin_title: payload.adminTitle } : {}),
      ...(payload.adminCategory !== undefined ? { admin_category: payload.adminCategory } : {}),
      ...(payload.adminAnswer !== undefined ? { admin_answer: payload.adminAnswer } : {}),
      ...(payload.adminNotes !== undefined ? { admin_notes: payload.adminNotes } : {}),
    }),
  })
  const result = await readJson<KnowledgeGapItemApi>(response, '保存知识缺口草稿失败。')
  return mapKnowledgeGapItem(result)
}

export async function importKnowledgeGap(
  apiBaseUrl: string,
  token: string,
  gapId: string,
  payload: KnowledgeGapImportPayload,
): Promise<KnowledgeGapImportResult> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/knowledge/gaps/${gapId}/import`, {
    method: 'POST',
    headers: buildAuthHeaders(token),
    body: JSON.stringify({
      ...(payload.adminTitle !== undefined ? { admin_title: payload.adminTitle } : {}),
      ...(payload.adminCategory !== undefined ? { admin_category: payload.adminCategory } : {}),
      ...(payload.adminAnswer !== undefined ? { admin_answer: payload.adminAnswer } : {}),
      ...(payload.adminNotes !== undefined ? { admin_notes: payload.adminNotes } : {}),
      ...(payload.filenamePrefix !== undefined ? { filename_prefix: payload.filenamePrefix } : {}),
    }),
  })
  const result = await readJson<KnowledgeGapImportResultApi>(response, '导入知识库失败。')
  return {
    item: mapKnowledgeGapItem(result.item),
    message: result.message,
  }
}

export async function fetchVoiceProfiles(apiBaseUrl: string, token: string): Promise<VoiceProfile[]> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/voice-profiles`, {
    headers: buildAuthHeaders(token, ''),
  })
  const payload = await readJson<VoiceProfileListResponseApi>(response, '加载音色资源列表失败。')
  return payload.items.map(mapVoiceProfile)
}

export async function uploadVoiceProfile(
  apiBaseUrl: string,
  token: string,
  payload: {
    file: File
    name: string
    referenceText: string
    description: string
  },
): Promise<VoiceProfileUploadResult> {
  const formData = new FormData()
  formData.append('file', payload.file)
  formData.append('name', payload.name)
  formData.append('reference_text', payload.referenceText)
  formData.append('description', payload.description)

  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/voice-profiles`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  })
  const result = await readJson<VoiceProfileUploadResultApi>(response, '上传音色资源失败。')
  return {
    item: mapVoiceProfile(result.item),
    message: result.message,
  }
}

export async function deleteVoiceProfile(apiBaseUrl: string, token: string, profileId: string) {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/voice-profiles/${profileId}`, {
    method: 'DELETE',
    headers: buildAuthHeaders(token, ''),
  })
  return await readJson<MessageResponse>(response, '删除音色资源失败。')
}

export async function fetchVoiceProfileAudioBlobUrl(
  apiBaseUrl: string,
  token: string,
  profileId: string,
): Promise<string> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/voice-profiles/${profileId}/audio`, {
    headers: buildAuthHeaders(token, ''),
  })

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, '加载音色试听失败。'))
  }

  const blob = await response.blob()
  return URL.createObjectURL(blob)
}

export async function fetchAdminSessions(
  apiBaseUrl: string,
  token: string,
  options: {
    limit?: number
  } = {},
): Promise<AdminSessionListResponse> {
  const query = new URLSearchParams()
  query.set('limit', String(options.limit ?? 50))

  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/sessions?${query.toString()}`, {
    headers: buildAuthHeaders(token, ''),
  })
  const payload = await readJson<AdminSessionListResponseApi>(response, '加载会话记录列表失败。')
  return {
    items: payload.items.map(mapAdminSessionSummary),
  }
}

export async function fetchAdminSessionDetail(
  apiBaseUrl: string,
  token: string,
  sessionId: string,
): Promise<AdminSessionDetail> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/sessions/${sessionId}`, {
    headers: buildAuthHeaders(token, ''),
  })
  const payload = await readJson<AdminSessionDetailApi>(response, '加载会话详情失败。')
  return {
    sessionId: payload.session_id,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at,
    deviceType: payload.device_type,
    interestTags: payload.interest_tags,
    messageCount: payload.message_count,
    items: payload.items.map(mapAdminSessionMessage),
    replyTraces: payload.reply_traces.map(mapAdminReplyTrace),
    replyTraceSummary: mapAdminReplyTraceSummary(payload.reply_trace_summary),
  }
}

export async function fetchDailyReports(
  apiBaseUrl: string,
  token: string,
  options: {
    dateFrom?: string
    dateTo?: string
    limit?: number
  } = {},
): Promise<DailyEmotionReportListResponse> {
  const query = new URLSearchParams()
  if (options.dateFrom) {
    query.set('date_from', options.dateFrom)
  }
  if (options.dateTo) {
    query.set('date_to', options.dateTo)
  }
  query.set('limit', String(options.limit ?? 31))

  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/reports/daily?${query.toString()}`, {
    headers: buildAuthHeaders(token, ''),
  })
  const payload = await readJson<DailyEmotionReportListResponseApi>(response, '加载日报列表失败。')
  return {
    items: payload.items.map(mapDailyEmotionReport),
  }
}

export async function fetchReportSummary(
  apiBaseUrl: string,
  token: string,
  options: {
    dateFrom?: string
    dateTo?: string
  } = {},
): Promise<ReportRangeSummary> {
  const query = new URLSearchParams()
  if (options.dateFrom) {
    query.set('date_from', options.dateFrom)
  }
  if (options.dateTo) {
    query.set('date_to', options.dateTo)
  }

  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/reports/summary?${query.toString()}`, {
    headers: buildAuthHeaders(token, ''),
  })
  const payload = await readJson<ReportRangeSummaryApi>(response, '加载报告汇总失败。')
  return {
    dateFrom: payload.date_from,
    dateTo: payload.date_to,
    reportCount: payload.report_count,
    sessionCount: payload.session_count,
    messageCount: payload.message_count,
    userMessageCount: payload.user_message_count,
    assistantMessageCount: payload.assistant_message_count,
    avgAssistantLatencyMs: payload.avg_assistant_latency_ms,
    emotionCounts: payload.emotion_counts,
    topInterestTags: payload.top_interest_tags,
    topKeywords: payload.top_keywords,
    overallSentiment: payload.overall_sentiment,
    summaryText: payload.summary_text,
  }
}

export async function fetchDashboardOverview(
  apiBaseUrl: string,
  token: string,
  options: {
    period?: 'today' | 'week' | 'month'
  } = {},
): Promise<DashboardOverview> {
  const query = new URLSearchParams()
  query.set('period', options.period ?? 'week')

  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/dashboard/overview?${query.toString()}`, {
    headers: buildAuthHeaders(token, ''),
  })
  const payload = await readJson<DashboardOverviewApi>(response, 'Load dashboard overview failed.')
  return mapDashboardOverview(payload)
}

export async function fetchDashboardEmotion(
  apiBaseUrl: string,
  token: string,
  options: {
    start?: string
    end?: string
  } = {},
): Promise<DashboardEmotionSummary> {
  const query = new URLSearchParams()
  if (options.start) {
    query.set('start', options.start)
  }
  if (options.end) {
    query.set('end', options.end)
  }

  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/dashboard/emotion?${query.toString()}`, {
    headers: buildAuthHeaders(token, ''),
  })
  const payload = await readJson<DashboardEmotionSummaryApi>(response, 'Load dashboard emotion failed.')
  return mapDashboardEmotionSummary(payload)
}

export async function generateDailyReport(
  apiBaseUrl: string,
  token: string,
  options: {
    reportDate?: string
    force?: boolean
  } = {},
): Promise<DailyEmotionReport> {
  const query = new URLSearchParams()
  if (options.reportDate) {
    query.set('report_date', options.reportDate)
  }
  if (options.force !== undefined) {
    query.set('force', String(options.force))
  }

  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/admin/reports/daily/generate?${query.toString()}`, {
    method: 'POST',
    headers: buildAuthHeaders(token, ''),
  })
  const payload = await readJson<DailyEmotionReportApi>(response, '生成日报失败。')
  return mapDailyEmotionReport(payload)
}
