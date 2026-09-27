# NoBSTube v1.3.1

A local, self-hosted video discovery application designed to find useful videos without exposing you to an algorithmic recommendation feed.

## v1.2.0 changes

- 100 candidates requested from each source per search.
- YouTube search optimized for discovery using lightweight `yt-dlp` extraction.
- YouTube search timeout reduced so a slow YouTube request cannot hold the whole search open indefinitely.
- Source searches remain concurrent and isolated.
- Hard exclusions are applied before sending videos to Ollama.
- Qwen/Ollama classification is batched and uses bounded concurrency.
- Search results are cached in memory for 15 minutes.
- Sorting and all pagination operate on the cached candidate set; changing page does not search YouTube, PeerTube, Internet Archive, or Ollama again.
- The complete filtered 100-video pool is saved to SQLite so opening a result does not trigger another source search.
- YouTube uses the official embedded player. Other sources use direct playback when their metadata exposes a playable URL.
- When an embedded/direct player is unavailable, the watch page provides an external link to the hosting site.
- Source-provided thumbnails only. No generated thumbnails, video downloads, screenshots, or ffmpeg are used for discovery.
- `.env.example` now documents the Ollama configuration.
- Existing SQLite database migrations remain compatible with older databases.
- Fixes the classifier/pipeline append bug and keeps the rule-engine tests compatible.

## Install / upgrade

Stop the existing Nobstube server and back up the project. Extract this release over the existing project.

Then update the environment:

```bash
pip install -U -r requirements.txt
```

For Ollama:

```dotenv
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
OLLAMA_TIMEOUT=20
OLLAMA_ENABLED=true
OLLAMA_BATCH_SIZE=40
OLLAMA_MAX_CONCURRENT=2
```

Start Nobstube:

```bash
uvicorn app.main:app --reload
```

## Search architecture

A search builds a candidate pool once:

```text
YouTube  ──────┐
PeerTube ──────┼──> deduplicate -> hard rules -> Ollama -> sort -> cache
Archive  ──────┘
                                      │
                                      └──> up to 100 filtered results
```

The browser then pages through that cached result set. Page 2, 3, etc. do not start a new external search. Sorting also reuses the candidate pool.

The cache is local to the running process and expires after 15 minutes. Restarting Nobstube clears it.

## Performance

The application aims to return a useful result set within roughly 30 seconds on a typical local MacBook Air, but actual time depends on YouTube/other source response time and local Qwen inference speed.

The main controls are:

- `candidates_per_source`: 100
- The search UI also lets you choose 10, 25, 50, 75, or 100 candidates per source; the selected count is included in the candidate cache key so changing it triggers the appropriate source query without repeating pagination searches.
- `OLLAMA_BATCH_SIZE`: 40
- `OLLAMA_MAX_CONCURRENT`: 2
- `OLLAMA_TIMEOUT`: 20 seconds per batch

If Qwen inference is the bottleneck, lowering `OLLAMA_BATCH_SIZE` or concurrency may help depending on the Mac's memory/compute.

## YouTube

Nobstube uses `yt-dlp` without a YouTube API account. Search discovery uses flat extraction rather than fully extracting every result, which avoids unnecessary metadata/media work.

Nobstube never generates replacement thumbnails. YouTube thumbnails come from YouTube's own thumbnail URLs.

If YouTube becomes unavailable or exceeds its source timeout, the other sources can still return results.

## Playback

YouTube videos are displayed using the official YouTube embedded player. Nobstube does not download or re-host YouTube video media.

For sources exposing direct playable media URLs, Nobstube can use the browser's native video player. If a video cannot be played inside Nobstube, the watch page provides a link to open the original video on its hosting site in a new tab.

## Sorting

Supported sorting modes:

- relevance
- newest
- oldest
- views high → low
- views low → high
- duration short → long
- duration long → short

## Tests

From the project root:

```bash
PYTHONPATH=. pytest -q
```


## v1.2.1 diagnostic/performance update

This upgrade is based on v1.2.0 and is intended to diagnose the case where
Ollama spends a long time classifying batches but the search returns zero
allowed videos.

Changes:
- Logs every Ollama batch independently, including elapsed time and counts.
- Logs malformed/empty Ollama responses and batch exceptions with tracebacks.
- Enables Qwen3 `think=false` by default for the classification pass, which
  avoids spending inference time on extended reasoning when the task only
  needs a structured allow/reject decision.
- Adds `OLLAMA_THINK` to `.env.example`; set it to `true` if deeper reasoning
  is desired.
- Adds a bounded `num_predict=4096` to keep structured batch responses from
  running indefinitely.
- Keeps failures fail-closed: an unavailable or malformed classification is
  rejected rather than accidentally allowed.

After upgrading, a useful search log should look like:

```text
Ollama batch 1/7: sending 40 videos
Ollama batch 2/7: sending 40 videos
Ollama batch 1/7: 8.42s, returned=40, allowed=12, rejected=28, missing=0
Ollama batch 2/7: 9.01s, returned=40, allowed=8, rejected=32, missing=0
```

If a batch fails, v1.2.1 now makes the exact failure visible instead of only
reporting the aggregate batch duration.

## v1.2.2 performance/filtering update

This release keeps the v1.2.1 search architecture but tunes the local Qwen/Ollama
classifier for a MacBook Air.

Changes:
- Keeps 100 source candidates per source.
- Qwen receives the search query explicitly, so a broad query such as `game dev`
  is not incorrectly rejected merely because the video is not a formal lecture.
- The classifier prompt is shorter and explicitly allows substantive independent
  technical/project creators.
- Descriptions sent to Ollama are capped at 650 characters and tags at 12 items.
- Default batch size is 16 instead of 40 or 8; this keeps each JSON response
  manageable without creating dozens of tiny requests.
- Default local concurrency is 1. Running multiple Qwen generations at once can
  compete for the same MacBook memory/compute and make every request slower.
- A single warmed `httpx.AsyncClient` is reused for all batches instead of
  creating a new client for every batch.
- `keep_alive` keeps Qwen loaded between batches.
- `num_predict` defaults to 1200 because classification responses are short;
  the old 4096 limit allowed unnecessary generation.
- `think=false` remains the default for this fast classification pass.
- Candidate metadata is cheaply ranked by query relevance before Ollama sees it.
  This does not approve or reject anything; it simply means the most promising
  candidates are classified first.
- Ollama failures remain fail-closed.
- Existing search-result caching and pagination behavior is retained: changing
  page or sort does not search the external sources again.
- No generated thumbnails or downloaded video media are introduced.

Recommended `.env` starting point:

```dotenv
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
OLLAMA_TIMEOUT=75
OLLAMA_ENABLED=true
OLLAMA_BATCH_SIZE=16
OLLAMA_MAX_CONCURRENT=1
OLLAMA_NUM_PREDICT=1200
OLLAMA_DESCRIPTION_CHARS=650
OLLAMA_KEEP_ALIVE=10m
OLLAMA_THINK=false
```

If one batch still takes a very long time, try `OLLAMA_BATCH_SIZE=8`. Do not
increase concurrency first on a MacBook Air; measure single-generation speed
before adding parallel inference.


## v1.3.1

- Page title and header branding are now **NoBSTube** with a matching favicon/brand mark.
- Search requests show an on-page loading indicator while source search and Ollama classification are running.
- Changing the sort selector automatically refreshes the results using the existing server-side candidate cache; the user no longer needs to press Search again.
- Ollama now reports a best-effort primary language and gives English-language results a small relevance preference without rejecting other languages.
- Existing relevance remains the primary ordering signal.
