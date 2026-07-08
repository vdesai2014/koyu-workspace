import { NodeViewWrapper } from '@tiptap/react'
import type { NodeViewProps } from '@tiptap/react'
import { useEffect, useState } from 'react'

import { useAuth } from '../../auth/localAuth'
import { fetchManifestEpisode, resolveEpisodeVideoUrl } from '../embedApi'

export function VideoEmbedBlock({ node }: NodeViewProps) {
  const manifestId = String(node.attrs.manifestId ?? '')
  const episodeId = String(node.attrs.episodeId ?? '')
  const camera = String(node.attrs.camera ?? '')
  const { getToken } = useAuth()
  const [videoUrl, setVideoUrl] = useState<string | null>(null)
  const [status, setStatus] = useState('Loading video…')

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const episode = await fetchManifestEpisode(manifestId, episodeId, getToken)
        if (cancelled) return
        if (!episode) {
          setStatus('Episode not found')
          return
        }
        const resolved = resolveEpisodeVideoUrl(episode.files, camera)
        if (!resolved) {
          setStatus(`No mp4 found for camera "${camera}"`)
          return
        }
        setVideoUrl(resolved)
        setStatus('')
      } catch (error) {
        if (cancelled) return
        setStatus((error as Error).message || 'Unable to load video')
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [manifestId, episodeId, camera, getToken])

  return (
    <NodeViewWrapper as="div" className="video-embed-block" data-manifest-id={manifestId} data-episode-id={episodeId}>
      <div className="video-embed-meta">
        <span>video</span>
        <code>{manifestId}</code>
        <code>{episodeId}</code>
        <span>{camera}</span>
      </div>
      {videoUrl ? (
        <video className="video-embed-player" controls preload="metadata" src={videoUrl} />
      ) : (
        <div className="video-embed-placeholder">{status}</div>
      )}
    </NodeViewWrapper>
  )
}
