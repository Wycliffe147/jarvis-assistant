import datetime
import threading
import time
import subprocess
from jarvis.tools.media import speak

def get_current_time():
    """Returns the current date and time."""
    return datetime.datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

def set_timer(seconds: int, message: str = "Timer finished!"):
    """Sets a timer to speak a message after x seconds."""
    try:
        seconds = int(seconds)
    except ValueError:
        return f"Error: Timer duration '{seconds}' is not a valid number."

    def timer_task():
        time.sleep(seconds)
        speak(message)
    
    thread = threading.Thread(target=timer_task)
    thread.start()
    return f"Timer set for {seconds} seconds."

def schedule_action(delay_seconds: int, tool_name: str, tool_args: dict = {}):
    """Schedules a tool to run after a specified delay."""
    from jarvis.tools import TOOLS
    
    try:
        delay_seconds = int(delay_seconds)
    except ValueError:
        return f"Error: Delay '{delay_seconds}' is not a valid number."
    
    if tool_name not in TOOLS:
        return f"Error: Tool '{tool_name}' not found."
    
    def delayed_task():
        time.sleep(delay_seconds)
        TOOLS[tool_name](**tool_args)
        
    thread = threading.Thread(target=delayed_task)
def set_alarm(hour: int, minutes: int, message: str = "Alarm"):
    """Sets a system alarm."""
    try:
        hour = int(hour)
        minutes = int(minutes)
    except ValueError:
        return f"Error: Hour or minutes are not valid numbers."

    cmd = [
        "am", "start", "-a", "android.intent.action.SET_ALARM",
        "--ei", "android.intent.extra.alarm.HOUR", str(hour),
        "--ei", "android.intent.extra.alarm.MINUTES", str(minutes),
        "--es", "android.intent.extra.alarm.MESSAGE", message
    ]
    subprocess.run(cmd, stdin=subprocess.DEVNULL)
    return f"System alarm set for {hour:02}:{minutes:02} with message: {message}"
