import subprocess
import os
import time
import requests
from jarvis.config import API_KEY, MODEL_VISION, URL_CHAT, VISION_MAX_PX, VISION_PHOTO_FILE, COLOR_GRAY, COLOR_RED, COLOR_RESET

def take_photo(camera: int = 0, output: str = "/sdcard/photo.jpg"):
    subprocess.run(["termux-camera-photo", "-c", str(camera), output], stdin=subprocess.DEVNULL)
    return f"Photo taken with camera {camera}, saved to {output}"

def analyze_photo(prompt: str = "Describe what you see in detail.", camera: int = 0) -> str:
    photo_path = VISION_PHOTO_FILE
    print(f"{COLOR_GRAY}[Taking snapshot via camera {camera}...]{COLOR_RESET}")
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
    try:
        ffmpeg_check = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if ffmpeg_check.returncode == 0:
            resized_path = "/sdcard/jarvis_vision_small.jpg"
            if os.path.exists(resized_path):
                os.remove(resized_path)
                
            subprocess.run([
                "ffmpeg", "-y", "-i", input_path,
                "-vf", f"scale='if(gt(iw,ih),{VISION_MAX_PX},-2)':'if(gt(iw,ih),-2,{VISION_MAX_PX})'",
                "-q:v", "2",
                resized_path
            ], capture_output=True, stdin=subprocess.DEVNULL)
            
            if os.path.exists(resized_path) and os.path.getsize(resized_path) > 0:
                image_path = resized_path
    except Exception:
        pass

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
