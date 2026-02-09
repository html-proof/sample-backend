import firebase_admin
from firebase_admin import credentials, db
import os

# Use the database URL provided by the user in their config
FIREBASE_DB_URL = "https://music-app-f2e65-default-rtdb.asia-southeast1.firebasedatabase.app"
SERVICE_ACCOUNT_FILE = "serviceAccountKey.json"

firebase_app = None

def init_firebase():
    global firebase_app
    if not firebase_admin._apps:
        # Construct absolute path to ensure it finds the file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        cert_path = os.path.join(current_dir, SERVICE_ACCOUNT_FILE)
        
        if not os.path.exists(cert_path):
            print(f"Warning: {SERVICE_ACCOUNT_FILE} not found at {cert_path}")
            return

        cred = credentials.Certificate(cert_path)
        firebase_app = firebase_admin.initialize_app(cred, {
            "databaseURL": FIREBASE_DB_URL
        })

# ---------------------------
# PLAY HISTORY
# ---------------------------
def get_user_play_history(user_id: str, limit: int = 50):
    init_firebase()
    if not firebase_admin._apps: return []
    
    ref = db.reference(f"play_history/{user_id}")
    data = ref.get()

    if not data:
        return []

    songs = []

    if isinstance(data, dict):
        items = list(data.values())

        # sort by timestamp if exists
        items_sorted = sorted(
            items,
            key=lambda x: x.get("timestamp", 0) if isinstance(x, dict) else 0
        )

        for item in items_sorted:
            if isinstance(item, dict):
                sid = item.get("song_id") or item.get("id") or item.get("track_id")
                if sid:
                    songs.append(str(sid))
            elif isinstance(item, str):
                songs.append(str(item))

    return songs[-limit:]


# ---------------------------
# SONG METADATA (Album + image)
# ---------------------------
def get_song_metadata(song_id: str):
    """
    Returns album + image if you stored it in Firebase.
    """
    init_firebase()
    if not firebase_admin._apps: return {}
    
    ref = db.reference(f"songs/{song_id}")
    data = ref.get()

    if not data:
        return {}

    return {
        "album": data.get("album"),
        "album_image": data.get("album_image"),
    }


# ---------------------------
# COLLECTIONS / PLAYLISTS
# ---------------------------
def get_user_collections(user_id: str):
    init_firebase()
    if not firebase_admin._apps: return {}
    
    ref = db.reference(f"collections/{user_id}")
    data = ref.get()
    return data if data else {}

def get_collection_songs(user_id: str, playlist_id: str):
    init_firebase()
    if not firebase_admin._apps: return []
    
    ref = db.reference(f"collections/{user_id}/{playlist_id}/songs")
    data = ref.get()

    if not data:
        return []

    # data may be list or dict
    if isinstance(data, list):
        return [str(x) for x in data]

    if isinstance(data, dict):
        return [str(v) for v in data.values()]

    return []
