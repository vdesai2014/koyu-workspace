import { type MouseEvent } from 'react'
import { Link } from 'react-router-dom'

import type { ManifestSummary } from '../projects/types'

interface DatasetCardProps {
  manifest: ManifestSummary
  onEdit?: (manifest: ManifestSummary) => void
  onDelete?: (manifest: ManifestSummary) => void
}

function formatDate(value: string) {
  const date = new Date(value)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}.${month}.${day}`
}

function stopNavigation(event: MouseEvent<HTMLButtonElement>) {
  event.preventDefault()
  event.stopPropagation()
}

export function DatasetCard({ manifest, onEdit, onDelete }: DatasetCardProps) {
  const canManage = Boolean(onEdit || onDelete)

  return (
    <article className="project-card dataset-card" data-tour-manifest={manifest.name}>
      <Link to={`/datasets/${manifest.id}`} className="project-card-surface">
        <div className="project-card-header">
          <div>
            <p className="project-card-owner">{manifest.type}</p>
            <h3>{manifest.name}</h3>
          </div>

          {canManage ? (
            <div className="project-card-actions">
              {onEdit ? (
                <button
                  type="button"
                  className="project-card-icon-button"
                  aria-label="Edit dataset"
                  onClick={(event) => {
                    stopNavigation(event)
                    onEdit(manifest)
                  }}
                >
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M3 11.5 11.8 2.7l1.5 1.5L4.5 13H3z" />
                    <path d="M10.9 3.6 12.4 5.1" />
                  </svg>
                </button>
              ) : null}
              {onDelete ? (
                <button
                  type="button"
                  className="project-card-icon-button project-card-icon-danger"
                  aria-label="Delete dataset"
                  onClick={(event) => {
                    stopNavigation(event)
                    onDelete(manifest)
                  }}
                >
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M3 4.5h10" />
                    <path d="M6 4.5v-1h4v1" />
                    <path d="M5 6.5v5" />
                    <path d="M8 6.5v5" />
                    <path d="M11 6.5v5" />
                    <path d="M4 4.5l.6 8h6.8l.6-8" />
                  </svg>
                </button>
              ) : null}
            </div>
          ) : null}
        </div>

        <p className="project-card-description">
          {manifest.description || 'No dataset description yet.'}
        </p>

        <div className="project-card-tags">
          {manifest.tags.length > 0 ? (
            manifest.tags.map((tag) => (
              <span key={tag} className="project-tag">
                {tag}
              </span>
            ))
          ) : (
            <span className="project-tag project-tag-muted">untagged</span>
          )}
        </div>

        <div className="project-card-meta">
          <span>[{manifest.is_public ? 'PUBLIC' : 'PRIVATE'}]</span>
          <span>{manifest.episode_count} EPS</span>
          <span>{manifest.fps ?? '—'} FPS</span>
          <span>{formatDate(manifest.updated_at)}</span>
        </div>
      </Link>
    </article>
  )
}
