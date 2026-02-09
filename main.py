from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import requests

app = FastAPI()

# Add CORS middleware to allow requests from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the actual frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
@app.get("/health")
def health():
    return {"status": "ok"}

YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "skip_download": True,
}

@app.get("/search")
def search_song(q: str = Query(...)):
    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        result = ydl.extract_info(f"ytsearch5:{q}", download=False)
        songs = []

        for entry in result["entries"]:
            songs.append({
                "title": entry["title"],
                "id": entry["id"],
                "duration": entry["duration"],
                "thumbnail": entry["thumbnail"]
            })

        return songs


@app.get("/stream/{video_id}")
def stream_audio(video_id: str):
    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        info = ydl.extract_info(
            f"https://www.youtube.com/watch?v={video_id}",
            download=False
        )
        audio_url = info["url"]

    def audio_stream():
        r = requests.get(audio_url, stream=True)
        for chunk in r.iter_content(chunk_size=1024 * 32):
            if chunk:
                yield chunk

    return StreamingResponse(audio_stream(), media_type="audio/mpeg")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
