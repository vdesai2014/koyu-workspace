import { useMemo, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '../../../components/ui/Button'
import { Modal } from '../../../components/ui/Modal'
import { createRun, deleteRun, updateRun } from '../api'
import { buildRunTree, countRunDescendants, type RunTreeNode } from '../runTree'
import type { RunSummary } from '../types'
import { usePanelOpen, useScrollRestore, useTreeExpanded } from '../usePanelState'

interface RunsPanelProps {
  projectId: string
  runs: RunSummary[]
  isOwner: boolean
  onRunsChanged: () => Promise<void>
  workspace?: boolean
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function flattenRuns(nodes: RunTreeNode[]): RunSummary[] {
  return nodes.flatMap((node) => [node, ...flattenRuns(node.children)])
}

function RunTreeList({
  nodes,
  editable,
  expanded,
  onToggle,
  onEdit,
  onDelete,
  projectId,
  workspace,
}: {
  nodes: RunTreeNode[]
  editable: boolean
  expanded: Set<string>
  onToggle: (path: string) => void
  onEdit: (run: RunSummary) => void
  onDelete: (run: RunSummary) => void
  projectId: string
  workspace: boolean
}) {
  return (
    <ul className="project-run-tree">
      {nodes.map((node) => {
        const hasChildren = node.children.length > 0
        const open = hasChildren && expanded.has(node.id)
        const descendantCount = countRunDescendants(node)

        return (
          <li key={node.id}>
            <div className={`project-run-node${hasChildren ? ' project-run-node-folder' : ''}`}>
              <div className="project-run-node-main">
                {hasChildren ? (
                  <span className="project-run-node-glyph" aria-hidden="true" onClick={() => onToggle(node.id)}>
                    {open ? '▾' : '▸'}
                  </span>
                ) : (
                  <span className="project-run-node-glyph" aria-hidden="true">·</span>
                )}
                <Link
                  to={workspace ? `/workspace/projects/${projectId}/runs/${node.id}` : `/projects/${projectId}/runs/${node.id}`}
                  className="project-run-link"
                >
                  <strong>{node.name}</strong>
                </Link>
                {descendantCount > 0 ? <span className="project-run-node-count">{descendantCount}</span> : null}
              </div>

              <div className="project-run-node-meta">
                <time>{formatDate(node.updated_at)}</time>
                {editable ? (
                  <div className="project-run-actions">
                    <button type="button" className="project-card-icon-button" aria-label="Edit run" onClick={() => onEdit(node)}>
                      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path d="M3 11.5 11.8 2.7l1.5 1.5L4.5 13H3z" />
                        <path d="M10.9 3.6 12.4 5.1" />
                      </svg>
                    </button>
                    <button
                      type="button"
                      className="project-card-icon-button project-card-icon-danger"
                      aria-label="Delete run"
                      onClick={() => onDelete(node)}
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
            </div>

            {hasChildren && open ? (
              <RunTreeList
                nodes={node.children}
                editable={editable}
                expanded={expanded}
                onToggle={onToggle}
                onEdit={onEdit}
                onDelete={onDelete}
                projectId={projectId}
                workspace={workspace}
              />
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}

function RunFormModal({
  title,
  runs,
  initialRun,
  onClose,
  onSubmit,
}: {
  title: string
  runs: RunSummary[]
  initialRun?: RunSummary | null
  onClose: () => void
  onSubmit: (body: { name: string; parent_id: string | null }) => Promise<void>
}) {
  const [name, setName] = useState(initialRun?.name ?? '')
  const [parentId, setParentId] = useState(initialRun?.parent_id ?? '')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      setError('Run name is required.')
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      await onSubmit({ name: trimmed, parent_id: parentId || null })
      onClose()
    } catch (submitError) {
      setError((submitError as Error).message || 'Unable to save run.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal title={title} onClose={onClose}>
      <form className="project-form" onSubmit={handleSubmit}>
        <label>
          <span>Name</span>
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="train-v1" />
        </label>

        <label>
          <span>Parent Run</span>
          <select value={parentId} onChange={(event) => setParentId(event.target.value)}>
            <option value="">Top level</option>
            {runs.filter((run) => run.id !== initialRun?.id).map((run) => (
              <option key={run.id} value={run.id}>{run.name}</option>
            ))}
          </select>
        </label>

        {error ? <div className="project-form-error">{error}</div> : null}

        <div className="project-form-actions">
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? 'Saving...' : 'Save Run'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

export function RunsPanel({ projectId, runs, isOwner, onRunsChanged, workspace = false }: RunsPanelProps) {
  const runTree = useMemo(() => buildRunTree(runs), [runs])
  const flatRuns = useMemo(() => flattenRuns(runTree), [runTree])
  const [creating, setCreating] = useState(false)
  const [editingRun, setEditingRun] = useState<RunSummary | null>(null)
  const { isOpen: panelOpen, handleToggle: handlePanelToggle } = usePanelOpen(`runs_${projectId}`)
  const { expanded, toggle } = useTreeExpanded(`runs_${projectId}`)
  const scrollRef = useScrollRestore(`runs_${projectId}`)

  async function handleCreateRun(body: { name: string; parent_id: string | null }) {
    await createRun(projectId, body)
    await onRunsChanged()
  }

  async function handleUpdateRun(body: { name: string; parent_id: string | null }) {
    if (!editingRun) return
    await updateRun(editingRun.id, body)
    await onRunsChanged()
  }

  async function handleDeleteRun(run: RunSummary) {
    const confirmed = window.confirm(`Delete run "${run.name}" and its subtree?`)
    if (!confirmed) return
    await deleteRun(run.id)
    await onRunsChanged()
  }

  return (
    <>
      <details className="project-detail-panel" open={panelOpen} onToggle={handlePanelToggle}>
        <summary>
          <span>Runs</span>
          <span className="project-panel-summary-right">
            <span>{runs.length}</span>
            {isOwner ? (
              <button
                type="button"
                className="project-inline-action"
                onClick={(event) => {
                  event.preventDefault()
                  setCreating(true)
                }}
              >
                + new run
              </button>
            ) : null}
          </span>
        </summary>

        <div className="project-detail-panel-body">
          <div className="project-run-tree-scroll" ref={scrollRef}>
            {runTree.length === 0 ? (
              <p className="project-detail-empty">No runs yet.</p>
            ) : (
              <RunTreeList
                nodes={runTree}
                editable={isOwner}
                expanded={expanded}
                onToggle={toggle}
                onEdit={setEditingRun}
                onDelete={handleDeleteRun}
                projectId={projectId}
                workspace={workspace}
              />
            )}
          </div>
        </div>
      </details>

      {creating ? (
        <RunFormModal
          title="Create Run"
          runs={flatRuns}
          onClose={() => setCreating(false)}
          onSubmit={handleCreateRun}
        />
      ) : null}

      {editingRun ? (
        <RunFormModal
          title="Edit Run"
          runs={flatRuns}
          initialRun={editingRun}
          onClose={() => setEditingRun(null)}
          onSubmit={handleUpdateRun}
        />
      ) : null}
    </>
  )
}
