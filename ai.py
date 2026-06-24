import requests
import os
import json
from collections import deque
from datetime import date
from jarvis.config import API_KEY, URL_CHAT, URL_WHISPER, MODEL_PRIMARY, MODEL_FALLBACK, SYSTEM_PROMPT, COLOR_YELLOW, COLOR_RESET, COLOR_RED, CEREBRAS_API_KEY, URL_CEREBRAS, MODEL_CEREBRAS_FALLBACK
from jarvis.tools.media import speak
from jarvis.tools import TOOLS_DESCRIPTION

active_model = MODEL_PRIMARY
_primary_exhausted_date = None    # date when Groq primary (70b) daily quota was exhausted
_cerebras_exhausted_date = None   # date when Cerebras (120b, 2nd tier) was also exhausted


def _get_model() -> str:
    """Returns the best available model. Tries Groq primary (70b) first,
    then Cerebras (120b, a genuinely separate quota pool, bigger than the
    Groq fallback) second, then Groq's own fallback (8b) as the absolute
    last resort -- only reached once BOTH the primary and Cerebras are
    exhausted today. Each exhaustion flag resets automatically the next day."""
    global active_model, _primary_exhausted_date, _cerebras_exhausted_date
    today = date.today()

    if _primary_exhausted_date is not None and _primary_exhausted_date != today:
        active_model = MODEL_PRIMARY
        _primary_exhausted_date = None
    if _cerebras_exhausted_date is not None and _cerebras_exhausted_date != today:
        _cerebras_exhausted_date = None

    if _primary_exhausted_date == today and _cerebras_exhausted_date == today:
        return MODEL_FALLBACK
    if _primary_exhausted_date == today and CEREBRAS_API_KEY:
        return MODEL_CEREBRAS_FALLBACK
    if _primary_exhausted_date == today:
        # No Cerebras key configured — skip straight to Groq fallback.
        return MODEL_FALLBACK
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


def _apply_gpt_oss_params(payload: dict, model: str):
    """Sets the right gpt-oss-specific params for whichever provider is
    serving the model. Cerebras's API supports the standard reasoning_effort
    parameter but rejects include_reasoning entirely (400: unsupported) --
    that param is specific to other gpt-oss hosts (e.g. Groq's), not part
    of Cerebras's API surface."""
    if "gpt-oss" not in model:
        return
    payload["reasoning_effort"] = "low"
    if model != MODEL_CEREBRAS_FALLBACK:
        payload["include_reasoning"] = False


def _endpoint_for(model: str) -> tuple[str, dict]:
    """Returns (url, headers) for the given model. Cerebras is a genuinely
    separate provider with its own base URL and API key — everything else
    (Groq primary/fallback) shares Groq's endpoint and key."""
    if model == MODEL_CEREBRAS_FALLBACK:
        return URL_CEREBRAS, {"Authorization": f"Bearer {CEREBRAS_API_KEY}", "Content-Type": "application/json"}
    return URL_CHAT, {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def _post(payload, headers, stream, url=URL_CHAT):
    return requests.post(url, headers=headers, json=payload, timeout=20, stream=stream)


def _non_streaming_retry(payload, headers, url=URL_CHAT):
    """Retries the same model non-streaming. Used both when streaming yields
    nothing and when Groq's tool_use_failed bug fires — non-streaming is more
    reliable for surfacing real content on reasoning models, and a plain retry
    often dodges the transient tool_use_failed bug entirely."""
    retry_payload = dict(payload)
    retry_payload["stream"] = False
    try:
        r2 = requests.post(url, headers=headers, json=retry_payload, timeout=20)
        if r2.status_code == 200:
            text = r2.json()["choices"][0]["message"].get("content", "").strip()
            if text:
                return text, True
            return "", True
        if _is_tool_use_failed(r2.text):
            # Give it one more shot — this Groq-side bug is often transient.
            try:
                r3 = requests.post(url, headers=headers, json=retry_payload, timeout=20)
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
    global active_model, _primary_exhausted_date, _fallback_exhausted_date
    model = _get_model()
    url, headers = _endpoint_for(model)
    payload = {"model": model, "messages": messages, "max_tokens": 800, "stream": stream}
    _apply_gpt_oss_params(payload, model)

    try:
        r = _post(payload, headers, stream, url=url)

        if r.status_code == 429 and model == MODEL_PRIMARY:
            _primary_exhausted_date = date.today()
            if CEREBRAS_API_KEY:
                print(f"{COLOR_YELLOW}[Daily quota exhausted on {MODEL_PRIMARY}, switching to Cerebras ({MODEL_CEREBRAS_FALLBACK}) until midnight UTC]{COLOR_RESET}", flush=True)
                model = MODEL_CEREBRAS_FALLBACK
                url, headers = _endpoint_for(model)
                payload["model"] = model
                _apply_gpt_oss_params(payload, model)
            else:
                print(f"{COLOR_YELLOW}[Daily quota exhausted on {MODEL_PRIMARY}, switching to {MODEL_FALLBACK} until midnight UTC]{COLOR_RESET}", flush=True)
                active_model = MODEL_FALLBACK
                model = MODEL_FALLBACK
                url, headers = _endpoint_for(model)
                payload["model"] = model
            r = _post(payload, headers, stream, url=url)

        if r.status_code == 429 and model == MODEL_CEREBRAS_FALLBACK:
            print(f"{COLOR_YELLOW}[Cerebras ({MODEL_CEREBRAS_FALLBACK}) also exhausted, switching to {MODEL_FALLBACK} until midnight UTC]{COLOR_RESET}", flush=True)
            _cerebras_exhausted_date = date.today()
            active_model = MODEL_FALLBACK
            model = MODEL_FALLBACK
            url, headers = _endpoint_for(model)
            payload["model"] = model
            r = _post(payload, headers, stream, url=url)

        if r.status_code == 400 and _is_tool_use_failed(r.text):
            # Groq-side bug: it attaches an implicit tool schema and then rejects
            # the model's own tool call. Not caused by our payload (we never send
            # `tools`). A plain retry, or falling back to non-streaming, usually
            # gets a clean response.
            print(f"{COLOR_RED}[Groq tool_use_failed glitch on {model}, retrying...]{COLOR_RESET}")
            text, ok = _non_streaming_retry(payload, headers, url=url)
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
                text, ok = _non_streaming_retry(payload, headers, url=url)
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
