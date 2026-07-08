import { useEffect, useMemo, useRef, useState } from 'react'

import { Button } from '../../../components/ui/Button'
import { useAuth, useUser } from '../../auth/localAuth'
import { createProject, deleteProject, listProjects, updateProject } from '../api'
import { ProjectCard } from '../components/ProjectCard'
import { ProjectFormModal } from '../components/ProjectFormModal'
import type { ProjectMutationInput, ProjectOrder, ProjectScope, ProjectSummary } from '../types'

const PER_PAGE_KEY = 'koyu_projects_per_page'
const PER_PAGE_OPTIONS = [5, 10, 15, 25] as const
const CARD_HEIGHT_ESTIMATE = 110

function readPerPage(): number | null {
  const stored = localStorage.getItem(PER_PAGE_KEY)
  if (!stored) return null
  const n = Number(stored)
  return PER_PAGE_OPTIONS.includes(n as typeof PER_PAGE_OPTIONS[number]) ? n : null
}

function autoPerPage(containerHeight: number): number {
  const fit = Math.floor(containerHeight / CARD_HEIGHT_ESTIMATE)
  for (let i = PER_PAGE_OPTIONS.length - 1; i >= 0; i--) {
    if (PER_PAGE_OPTIONS[i] <= fit) return PER_PAGE_OPTIONS[i]
  }
  return PER_PAGE_OPTIONS[0]
}

interface ProjectsPageProps {
  scope: ProjectScope
  title: string
  description: string
}

function toProjectPayload(values: {
  name: string
  description: string
  tags: string
  isPublic: boolean
}): ProjectMutationInput {
  const tags = values.tags
    .split(',')
    .map((tag) => tag.trim().toLowerCase())
    .filter(Boolean)

  return {
    name: values.name.trim(),
    description: values.description.trim() || null,
    tags,
    is_public: values.isPublic,
  }
}

