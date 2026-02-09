from fastapi import FastAPI, Query, BackgroundTasks, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import requests
import asyncio
import os
import json
import redis.asyncio as redis
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

# Persistent yt-dlp instance with extreme speed optimizations
YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "extract_flat": "in_playlist",
    "skip_download": True,
    "source_address": "0.0.0.0",
    "nocheckcertificate": True,
    "youtube_include_dash_manifest": False,
    "youtube_include_hls_manifest": False,
    "no_color": True,
}

# Check for cookies (file or environment variable)
COOKIE_PATH = "cookies.txt"
yt_cookies = os.getenv("YT_COOKIES")

if yt_cookies:
    with open("cookies_env.txt", "w") as f:
        f.write(yt_cookies)
    COOKIE_PATH = "cookies_env.txt"
elif os.path.exists("cookies.txt"):
    pass
else:
    COOKIE_PATH = None

if COOKIE_PATH:
    YDL_OPTS["cookiefile"] = COOKIE_PATH

ydl_instance = yt_dlp.YoutubeDL(YDL_OPTS)

STREAM_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "youtube_include_dash_manifest": False,
    "youtube_include_hls_manifest": False,
}
if COOKIE_PATH:
    STREAM_OPTS["cookiefile"] = COOKIE_PATH

stream_ydl = yt_dlp.YoutubeDL(STREAM_OPTS)




# Redis connection with connection timeout
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=5, socket_connect_timeout=5)

@app.get("/")
@app.get("/health")
def health():
    return {"status": "ok"}

async def prewarm_streams(video_ids: List[str]):
    """Background task to fetch stream URLs for top results."""
    for vid in video_ids:
        try:
            # Check Redis first
            if not await redis_client.get(f"stream:{vid}"):
                info = await asyncio.to_thread(
                    stream_ydl.extract_info, 
                    f"https://www.youtube.com/watch?v={vid}", 
                    download=False
                )
                await redis_client.setex(f"stream:{vid}", 3600, info["url"])
        except Exception as e:
            # If Redis fails, we just don't pre-warm or cache
            print(f"Redis pre-warm failed/skipped: {e}")

async def get_search_results(query: str) -> List[Dict]:
    cache_key = f"search:{query.lower()}"
    try:
        cached_results = await redis_client.get(cache_key)
        if cached_results:
            return json.loads(cached_results)
    except Exception as e:
        print(f"Redis cache read failed: {e}")

    result = await asyncio.to_thread(ydl_instance.extract_info, f"ytsearch5:{query}", download=False)
    songs = []
    for entry in result.get("entries", []):
        songs.append({
            "title": entry.get("title"),
            "id": entry.get("id"),
            "duration": entry.get("duration"),
            "thumbnail": entry.get("thumbnail") or (entry.get("thumbnails")[0]["url"] if entry.get("thumbnails") else None)
        })
    
    try:
        await redis_client.setex(cache_key, 3600, json.dumps(songs))
    except Exception as e:
        print(f"Redis cache write failed: {e}")
        
    return songs

@app.api_route("/search", methods=["GET", "HEAD"])
async def search_song(request: Request, background_tasks: BackgroundTasks, q: str = Query(...)):
    try:
        results = await get_search_results(q)
        
        # Check if we have cached URLs in Redis for these items
        for song in results:
            try:
                cached_url = await redis_client.get(f"stream:{song['id']}")
                if cached_url:
                    song["stream_url"] = cached_url
            except:
                pass

        # Trigger pre-warming for the first 3 results
        vids = [s["id"] for s in results[:3] if s["id"]]
        background_tasks.add_task(prewarm_streams, vids)
        
        if request.method == "HEAD":
            return Response(status_code=200)
            
        return results
    except Exception as e:
        print(f"Search failed: {e}")
        return []

@app.api_route("/stream/{video_id}", methods=["GET", "HEAD"])
async def stream_audio(request: Request, video_id: str):
    audio_url = None
    try:
        audio_url = await redis_client.get(f"stream:{video_id}")
    except:
        pass
    
    if not audio_url:
        def get_audio_url(vid):
            info = stream_ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
            return info["url"]
        try:
            audio_url = await asyncio.to_thread(get_audio_url, video_id)
            try:
                await redis_client.setex(f"stream:{video_id}", 3600, audio_url)
            except:
                pass
        except Exception as e:
            print(f"Extraction failed: {e}")
            return {"error": "Could not extract audio"}

    if request.method == "HEAD":
        return Response(status_code=200)

    def audio_stream():
        with requests.get(audio_url, stream=True) as r:
            for chunk in r.iter_content(chunk_size=128 * 1024):
                if chunk:
                    yield chunk

    return StreamingResponse(audio_stream(), media_type="audio/mpeg")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, background_tasks: BackgroundTasks):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            try:
                request_data = json.loads(data)
                if request_data.get("type") == "search":
                    query = request_data.get("query")
                    if query:
                        results = await get_search_results(query)
                        # Enrich with cached stream URLs
                        for song in results:
                            cached_url = await redis_client.get(f"stream:{song['id']}")
                            if cached_url:
                                song["stream_url"] = cached_url
                        
                        await websocket.send_json({
                            "type": "search_results",
                            "query": query,
                            "results": results
                        })
                        
                        # Trigger pre-warming
                        vids = [s["id"] for s in results[:3] if s["id"]]
                        background_tasks.add_task(prewarm_streams, vids)
            except Exception as e:
                await websocket.send_json({"type": "error", "message": str(e)})
    except WebSocketDisconnect:
        print("Client disconnected from WebSocket")

if __name__ == "__main__":

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)



