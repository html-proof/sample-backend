from typing import List, Dict, Any
import random
from services.firebase_db import firebase_db
from services.search import search_service
from services.youtube import yt_service
from services.ml_recommender import ml_recommender
from services.spotify_recommender import spotify_recommender
import asyncio

class RecommendationService:
    async def get_personalized_recommendations(self, user_id: str):
        recommendations = []
        seen_ids = set()
        
        # 1. Try ML (ALS) Recommendations First
        try:
            if ml_recommender.enabled:
                ml_results = ml_recommender.get_als_recommendations(user_id)
                for vid in ml_results:
                    res = await search_service.search_songs(vid, limit=1, user_id=user_id)
                    if res and res[0]['id'] not in seen_ids:
                        recommendations.append(res[0])
                        seen_ids.add(res[0]['id'])
        except Exception as e:
            print(f"ML Rec failed: {e}")

        # 2. Strategy A: Based on Favorite Artists
        try:
            top_artists = firebase_db.get_frequent_artists(user_id, limit=5)
            user_likes = firebase_db.get_liked_songs(user_id)
            for s in user_likes:
                seen_ids.add(s.get('id') or s.get('video_id'))
        except Exception as e:
            print(f"Error fetching user profile: {e}")
            top_artists = []

        if top_artists and len(recommendations) < 20:
            for artist in top_artists:
                results = await search_service.search_songs(f"best of {artist}", limit=5, user_id=user_id)
                for song in results:
                    if song['id'] not in seen_ids:
                        recommendations.append(song)
                        seen_ids.add(song['id'])
                if len(recommendations) >= 30: break

        # 3. Strategy B: Spotify Recommender (Content-Based)
        if spotify_recommender.enabled and len(recommendations) < 20:
            history = firebase_db.get_play_history(user_id, limit=10)
            history_ids = [h.get('song_id') or h.get('video_id') for h in history if h.get('song_id') or h.get('video_id')]
            
            spotify_recs = spotify_recommender.recommend_for_user(history_ids, top_n=15)
            if spotify_recs:
                for rec in spotify_recs:
                    recommendations.append({
                        "id": rec['id'],
                        "title": rec['name'],
                        "artist": rec['artists'],
                        "is_spotify": True,
                        "needs_resolution": True
                    })

        # 4. Strategy C: Fill with trending
        if len(recommendations) < 20:
            fillers = await search_service.search_songs("latest music hits 2024", limit=10, user_id=user_id)
            for song in fillers:
                if song['id'] not in seen_ids:
                    recommendations.append(song)
                    seen_ids.add(song['id'])
        
        return recommendations[:30]

    async def get_daily_mix(self, user_id: str):
        try:
            top_artists = firebase_db.get_frequent_artists(user_id, limit=30)
            if not top_artists:
                return await search_service.search_songs("lofi chill beats for study", limit=12, user_id=user_id)
            
            primary_artist = top_artists[0]
            return await search_service.search_songs(f"{primary_artist} essential mix", limit=12, user_id=user_id)
        except:
            return []

    async def get_recent_context(self, user_id: str):
        try:
            history = firebase_db.get_play_history(user_id, limit=1)
            if not history: return {"last_song": None, "recommendations": []}
                
            last_song = history[0]
            video_id = last_song.get('song_id') or last_song.get('video_id')
            recommendations = []
            seen_ids = {video_id}

            # Similarity via Search
            search_query = f"songs similar to {last_song.get('title')} {last_song.get('artist')}"
            results = await search_service.search_songs(search_query, limit=12, user_id=user_id)
            for s in results:
                if s['id'] not in seen_ids:
                    recommendations.append(s)
                    seen_ids.add(s['id'])
            
            return {
                "last_song": last_song,
                "recommendations": recommendations[:12]
            }
        except Exception as e:
            print(f"Error in context rec: {e}")
            return {"last_song": None, "recommendations": []}

    async def get_autoplay_next(self, user_id: str, current_song_id: str) -> List[Dict[str, Any]]:
        try:
            seen_ids = {current_song_id}
            # Similarity keywords
            search_query = f"songs similar to current track {current_song_id}"
            results = await search_service.search_songs(search_query, limit=5, user_id=user_id)
            candidates = [s for s in results if s['id'] not in seen_ids]
            if candidates: return candidates[:3]

            # Fallback
            return await search_service.search_songs("top hits global 2024", limit=3, user_id=user_id)
        except Exception as e:
            print(f"Autoplay Error: {e}")
            return []

recommendation_service = RecommendationService()
