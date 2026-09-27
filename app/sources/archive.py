import asyncio
import httpx
import logging
from .base import VideoSource
from ..models import Video

logger = logging.getLogger(__name__)

class InternetArchiveSource(VideoSource):
    name = "Internet Archive"

    async def search(self, query: str, limit: int = 25) -> list[Video]:
        try:
            return await asyncio.wait_for(
                self._search(query, limit),
                timeout=20,
            )
        except asyncio.TimeoutError:
            logger.warning("Internet Archive search timed out for %r", query)
            return []
        except Exception:
            logger.exception("Internet Archive search failed for %r", query)
            return []

    async def _search(self, query: str, limit: int) -> list[Video]:
        params = {
            "q": f"({query}) AND mediatype:movies",
            "fl[]": [
                "identifier", "title", "description",
                "creator", "date", "downloads",
            ],
            "rows": limit,
            "page": 1,
            "output": "json",
        }

        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(
                "https://archive.org/advancedsearch.php",
                params=params,
            )
            response.raise_for_status()
            docs = response.json().get("response", {}).get("docs", [])

        results = []
        for item in docs:
            identifier = item.get("identifier")
            if not identifier:
                continue

            # IA exposes thumbnails by identifier without requiring video
            # download. This is a source metadata/asset URL only.
            thumbnail = f"https://archive.org/services/img/{identifier}"

            results.append(Video(
                source=self.name,
                source_id=identifier,
                url=f"https://archive.org/details/{identifier}",
                title=item.get("title") or identifier,
                channel=item.get("creator") or "",
                description=item.get("description") or "",
                published_at=item.get("date"),
                thumbnail_url=thumbnail,
                view_count=item.get("downloads"),
            ))

        return results
