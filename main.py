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
    "youtube_include_dash_manifest": True,
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
    "youtube_include_dash_manifest": True,
}

if COOKIE_PATH:
    STREAM_OPTS["cookiefile"] = COOKIE_PATH

stream_ydl = yt_dlp.YoutubeDL(STREAM_OPTS)

# Global session for connection pooling to reduce SSL handshake overhead
http_session = requests.Session()
# Set a browser-like User-Agent to avoid 403 Forbidden from YouTube
http_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})
adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20)
http_session.mount("https://", adapter)
http_session.mount("http://", adapter)


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
        
        for song in results:
            try:
                cached_url = await redis_client.get(f"stream:{song['id']}")
                if cached_url:
                    song["stream_url"] = cached_url
            except:
                pass

        vids = [s["id"] for s in results[:3] if s["id"]]
        background_tasks.add_task(prewarm_streams, vids)
        
        if request.method == "HEAD":
            return Response(status_code=200)
            
        from fastapi.responses import JSONResponse
        return JSONResponse(content=results)
    except Exception as e:
        print(f"Search failed: {e}")
        return JSONResponse(content=[])

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
            return Response(content=json.dumps({"error": str(e)}), status_code=500, media_type="application/json")

    # Pass through Range headers for super-fast browser buffering
    range_header = request.headers.get("Range")
    upstream_headers = {}
    if range_header:
        upstream_headers["Range"] = range_header

    # Pre-fetch headers from YouTube with one-time retry if 403/expired
    try:
        r = http_session.get(audio_url, headers=upstream_headers, stream=True, timeout=5)
        
        # If forbidden, the signature might have expired or UA was blocked
        if r.status_code == 403:
            r.close()
            print(f"URL expired or blocked (403). Re-extracting for {video_id}...")
            def re_extract(vid):
                info = stream_ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
                return info["url"]
            audio_url = await asyncio.to_thread(re_extract, video_id)
            await redis_client.setex(f"stream:{video_id}", 3600, audio_url)
            r = http_session.get(audio_url, headers=upstream_headers, stream=True, timeout=5)

        res_headers = {
            "Accept-Ranges": "bytes",
            "Content-Type": r.headers.get("Content-Type", "audio/mpeg"),
            "X-Accel-Buffering": "no",  # Tell proxies (nginx/railway) not to buffer
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
        if r.headers.get("Content-Range"):
            res_headers["Content-Range"] = r.headers.get("Content-Range")
        if r.headers.get("Content-Length"):
            res_headers["Content-Length"] = r.headers.get("Content-Length")
        
        status_code = r.status_code

        if request.method == "HEAD":
            r.close()
            return Response(status_code=status_code, headers=res_headers)

        def iter_content():
            try:
                # Tiny 8KB chunks for instant playback start
                for chunk in r.iter_content(chunk_size=8 * 1024):
                    if chunk:
                        yield chunk
            finally:
                r.close()


        return StreamingResponse(
            iter_content(),
            status_code=status_code,
            media_type=res_headers["Content-Type"],
            headers=res_headers
        )
    except Exception as e:
        print(f"Streaming failed: {e}")
        return Response(status_code=500)






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
                        
                        # Trigger pre-warming for the TOP 1 result only to save data
                        vids = [s["id"] for s in results[:1] if s["id"]]

                        background_tasks.add_task(prewarm_streams, vids)
            except Exception as e:
                await websocket.send_json({"type": "error", "message": str(e)})
    except WebSocketDisconnect:
        print("Client disconnected from WebSocket")

if __name__ == "__main__":

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)



