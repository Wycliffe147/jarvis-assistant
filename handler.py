import json
import sys
import re
from collections import deque
from jarvis.config import COLOR_GRAY, COLOR_RESET, COLOR_RED, COLOR_CYAN, COLOR_GREEN, COLOR_YELLOW
from jarvis.tools import TOOLS, DATA_TOOLS
from jarvis.ai import call_ai, build_messages
from jarvis.history import load_persistent_history, save_persistent_history
from jarvis.cache.activity_cache import _load_activity_cache, _save_activity_cache

# --- Forced-refresh diagnostic queries ---
#
# These phrases map to a tool that MUST be called fresh every time, never
# answered from conversation history. Prompt-level rules (ACCURACY RULE,
# FRESHNESS RULE in config.py) reduce but don't reliably eliminate the
# model answering from a stale number it saw in its own earlier reply --
# especially on weaker fallback models. For these specific diagnostic
# queries, we don't give the model the option: the tool is called here in
# code, and the LLM is only asked to phrase the result that's already in
# hand, never to decide whether fetching it again was necessary.
FORCE_REFRESH_TOOLS = [
    (["why is my battery draining", "battery drain", "draining my battery",
      "what's using my battery", "what is using my battery"], "get_battery_diagnostics", {}),
    (["screen timeout", "screen off timeout"], "get_system_setting",
     {"key": "screen_off_timeout", "namespace": "system"}),
]


def detect_force_refresh(text: str):
    """Returns (tool_name, args) if the text matches a forced-refresh
    diagnostic query, else None. Only matches read-style phrasing ('what
    is', 'tell me', 'why') -- a command like 'set screen timeout to 30
    seconds' should still go through the normal LLM tool-selection path,
    since it needs set_system_setting, not a forced read.

    Note: "set" alone isn't enough to detect a write command -- phrasing
    like "what's my screen timeout set to" is a READ (asking what it's
    currently set to), not a write, even though it contains "set". A write
    command has a VALUE after "to" (e.g. "set screen timeout to 30
    seconds"); a read query ends at "set to" with nothing meaningful after
    it (other than a trailing "?").
    """
    t = text.lower().strip()

    if re.search(r"\bset\b", t):
        after_to = re.search(r"\bto\b(.*)$", t)
        is_write_command = bool(after_to and after_to.group(1).strip().strip("?"))
    else:
        is_write_command = any(w in t for w in ["change ", "turn on", "turn off", "enable", "disable"])

    if is_write_command:
        return None
    for phrases, tool_name, args in FORCE_REFRESH_TOOLS:
        if any(p in t for p in phrases):
            return tool_name, args
    return None


def handle_force_refresh(tool_name: str, args: dict, command_str: str, history: deque):
    """Runs a forced-refresh tool fresh, then asks the LLM only to phrase
    the result for speech -- the LLM cannot skip the tool call, only the
    wording of the final spoken answer."""
    print(f"{COLOR_GRAY}[Force-refresh: {tool_name}]{COLOR_RESET}")
    try:
        result = TOOLS[tool_name](**args)
    except Exception as e:
        result = f"[{tool_name} Error: {e}]"

    from jarvis.tools.media import speak
    extra_guidance = ""
    if tool_name == "get_battery_diagnostics":
        extra_guidance = (
            " This data describes battery STATE only -- it does not identify what is consuming power. "
            "If the user asked 'why' it's draining, do not imply these state facts are the cause. "
            "Briefly report level/health/charging status, then say this doesn't show what's using the power, "
            "and suggest checking Settings > Battery > Battery usage on the device for an app-level breakdown."
        )
    messages = build_messages(history, (
        f"The user asked: \"{command_str}\"\n"
        f"Fresh tool result just retrieved (use these exact values, do not alter them): {result}\n"
        f"Speak a short, natural, and HONEST answer using ONLY the values above.{extra_guidance} Call the 'speak' tool now."
    ))
    response_gen = call_ai(messages)
    display, full_text = handle_response(response_gen, history, messages)
    print(f"\n{COLOR_CYAN}AI Summary:{COLOR_RESET} {display}\n")

    history.append({"role": "user", "content": command_str})
    history.append({"role": "assistant", "content": f"{display}\n[Fresh tool result this turn: {result}]"})
    save_persistent_history(history)


