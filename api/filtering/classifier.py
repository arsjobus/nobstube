from dataclasses import dataclass
from typing import Any
import re

from .ollama import classify_videos


@dataclass
class ClassificationResult:
    allowed: bool
    score: float
    reason: str = ""
    category: str = ""
    confidence: float = 0.0
    language: str = "unknown"


class AIClassifier:
    def __init__(self, rules):
        self.rules = rules

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}

    def _cheap_relevance(self, video, query: str) -> float:
        """Cheap metadata relevance score used to prioritize local inference.

        This does not approve/reject videos. It only puts the most obviously
        query-relevant items first so that if Ollama is slow, useful results
        are classified before weakly related candidates.
        """
        q = self._tokens(query)
        if not q:
            return 0.0
        title = self._tokens(str(getattr(video, "title", "") or ""))
        channel = self._tokens(str(getattr(video, "channel", "") or ""))
        description = self._tokens(str(getattr(video, "description", "") or "")[:900])
        return len(q & title) * 4.0 + len(q & channel) * 2.0 + len(q & description)

    async def classify(self, video, query=""):
        return (await self.classify_batch([video], query=query))[0]

    async def classify_batch(self, videos: list[Any], query: str = "") -> list[ClassificationResult]:
        if not videos:
            return []

        results: list[ClassificationResult | None] = [None] * len(videos)
        llm_items = []

        for index, video in enumerate(videos):
            rejected, reason = self.rules.hard_reject(video)
            if rejected:
                results[index] = ClassificationResult(False, 0.0, reason, "hard_rule", 1.0)
            else:
                llm_items.append((index, video))

        # Classify strongest metadata matches first. We still classify every
        # non-hard-rejected video; this only improves the order of inference.
        llm_items.sort(key=lambda pair: self._cheap_relevance(pair[1], query), reverse=True)
        llm_videos = [video for _, video in llm_items]
        batch_results = await classify_videos(llm_videos, query=query)

        for (index, _video), result in zip(llm_items, batch_results):
            confidence = float(result.get("confidence", 0.0))
            results[index] = ClassificationResult(
                allowed=bool(result.get("allow", False)),
                score=confidence if result.get("allow", False) else 0.0,
                reason=str(result.get("reason", "")),
                category=str(result.get("category", "unknown")),
                confidence=confidence,
                language=str(result.get("language", "unknown")),
            )

        return [
            r if r is not None else ClassificationResult(False, 0.0, "Video was not classified", "unknown", 0.0)
            for r in results
        ]
