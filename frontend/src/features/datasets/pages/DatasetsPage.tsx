import { useEffect, useMemo, useRef, useState } from 'react'

import { useAuth } from '../../auth/localAuth'
import { listManifests } from '../../projects/api'
import type { ManifestSummary } from '../../projects/types'
import { deleteManifest, updateManifest, type ManifestPatchInput } from '../api'
import { DatasetCard } from '../DatasetCard'
import { DatasetFormModal } from '../DatasetFormModal'

const PER_PAGE_KEY = 'koyu_datasets_per_page'
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
  for (let i = PER_PAGE_OPTIONS.length - 1; i >= 0; i -= 1) {
    if (PER_PAGE_OPTIONS[i] <= fit) return PER_PAGE_OPTIONS[i]
  }
  return PER_PAGE_OPTIONS[0]
}

export function DatasetsPage() {
  const { getToken } = useAuth()
  const listRef = useRef<HTMLDivElement>(null)
  const latestRequestRef = useRef(0)
  const [manifests, setManifests] = useState<ManifestSummary[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [totalCount, setTotalCount] = useState(0)
  const [cursorHistory, setCursorHistory] = useState<Array<string | null>>([null])
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [tagDraft, setTagDraft] = useState('')
  const [tagMenuOpen, setTagMenuOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [perPage, setPerPage] = useState<number>(() => readPerPage() ?? 10)
  const [autoDetected, setAutoDetected] = useState<boolean>(() => readPerPage() === null)
  const [activeManifest, setActiveManifest] = useState<ManifestSummary | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (!autoDetected || !listRef.current) return
    const h = listRef.current.clientHeight
    if (h > 0) {
      setPerPage(autoPerPage(h))
    }
  }, [autoDetected])

  const currentCursor = cursorHistory[cursorHistory.length - 1] ?? null
  const currentPage = cursorHistory.length

  async function load(cursor: string | null = currentCursor) {
    const requestId = latestRequestRef.current + 1
    latestRequestRef.current = requestId
    setLoading(true)
    setError(null)
    try {
      const response = await listManifests(getToken, {
        scope: 'mine',
        limit: perPage,
        cursor,
        tags: selectedTags,
      })
      if (latestRequestRef.current !== requestId) return
      setManifests(response.manifests)
      setNextCursor(response.next_cursor)
      setTotalCount(response.total_count)
    } catch (loadError) {
      if (latestRequestRef.current !== requestId) return
      setError((loadError as Error).message || 'Failed to load datasets.')
    } finally {
      if (latestRequestRef.current === requestId) {
        setLoading(false)
      }
    }
  }

  useEffect(() => {
    setCursorHistory([null])
  }, [perPage, selectedTags])

  useEffect(() => {
    void load(currentCursor)
  }, [currentCursor, perPage, selectedTags])

  const allTags = useMemo(
    () =>
      Array.from(new Set(manifests.flatMap((manifest) => manifest.tags)))
        .sort((left, right) => left.localeCompare(right)),
    [manifests],
  )

  const filteredTags = useMemo(
    () => allTags.filter((tag) => !selectedTags.includes(tag) && tag.toLowerCase().includes(tagDraft.toLowerCase())),
    [allTags, selectedTags, tagDraft],
  )

  function handlePerPageChange(value: number) {
    setPerPage(value)
    setAutoDetected(false)
    localStorage.setItem(PER_PAGE_KEY, String(value))
  }

  function closeForm() {
    setActiveManifest(null)
    setFormError(null)
    setSubmitting(false)
  }

  async function handleSubmit(values: {
    name: string
    description: string
    type: string
    tags: string
    fps: string
    isPublic: boolean
  }) {
    if (!activeManifest) return

    const name = values.name.trim()
    if (!name) {
      setFormError('Dataset name is required.')
      return
    }

    const trimmedFps = values.fps.trim()
    let fps: number | null | undefined
    if (trimmedFps === '') {
      fps = null
    } else {
      const parsed = Number(trimmedFps)
      if (!Number.isFinite(parsed) || parsed <= 0) {
        setFormError('FPS must be a positive number or blank.')
        return
      }
      fps = parsed
    }

    const tagList = values.tags
      .split(',')
      .map((tag) => tag.trim().toLowerCase())
      .filter(Boolean)

    const payload: ManifestPatchInput = {
      name,
      description: values.description.trim() || null,
      type: values.type,
      tags: tagList,
      is_public: values.isPublic,
      fps,
    }

    setSubmitting(true)
    setFormError(null)
    try {
      await updateManifest(activeManifest.id, payload, getToken)
      closeForm()
      await load(currentCursor)
    } catch (err) {
      setFormError((err as Error).message || 'Unable to save dataset.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(manifest: ManifestSummary) {
    const count = manifest.episode_count
    const episodeLine = count === 0
      ? 'It has no episodes linked.'
      : `Its ${count} ${count === 1 ? 'episode' : 'episodes'} will remain on disk.`
    const confirmed = window.confirm(
      `Delete manifest "${manifest.name}"?\n\n${episodeLine}\nThe manifest JSON and its rollup will be removed.`,
    )
    if (!confirmed) return

    try {
      await deleteManifest(manifest.id, getToken)
      await load(currentCursor)
    } catch (err) {
      setError((err as Error).message || 'Unable to delete dataset.')
    }
  }

  return (
    <section className="projects-page">
      <header className="projects-header">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1>Workspace Datasets</h1>
          <p className="projects-copy">Private and shared datasets in your workspace, ready to open in the viewer.</p>
        </div>
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
            {totalCount} {totalCount === 1 ? 'dataset' : 'datasets'}
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
              «
            </button>
            <button
              type="button"
              className="projects-page-btn"
              disabled={currentPage <= 1}
              onClick={() => setCursorHistory((history) => history.slice(0, -1))}
              title="Previous page"
            >
              ‹
            </button>
            <button
              type="button"
              className="projects-page-btn"
              disabled={!nextCursor}
              onClick={() => nextCursor && setCursorHistory((history) => [...history, nextCursor])}
              title="Next page"
            >
              ›
            </button>
          </div>
        </div>
      </div>

      {selectedTags.length > 0 ? (
        <div className="projects-tag-chip-row">
          {selectedTags.map((tag) => (
            <button
              key={tag}
              type="button"
              className="project-tag active"
              onClick={() => setSelectedTags((current) => current.filter((value) => value !== tag))}
            >
              {tag}
            </button>
          ))}
        </div>
      ) : null}

      {error ? <div className="projects-status projects-status-error">{error}</div> : null}

      <div ref={listRef} className="projects-list-area">
        {loading ? (
          <div className="projects-empty-state">Loading datasets…</div>
        ) : manifests.length === 0 ? (
          <div className="projects-empty-state">No datasets found for the current filter.</div>
        ) : (
          <div className="projects-grid">
            {manifests.map((manifest) => (
              <DatasetCard
                key={manifest.id}
                manifest={manifest}
                onEdit={(target) => setActiveManifest(target)}
                onDelete={(target) => void handleDelete(target)}
              />
            ))}
          </div>
        )}
      </div>

      {activeManifest ? (
        <DatasetFormModal
          manifest={activeManifest}
          submitting={submitting}
          error={formError}
          onClose={closeForm}
          onSubmit={handleSubmit}
        />
      ) : null}
    </section>
  )
}
