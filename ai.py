import requests
import os
import json
from collections import deque
from datetime import date
from jarvis.config import API_KEY, URL_CHAT, URL_WHISPER, MODEL_PRIMARY, MODEL_FALLBACK, SYSTEM_PROMPT, COLOR_YELLOW, COLOR_RESET, COLOR_RED
from jarvis.tools.media import speak
from jarvis.tools import TOOLS_DESCRIPTION

active_model = MODEL_PRIMARY
_primary_exhausted_date = None  # date when primary daily quota was exhausted


def _get_model() -> str:
    """Returns the best available model. Skips primary if its daily quota was
    exhausted today. Resets automatically the next day when Groq refreshes quota."""
    global active_model, _primary_exhausted_date
    if _primary_exhausted_date is not None and _primary_exhausted_date == date.today():
        return MODEL_FALLBACK
    # New day has started — reset and try primary again
    if _primary_exhausted_date is not None and _primary_exhausted_date != date.today():
        active_model = MODEL_PRIMARY
        _primary_exhausted_date = None
    return active_model


def _is_tool_use_failed(resp_text: str) -> bool:
    """Detects Groq's server-side 'tool_choice is none, but model called a tool'
    bug. This fires even when we never send a `tools` param — Groq appears to
    attach an implicit tool schema (e.g. a built-in browser/search tool) on its
    own and then rejects the model's own output. Not something the client
    payload controls; just needs to be retried/recovered from."""
    return '"code":"tool_use_failed"' in resp_text or "Tool choice is none, but model called a tool" in resp_text


def _stream_response(r):
    """Parses a streaming SSE response, handling both standard delta content
    and reasoning_content fields used by some models (e.g. gpt-oss-20b).
    NOTE: with include_reasoning=False set in call_ai, reasoning_content should
    rarely appear. This fallback is a safety net only — do not rely on it for
    tool-call parsing, since reasoning text is not guaranteed to contain a
    well-formed final answer or JSON tool-call."""
    for line in r.iter_lines():
        if not line:
            continue
        line_str = line.decode('utf-8')
        if not line_str.startswith("data: "):
            continue
        data_part = line_str[6:]
        if data_part == "[DONE]":
            break
        try:
            chunk = json.loads(data_part)
            delta = chunk["choices"][0]["delta"]
            # Standard content field
            text = delta.get("content") or ""
            # Some models put output in reasoning_content instead
            if not text:
                text = delta.get("reasoning_content") or ""
            if text:
                yield text, True
        except Exception:
            continue


def _post(payload, headers, stream):
    return requests.post(URL_CHAT, headers=headers, json=payload, timeout=20, stream=stream)


def _non_streaming_retry(payload, headers):
    """Retries the same model non-streaming. Used both when streaming yields
    nothing and when Groq's tool_use_failed bug fires — non-streaming is more
    reliable for surfacing real content on reasoning models, and a plain retry
    often dodges the transient tool_use_failed bug entirely."""
    retry_payload = dict(payload)
    retry_payload["stream"] = False
    try:
        r2 = requests.post(URL_CHAT, headers=headers, json=retry_payload, timeout=20)
        if r2.status_code == 200:
            text = r2.json()["choices"][0]["message"].get("content", "").strip()
            if text:
                return text, True
            return "", True
        if _is_tool_use_failed(r2.text):
            # Give it one more shot — this Groq-side bug is often transient.
            try:
                r3 = requests.post(URL_CHAT, headers=headers, json=retry_payload, timeout=20)
                if r3.status_code == 200:
                    text = r3.json()["choices"][0]["message"].get("content", "").strip()
                    return text, True
            except Exception as e:
                return f"Request Error: {e}", False
            return "Sorry, I had trouble getting a clean response that time — please try again.", True
        return f"API Error {r2.status_code}: {r2.text[:200]}", False
    except Exception as e:
        return f"Retry Error: {e}", False


def call_ai(messages: list, stream: bool = True):
    global active_model, _primary_exhausted_date
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    model = _get_model()
    payload = {"model": model, "messages": messages, "max_tokens": 800, "stream": stream}
    if "gpt-oss" in model:
        # gpt-oss models often route the tool-call / answer text into reasoning_content
        # instead of content, especially with a long system prompt + tools list.
        # Forcing low reasoning effort and excluding reasoning from the response keeps
        # the model focused on emitting the final JSON tool-call / answer in `content`.
        payload["reasoning_effort"] = "low"
        payload["include_reasoning"] = False

    try:
        r = _post(payload, headers, stream)

        if r.status_code == 429 and model == MODEL_PRIMARY:
            print(f"{COLOR_YELLOW}[Daily quota exhausted on {MODEL_PRIMARY}, switching to {MODEL_FALLBACK} until midnight UTC]{COLOR_RESET}", flush=True)
            _primary_exhausted_date = date.today()
            active_model = MODEL_FALLBACK
            model = MODEL_FALLBACK
            payload["model"] = model
            if "gpt-oss" in model:
                payload["reasoning_effort"] = "low"
                payload["include_reasoning"] = False
            r = _post(payload, headers, stream)

        if r.status_code == 400 and _is_tool_use_failed(r.text):
            # Groq-side bug: it attaches an implicit tool schema and then rejects
            # the model's own tool call. Not caused by our payload (we never send
            # `tools`). A plain retry, or falling back to non-streaming, usually
            # gets a clean response.
            print(f"{COLOR_RED}[Groq tool_use_failed glitch on {model}, retrying...]{COLOR_RESET}")
            text, ok = _non_streaming_retry(payload, headers)
            yield text, ok
            return

        if r.status_code != 200:
            yield f"API Error {r.status_code}: {r.text[:200]}", False
            return

        if stream:
            yielded_anything = False
            for text, ok in _stream_response(r):
                yielded_anything = True
                yield text, ok
            if not yielded_anything:
                print(f"{COLOR_RED}[Warning: streaming returned empty response from {model}. Retrying non-streaming...]{COLOR_RESET}")
                text, ok = _non_streaming_retry(payload, headers)
                yield text, ok
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
