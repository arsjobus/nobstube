<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getBookmarks, getConfig, getVideo, searchVideos, setBookmark } from './api'
import type { AppConfig, SearchResults, Video } from './types'

const route = useRoute()
const router = useRouter()
const query = ref(String(route.query.q ?? ''))
const sort = ref(String(route.query.sort ?? 'relevance'))
const page = ref(Number(route.query.page ?? 1))
const candidateCount = ref(Number(route.query.candidates_per_source ?? 10))
const config = ref<AppConfig | null>(null)
const searchResults = ref<SearchResults | null>(null)
const bookmarkResults = ref<SearchResults | null>(null)
const results = computed(() => routeView.value === 'bookmarks' ? bookmarkResults.value : searchResults.value)
const video = ref<Video | null>(null)
const player = ref<HTMLVideoElement | null>(null)
const loading = ref(false)
const error = ref('')
const routeView = computed(() => route.path === '/rules' ? 'rules' : route.path === '/bookmarks' ? 'bookmarks' : route.path.startsWith('/watch/') ? 'watch' : 'search')
const busyLabel = computed(() => routeView.value === 'watch' ? 'Loading video…' : 'Removing the bullsh*t…')

async function loadSearch(nextPage = 1, updateUrl = true) {
  page.value = nextPage
  loading.value = true
  error.value = ''
  if (updateUrl) await router.push({ path: '/', query: { q: query.value.trim() || undefined, sort: sort.value, page: nextPage, candidates_per_source: candidateCount.value } })
  try {
    searchResults.value = await searchVideos(query.value, sort.value, nextPage, candidateCount.value)
    page.value = searchResults.value.page
  } catch (e) { error.value = e instanceof Error ? e.message : 'Search failed.' }
  finally { loading.value = false }
}
async function loadBookmarks(nextPage = 1) {
  page.value = nextPage
  loading.value = true; error.value = ''
  if (route.query.page !== String(nextPage)) await router.replace({ path: '/bookmarks', query: nextPage > 1 ? { page: String(nextPage) } : {} })
  try { bookmarkResults.value = await getBookmarks(nextPage); page.value = bookmarkResults.value.page }
  catch (e) { error.value = e instanceof Error ? e.message : 'Unable to load bookmarks.' }
  finally { loading.value = false }
}
async function toggleBookmark(item: Video) {
  try {
    const result = await setBookmark(item.source, item.source_id, !item.is_bookmarked)
    item.is_bookmarked = result.bookmarked
    if (video.value?.source === item.source && video.value.source_id === item.source_id) video.value.is_bookmarked = result.bookmarked
    if (routeView.value === 'bookmarks' && !result.bookmarked) await loadBookmarks(page.value)
  } catch (e) { error.value = e instanceof Error ? e.message : 'Unable to update bookmark.' }
}

async function openVideo(item: Video) {
  await router.push(`/watch/${encodeURIComponent(item.source)}/${item.source_id.split('/').map(encodeURIComponent).join('/')}`)
}
function closeVideo() {
  player.value?.pause()
  video.value = null
  if (window.history.state?.back) router.back()
  else void router.replace('/')
}
async function loadCurrentVideo() {
  loading.value = true; error.value = ''; video.value = null
  try { video.value = await getVideo(String(route.params.source), String(route.params.sourceId)) }
  catch (e) { error.value = e instanceof Error ? e.message : 'Unable to load this video.' }
  finally { loading.value = false }
}
function handleKey(event: KeyboardEvent) {
  if (event.key === 'Escape' && routeView.value === 'watch') {
    event.preventDefault()
    closeVideo()
  }
  if (event.key === '/' && !(document.activeElement instanceof HTMLInputElement) && routeView.value === 'search') {
    event.preventDefault(); document.querySelector<HTMLInputElement>('#search-input')?.focus()
  }
  if (routeView.value === 'search' && !loading.value && event.key === 'ArrowLeft' && page.value > 1) void loadSearch(page.value - 1)
  if (routeView.value === 'search' && !loading.value && event.key === 'ArrowRight' && results.value && page.value < results.value.pages) void loadSearch(page.value + 1)
}

