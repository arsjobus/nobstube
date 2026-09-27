from dataclasses import dataclass, field
from typing import Optional


def _format_duration(seconds: Optional[int]) -> str:
    if seconds is None:
        return ""
    try:
        total = max(0, int(seconds))
    except (TypeError, ValueError):
        return ""
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_count(value: Optional[int]) -> str:
    if value is None:
        return ""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return ""
    if number < 1000:
        return f"{number:,}"
    if number < 1_000_000:
        return f"{number / 1000:.1f}K"
    if number < 1_000_000_000:
        return f"{number / 1_000_000:.1f}M"
    return f"{number / 1_000_000_000:.1f}B"


@dataclass
class Video:
    source: str
    source_id: str

    title: str = ""
    url: str = ""
    channel: str = ""
    description: str = ""

    duration_seconds: Optional[int] = None
    published_at: Optional[str] = None

    thumbnail_url: str = ""

    view_count: Optional[int] = None
    like_count: Optional[int] = None

    embed_url: str = ""
    playable_url: str = ""

    tags: list[str] = field(default_factory=list)

    score: float = 0.0

    @property
    def duration_label(self) -> str:
        return _format_duration(self.duration_seconds)

    @property
    def views_label(self) -> str:
        if self.view_count is None:
            return ""
        count = _format_count(self.view_count)
        if self.source == "Internet Archive":
            return f"{count} downloads"
        return f"{count} views"

    def searchable_text(self) -> str:
        """Return normalized text used by the filtering/classification pipeline."""
        parts = [
            self.title or "",
            self.channel or "",
            self.description or "",
            " ".join(str(tag) for tag in (self.tags or [])),
        ]
        return " ".join(parts)