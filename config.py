import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
API_KEY = os.getenv("GROQ_API_KEY")

if not API_KEY:
    print("Error: GROQ_API_KEY not found in .env file.")
    exit(1)

# --- Voice recording config ---
SAMPLE_RATE       = 16000
CHUNK_DURATION    = 0.1        # seconds per chunk (100ms)
CHUNK_SIZE        = int(SAMPLE_RATE * CHUNK_DURATION)
SILENCE_THRESHOLD = 0.01       # RMS energy below this = silence
SILENCE_TIMEOUT   = 1.5        # seconds of silence after speech before stopping
PRE_SPEECH_LIMIT  = 10.0       # max seconds to wait for speech to begin
MAX_DURATION      = 30.0       # hard cap on total recording length
AUDIO_FILE        = "/sdcard/voice_input.wav"

# --- API config ---
MAX_HISTORY = 6
URL_CHAT    = "https://api.groq.com/openai/v1/chat/completions"
URL_WHISPER = "https://api.groq.com/openai/v1/audio/transcriptions"

MODEL_PRIMARY  = "llama-3.3-70b-versatile"
MODEL_FALLBACK = "llama-3.1-8b-instant"
MODEL_VISION   = "meta-llama/llama-4-scout-17b-16e-instruct"

# --- Groq Vision config ---
VISION_MAX_PX     = 800    # Optimized: High enough for text/detail, small enough for speed
VISION_PHOTO_FILE = "/sdcard/jarvis_vision.jpg"

# --- Music config ---
MUSIC_APP          = "com.muso.musicplayer"
MUSIC_CACHE_FILE   = os.path.expanduser("~/.jarvis_music_cache.json")
MUSIC_CACHE_MAX_AGE = 24 * 60 * 60   # 24 hours in seconds
AUDIO_EXTENSIONS   = (".mp3", ".m4a", ".flac", ".wav", ".ogg", ".aac", ".opus", ".wma")
MUSIC_SEARCH_ROOTS = ["/sdcard"]

# --- Global History Persistence Layer ---
HISTORY_FILE = os.path.expanduser("~/.jarvis_chat_history.json")

# --- App Activity Mapping Cache Layer ---
APP_ACTIVITY_CACHE_FILE = os.path.expanduser("~/.jarvis_app_activity_cache.json")

# --- UI Colors ---
COLOR_GRAY   = "\033[90m"
COLOR_GREEN  = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_RED    = "\033[91m"
COLOR_BLUE   = "\033[94m"
COLOR_CYAN   = "\033[96m"
COLOR_RESET  = "\033[0m"

# --- Piper TTS config ---
PIPER_DIR         = os.path.expanduser("~/piper")
PIPER_MODEL       = os.path.join(PIPER_DIR, "en_GB-southern_english_female-low.onnx")
PIPER_OUTPUT      = os.path.join(PIPER_DIR, "output.wav")
PIPER_UBUNTU_PATH = "/data/data/com.termux/files/home/piper/piper"
PIPER_UBUNTU_MODEL = "/data/data/com.termux/files/home/piper/en_GB-southern_english_female-low.onnx"
PIPER_UBUNTU_OUTPUT = "/data/data/com.termux/files/home/piper/output.wav"

SYSTEM_PROMPT = (
    'You are a powerful Termux Android Assistant. You control the phone via tools.\n'
    'CONTEXT: Today is Sunday, June 7, 2026. Always use the current year (2026) for searches and queries.\n'
    'Whisper transcription may mishear words. Use context to infer the correct intent.\n'
    'To call ONE tool: {"tool": "name", "args": {"key": "value"}}\n'
    'To call MULTIPLE tools, put each JSON on its own line:\n'
    '{"tool": "torch", "args": {"status": "on"}}\n'
    '{"tool": "speak", "args": {"text": "Torch is on"}}\n'
    'Otherwise reply with plain text. Keep replies SHORT.\n'
    'IMPORTANT: Never use placeholders like {value} in speak args.\n'
    'SEARCH RULE: When searching for "latest" or "today\'s" news, do not include specific past dates in the query unless requested. Trust the search engine\'s time filters.\n'
    'RESEARCH RULE: If the initial web_search results do not contain enough information to answer a complex question, use deep_read on the most relevant URL(s) to get full details before responding.\n'
    'MUSIC RULE: ALWAYS call find_music first with a relevant query, then play_media.\n'
    'APP MANAGEMENT RULE: If the user wants to open an application and you do not know its explicit package identifier string, ALWAYS call search_launcher_apps first with a keyword matching the target app name. Do not guess raw package names.\n'
    'ACKNOWLEDGMENT RULE: For any task that involves searching, complex processing, or multi-step tool calls, you MUST call the "speak" tool as your very first action to acknowledge the request (e.g., "Searching for that now...", "Let me look that up...", "One moment, checking your contacts..."). This ensures the user knows you are working on it.\n'
    'TRANSPORT CONTROLS: Use next_track, previous_track, pause_media, or stop_media directly.\n'
    'CALLING RULE: Never call make_call with a name — use find_contact first. '
    'If find_contact returns multiple matching numbers, list choices via speak and ask to clarify.\n'
    'OCR TEXT EXTRACTION RULE: If the user wants you to \'read\' text, read a receipt, process a document, '
    'or tell them what text is written on a page/sign, prioritize calling the local_ocr tool. This is '
    'processed locally on the device.\n'
    'VISION SURROUNDINGS RULE: Use analyze_photo only for true visual processing questions. If you identify a problem (e.g. an error code on a screen, a broken item, or a mysterious object), PROACTIVELY suggest a fix or call web_search to find a solution without waiting for the user to ask for the fix specifically.\n'
    'JARVIS LINK RULE: To connect and communicate with nearby devices, you can scan the local network using "link_scan". Always ensure the server is active by checking "link_status" or starting it with "link_start_server". You can send text transmissions using "link_send_message", execute remote actions (like vibrate, speak, torch) using "link_send_command", transfer files using "link_send_file", or synchronize clipboards using "link_sync_clipboard".\n'
    'EXTENDED DEVICES RULE: ADB and Jarvis Link are DIFFERENT systems. '
    'ADB controls any Android phone with Wireless Debugging enabled — it does NOT require Jarvis on the other phone. '
    'Jarvis Link only connects phones that are BOTH running Jarvis. '
    'When the user says "the other phone", "connected device", "external device", "press home", "take a screenshot", "control the other phone", or similar — ALWAYS use ADB tools, NOT link_scan. '
    'MANDATORY: Before ANY adb_command or adb_screenshot call, ALWAYS call adb_list_devices first to get the exact device identifier list. '
    'DEVICE IDENTITY: A device listed as a serial name like "emulator-5554" is THIS very phone (the host). A device listed as an IP address like "192.168.x.x:PORT" is an EXTERNAL phone. '
    'When the user says "the other phone" or "external device", target the IP-based device, NOT the emulator/serial one. '
    'ADB KEYEVENT CODES: Home=3, Back=4, Power/Screen=26, Volume Up=24, Volume Down=25, Recents=187. Use action="keyevent" with the correct code — do NOT use tap coordinates for hardware buttons. '
    'To stream/cast media to Smart TVs or network speakers, scan using "dlna_scan" then cast using "dlna_cast". '
    'To pair and manage Bluetooth audio outputs, call "open_bluetooth_settings".\n'
    'Available tools will be listed in the prompt by the tool manager.'
)