watch(() => route.fullPath, async () => {
  query.value = String(route.query.q ?? query.value)
  sort.value = String(route.query.sort ?? sort.value)
  if (routeView.value === 'search') {
    if (route.query.q === undefined) page.value = searchResults.value?.page ?? 1
    if (!loading.value && route.query.q !== undefined && (!results.value || results.value.query !== route.query.q || page.value !== Number(route.query.page ?? 1))) {
      page.value = Number(route.query.page ?? 1); candidateCount.value = Number(route.query.candidates_per_source ?? candidateCount.value); await loadSearch(page.value, false)
    }
  } else if (routeView.value === 'watch') {
    await loadCurrentVideo()
  } else if (routeView.value === 'bookmarks' && !loading.value) {
    await loadBookmarks(Number(route.query.page ?? 1))
  }
})

onMounted(async () => {
  window.addEventListener('keydown', handleKey, true)
  try { config.value = await getConfig(); candidateCount.value = Number(route.query.candidates_per_source ?? config.value.default_candidates_per_source) }
  catch (e) { error.value = e instanceof Error ? e.message : 'Unable to connect to the API.' }
  if (routeView.value === 'search' && route.query.q) await loadSearch(Number(route.query.page ?? 1), false)
  if (routeView.value === 'watch') await loadCurrentVideo()
  if (routeView.value === 'bookmarks') await loadBookmarks(Number(route.query.page ?? 1))
})
onUnmounted(() => window.removeEventListener('keydown', handleKey, true))
</script>

