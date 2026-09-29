import asyncio
import httpx
import logging
from urllib.parse import urljoin
from .base import VideoSource
from ..models import Video

logger = logging.getLogger(__name__)

DEFAULT_INSTANCES = [
    "https://framatube.org",
    "https://peertube.tv",
]

class PeerTubeSource(VideoSource):
    name = "PeerTube"

    async def search(self, query: str, limit: int = 25) -> list[Video]:
        try:
            return await asyncio.wait_for(
                self._search(query, limit),
                timeout=20,
            )
        except asyncio.TimeoutError:
            logger.warning("PeerTube search timed out for %r", query)
            return []
        except Exception:
            logger.exception("PeerTube search failed for %r", query)
            return []

    async def _search(self, query: str, limit: int) -> list[Video]:
        results = []

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=True,
        ) as client:
            tasks = [
                self._search_instance(client, instance, query, limit)
                for instance in DEFAULT_INSTANCES
            ]
            batches = await asyncio.gather(*tasks, return_exceptions=True)

        for batch in batches:
            if isinstance(batch, list):
                results.extend(batch)

        return results[:limit]

    async def _search_instance(self, client, instance, query, limit):
        try:
            response = await client.get(
                f"{instance}/api/v1/search/videos",
                params={"search": query, "count": limit},
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("data", []):
                uuid = item.get("uuid")
                if not uuid:
                    continue

                channel = item.get("channel") or {}
                playlist = item.get("streamingPlaylists") or []

                thumbnail_path = item.get("thumbnailPath") or item.get("thumbnailUrl") or ""
                thumbnail = urljoin(instance.rstrip("/") + "/", thumbnail_path) if thumbnail_path else ""
                playable = None
                if playlist:
                    playable = playlist[0].get("playlistUrl")

                results.append(Video(
                    source=self.name,
                    source_id=f"{instance}:{uuid}",
                    url=item.get("url") or "",
                    title=item.get("name") or "",
                    channel=channel.get("displayName", ""),
                    description=item.get("description") or "",
                    duration_seconds=item.get("duration"),
                    published_at=item.get("publishedAt"),
                    thumbnail_url=thumbnail,
                    view_count=item.get("views"),
                    like_count=item.get("likes"),
                    playable_url=playable,
                    tags=item.get("tags") or [],
                ))
            return results
        except Exception:
            logger.exception("PeerTube instance failed: %s", instance)
            return []
