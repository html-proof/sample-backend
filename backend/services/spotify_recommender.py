import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity
import os

class SpotifyRecommender:
    def __init__(self, csv_path: str = "data/data.csv"):
        self.csv_path = csv_path
        self.df = None
        self.features = None
        self.scaler = StandardScaler()
        self.song_matrix = None
        self.enabled = False

        self.feature_cols = [
            "danceability", "energy", "key", "loudness", "mode",
            "speechiness", "acousticness", "instrumentalness",
            "liveness", "valence", "tempo"
        ]

        if os.path.exists(self.csv_path):
            try:
                self.load_data()
                self.enabled = True
                print(f"✅ Spotify Recommender Initialized (Offline Mode) with {len(self.df)} songs.")
            except Exception as e:
                print(f"❌ Failed to load Spotify dataset: {e}")
        else:
            print(f"⚠️ Spotify dataset not found at {self.csv_path}. Advanced offline features disabled.")

    def load_data(self):
        self.df = pd.read_csv(self.csv_path)
        self.df = self.df.dropna(subset=self.feature_cols)

        if "id" not in self.df.columns:
            self.df["id"] = self.df.index.astype(str)

        self.features = self.df[self.feature_cols].values
        self.song_matrix = self.scaler.fit_transform(self.features)

    def get_song_by_id(self, song_id: str):
        if not self.enabled: return None
        # Handle string matching carefully
        row = self.df[self.df["id"].astype(str) == str(song_id)]
        if row.empty:
            return None
        return row.iloc[0].to_dict()

    def recommend_similar_songs(self, song_id: str, top_n: int = 20):
        if not self.enabled: return []
        
        song_index = self.df.index[self.df["id"].astype(str) == str(song_id)]
        if len(song_index) == 0:
            return []

        song_index = song_index[0]
        try:
            song_vector = self.song_matrix[song_index].reshape(1, -1)
            sims = cosine_similarity(song_vector, self.song_matrix)[0]
            top_indices = np.argsort(sims)[::-1][1:top_n+1]
            return self._format_results(top_indices, sims)
        except Exception as e:
            print(f"Error in recommend_similar_songs: {e}")
            return []

    def recommend_for_user(self, played_song_ids: list, top_n: int = 20):
        if not self.enabled: return self.get_trending(top_n)
        if not played_song_ids:
            return self.get_trending(top_n)

        indices = []
        for sid in played_song_ids:
            idx = self.df.index[self.df["id"].astype(str) == str(sid)]
            if len(idx) > 0:
                indices.append(idx[0])

        if len(indices) == 0:
            return self.get_trending(top_n)

        try:
            user_vector = np.mean(self.song_matrix[indices], axis=0).reshape(1, -1)
            sims = cosine_similarity(user_vector, self.song_matrix)[0]

            played_set = set(map(str, played_song_ids))
            ranked = np.argsort(sims)[::-1]

            results = []
            for i in ranked:
                sid = str(self.df.iloc[i]["id"])
                if sid not in played_set:
                    results.append(i)
                if len(results) >= top_n:
                    break

            return self._format_results(results, sims)
        except Exception as e:
            print(f"Error in recommend_for_user: {e}")
            return self.get_trending(top_n)

    def recommend_for_collection(self, playlist_song_ids: list, top_n: int = 30):
        """
        This gives recommendations based on a playlist/collection.
        """
        return self.recommend_for_user(playlist_song_ids, top_n=top_n)

    def get_trending(self, top_n: int = 20):
        if not self.enabled: return []
        
        if "popularity" in self.df.columns:
            top = self.df.sort_values("popularity", ascending=False).head(top_n)
            return top[["id", "name", "artists", "year", "popularity"]].to_dict(orient="records")

        top = self.df.sample(min(top_n, len(self.df)))
        return top[["id", "name", "artists", "year"]].to_dict(orient="records")

    def _format_results(self, indices, sims):
        output = []
        for i in indices:
            row = self.df.iloc[i]
            year = row.get("year")
            pop = row.get("popularity")
            output.append({
                "id": str(row["id"]),
                "name": row.get("name"),
                "artists": row.get("artists"),
                "year": int(year) if pd.notna(year) and not isinstance(year, str) else None,
                "popularity": int(pop) if pd.notna(pop) and not isinstance(pop, str) else None,
                "similarity_score": float(sims[i])
            })
        return output

# Instantiate singleton
spotify_recommender = SpotifyRecommender()
