import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { deleteSyncJob, listSyncJobs } from '../api'
import type { SyncJobEvent, SyncJobPayload } from '../types'

function formatTime(value?: number | null) {
  if (!value) return 'not started'
  return new Date(value * 1000).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let scaled = value / 1024
  let unit = units[0]
  for (let index = 1; index < units.length && scaled >= 1024; index += 1) {
    scaled /= 1024
    unit = units[index]
  }
  return `${scaled.toFixed(scaled >= 10 ? 1 : 2)} ${unit}`
}

function eventLabel(event: SyncJobEvent) {
  return [
    event.phase,
    event.status,
    event.message,
    event.path,
  ].filter(Boolean).join(' / ')
}

function statusClass(status: string) {
  if (status === 'succeeded') return 'sync-status-succeeded'
  if (status === 'failed') return 'sync-status-failed'
  if (status === 'running' || status === 'planning' || status === 'planned') return 'sync-status-running'
  return ''
}

function canDeleteJob(status: string) {
  return status === 'succeeded' || status === 'failed'
}

function JobCard({ job, selected }: { job: SyncJobPayload; selected: boolean }) {
  return (
    <Link className={`sync-job-card ${selected ? 'selected' : ''}`} to={`/sync?job=${job.job_id}`}>
      <div className="sync-job-card-top">
        <span className={`sync-job-status ${statusClass(job.status)}`}>{job.status}</span>
        <span>{formatTime(job.updated_at)}</span>
      </div>
      <strong>{job.request.operation} {job.request.entity_type}</strong>
      <code>{job.request.entity_id}</code>
    </Link>
  )
}

function JobDetail({ deleting, job, onDelete }: { deleting: boolean; job: SyncJobPayload; onDelete: (jobId: string) => void }) {
  const events = job.execute.events.slice(-12).reverse()
  const summary = job.plan?.summary

  return (
    <section className="sync-detail-panel">
      <div className="sync-detail-header">
        <div>
          <p className="eyebrow">Sync Job</p>
          <h1>{job.request.operation} {job.request.entity_type}</h1>
          <code>{job.job_id}</code>
        </div>
        <div className="sync-detail-actions">
          <span className={`sync-job-status sync-job-status-large ${statusClass(job.status)}`}>{job.status}</span>
          {canDeleteJob(job.status) ? (
            <button
              type="button"
              className="sync-delete-button"
              disabled={deleting}
              onClick={() => onDelete(job.job_id)}
            >
              {deleting ? 'Deleting…' : 'Delete job'}
            </button>
          ) : null}
        </div>
      </div>

      <div className="sync-detail-grid">
        <div>
          <span>entity</span>
          <strong>{job.request.entity_id}</strong>
        </div>
        <div>
          <span>updated</span>
          <strong>{formatTime(job.updated_at)}</strong>
        </div>
        <div>
          <span>files</span>
          <strong>{job.execute.counters.files_done}</strong>
        </div>
        <div>
          <span>bytes</span>
          <strong>{formatBytes(job.execute.counters.bytes_done)}</strong>
        </div>
      </div>

      {summary ? (
        <div className="sync-summary-row">
          {Object.entries(summary).map(([key, value]) => (
            <div key={key} className="sync-summary-pill">
              <span>{key.replace(/_/g, ' ')}</span>
              <strong>{typeof value === 'number' && key.includes('bytes') ? formatBytes(value) : value}</strong>
            </div>
          ))}
        </div>
      ) : (
        <div className="projects-status">No plan has been written yet.</div>
      )}

      {job.error ? <div className="projects-status projects-status-error">{job.error}</div> : null}

      <section className="sync-events-panel">
        <h2>Recent Events</h2>
        {events.length > 0 ? (
          <ul className="sync-events-list">
            {events.map((event, index) => (
              <li key={`${event.t}-${index}`}>
                <span>{formatTime(event.t)}</span>
                <strong>{eventLabel(event)}</strong>
              </li>
            ))}
          </ul>
        ) : (
          <div className="projects-status">No execution events yet.</div>
        )}
      </section>

      <details className="sync-json-panel">
        <summary>Raw JSON</summary>
        <pre>{JSON.stringify(job, null, 2)}</pre>
      </details>
    </section>
  )
}

export function SyncJobsPage() {
  const [searchParams] = useSearchParams()
  const selectedJobId = searchParams.get('job')
  const [jobs, setJobs] = useState<SyncJobPayload[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const response = await listSyncJobs(100)
      setJobs(response.jobs)
      setError(null)
    } catch (refreshError) {
      setError((refreshError as Error).message || 'Failed to load sync jobs.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
    const interval = window.setInterval(() => void refresh(), 1000)
    return () => window.clearInterval(interval)
  }, [refresh])

  const selectedJob = useMemo(() => {
    return jobs.find((job) => job.job_id === selectedJobId) ?? jobs[0] ?? null
  }, [jobs, selectedJobId])

  const handleDeleteJob = useCallback(async (jobId: string) => {
    setDeletingJobId(jobId)
    try {
      await deleteSyncJob(jobId)
      setJobs((current) => current.filter((job) => job.job_id !== jobId))
      setError(null)
    } catch (deleteError) {
      setError((deleteError as Error).message || 'Failed to delete sync job.')
    } finally {
      setDeletingJobId(null)
    }
  }, [])

  if (loading) {
    return <section className="projects-empty-state">Loading sync jobs…</section>
  }

  return (
    <section className="sync-page">
      <div className="sync-page-header">
        <p className="eyebrow">Push / Pull</p>
        <h1>Sync jobs</h1>
        <p>Passive progress from local `.koyu/run/sync/*.json` job files.</p>
      </div>

      {error ? <div className="projects-status projects-status-error">{error}</div> : null}

      {jobs.length === 0 ? (
        <div className="projects-empty-state">No sync jobs yet. Start a push or pull from a project page.</div>
      ) : (
        <div className="sync-layout">
          <aside className="sync-job-list">
            {jobs.map((job) => (
              <JobCard key={job.job_id} job={job} selected={job.job_id === selectedJob?.job_id} />
            ))}
          </aside>
          {selectedJob ? (
            <JobDetail
              deleting={deletingJobId === selectedJob.job_id}
              job={selectedJob}
              onDelete={(jobId) => void handleDeleteJob(jobId)}
            />
          ) : null}
        </div>
      )}
    </section>
  )
}
