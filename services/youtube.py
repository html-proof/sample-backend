import yt_dlp
import os
import asyncio
from asyncio import Semaphore

class YouTubeService:
    def __init__(self):
        self.YDL_OPTS = {
            "format": "bestaudio[abr<=128]/bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False, # Need full format extraction
            "skip_download": True,
            "nocheckcertificate": True,
            "youtube_include_dash_manifest": True, # Sometimes needed for bestaudio
            "no_color": True,
            "socket_timeout": 10, 
            "retries": 2, 
            "noplaylist": True,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "extractor_args": {
                "youtube": {
                    "player_client": ["android"]
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
        
        # Limit parallel extractions to prevent OOM on Railway (512MB RAM)
        self.semaphore = Semaphore(2)

    def get_opts(self):
        opts = self.YDL_OPTS.copy()
        # Ensure fresh cookies are always used if file exists
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if os.path.exists(os.path.join(current_dir, "cookies_env.txt")):
            opts["cookiefile"] = os.path.join(current_dir, "cookies_env.txt")
        return opts

    async def get_stream_url(self, video_id: str):
        # Throttle parallel extractions
        async with self.semaphore:
            try:
                url = f"https://www.youtube.com/watch?v={video_id}"
                loop = asyncio.get_event_loop()
                
                # Use fresh instance for each request to avoid session flagging
                opts = self.get_opts()
                def extract():
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(url, download=False)
                
                info = await loop.run_in_executor(None, extract)
                return info
            except Exception as e:
                print(f"Error fetching stream info for {video_id}: {e}")
                return None

yt_service = YouTubeService()
