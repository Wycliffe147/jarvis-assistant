import sys
import time
from jarvis.config import COLOR_GREEN, COLOR_YELLOW, COLOR_GRAY, COLOR_BLUE, COLOR_CYAN, COLOR_RED, COLOR_RESET
from jarvis.history import load_persistent_history, save_persistent_history
from jarvis.cache.music_cache import _load_music_cache, _save_music_cache, _scan_music_files
from jarvis.voice import listen_for_wake_word, get_voice_input
from jarvis.tools.device import vibrate
from jarvis.ai import call_ai, build_messages
from jarvis.handler import handle_response, execute_text_command

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

            messages = build_messages(history, user_input)
            response_text, success = call_ai(messages)

            if not success:
                print(f"{COLOR_RED}AI Error:{COLOR_RESET} {response_text}\n")
            else:
                display = handle_response(response_text, history, messages)
                print(f"\n{COLOR_CYAN}AI:{COLOR_RESET} {display}\n")
                history.append({"role": "user", "content": user_input})
                if '{"tool":' in response_text:
                    history.append({"role": "assistant", "content": f"{response_text}\n[Executed Results Summary]: {display}"})
                else:
                    history.append({"role": "assistant", "content": response_text})
                save_persistent_history(history)

            follow_up_deadline = time.time() + 10
            while time.time() < follow_up_deadline:
                remaining = int(follow_up_deadline - time.time())
                print(f"{COLOR_GRAY}[Follow-up? {remaining}s...]{COLOR_RESET}", end="\r", flush=True)
                user_input = get_voice_input()
                if user_input:
                    messages = build_messages(history, user_input)
                    response_text, success = call_ai(messages)
                    if not success:
                        print(f"{COLOR_RED}AI Error:{COLOR_RESET} {response_text}\n")
                    else:
                        display = handle_response(response_text, history, messages)
                        print(f"\n{COLOR_CYAN}AI:{COLOR_RESET} {display}\n")
                        history.append({"role": "user", "content": user_input})
                        if '{"tool":' in response_text:
                            history.append({"role": "assistant", "content": f"{response_text}\n[Executed Results Summary]: {display}"})
                        else:
                            history.append({"role": "assistant", "content": response_text})
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