def classify_local_intent(text: str):
    """
    Lightweight regex-based router to intercept hardware commands locally.
    Returns (tool_name, args, confirmation_text) or None.
    """
    t = text.lower().strip()
    
    # Check for hardware keywords
    is_torch = any(k in t for k in ["torch", "flashlight", "light"])
    is_wifi  = any(k in t for k in ["wifi", "wi-fi"])
    
    # Common action keywords
    on_keywords  = ["on", "activate", "enable", "start", "turn on"]
    off_keywords = ["off", "deactivate", "disable", "stop", "turn off"]
    
    # Priority on 'off' to avoid accidental 'on' matches in phrases like 'turn off'
    is_off = any(k in t for k in off_keywords)
    is_on  = any(k in t for k in on_keywords) and not is_off
    
    # --- Torch ---
    if is_torch:
        if is_on:
            return "torch", {"status": "on"}, "Flashlight enabled."
        if is_off:
            return "torch", {"status": "off"}, "Flashlight disabled."
        
    # --- WiFi ---
    if is_wifi:
        if is_on:
            return "set_wifi", {"enabled": True}, "Enabling WiFi."
        if is_off:
            return "set_wifi", {"enabled": False}, "Disabling WiFi."

    # --- Volume ---
    vol_match = re.search(r"\bvolume\b.*\b(\d+)\b", t)
    if vol_match:
        try:
            val = int(vol_match.group(1))
            return "set_volume", {"stream": "music", "volume": val}, f"Volume set to {val}."
        except: pass
    if any(k in t for k in ["volume up", "louder", "increase volume"]):
        return "set_volume", {"stream": "music", "volume": 12}, "Increasing volume."
    if any(k in t for k in ["volume down", "quieter", "decrease volume"]):
        return "set_volume", {"stream": "music", "volume": 5}, "Decreasing volume."
    if "mute" in t:
        return "set_volume", {"stream": "music", "volume": 0}, "Volume muted."

    # --- Battery ---
    # Simple level/status checks are fast-pathed. Diagnostic/analytical
    # phrasing ("why is my battery draining", "what's draining my battery")
    # needs LLM reasoning over deeper data, so it falls through instead of
    # being short-circuited to the raw status dump.
    is_diagnostic_phrasing = any(p in t for p in ["why", "drain", "draining", "what's using", "what is using"])
    if any(x in t for x in ["battery", "charge", "percentage"]) and not is_diagnostic_phrasing:
        return "get_battery_status", {}, "Checking battery status..."

    # --- Location ---
    if any(k in t for k in ["location", "gps"]):
        if any(k in t for k in on_keywords + off_keywords + ["settings", "toggle"]):
            return "open_location_settings", {}, "Opening location settings."

    # --- Time/Date ---
    if any(x in t for x in ["time is it", "current time", "what time", "what's the time"]):
        return "get_current_time", {}, "Getting current time..."
    
    # --- Vibration ---
    if "vibrate" in t:
        return "vibrate", {"duration_ms": 500}, "Vibrating phone."

    # --- ADB Pairing ---
    if "pair" in t and any(k in t for k in ["device", "phone", "adb", "wireless"]):
        return "__adb_pair__", {}, ""

    return None


def _parse_dialog_result(raw: str) -> str:
    """Extracts the user input value from a termux-dialog JSON response.
    termux-dialog returns: {"text": "value", "code": -1}
    Returns the text value, or empty string if cancelled.
    """
    try:
        data = json.loads(raw)
        if data.get("code") == -2:  # user dismissed/cancelled
            return ""
        return str(data.get("text", "")).strip()
    except Exception:
        return raw.strip() if raw else ""


