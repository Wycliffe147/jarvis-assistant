import subprocess
import json
from jarvis.config import COLOR_GRAY, COLOR_RESET

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
    """Reads a system sensor (light, accelerometer, etc). Defaults to 'light'."""
    # Map common names to actual sensor strings found on this device
    sensor_map = {
        "light": "STK31610 Light",
        "accel": "LIS2DWE12TR Accelerometer",
        "mag": "MXG4300S Magnetometer"
    }
    target = sensor_map.get(sensor.lower(), sensor)

    try:
        result = subprocess.run(["termux-sensor", "-n", "1", "-s", target], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            vals = data.get(target, {}).get("values", [])
            return vals[0] if len(vals) == 1 else vals
        return f"Error: {result.stderr}"
    except Exception as e:
        return f"Sensor Error: {e}"

def open_location_settings():
    """Opens the Android Location Settings page for the user to toggle GPS."""
    subprocess.run(["am", "start", "-a", "android.settings.LOCATION_SOURCE_SETTINGS"], stdin=subprocess.DEVNULL)
    return "Opened Location Settings. Please enable GPS manually."
