import yt_dlp
import os
import asyncio

class YouTubeService:
    def __init__(self):
        self.YDL_OPTS = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
            "nocheckcertificate": True,
            "youtube_include_dash_manifest": False,
            "youtube_include_hls_manifest": False,
            "no_color": True,
            "socket_timeout": 5, 
            "retries": 1, 
            "noplaylist": True,
            "lazy_playlist": True,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "extractor_args": {
                "youtube": {
                    "player_client": ["web"]
                }
            }
        }
        
        # Check for cookies (Base64 preferred for Env Vars)
        import base64
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        encoded_cookies = os.getenv("YT_COOKIES_BASE64")
        raw_cookies = os.getenv("YT_COOKIES")
        
        if encoded_cookies:
            try:
                decoded = base64.b64decode(encoded_cookies).decode('utf-8')
                cookie_path = os.path.join(current_dir, "cookies_env.txt")
                with open(cookie_path, "w") as f:
                    f.write(decoded)
                self.YDL_OPTS["cookiefile"] = cookie_path
                print(f"Loaded cookies from YT_COOKIES_BASE64")
            except Exception as e:
                print(f"Failed to decode YT_COOKIES_BASE64: {e}")

        elif raw_cookies:
            cookie_path = os.path.join(current_dir, "cookies_env.txt")
            with open(cookie_path, "w") as f:
                f.write(raw_cookies)
            self.YDL_OPTS["cookiefile"] = cookie_path
            print(f"Loaded cookies from YT_COOKIES")

        elif os.path.exists(os.path.join(current_dir, "cookies.txt")):
            self.YDL_OPTS["cookiefile"] = os.path.join(current_dir, "cookies.txt")
            print(f"Loaded local cookies.txt")

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
