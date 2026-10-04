import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import logging
import os
from typing import Any

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "120"))
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
OLLAMA_BATCH_SIZE = max(1, int(os.getenv("OLLAMA_BATCH_SIZE", "16")))
OLLAMA_MIN_BATCH_SIZE = max(1, int(os.getenv("OLLAMA_MIN_BATCH_SIZE", "4")))
OLLAMA_MAX_BATCH_SIZE = max(OLLAMA_MIN_BATCH_SIZE, int(os.getenv("OLLAMA_MAX_BATCH_SIZE", "24")))
OLLAMA_FAST_BATCH_SECONDS = float(os.getenv("OLLAMA_FAST_BATCH_SECONDS", "25"))
OLLAMA_SLOW_BATCH_SECONDS = float(os.getenv("OLLAMA_SLOW_BATCH_SECONDS", "45"))
OLLAMA_MAX_CONCURRENT = max(1, int(os.getenv("OLLAMA_MAX_CONCURRENT", "1")))
OLLAMA_THINK = os.getenv("OLLAMA_THINK", "false").lower() in {"1", "true", "yes", "on"}
OLLAMA_NUM_PREDICT = max(256, int(os.getenv("OLLAMA_NUM_PREDICT", "800")))
OLLAMA_DESCRIPTION_CHARS = max(100, int(os.getenv("OLLAMA_DESCRIPTION_CHARS", "650")))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "10m")
AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama").strip().lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_MAX_RETRIES = 3
OPENAI_MAX_RETRY_DELAY = 30.0

SYSTEM_PROMPT = """
You are a fast video relevance filter.

Allow substantive videos that are genuinely relevant to the user's search,
including tutorials, technical demonstrations, educational explanations,
lectures, documentaries, relevant expert interviews, project/development work,
and useful primary-source material.

Reject videos that are primarily influencer/lifestyle/personality content,
celebrity gossip/drama, reactions, pranks, ragebait, shock content, clickbait,
engagement bait, political persuasion, conspiracy content, shorts/clips/
compilations, or primarily advertising/promotional content.

A video does NOT need to be from a university or be a formal lecture.
Independent technical creators and project videos are allowed when substantive.
When metadata is incomplete, do not reject merely because of missing detail.
Reject only when there is a clear reason.

Return ONLY valid JSON with this exact structure:
{"results":[{"index":1,"allow":true,"category":"technology","language":"en","confidence":0.91,"reason":"Relevant technical tutorial"}]}

Language guidance: identify the video's primary language from its title and available details such as description and tags. Use "en" for English, another ISO 639-1 code when reasonably clear, or "unknown" only when the language cannot be determined. Do not infer language from the channel name alone when the video details indicate another language.
"""


def _video_text(index: int, video: Any, query: str = "") -> str:
    title = str(getattr(video, "title", "") or "")[:240]
    channel = str(getattr(video, "channel", "") or "")[:140]
    description = str(getattr(video, "description", "") or "")[:OLLAMA_DESCRIPTION_CHARS]
    tags = getattr(video, "tags", []) or []
    if not isinstance(tags, list):
        tags = [tags]
    tags_text = ", ".join(str(tag)[:60] for tag in tags[:12])
    return (
        f"VIDEO {index}\n"
        f"Query: {query[:160]}\n"
        f"Title: {title}\n"
        f"Channel: {channel}\n"
        f"Description: {description}\n"
        f"Tags: {tags_text}\n"
    )


def _failure(reason: str, count: int) -> list[dict]:
    return [
        {"allow": False, "category": "unknown", "language": "unknown", "confidence": 0.0, "reason": reason}
        for _ in range(count)
    ]


def _openai_error(response: httpx.Response) -> tuple[str, str, str]:
    try:
        error = response.json().get("error", {})
    except (ValueError, AttributeError):
        error = {}
    if not isinstance(error, dict):
        error = {}
    return (
        str(error.get("code", "") or "").lower(),
        str(error.get("type", "") or "").lower(),
        str(error.get("message", "") or ""),
    )


def _retry_after_seconds(response: httpx.Response) -> float | None:
    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return None
    try:
        return max(0.0, float(retry_after))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(retry_after)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


