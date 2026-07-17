import { assertRecommendationInterestTags } from '../lib/recommendationState'
import { normalizeVisitorMessageRole } from '../lib/visitorSessionState'
import type {
  VisitorAvatarProfileListResponse,
  VisitorAvatarProfileSummary,
  VisionRecognitionResult,
  VisitorRecommendation,
  VisitorSessionListResponse,
  VisitorSessionMessageListResponse,
  VisitorSessionSummary,
} from '../types/visitor'

interface SessionCreateResponseApi {
  session_id: string
}

interface VisitorSessionSummaryApi {
  session_id: string
  created_at: string
  updated_at: string
  interest_tags: string[]
  message_count: number
  last_message_preview: string
}

interface VisitorSessionListResponseApi {
  items: VisitorSessionSummaryApi[]
}

interface VisitorSessionMessageApi {
  id: number
  role: string
  content: string
  created_at: string
}

interface VisitorSessionMessageListResponseApi {
  items: VisitorSessionMessageApi[]
}

interface VisitorRecommendationApi {
  route_title: string
  intro: string
  highlights: string[]
  suggested_questions: string[]
  applied_interest_tags: string[]
}

interface VisionRecognitionResultApi {
  recognized_spot: string
  recognition_summary: string
  resolved_question: string
  stored_image_path: string
}

interface VisitorAvatarProfileSummaryApi {
  id: number
  name: string
  slug: string
  is_active: boolean
  model_path: string
  display_scale: number
  display_offset_x: number
  display_offset_y: number
  stage_height: number
  updated_at: string
}

interface VisitorAvatarProfileListResponseApi {
  items: VisitorAvatarProfileSummaryApi[]
}

const MODEL_FALLBACK_PATH = '/live2d/haru/haru_greeter_t03.model3.json'
const LEGACY_BROKEN_MODEL_PATH = '/live2d/models/guide/guide.model3.json'

function trimApiBaseUrl(apiBaseUrl: string) {
  return apiBaseUrl.replace(/\/+$/, '')
}

async function readJson<T>(response: Response, action: string) {
  if (!response.ok) {
    let detail = ''
    try {
      const payload = (await response.json()) as { detail?: unknown }
      if (typeof payload.detail === 'string' && payload.detail.trim()) {
        detail = payload.detail.trim()
      }
    } catch {
      // Fall back to the HTTP status when the backend does not return JSON.
    }

    throw new Error(detail ? `Failed to ${action}: ${detail}` : `Failed to ${action}: ${response.status}`)
  }

  return (await response.json()) as T
}

function mapSessionSummary(item: VisitorSessionSummaryApi): VisitorSessionSummary {
  return {
    sessionId: item.session_id,
    createdAt: item.created_at,
    updatedAt: item.updated_at,
    interestTags: item.interest_tags,
    messageCount: item.message_count,
    lastMessagePreview: item.last_message_preview,
  }
}

function mapRecommendation(payload: VisitorRecommendationApi): VisitorRecommendation {
  return {
    routeTitle: payload.route_title,
    intro: payload.intro,
    highlights: payload.highlights,
    suggestedQuestions: payload.suggested_questions,
    appliedInterestTags: payload.applied_interest_tags,
  }
}

function mapVisionRecognition(payload: VisionRecognitionResultApi): VisionRecognitionResult {
  return {
    recognizedSpot: payload.recognized_spot,
    recognitionSummary: payload.recognition_summary,
    resolvedQuestion: payload.resolved_question,
    storedImagePath: payload.stored_image_path,
  }
}

function mapVisitorAvatarProfile(
  payload: VisitorAvatarProfileSummaryApi,
): VisitorAvatarProfileSummary {
  const normalizedModelPath =
    payload.model_path && payload.model_path !== LEGACY_BROKEN_MODEL_PATH
      ? payload.model_path
      : MODEL_FALLBACK_PATH

  return {
    id: payload.id,
    name: payload.name,
    slug: payload.slug,
    isActive: payload.is_active,
    modelPath: normalizedModelPath,
    displayScale: payload.display_scale,
    displayOffsetX: payload.display_offset_x,
    displayOffsetY: payload.display_offset_y,
    stageHeight: payload.stage_height,
    updatedAt: payload.updated_at,
  }
}

