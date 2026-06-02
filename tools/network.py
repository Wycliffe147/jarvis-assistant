import subprocess
import json
import requests
from jarvis.config import COLOR_GRAY, COLOR_RESET

def open_url(url: str):
    subprocess.run(["termux-open-url", url], stdin=subprocess.DEVNULL)
    return f"Opened URL: {url}"

def get_wifi_info():
    result = subprocess.run(["termux-wifi-connectioninfo"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def scan_wifi():
    result = subprocess.run(["termux-wifi-scaninfo"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def _fetch_coordinates(provider: str, timeout: int) -> dict | None:
    try:
        result = subprocess.run(
            ["termux-location", "-p", provider, "-r", "once"],
            capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL
        )
        data = json.loads(result.stdout.strip())
        if data.get("latitude") is not None:
            return data
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        pass
    return None

def _reverse_geocode(lat: float, lon: float) -> str | None:
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json"},
            headers={"User-Agent": "TermuxAIAssistant/1.0"},
            timeout=10
        )
        if r.status_code == 200:
            return r.json().get("display_name")
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        pass
    return None

def get_location():
    lat, lon, acc, provider_used = None, None, "?", None
    print(f"{COLOR_GRAY}[Trying GPS...]{COLOR_RESET}", end="\r")
    data = _fetch_coordinates("gps", timeout=30)

    if data is None:
        print(f"{COLOR_GRAY}[GPS unavailable, trying network...]{COLOR_RESET}", end="\r")
        data = _fetch_coordinates("network", timeout=15)
        provider_used = "network"
    else:
        provider_used = "gps"

    if data is None:
        return "Could not determine location via GPS or network."

    lat = data["latitude"]
    lon = data["longitude"]
    acc = data.get("accuracy", "?")

    address = _reverse_geocode(lat, lon)
    provider_label = "GPS" if provider_used == "gps" else "Network (indoor estimate)"

    if address:
        return f"{address} [{provider_label}, accuracy: {acc}m]"
    else:
        maps_url = f"https://maps.google.com/?q={lat},{lon}"
        return f"{lat}, {lon} [{provider_label}, accuracy: {acc}m] — Maps: {maps_url}"

def get_device_info():
    result = subprocess.run(["termux-telephony-deviceinfo"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def get_cell_info():
    result = subprocess.run(["termux-telephony-cellinfo"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()
