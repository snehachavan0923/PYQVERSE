export interface YouTubeInfo {
  isYouTube: boolean
  isPlaylist: boolean
  videoId: string | null
  playlistId: string | null
  thumbnailUrl: string | null
}

export function parseYouTubeUrl(rawUrl: string | null | undefined): YouTubeInfo {
  if (!rawUrl || typeof rawUrl !== 'string') {
    return { isYouTube: false, isPlaylist: false, videoId: null, playlistId: null, thumbnailUrl: null }
  }
  const url = rawUrl.trim()
  try {
    const parsed = new URL(url)
    const host = parsed.hostname.toLowerCase()
    const isYt = host.includes('youtube.com') || host.includes('youtu.be')
    if (!isYt) {
      return { isYouTube: false, isPlaylist: false, videoId: null, playlistId: null, thumbnailUrl: null }
    }

    let videoId: string | null = null
    let playlistId: string | null = null

    if (host.includes('youtu.be')) {
      videoId = parsed.pathname.slice(1).split('?')[0] || null
      playlistId = parsed.searchParams.get('list')
    } else {
      videoId = parsed.searchParams.get('v')
      playlistId = parsed.searchParams.get('list')
      if (!videoId && parsed.pathname.startsWith('/shorts/')) {
        videoId = parsed.pathname.split('/shorts/')[1]?.split('?')[0] || null
      }
      if (!videoId && parsed.pathname.startsWith('/embed/')) {
        videoId = parsed.pathname.split('/embed/')[1]?.split('?')[0] || null
      }
    }

    const isPlaylist = Boolean(playlistId && (!videoId || parsed.pathname.includes('/playlist')))
    const thumbnailUrl = videoId ? `https://img.youtube.com/vi/${videoId}/hqdefault.jpg` : null

    return {
      isYouTube: true,
      isPlaylist,
      videoId,
      playlistId,
      thumbnailUrl,
    }
  } catch {
    return { isYouTube: false, isPlaylist: false, videoId: null, playlistId: null, thumbnailUrl: null }
  }
}

export function isValidHttpUrl(rawUrl: string | null | undefined): boolean {
  if (!rawUrl || typeof rawUrl !== 'string') return false
  const trimmed = rawUrl.trim()
  try {
    const url = new URL(trimmed)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

export function getDomain(rawUrl: string | null | undefined): string {
  if (!rawUrl || typeof rawUrl !== 'string') return ''
  try {
    return new URL(rawUrl.trim()).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}

export function detectResourceSource(item: {
  resource_source?: string | null
  external_url?: string | null
  storage_path?: string | null
  file_size?: number | null
  file_type?: string | null
}): 'FILE' | 'LINK' | 'BOTH' {
  if (item.resource_source === 'FILE' || item.resource_source === 'LINK' || item.resource_source === 'BOTH') {
    return item.resource_source
  }
  const hasUrl = Boolean(item.external_url?.trim())
  const hasFile = Boolean(item.file_size || item.storage_path || (item.file_type && item.file_type !== 'none' && item.file_type !== 'link'))
  if (hasUrl && hasFile) return 'BOTH'
  if (hasUrl) return 'LINK'
  return 'FILE'
}
