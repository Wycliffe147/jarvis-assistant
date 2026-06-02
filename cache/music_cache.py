import os
import json
import time
from jarvis.config import MUSIC_CACHE_FILE, MUSIC_CACHE_MAX_AGE, MUSIC_SEARCH_ROOTS, AUDIO_EXTENSIONS, COLOR_GRAY, COLOR_RESET

def _load_music_cache() -> list[str] | None:
    try:
        with open(MUSIC_CACHE_FILE, "r") as f:
            data = json.load(f)
        age = time.time() - data.get("timestamp", 0)
        if age < MUSIC_CACHE_MAX_AGE:
            return data.get("files", [])
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return None

def _save_music_cache(files: list[str]):
    try:
        with open(MUSIC_CACHE_FILE, "w") as f:
            json.dump({"timestamp": time.time(), "files": files}, f)
    except Exception as e:
        print(f"{COLOR_GRAY}[Cache write error: {e}]{COLOR_RESET}")

def _scan_music_files() -> list[str]:
    found = []
    for root in MUSIC_SEARCH_ROOTS:
        for dirpath, _, filenames in os.walk(root):
            for fname in filenames:
                if fname.lower().endswith(AUDIO_EXTENSIONS):
                    found.append(os.path.join(dirpath, fname))
    return found
