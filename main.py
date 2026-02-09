from fastapi import FastAPI, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import requests
import asyncio
from functools import lru_cache
from typing import List, Dict

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Persistent yt-dlp instance for speed
YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "extract_flat": "in_playlist",
    "skip_download": True,
    "source_address": "0.0.0.0",
}
ydl_instance = yt_dlp.YoutubeDL(YDL_OPTS)
stream_ydl = yt_dlp.YoutubeDL({"format": "bestaudio/best", "quiet": True, "no_warnings": True})

# In-memory storage for pre-warmed stream URLs
stream_url_cache = {}

@app.get("/")
@app.get("/health")
def health():
    return {"status": "ok"}

async def prewarm_streams(video_ids: List[str]):
    """Background task to fetch stream URLs for top results."""
    for vid in video_ids:
        if vid not in stream_url_cache:
            try:
                # Run blocking extraction in a thread
                info = await asyncio.to_thread(
                    stream_ydl.extract_info, 
                    f"https://www.youtube.com/watch?v={vid}", 
                    download=False
                )
                stream_url_cache[vid] = info["url"]
            except Exception as e:
                print(f"Pre-warm failed for {vid}: {e}")

@lru_cache(maxsize=100)
def get_search_results(query: str) -> List[Dict]:
    result = ydl_instance.extract_info(f"ytsearch5:{query}", download=False)
    songs = []
    for entry in result.get("entries", []):
        songs.append({
            "title": entry.get("title"),
            "id": entry.get("id"),
            "duration": entry.get("duration"),
            "thumbnail": entry.get("thumbnail") or (entry.get("thumbnails")[0]["url"] if entry.get("thumbnails") else None)
        })
    return songs

@app.get("/search")
async def search_song(background_tasks: BackgroundTasks, q: str = Query(...)):
    results = await asyncio.to_thread(get_search_results, q)
    
    # Check if we have cached URLs for these items to include them directly
    for song in results:
        song["stream_url"] = stream_url_cache.get(song["id"])

    # Trigger pre-warming for the first 3 results in the background
    vids = [s["id"] for s in results[:3] if s["id"]]
    background_tasks.add_task(prewarm_streams, vids)
    return results

@app.get("/stream/{video_id}")
async def stream_audio(video_id: str):
    # Check if we already have it in the pre-warm cache
    audio_url = stream_url_cache.get(video_id)
    
    if not audio_url:
        # Fallback to manual extraction if not pre-warmed
        def get_audio_url(vid):
            info = stream_ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
            return info["url"]
        audio_url = await asyncio.to_thread(get_audio_url, video_id)
        stream_url_cache[video_id] = audio_url

    def audio_stream():
        with requests.get(audio_url, stream=True) as r:
            for chunk in r.iter_content(chunk_size=128 * 1024):
                if chunk:
                    yield chunk

    return StreamingResponse(audio_stream(), media_type="audio/mpeg")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


