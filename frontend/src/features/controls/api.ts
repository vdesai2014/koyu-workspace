import { natsRequest } from '../../lib/useBridge'

export interface RecordingContext {
  manifest_id: string | null
  manifest_name: string | null
  manifest_type: string | null
  task: string | null
  task_description: string | null
  source_project_id: string | null
  source_run_id: string | null
  source_checkpoint: string | null
  policy_name: string | null
  fps: number | null
  updated_at: string | null
  updated_by: string | null
  timestamp?: string | null
}

export interface RecordingContextInput {
  manifest_id?: string | null
  manifest_name?: string | null
  manifest_type?: string | null
  task?: string | null
  task_description?: string | null
  source_project_id?: string | null
  source_run_id?: string | null
  source_checkpoint?: string | null
  policy_name?: string | null
  fps?: number | null
  updated_by?: string | null
}

export function getRecordingContext() {
  return natsRequest<RecordingContext>('provenance.get', {})
}

export function putRecordingContext(body: RecordingContextInput) {
  return natsRequest<RecordingContext>('provenance.override.set', body)
}

export function clearRecordingContextOverrides() {
  return natsRequest<RecordingContext>('provenance.override.clear', {})
}
