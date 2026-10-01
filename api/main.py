import logging
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from math import ceil

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import load_rules
from .database import get_video, init_db, is_bookmarked, list_bookmarks, save_videos, set_bookmarked
from .filtering.pipeline import SearchPipeline, VALID_SORTS
from .media.playback import resolve_playback
from .models import Video

CANDIDATE_OPTIONS = (10, 25, 50, 75, 100)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
pipeline = SearchPipeline()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="NoBSTube API", version="1.0.0", lifespan=lifespan)
cors_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "PUT", "DELETE"],
    allow_headers=["*"],
)


def video_payload(video: Video) -> dict:
    payload = asdict(video)
    payload.update(duration_label=video.duration_label, views_label=video.views_label)
    return payload


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/config")
async def get_config():
    return {
        "rules": load_rules(),
        "candidate_options": CANDIDATE_OPTIONS,
        "default_candidates_per_source": int(pipeline.rules.settings.get("candidates_per_source", 10)),
        "sort_options": ["relevance", "newest", "oldest", "views_desc", "views_asc", "duration_asc", "duration_desc"],
    }


@app.get("/api/search")
async def search(q: str = "", sort: str = "relevance", page: int = 1, candidates_per_source: int | None = None):
    q = q.strip()
    sort = sort if sort in VALID_SORTS else "relevance"
    page = max(1, min(page, 10))
    if candidates_per_source is None:
        candidates_per_source = int(pipeline.rules.settings.get("candidates_per_source", 10))
    candidates_per_source = max(1, min(candidates_per_source, 100))
    if candidates_per_source not in CANDIDATE_OPTIONS:
        candidates_per_source = 10

    all_videos = await pipeline.search(q, sort, candidates_per_source) if q else []
    total = len(all_videos)
    pages = min(10, ceil(total / 10)) if total else 0
    if pages:
        page = min(page, pages)
    start = (page - 1) * 10
    save_videos(all_videos)
    return {
        "videos": [dict(video_payload(video), is_bookmarked=is_bookmarked(video.source, video.source_id)) for video in all_videos[start:start + 10]],
        "query": q,
        "sort": sort,
        "page": page,
        "pages": pages,
        "total": total,
        "candidates_per_source": candidates_per_source,
    }


@app.get("/api/bookmarks")
async def bookmarks(page: int = 1):
    page = max(1, page)
    videos, total = list_bookmarks(10, (page - 1) * 10)
    pages = ceil(total / 10) if total else 0
    if pages and page > pages:
        page = pages
        videos, total = list_bookmarks(10, (page - 1) * 10)
    return {"videos": [dict(video_payload(video), is_bookmarked=True) for video in videos], "page": page, "pages": pages, "total": total}


@app.put("/api/bookmarks/{source}/{source_id:path}")
async def add_bookmark(source: str, source_id: str):
    if not set_bookmarked(source, source_id, True):
        raise HTTPException(status_code=404, detail="Video not found")
    return {"bookmarked": True}


@app.delete("/api/bookmarks/{source}/{source_id:path}")
async def remove_bookmark(source: str, source_id: str):
    if not set_bookmarked(source, source_id, False):
        raise HTTPException(status_code=404, detail="Video not found")
    return {"bookmarked": False}


@app.get("/api/watch/{source}/{source_id:path}")
async def watch(source: str, source_id: str):
    video = get_video(source, source_id)
    if video is None and source.lower() == "youtube":
        video = Video(
            source="YouTube", source_id=source_id,
            url=f"https://www.youtube.com/watch?v={source_id}",
            title="YouTube video",
            thumbnail_url=f"https://i.ytimg.com/vi/{source_id}/hqdefault.jpg",
            embed_url=f"https://www.youtube.com/embed/{source_id}",
        )
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return dict(video_payload(await resolve_playback(video)), is_bookmarked=is_bookmarked(source, source_id))
