import subprocess
import os
from jarvis.config import MUSIC_APP, COLOR_GRAY, COLOR_RESET
from jarvis.cache.music_cache import _load_music_cache, _save_music_cache, _scan_music_files
from jarvis.cache.activity_cache import _load_activity_cache, _save_activity_cache

def speak(text: str):
    subprocess.run(["termux-tts-speak", text], stdin=subprocess.DEVNULL)
    return f"Spoke: {text}"

def tts_engines():
    result = subprocess.run(["termux-tts-engines"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def set_volume(stream: str = "music", volume: int = 5):
    subprocess.run(["termux-volume", stream, str(volume)], stdin=subprocess.DEVNULL)
    return f"Volume for {stream} set to {volume}"

def get_volume():
    result = subprocess.run(["termux-volume"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def play_media(file: str):
    subprocess.run(["am", "start", "-a", "android.intent.action.VIEW", "-d", f"file://{file}", "-t", "audio/*", "-p", MUSIC_APP], stdin=subprocess.DEVNULL)
    return f"Playing in Muso: {os.path.basename(file)}"

def stop_media():
    subprocess.run(["input", "keyevent", "KEYCODE_MEDIA_STOP"], stdin=subprocess.DEVNULL)
    return "Media stopped"

def pause_media():
    subprocess.run(["input", "keyevent", "KEYCODE_MEDIA_PLAY_PAUSE"], stdin=subprocess.DEVNULL)
    return "Play/Pause toggled"

def next_track():
    subprocess.run(["input", "keyevent", "KEYCODE_MEDIA_NEXT"], stdin=subprocess.DEVNULL)
    return "Skipped to next track"

def previous_track():
    subprocess.run(["input", "keyevent", "KEYCODE_MEDIA_PREVIOUS"], stdin=subprocess.DEVNULL)
    return "Went to previous track"

def get_media_info():
    result = subprocess.run(["termux-media-player", "info"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def find_music(query: str = "", refresh_cache: bool = False) -> str:
    all_files = None if refresh_cache else _load_music_cache()
    if all_files is None:
        print(f"{COLOR_GRAY}[Scanning storage for music...]{COLOR_RESET}")
        all_files = _scan_music_files()
        _save_music_cache(all_files)
        print(f"{COLOR_GRAY}[Music cache ready: {len(all_files)} files found]{COLOR_RESET}")
    else:
        print(f"{COLOR_GRAY}[Using music cache ({len(all_files)} files)]{COLOR_RESET}")

    if query:
        matches = [f for f in all_files if query.lower() in os.path.basename(f).lower()]
    else:
        matches = all_files

    if not matches:
        return f"No audio files found matching '{query}'." if query else "No audio files found on device."

    MAX_RESULTS = 20
    result_lines = matches[:MAX_RESULTS]
    suffix = f"\n(+{len(matches) - MAX_RESULTS} more not shown)" if len(matches) > MAX_RESULTS else ""
    return "\n".join(result_lines) + suffix

def open_music_app():
    """Uses explicit mapping cache validation to boot Muso reliably via component strings."""
    # This depends on open_app which is in apps.py. 
    # To avoid circular imports, I'll move open_app to a shared place or just import it locally.
    from jarvis.tools.apps import open_app
    return open_app(MUSIC_APP)

def stop_recording():
    subprocess.run(["termux-microphone-record", "-q"], stdin=subprocess.DEVNULL)
    return "Recording stopped"