export async function createVisitorSession(
  apiBaseUrl: string,
  payload: {
    interestTags?: string[]
    deviceType?: 'mobile' | 'kiosk'
  } = {},
) {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/sessions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      interest_tags: payload.interestTags ?? [],
      device_type: payload.deviceType ?? 'mobile',
    }),
  })

  const data = await readJson<SessionCreateResponseApi>(response, 'create session')
  return {
    sessionId: data.session_id,
  }
}

export async function listVisitorSessions(apiBaseUrl: string): Promise<VisitorSessionListResponse> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/sessions`)
  const data = await readJson<VisitorSessionListResponseApi>(response, 'load sessions')

  return {
    items: data.items.map(mapSessionSummary),
  }
}

export async function loadVisitorSessionMessages(
  apiBaseUrl: string,
  sessionId: string,
): Promise<VisitorSessionMessageListResponse> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/sessions/${sessionId}/messages`)
  const data = await readJson<VisitorSessionMessageListResponseApi>(response, 'load session messages')

  return {
    items: data.items.map((item) => ({
      id: item.id,
      role: normalizeVisitorMessageRole(item.role),
      content: item.content,
      createdAt: item.created_at,
    })),
  }
}

export async function updateVisitorSessionInterestTags(
  apiBaseUrl: string,
  sessionId: string,
  interestTags: string[],
) {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      interest_tags: interestTags,
    }),
  })

  const data = await readJson<VisitorSessionSummaryApi>(response, 'update interest tags')
  return mapSessionSummary(data)
}

export async function fetchVisitorRecommendations(
  apiBaseUrl: string,
  sessionId: string,
  interestTags: string[],
  visitorProfile?: string,
): Promise<VisitorRecommendation> {
  const normalizedInterestTags = assertRecommendationInterestTags(interestTags)
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/sessions/${sessionId}/recommendations`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      interest_tags: normalizedInterestTags,
      visitor_profile: visitorProfile,
    }),
  })

  const data = await readJson<VisitorRecommendationApi>(response, 'load recommendations')
  return mapRecommendation(data)
}

export async function recognizeVisitorPhoto(
  apiBaseUrl: string,
  sessionId: string,
  file: File,
  interestTags: string[],
  userPrompt?: string,
): Promise<VisionRecognitionResult> {
  const formData = new FormData()
  formData.append('file', file)
  if (interestTags.length > 0) {
    formData.append('interest_tags', JSON.stringify(interestTags))
  }
  if (userPrompt) {
    formData.append('user_prompt', userPrompt)
  }

  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/sessions/${sessionId}/vision/recognize`, {
    method: 'POST',
    body: formData,
  })

  const data = await readJson<VisionRecognitionResultApi>(response, 'recognize photo')
  return mapVisionRecognition(data)
}

export async function listVisitorAvatarProfiles(
  apiBaseUrl: string,
): Promise<VisitorAvatarProfileListResponse> {
  const response = await fetch(`${trimApiBaseUrl(apiBaseUrl)}/sessions/avatar/profiles`)
  const data = await readJson<VisitorAvatarProfileListResponseApi>(
    response,
    'load visitor avatar profiles',
  )

  return {
    items: data.items.map(mapVisitorAvatarProfile),
  }
}

export async function activateVisitorAvatarProfile(
  apiBaseUrl: string,
  profileId: number,
): Promise<VisitorAvatarProfileSummary> {
  const response = await fetch(
    `${trimApiBaseUrl(apiBaseUrl)}/sessions/avatar/profiles/${profileId}/activate`,
    {
      method: 'POST',
    },
  )
  const data = await readJson<VisitorAvatarProfileSummaryApi>(
    response,
    'activate visitor avatar profile',
  )
  return mapVisitorAvatarProfile(data)
}
