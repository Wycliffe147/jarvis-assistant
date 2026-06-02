from jarvis.tools.device import vibrate, get_battery_status, torch, set_brightness, get_sensor
from jarvis.tools.media import speak, tts_engines, set_volume, get_volume, play_media, stop_media, pause_media, next_track, previous_track, get_media_info, find_music, open_music_app, stop_recording
from jarvis.tools.comms import send_sms, list_sms, get_call_log, get_contacts, find_contact, make_call, open_dialer
from jarvis.tools.system import get_clipboard, set_clipboard, show_notification, remove_notification, set_wallpaper, show_dialog, fingerprint_auth, show_toast, share
from jarvis.tools.network import open_url, get_wifi_info, scan_wifi, get_location, get_device_info, get_cell_info
from jarvis.tools.camera import take_photo, analyze_photo, local_ocr
from jarvis.tools.apps import list_apps, open_app, search_launcher_apps

TOOLS = {
    "vibrate":             vibrate,
    "get_battery_status":  get_battery_status,
    "speak":               speak,
    "show_toast":          show_toast,
    "torch":               torch,
    "set_volume":          set_volume,
    "get_volume":          get_volume,
    "show_notification":   show_notification,
    "remove_notification": remove_notification,
    "get_clipboard":       get_clipboard,
    "set_clipboard":       set_clipboard,
    "open_url":            open_url,
    "get_location":        get_location,
    "get_wifi_info":       get_wifi_info,
    "scan_wifi":           scan_wifi,
    "get_device_info":     get_device_info,
    "get_cell_info":       get_cell_info,
    "send_sms":            send_sms,
    "list_sms":            list_sms,
    "get_call_log":        get_call_log,
    "get_contacts":        get_contacts,
    "find_contact":        find_contact,
    "set_brightness":      set_brightness,
    "take_photo":          take_photo,
    "analyze_photo":       analyze_photo,
    "local_ocr":           local_ocr,
    "list_apps":           list_apps,
    "open_app":            open_app,
    "search_launcher_apps": search_launcher_apps,
    "find_music":          find_music,
    "play_media":          play_media,
    "stop_media":          stop_media,
    "pause_media":         pause_media,
    "next_track":          next_track,
    "previous_track":      previous_track,
    "open_music_app":      open_music_app,
    "get_media_info":      get_media_info,
    "make_call":           make_call,
    "open_dialer":         open_dialer,
    "share":               share,
    "set_wallpaper":       set_wallpaper,
    "show_dialog":         show_dialog,
    "fingerprint_auth":    fingerprint_auth,
    "get_sensor":          get_sensor,
    "tts_engines":         tts_engines,
}

DATA_TOOLS = {
    "get_battery_status", "get_volume", "get_clipboard", "get_location",
    "get_wifi_info", "scan_wifi", "get_device_info", "get_cell_info",
    "list_sms", "get_call_log", "get_contacts", "get_media_info",
    "get_sensor", "tts_engines", "show_dialog", "fingerprint_auth",
    "find_music", "find_contact", "analyze_photo", "local_ocr", "list_apps",
    "search_launcher_apps"
}

TOOLS_DESCRIPTION = """
vibrate(duration_ms)             - Vibrate the phone
get_battery_status()             - Get battery level, health, temp, charging status
speak(text)                      - Speak text aloud via TTS
show_toast(message)              - Show a brief toast popup
torch(status)                    - Turn flashlight on/off (status: "on"/"off")
set_volume(stream, volume)       - Set volume (streams: music/ring/alarm/notification/system, 0-15)
get_volume()                     - Get current volume levels for all streams
show_notification(title, content, id) - Show a persistent notification
remove_notification(id)          - Remove a notification by ID
get_clipboard()                  - Read clipboard contents
set_clipboard(text)              - Write text to clipboard
open_url(url)                    - Open a URL in browser/app
get_location()                   - Get GPS location (lat, lon, altitude, speed)
get_wifi_info()                  - Get current WiFi connection details
scan_wifi()                      - Scan for nearby WiFi networks
get_device_info()                - Get device/telephony info
get_cell_info()                  - Get cell tower info
send_sms(number, message)        - Send an SMS
list_sms(limit)                  - List received SMS messages
get_call_log(limit)              - View recent call history
get_contacts()                   - List all contacts (full dump)
find_contact(name)               - Search contacts by name, returns matching name + number pairs.
set_brightness(brightness)       - Set screen brightness (0-255)
take_photo(camera, output)       - Take a quick photo and save it (camera: 0=back, 1=front).
analyze_photo(prompt, camera)    - Take a picture and analyze it visually using Groq cloud models. Use this for physical surroundings.
local_ocr(camera)                - Snaps a frame and extracts text instantly offline using Tesseract. ALWAYS use this instead of analyze_photo when the user asks to "read this", "OCR", "read text", "extract writing", or ask what a specific piece of paper, book page, or sign says.
list_apps(search_query)          - List third party installed app package identifiers via 'cmd package list'.
search_launcher_apps(query)      - Fast checks or sweeps system package listings to translate plain app names (e.g. 'YouTube') into verified package strings. Always call this first when an explicit package identifier isn't known.
open_app(package_name)           - Launch an installed application utilizing an internal intent-directed trigger.
find_music(query, refresh_cache) - Search for audio files across internal storage.
play_media(file)                 - Open and play a file in Muso Music Player (requires full path).
pause_media()                    - Toggle play/pause in the active media session
stop_media()                     - Stop media playback
next_track()                     - Skip to the next track
previous_track()                     - Go to the previous track
open_music_app()                 - Launch Muso Music Player without a specific file
get_media_info()                 - Get current media player status
make_call(number)                - IMMEDIATELY calls the number. No confirmation.
open_dialer(number)              - Opens the dialer pre-filled with the number.
share(text, file)                - Share text or file via Android share sheet
set_wallpaper(file, url)         - Set wallpaper from file path or URL
show_dialog(input_type, title, hint) - Show input dialog
fingerprint_auth()               - Trigger fingerprint authentication
get_sensor(sensor)               - Read a sensor (light/accelerometer/gyroscope/proximity/magnetic_field)
tts_engines()                    - List available TTS engines
"""