async def _openai_post_with_retries(client, url, payload, headers, batch_number, total_batches):
    for attempt in range(OPENAI_MAX_RETRIES + 1):
        response = await client.post(url, json=payload, headers=headers)
        try:
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429:
                raise

            code, error_type, message = _openai_error(exc.response)
            normalized_message = message.lower()
            if (
                code in {"insufficient_quota", "billing_hard_limit_reached"}
                or error_type == "insufficient_quota"
                or "quota" in normalized_message
                or "billing" in normalized_message
            ):
                raise RuntimeError(
                    "OpenAI API quota is unavailable. Check the API account's billing and usage limits."
                ) from exc

            if attempt >= OPENAI_MAX_RETRIES:
                raise RuntimeError(
                    f"OpenAI rate limit persisted after {OPENAI_MAX_RETRIES} retries. "
                    "Try again later or lower OPENAI_MAX_CONCURRENT."
                ) from exc

            delay = _retry_after_seconds(exc.response)
            if delay is None:
                delay = min(2**attempt, OPENAI_MAX_RETRY_DELAY)
            elif delay > OPENAI_MAX_RETRY_DELAY:
                raise RuntimeError(
                    f"OpenAI requested a retry after {delay:.0f} seconds. Try again later."
                ) from exc

            logger.warning(
                "OpenAI batch %d/%d rate limited; retrying in %.1fs (%d/%d)",
                batch_number, total_batches, delay, attempt + 1, OPENAI_MAX_RETRIES,
            )
            await asyncio.sleep(delay)


async def _classify_batch(client, videos, query, batch_number, total_batches):
    prompt = "\n".join(_video_text(i, video, query) for i, video in enumerate(videos, 1))
    started = asyncio.get_running_loop().time()
    provider = AI_PROVIDER
    logger.info("%s batch %d/%d: sending %d videos", provider, batch_number, total_batches, len(videos))

    try:
        headers = {}
        if provider == "ollama":
            url = f"{OLLAMA_BASE_URL}/api/chat"
            payload = {
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",
                "think": OLLAMA_THINK,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": {
                    "temperature": 0,
                    "num_predict": OLLAMA_NUM_PREDICT,
                    "num_ctx": 8192,
                },
            }
        elif provider == "openai":
            if not OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is required when AI_PROVIDER=openai")
            url = f"{OPENAI_BASE_URL}/chat/completions"
            headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
            payload = {
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            }
        else:
            raise ValueError(f"Unsupported AI_PROVIDER: {provider}")

        if provider == "openai":
            response = await _openai_post_with_retries(
                client, url, payload, headers, batch_number, total_batches,
            )
        else:
            response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        if provider == "ollama":
            content = data.get("message", {}).get("content", "")
        else:
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"{provider} returned empty message content")
        parsed = json.loads(content)
        raw_results = parsed.get("results")
        if not isinstance(raw_results, list):
            raise ValueError(f"{provider} response did not contain a results list")

        indexed = {}
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item["index"])
            except (KeyError, TypeError, ValueError):
                continue
            try:
                confidence = max(0.0, min(1.0, float(item.get("confidence", 0))))
            except (TypeError, ValueError):
                confidence = 0.0
            indexed[index] = {
                "allow": bool(item.get("allow", False)),
                "category": str(item.get("category", "unknown")),
                "language": str(item.get("language", "unknown")),
                "confidence": confidence,
                "reason": str(item.get("reason", ""))[:240],
            }

        output = [indexed.get(i, {
            "allow": False,
            "category": "unknown",
            "language": "unknown",
            "confidence": 0.0,
            "reason": f"Video was not classified by {provider}",
        }) for i in range(1, len(videos) + 1)]
        allowed = sum(1 for item in output if item["allow"])
        missing = sum(1 for item in output if "not classified" in item["reason"])
        elapsed = asyncio.get_running_loop().time() - started
        logger.info(
            "%s batch %d/%d: %.2fs, returned=%d, allowed=%d, rejected=%d, missing=%d",
            provider, batch_number, total_batches, elapsed, len(indexed), allowed,
            len(output) - allowed - missing, missing,
        )
        return output, elapsed
    except Exception as exc:
        elapsed = asyncio.get_running_loop().time() - started
        logger.exception("%s batch %d/%d failed after %.2fs: %s", provider, batch_number, total_batches, elapsed, exc)
        return _failure(f"{provider} unavailable: {exc}", len(videos)), elapsed


