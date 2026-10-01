import asyncio
import httpx
import logging
import re
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
        # Archive.org's query parser accepts Boolean operators. A bare
        # multiword query can behave like a broad metadata search, so require
        # all meaningful query terms in the first pass. If that is sparse,
        # use an OR fallback to retain recall while keeping the stronger
        # matches first.
        terms = list(dict.fromkeys(re.findall(r"[a-z0-9]+", query.lower())))
        strict_terms = [term for term in terms if len(term) > 2]
        if not strict_terms:
            strict_terms = terms
        strict_terms = strict_terms[:10]
        if not strict_terms:
            return []

        async with httpx.AsyncClient(timeout=8) as client:
            strict_docs = await self._search_docs(
                client, self._term_query(strict_terms, "AND"), limit
            )
            docs = list(strict_docs)
            if len(docs) < limit and len(strict_terms) > 1:
                relaxed_docs = await self._search_docs(
                    client, self._term_query(strict_terms, "OR"), limit
                )
                seen = {item.get("identifier") for item in docs}
                docs.extend(
                    item for item in relaxed_docs
                    if item.get("identifier") not in seen
                )
                docs = docs[:limit]

        results = []
        for item in docs:
            identifier = item.get("identifier")
            if not identifier:
                continue

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

    @staticmethod
    def _term_query(terms: list[str], operator: str) -> str:
        quoted_terms = [f'"{term}"' for term in terms]
        joined_terms = f" {operator} ".join(quoted_terms)
        return f"({joined_terms}) AND mediatype:movies"

    @staticmethod
    async def _search_docs(client, query: str, limit: int) -> list[dict]:
        params = {
            "q": query,
            "fl[]": [
                "identifier", "title", "description",
                "creator", "date", "downloads",
            ],
            "rows": limit,
            "page": 1,
            "output": "json",
        }

        response = await client.get(
            "https://archive.org/advancedsearch.php",
            params=params,
        )
        response.raise_for_status()
        return response.json().get("response", {}).get("docs", [])
