import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Button } from '../../../components/ui/Button'
import { Breadcrumbs } from '../../../components/ui/Breadcrumbs'
import { useAuth, useUser } from '../../auth/localAuth'
import { startSyncJob } from '../../sync/api'
import type { SyncJobStartResponse, SyncOperation } from '../../sync/types'
import { FilesPanel } from '../components/FilesPanel'
import { MarkdownReadmeEditor } from '../components/MarkdownReadmeEditor'
import { RunsPanel } from '../components/RunsPanel'
import { downloadProjectFiles, getProject, getProjectReadme, listProjectFiles, listRuns } from '../api'
import { saveProjectReadme } from '../readmeSync'
import type { FileListEntry, ProjectDetail, RunSummary } from '../types'

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export function ProjectDetailPage({ workspace }: { workspace: boolean }) {
  const { projectId } = useParams()
  const { getToken } = useAuth()
  const { user } = useUser()
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [files, setFiles] = useState<Record<string, FileListEntry>>({})
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [readme, setReadme] = useState('')
  const [savedReadme, setSavedReadme] = useState('')
  const [readmeRevision, setReadmeRevision] = useState(0)
  const [readmeState, setReadmeState] = useState<'idle' | 'loading' | 'ready' | 'missing' | 'error'>('idle')
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [copiedProjectId, setCopiedProjectId] = useState(false)
  const [syncingOperation, setSyncingOperation] = useState<SyncOperation | null>(null)
  const [syncError, setSyncError] = useState<string | null>(null)
  const [syncJob, setSyncJob] = useState<(SyncJobStartResponse & { operation: SyncOperation }) | null>(null)

  const loadProjectPage = useCallback(async () => {
    if (!projectId) {
      setError('Missing project id.')
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)

    try {
      const currentProjectId = projectId
      const [projectResponse, filesResponse, runsResponse] = await Promise.all([
        getProject(currentProjectId, getToken),
        listProjectFiles(currentProjectId, getToken),
        listRuns(currentProjectId, getToken),
      ])

      setProject(projectResponse)
      setFiles(filesResponse.files)
      setRuns(runsResponse.runs)

      if (projectResponse.has_readme) {
        setReadmeState('loading')
        const response = await getProjectReadme(currentProjectId)
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
      setError((loadError as Error).message || 'Failed to load project.')
      setReadmeState('error')
    } finally {
      setLoading(false)
    }
  }, [projectId, getToken])

  useEffect(() => {
    void loadProjectPage()
  }, [loadProjectPage])

  const isOwner = project?.owner_user_id === user?.id
  const readmeDirty = useMemo(() => readme !== savedReadme, [readme, savedReadme])
  const readmeStatusLabel = useMemo(() => {
    if (saveState === 'saving') return 'saving…'
    if (readmeDirty) return 'unsaved changes'
    return ''
  }, [saveState, readmeDirty])

  async function handleCopyProjectId() {
    if (!project) return
    try {
      await navigator.clipboard.writeText(project.id)
      setCopiedProjectId(true)
      window.setTimeout(() => setCopiedProjectId(false), 1200)
    } catch {
      setCopiedProjectId(false)
    }
  }

  async function handleSaveReadme() {
    if (!project || !isOwner || !readmeDirty) return
    setSaveState('saving')
    setSaveError(null)
    try {
      await saveProjectReadme(project.id, readme, getToken)
      setProject((current) => {
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

  async function handleStartSyncJob(operation: SyncOperation) {
    if (!project || syncingOperation) return
    setSyncingOperation(operation)
    setSyncError(null)
    try {
      const result = await startSyncJob({
        operation,
        entity_type: 'project',
        entity_id: project.id,
      })
      setSyncJob({ ...result, operation })
    } catch (syncProjectError) {
      setSyncError((syncProjectError as Error).message || `Failed to start ${operation} job.`)
      setSyncJob(null)
    } finally {
      setSyncingOperation(null)
    }
  }

  if (loading) {
    return <section className="projects-empty-state">Loading project…</section>
  }

  if (error || !project) {
    return (
      <section className="project-detail-page">
        <div className="project-detail-shell">
          <div className="projects-status projects-status-error">{error || 'Project not found.'}</div>
          <Link to={workspace ? '/workspace/projects' : '/projects'} className="project-detail-backlink">
            Back to projects
          </Link>
        </div>
      </section>
    )
  }

  return (
    <section className="project-detail-page">
      <div className="project-detail-shell">
        <Breadcrumbs crumbs={[
          { label: 'Projects', href: workspace ? '/workspace/projects' : '/projects' },
          { label: project.name },
        ]} />

        <header className="project-hero">
          <p className="project-hero-copy">{project.description || 'No short project description yet.'}</p>

          <div className="project-hero-meta">
            <div className="project-hero-meta-left">
              {workspace ? null : <span>@{project.owner_username}</span>}
              <span className="project-id-meta">
                <span>{project.id}</span>
                <button type="button" className="project-meta-copy" onClick={handleCopyProjectId} aria-label="Copy project id">
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <rect x="5" y="5" width="8" height="8" />
                    <path d="M3 11V3h8" />
                  </svg>
                </button>
                {copiedProjectId ? <span className="project-meta-copy-state">copied</span> : null}
              </span>
              {project.cloned_source_project_id ? (
                <Link className="project-lineage-link" to={`/projects/${project.cloned_source_project_id}`}>
                  cloned from {project.cloned_source_project_id.slice(0, 13)}
                </Link>
              ) : null}
            </div>
            <div className="project-hero-meta-right">
              <span>{project.is_public ? 'Public' : 'Private'}</span>
              <span>{runs.length} runs</span>
              <span>{project.file_count} files</span>
              <span>updated {formatDate(project.updated_at)}</span>
            </div>
          </div>

          <div className="project-hero-tags">
            {project.tags.length > 0 ? (
              project.tags.map((tag) => <span key={tag} className="project-tag">{tag}</span>)
            ) : (
              <span className="project-tag project-tag-muted">untagged</span>
            )}
          </div>

          <div className="project-sync-row">
            <Button type="button" variant="secondary" onClick={() => void handleStartSyncJob('push')} disabled={Boolean(syncingOperation)}>
              {syncingOperation === 'push' ? (
                <span className="button-spinner-wrap">
                  <span className="button-spinner" aria-hidden="true" />
                  <span>Submitting Push…</span>
                </span>
              ) : 'Push'}
            </Button>
            <Button type="button" variant="ghost" onClick={() => void handleStartSyncJob('pull')} disabled={Boolean(syncingOperation)}>
              {syncingOperation === 'pull' ? (
                <span className="button-spinner-wrap">
                  <span className="button-spinner" aria-hidden="true" />
                  <span>Submitting Pull…</span>
                </span>
              ) : 'Pull'}
            </Button>
            {syncError ? <div className="projects-status projects-status-error">{syncError}</div> : null}
            {syncJob ? (
              <div className="projects-status">
                {syncJob.operation} job submitted: <Link to={`/sync?job=${syncJob.job_id}`}>{syncJob.job_id}</Link>. Check the <Link to="/sync">sync jobs page</Link> for status.
              </div>
            ) : null}
          </div>
        </header>

        <RunsPanel projectId={project.id} runs={runs} isOwner={isOwner} onRunsChanged={loadProjectPage} workspace={workspace} />

        <FilesPanel
          entityName={project.name}
          files={files}
          fetchDownloadUrls={(paths, getToken) => downloadProjectFiles(project.id, paths, getToken)}
        />

        <section className="project-readme-panel">
          <MarkdownReadmeEditor
            key={`${project.id}:${readmeRevision}`}
            value={readme}
            editable={Boolean(isOwner)}
            placeholder="README.md will appear here once uploaded."
            onChange={setReadme}
          />

          {saveError ? <div className="projects-status projects-status-error">{saveError}</div> : null}

          <div className="project-readme-footer">
            {isOwner ? (
              <div className="project-readme-actions">
                <Button type="button" variant="primary" onClick={() => void handleSaveReadme()} disabled={!readmeDirty || saveState === 'saving'}>
                  {saveState === 'saving' ? 'Saving…' : 'Save'}
                </Button>
                <Button type="button" variant="ghost" onClick={() => setReadme(savedReadme)} disabled={!readmeDirty || saveState === 'saving'}>
                  Revert
                </Button>
              </div>
            ) : <div />}
            <div className="project-readme-status">
              {readmeStatusLabel ? <span>{readmeStatusLabel}</span> : null}
              {saveState === 'saved' ? <span>saved</span> : null}
            </div>
          </div>
        </section>
      </div>
    </section>
  )
}
