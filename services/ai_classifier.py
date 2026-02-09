import json
import asyncio
import os
from typing import Dict, Any

class AIChannelClassifier:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        
    async def classify_channel(self, channel_name: str, recent_titles: list) -> Dict[str, Any]:
        """
        Classifies a YouTube channel based on metadata using an LLM.
        """
        if not self.api_key:
            return self._heuristic_classify(channel_name)
            
        prompt = f"""
        You are a YouTube channel classifier.
        Classify this channel based on its name and recent video titles.
        
        Channel Name: {channel_name}
        Recent Titles: {", ".join(recent_titles[:10])}
        
        Return JSON ONLY:
        {{
          "channel_type": "music_label" | "official_artist" | "podcast" | "news" | "movies" | "gaming" | "spam" | "mixed",
          "score": 0.0-1.0,
          "reason": "short explanation"
        }}
        """
        
        try:
            # Fallback to heuristic for now until API integration is live
            return self._heuristic_classify(channel_name)
        except Exception as e:
            print(f"AI Classification Error: {e}")
            return self._heuristic_classify(channel_name)

    def _heuristic_classify(self, channel_name: str) -> Dict[str, Any]:
        """Sophisticated heuristic fallback."""
        name = channel_name.lower()
        
        music_keywords = ["music", "records", "audios", "audio", "label", "topic", "vevo"]
        if any(k in name for k in music_keywords):
            return {"channel_type": "music_label", "score": 0.9, "reason": "Keyword match in name"}
            
        news_keywords = ["news", "live", "breaking", "times", "media"]
        if any(k in name for k in news_keywords):
            return {"channel_type": "news", "score": 0.95, "reason": "News keyword match"}
            
        movie_keywords = ["film", "movie", "trailers", "cinema"]
        if any(k in name for k in movie_keywords):
            return {"channel_type": "movies", "score": 0.9, "reason": "Movie keyword match"}

        return {"channel_type": "unknown", "score": 0.5, "reason": "Indeterminate"}

ai_classifier = AIChannelClassifier()