async def classify_videos(videos: list[Any], query: str = "") -> list[dict]:
    """Classify videos with adaptive batches and bounded parallel provider requests.

    Batches are processed in concurrent waves. After each wave, the batch size
    is adjusted from observed latency. This keeps concurrency bounded so a
    MacBook does not get flooded while still allowing multiple Ollama requests
    to make progress at once.
    """
    if not videos:
        return []
    if AI_PROVIDER == "ollama" and not OLLAMA_ENABLED:
        return _failure("Ollama filtering is disabled", len(videos))
    if AI_PROVIDER == "openai" and not OPENAI_API_KEY:
        return _failure("OPENAI_API_KEY is required when AI_PROVIDER=openai", len(videos))
    if AI_PROVIDER not in {"ollama", "openai"}:
        return _failure(f"Unsupported AI_PROVIDER: {AI_PROVIDER}", len(videos))

    batch_size = min(max(OLLAMA_BATCH_SIZE, OLLAMA_MIN_BATCH_SIZE), OLLAMA_MAX_BATCH_SIZE)
    concurrency = max(1, OLLAMA_MAX_CONCURRENT)
    started_all = asyncio.get_running_loop().time()
    timeout = httpx.Timeout(OLLAMA_TIMEOUT, connect=3.0)
    results: list[dict | None] = [None] * len(videos)
    position = 0
    batch_number = 0
    total_batches_estimate = max(1, (len(videos) + batch_size - 1) // batch_size)

    logger.info(
        "%s: classifying %d videos with adaptive batches (start=%d, min=%d, max=%d, max concurrent=%d)",
        AI_PROVIDER, len(videos), batch_size, OLLAMA_MIN_BATCH_SIZE, OLLAMA_MAX_BATCH_SIZE, concurrency,
    )

    async with httpx.AsyncClient(timeout=timeout) as client:
        while position < len(videos):
            wave = []
            wave_start_positions = []
            for _ in range(concurrency):
                if position >= len(videos):
                    break
                chunk = videos[position:position + batch_size]
                batch_number += 1
                wave_start_positions.append(position)
                wave.append(_classify_batch(client, chunk, query, batch_number, total_batches_estimate))
                position += len(chunk)

            wave_results = await asyncio.gather(*wave, return_exceptions=True)
            timings = []

            for start_position, outcome in zip(wave_start_positions, wave_results):
                count = min(batch_size, len(videos) - start_position)
                if isinstance(outcome, Exception):
                    logger.exception("%s batch failed unexpectedly", AI_PROVIDER, exc_info=outcome)
                    batch_results, elapsed = _failure(f"{AI_PROVIDER} unavailable: {outcome}", count), 0.0
                else:
                    batch_results, elapsed = outcome
                results[start_position:start_position + count] = batch_results[:count]
                if elapsed > 0:
                    timings.append(elapsed)

            if timings:
                representative = max(timings)
                old_size = batch_size
                if representative >= OLLAMA_SLOW_BATCH_SECONDS:
                    batch_size = max(OLLAMA_MIN_BATCH_SIZE, max(1, batch_size // 2))
                elif representative <= OLLAMA_FAST_BATCH_SECONDS:
                    batch_size = min(OLLAMA_MAX_BATCH_SIZE, batch_size + max(1, batch_size // 4))
                if batch_size != old_size:
                    logger.info(
                        "%s adaptive batch size: %d -> %d after wave max %.2fs",
                        AI_PROVIDER, old_size, batch_size, representative,
                    )

    final_results = [
        result if result is not None else {
            "allow": False,
            "category": "unknown",
            "language": "unknown",
            "confidence": 0.0,
            "reason": f"Video was not classified by {AI_PROVIDER}",
        }
        for result in results
    ]
    logger.info(
        "%s: completed %d batches in %.2fs (concurrency=%d)",
        AI_PROVIDER, batch_number, asyncio.get_running_loop().time() - started_all, concurrency,
    )
    return final_results


async def classify_video(title="", channel="", description="", tags=None, query="") -> dict:
    class TemporaryVideo:
        pass
    video = TemporaryVideo()
    video.title = title
    video.channel = channel
    video.description = description
    video.tags = tags or []
    return (await classify_videos([video], query=query))[0]
