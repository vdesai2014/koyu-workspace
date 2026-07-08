import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Button } from '../../../components/ui/Button'
import { Breadcrumbs } from '../../../components/ui/Breadcrumbs'
import { useAuth, useUser } from '../../auth/localAuth'
import { FilesPanel } from '../components/FilesPanel'
import { ManifestLinkPickerModal } from '../components/ManifestLinkPickerModal'
import { MarkdownReadmeEditor } from '../components/MarkdownReadmeEditor'
import { ManifestViewerModal } from '../components/ManifestViewerModal'
import {
  addRunManifest,
  downloadRunFiles,
  getProject,
  getRun,
  getRunReadme,
  listManifests,
  listRunFiles,
  listRunManifests,
  listRuns,
  removeRunManifest,
} from '../api'
import { saveRunReadme } from '../runReadmeSync'
import type { FileListEntry, ManifestSummary, ProjectDetail, RunDetail, RunManifestSummary, RunSummary } from '../types'

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function ManifestAssociationCard({
  manifest,
  canRemove,
  onClick,
  onRemove,
}: {
  manifest: RunManifestSummary
  canRemove: boolean
  onClick?: (manifest: RunManifestSummary) => void
  onRemove?: (manifest: RunManifestSummary) => void
}) {
  return (
    <div className="run-link-card">
      <div className="run-link-card-head">
        <button type="button" className="run-link-card-main" onClick={() => onClick?.(manifest)}>
          <div className="run-link-card-top">
            <span>{manifest.type}</span>
            <code>{manifest.episode_count} episodes</code>
          </div>
          <strong>{manifest.name}</strong>
          <span>{manifest.id}</span>
          {manifest.description ? <small>{manifest.description}</small> : null}
        </button>
        {canRemove ? (
          <button
            type="button"
            className="run-link-remove"
            aria-label="Remove manifest association"
            onClick={() => onRemove?.(manifest)}
          >
            ×
          </button>
        ) : null}
      </div>
    </div>
  )
}

function RunManifestsPanel({
  manifests,
  canAdd,
  canRemove,
  onAdd,
  onManifestClick,
  onRemoveManifest,
  dataTour,
}: {
  manifests: RunManifestSummary[]
  canAdd: boolean
  canRemove: boolean
  onAdd: () => void
  onManifestClick: (manifest: RunManifestSummary) => void
  onRemoveManifest: (manifest: RunManifestSummary) => void
  dataTour?: string
}) {
  return (
    <section className="run-detail-card run-links-panel" data-tour={dataTour}>
      <div className="run-detail-card-header">
        <span>Manifests</span>
        <span className="run-detail-card-header-actions">
          <span>{manifests.length}</span>
          {canAdd ? (
            <button type="button" className="project-inline-action" onClick={onAdd}>
              + manifest
            </button>
          ) : null}
        </span>
      </div>
      {manifests.length === 0 ? (
        <p className="project-detail-empty">No manifests associated yet.</p>
      ) : (
        <div className="run-links-grid">
          {manifests.map((manifest) => (
            <ManifestAssociationCard
              key={manifest.id}
              manifest={manifest}
              canRemove={canRemove}
              onClick={onManifestClick}
              onRemove={onRemoveManifest}
            />
          ))}
        </div>
      )}
    </section>
  )
}

