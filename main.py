import sys
import time
import subprocess
from jarvis.config import COLOR_GREEN, COLOR_YELLOW, COLOR_GRAY, COLOR_BLUE, COLOR_CYAN, COLOR_RED, COLOR_RESET
from jarvis.history import load_persistent_history, save_persistent_history
from jarvis.cache.music_cache import _load_music_cache, _save_music_cache, _scan_music_files
from jarvis.voice import listen_for_wake_word, get_voice_input
from jarvis.tools.device import vibrate
from jarvis.tools.media import speak
from jarvis.tools.link import link_start_server
from jarvis.tools.devices_ext import adb_self_connect
from jarvis.ai import call_ai, build_messages
from jarvis.handler import handle_response, execute_text_command, classify_local_intent


def clean_assistant_turn(full_text: str, display: str) -> str:
    """Builds what goes into chat history for an assistant turn.

    CRITICAL: never store raw JSON tool-call lines or the
    '[Executed Results Summary]' scaffolding in history. Weak fallback models
    (llama-3.1-8b-instant, gpt-oss-20b) will pattern-complete that exact format
    in future turns instead of emitting a real tool call — i.e. they'll narrate
    fake "Successfully executed ADB..." text rather than actually calling the
    tool. History should only ever contain what the assistant actually said to
    the user in natural language.
    """
    # Strip any literal JSON tool-call lines, just in case full_text leaks through.
    lines = []
    for line in full_text.splitlines():
        stripped = line.strip()
        if stripped.startswith('{"tool"') or stripped.startswith('{ "tool"'):
            continue
        lines.append(line)
    leftover_text = "\n".join(lines).strip()

    # If the model's own text had a natural-language remainder (rare, since most
    # tool-calling turns are pure JSON), prefer that. Otherwise fall back to the
    # spoken/displayed summary — but never tag it as an "Executed Results Summary".
    return leftover_text if leftover_text else display


def append_turn(history, user_input: str, full_text: str, display: str):
    """Single place to append a user/assistant exchange to history, ensuring the
    assistant side is always sanitized (see clean_assistant_turn)."""
    history.append({"role": "user", "content": user_input})
    history.append({"role": "assistant", "content": clean_assistant_turn(full_text, display)})


def run_voice_loop():
    print(f"{COLOR_GREEN}\n--- Jarvis Voice Wake Word Mode Active ---{COLOR_RESET}")
    print(f"Say {COLOR_YELLOW}'Jarvis'{COLOR_RESET} to activate. press Ctrl+C to stop audio loop.\n")

    history = load_persistent_history()

    if _load_music_cache() is None:
        print(f"{COLOR_GRAY}[Scanning storage for music...]{COLOR_RESET}")
        files = _scan_music_files()
        _save_music_cache(files)
        print(f"{COLOR_GRAY}[Music cache ready: {len(files)} files found]{COLOR_RESET}")

    print(f"{COLOR_GRAY}[Listening for wake word...]{COLOR_RESET}")
    while True:
        try:
            inline_command = listen_for_wake_word("jarvis")
            if inline_command is None:
                continue

            print(f"{COLOR_GREEN}[Wake word detected!]{COLOR_RESET}", flush=True)
            vibrate(200)

            if inline_command:
                print(f"{COLOR_BLUE}You (Voice):{COLOR_RESET} {inline_command}")
                user_input = inline_command
            else:
                user_input = get_voice_input()
                if not user_input:
                    print(f"{COLOR_GRAY}[Listening for wake word...]{COLOR_RESET}")
                    continue

            # --- Local Fast-Pass Routing ---
            local_match = classify_local_intent(user_input)
            if local_match:
                tool_name, args, confirmation = local_match
                print(f"{COLOR_GRAY}[Local Route: {tool_name}]{COLOR_RESET}")
                try:
                    from jarvis.tools import TOOLS
                    result = TOOLS[tool_name](**args)
                    display = f"{confirmation}\n{result}"
                    print(f"\n{COLOR_CYAN}AI Summary (Local):{COLOR_RESET} {display}\n")
                    speak(confirmation)
                    append_turn(history, user_input, confirmation, display)
                    save_persistent_history(history)
                    # Skip to follow-up logic
                except Exception as e:
                    print(f"{COLOR_RED}Local Execution Error: {e}{COLOR_RESET}")
                    # Fallback to AI
                    messages = build_messages(history, user_input)
                    print(f"{COLOR_GRAY}[Thinking...]{COLOR_RESET}", end="\r", flush=True)
                    response_gen = call_ai(messages)
                    display, full_text = handle_response(response_gen, history, messages)
                    print(f"\n{COLOR_CYAN}AI Summary:{COLOR_RESET} {display}\n")
                    append_turn(history, user_input, full_text, display)
                    save_persistent_history(history)
            else:
                messages = build_messages(history, user_input)
                print(f"{COLOR_GRAY}[Thinking...]{COLOR_RESET}", end="\r", flush=True)
                response_gen = call_ai(messages)

                display, full_text = handle_response(response_gen, history, messages)
                print(f"\n{COLOR_CYAN}AI Summary:{COLOR_RESET} {display}\n")
                append_turn(history, user_input, full_text, display)
                save_persistent_history(history)

            follow_up_deadline = time.time() + 10
            while time.time() < follow_up_deadline:
                remaining = int(follow_up_deadline - time.time())
                print(f"{COLOR_GRAY}[Follow-up? {remaining}s...]{COLOR_RESET}", end="\r", flush=True)
                user_input = get_voice_input()
                if user_input:
                    messages = build_messages(history, user_input)
                    print(f"{COLOR_GRAY}[Thinking...]{COLOR_RESET}", end="\r", flush=True)
                    response_gen = call_ai(messages)
                    display, full_text = handle_response(response_gen, history, messages)
                    print(f"\n{COLOR_CYAN}AI Summary:{COLOR_RESET} {display}\n")
                    append_turn(history, user_input, full_text, display)
                    save_persistent_history(history)
                    follow_up_deadline = time.time() + 10
                    continue
                break

            print(f"{COLOR_GRAY}[Listening for wake word...]{COLOR_RESET}")

        except KeyboardInterrupt:
            print("\nDropping voice environment...")
            break
        except Exception as e:
            print(f"Error: {e}")

def main():
    # Auto-start the Jarvis Link local communications server
    try:
        status_msg = link_start_server()
        print(f"{COLOR_GRAY}[{status_msg}]{COLOR_RESET}")
    except Exception as e:
        print(f"{COLOR_RED}[Failed to start Jarvis Link: {e}]{COLOR_RESET}")

    # Silently attempt self-ADB loopback connect for screen control features.
    # If it fails, wireless debugging is off — open the settings screen and prompt.
    if adb_self_connect():
        print(f"{COLOR_GRAY}[Self-ADB connected on 127.0.0.1:5555]{COLOR_RESET}")
    else:
        print(f"{COLOR_YELLOW}[Self-ADB unavailable — wireless debugging is off]{COLOR_RESET}")
        try:
            subprocess.run(
                ["am", "start", "-n",
                 "com.android.settings/.Settings$WirelessDebuggingActivity"],
                stdin=subprocess.DEVNULL, capture_output=True
            )
        except Exception:
            pass
        speak("Wireless debugging is off. I've opened the settings — please enable it so I can control the screen.")

    if len(sys.argv) > 1:
        command_str = " ".join(sys.argv[1:])
        
        if command_str.lower().strip() == "voice":
            run_voice_loop()
        else:
            execute_text_command(command_str)
        sys.exit(0)

    run_voice_loop()

if __name__ == "__main__":
    main()
