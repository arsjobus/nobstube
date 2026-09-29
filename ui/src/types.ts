export interface Video {
  source: string
  source_id: string
  title: string
  url: string
  channel: string
  description: string
  duration_seconds: number | null
  duration_label: string
  published_at: string | null
  thumbnail_url: string
  view_count: number | null
  views_label: string
  embed_url: string
  playable_url: string
  tags: string[]
  score: number
}

export interface SearchResults {
  videos: Video[]
  query: string
  sort: string
  page: number
  pages: number
  total: number
  candidates_per_source: number
}

export interface AppConfig {
  rules: { exclusions: Record<string, unknown[]>; preferences: Record<string, unknown[]>; settings: Record<string, unknown> }
  candidate_options: number[]
  default_candidates_per_source: number
  sort_options: string[]
}
