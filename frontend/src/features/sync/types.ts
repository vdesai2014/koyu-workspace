export type SyncOperation = 'push' | 'pull' | 'clone'
export type SyncEntityType = 'project' | 'run' | 'manifest'

export interface SyncJobRequest {
  operation: SyncOperation
  entity_type: SyncEntityType
  entity_id: string
  include_manifests?: boolean
  include_descendants?: boolean
}

export interface SyncJobStartResponse {
  job_id: string
  path: string
  status_url: string
}

export interface SyncJobEvent {
  t: number
  phase: string
  status: string
  message?: string
  operation?: string
  entity_type?: string
  entity_id?: string
  path?: string
  size?: number
  [key: string]: unknown
}

export interface SyncJobPayload {
  job_id: string
  status: string
  request: SyncJobRequest & { dry_run?: boolean }
  created_at: number
  updated_at: number
  plan: {
    created_at: number
    summary: Record<string, number>
    scope: Record<string, unknown>
    warnings: string[]
    id_remaps: Record<string, Record<string, string>>
    required_id_remaps: Record<string, string[]>
  } | null
  execute: {
    started_at: number | null
    updated_at: number | null
    events: SyncJobEvent[]
    counters: {
      metadata_done: number
      files_done: number
      bytes_done: number
      associations_done: number
    }
  }
  result: Record<string, unknown> | null
  error: string | null
}

export interface SyncJobListResponse {
  jobs: SyncJobPayload[]
}
