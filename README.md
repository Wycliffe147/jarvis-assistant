# Jarvis Assistant

A voice-controlled AI assistant that runs entirely on an Android phone via [Termux](https://termux.dev/) — no PC, no cloud server, no companion app. Say "Jarvis," speak a command, and it can search the web, control device hardware, manage contacts/calls/SMS, take and analyze photos, play music, remote-control other Android devices over ADB, and more.

## Table of Contents
- [How It Works](#how-it-works)
- [Model Setup](#model-setup)
- [Tools Breakdown](#tools-breakdown)
  - [ADB Dual Identities Note](#a-note-on-this-phone-having-two-adb-identities)
- [Requirements](#requirements)
- [Setup Guide (New Phone)](#setup-guide-new-phone)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Multi-step Tool-Call Loop](#multi-step-tool-call-loop-handlerpy)
- [Notes](#notes)

---

## How it works

```
Wake word ("Jarvis") → Whisper STT → Local intent router → LLM (tool-calling) → Tool execution → Piper/TTS
```

- **Wake word + STT**: `voice.py` listens for "Jarvis" via the microphone, then records the follow-up command and transcribes it using Groq's hosted Whisper (`whisper-large-v3`).
- **Fast-path routing**: `handler.py`'s `classify_local_intent` matches common phrases directly to a tool call, skipping the LLM round-trip entirely for instant responses (e.g. "flashlight on," "what's my battery").
- **LLM reasoning**: anything that doesn't match a local intent goes to `ai.py`, which calls Groq's chat completions API. The model decides which tool(s) to call by emitting JSON (`{"tool": "name", "args": {...}}`), one per line for multi-step actions.
- **Tool execution**: `handler.py` parses the model's tool calls and dispatches them to the corresponding Python function in `tools/`.
- **Speech output**: results are spoken back via Piper (offline neural TTS) or Android's built-in TTS engine.

---

## Model setup

| Purpose | Model |
|---|---|
| Primary chat/tool-calling | `llama-3.3-70b-versatile` (Groq) |
| 2nd-tier fallback (separate quota pool, larger model) | `gpt-oss-120b` (Cerebras) |
| Last-resort fallback (only if both above are exhausted same-day) | `llama-3.1-8b-instant` (Groq) |
| Vision (photo analysis) | `meta-llama/llama-4-scout-17b-16e-instruct` (Groq) |
| Speech-to-text | `whisper-large-v3` (Groq) |

<details>
<summary><b>Click to expand model fallback & retry details</b></summary>

`ai.py` tries the Groq primary first, then Cerebras (if `CEREBRAS_API_KEY` is set) once the primary hits its daily rate limit (HTTP 429), and only falls back to the small Groq model if *both* are exhausted on the same day. Each exhaustion flag clears automatically at midnight UTC. It also detects and retries around a known Groq-side bug (`tool_use_failed`) where the API attaches an implicit tool schema and rejects the model's own output.

</details>

---

## Tools Breakdown

<details>
<summary><b>Click to expand list of 96 tools registered across 12 files</b></summary>

96 tools registered in `tools/__init__.py`, organized by file:

| File | Capabilities |
|---|---|
| `device.py` | Vibrate, battery status, torch, brightness, sensors, location settings |
| `media.py` | TTS, volume, playback control (play/pause/stop/skip), music search, media player launch |
| `comms.py` | Send/list SMS, call log, contacts lookup, place calls |
| `system.py` | Clipboard, notifications, wallpaper, dialogs, fingerprint auth, share sheet, toasts |
| `network.py` | URL opening, WiFi info/scan/toggle, device/cell info, nearby place search, web search, full-page reading |
| `camera.py` | Photo capture, vision-model analysis, offline OCR (Tesseract) |
| `apps.py` | List/launch installed apps, fuzzy app-name → package resolution, force-stop + relaunch frozen/misbehaving apps (`restart_app`), logcat crash/ANR diagnostics (`get_crash_diagnostics`) |
| `ui_inspect.py` | On-screen UI automation — dump the current view hierarchy, find/tap elements by text or resource ID, send taps/swipes/keyevents/text input directly to the screen. Used for in-app navigation (e.g. tapping a search result) that package-level intents can't reach |
| `link.py` | **Jarvis Link** — a custom TCP/UDP protocol for phone-to-phone messaging, remote commands, file transfer, and clipboard sync between two phones both running this assistant |
| `devices_ext.py` | **ADB control of *other* Android devices** — pairing, connect/disconnect, tap/swipe/text/keyevent/shell commands, screenshots, mDNS-based reconnect when IP changes; plus DLNA cast to smart TVs/speakers |
| `hotspot.py` | Enable/disable hotspot, scan connected clients, auto-connect to them via ADB |
| `time_utils.py` | Current time, timers, system alarms, delayed tool scheduling |

Two distinct "control another device" systems exist side by side:
- **ADB tools** control *any* Android phone with Wireless Debugging enabled — the target doesn't need Jarvis installed.
- **Jarvis Link** only works between two phones that are *both* running this assistant.

</details>

<details>
<summary><b>A note on "this phone" having two ADB identities</b></summary>

Jarvis talks to its own host phone over ADB (for `ui_inspect.py`, `apps.py`'s `restart_app`/`get_crash_diagnostics`, etc.), and that phone shows up to `adb devices` as **two separate entries at once**:

```
127.0.0.1:5555  device   # loopback TCP target, set up by devices_ext.py
emulator-5554   device   # Termux's local adbd reporting its own serial
```

Both are the same physical device — neither is stray or removable. Any bare `adb` call with no explicit `-s <target>` has to guess between them, which gets worse the moment a real second device is also connected (`adb` then refuses to guess at all: `error: more than one device/emulator`). All ADB calls in this codebase should resolve an explicit target first (`_resolve_local_target()` / `_adb_target()`) rather than relying on bare `adb`.

</details>

---

## Requirements

- Android phone, [Termux](https://termux.dev/) + [Termux:API](https://wiki.termux.com/wiki/Termux:API) app installed
- Python 3 + libraries (`requests`, `python-dotenv`, `sounddevice`, `numpy`, `beautifulsoup4`)
- A [Groq](https://console.groq.com/) API key
- `adb` binary + Wireless Debugging enabled on host phone
- (Optional) [Piper TTS](https://github.com/rhasspy/piper) for offline neural speech output
- (Optional) `tesseract` binary for offline OCR
- `.env` file with `GROQ_API_KEY=your_key_here`

<details>
<summary><b>Click to expand detailed breakdown of dependencies & their purpose</b></summary>

### System Package Dependencies
| Package | Purpose |
|---|---|
| **`python`** | Python 3 runtime environment required to execute the Jarvis assistant core modules. |
| **`git`** | Version control software used to clone, update, and manage the Jarvis codebase. |
| **`termux-api`** | CLI utilities interfacing Termux with Android system APIs (Microphone, Camera, SMS, Calls, Battery, WiFi, Notifications, Sensors). |
| **`android-tools`** | Provides the `adb` (Android Debug Bridge) client to perform on-screen UI automation (`ui_inspect.py`) and remote device control. |
| **`tesseract`** | *(Optional)* Offline Optical Character Recognition (OCR) engine for extracting text from images and camera snapshots. |
| **`ffmpeg`** | Audio and video processing tool for encoding, decoding, and handling speech audio streams. |

### Python Library Dependencies (`requirements.txt`)
| Library | Purpose |
|---|---|
| **`requests`** | Handles HTTP requests for Groq & Cerebras LLM API calls, Web Search queries, and web page content fetching. |
| **`python-dotenv`** | Reads and loads environment variables (e.g. `GROQ_API_KEY`, `CEREBRAS_API_KEY`) from local `.env` files. |
| **`sounddevice`** | Captures real-time audio input from the phone's microphone for wake word detection and speech recognition. |
| **`numpy`** | Performs high-performance numerical array operations on raw PCM audio buffers before STT processing. |
| **`beautifulsoup4`** | Parses HTML/XML structure to extract clean, readable text content from websites for LLM analysis. |

</details>

---

## Setup Guide (New Phone)

<details>
<summary><b>Click to expand full step-by-step setup guide for a new phone</b></summary>

Follow these steps to set up Jarvis on a fresh Android phone:

### 1. Install Termux & Termux:API
1. Install **Termux** and **Termux:API** apps (preferably from [F-Droid](https://f-droid.org/) or GitHub Releases).
2. Open Termux and grant storage access:
   ```bash
   termux-setup-storage
   ```
3. Grant necessary permissions to **Termux:API** in Android Settings (Microphone, Location, Camera, SMS, Contacts, Phone, and "Display over other apps").

### 2. Install Required System Packages
Update packages and install Python, pre-compiled NumPy, Git, Termux-API tools, ADB, and optional dependencies:
```bash
pkg update && pkg upgrade -y
pkg install python python-numpy git termux-api android-tools tesseract ffmpeg -y
```

### 3. Clone Repository & Install Python Dependencies
```bash
git clone https://github.com/Wycliffe147/jarvis-assistant.git jarvis
cd jarvis
pip install -r requirements.txt
```
> [!TIP]
> **Performance Note for Budget Phones**: Installing `python-numpy` via `pkg install` in Step 2 installs a pre-compiled binary in ~15 seconds. If skipped, `pip` attempts to compile NumPy from C source code on your phone, taking 20+ minutes on budget phone CPUs.

### 4. Create Environment File (`.env`)
Create a `.env` file in the root of the `jarvis` directory:
```bash
cat << 'EOF' > .env
GROQ_API_KEY=your_groq_api_key_here
# Optional fallback keys
CEREBRAS_API_KEY=your_cerebras_api_key_here
EOF
```
Replace `your_groq_api_key_here` with your actual API key from [Groq Console](https://console.groq.com/).

### 5. Enable Wireless Debugging & Local ADB
1. Go to **Android Settings** → **Developer Options** → Enable **Wireless Debugging**.
2. Pair ADB locally on Termux (if required by your Android version):
   ```bash
   adb pair 127.0.0.1:<PORT> <PAIRING_CODE>
   ```
3. Connect local ADB daemon:
   ```bash
   adb connect 127.0.0.1:5555
   ```
4. Verify ADB connection:
   ```bash
   adb devices
   ```

### 6. Set Up Termux Widget Shortcuts
Jarvis includes launcher & control scripts for [Termux:Widget](https://wiki.termux.com/wiki/Termux:Widget) in the `shortcuts/` directory.

To copy the shortcut scripts into your Termux widget directory (`~/.shortcuts/`), run:
```bash
mkdir -p ~/.shortcuts
cp ~/jarvis/shortcuts/* ~/.shortcuts/
chmod +x ~/.shortcuts/*.sh
```

#### Shortcut Scripts Breakdown:
| Script | Description |
|---|---|
| **`launch-assistant.sh`** | Acquires a Termux wake-lock (`termux-wake-lock`), starts the Piper TTS server in Ubuntu proot, launches Jarvis main process (`jarvis.main`) in background, logs to `~/boot_debug.log`, and triggers a toast notification. |
| **`kill-jarvis.sh`** | Force-terminates Jarvis main process, Piper server, watchdog script, and log-tailing processes, releases wake-lock (`termux-wake-unlock`), and notifies via toast. |
| **`tail-jarvis-log.sh`** | Opens a real-time tail of the log file (`tail -f ~/boot_debug.log`) for live activity monitoring and debugging. |
| **`piper-read.sh`** | Displays a multi-line GUI text input dialog (`termux-dialog`), generates TTS speech audio via Piper inside Ubuntu proot, and plays it aloud using `termux-media-player`. |
| **`run_piper.sh`** | Standalone launcher to start the Piper neural TTS server process inside Ubuntu proot. |
| **`piper_watchdog.py`** | Background Python watchdog daemon that monitors the Piper TTS server inside Ubuntu proot and automatically restarts it if it crashes. |

### 7. Verify and Run
Run Jarvis in continuous voice assistant mode:
```bash
python -m jarvis.main voice
```
Or run a one-shot text command:
```bash
python -m jarvis.main "what is my battery level"
```

### 8. Setup Command Reference & Purpose
Below is a reference guide explaining the exact purpose of each command used in the setup process:

| Command | Purpose |
|---|---|
| **`termux-setup-storage`** | Grants Termux permission to access shared device storage (`/sdcard/`). |
| **`pkg update && pkg upgrade -y`** | Refreshes Termux package indices and upgrades all installed packages to their latest versions. |
| **`pkg install python python-numpy git termux-api android-tools tesseract ffmpeg -y`** | Installs system binaries and pre-compiled NumPy required for Python runtime, fast math array handling, repository cloning, Android API bridge, local ADB automation, OCR, and audio stream handling. |
| **`git clone ...`** | Downloads the latest Jarvis source code repository from GitHub to `~/jarvis`. |
| **`pip install -r requirements.txt`** | Installs all required Python third-party packages (`requests`, `python-dotenv`, `sounddevice`, `numpy`, `beautifulsoup4`). |
| **`cat << 'EOF' > .env ...`** | Generates the local `.env` configuration file to store secret API credentials (`GROQ_API_KEY`, `CEREBRAS_API_KEY`). |
| **`adb pair 127.0.0.1:<PORT> <CODE>`** | Authenticates Termux ADB with Android's Wireless Debugging service. |
| **`adb connect 127.0.0.1:5555`** | Connects Termux ADB to the local loopback interface for on-screen UI inspection and app control. |
| **`cp ~/jarvis/shortcuts/* ~/.shortcuts/`** | Deploys Termux:Widget launcher & management scripts to the widget shortcuts folder. |
| **`chmod +x ~/.shortcuts/*.sh`** | Grants executable permissions to all shortcut shell scripts. |
| **`python -m jarvis.main voice`** | Starts Jarvis in continuous voice assistant mode listening for the wake word "Jarvis". |

</details>

---

## Usage

```bash
# Continuous voice mode (wake word "Jarvis")
python -m jarvis.main voice

# One-shot text command
python -m jarvis.main "what's my battery level"

# No arguments defaults to voice mode
python -m jarvis.main
```

---

## Project structure

<details>
<summary><b>Click to expand project directory tree</b></summary>

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
├── shortcuts/           # Termux:Widget shortcuts & control scripts
│   ├── launch-assistant.sh
│   ├── kill-jarvis.sh
│   ├── tail-jarvis-log.sh
│   ├── piper-read.sh
│   ├── run_piper.sh
│   └── piper_watchdog.py
└── tools/
    ├── device.py, media.py, comms.py, system.py, network.py
    ├── camera.py, apps.py, time_utils.py
    ├── ui_inspect.py       # On-screen UI automation (dump/find/tap elements, raw input)
    ├── link.py            # Jarvis-to-Jarvis phone protocol
    ├── devices_ext.py      # ADB remote control + DLNA casting
    └── hotspot.py
```

</details>

---

## Multi-step tool-call loop (`handler.py`)

<details>
<summary><b>Click to expand multi-step tool-call loop mechanics</b></summary>

When a tool's result needs the model to look at it and decide what to do next (e.g. read a UI dump, then tap something based on what it found), `handle_response` recurses: it sends the tool result back to the model as a follow-up turn, and keeps doing so until the model produces a final answer with no more "data" tool calls pending.

This recursion is capped, **not unlimited** — `_depth` tracks how many follow-up passes have happened, and once it hits the limit, the loop stops recursing and returns whatever the model said last, even if the task isn't actually finished. Multi-step UI-automation chains (open app → tap search bar → type → submit → read results → tap a result) routinely need more passes than a single data lookup like "what's my battery," so UI-tool chains (anything using `ui_dump`, `ui_find_text`, `ui_tap_element`, or `input_my_screen`) get a higher depth ceiling than everything else.

If a command that should be multi-step keeps ending early with a guessed/narrated outcome instead of a confirmed result, the depth ceiling for that tool category is the first thing to check.

</details>

---

## Notes

- Conversation history is sanitized before being stored — raw tool-call JSON and execution-result scaffolding are stripped out. This prevents weaker fallback models from pattern-completing fake tool results in later turns instead of issuing real tool calls.
- The system prompt enforces specific behavioral rules per tool category (e.g. always resolve contacts by name before calling, always check `adb_list_devices` before any ADB action, prefer offline OCR over vision-model calls for reading text).
