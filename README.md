# Jarvis Assistant

A voice-controlled AI assistant that runs entirely on an Android phone via [Termux](https://termux.dev/) — no PC, no cloud server, no companion app. Say "Jarvis," speak a command, and it can search the web, control device hardware, manage contacts/calls/SMS, take and analyze photos, play music, remote-control other Android devices over ADB, and more.

## How it works

```
Wake word ("Jarvis") → Whisper STT → Local intent router → LLM (tool-calling) → Tool execution → Piper/TTS
```

- **Wake word + STT**: `voice.py` listens for "Jarvis" via the microphone, then records the follow-up command and transcribes it using Groq's hosted Whisper (`whisper-large-v3`).
- **Fast-path routing**: `handler.py`'s `classify_local_intent` matches common phrases directly to a tool call, skipping the LLM round-trip entirely for instant responses (e.g. "flashlight on," "what's my battery").
- **LLM reasoning**: anything that doesn't match a local intent goes to `ai.py`, which calls Groq's chat completions API. The model decides which tool(s) to call by emitting JSON (`{"tool": "name", "args": {...}}`), one per line for multi-step actions.
- **Tool execution**: `handler.py` parses the model's tool calls and dispatches them to the corresponding Python function in `tools/`.
- **Speech output**: results are spoken back via Piper (offline neural TTS) or Android's built-in TTS engine.

## Model setup

| Purpose | Model |
|---|---|
| Primary chat/tool-calling | `llama-3.3-70b-versatile` (Groq) |
| Fallback (auto-switches on daily quota exhaustion) | `llama-3.1-8b-instant` (Groq) |
| Vision (photo analysis) | `meta-llama/llama-4-scout-17b-16e-instruct` (Groq) |
| Speech-to-text | `whisper-large-v3` (Groq) |

`ai.py` automatically falls back to the secondary model when the primary hits its daily rate limit (HTTP 429), and switches back the next day. It also detects and retries around a known Groq-side bug (`tool_use_failed`) where the API attaches an implicit tool schema and rejects the model's own output.

## Tools

Over 70 tools registered in `tools/__init__.py`, organized by file:

| File | Capabilities |
|---|---|
| `device.py` | Vibrate, battery status, torch, brightness, sensors, location settings |
| `media.py` | TTS, volume, playback control (play/pause/stop/skip), music search, media player launch |
| `comms.py` | Send/list SMS, call log, contacts lookup, place calls |
| `system.py` | Clipboard, notifications, wallpaper, dialogs, fingerprint auth, share sheet, toasts |
| `network.py` | URL opening, WiFi info/scan/toggle, device/cell info, nearby place search, web search, full-page reading |
| `camera.py` | Photo capture, vision-model analysis, offline OCR (Tesseract) |
| `apps.py` | List/launch installed apps, fuzzy app-name → package resolution |
| `link.py` | **Jarvis Link** — a custom TCP/UDP protocol for phone-to-phone messaging, remote commands, file transfer, and clipboard sync between two phones both running this assistant |
| `devices_ext.py` | **ADB control of *other* Android devices** — pairing, connect/disconnect, tap/swipe/text/keyevent/shell commands, screenshots, mDNS-based reconnect when IP changes; plus DLNA cast to smart TVs/speakers |
| `hotspot.py` | Enable/disable hotspot, scan connected clients, auto-connect to them via ADB |
| `time_utils.py` | Current time, timers, system alarms, delayed tool scheduling |

Two distinct "control another device" systems exist side by side:
- **ADB tools** control *any* Android phone with Wireless Debugging enabled — the target doesn't need Jarvis installed.
- **Jarvis Link** only works between two phones that are *both* running this assistant.

## Requirements

- Android phone, [Termux](https://termux.dev/) + [Termux:API](https://wiki.termux.com/wiki/Termux:API) app installed
- Python 3 with: `requests`, `python-dotenv`, `sounddevice`, `numpy`, `beautifulsoup4`
- A [Groq](https://console.groq.com/) API key
- (Optional) [Piper TTS](https://github.com/rhasspy/piper) for offline neural speech output
- (Optional) `adb` and `tesseract` binaries for device control / OCR features
- `.env` file with `GROQ_API_KEY=your_key_here`

## Usage

```bash
# Continuous voice mode (wake word "Jarvis")
python -m jarvis.main voice

# One-shot text command
python -m jarvis.main "what's my battery level"

# No arguments defaults to voice mode
python -m jarvis.main
```

## Project structure

```
jarvis/
├── main.py            # Entry point, voice loop, history management
├── ai.py               # Groq API calls, streaming, model fallback/retry logic
├── handler.py           # Tool-call parsing/execution, local intent routing
├── voice.py            # Wake word detection, audio recording, STT
├── config.py            # API keys, model names, system prompt, paths
├── history.py           # Persistent conversation history
├── state.py
├── cache/
│   ├── music_cache.py    # Cached scan of audio files on device
│   └── activity_cache.py # Cached app package → launch activity mapping
└── tools/
    ├── device.py, media.py, comms.py, system.py, network.py
    ├── camera.py, apps.py, time_utils.py
    ├── link.py            # Jarvis-to-Jarvis phone protocol
    ├── devices_ext.py      # ADB remote control + DLNA casting
    └── hotspot.py
```

## Notes

- Conversation history is sanitized before being stored — raw tool-call JSON and execution-result scaffolding are stripped out. This prevents weaker fallback models from pattern-completing fake tool results in later turns instead of issuing real tool calls.
- The system prompt enforces specific behavioral rules per tool category (e.g. always resolve contacts by name before calling, always check `adb_list_devices` before any ADB action, prefer offline OCR over vision-model calls for reading text).
