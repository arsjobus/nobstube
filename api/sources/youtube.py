import asyncio
import logging

import yt_dlp

from .base import VideoSource
from ..models import Video

logger = logging.getLogger(__name__)


class YouTubeSource(VideoSource):
    name = "YouTube"
    SEARCH_TIMEOUT = 15

    async def search(self, query: str, limit: int = 100) -> list[Video]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._search_sync, query, limit),
                timeout=self.SEARCH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "YouTube search timed out after %ss for %r",
                self.SEARCH_TIMEOUT,
                query,
            )
            return []
        except Exception:
            logger.exception("YouTube search failed for %r", query)
            return []

    def _search_sync(self, query: str, limit: int) -> list[Video]:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            # Search discovery does not need full media extraction.
            # This is substantially faster than extracting every result.
            "extract_flat": True,
            "noplaylist": True,
            "socket_timeout": 5,
            "retries": 0,
            "fragment_retries": 0,
        }

        results = []
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(
                    f"ytsearch{limit}:{query}",
                    download=False,
                )

            for item in (info or {}).get("entries", []):
                if not item or not item.get("id"):
                    continue

                vid = str(item["id"])
                url = (
                    item.get("webpage_url")
                    or item.get("original_url")
                    or f"https://www.youtube.com/watch?v={vid}"
                )

                # YouTube's standard thumbnail endpoint is a source-hosted
                # thumbnail, not a generated screenshot.
                thumbnail = item.get("thumbnail") or (
                    f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                )

                results.append(
                    Video(
                        source=self.name,
                        source_id=vid,
                        url=url,
                        title=item.get("title") or "",
                        channel=(
                            item.get("channel")
                            or item.get("uploader")
                            or item.get("creator")
                            or ""
                        ),
                        description=item.get("description") or "",
                        duration_seconds=item.get("duration"),
                        published_at=item.get("upload_date"),
                        thumbnail_url=thumbnail,
                        view_count=item.get("view_count"),
                        like_count=item.get("like_count"),
                        embed_url=f"https://www.youtube.com/embed/{vid}",
                        tags=item.get("tags") or [],
                    )
                )

        except Exception:
            logger.exception("yt-dlp extraction failed for %r", query)
            return []

        return results
