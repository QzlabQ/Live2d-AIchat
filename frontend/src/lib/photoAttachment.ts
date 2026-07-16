const SUPPORTED_VISITOR_PHOTO_TYPES = new Set([
  'image/jpeg',
  'image/png',
  'image/webp',
])

type ClipboardItemLike = {
  kind?: string
  type?: string
  getAsFile?: () => File | null
}

function normalizeMimeType(value: string | null | undefined) {
  return (value || '').trim().toLowerCase()
}

export function canUsePhotoAttachment(state: {
  sessionBooting: boolean
  sessionsLoading: boolean
}) {
  return !state.sessionBooting && !state.sessionsLoading
}

export function extractClipboardImageFile(
  items: Iterable<ClipboardItemLike> | null | undefined,
) {
  if (!items) {
    return null
  }

  for (const item of items) {
    if (item.kind !== 'file') {
      continue
    }

    const itemType = normalizeMimeType(item.type)
    const file = item.getAsFile?.() ?? null
    const fileType = normalizeMimeType(file?.type)

    if (SUPPORTED_VISITOR_PHOTO_TYPES.has(fileType) || SUPPORTED_VISITOR_PHOTO_TYPES.has(itemType)) {
      return file
    }
  }

  return null
}
