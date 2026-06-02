import subprocess

def vibrate(duration_ms: int = 500):
    subprocess.run(["termux-vibrate", "-d", str(duration_ms)], stdin=subprocess.DEVNULL)
    return f"Vibrated for {duration_ms}ms"

def get_battery_status():
    result = subprocess.run(["termux-battery-status"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def torch(status: str = "on"):
    subprocess.run(["termux-torch", status], stdin=subprocess.DEVNULL)
    return f"Torch turned {status}"

def set_brightness(brightness: int = 128):
    subprocess.run(["termux-brightness", str(brightness)], stdin=subprocess.DEVNULL)
    return f"Brightness set to {brightness}"

def get_sensor(sensor: str = "light"):
    result = subprocess.run(["termux-sensor", "-s", sensor, "-n", "1"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()
