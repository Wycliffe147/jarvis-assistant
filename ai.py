import requests
import os
import json
from collections import deque
from jarvis.config import API_KEY, URL_CHAT, URL_WHISPER, MODEL_PRIMARY, MODEL_FALLBACK, SYSTEM_PROMPT, COLOR_YELLOW, COLOR_RESET, COLOR_RED
from jarvis.tools.media import speak
from jarvis.tools import TOOLS_DESCRIPTION

active_model = MODEL_PRIMARY

def call_ai(messages: list, stream: bool = True):
    global active_model
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"model": active_model, "messages": messages, "max_tokens": 400, "stream": stream}
    
    try:
        r = requests.post(URL_CHAT, headers=headers, json=payload, timeout=20, stream=stream)
        
        if r.status_code == 429 and active_model == MODEL_PRIMARY:
            print(f"{COLOR_YELLOW}[Rate limit hit on {MODEL_PRIMARY}, switching to {MODEL_FALLBACK}...]{COLOR_RESET}", flush=True)
            active_model = MODEL_FALLBACK
            payload["model"] = active_model
            r = requests.post(URL_CHAT, headers=headers, json=payload, timeout=20, stream=stream)
            
        if r.status_code != 200:
            yield f"API Error {r.status_code}: {r.text[:200]}", False
            return

        if stream:
            full_content = ""
            for line in r.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: "):
                        data_part = line_str[6:]
                        if data_part == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_part)
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                full_content += delta
                                yield delta, True
                        except Exception:
                            continue
        else:
            text = r.json()["choices"][0]["message"]["content"].strip()
            yield text, True

    except Exception as e:
        yield f"Request Error: {e}", False

def transcribe_audio(filepath: str) -> str | None:
    try:
        with open(filepath, "rb") as f:
            r = requests.post(
                URL_WHISPER,
                headers={"Authorization": f"Bearer {API_KEY}"},
                files={"file": (os.path.basename(filepath), f, "audio/wav")},
                data={
                    "model": "whisper-large-v3",
                    "response_format": "text",
                    "language": "en",
                    "prompt": "Commands for a phone assistant: call log, flashlight, battery, volume, SMS, contacts, location, WiFi, torch, brightness, camera, next track, previous track, pause, stop music, call, dial, ring, OCR, read text, open application, package, launcher search."
                },
                timeout=30
            )
        if r.status_code == 200:
            return r.text.strip()
        else:
            print(f"{COLOR_RED}Whisper Error {r.status_code}:{COLOR_RESET} {r.text[:200]}")
            return None
    except Exception as e:
        print(f"Transcription Error: {e}")
        return None

def build_messages(history: deque, user_input: str) -> list:
    full_system_prompt = f"{SYSTEM_PROMPT}\nAvailable tools:\n{TOOLS_DESCRIPTION}"
    messages = [{"role": "system", "content": full_system_prompt}]
    for msg in history:
        role = "assistant" if msg["role"] == "assistant" else "user"
        messages.append({"role": role, "content": msg["content"]})
    messages.append({"role": "user", "content": user_input})
    return messages