def handle_adb_pairing(history: deque):
    """Runs the guided ADB pairing flow: collects all values shown on the
    Wireless Debugging screen, pairs, then connects."""
    from jarvis.tools.devices_ext import adb_pair_device, adb_connect
    from jarvis.tools.system import show_dialog
    from jarvis.tools.media import speak

    print(f"{COLOR_GRAY}[Local Route: ADB Pairing]{COLOR_RESET}")

    speak("On the target device, go to Settings, Developer Options, and open Wireless Debugging. I will need four things from that screen.")

    # Step 1 — IP address (main Wireless Debugging screen)
    raw = show_dialog(input_type="text", title="ADB Pairing — 1 of 4", hint="IP address from main screen (e.g. 10.51.91.29)")
    ip = _parse_dialog_result(raw)
    if not ip:
        msg = "No IP address provided. Pairing cancelled."
        speak(msg)
        return msg

    # Step 2 — Connection port (main Wireless Debugging screen, shown as "IP address & Port")
    raw = show_dialog(input_type="text", title="ADB Pairing — 2 of 4", hint="Connection port from main screen (e.g. 37139)")
    conn_port_str = _parse_dialog_result(raw)
    if not conn_port_str or not conn_port_str.isdigit():
        msg = "Invalid connection port. Pairing cancelled."
        speak(msg)
        return msg

    # Step 3 — Pairing port (shown in the popup after tapping Pair device with pairing code)
    speak("Now tap Pair device with pairing code on the target device.")
    raw = show_dialog(input_type="text", title="ADB Pairing — 3 of 4", hint="Pairing port from the popup (e.g. 36931)")
    pairing_port_str = _parse_dialog_result(raw)
    if not pairing_port_str or not pairing_port_str.isdigit():
        msg = "Invalid pairing port. Pairing cancelled."
        speak(msg)
        return msg

    # Step 4 — Pairing code (shown in the same popup)
    raw = show_dialog(input_type="text", title="ADB Pairing — 4 of 4", hint="6-digit pairing code from the popup (e.g. 738788)")
    code = _parse_dialog_result(raw)
    if not code:
        msg = "No pairing code provided. Pairing cancelled."
        speak(msg)
        return msg
    if not code.isdigit() or len(code) != 6:
        msg = f"{code} is not a valid 6-digit pairing code. Please try again."
        speak(msg)
        return msg

    # Pair
    speak(f"Got everything. Pairing with {ip} now.")
    pair_result = adb_pair_device(target_ip=ip, pairing_port=int(pairing_port_str), pairing_code=code)
    speak(pair_result)

    if "✅" not in pair_result:
        history.append({"role": "user", "content": "pair new adb device"})
        history.append({"role": "assistant", "content": pair_result})
        save_persistent_history(history)
        return pair_result

    # Connect using the connection port from the main screen
    speak("Pairing done. Now connecting.")
    connect_result = adb_connect(target_ip=ip, port=int(conn_port_str))
    speak(connect_result)

    final = f"{pair_result}\nConnection: {connect_result}"
    history.append({"role": "user", "content": "pair new adb device"})
    history.append({"role": "assistant", "content": final})
    save_persistent_history(history)
    return final

