export interface DatasetFeatureSpec {
  dtype?: string
  shape?: number[]
  names?: string[]
}

export interface DatasetManifestDetail {
  id: string
  owner_user_id: string
  name: string
  description: string | null
  type: string
  tags: string[]
  is_public: boolean
  fps: number | null
  encoding: Record<string, unknown>
  features: Record<string, DatasetFeatureSpec>
  run_ids: string[]
  success_rate: number | null
  rated_episodes: number
  episode_count: number
  created_at: string
  updated_at: string
}

export interface DatasetManifestRunSummary {
  id: string
  project_id: string
  parent_id: string | null
  name: string
  created_at: string
  updated_at: string
}

export interface DatasetManifestRunListResponse {
  runs: DatasetManifestRunSummary[]
}

export interface DatasetEpisodeSummary {
  id: string
  length: number
  task: string | null
  task_description: string | null
  collection_mode: string | null
  source_project_id: string | null
  source_run_id: string | null
  source_checkpoint: string | null
  policy_name: string | null
  reward: number | null
  features: Record<string, DatasetFeatureSpec>
  size_bytes: number
  created_at: string
}

export interface DatasetEpisodePage {
  episodes: DatasetEpisodeSummary[]
  next_cursor: string | null
}

export interface DatasetEpisodeDetail {
  id: string
  length: number
  task: string | null
  task_description: string | null
  collection_mode: string | null
  source_project_id: string | null
  source_run_id: string | null
  source_checkpoint: string | null
  policy_name: string | null
  reward: number | null
  features: Record<string, DatasetFeatureSpec>
  files: Record<string, { url: string; size: number }>
  created_at: string
}

export interface ParsedSeries {
  key: string
  names: string[]
  rows: number[][]
}

export interface ParsedEpisodeData {
  frameIndices: number[]
  timestamps: number[]
  series: ParsedSeries[]
}
