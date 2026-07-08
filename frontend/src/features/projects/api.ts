import { api } from '../../lib/api'

import type {
  DownloadFilesResponse,
  FileListResponse,
  ManifestListResponse,
  ProjectDetail,
  ProjectListResponse,
  ProjectMutationInput,
  ProjectOrder,
  ProjectScope,
  ProjectSyncResult,
  RunDetail,
  RunManifestListResponse,
  RunListResponse,
  RunMutationInput,
  RunPatchInput,
} from './types'

interface ListProjectsParams {
  scope: ProjectScope
  limit?: number
  cursor?: string | null
  tags?: string[]
  order?: ProjectOrder
}

type TokenGetter = () => Promise<string | null>

export function listProjects({ scope, limit, cursor, tags, order }: ListProjectsParams, _getToken?: TokenGetter) {
  const query = new URLSearchParams({ scope })
  if (limit !== undefined) query.set('limit', String(limit))
  if (cursor) query.set('cursor', cursor)
  if (tags && tags.length > 0) query.set('tags', tags.join(','))
  if (order) query.set('order', order)
  return api.get<ProjectListResponse>(`/api/projects?${query.toString()}`)
}

export function createProject(body: ProjectMutationInput, _getToken?: TokenGetter) {
  return api.post<ProjectDetail>('/api/projects', body)
}

export function getProject(projectId: string, _getToken?: TokenGetter) {
  return api.get<ProjectDetail>(`/api/projects/${projectId}`)
}

export function updateProject(projectId: string, body: Partial<ProjectMutationInput>, _getToken?: TokenGetter) {
  return api.patch<ProjectDetail>(`/api/projects/${projectId}`, body)
}

export function syncProject(projectId: string, _getToken?: TokenGetter) {
  return api.post<ProjectSyncResult>(`/api/projects/${projectId}/sync`, {})
}

export function deleteProject(projectId: string, _getToken?: TokenGetter) {
  return api.delete<void>(`/api/projects/${projectId}`)
}

export function listRuns(projectId: string, _getToken?: TokenGetter) {
  return api.get<RunListResponse>(`/api/projects/${projectId}/runs`)
}

export function createRun(projectId: string, body: RunMutationInput, _getToken?: TokenGetter) {
  return api.post<RunDetail>(`/api/projects/${projectId}/runs`, body)
}

export function updateRun(runId: string, body: RunPatchInput, _getToken?: TokenGetter) {
  return api.patch<RunDetail>(`/api/runs/${runId}`, body)
}

export function deleteRun(runId: string, _getToken?: TokenGetter) {
  return api.delete<void>(`/api/runs/${runId}`)
}

export function getRun(runId: string, _getToken?: TokenGetter) {
  return api.get<RunDetail>(`/api/runs/${runId}`)
}

export function listRunManifests(runId: string, _getToken?: TokenGetter) {
  return api.get<RunManifestListResponse>(`/api/runs/${runId}/manifests`)
}

export function addRunManifest(runId: string, manifestId: string, _getToken?: TokenGetter) {
  return api.post<{ run_id: string; manifest_id: string }>(`/api/runs/${runId}/manifests`, { manifest_id: manifestId })
}

export function removeRunManifest(runId: string, manifestId: string, _getToken?: TokenGetter) {
  return api.delete<void>(`/api/runs/${runId}/manifests/${manifestId}`)
}

export function listProjectFiles(projectId: string, _getToken?: TokenGetter) {
  return api.get<FileListResponse>(`/api/projects/${projectId}/files`)
}

export function listRunFiles(runId: string, _getToken?: TokenGetter) {
  return api.get<FileListResponse>(`/api/runs/${runId}/files`)
}

export function getProjectReadme(projectId: string) {
  return api.get<{ content: string }>(`/api/projects/${projectId}/readme`)
}

export function saveProjectReadmeDirect(projectId: string, content: string, _getToken?: TokenGetter) {
  return api.put<{ content: string }>(`/api/projects/${projectId}/readme`, { content })
}

export function getRunReadme(runId: string) {
  return api.get<{ content: string }>(`/api/runs/${runId}/readme`)
}

export function saveRunReadmeDirect(runId: string, content: string, _getToken?: TokenGetter) {
  return api.put<{ content: string }>(`/api/runs/${runId}/readme`, { content })
}

export function downloadProjectFiles(projectId: string, paths: string[], _getToken?: TokenGetter) {
  return api.post<DownloadFilesResponse>(`/api/projects/${projectId}/files/download`, { paths })
}

export function downloadRunFiles(runId: string, paths: string[], _getToken?: TokenGetter) {
  return api.post<DownloadFilesResponse>(`/api/runs/${runId}/files/download`, { paths })
}

export async function listManifests(_getToken?: TokenGetter, _options?: { scope?: 'all' | 'mine' | 'shared' | 'public'; limit?: number; cursor?: string | null; tags?: string[] }) {
  const query = new URLSearchParams()
  if (_options?.scope) query.set('scope', _options.scope)
  if (_options?.limit !== undefined) query.set('limit', String(_options.limit))
  if (_options?.cursor) query.set('cursor', _options.cursor)
  if (_options?.tags && _options.tags.length > 0) query.set('tags', _options.tags.join(','))
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return api.get<ManifestListResponse>(`/api/manifests${suffix}`)
}
