from fastapi import FastAPI, Query, BackgroundTasks, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis
import json
import os
import asyncio
from typing import List, Dict

# New Service-Oriented Architecture
from services.search import search_service
from services.youtube import yt_service
from services.recommendation import recommendation_service
from services.firebase_db import firebase_db
from services.spotify_recommender import spotify_recommender
from services.device_manager import device_manager

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis connection
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
            if not await redis_client.get(f"stream:{vid}"):
                info = await yt_service.get_stream_url(vid)
                if info and "url" in info:
                    await redis_client.setex(f"stream:{vid}", 3600, info["url"])
        except Exception as e:
            print(f"Redis pre-warm failed/skipped: {e}")

@app.api_route("/search", methods=["GET", "HEAD"])
async def search_song(request: Request, background_tasks: BackgroundTasks, q: str = Query(...), user_id: str = "guest"):
    try:
        cache_key = f"search:{q.lower()}:{user_id}"
        cached = await redis_client.get(cache_key)
        
        if cached:
            results = json.loads(cached)
        else:
            results = await search_service.search_songs(q, user_id=user_id)
            await redis_client.setex(cache_key, 3600, json.dumps(results))
        
        # Enrich with stream URLs and trigger pre-warm
        vids = []
        for song in results:
            sid = song.get("id")
            if sid:
                cached_url = await redis_client.get(f"stream:{sid}")
                if cached_url:
                    song["stream_url"] = cached_url
                elif len(vids) < 3:
                    vids.append(sid)

        if vids:
            background_tasks.add_task(prewarm_streams, vids)
        
        if request.method == "HEAD":
            return Response(status_code=200)
            
        return JSONResponse(content=results)
    except Exception as e:
        print(f"Search failed: {e}")
        return JSONResponse(content=[])

