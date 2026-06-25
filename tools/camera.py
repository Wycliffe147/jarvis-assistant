import subprocess
import os
import time
import requests
from jarvis.config import API_KEY, MODEL_VISION, URL_CHAT, VISION_MAX_PX, VISION_PHOTO_FILE, COLOR_GRAY, COLOR_RED, COLOR_YELLOW, COLOR_RESET
from jarvis import state

from jarvis.tools.device import get_sensor, torch


def _check_ffmpeg_available() -> bool:
    """Checks once per session whether ffmpeg is installed, caching the
    result in state.py so every photo/screenshot analysis doesn't re-run
    `which ffmpeg` as its own subprocess call."""
    if state.ffmpeg_available is None:
        result = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        state.ffmpeg_available = (result.returncode == 0)
    return state.ffmpeg_available


def confirm_uncompressed_upload() -> str:
    """Call this ONLY after the user has explicitly agreed to send images/
    screenshots to the vision API at full size, uncompressed, because ffmpeg
    is not installed on this device. Do not call this proactively or assume
    consent -- it must follow a direct yes from the user in this session
    (e.g. they were asked and replied "go ahead anyway" / "skip it" /
    "proceed without compression" or similar).

    This approval lasts for the rest of the current session only. If Jarvis
    restarts, the user will be asked again the next time vision analysis is
    attempted.
    """
    state.user_approved_uncompressed_upload = True
    return (
        "Understood — uncompressed image uploads are now approved for the rest of this session. "
        "Photos and screenshots sent for analysis will use full resolution/quality until Jarvis restarts."
    )


def take_photo(camera: int = 0, output: str = "/sdcard/photo.jpg"):
    subprocess.run(["termux-camera-photo", "-c", str(camera), output], stdin=subprocess.DEVNULL)
    return f"Photo taken with camera {camera}, saved to {output}"

def analyze_photo(prompt: str = "Analyze this image carefully. If you see any problems, error codes, or objects that need fixing, identify them and provide a solution or trigger a search for one.", camera: int = 0) -> str:
    photo_path = VISION_PHOTO_FILE

    print(f"{COLOR_GRAY}[Taking actionable snapshot via camera {camera}...]{COLOR_RESET}")
    subprocess.run(["termux-camera-photo", "-c", str(camera), photo_path], capture_output=True, text=True, stdin=subprocess.DEVNULL)

    photo_saved = False
    for _ in range(20):
        if os.path.exists(photo_path) and os.path.getsize(photo_path) > 0:
            photo_saved = True
            break
        time.sleep(0.5)

    if not photo_saved:
        return "Vision capture failed: Native camera failed to save image within timeout."

    return _process_and_upload_vision(photo_path, prompt)
