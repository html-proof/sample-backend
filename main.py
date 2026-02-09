from fastapi import FastAPI, Query
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

@app.get("/")
@app.get("/health")
def health():
    return {"status": "ok"}

# Optimized options for speed
YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "extract_flat": "in_playlist", # Don't extract full info for speed
    "skip_download": True,
    "source_address": "0.0.0.0", # Can help with some connection issues
}

# Cache results for 1 hour (approx)
@lru_cache(maxsize=100)
def get_search_results(query: str) -> List[Dict]:
    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        result = ydl.extract_info(f"ytsearch5:{query}", download=False)
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
async def search_song(q: str = Query(...)):
    # Run the blocking yt-dlp call in a separate thread
    return await asyncio.to_thread(get_search_results, q)

@app.get("/stream/{video_id}")
async def stream_audio(video_id: str):
    def get_audio_url(vid):
        # We need the full info for streaming, but we only do it for one video
        with yt_dlp.YoutubeDL({"format": "bestaudio/best", "quiet": True}) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
            return info["url"]

    audio_url = await asyncio.to_thread(get_audio_url, video_id)

    def audio_stream():
        # Using a larger chunk size for smoother streaming
        with requests.get(audio_url, stream=True) as r:
            for chunk in r.iter_content(chunk_size=128 * 1024):
                if chunk:
                    yield chunk

    return StreamingResponse(audio_stream(), media_type="audio/mpeg")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