export function ProjectsPage({ scope, title, description }: ProjectsPageProps) {
  const { getToken } = useAuth()
  const { user } = useUser()

  const listRef = useRef<HTMLDivElement>(null)
  const latestRequestRef = useRef(0)
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [totalCount, setTotalCount] = useState(0)
  const [cursorHistory, setCursorHistory] = useState<Array<string | null>>([null])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sortOrder, setSortOrder] = useState<ProjectOrder>('newest')
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [tagDraft, setTagDraft] = useState('')
  const [tagMenuOpen, setTagMenuOpen] = useState(false)
  const [formMode, setFormMode] = useState<'create' | 'edit' | null>(null)
  const [activeProject, setActiveProject] = useState<ProjectSummary | undefined>(undefined)
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [perPage, setPerPage] = useState<number>(() => readPerPage() ?? 10)
  const [autoDetected, setAutoDetected] = useState<boolean>(() => readPerPage() === null)

  useEffect(() => {
    if (!autoDetected || !listRef.current) return
    const h = listRef.current.clientHeight
    if (h > 0) {
      setPerPage(autoPerPage(h))
    }
  }, [autoDetected])

  function handlePerPageChange(value: number) {
    setPerPage(value)
    setAutoDetected(false)
    localStorage.setItem(PER_PAGE_KEY, String(value))
  }

  const currentCursor = cursorHistory[cursorHistory.length - 1] ?? null
  const currentPage = cursorHistory.length

  async function load(cursor: string | null = currentCursor) {
    const requestId = latestRequestRef.current + 1
    latestRequestRef.current = requestId
    setLoading(true)
    setError(null)

    try {
      const response = await listProjects(
        {
          scope,
          limit: perPage,
          cursor,
          tags: selectedTags,
          order: sortOrder,
        },
        scope === 'mine' ? getToken : undefined,
      )
      if (latestRequestRef.current !== requestId) return
      setProjects(response.projects)
      setNextCursor(response.next_cursor)
      setTotalCount(response.total_count)
    } catch (loadError) {
      if (latestRequestRef.current !== requestId) return
      setError((loadError as Error).message || 'Failed to load projects.')
    } finally {
      if (latestRequestRef.current === requestId) {
        setLoading(false)
      }
    }
  }

  useEffect(() => {
    setCursorHistory([null])
  }, [scope, perPage, sortOrder, selectedTags])

  useEffect(() => {
    void load(currentCursor)
  }, [scope, perPage, sortOrder, selectedTags, currentCursor])

  const allTags = useMemo(
    () =>
      Array.from(new Set(projects.flatMap((project) => project.tags)))
        .sort((left, right) => left.localeCompare(right)),
    [projects],
  )

  const filteredTags = useMemo(
    () =>
      allTags.filter((tag) => !selectedTags.includes(tag) && tag.toLowerCase().includes(tagDraft.toLowerCase())),
    [allTags, selectedTags, tagDraft],
  )

  function closeFormModal() {
    setFormMode(null)
    setActiveProject(undefined)
    setFormError(null)
  }

  async function handleCreateOrEdit(values: { name: string; description: string; tags: string; isPublic: boolean }) {
    const payload = toProjectPayload(values)
    if (!payload.name) {
      setFormError('Project name is required.')
      return
    }

    setSubmitting(true)
    setFormError(null)

    try {
      if (formMode === 'edit' && activeProject) {
        await updateProject(activeProject.id, payload, getToken)
      } else {
        await createProject(payload, getToken)
      }

      setCursorHistory([null])
      closeFormModal()
      await load(null)
    } catch (submitError) {
      setFormError((submitError as Error).message || 'Unable to save project.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(project: ProjectSummary) {
    const confirmed = window.confirm(`Delete "${project.name}"? This cannot be undone.`)
    if (!confirmed) {
      return
    }

    try {
      await deleteProject(project.id, getToken)
      await load(currentCursor)
    } catch (deleteError) {
      setError((deleteError as Error).message || 'Unable to delete project.')
    }
  }

  return (
    <section className="projects-page">
      <header className="projects-header">
        <div>
          <p className="eyebrow">{scope === 'mine' ? 'Workspace' : 'Public'}</p>
          <h1>{title}</h1>
          <p className="projects-copy">{description}</p>
        </div>
        {scope === 'mine' ? (
          <Button onClick={() => setFormMode('create')}>Create Project</Button>
        ) : null}
      </header>

      <div className="projects-toolbar">
        <div className="projects-tag-filter">
          <input
            value={tagDraft}
            onChange={(event) => {
              setTagDraft(event.target.value)
              setTagMenuOpen(true)
            }}
            onFocus={() => setTagMenuOpen(true)}
            onBlur={() => window.setTimeout(() => setTagMenuOpen(false), 120)}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                setTagMenuOpen(false)
              }
            }}
            placeholder="Filter by tag..."
          />
          {tagMenuOpen && filteredTags.length > 0 ? (
            <div className="projects-tag-suggestions">
              {filteredTags.slice(0, 6).map((tag) => (
                <button
                  key={tag}
                  type="button"
                  onClick={() => {
                    setSelectedTags((current) => [...current, tag])
                    setTagDraft('')
                    setTagMenuOpen(false)
                  }}
                >
                  {tag}
                </button>
              ))}
            </div>
          ) : null}
        </div>

        <div className="projects-pagination-inline">
          <span className="projects-pagination-info">
            {totalCount} {totalCount === 1 ? 'project' : 'projects'}
            <span className="projects-pagination-sep">/</span>
            page {currentPage}
          </span>

          <label className="projects-per-page">
            <select
              value={perPage}
              onChange={(event) => handlePerPageChange(Number(event.target.value))}
            >
              {PER_PAGE_OPTIONS.map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </label>

          <div className="projects-page-nav">
            <button
              type="button"
              className="projects-page-btn"
              disabled={currentPage <= 1}
              onClick={() => setCursorHistory([null])}
              title="First page"
            >
              &#x21E4;
            </button>
            <button
              type="button"
              className="projects-page-btn"
              disabled={currentPage <= 1}
              onClick={() => {
                setCursorHistory((history) => (history.length > 1 ? history.slice(0, -1) : history))
              }}
              title="Previous page"
            >
              &#x25C2;
            </button>
            <button
              type="button"
              className="projects-page-btn"
              disabled={!nextCursor}
              onClick={() => {
                if (!nextCursor) return
                setCursorHistory((history) => [...history, nextCursor])
              }}
              title="Next page"
            >
              &#x25B8;
            </button>
            <button
              type="button"
              className="projects-page-btn"
              disabled
              title="Last page unavailable with cursor pagination"
            >
              &#x21E5;
            </button>
          </div>
        </div>

        <div className="projects-toolbar-actions">
          <select value={sortOrder} onChange={(event) => setSortOrder(event.target.value as ProjectOrder)}>
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
          </select>
        </div>
      </div>

      {selectedTags.length > 0 ? (
        <div className="projects-selected-tags">
          {selectedTags.map((tag) => (
            <button
              key={tag}
              type="button"
              className="project-tag"
              onClick={() => setSelectedTags((current) => current.filter((value) => value !== tag))}
            >
              {tag} ×
            </button>
          ))}
          <button type="button" className="projects-clear-tags" onClick={() => setSelectedTags([])}>
            clear filters
          </button>
        </div>
      ) : null}

      {error ? <div className="projects-status projects-status-error">{error}</div> : null}

      <div className="projects-list-area" ref={listRef}>
        {loading ? (
          <div className="projects-empty-state">Loading projects...</div>
        ) : projects.length === 0 ? (
          <div className="projects-empty-state">
            {selectedTags.length > 0 ? 'No projects match the current filters.' : 'No projects yet.'}
          </div>
        ) : (
          <div className="projects-grid">
            {projects.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                canManage={project.owner_user_id === user?.id}
                showOwner={scope !== 'mine'}
                href={`/projects/${project.id}`}
                onEdit={(target) => {
                  setActiveProject(target)
                  setFormMode('edit')
                }}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>

      {formMode ? (
        <ProjectFormModal
          mode={formMode}
          project={activeProject}
          submitting={submitting}
          error={formError}
          onClose={closeFormModal}
          onSubmit={handleCreateOrEdit}
        />
      ) : null}
    </section>
  )
}
