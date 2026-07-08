import { env } from '../../app/env'
import type { ManifestSummary } from '../projects/types'
import type {
  DatasetEpisodeDetail,
  DatasetEpisodePage,
  DatasetEpisodeSummary,
  DatasetManifestDetail,
  DatasetManifestRunListResponse,
} from './types'

type TokenGetter = (() => Promise<string | null>) | undefined

export interface ManifestPatchInput {
  name?: string
  description?: string | null
  type?: string
  tags?: string[]
  is_public?: boolean
  fps?: number | null
}

async function buildAuthHeaders(getToken?: TokenGetter): Promise<Record<string, string>> {
  if (!getToken) return {}
  const token = await getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function fetchDatasetManifest(manifestId: string, getToken?: TokenGetter) {
  const response = await fetch(`${env.apiBase}/api/manifests/${manifestId}`, {
    headers: await buildAuthHeaders(getToken),
  })
  if (!response.ok) {
    throw new Error(response.status === 403 ? 'Private manifest' : `Manifest load failed with ${response.status}`)
  }
  return response.json() as Promise<DatasetManifestDetail>
}

export async function fetchDatasetManifestRuns(manifestId: string, getToken?: TokenGetter) {
  const response = await fetch(`${env.apiBase}/api/manifests/${manifestId}/runs`, {
    headers: await buildAuthHeaders(getToken),
  })
  if (!response.ok) {
    throw new Error(`Manifest run links failed with ${response.status}`)
  }
  return response.json() as Promise<DatasetManifestRunListResponse>
}

export async function fetchDatasetEpisodesPage(
  manifestId: string,
  limit: number,
  cursor: string | null,
  getToken?: TokenGetter,
) {
  const search = new URLSearchParams({ limit: String(limit) })
  if (cursor) search.set('cursor', cursor)
  const response = await fetch(`${env.apiBase}/api/manifests/${manifestId}/episodes?${search.toString()}`, {
    headers: await buildAuthHeaders(getToken),
  })
  if (!response.ok) {
    throw new Error(`Episode page load failed with ${response.status}`)
  }
  return response.json() as Promise<DatasetEpisodePage>
}

export async function fetchDatasetEpisodeDetail(
  manifestId: string,
  episodeId: string,
  getToken?: TokenGetter,
) {
  const response = await fetch(`${env.apiBase}/api/manifests/${manifestId}/episodes/batch-get`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(await buildAuthHeaders(getToken)),
    },
    body: JSON.stringify({ episode_ids: [episodeId] }),
  })
  if (!response.ok) {
    throw new Error(`Episode detail load failed with ${response.status}`)
  }
  const payload = await response.json() as { episodes: DatasetEpisodeDetail[] }
  return payload.episodes[0] ?? null
}

export function getEpisodeCameraList(detail: DatasetEpisodeDetail | null): string[] {
  if (!detail) return []
  const cameras = new Set<string>()

  for (const [key, spec] of Object.entries(detail.features)) {
    if (spec.dtype !== 'video') continue
    if (key.startsWith('observation.images.')) {
      cameras.add(key.slice('observation.images.'.length))
    } else if (key.startsWith('observation.')) {
      cameras.add(key.slice('observation.'.length))
    } else {
      cameras.add(key)
    }
  }

  for (const path of Object.keys(detail.files)) {
    const match = path.match(/^videos\/observation\.images\.([^.\/]+)\.mp4$/)
    if (match) cameras.add(match[1])
  }

  return Array.from(cameras)
}

export async function updateManifest(
  manifestId: string,
  body: ManifestPatchInput,
  getToken?: TokenGetter,
): Promise<ManifestSummary> {
  const response = await fetch(`${env.apiBase}/api/manifests/${manifestId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      ...(await buildAuthHeaders(getToken)),
    },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`Manifest update failed with ${response.status}`)
  }
  return response.json() as Promise<ManifestSummary>
}

export async function deleteManifest(manifestId: string, getToken?: TokenGetter): Promise<void> {
  const response = await fetch(`${env.apiBase}/api/manifests/${manifestId}`, {
    method: 'DELETE',
    headers: await buildAuthHeaders(getToken),
  })
  if (!response.ok) {
    throw new Error(`Manifest delete failed with ${response.status}`)
  }
}

export async function patchEpisode(
  episodeId: string,
  body: { reward?: number | null; task?: string | null; task_description?: string | null },
  getToken?: TokenGetter,
): Promise<DatasetEpisodeSummary> {
  const response = await fetch(`${env.apiBase}/api/episodes/${episodeId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      ...(await buildAuthHeaders(getToken)),
    },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`Episode patch failed with ${response.status}`)
  }
  return response.json() as Promise<DatasetEpisodeSummary>
}

export function resolveEpisodeVideoUrl(
  files: Record<string, { url: string; size: number }>,
  camera: string,
) {
  const candidates = [
    `videos/observation.images.${camera}.mp4`,
    `videos/${camera}.mp4`,
  ]
  for (const candidate of candidates) {
    if (files[candidate]) return files[candidate].url
  }
  return null
}

export function getParquetUrl(files: Record<string, { url: string; size: number }>) {
  return files['data.parquet']?.url ?? null
}
