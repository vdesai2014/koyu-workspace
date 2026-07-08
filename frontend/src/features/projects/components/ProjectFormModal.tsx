import { useEffect, useState, type FormEvent } from 'react'

import { Button } from '../../../components/ui/Button'
import { Modal } from '../../../components/ui/Modal'
import type { ProjectSummary } from '../types'

interface ProjectFormValues {
  name: string
  description: string
  tags: string
  isPublic: boolean
}

interface ProjectFormModalProps {
  mode: 'create' | 'edit'
  project?: ProjectSummary
  submitting: boolean
  error: string | null
  onClose: () => void
  onSubmit: (values: ProjectFormValues) => Promise<void>
}

function buildInitialValues(project?: ProjectSummary): ProjectFormValues {
  return {
    name: project?.name ?? '',
    description: project?.description ?? '',
    tags: project?.tags.join(', ') ?? '',
    isPublic: project?.is_public ?? false,
  }
}

export function ProjectFormModal({
  mode,
  project,
  submitting,
  error,
  onClose,
  onSubmit,
}: ProjectFormModalProps) {
  const [values, setValues] = useState<ProjectFormValues>(() => buildInitialValues(project))

  useEffect(() => {
    setValues(buildInitialValues(project))
  }, [project])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await onSubmit(values)
  }

  return (
    <Modal title={mode === 'create' ? 'Create Project' : 'Edit Project'} onClose={onClose}>
      <form className="project-form" onSubmit={handleSubmit}>
        <label>
          <span>Name</span>
          <input
            value={values.name}
            onChange={(event) => setValues((current) => ({ ...current, name: event.target.value }))}
            placeholder="pi-zero-folding"
            maxLength={120}
          />
        </label>

        <label>
          <span>Description</span>
          <textarea
            value={values.description}
            onChange={(event) => setValues((current) => ({ ...current, description: event.target.value }))}
            placeholder="Short blurb for project cards."
            rows={4}
            maxLength={400}
          />
        </label>

        <label>
          <span>Tags</span>
          <input
            value={values.tags}
            onChange={(event) => setValues((current) => ({ ...current, tags: event.target.value }))}
            placeholder="manipulation, cloth, sim2real"
          />
          <small>Comma-separated. Tags are normalized to lowercase.</small>
        </label>

        <label className="project-form-checkbox">
          <input
            type="checkbox"
            checked={values.isPublic}
            onChange={(event) => setValues((current) => ({ ...current, isPublic: event.target.checked }))}
          />
          <span>Visible on the public projects page</span>
        </label>

        {error ? <div className="project-form-error">{error}</div> : null}

        <div className="project-form-actions">
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? 'Saving...' : mode === 'create' ? 'Create Project' : 'Save Changes'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
