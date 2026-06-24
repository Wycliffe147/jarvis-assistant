import json
import sys
import re
from collections import deque
from jarvis.config import COLOR_GRAY, COLOR_RESET, COLOR_RED, COLOR_CYAN, COLOR_GREEN
from jarvis.tools import TOOLS, DATA_TOOLS
from jarvis.ai import call_ai, build_messages
from jarvis.history import load_persistent_history, save_persistent_history
from jarvis.cache.activity_cache import _load_activity_cache, _save_activity_cache

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
                        except Exception as e:
                            final_results.append(f"[{tool_name} Error: {e}]")
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

    data_results = [t for t in tool_outputs if t["tool"] in DATA_TOOLS]
    if data_results and _depth < 3:
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
