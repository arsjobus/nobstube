from pathlib import Path
import sqlite3

DB_PATH = Path("data/videos.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    url TEXT,
    title TEXT,
    channel TEXT,
    description TEXT,
    duration_seconds INTEGER,
    published_at TEXT,
    thumbnail_url TEXT,
    view_count INTEGER,
    like_count INTEGER,
    embed_url TEXT,
    playable_url TEXT,
    tags TEXT,
    score REAL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, source_id)
);
"""


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    try:
        conn.executescript(SCHEMA)
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(videos)").fetchall()
        }
        columns = {
            "url": "TEXT",
            "title": "TEXT",
            "channel": "TEXT",
            "description": "TEXT",
            "duration_seconds": "INTEGER",
            "published_at": "TEXT",
            "thumbnail_url": "TEXT",
            "view_count": "INTEGER",
            "like_count": "INTEGER",
            "embed_url": "TEXT",
            "playable_url": "TEXT",
            "tags": "TEXT",
            "score": "REAL",
            "created_at": "TEXT",
            "updated_at": "TEXT",
        }
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(
                    f"ALTER TABLE videos ADD COLUMN {name} {definition}"
                )
        conn.commit()
    finally:
        conn.close()


def _text(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(f"{_text(k)}: {_text(v)}" for k, v in value.items())
    return str(value)


def save_videos(videos):
    if not videos:
        return
    init_db()
    conn = _connect()
    try:
        for video in videos:
            conn.execute(
                """
                INSERT INTO videos (
                    source, source_id, url, title, channel, description,
                    duration_seconds, published_at, thumbnail_url,
                    view_count, like_count, embed_url, playable_url,
                    tags, score, created_at, updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                ON CONFLICT(source, source_id)
                DO UPDATE SET
                    url = excluded.url,
                    title = excluded.title,
                    channel = excluded.channel,
                    description = excluded.description,
                    duration_seconds = excluded.duration_seconds,
                    published_at = excluded.published_at,
                    thumbnail_url = excluded.thumbnail_url,
                    view_count = excluded.view_count,
                    like_count = excluded.like_count,
                    embed_url = excluded.embed_url,
                    playable_url = excluded.playable_url,
                    tags = excluded.tags,
                    score = excluded.score,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    _text(getattr(video, "source", "")),
                    _text(getattr(video, "source_id", "")),
                    _text(getattr(video, "url", "")),
                    _text(getattr(video, "title", "")),
                    _text(getattr(video, "channel", "")),
                    _text(getattr(video, "description", "")),
                    getattr(video, "duration_seconds", None),
                    _text(getattr(video, "published_at", "")),
                    _text(getattr(video, "thumbnail_url", "")),
                    getattr(video, "view_count", None),
                    getattr(video, "like_count", None),
                    _text(getattr(video, "embed_url", "")),
                    _text(getattr(video, "playable_url", "")),
                    _text(getattr(video, "tags", "")),
                    getattr(video, "score", 0.0),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def get_video(source: str, source_id: str):
    init_db()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM videos WHERE lower(source)=lower(?) AND source_id=?",
            (source, source_id),
        ).fetchone()
        if not row:
            return None

        from .models import Video
        return Video(
            source=row["source"],
            source_id=row["source_id"],
            url=row["url"] or "",
            title=row["title"] or "",
            channel=row["channel"] or "",
            description=row["description"] or "",
            duration_seconds=row["duration_seconds"],
            published_at=row["published_at"],
            thumbnail_url=row["thumbnail_url"] or "",
            view_count=row["view_count"],
            like_count=row["like_count"],
            embed_url=row["embed_url"] or "",
            playable_url=row["playable_url"] or "",
            tags=(row["tags"] or "").split(", ") if row["tags"] else [],
            score=row["score"] or 0.0,
        )
    finally:
        conn.close()
