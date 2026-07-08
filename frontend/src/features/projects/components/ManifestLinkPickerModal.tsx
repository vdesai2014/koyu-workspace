import { useMemo, useState } from 'react'

import { Modal } from '../../../components/ui/Modal'
import type { ManifestSummary } from '../types'

interface ManifestLinkPickerModalProps {
  manifests: ManifestSummary[]
  scope: 'all' | 'shared'
  onScopeChange: (scope: 'all' | 'shared') => void
  onSelect: (manifest: ManifestSummary) => void
  onClose: () => void
}

export function ManifestLinkPickerModal({
  manifests,
  scope,
  onScopeChange,
  onSelect,
  onClose,
}: ManifestLinkPickerModalProps) {
  const [query, setQuery] = useState('')
  const [activeTag, setActiveTag] = useState<string>('all')

  const tags = useMemo(() => {
    const values = new Set<string>()
    for (const manifest of manifests) {
      for (const tag of manifest.tags) values.add(tag)
    }
    return ['all', ...Array.from(values).sort((left, right) => left.localeCompare(right))]
  }, [manifests])

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return manifests.filter((manifest) => {
      const matchesQuery = !normalized
        || manifest.name.toLowerCase().includes(normalized)
        || manifest.id.toLowerCase().includes(normalized)
        || (manifest.description ?? '').toLowerCase().includes(normalized)
      const matchesTag = activeTag === 'all' || manifest.tags.includes(activeTag)
      return matchesQuery && matchesTag
    })
  }, [manifests, query, activeTag])

  return (
    <Modal title="Link Manifest" onClose={onClose}>
      <div className="manifest-picker">
        <div className="manifest-picker-scope-toggle">
          <button
            type="button"
            className={`manifest-picker-scope${scope === 'all' ? ' is-active' : ''}`}
            onClick={() => onScopeChange('all')}
          >
            All
          </button>
          <button
            type="button"
            className={`manifest-picker-scope${scope === 'shared' ? ' is-active' : ''}`}
            onClick={() => onScopeChange('shared')}
          >
            Shared with me
          </button>
        </div>

        <input
          className="manifest-picker-search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search manifests by name or id"
        />

        <div className="manifest-picker-tags">
          {tags.map((tag) => (
            <button
              key={tag}
              type="button"
              className={`manifest-picker-tag${activeTag === tag ? ' is-active' : ''}`}
              onClick={() => setActiveTag(tag)}
            >
              {tag}
            </button>
          ))}
        </div>

        <div className="manifest-picker-list">
          {filtered.length === 0 ? (
            <p className="project-detail-empty">No manifests match the current filter.</p>
          ) : (
            filtered.map((manifest) => (
              <button
                key={manifest.id}
                type="button"
                className="manifest-picker-item"
                onClick={() => onSelect(manifest)}
              >
                <div className="manifest-picker-item-top">
                  <strong>{manifest.name}</strong>
                  <span>{manifest.type}</span>
                </div>
                <div className="manifest-picker-item-meta">
                  <code>{manifest.id}</code>
                  <span>@{manifest.owner_username || manifest.owner_user_id}</span>
                  <span>{manifest.episode_count} episodes</span>
                </div>
                {manifest.tags.length > 0 ? (
                  <div className="manifest-picker-item-tags">
                    {manifest.tags.map((tag) => <span key={tag}>{tag}</span>)}
                  </div>
                ) : null}
              </button>
            ))
          )}
        </div>
      </div>
    </Modal>
  )
}
