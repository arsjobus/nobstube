import asyncio
import logging
import time
from ..sources.youtube import YouTubeSource
from ..sources.peertube import PeerTubeSource
from ..sources.archive import InternetArchiveSource
from .classifier import AIClassifier
from .rules import RuleEngine

logger = logging.getLogger(__name__)

VALID_SORTS = {
    "relevance",
    "newest",
    "oldest",
    "views_desc",
    "views_asc",
    "duration_asc",
    "duration_desc",
}


class SearchPipeline:
    """Search, filter and cache a complete candidate result set per query.

    Pagination and sorting are performed against the cached candidate set so
    changing pages never causes the external sources or Ollama to be queried
    again.
    """

    CACHE_TTL_SECONDS = 15 * 60
    MAX_CACHE_ENTRIES = 50

    def __init__(self):
        self.rules = RuleEngine()
        self.classifier = AIClassifier(self.rules)
        self.sources = [
            YouTubeSource(),
            PeerTubeSource(),
            InternetArchiveSource(),
        ]
        self._cache: dict[str, tuple[float, list]] = {}
        self._cache_lock = asyncio.Lock()

    def _get_cached(self, cache_key: str):
        entry = self._cache.get(cache_key)
        if not entry:
            return None

        created, videos = entry
        if time.monotonic() - created > self.CACHE_TTL_SECONDS:
            self._cache.pop(cache_key, None)
            return None

        return list(videos)

    def _store_cached(self, cache_key: str, videos: list):
        self._cache[cache_key] = (time.monotonic(), list(videos))

        while len(self._cache) > self.MAX_CACHE_ENTRIES:
            oldest = min(
                self._cache,
                key=lambda key: self._cache[key][0],
            )
            self._cache.pop(oldest, None)

    async def _build_candidates(self, query: str, candidates_per_source: int | None = None) -> list:
        if candidates_per_source is None:
            candidates_per_source = int(self.rules.settings.get("candidates_per_source", 10))
        candidates_per_source = max(1, min(int(candidates_per_source), 100))
        cache_key = f"{query.lower()}\0{candidates_per_source}"

        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.info("Search %r served from candidate cache (%d per source)", query, candidates_per_source)
            return cached

        # Prevent two simultaneous page/search requests for the same query
        # from both launching expensive source + LLM searches.
        async with self._cache_lock:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached

            started = time.monotonic()
            limit = candidates_per_source

            batches = await asyncio.gather(
                *(source.search(query, limit) for source in self.sources),
                return_exceptions=True,
            )

            by_key = {}
            source_counts = {}

            for source, batch in zip(self.sources, batches):
                if isinstance(batch, Exception):
                    logger.warning(
                        "%s failed during search: %s",
                        source.name,
                        batch,
                    )
                    source_counts[source.name] = 0
                    continue

                source_counts[source.name] = len(batch)

                for video in batch:
                    by_key[(video.source, video.source_id)] = video

            logger.info(
                "Search %r candidates (%d per source) by source: %s",
                query,
                candidates_per_source,
                source_counts,
            )

            videos = list(by_key.values())

            # Remove deterministic exclusions before sending anything to the
            # local LLM. This reduces both prompt size and inference time.
            candidates = []
            hard_rejected = 0
            rejection_counts = {}
            rejection_examples = []

            for video in videos:
                rejected, reason = self.rules.hard_reject(video)
                if rejected:
                    hard_rejected += 1
                    reason = reason or "No reason supplied"
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                    if len(rejection_examples) < 8:
                        rejection_examples.append((video, reason))
                else:
                    candidates.append(video)

            logger.info(
                "Search %r: %d unique candidates, %d hard rejected, %d sent to Ollama",
                query, len(videos), hard_rejected, len(candidates),
            )
            if rejection_counts:
                summary = ", ".join(
                    f"{count}x {reason}"
                    for reason, count in sorted(rejection_counts.items(), key=lambda item: (-item[1], item[0]))
                )
                logger.info("Search %r hard rejection reasons: %s", query, summary)
            for video, reason in rejection_examples:
                logger.info(
                    "HARD REJECT [%s] %r: %s",
                    video.source, video.title or video.source_id, reason,
                )

            results = await self.classifier.classify_batch(
                candidates,
                query=query,
            )

            classified = []
            for video, result in zip(candidates, results):
                if result.allowed:
                    # Blend the user's configured preferences with the LLM
                    # confidence without letting either dominate completely.
                    preference = self.rules.preference_score(video)
                    language = str(getattr(result, "language", "unknown")).lower()
                    # English is preferred, not required. Keep the language
                    # signal deliberately small so relevance remains primary.
                    language_bonus = 0.10 if language in {"en", "eng", "english"} else (
                        -0.03 if language not in {"unknown", ""} else 0.0
                    )
                    video.score = result.score + (preference * 0.05) + language_bonus
                    classified.append(video)

            # Keep the complete filtered pool needed for local pagination.
            # The sources still provide 100 candidates each; only the first
            # 100 accepted results are exposed by the search endpoint.
            classified = classified[:100]
            self._store_cached(cache_key, classified)

            elapsed = time.monotonic() - started
            logger.info(
                "Search %r completed in %.2fs: %d candidates -> %d allowed",
                query,
                elapsed,
                len(videos),
                len(classified),
            )

            return list(classified)

    async def search(self, query: str, sort: str = "relevance", candidates_per_source: int | None = None):
        if sort not in VALID_SORTS:
            sort = "relevance"

        query = query.strip()
        if not query:
            return []

        classified = await self._build_candidates(query, candidates_per_source)
        classified = list(classified)

        def date_key(video):
            return video.published_at or ""

        def views_key(video):
            return (
                video.view_count
                if video.view_count is not None
                else -1
            )

        def duration_key(video):
            return (
                video.duration_seconds
                if video.duration_seconds is not None
                else -1
            )

        if sort == "newest":
            classified.sort(key=date_key, reverse=True)
        elif sort == "oldest":
            classified.sort(key=date_key)
        elif sort == "views_desc":
            classified.sort(key=views_key, reverse=True)
        elif sort == "views_asc":
            classified.sort(key=views_key)
        elif sort == "duration_asc":
            classified.sort(key=duration_key)
        elif sort == "duration_desc":
            classified.sort(key=duration_key, reverse=True)
        else:
            classified.sort(key=lambda video: video.score, reverse=True)

        return classified[:100]
