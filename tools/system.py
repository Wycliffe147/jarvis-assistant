import subprocess

def get_clipboard():
    result = subprocess.run(["termux-clipboard-get"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def set_clipboard(text: str):
    subprocess.run(["termux-clipboard-set", text], stdin=subprocess.DEVNULL)
    return f"Clipboard set to: {text}"

def show_notification(title: str = "Notification", content: str = "", id: int = 1):
    subprocess.run(["termux-notification", "--title", title, "--content", content, "--id", str(id)], stdin=subprocess.DEVNULL)
    return f"Notification shown: {title} - {content}"

def remove_notification(id: int = 1):
    subprocess.run(["termux-notification-remove", str(id)], stdin=subprocess.DEVNULL)
    return f"Notification {id} removed"

def set_wallpaper(file: str = "", url: str = ""):
    if url:
        subprocess.run(["termux-wallpaper", "-u", url], stdin=subprocess.DEVNULL)
        return f"Wallpaper set from URL: {url}"
    elif file:
        subprocess.run(["termux-wallpaper", "-f", file], stdin=subprocess.DEVNULL)
        return f"Wallpaper set from file: {file}"
    return "No file or URL provided"

def show_dialog(input_type: str = "text", title: str = "Input", hint: str = ""):
    result = subprocess.run(["termux-dialog", input_type, "-t", title, "-i", hint], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def fingerprint_auth():
    result = subprocess.run(["termux-fingerprint"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def show_toast(message: str):
    subprocess.run(["termux-toast", message], stdin=subprocess.DEVNULL)
    return f"Toast shown: {message}"

def share(text: str = "", file: str = ""):
    if file:
        subprocess.run(["termux-share", file], stdin=subprocess.DEVNULL)
        return f"Shared file: {file}"
    else:
        result = subprocess.run(["termux-share", "-a", "send"], input=text, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        return f"Shared text: {text}"