def _process_and_upload_vision(input_path: str, prompt: str) -> str:
    image_path = input_path

    if _check_ffmpeg_available():
        try:
            resized_path = "/sdcard/jarvis_vision_small.jpg"
            if os.path.exists(resized_path):
                os.remove(resized_path)

            subprocess.run([
                "ffmpeg", "-y", "-i", input_path,
                "-vf", f"scale='if(gt(iw,ih),{VISION_MAX_PX},-2)':'if(gt(iw,ih),-2,{VISION_MAX_PX})'",
                "-q:v", "5",
                resized_path
            ], capture_output=True, stdin=subprocess.DEVNULL)

            if os.path.exists(resized_path) and os.path.getsize(resized_path) > 0:
                image_path = resized_path
        except Exception:
            pass
    elif not state.user_approved_uncompressed_upload:
        # ffmpeg is missing and the user hasn't said it's OK to upload
        # uncompressed images this session -- stop here instead of silently
        # sending the full-resolution file. Report the real file size so
        # the user can make an informed call rather than guessing at impact.
        try:
            size_kb = os.path.getsize(input_path) / 1024
            size_note = f"~{size_kb:.0f} KB uncompressed"
        except Exception:
            size_note = "size unknown"
        print(f"{COLOR_YELLOW}[ffmpeg not found -- pausing before upload, awaiting user confirmation]{COLOR_RESET}")
        return (
            "I can't compress this image before sending it for analysis because ffmpeg isn't installed "
            f"on this device ({size_note}). I'm not uploading it yet. "
            "You can either install ffmpeg yourself (e.g. `pkg install ffmpeg` in Termux) and try again, "
            "or tell me to go ahead without compression and I'll send it at full size for this session."
        )
    # else: ffmpeg missing but the user already approved uncompressed
    # uploads this session -- fall through and upload input_path as-is.

    try:
        with open(image_path, "rb") as f:
            image_b64 = __import__("base64").b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return f"Image read error: {e}"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL_VISION,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 400
    }

    print(f"{COLOR_GRAY}[Uploading optimized vision stream to Groq payload...]{COLOR_RESET}")
    try:
        r = requests.post(URL_CHAT, headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        else:
            print(f"{COLOR_RED}[Groq Vision error {r.status_code}: {r.text[:120]}]{COLOR_RESET}")
            return "I couldn't process the visual elements right now due to an upstream API error."
    except Exception as e:
        return f"Network link dropped during cloud vision parsing: {e}"

def _local_screencap(output_path: str = "/sdcard/jarvis_screencap.png") -> str | None:
    """Captures a screenshot of THIS phone's screen using ADB (host device).
    Returns the saved file path on success, or None on failure.

    Uses _get_default_adb_target() which returns the first connected ADB device —
    on Termux this is always the host device serial (e.g. emulator-5554), the
    same target ui_dump already uses for local screen inspection.
    No wireless debugging needed; ADB runs locally over the loopback interface.
    """
    from jarvis.tools.devices_ext import _get_default_adb_target, _resolve_target, _ensure_adb_connected

    target_id = _get_default_adb_target()
    target = _resolve_target(target_id)

    if not _ensure_adb_connected(target):
        return None

    # screencap writes a PNG directly to the device filesystem. Since this IS
    # the device, /sdcard/ is directly accessible — no adb pull needed.
    result = subprocess.run(
        ["adb", "-s", target, "shell", "screencap", "-p", output_path],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10
    )
    if result.returncode != 0:
        return None

    # Give the file a moment to flush to disk before we read it
    import time as _time
    for _ in range(10):
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
        _time.sleep(0.2)

    return None


def read_my_screen(prompt: str = "Describe what is currently on the screen. If there is text, read it. If it is a UI, describe what app and what the user is looking at. If there are any errors or warnings, highlight them.") -> str:
    """Captures a screenshot of THIS phone's screen and sends it to the vision
    model for analysis. Use when the user asks 'what's on my screen', 'what am
    I looking at', 'read this page', 'what does this error say', or any question
    about the current screen content that goes beyond button/element listing.

    Unlike ui_dump (which reads the accessibility tree), this sees the actual
    rendered pixels — including canvas content, web views, images with text,
    PDFs, video frames, and anything uiautomator cannot introspect.

    Args:
        prompt: What to ask the vision model about the screenshot. Defaults to
                a general screen-reading prompt. Customise for specific tasks,
                e.g. 'What error is shown?' or 'Summarise the article visible.'
    """
    screencap_path = "/sdcard/jarvis_screencap.png"
    print(f"{COLOR_GRAY}[Capturing host screen via ADB screencap...]{COLOR_RESET}")

    saved_path = _local_screencap(screencap_path)
    if not saved_path:
        return "Screen capture failed: could not get a screenshot from the local ADB device. Make sure Wireless Debugging is enabled in Developer Options."

    return _process_and_upload_vision(saved_path, prompt)


def local_ocr(camera: int = 0) -> str:
    photo_path = "/sdcard/ocr_snap.jpg"
    print(f"{COLOR_GRAY}[Taking snapshot for OCR via camera {camera}...]{COLOR_RESET}")
    subprocess.run(["termux-camera-photo", "-c", str(camera), photo_path], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    
    photo_saved = False
    for _ in range(20):
        if os.path.exists(photo_path) and os.path.getsize(photo_path) > 0:
            photo_saved = True
            break
        time.sleep(0.5)

    if not photo_saved:
        return "OCR operation failed: Native camera failed to save capture frame within timeout."

    print(f"{COLOR_GRAY}[Processing local Tesseract OCR Engine...]{COLOR_RESET}")
    result = subprocess.run(["tesseract", photo_path, "stdout"], capture_output=True, text=True, stdin=subprocess.DEVNULL)

    extracted_text = result.stdout.strip()
    if not extracted_text:
        return "The local OCR engine completed processing but found no readable text inside the frame."

    return f"Extracted text from image: {extracted_text}"


def ocr_my_screen() -> str:
    """Captures a screenshot of THIS phone's screen and extracts all visible
    text from it using Tesseract OCR — offline, no API call, near-instant.

    Use this when the user asks to 'read my screen', 'read the text on screen',
    'what does that notification say', or needs raw text lifted from an app that
    blocks copy-paste (e.g. banking apps, DRM content, games). Prefer this over
    read_my_screen when the goal is text extraction rather than understanding
    layout or context.
    """
    screencap_path = "/sdcard/jarvis_screencap_ocr.png"
    print(f"{COLOR_GRAY}[Capturing host screen for OCR...]{COLOR_RESET}")

    saved_path = _local_screencap(screencap_path)
    if not saved_path:
        return "Screen capture failed: could not get a screenshot from the local ADB device. Make sure Wireless Debugging is enabled in Developer Options."

    print(f"{COLOR_GRAY}[Running Tesseract OCR on screen capture...]{COLOR_RESET}")
    result = subprocess.run(
        ["tesseract", saved_path, "stdout"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL
    )

    extracted_text = result.stdout.strip()
    if not extracted_text:
        return "OCR found no readable text on the current screen."

    return f"Text extracted from screen: {extracted_text}"


SCREENSHOT_DIR = "/sdcard/DCIM/jarvis"

def screenshot_my_screen() -> str:
    """Captures a screenshot of THIS phone's screen and saves it to
    /sdcard/DCIM/jarvis/ with a timestamp filename (e.g. screenshot_20260624_153042.png).
    Use when the user asks to 'take a screenshot', 'capture my screen', 'save what's on screen'.
    """
    import time as _time

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    timestamp = _time.strftime("%Y%m%d_%H%M%S")
    filename = f"screenshot_{timestamp}.png"
    output_path = os.path.join(SCREENSHOT_DIR, filename)

    print(f"{COLOR_GRAY}[Capturing screenshot to {output_path}...]{COLOR_RESET}")
    saved = _local_screencap(output_path)

    if not saved:
        return "Screenshot failed: could not capture the screen via local ADB."

    return f"Screenshot saved to {output_path} (in DCIM/jarvis — NOT in Downloads). Tell the user the exact path: {output_path}"