def handle_response(response_gen, history: deque, messages: list, _depth: int = 0) -> tuple[str, str]:
    """
    Processes a streaming response generator from call_ai.
    Parses and executes tools as soon as they are complete.
    Returns (display_text, full_raw_text).
    """
    full_text = ""
    tool_outputs = []
    final_results = []
    buffer = ""

    def process_segment(segment: str):
        nonlocal buffer
        buffer += segment
        
        while "{" in buffer:
            start_idx = buffer.find("{")
            
            # Simple balancing to find the end of the JSON object
            brace_count = 0
            end_idx = -1
            for i in range(start_idx, len(buffer)):
                if buffer[i] == "{":
                    brace_count += 1
                elif buffer[i] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            
            if end_idx == -1:
                break
            
            json_str = buffer[start_idx:end_idx]
            
            try:
                if '"tool"' in json_str or "'tool'" in json_str:
                    repaired = json_str.replace("'", '"')
                    try:
                        tool_data = json.loads(repaired)
                    except:
                        tool_data = json.loads(json_str)
                    
                    tool_name = tool_data.get("tool")
                    args = tool_data.get("args", {})
                    
                    if tool_name in TOOLS:
                        print(f"\n{COLOR_GRAY}[Running {tool_name}...]{COLOR_RESET}")
                        try:
                            result = TOOLS[tool_name](**args)
                            if tool_name not in DATA_TOOLS:
                                final_results.append(str(result))
                            else:
                                final_results.append(f"[{tool_name}] \u2192 {result}")
                            tool_outputs.append({"tool": tool_name, "result": result})
                            # Print tool result for visibility (skip 'speak' to avoid clutter)
                            if tool_name != "speak":
                                print(f"{COLOR_YELLOW}  → {result}{COLOR_RESET}")
                        except Exception as e:
                            final_results.append(f"[{tool_name} Error: {e}]")
                            print(f"{COLOR_RED}  → Error: {e}{COLOR_RESET}")
                    else:
                        final_results.append(f"[Unknown tool: {tool_name}]")
                else:
                    final_results.append(json_str)
            except Exception:
                final_results.append(json_str)

            buffer = buffer[end_idx:]

    for chunk, success in response_gen:
        if not success:
            return f"Error: {chunk}", full_text
        
        full_text += chunk
        # Only print if it doesn't look like we're in the middle of a JSON block
        if "{" not in buffer and "{" not in chunk:
            sys.stdout.write(chunk)
            sys.stdout.flush()
        
        process_segment(chunk)

    if buffer.strip():
        final_results.append(buffer.strip())

    display = "\n".join(final_results) if final_results else full_text

    # Guard against "narrated but didn't act": on the very first pass for a
    # command (_depth == 0), the model sometimes just speaks a description
    # of what it's about to do (e.g. "Opening YouTube and searching...")
    # without calling any tool at all. With no tool_outputs, the DATA_TOOLS
    # follow-up logic below never triggers, so that narration would
    # otherwise be accepted as the final answer -- a guess presented as a
    # completed action. Give the model exactly one forced retry that makes
    # it call a real tool instead of just speaking. Only applies at
    # _depth == 0; deeper passes are themselves the "speak the final
    # summary" step of an already-executed chain and are expected to end
    # in a tool-less speak.
    if _depth == 0 and not tool_outputs:
        print(f"\n{COLOR_GRAY}[No tool call detected -- forcing action...]{COLOR_RESET}")
        retry_messages = messages + [
            {"role": "assistant", "content": full_text},
            {
                "role": "user",
                "content": (
                    "You did not call any tool -- you only spoke a description of what you intend to do. "
                    "Speaking an intention is not the same as doing it. "
                    "Call the actual tool needed to perform this task now. Do not call 'speak' until "
                    "you have called at least one other tool and seen its result."
                )
            }
        ]
        retry_gen = call_ai(retry_messages)
        retry_display, retry_full = handle_response(retry_gen, history, retry_messages, _depth=_depth + 1)
        return retry_display, full_text + "\n" + retry_full

    data_results = [t for t in tool_outputs if t["tool"] in DATA_TOOLS]

    # UI-automation chains (open app -> tap -> type -> verify -> tap result...)
    # routinely need more reasoning turns than a single data lookup. Give
    # those a higher ceiling than the default 3, since a multi-step task
    # like "search X and play the first result" can easily need 5-7 turns
    # of "act, look at the screen, decide next action" before it's actually
    # done -- the old fixed limit of 3 was cutting these off mid-task.
    UI_TOOLS = {"ui_dump", "ui_find_text", "ui_tap_element", "input_my_screen"}
    is_ui_chain = any(t["tool"] in UI_TOOLS for t in tool_outputs)
    max_depth = 8 if is_ui_chain else 3

    if data_results and _depth < max_depth:
        print(f"\n{COLOR_GRAY}[Analyzing data results...]{COLOR_RESET}")
        # Forward ALL tool results from this turn, not just the DATA_TOOLS
        # ones. Otherwise, if a turn calls e.g. adb_list_devices (a data
        # tool) alongside something like get_latest_notification (not a
        # data tool), this follow-up pass would only see the ADB device
        # list and lose the actual notification result -- forcing the
        # model to either guess or blindly re-call the other tool with no
        # memory of what it already found.
        feedback = "\n".join(f"Tool result for {t['tool']}: {t['result']}" for t in tool_outputs)
        followup_messages = messages + [
            {"role": "assistant", "content": full_text},
            {
                "role": "user",
                "content": (
                    f"{feedback}\n"
                    "Now analyze these results. If you have enough information, you MUST summarize and speak the final answer to the user using the 'speak' tool now.\n"
                    "AUTO-SPEAK RULE: Do not just reply with text. You must use the 'speak' tool for your final summary."
                )
            }
        ]
        followup_gen = call_ai(followup_messages)
        followup_display, followup_full = handle_response(followup_gen, history, followup_messages, _depth=_depth + 1)
        return followup_display, full_text + "\n" + followup_full

    return display, full_text

