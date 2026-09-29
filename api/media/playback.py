import asyncio
import yt_dlp


async def resolve_playback(video):
    # YouTube is intentionally played through its official embedded player.
    # Nobstube does not download, proxy, or re-host YouTube media.
    if video.source == "YouTube":
        video.embed_url = f"https://www.youtube.com/embed/{video.source_id}"
        if not video.url:
            video.url = f"https://www.youtube.com/watch?v={video.source_id}"
        return video

    if video.playable_url:
        return video

    return video


async def resolve_ytdlp_playable_url(url: str):
    def run():
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "format": "best[ext=mp4]/best",
            "socket_timeout": 8,
            "retries": 0,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get("url")
        except Exception:
            return None

    return await asyncio.to_thread(run)
