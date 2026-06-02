import os
import json
from jarvis.config import APP_ACTIVITY_CACHE_FILE, COLOR_GRAY, COLOR_RESET

def _load_activity_cache() -> dict:
    try:
        if os.path.exists(APP_ACTIVITY_CACHE_FILE):
            with open(APP_ACTIVITY_CACHE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    # Seed known explicit defaults to ensure native performance immediately
    return {
        "com.muso.musicplayer": "com.muso.musicplayer.MainActivity",
        "com.google.android.youtube": "com.google.android.youtube.MainActivity",
        "com.whatsapp": "com.whatsapp.Main",
        "com.android.chrome": "com.google.android.apps.chrome.Main",
        "com.termux": "com.termux.app.TermuxActivity",
        "com.android.settings": "com.android.settings.Settings"
    }

def _save_activity_cache(cache_data: dict):
    try:
        with open(APP_ACTIVITY_CACHE_FILE, "w") as f:
            json.dump(cache_data, f, indent=4)
    except Exception as e:
        print(f"{COLOR_GRAY}[Activity cache write error: {e}]{COLOR_RESET}")
