import firebase_admin
from firebase_admin import credentials, db
import os
import json
import base64

# Use the database URL provided by the user in their config
FIREBASE_DB_URL = os.getenv("FIREBASE_DB_URL", "https://music-app-f2e65-default-rtdb.asia-southeast1.firebasedatabase.app")
SERVICE_ACCOUNT_FILE = "serviceAccountKey.json"

class FirebaseDB:
    def __init__(self):
        self.app = None
        self._init_firebase()

    def _init_firebase(self):
        if not firebase_admin._apps:
            # 1. Try Environment Variable (Base64 Encoded) - Best for Railway
            encoded_key = os.getenv("FIREBASE_SERVICE_ACCOUNT_BASE64")
            if encoded_key:
                try:
                    decoded = base64.b64decode(encoded_key)
                    cred_dict = json.loads(decoded)
                    cred = credentials.Certificate(cred_dict)
                    self.app = firebase_admin.initialize_app(cred, {
                        "databaseURL": FIREBASE_DB_URL
                    })
                    print("Firebase initialized via Environment Variable.")
                    return
                except Exception as e:
                    print(f"Failed to load Firebase from Env: {e}")

            # 2. Try Local File
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cert_path = os.path.join(current_dir, SERVICE_ACCOUNT_FILE)
            
            if os.path.exists(cert_path):
                try:
                    cred = credentials.Certificate(cert_path)
                    self.app = firebase_admin.initialize_app(cred, {
                        "databaseURL": FIREBASE_DB_URL
                    })
                    print("Firebase initialized via Local File.")
                except Exception as e:
                     print(f"Failed to load Firebase from Local File: {e}")
            else:
                print(f"Warning: Firebase credentials not found. DB operations will fail gracefully.")

    def get_play_history(self, user_id, limit=50):
        ref = db.reference(f"play_history/{user_id}")
        data = ref.get()
        if not data: return []
        
        # In current setup, it's a list of song IDs or objects
        songs = []
        if isinstance(data, dict):
            items = list(data.values())
            items_sorted = sorted(items, key=lambda x: x.get("timestamp", 0) if isinstance(x, dict) else 0)
            for item in items_sorted:
                if isinstance(item, dict):
                    songs.append(item)
                else:
                    songs.append({"video_id": str(item)})
        return songs[-limit:]

    def get_frequent_artists(self, user_id, limit=10):
        # Implementation of frequent artist logic
        # For now, we simulate this as it might require a complex query or post-processing
        history = self.get_play_history(user_id, limit=100)
        artists = {}
        for h in history:
            artist = h.get('artist')
            if artist:
                artists[artist] = artists.get(artist, 0) + 1
        
        sorted_artists = sorted(artists.items(), key=lambda x: x[1], reverse=True)
        return [a[0] for a in sorted_artists[:limit]]

    def get_liked_songs(self, user_id):
        ref = db.reference(f"likes/{user_id}")
        data = ref.get()
        if not data: return []
        if isinstance(data, dict):
            return list(data.values())
        return data

    def get_song_metadata(self, song_id: str):
        ref = db.reference(f"songs/{song_id}")
        data = ref.get()
        return data if data else {}

    def get_user_collections(self, user_id: str):
        try:
            ref = db.reference(f"collections/{user_id}")
            data = ref.get()
            return data if data else {}
        except Exception as e:
            print(f"Error fetching collections for {user_id}: {e}")
            return {}

firebase_db = FirebaseDB()
