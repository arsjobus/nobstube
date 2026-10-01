import type { AppConfig, SearchResults, Video } from './types'

const base = import.meta.env.VITE_API_BASE_URL ?? ''

async function request<T>(path: string, method = 'GET'): Promise<T> {
  const response = await fetch(`${base}${path}`, { method })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? 'The API request failed.')
  return response.json() as Promise<T>
}

export const getConfig = () => request<AppConfig>('/api/config')
export const searchVideos = (q: string, sort: string, page: number, count: number) => {
  const params = new URLSearchParams({ q, sort, page: String(page), candidates_per_source: String(count) })
  return request<SearchResults>(`/api/search?${params}`)
}
export const getVideo = (source: string, sourceId: string) => request<Video>(`/api/watch/${encodeURIComponent(source)}/${sourceId.split('/').map(encodeURIComponent).join('/')}`)
export const getBookmarks = (page: number) => request<SearchResults>(`/api/bookmarks?page=${page}`)
export const setBookmark = (source: string, sourceId: string, bookmarked: boolean) => request<{ bookmarked: boolean }>(`/api/bookmarks/${encodeURIComponent(source)}/${sourceId.split('/').map(encodeURIComponent).join('/')}`, bookmarked ? 'PUT' : 'DELETE')
