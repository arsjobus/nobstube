import asyncio
import httpx
import logging
from urllib.parse import urljoin, urlsplit, urlunsplit
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

        # Keep results from each instance represented. Concatenating then
        # truncating lets the first instance consume the entire search quota.
        instance_batches = [batch for batch in batches if isinstance(batch, list)]
        for offset in range(max((len(batch) for batch in instance_batches), default=0)):
            for batch in instance_batches:
                if offset < len(batch):
                    results.append(batch[offset])
                    if len(results) >= limit:
                        return results

        return results

    async def _search_instance(self, client, instance, query, limit):
        try:
            url = f"{instance}/api/v1/search/videos"
            params = {
                "search": query,
                "count": limit,
                "sort": "-match",
                "searchTarget": "search-index",
            }
            response = await client.get(url, params=params)
            if response.is_error:
                # The global index is optional and controlled by each
                # instance administrator. Retry using that instance's
                # configured default search when it is not available.
                logger.info("PeerTube search index unavailable on %s; using default search", instance)
                params.pop("searchTarget")
                response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("data", []):
                uuid = item.get("uuid")
                if not uuid:
                    continue

                channel = item.get("channel") or {}
                playlist = item.get("streamingPlaylists") or []

                video_url = item.get("url") or ""
                thumbnails = item.get("thumbnails") or []
                thumbnail_path = ""
                if isinstance(thumbnails, list):
                    thumbnail_path = next(
                        (thumbnail.get("fileUrl") for thumbnail in thumbnails
                         if isinstance(thumbnail, dict) and thumbnail.get("fileUrl")),
                        "",
                    )
                thumbnail_path = (
                    thumbnail_path
                    or item.get("thumbnailPath")
                    or item.get("previewPath")
                    or item.get("thumbnailUrl")
                    or ""
                )
                # Search-index results can point to videos hosted on a remote
                # PeerTube instance. Relative thumbnail paths belong to the
                # video's origin, not necessarily the instance we searched.
                origin = urlsplit(video_url)
                thumbnail_base = (
                    urlunsplit((origin.scheme, origin.netloc, "/", "", ""))
                    if origin.scheme and origin.netloc
                    else instance.rstrip("/") + "/"
                )
                # Search-index entries for remote videos can contain stale
                # thumbnail paths. Refresh metadata from the hosting instance
                # for remote results, and also fill omissions on local ones.
                is_remote = bool(
                    origin.netloc
                    and origin.netloc.lower() != urlsplit(instance).netloc.lower()
                )
                if is_remote or not thumbnail_path:
                    try:
                        detail_response = await client.get(
                            urljoin(thumbnail_base, f"api/v1/videos/{uuid}")
                        )
                        detail_response.raise_for_status()
                        details = detail_response.json()
                        detail_thumbnails = details.get("thumbnails") or []
                        detail_thumbnail = next(
                            (thumbnail.get("fileUrl") for thumbnail in detail_thumbnails
                             if isinstance(thumbnail, dict) and thumbnail.get("fileUrl")),
                            "",
                        ) if isinstance(detail_thumbnails, list) else ""
                        detail_thumbnail_path = (
                            detail_thumbnail
                            or details.get("thumbnailPath")
                            or details.get("previewPath")
                            or details.get("thumbnailUrl")
                            or ""
                        )
                        if detail_thumbnail_path:
                            thumbnail_path = detail_thumbnail_path
                    except Exception:
                        logger.debug(
                            "PeerTube video metadata unavailable for thumbnail: %s",
                            video_url or uuid,
                            exc_info=True,
                        )
                thumbnail = urljoin(thumbnail_base, thumbnail_path) if thumbnail_path else ""
                playable = None
                if playlist:
                    playable = playlist[0].get("playlistUrl")

                results.append(Video(
                    source=self.name,
                    source_id=f"{instance}:{uuid}",
                    url=video_url,
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
