import yt_dlp
import os
import asyncio

class YouTubeService:
    def __init__(self):
        self.YDL_OPTS = {
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
        
        # Check for cookies
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        COOKIE_PATH = os.path.join(current_dir, "cookies.txt")
        yt_cookies = os.getenv("YT_COOKIES")

        if yt_cookies:
            temp_cookie_path = os.path.join(current_dir, "cookies_env.txt")
            with open(temp_cookie_path, "w") as f:
                f.write(yt_cookies)
            self.YDL_OPTS["cookiefile"] = temp_cookie_path
        elif os.path.exists(COOKIE_PATH):
            self.YDL_OPTS["cookiefile"] = COOKIE_PATH

        self.ydl = yt_dlp.YoutubeDL(self.YDL_OPTS)

    async def get_stream_url(self, video_id: str):
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, lambda: self.ydl.extract_info(url, download=False))
            return info
        except Exception as e:
            print(f"Error fetching stream info: {e}")
            return None

yt_service = YouTubeService()
