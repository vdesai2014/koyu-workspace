import { useEffect, useState, type FormEvent } from 'react'

import { Button } from '../../components/ui/Button'
import { Modal } from '../../components/ui/Modal'
import type { ManifestSummary } from '../projects/types'

const MANIFEST_TYPES = ['teleop', 'eval', 'intervention', 'synthetic'] as const

interface DatasetFormValues {
  name: string
  description: string
  type: string
  tags: string
  fps: string
  isPublic: boolean
}

interface DatasetFormModalProps {
  manifest: ManifestSummary
  submitting: boolean
  error: string | null
  onClose: () => void
  onSubmit: (values: DatasetFormValues) => Promise<void>
}

function buildInitialValues(manifest: ManifestSummary): DatasetFormValues {
  return {
    name: manifest.name,
    description: manifest.description ?? '',
    type: manifest.type,
    tags: manifest.tags.join(', '),
    fps: manifest.fps != null ? String(manifest.fps) : '',
    isPublic: manifest.is_public,
  }
}

export function DatasetFormModal({
  manifest,
  submitting,
  error,
  onClose,
  onSubmit,
}: DatasetFormModalProps) {
  const [values, setValues] = useState<DatasetFormValues>(() => buildInitialValues(manifest))

  useEffect(() => {
    setValues(buildInitialValues(manifest))
  }, [manifest])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await onSubmit(values)
  }

  return (
    <Modal title="Edit Dataset" onClose={onClose}>
      <form className="project-form" onSubmit={handleSubmit}>
        <label>
          <span>Name</span>
          <input
            value={values.name}
            onChange={(event) => setValues((current) => ({ ...current, name: event.target.value }))}
            placeholder="eval-policy-a-20260420"
            maxLength={120}
          />
        </label>

        <label>
          <span>Description</span>
          <textarea
            value={values.description}
            onChange={(event) => setValues((current) => ({ ...current, description: event.target.value }))}
            placeholder="Short blurb for dataset cards."
            rows={3}
            maxLength={400}
          />
        </label>

        <label>
          <span>Type</span>
          <select
            value={values.type}
            onChange={(event) => setValues((current) => ({ ...current, type: event.target.value }))}
          >
            {MANIFEST_TYPES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
            {!MANIFEST_TYPES.includes(values.type as typeof MANIFEST_TYPES[number]) ? (
              <option value={values.type}>{values.type}</option>
            ) : null}
          </select>
        </label>

        <label>
          <span>Tags</span>
          <input
            value={values.tags}
            onChange={(event) => setValues((current) => ({ ...current, tags: event.target.value }))}
            placeholder="grasp, sim, act-ppo"
          />
          <small>Comma-separated. Tags are normalized to lowercase.</small>
        </label>

        <label>
          <span>FPS</span>
          <input
            value={values.fps}
            onChange={(event) => setValues((current) => ({ ...current, fps: event.target.value }))}
            placeholder="30"
            inputMode="numeric"
          />
          <small>Leave blank to leave unset.</small>
        </label>

        <label className="project-form-checkbox">
          <input
            type="checkbox"
            checked={values.isPublic}
            onChange={(event) => setValues((current) => ({ ...current, isPublic: event.target.checked }))}
          />
          <span>Visible on the public datasets page</span>
        </label>

        {error ? <div className="project-form-error">{error}</div> : null}

        <div className="project-form-actions">
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? 'Saving...' : 'Save Changes'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
