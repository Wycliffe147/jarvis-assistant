import json
import os
from collections import deque
from jarvis.config import HISTORY_FILE, MAX_HISTORY, COLOR_GRAY, COLOR_RESET

def load_persistent_history() -> deque:
    history = deque(maxlen=MAX_HISTORY)
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                for item in data[-MAX_HISTORY:]:
                    history.append(item)
    except Exception as e:
        print(f"{COLOR_GRAY}[History read error: {e}]{COLOR_RESET}")
    return history

def save_persistent_history(history: deque):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(list(history), f)
    except Exception as e:
        print(f"{COLOR_GRAY}[History write error: {e}]{COLOR_RESET}")
