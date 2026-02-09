import yt_dlp
import re
from typing import List, Dict, Any
import asyncio

class SearchService:
    def __init__(self):
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch',
        }

    def normalize(self, text: str) -> str:
        from services.trusted_channels import trusted_channels
        return trusted_channels.normalize(text)

    def contains_negative(self, title: str, query: str) -> bool:
        from services.trusted_channels import trusted_channels
        return trusted_channels.is_spam(title, query)

    def get_duration_score(self, seconds: int) -> int:
        if not seconds: return 0
        if seconds < 90: return -40
        if 120 <= seconds <= 420: return 30
        if 421 <= seconds <= 600: return 10
        if seconds > 900: return -30
        return 0

    def get_official_score(self, channel: str, title: str) -> int:
        from services.trusted_channels import trusted_channels
        return trusted_channels.calculate_trust_score(channel, title)

    def get_match_score(self, query: str, title: str) -> int:
        q = self.normalize(query)
        t = self.normalize(title)
        score = 0
        q_tokens = q.split()
        for token in q_tokens:
            if token in t:
                score += 15
        if q in t: score += 20
        return score

    def get_personal_context(self, user_id: str) -> Dict[str, Any]:
        if not user_id:
            return {"liked_artists": set(), "skipped_artists": set()}
        
        from services.firebase_db import firebase_db
        liked = firebase_db.get_liked_songs(user_id)
        # Liked artists extraction
        liked_artists = {self.normalize(s.get('artist', '')) for s in liked if s.get('artist')}
        skipped_artists = set()
        
        return {
            "liked_artists": liked_artists,
            "skipped_artists": skipped_artists
        }

    async def search_songs(self, query: str, limit: int = 10, user_id: str = None) -> List[Dict[str, Any]]:
        loop = asyncio.get_running_loop()
        
        # 1. Intent Detection (Language check)
        languages = ["malayalam", "hindi", "tamil", "english", "telugu", "kannada", "punjabi", "spanish", "korean"]
        q_norm = self.normalize(query)
        
        search_query = query
        if q_norm in languages:
            search_query = f"{query} songs official audio"

        # 2. Get User Context
        try:
            context = self.get_personal_context(user_id)
        except:
            context = {"liked_artists": set(), "skipped_artists": set()}
            
        liked_artists = context["liked_artists"]
        skipped_artists = context["skipped_artists"]

        def _blocking_search():
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                # Fetch more than needed to allow for personal ranking (Top 40)
                search_results = ydl.extract_info(f"ytsearch40:{search_query}", download=False)
                return search_results.get('entries', [])

        try:
            entries = await loop.run_in_executor(None, _blocking_search)
            
            candidates = []
            seen_ids = set()
            seen_titles_durations = []

            for entry in entries:
                if not entry or entry.get('id') in seen_ids:
                    continue
                
                title = entry.get('title', '').strip()
                channel = entry.get('uploader', '').strip()
                duration = entry.get('duration', 0)
                view_count = entry.get('view_count', 0)
                
                if self.contains_negative(title, search_query):
                    continue

                # --- ADVANCED FILTERING & AI SCORING ---
                from services.trusted_channels import trusted_channels
                
                # 1. Official/Basic Trust Score
                trust_score = self.get_official_score(channel, title)
                
                # 2. AI Classification Check
                ai_info = await trusted_channels.get_ai_trust_score(channel, [title])
                # We penalize news, movies, and gaming heavily
                # if trust_score already handled it via keywords, ai_info adds semantic weight
                
                if ai_info < 0: # Heavily penalized by AI (news, movies, etc.)
                    continue

                # Base score
                score = 0
                score += self.get_match_score(search_query, title)
                score += trust_score
                score += self.get_duration_score(duration)
                score += ai_info # Add AI semantic trust
                
                # Popularity boost
                if view_count and view_count > 10000000: score += 20
                elif view_count and view_count > 1000000: score += 10

                # --- PERSONALIZATION LAYER ---
                c_norm = self.normalize(channel)
                if c_norm in liked_artists:
                    score += 50 # Massive boost for favorite artists
                if c_norm in skipped_artists:
                    score -= 100 # Heavy penalty for skipped artists
                # -----------------------------
                
                # FINAL THRESHOLD: If it's not music/podcasts it should have a very low score
                # Discard anything with too low score to be legitimate audio
                if score < 20 and not any(k in title.lower() for k in ["song", "audio", "podcast", "music"]):
                    continue

                is_duplicate = False
                lower_title = title.lower()
                for existing_title, existing_duration in seen_titles_durations:
                    ed_raw = existing_duration or 0
                    if (lower_title in existing_title or existing_title in lower_title) and abs(duration - ed_raw) < 5:
                        is_duplicate = True
                        break
                
                if is_duplicate:
                    continue
                    
                candidates.append({
                    "id": entry.get('id'),
                    "title": title,
                    "artist": channel,
                    "channelId": entry.get('uploader_id'),
                    "duration": duration,
                    "thumbnail": entry.get('thumbnails', [{}])[0].get('url'),
                    "album": entry.get('album'),
                    "score": score
                })
                
                seen_ids.add(entry.get('id'))
                seen_titles_durations.append((lower_title, duration))

            candidates.sort(key=lambda x: x['score'], reverse=True)
            return candidates[:limit]
        except Exception as e:
            print(f"Error during search: {e}")
            return []

    async def resolve_track(self, title: str, artist: str):
        """Resolves a track title and artist to a YouTube Video ID."""
        query = f"{title} {artist} official audio"
        results = await self.search_songs(query, limit=1)
        if results:
            return results[0]["id"]
        return None

search_service = SearchService()
