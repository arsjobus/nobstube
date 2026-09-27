import logging
from contextlib import asynccontextmanager
from math import ceil
from urllib.parse import urlencode

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .database import get_video, init_db, save_videos
from .filtering.pipeline import SearchPipeline, VALID_SORTS
from .config import load_rules
from .media.playback import resolve_playback
from .models import Video

CANDIDATE_OPTIONS = (10, 25, 50, 75, 100)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/templates")
pipeline = SearchPipeline()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Filtered Video", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "videos": [],
            "query": "",
            "sort": "relevance",
            "page": 1,
            "pages": 0,
            "total": 0,
            "candidates_per_source": int(pipeline.rules.settings.get("candidates_per_source", 10)),
            "candidate_options": CANDIDATE_OPTIONS,
        },
    )


@app.get("/rules", response_class=HTMLResponse)
async def rules(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="rules.html",
        context={"rules": load_rules()},
    )


@app.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = "",
    sort: str = "relevance",
    page: int = 1,
    candidates_per_source: int | None = None,
):
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
    videos = all_videos[start:start + 10]

    # Save the complete candidate set, not just the visible page. This lets
    # /watch load metadata from SQLite instead of searching the source again.
    save_videos(all_videos)

    def page_url(number):
        return "/search?" + urlencode({
            "q": q,
            "sort": sort,
            "page": number,
            "candidates_per_source": candidates_per_source,
        })

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "videos": videos,
            "query": q,
            "sort": sort,
            "page": page,
            "candidates_per_source": candidates_per_source,
            "candidate_options": CANDIDATE_OPTIONS,
            "pages": pages,
            "total": total,
            "page_url": page_url,
        },
    )


@app.get("/watch/{source}/{source_id:path}", response_class=HTMLResponse)
async def watch(request: Request, source: str, source_id: str):
    # First use the local result cache/database. Do not perform another
    # expensive external search merely because the user opened a result.
    video = get_video(source, source_id)

    if video is None and source.lower() == "youtube":
        video = Video(
            source="YouTube",
            source_id=source_id,
            url=f"https://www.youtube.com/watch?v={source_id}",
            title="YouTube video",
            thumbnail_url=f"https://i.ytimg.com/vi/{source_id}/hqdefault.jpg",
            embed_url=f"https://www.youtube.com/embed/{source_id}",
        )

    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    video = await resolve_playback(video)

    return templates.TemplateResponse(
        request=request,
        name="watch.html",
        context={"video": video},
    )
