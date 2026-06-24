from jarvis.tools.time_utils import get_current_time, set_timer, set_alarm, schedule_action
from jarvis.tools.device import vibrate, get_battery_status, torch, set_brightness, get_sensor, open_location_settings
from jarvis.tools.media import speak, tts_engines, set_volume, get_volume, play_media, stop_media, pause_media, next_track, previous_track, get_media_info, find_music, open_music_app, stop_recording
from jarvis.tools.comms import send_sms, list_sms, get_call_log, get_contacts, find_contact, make_call, open_dialer
from jarvis.tools.system import get_clipboard, set_clipboard, show_notification, remove_notification, set_wallpaper, show_dialog, fingerprint_auth, show_toast, share
from jarvis.tools.network import open_url, get_wifi_info, scan_wifi, set_wifi, get_location, get_device_info, get_cell_info, search_nearby, web_search, deep_read
from jarvis.tools.camera import take_photo, analyze_photo, local_ocr, read_my_screen, ocr_my_screen, screenshot_my_screen
from jarvis.tools.apps import list_apps, open_app, search_launcher_apps
from jarvis.tools.link import link_start_server, link_status, link_scan, link_send_message, link_send_command, link_send_file, link_sync_clipboard
from jarvis.tools.devices_ext import open_bluetooth_settings, adb_connect, adb_disconnect, adb_pair_device, adb_list_devices, adb_command, adb_screenshot, adb_mdns_reconnect, adb_mirror_device, adb_stop_mirror, dlna_scan, dlna_cast, dlna_stop
from jarvis.tools.hotspot import hotspot_enable, hotspot_disable, hotspot_open_settings, hotspot_status, hotspot_scan_clients, hotspot_adb_autoconnect
from jarvis.tools.ui_inspect import ui_dump, ui_find_text, input_my_screen
from jarvis.tools.notifications import list_notifications, get_latest_notification
from jarvis.tools.app_settings import get_battery_diagnostics, get_system_setting, set_system_setting, get_app_info, clear_app_data




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
    "web_search":          web_search,
    "deep_read":           deep_read,
    "get_location":        get_location,
    "search_nearby":       search_nearby,
    "get_wifi_info":       get_wifi_info,
    "scan_wifi":           scan_wifi,
    "set_wifi":            set_wifi,
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
    "read_my_screen":      read_my_screen,
    "ocr_my_screen":       ocr_my_screen,
    "screenshot_my_screen": screenshot_my_screen,
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
    "open_location_settings": open_location_settings,
    "get_current_time":    get_current_time,
    "set_timer":           set_timer,
    "set_alarm":           set_alarm,
    "schedule_action":     schedule_action,
    "tts_engines":         tts_engines,
    "link_start_server":   link_start_server,
    "link_status":         link_status,
    "link_scan":           link_scan,
    "link_send_message":   link_send_message,
    "link_send_command":   link_send_command,
    "link_send_file":      link_send_file,
    "link_sync_clipboard": link_sync_clipboard,
    "open_bluetooth_settings": open_bluetooth_settings,
    "adb_connect":         adb_connect,
    "adb_disconnect":      adb_disconnect,
    "adb_pair_device":     adb_pair_device,
    "adb_list_devices":    adb_list_devices,
    "adb_command":         adb_command,
    "adb_screenshot":      adb_screenshot,
    "adb_mdns_reconnect":  adb_mdns_reconnect,
    "adb_mirror_device":   adb_mirror_device,
    "adb_stop_mirror":     adb_stop_mirror,
    "dlna_scan":           dlna_scan,
    "dlna_cast":           dlna_cast,
    "dlna_stop":           dlna_stop,
    "hotspot_enable":      hotspot_enable,
    "hotspot_disable":     hotspot_disable,
    "hotspot_open_settings": hotspot_open_settings,
    "hotspot_status":      hotspot_status,
    "hotspot_scan_clients": hotspot_scan_clients,
    "hotspot_adb_autoconnect": hotspot_adb_autoconnect,
    "ui_dump":             ui_dump,
    "ui_find_text":        ui_find_text,
    "input_my_screen":     input_my_screen,
    "list_notifications":  list_notifications,
    "get_latest_notification": get_latest_notification,
    "get_battery_diagnostics": get_battery_diagnostics,
    "get_system_setting":  get_system_setting,
    "set_system_setting":  set_system_setting,
    "get_app_info":        get_app_info,
    "clear_app_data":      clear_app_data,
}