def execute_text_command(command_str: str):
    # Structural Check: Intercept manual Option B registrations directly
    # Formats: "jarvis apps add com.example.app .ExplicitActivityClass"
    tokens = command_str.lower().split()
    if len(tokens) >= 5 and tokens[0] == "apps" and tokens[1] == "add":
        pkg = sys.argv[3].strip()
        act = sys.argv[4].strip()
        cache = _load_activity_cache()
        cache[pkg] = act
        _save_activity_cache(cache)
        print(f"{COLOR_GREEN}[Saved manual activity override: {pkg} -> {act}]{COLOR_RESET}")
        sys.exit(0)

    history = load_persistent_history()

    # --- Forced-refresh diagnostic queries ---
    # Checked BEFORE classify_local_intent and BEFORE the LLM gets a chance
    # to "decide" whether to call the tool. These specific queries (battery
    # drain, screen timeout, etc.) must always run fresh -- never answered
    # from a stale number sitting in conversation history.
    force_match = detect_force_refresh(command_str)
    if force_match:
        tool_name, args = force_match
        handle_force_refresh(tool_name, args, command_str, history)
        return

    # --- Local Fast-Pass Routing ---
    local_match = classify_local_intent(command_str)
    if local_match:
        tool_name, args, confirmation = local_match

        # Multi-step flows get their own handler
        if tool_name == "__adb_pair__":
            handle_adb_pairing(history)
            return

        print(f"{COLOR_GRAY}[Local Route: {tool_name}]{COLOR_RESET}")
        try:
            result = TOOLS[tool_name](**args)
            display = f"{confirmation}\n{result}"
            print(f"\n{COLOR_CYAN}AI Summary (Local):{COLOR_RESET} {display}\n")
            history.append({"role": "user", "content": command_str})
            history.append({"role": "assistant", "content": display})
            save_persistent_history(history)
            return
        except Exception as e:
            print(f"{COLOR_RED}Local Execution Error: {e}{COLOR_RESET}")

    messages = build_messages(history, command_str)
    
    print(f"{COLOR_GRAY}[Thinking...]{COLOR_RESET}", end="\r", flush=True)
    response_gen = call_ai(messages)
    
    display, full_text = handle_response(response_gen, history, messages)
    print(f"\n{COLOR_CYAN}AI Summary:{COLOR_RESET} {display}\n")
    
    history.append({"role": "user", "content": command_str})
    if '{"tool":' in full_text:
        history.append({"role": "assistant", "content": f"{full_text}\n[Executed Results Summary]: {display}"})
    else:
        history.append({"role": "assistant", "content": full_text})
        
    save_persistent_history(history)