@app.get("/suggestions")
async def suggestions(q: str = Query(...), user_id: str = "guest"):
    cache_key = f"suggest:{q.lower()}:{user_id}"
    try:
        cached = await redis_client.get(cache_key)
        if cached: return json.loads(cached)
        
        results = await search_service.search_songs(q, limit=5, user_id=user_id)
        formatted = [{
            "id": s["id"],
            "title": s["title"],
            "thumbnail": s["thumbnail"],
            "duration": s["duration"],
            "type": "suggestion"
        } for s in results]
        
        await redis_client.setex(cache_key, 1800, json.dumps(formatted))
        return formatted
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.api_route("/stream/{video_id}", methods=["GET", "HEAD"])
async def stream_audio(request: Request, video_id: str):
    audio_url = await redis_client.get(f"stream:{video_id}")
    
    if not audio_url:
        info = await yt_service.get_stream_url(video_id)
        if not info or "url" not in info:
            print(f"Extraction failed for {video_id}")
            return JSONResponse(status_code=500, content={"error": "Failed to extract stream URL"})

        audio_url = info["url"]
        # Cache for 1 hour
        await redis_client.setex(f"stream:{video_id}", 3600, audio_url)

    # Proxying logic
    import requests
    http_session = requests.Session()
    # Use the same User-Agent as yt-dlp to avoid basic blocking
    http_session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    })
    
    range_header = request.headers.get("Range")
    headers = {"Range": range_header} if range_header else {}
    
    try:
        r = http_session.get(audio_url, headers=headers, stream=True, timeout=10)
        
        # specific handling for 403 (expired link or IP block)
        if r.status_code == 403:
            print(f"Stream 403 Forbidden for {video_id}, refreshing URL...")
            r.close()
            # Force refresh extraction
            info = await yt_service.get_stream_url(video_id)
            if info and "url" in info:
                audio_url = info["url"]
                await redis_client.setex(f"stream:{video_id}", 3600, audio_url)
                r = http_session.get(audio_url, headers=headers, stream=True, timeout=10)
            else:
                return JSONResponse(status_code=403, content={"error": "Stream expired or blocked"})

        if r.status_code != 200 and r.status_code != 206:
             print(f"Upstream returned status {r.status_code}")
             return JSONResponse(status_code=502, content={"error": "Upstream stream error"})

        res_headers = {
            "Accept-Ranges": "bytes",
            "Content-Type": r.headers.get("Content-Type", "audio/mpeg"),
            "X-Accel-Buffering": "no", # Disable Nginx buffering if present
            "Cache-Control": "no-cache, no-store, must-revalidate",
        }
        if r.headers.get("Content-Range"): res_headers["Content-Range"] = r.headers.get("Content-Range")
        if r.headers.get("Content-Length"): res_headers["Content-Length"] = r.headers.get("Content-Length")
        
        # HEAD request optimization
        if request.method == "HEAD":
            r.close()
            return Response(status_code=r.status_code, headers=res_headers)

        async def iter_content():
            try:
                # Use smaller chunks for smoother streaming start
                for chunk in r.iter_content(chunk_size=32 * 1024):
                    if chunk: yield chunk
            except Exception as e:
                print(f"Stream chunk error: {e}")
            finally:
                r.close()

        return StreamingResponse(iter_content(), status_code=r.status_code, media_type=res_headers["Content-Type"], headers=res_headers)
    except Exception as e:
        print(f"Streaming critical failure: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

# Recommendation Endpoints
@app.get("/recommend/user/{user_id}")
async def recommend_user(user_id: str):
    recos = await recommendation_service.get_personalized_recommendations(user_id)
    return {"user_id": user_id, "recommendations": recos}

@app.get("/recommend/song/{song_id}")
async def recommend_song(song_id: str, user_id: str = "guest"):
    res = await recommendation_service.get_recent_context(user_id)
    return res

@app.get("/recommend/trending")
async def trending():
    recos = spotify_recommender.get_trending(top_n=20)
    return {"recommendations": recos}

@app.get("/recommend/daily/{user_id}")
async def daily_mix(user_id: str):
    recos = await recommendation_service.get_daily_mix(user_id)
    return {"user_id": user_id, "recommendations": recos}

@app.get("/collections/{user_id}")
async def collections(user_id: str):
    return {"collections": firebase_db.get_user_collections(user_id)}

# Device Management Endpoints
@app.post("/devices/register")
async def register_device(request: Request):
    data = await request.json()
    success = device_manager.register_device(
        data.get("user_id"), 
        data.get("device_id"), 
        data.get("device_info", {})
    )
    return {"success": success}

@app.get("/devices/{user_id}")
async def get_devices(user_id: str):
    return {"devices": device_manager.get_user_devices(user_id)}

@app.post("/devices/active")
async def set_active_device(request: Request):
    data = await request.json()
    success = device_manager.set_active_device(data.get("user_id"), data.get("device_id"))
    return {"success": success}

@app.websocket("/ws/music")
async def websocket_endpoint(websocket: WebSocket, background_tasks: BackgroundTasks):
    await websocket.accept()
    user_id = "guest"
    device_id = None
    
    try:
        while True:
            data = await websocket.receive_text()
            req = json.loads(data)
            
            if req.get("type") == "auth":
                user_id = req.get("user_id", "guest")
                device_id = req.get("device_id")
            
            elif req.get("type") == "ping":
                if device_id:
                    device_manager.update_device_heartbeat(user_id, device_id)
                await websocket.send_json({"type": "pong"})

            elif req.get("type") == "search":
                results = await search_service.search_songs(req.get("query"), user_id=user_id)
                await websocket.send_json({"type": "search_results", "results": results})
                if results:
                    background_tasks.add_task(prewarm_streams, [results[0]["id"]])
            
            elif req.get("type") == "autocomplete":
                results = await search_service.search_songs(req.get("query"), limit=5, user_id=user_id)
                await websocket.send_json({"type": "suggestions", "results": results})
    except WebSocketDisconnect:
        pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