<template>
  <main v-if="routeView === 'search' || routeView === 'bookmarks'" class="container">
    <header>
      <div class="brand"><a class="brand-mark" href="/" aria-label="NoBSTube home"><img src="/favicon.svg" alt=""></a><div><h1>NoBSTube</h1><p>Search and discover without a recommendation feed.</p></div></div>
      <nav class="top-nav"><RouterLink class="settings" to="/">Search</RouterLink><RouterLink class="settings" to="/bookmarks">Bookmarks</RouterLink><RouterLink class="settings" to="/rules">Rules</RouterLink></nav>
    </header>
    <h1 v-if="routeView === 'bookmarks'" class="page-title">Bookmarks</h1>
    <form v-if="routeView === 'search'" class="search" @submit.prevent="loadSearch(1)">
      <input id="search-input" v-model="query" placeholder="What would you like to watch or learn?" autofocus>
      <select v-model.number="candidateCount" aria-label="Candidates per source" title="How many candidates to query from each source">
        <option v-for="count in config?.candidate_options ?? [10,25,50,75,100]" :key="count" :value="count">{{ count }} per source</option>
      </select>
      <select v-model="sort" aria-label="Sort" @change="searchResults && loadSearch(1)">
        <option value="relevance">Relevance</option><option value="newest">Newest</option><option value="oldest">Oldest</option>
        <option value="views_desc">Views: high → low</option><option value="views_asc">Views: low → high</option>
        <option value="duration_asc">Duration: short → long</option><option value="duration_desc">Duration: long → short</option>
      </select>
      <button type="submit" :disabled="loading">Search</button>
    </form>
    <div v-if="error" class="error" role="alert">{{ error }}</div>
    <div v-if="results && (routeView === 'bookmarks' || results.query)" class="result-info"><span>{{ results.total }} {{ routeView === 'bookmarks' ? 'bookmarked videos' : 'filtered results' }}</span><span v-if="results.pages">Page {{ results.page }} of {{ results.pages }}</span></div>
    <div v-if="results && (routeView === 'bookmarks' || results.query) && !results.videos.length" class="empty">{{ routeView === 'bookmarks' ? 'No bookmarked videos yet.' : 'No videos survived the current filters.' }}</div>
    <section class="grid">
      <article v-for="item in results?.videos" :key="`${item.source}:${item.source_id}`" class="card">
        <button class="bookmark-button" type="button" :aria-label="item.is_bookmarked ? 'Remove bookmark' : 'Bookmark video'" :aria-pressed="item.is_bookmarked" @click="toggleBookmark(item)">{{ item.is_bookmarked ? '★ Saved' : '☆ Bookmark' }}</button>
        <a class="video-link" :href="`/watch/${encodeURIComponent(item.source)}/${item.source_id}`" @click.prevent="openVideo(item)">
          <div class="thumbnail-wrap"><img v-if="item.thumbnail_url" :src="item.thumbnail_url" alt="" loading="lazy" referrerpolicy="no-referrer"><div v-else class="no-thumb">No source thumbnail</div><span v-if="item.duration_label" class="duration-badge">{{ item.duration_label }}</span></div>
          <div class="card-body"><h2>{{ item.title }}</h2><div class="meta"><span v-if="item.channel" class="card-channel" :title="item.channel">{{ item.channel.length > 25 ? `${item.channel.slice(0, 25)}…` : item.channel }}</span><span v-if="item.views_label" class="card-views">{{ item.views_label }}</span><span class="source-badge" :class="`source-${item.source.toLowerCase().replaceAll(' ', '-')}`">{{ item.source === 'YouTube' ? '▶' : item.source === 'PeerTube' ? '◉' : '▣' }} {{ item.source }}</span></div></div>
        </a>
      </article>
    </section>
    <nav v-if="results && results.pages > 1" class="pagination" aria-label="Pagination">
      <a v-if="page > 1" href="#" @click.prevent="routeView === 'bookmarks' ? loadBookmarks(page - 1) : loadSearch(page - 1)">← Previous</a>
      <a v-for="n in results.pages" :key="n" href="#" :class="{ current: n === page }" @click.prevent="routeView === 'bookmarks' ? loadBookmarks(n) : loadSearch(n)">{{ n }}</a>
      <a v-if="page < results.pages" href="#" @click.prevent="routeView === 'bookmarks' ? loadBookmarks(page + 1) : loadSearch(page + 1)">Next →</a>
    </nav>
  </main>

  <main v-else-if="routeView === 'rules'" class="container">
    <header><div><h1>Filtering Rules</h1><p>Current rules used to filter video candidates.</p></div><RouterLink class="settings" to="/">← Back to search</RouterLink></header>
    <section v-if="config" class="rules">
      <template v-for="[title, group] in [['Exclusions', config.rules.exclusions], ['Preferences', config.rules.preferences]] as const" :key="title">
        <h2>{{ title }}</h2><template v-for="[category, values] in Object.entries(group)" :key="category"><h3>{{ category.replaceAll('_', ' ') }}</h3><ul v-if="values.length"><li v-for="value in values" :key="String(value)">{{ value }}</li></ul><p v-else>None</p></template>
      </template>
      <h2>Settings</h2><ul><li v-for="[key, value] in Object.entries(config.rules.settings)" :key="key"><strong>{{ key.replaceAll('_', ' ') }}:</strong> {{ value }}</li></ul>
    </section>
  </main>

  <main v-else-if="video" class="watch-container watch-page">
    <div class="player"><video v-if="video.playable_url" ref="player" controls preload="metadata" :poster="video.thumbnail_url"><source :src="video.playable_url">Your browser does not support HTML5 video.</video><iframe v-else-if="video.embed_url" :src="video.embed_url" :title="video.title" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen></iframe><div v-else class="player-unavailable">This video cannot currently be played inside NoBSTube.</div><button class="watch-close" type="button" aria-label="Close video and return to results" title="Back to results" @click="closeVideo">×</button></div>
    <div v-if="video.url" class="external fallback-link"><a :href="video.url" target="_blank" rel="noopener noreferrer">{{ video.embed_url || video.playable_url ? 'If playback fails, open' : 'Open' }} this video on {{ video.source }} ↗</a></div>
    <div class="watch-title-row"><h1>{{ video.title }}</h1><button class="bookmark-action" type="button" :aria-pressed="video.is_bookmarked" @click="toggleBookmark(video)">{{ video.is_bookmarked ? '★ Bookmarked' : '☆ Bookmark' }}</button></div><div v-if="video.channel" class="watch-meta">{{ video.channel }}</div><div v-if="video.description" class="description">{{ video.description }}</div>
  </main>
  <div v-if="loading" class="page-loading" aria-live="polite" aria-busy="true"><div class="loading-card"><span class="spinner" aria-hidden="true"></span><span>{{ busyLabel }}</span></div></div>
  <div v-if="error && routeView === 'watch'" class="watch-error" role="alert">{{ error }} <RouterLink to="/">Back to search</RouterLink></div>
</template>