DATA_TOOLS = {
    "get_battery_status", "get_volume", "get_clipboard", "get_location", "search_nearby",
    "get_wifi_info", "scan_wifi", "get_device_info", "get_cell_info",
    "list_sms", "get_call_log", "get_contacts", "get_media_info",
    "get_sensor", "get_current_time", "tts_engines", "show_dialog", "fingerprint_auth",
    "find_music", "find_contact", "analyze_photo", "local_ocr", "read_my_screen", "ocr_my_screen", "list_apps",
    "search_launcher_apps", "web_search", "deep_read", "link_status", "link_scan",
    "dlna_scan", "adb_list_devices", "adb_pair_device", "adb_mdns_reconnect",
    "hotspot_status", "hotspot_scan_clients"
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
web_search(query)                - Search the internet for general knowledge, news, or facts. Returns snippets and URLs.
deep_read(url)                   - Reads the full text content of a specific webpage. Use this if the search snippets from web_search are not enough to answer the question.
get_location()                   - Get GPS location (lat, lon, altitude, speed)
search_nearby(query)             - Search for specific places (e.g. 'hospital', 'bank') nearby. Returns names and distances.
get_wifi_info()                  - Get current WiFi connection details
scan_wifi()                      - Scan for nearby WiFi networks
set_wifi(enabled)                - Enable/disable WiFi (enabled: True/False)
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
read_my_screen(prompt)           - Captures a screenshot of THIS phone's current screen and sends it to the vision model. Use for "what's on my screen?", "what am I looking at?", "read this page", "what does this error say?", or any question about screen content that goes beyond button listing. Sees rendered pixels — canvas, web views, PDFs, images, video frames — that ui_dump cannot introspect.
ocr_my_screen()                  - Captures a screenshot of THIS phone's screen and extracts text via Tesseract OCR. Offline, instant, no API call. Prefer over read_my_screen when the goal is raw text extraction (e.g. "read the text on my screen", "copy this", "what does that say") rather than understanding context or layout.
screenshot_my_screen()           - Captures a screenshot of THIS phone's screen and saves it to /sdcard/DCIM/jarvis/ with an automatic timestamp filename. Use when the user says "take a screenshot", "capture my screen", "save what's on screen". No arguments — filename is always timestamp-based.
list_apps(search_query)          - List third party installed app package identifiers via 'cmd package list'.
search_launcher_apps(query)      - Fast checks or sweeps system package listings to translate plain app names (e.g. 'YouTube') into verified package strings. Always call this first when an explicit package identifier isn't known.
open_app(package_name)           - Launch an app and wait for it to fully render. Returns the initial screen state (ui_dump snapshot) so you can act immediately — do NOT call ui_dump again right after open_app, the screen state is already in the response.
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
open_location_settings()         - Opens the Android Location/GPS settings page so the user can enable/disable it manually.
get_current_time()               - Get current date and time.
set_timer(seconds, message)      - Set a timer to speak a message after x seconds.
set_alarm(hour, minutes, message) - Set a system alarm.
schedule_action(delay, tool, args) - Schedule a tool (by name) to run after a delay.
tts_engines()                    - List available TTS engines
link_start_server()              - Starts the background Jarvis Link servers (TCP/UDP listener) for receiving remote commands/messages.
link_status()                    - Get current Jarvis Link status, local IP, and ports.
link_scan()                      - Scan the local network (Wi-Fi) to discover other active Jarvis Link nodes/phones.
link_send_message(target_ip, message) - Sends a text transmission to a remote phone running Jarvis.
link_send_command(target_ip, command, args_json) - Run a tool (like vibrate, speak, torch, show_toast, battery) on a remote Jarvis phone. Provide args_json as a JSON string.
link_send_file(target_ip, filepath) - Transfer a file from this phone to a remote phone's Downloads directory.
link_sync_clipboard(target_ip)   - Send the local clipboard contents to a remote Jarvis device's clipboard.
open_bluetooth_settings()        - Open the system Bluetooth settings UI for pairing and device routing.
adb_connect(target_ip, port)     - Connect to a nearby developer/power-user phone over Wireless ADB (default port: 5555).
adb_disconnect(target_ip)        - Disconnect from one or all Wireless ADB targets.
adb_pair_device(target_ip, pairing_port, pairing_code) - Pair a brand new device over Wireless ADB. Use handle_adb_pairing flow instead of calling this directly — it collects all required values via show_dialog.
adb_list_devices()               - List all currently connected ADB devices by identifier and model. Always call this first when the user asks to control another phone/device via ADB.
adb_command(target_ip, action, params_json) - Send a command (tap, swipe, text, keyevent, launch, shell) to ADB target phone. Provide arguments as stringified JSON.
adb_screenshot(target_ip, filename) - Takes a screenshot of the ADB target device and pulls it to the local Downloads folder.
ui_dump(target_ip, only_interactive) - READ-ONLY. Lists the text labels and buttons currently visible on screen (with positions), e.g. for "what's on screen", "what buttons are visible", "list clickable elements". Does NOT tap, type, or interact in any way — for that, use adb_command instead. only_interactive defaults to True (buttons/links only); set False to also see static text.
ui_find_text(query, target_ip) - READ-ONLY. Checks whether a specific label/button is currently visible on screen (e.g. "is there a Save button"), case-insensitive partial match. Does NOT tap or interact — for that, use adb_command instead.
input_my_screen(action, params_json) - Sends touch/keyboard input to THIS phone's screen. Actions: tap {x,y}, swipe {x1,y1,x2,y2,duration_ms}, text {text}, keyevent {code}, long_press {x,y,duration_ms}, shell {cmd}. Use coordinates from ui_dump's bounds. Combine with ui_dump/read_my_screen to navigate any app: read → decide → tap → read again → repeat. Key codes: 3=Home, 4=Back, 26=Power, 66=Enter, 67=Backspace, 187=Recents.
list_notifications(target_ip, app_filter, limit) - READ-ONLY. Lists currently-posted notifications (app, title, text), most recent first. Does NOT dismiss, open, or reply to any notification. app_filter is an optional partial package name (e.g. "whatsapp") to narrow results; limit defaults to 10.
get_latest_notification(target_ip, app_filter) - READ-ONLY. Returns just the single most recent notification, optionally filtered to one app (e.g. "what's my last WhatsApp message"). Does NOT dismiss, open, or reply to it.
get_battery_diagnostics(target_ip) - READ-ONLY. Deeper battery info than get_battery_status: voltage, charge current, technology, health. Use for "why is my battery draining" type questions.
get_system_setting(key, namespace, target_ip) - READ-ONLY. Reads one exact Android system setting by key (namespace: system/secure/global, defaults to system). Use before set_system_setting if the current value or exact key name is uncertain.
set_system_setting(key, value, namespace, target_ip) - Writes exactly ONE named system setting to exactly ONE given value (e.g. key="screen_off_timeout" value="30000" for 30 seconds). Does not touch any other setting. namespace defaults to "system".
get_app_info(package, target_ip) - READ-ONLY. Returns version, install/update dates, and granted permissions for ONE named installed package (exact package id, e.g. "com.whatsapp"). Use search_launcher_apps first if only the display name is known.
clear_app_data(package, target_ip) - Clears cache AND data for exactly ONE named installed package (like Settings > Apps > [App] > Storage > Clear Data). Logs the app out and resets it to fresh-install state. Does NOT uninstall. Requires exact package id — use search_launcher_apps first if only the display name is known. Confirm with the user before calling this, since it is destructive to that app's local data.
adb_mdns_reconnect(prefer_serial) - Reconnects to a previously-paired ADB device by scanning mDNS, regardless of which network it's on (no shared hotspot needed). Use this if adb_command/adb_screenshot fail because the device's IP or port changed and it's not on this phone's own hotspot.
adb_mirror_device(target_ip, orientation) - Opens a LIVE interactive mirror of the connected phone's screen in a Termux:X11 window using scrcpy. Use this for "mirror", "screen mirror", "show me the other phone's screen", "let me control it directly" — NOT adb_screenshot, which only takes a single static image. Tapping/swiping the window controls the target phone like a normal touchscreen, no extra setup needed. orientation defaults to "portrait".
adb_stop_mirror() - Closes the currently running screen mirror session.
dlna_scan()                      - Scan the local network for DLNA smart TVs, screens, and speakers.
dlna_cast(target_ip, media_url, media_title) - Stream audio/video URLs directly to a local smart TV or speaker.
dlna_stop(target_ip)             - Stop casting/playback on DLNA smart TV or speaker.
hotspot_enable()                 - Enable this phone's Wi-Fi hotspot programmatically.
hotspot_disable()                - Disable this phone's Wi-Fi hotspot.
hotspot_open_settings()          - Open the Hotspot & Tethering settings screen.
hotspot_status()                 - Check if hotspot is active and list connected client IPs.
hotspot_scan_clients()           - Scan for devices connected to this phone's hotspot (ARP + nmap).
hotspot_adb_autoconnect()        - Scan hotspot clients and auto-connect to them via ADB wireless debugging.
"""
