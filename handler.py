import json
import sys
from collections import deque
from jarvis.config import COLOR_GRAY, COLOR_RESET, COLOR_RED, COLOR_CYAN, COLOR_GREEN
from jarvis.tools import TOOLS, DATA_TOOLS
from jarvis.ai import call_ai, build_messages
from jarvis.history import load_persistent_history, save_persistent_history
from jarvis.cache.activity_cache import _load_activity_cache, _save_activity_cache

def handle_response(response_text: str, history: deque, messages: list, _depth: int = 0) -> str:
    if '{"tool":' not in response_text:
        return response_text

    results      = []
    tool_outputs = []
    text         = response_text.strip()

    while text:
        start = text.find('{')
        if start == -1:
            break
        try:
            decoder = json.JSONDecoder()
            tool_data, end_idx = decoder.raw_decode(text, start)
        except json.JSONDecodeError as e:
            results.append(f"[JSON Error: {e}]")
            break

        tool_name = tool_data.get("tool")
        args      = tool_data.get("args", {})

        if tool_name not in TOOLS:
            results.append(f"[Unknown tool: {tool_name}]")
        else:
            print(f"{COLOR_GRAY}[Running {tool_name}...]{COLOR_RESET}")
            try:
                result = TOOLS[tool_name](**args)
                results.append(f"[{tool_name}] \u2192 {result}")
                tool_outputs.append({"tool": tool_name, "result": result})
            except Exception as e:
                results.append(f"[{tool_name} Error: {e}]")

        text = text[start + end_idx:].strip()

    data_results = [t for t in tool_outputs if t["tool"] in DATA_TOOLS]
    if data_results and _depth == 0:
        feedback = "\n".join(f"Tool result for {t['tool']}: {t['result']}" for t in data_results)
        followup_messages = messages + [
            {"role": "assistant", "content": response_text},
            {
                "role": "user",
                "content": (
                    f"{feedback}\n"
                    "Now summarize and speak the key information naturally to the user using the speak tool.\n"
                    "CRITICAL ASSISTANT ROUTING RULES:\n"
                    "1. If the tool result is from search_launcher_apps and doesn't contain an error, IMMEDIATELY trigger open_app using that verified package identifier mapping string.\n"
                    "2. If find_contact returns multiple matching names or numbers, list choices via speak and ask to clarify.\n"
                    "3. If find_contact has EXACTLY ONE clear match, call make_call.\n"
                    "4. If the result is from find_music, play_media.\n"
                    "5. If the result is from analyze_photo or local_ocr, speak the outcome cleanly."
                )
            }
        ]
        followup_text, success = call_ai(followup_messages)
        if success:
            followup_display = handle_response(followup_text, history, followup_messages, _depth=1)
            results.append(followup_display)

    return "\n".join(results) if results else response_text

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
    messages = build_messages(history, command_str)
    response_text, success = call_ai(messages)
    
    if not success:
        print(f"{COLOR_RED}AI Error:{COLOR_RESET} {response_text}\n")
    else:
        display = handle_response(response_text, history, messages)
        print(f"\n{COLOR_CYAN}AI:{COLOR_RESET} {display}\n")
        
        history.append({"role": "user", "content": command_str})
        if '{"tool":' in response_text:
            history.append({"role": "assistant", "content": f"{response_text}\n[Executed Results Summary]: {display}"})
        else:
            history.append({"role": "assistant", "content": response_text})
            
        save_persistent_history(history)
