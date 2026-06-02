import subprocess
import json

def send_sms(number: str, message: str):
    subprocess.run(["termux-sms-send", "-n", number, message], stdin=subprocess.DEVNULL)
    return f"SMS sent to {number}: {message}"

def list_sms(limit: int = 5):
    result = subprocess.run(["termux-sms-list", "-l", str(limit)], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def get_call_log(limit: int = 5):
    result = subprocess.run(["termux-call-log", "-l", str(limit)], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def get_contacts():
    result = subprocess.run(["termux-contact-list"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def find_contact(name: str) -> str:
    result = subprocess.run(["termux-contact-list"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    try:
        contacts = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return "Could not read contacts."

    name_lower = name.lower()
    matches = [c for c in contacts if name_lower in c.get("name", "").lower()]

    if not matches:
        return f"No contact found matching '{name}'."

    return "\n".join(f"{c['name']} \u2192 {c['number']}" for c in matches)

def make_call(number: str):
    subprocess.run(["termux-telephony-call", number], stdin=subprocess.DEVNULL)
    return f"Calling {number}"

def open_dialer(number: str = ""):
    uri = f"tel:{number}" if number else "tel:"
    subprocess.run(["am", "start", "-a", "android.intent.action.DIAL", "-d", uri], stdin=subprocess.DEVNULL)
    return f"Dialer opened{' with ' + number if number else ''}"
