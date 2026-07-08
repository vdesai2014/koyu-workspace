type TokenGetter = (() => Promise<string | null>) | undefined

export interface ManifestDetail {
  id: string
  owner_user_id: string
  name: string
  description: string | null
  type: string
  tags: string[]
  is_public: boolean
  fps: number | null
  encoding: Record<string, unknown>
  features: Record<string, { dtype?: string; shape?: number[] }>
  run_ids: string[]
  episode_count: number
  created_at: string
  updated_at: string
}

export interface ManifestBatchEpisode {
  id: string
  length: number
  task: string | null
  task_description: string | null
  features: Record<string, { dtype?: string; shape?: number[] }>
  files: Record<string, { url: string; size: number }>
}

export async function fetchManifestDetail(manifestId: string, _getToken?: TokenGetter): Promise<ManifestDetail> {
  throw new Error(`Manifest viewer for "${manifestId}" is not available yet`)
}

export async function fetchManifestEpisode(
  _manifestId: string,
  _episodeId: string,
  _getToken?: TokenGetter,
): Promise<ManifestBatchEpisode | null> {
  return null as ManifestBatchEpisode | null
}

export function resolveEpisodeVideoUrl(
  files: Record<string, { url: string; size: number }>,
  camera: string,
) {
  const preferred = [
    `videos/observation.images.${camera}.mp4`,
    `videos/${camera}.mp4`,
  ]
  for (const key of preferred) {
    if (files[key]) return files[key].url
  }

  for (const [path, meta] of Object.entries(files)) {
    if (!path.endsWith('.mp4')) continue
    if (path.includes(`observation.images.${camera}`) || path.endsWith(`/${camera}.mp4`) || path === `${camera}.mp4`) {
      return meta.url
    }
  }
  return null
}
