import { NodeViewWrapper } from '@tiptap/react'
import type { NodeViewProps } from '@tiptap/react'
import { useEffect, useState } from 'react'

import { useAuth } from '../../auth/localAuth'
import { fetchManifestDetail } from '../embedApi'

export function ManifestEmbedCard({ node, editor }: NodeViewProps) {
  const manifestId = String(node.attrs.manifestId ?? '')
  const { getToken } = useAuth()
  const [title, setTitle] = useState(manifestId)
  const [meta, setMeta] = useState<string>('Loading manifest…')

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const manifest = await fetchManifestDetail(manifestId, getToken)
        if (cancelled) return
        setTitle(manifest.name)
        setMeta(`${manifest.type} · ${manifest.episode_count} episodes`)
      } catch (error) {
        if (cancelled) return
        setTitle(manifestId)
        setMeta((error as Error).message || 'Unable to load manifest')
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [manifestId, getToken])

  function handleOpen() {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const storage = editor.storage as any
    storage.manifestEmbed?.onOpenViewer?.(manifestId)
  }

  return (
    <NodeViewWrapper as="div" className="manifest-embed-card" data-manifest-id={manifestId}>
      <button type="button" className="manifest-embed-button" onClick={handleOpen}>
        <span className="manifest-embed-kicker">manifest</span>
        <strong>{title}</strong>
        <span>{meta}</span>
        <code>{manifestId}</code>
      </button>
    </NodeViewWrapper>
  )
}
