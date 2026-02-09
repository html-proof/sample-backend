import re
from typing import Dict, Any

class TrustedChannels:
    def __init__(self):
        self.trusted_keywords = ["topic", "vevo", "official", "records", "music", "entertainment"]
        self.spam_keywords = ["news", "politics", "speech", "interview", "comedy", "meme", "roast", 
                              "funny", "movie", "trailer", "scene", "dialogue", "short film", "vlog", 
                              "reaction", "review", "status", "whatsapp", "tiktok", "reels", "shorts"]

    def normalize(self, text: str) -> str:
        if not text: return ""
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', '', text)
        return text.strip()

    def is_spam(self, title: str, query: str) -> bool:
        title_norm = self.normalize(title)
        query_norm = self.normalize(query)
        if any(q in query_norm for q in ["news", "trailer", "interview"]):
            return False
            
        for word in self.spam_keywords:
            if word in title_norm:
                if word not in query_norm:
                    return True
        return False

    def calculate_trust_score(self, channel: str, title: str) -> int:
        score = 0
        channel_norm = self.normalize(channel)
        title_norm = self.normalize(title)
        
        if "topic" in channel_norm or "vevo" in channel_norm:
            score += 100
        
        if any(word in channel_norm for word in self.trusted_keywords):
            score += 40
            
        if "official" in title_norm:
            score += 30
            
        return score

    async def get_ai_trust_score(self, channel: str, recent_titles: list) -> int:
        """Leverages AI classifier for a more semantic trust score."""
        from services.ai_classifier import ai_classifier
        classification = await ai_classifier.classify_channel(channel, recent_titles)
        
        type_scores = {
            "official_artist": 100,
            "music_label": 80,
            "mixed": 40,
            "gaming": 10,
            "podcast": 0,
            "news": -100,
            "spam": -200,
            "movies": -100
        }
        
        ctype = classification.get("channel_type", "unknown")
        base_score = type_scores.get(ctype, 0)
        return int(base_score * classification.get("score", 1.0))

trusted_channels = TrustedChannels()
