import { api } from '../../lib/api'

import type { SyncJobListResponse, SyncJobPayload, SyncJobRequest, SyncJobStartResponse } from './types'

export function startSyncJob(body: SyncJobRequest) {
  return api.post<SyncJobStartResponse>('/api/sync/jobs', body)
}

export function listSyncJobs(limit = 50) {
  return api.get<SyncJobListResponse>(`/api/sync/jobs?limit=${limit}`)
}

export function getSyncJob(jobId: string) {
  return api.get<SyncJobPayload>(`/api/sync/jobs/${jobId}`)
}

export function deleteSyncJob(jobId: string) {
  return api.delete<void>(`/api/sync/jobs/${jobId}`)
}
