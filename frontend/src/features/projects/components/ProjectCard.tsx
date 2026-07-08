import { useMemo, type MouseEvent } from 'react'
import { Link } from 'react-router-dom'

import type { ProjectSummary } from '../types'

interface ProjectCardProps {
  project: ProjectSummary
  canManage: boolean
  showOwner: boolean
  href: string
  onEdit: (project: ProjectSummary) => void
  onDelete: (project: ProjectSummary) => void
}

function formatDate(value: string) {
  const date = new Date(value)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}.${month}.${day}`
}

export function ProjectCard({ project, canManage, showOwner, href, onEdit, onDelete }: ProjectCardProps) {
  const description = useMemo(() => {
    if (!project.description) return 'No project description yet.'
    return project.description.length <= 140 ? project.description : `${project.description.slice(0, 137)}...`
  }, [project.description])

  function stopNavigation(event: MouseEvent<HTMLButtonElement>) {
    event.preventDefault()
    event.stopPropagation()
  }

  return (
    <article className="project-card">
      <Link to={href} className="project-card-surface">
        <div className="project-card-header">
          <div>
            {showOwner ? <p className="project-card-owner">@{project.owner_username}</p> : null}
            <h3>{project.name}</h3>
          </div>

          {canManage ? (
            <div className="project-card-actions">
              <button
                type="button"
                className="project-card-icon-button"
                aria-label="Edit project"
                onClick={(event) => {
                  stopNavigation(event)
                  onEdit(project)
                }}
              >
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M3 11.5 11.8 2.7l1.5 1.5L4.5 13H3z" />
                  <path d="M10.9 3.6 12.4 5.1" />
                </svg>
              </button>
              <button
                type="button"
                className="project-card-icon-button project-card-icon-danger"
                aria-label="Delete project"
                onClick={(event) => {
                  stopNavigation(event)
                  onDelete(project)
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
            </div>
          ) : null}
        </div>

        <p className="project-card-description">{description}</p>

        <div className="project-card-tags">
          {project.tags.length > 0 ? (
            project.tags.map((tag) => (
              <span key={tag} className="project-tag">
                {tag}
              </span>
            ))
          ) : (
            <span className="project-tag project-tag-muted">untagged</span>
          )}
        </div>

        <div className="project-card-meta">
          <span>[{project.is_public ? 'PUBLIC' : 'PRIVATE'}]</span>
          <span>{formatDate(project.updated_at)}</span>
        </div>
      </Link>
    </article>
  )
}