export function RunDetailPage({ workspace }: { workspace: boolean }) {
  const { projectId, runId } = useParams()
  const { getToken } = useAuth()
  const { user } = useUser()

  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [run, setRun] = useState<RunDetail | null>(null)
  const [files, setFiles] = useState<Record<string, FileListEntry>>({})
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [manifests, setManifests] = useState<ManifestSummary[]>([])
  const [associatedManifests, setAssociatedManifests] = useState<RunManifestSummary[]>([])
  const [manifestPickerScope, setManifestPickerScope] = useState<'all' | 'shared'>('all')
  const [readme, setReadme] = useState('')
  const [savedReadme, setSavedReadme] = useState('')
  const [readmeRevision, setReadmeRevision] = useState(0)
  const [readmeState, setReadmeState] = useState<'idle' | 'loading' | 'ready' | 'missing' | 'error'>('idle')
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [linkingManifest, setLinkingManifest] = useState(false)
  const [selectedManifestId, setSelectedManifestId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadRunPage = useCallback(async () => {
    if (!projectId || !runId) {
      setError('Missing run or project id.')
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)

    try {
      const [projectResponse, runResponse, filesResponse, runsResponse, runManifestsResponse] = await Promise.all([
        getProject(projectId, getToken),
        getRun(runId, getToken),
        listRunFiles(runId, getToken),
        listRuns(projectId, getToken),
        listRunManifests(runId, getToken),
      ])

      setProject(projectResponse)
      setRun(runResponse)
      setFiles(filesResponse.files)
      setRuns(runsResponse.runs)
      setAssociatedManifests(runManifestsResponse.manifests)

      if (runResponse.has_readme) {
        setReadmeState('loading')
        const response = await getRunReadme(runId)
        const text = response.content
        setReadme(text)
        setSavedReadme(text)
        setReadmeRevision((revision) => revision + 1)
        setReadmeState('ready')
      } else {
        setReadme('')
        setSavedReadme('')
        setReadmeRevision((revision) => revision + 1)
        setReadmeState('missing')
      }

      setSaveState('idle')
      setSaveError(null)
    } catch (loadError) {
      setError((loadError as Error).message || 'Failed to load run.')
      setReadmeState('error')
    } finally {
      setLoading(false)
    }
  }, [projectId, runId, getToken])

  useEffect(() => {
    void loadRunPage()
  }, [loadRunPage])

  useEffect(() => {
    setLinkingManifest(false)
    setSelectedManifestId(null)
  }, [projectId, runId])

  useEffect(() => {
    let cancelled = false

    async function loadManifestList() {
      try {
        const response = await listManifests(getToken, { scope: manifestPickerScope })
        if (!cancelled) {
          setManifests(response.manifests)
        }
      } catch {
        if (!cancelled) {
          setManifests([])
        }
      }
    }

    void loadManifestList()
    return () => {
      cancelled = true
    }
  }, [getToken, manifestPickerScope])

  const isOwner = project?.owner_user_id === user?.id
  const readmeDirty = useMemo(() => readme !== savedReadme, [readme, savedReadme])
  const parentRun = useMemo(() => runs.find((entry) => entry.id === run?.parent_id) ?? null, [runs, run?.parent_id])
  const childRuns = useMemo(() => runs.filter((entry) => entry.parent_id === run?.id), [runs, run?.id])

  async function handleAddManifestLink(manifest: ManifestSummary) {
    if (!run) return
    const duplicate = associatedManifests.some((entry) => entry.id === manifest.id)
    if (duplicate) {
      setLinkingManifest(false)
      return
    }

    await addRunManifest(run.id, manifest.id, getToken)
    const response = await listRunManifests(run.id, getToken)
    setAssociatedManifests(response.manifests)
    setRun((current) => (
      current
        ? { ...current, manifest_ids: Array.from(new Set([...current.manifest_ids, manifest.id])) }
        : current
    ))
    setLinkingManifest(false)
  }

  async function handleRemoveManifest(manifest: RunManifestSummary) {
    if (!run) return
    await removeRunManifest(run.id, manifest.id, getToken)
    setAssociatedManifests((current) => current.filter((entry) => entry.id !== manifest.id))
    setRun((current) => (
      current
        ? { ...current, manifest_ids: current.manifest_ids.filter((id) => id !== manifest.id) }
        : current
    ))
  }

  function handleManifestClick(manifest: RunManifestSummary) {
    setSelectedManifestId(manifest.id)
  }

  async function handleSaveReadme() {
    if (!run || !isOwner || !readmeDirty) return
    setSaveState('saving')
    setSaveError(null)
    try {
      await saveRunReadme(run.id, readme, getToken)
      setRun((current) => {
        if (!current) return current
        return {
          ...current,
          has_readme: true,
          file_count: current.has_readme ? current.file_count : current.file_count + 1,
        }
      })
      setFiles((current) => ({
        ...current,
        'README.md': {
          size: new TextEncoder().encode(readme).length,
          updated_at: new Date().toISOString(),
          is_readme: true,
        },
      }))
      setSavedReadme(readme)
      setReadmeState('ready')
      setSaveState('saved')
      window.setTimeout(() => {
        setSaveState((current) => (current === 'saved' ? 'idle' : current))
      }, 1800)
    } catch (saveReadmeError) {
      setSaveState('error')
      setSaveError((saveReadmeError as Error).message || 'Failed to save README.md.')
    }
  }

  if (loading) {
    return <section className="projects-empty-state">Loading run…</section>
  }

  if (error || !project || !run) {
    return (
      <section className="project-detail-page">
        <div className="project-detail-shell">
          <div className="projects-status projects-status-error">{error || 'Run not found.'}</div>
          <Link to={workspace ? `/workspace/projects/${projectId}` : `/projects/${projectId}`} className="project-detail-backlink">
            Back to project
          </Link>
        </div>
      </section>
    )
  }

  return (
    <section className="run-detail-page">
      <div className="run-detail-shell">
        <Breadcrumbs crumbs={[
          { label: 'Projects', href: workspace ? '/workspace/projects' : '/projects' },
          { label: project.name, href: workspace ? `/workspace/projects/${project.id}` : `/projects/${project.id}` },
          { label: run.name },
        ]} />

        <header className="run-hero">
          <div className="run-hero-main">
            <p className="eyebrow">Run</p>
            <h1>{run.name}</h1>
          </div>
          <div className="run-hero-meta">
            <span>{run.id}</span>
            <span>created {formatDate(run.created_at)}</span>
            <span>updated {formatDate(run.updated_at)}</span>
            <span>{run.file_count} files</span>
          </div>
          <div className="run-hero-relations">
            <span>{parentRun ? `parent ${parentRun.name}` : 'top level'}</span>
            <span>{childRuns.length} children</span>
          </div>
        </header>

        <div className="run-detail-grid">
          <section className="run-detail-card run-editor-card">
            <MarkdownReadmeEditor
              key={`${run.id}:${readmeRevision}`}
              value={readme}
              editable={Boolean(isOwner)}
              placeholder="README.md will appear here once uploaded."
              onChange={setReadme}
            />

            {saveError ? <div className="projects-status projects-status-error">{saveError}</div> : null}

            <div className="project-readme-footer">
              {isOwner ? (
                <div className="project-readme-actions">
                  <Button
                    type="button"
                    variant="primary"
                    onClick={() => void handleSaveReadme()}
                    disabled={!readmeDirty || saveState === 'saving'}
                  >
                    {saveState === 'saving' ? 'Saving…' : 'Save'}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => setReadme(savedReadme)}
                    disabled={!readmeDirty || saveState === 'saving'}
                  >
                    Revert
                  </Button>
                </div>
              ) : <div />}
              <div className="project-readme-status">
                {saveState === 'saving' ? <span>saving…</span> : null}
                {readmeDirty ? <span>unsaved changes</span> : null}
                {saveState === 'saved' ? <span>saved</span> : null}
              </div>
            </div>
          </section>

          <div className="run-detail-sidebar">
            <section className="run-detail-card">
              <FilesPanel
                entityName={run.name}
                files={files}
                fetchDownloadUrls={(paths, tokenGetter) => downloadRunFiles(run.id, paths, tokenGetter)}
              />
            </section>

            <RunManifestsPanel
              manifests={associatedManifests}
              canAdd={Boolean(isOwner)}
              canRemove={Boolean(isOwner)}
              onAdd={() => setLinkingManifest(true)}
              onManifestClick={handleManifestClick}
              onRemoveManifest={(manifest) => void handleRemoveManifest(manifest)}
              dataTour="run-outputs"
            />
          </div>
        </div>

        {linkingManifest ? (
          <ManifestLinkPickerModal
            manifests={manifests}
            scope={manifestPickerScope}
            onScopeChange={setManifestPickerScope}
            onSelect={(manifest) => void handleAddManifestLink(manifest)}
            onClose={() => setLinkingManifest(false)}
          />
        ) : null}

        {selectedManifestId ? (
          <ManifestViewerModal
            manifestId={selectedManifestId}
            onClose={() => setSelectedManifestId(null)}
          />
        ) : null}
      </div>
    </section>
  )
}
