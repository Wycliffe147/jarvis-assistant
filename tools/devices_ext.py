import socket
import subprocess
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from jarvis.config import COLOR_GRAY, COLOR_RED, COLOR_RESET

def open_bluetooth_settings() -> str:
    """Opens the system Bluetooth settings screen for pairing or connecting audio devices."""
    subprocess.run(["am", "start", "-a", "android.settings.BLUETOOTH_SETTINGS"], stdin=subprocess.DEVNULL)
    return "Opened Bluetooth Settings."

# --- Wireless ADB Controls ---

import os
import json

STATE_FILE = os.path.expanduser("~/.jarvis_adb_state.json")

def _get_default_adb_target() -> str:
    # First, dynamically check if any device is already connected via adb devices
    try:
        res = subprocess.run(["adb", "devices"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        connected_devices = []
        for line in res.stdout.splitlines():
            if "\tdevice" in line:
                connected_devices.append(line.split()[0])
        # If there is an active connection, prefer it
        if connected_devices:
            return connected_devices[0]
    except Exception:
        pass

    # If nothing is active, fall back to the last cached connection target
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return data.get("default_target", "127.0.0.1:5555")
        except:
            pass
    return "127.0.0.1:5555"

def _set_default_adb_target(target: str):
    try:
        data = {}
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data["default_target"] = target
        with open(STATE_FILE, "w") as f:
            json.dump(data, f)
    except:
        pass

def _try_remember_serial_for_target(target: str):
    """After a successful adb connect, fetches the device's serial number and
    stores the serial -> target mapping, so future mDNS scans can recognize
    this same physical device even after its IP/port changes."""
    try:
        res = subprocess.run(["adb", "-s", target, "get-serialno"], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=10)
        serial = res.stdout.strip()
        if serial and "unknown" not in serial.lower() and "error" not in serial.lower():
            _remember_device_serial(serial, target)
    except Exception:
        pass

def adb_list_devices() -> str:
    """Lists all currently connected ADB devices. Use this to check what external phones/devices are linked before sending commands."""
    # Start the adb server if not already running (inherits already-connected devices)
    subprocess.run(["adb", "start-server"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    res = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    lines = res.stdout.strip().splitlines()
    # Match lines that have 'device' as a word (not 'offline', not 'unauthorized', not the header)
    import re as _re
    devices = [l for l in lines if _re.search(r'\bdevice\b', l) and not l.startswith("List")]
    if not devices:
        return "No ADB devices currently connected. Use adb_connect(target_ip) to establish a link first."
    result = ["Connected ADB devices:"]
    for d in devices:
        parts = d.split()
        identifier = parts[0]
        model = next((p.replace("model:", "") for p in parts if p.startswith("model:")), "Unknown Model")
        result.append(f"  - {identifier}  [{model}]")
    return "\n".join(result)


def adb_connect(target_ip: str, port: int = 5555) -> str:
    """Connects to a nearby phone/device using wireless debugging (ADB) and sets it as default target."""
    # Ensure port is valid
    addr = f"{target_ip}:{port}"
    result = subprocess.run(["adb", "connect", addr], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    out = result.stdout.strip()
    if "connected to" in out.lower():
        _set_default_adb_target(addr)
        _try_remember_serial_for_target(addr)
    return out

def adb_self_connect() -> bool:
    """Silently attempts to connect this phone to itself via loopback ADB (127.0.0.1:5555).
    Called on Jarvis startup. Returns True if connected, False if wireless debugging is off.
    Does not raise — safe to call unconditionally."""
    try:
        subprocess.run(["adb", "start-server"], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=5)
        res = subprocess.run(["adb", "connect", "127.0.0.1:5555"], capture_output=True, text=True,
                             stdin=subprocess.DEVNULL, timeout=5)
        out = res.stdout.strip().lower()
        if "connected to" in out or "already connected" in out:
            _set_default_adb_target("127.0.0.1:5555")
            return True
        return False
    except Exception:
        return False


def adb_disconnect(target_ip: str = "") -> str:
    """Disconnects the ADB link from target device(s)."""
    cmd = ["adb", "disconnect"]
    if target_ip:
        cmd.append(target_ip)
    result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def adb_pair_device(target_ip: str, pairing_port: int, pairing_code: str) -> str:
    """Pairs a new device over Wireless ADB using the pairing port and 6-digit
    code shown on the target device's Wireless Debugging screen.
    After successful pairing, automatically connects using the connection port
    and saves as the default ADB target.

    Args:
        target_ip:    IP shown on the Wireless Debugging screen (e.g. '10.51.91.29')
        pairing_port: Port shown next to the pairing code (e.g. 36931)
        pairing_code: The 6-digit Wi-Fi pairing code shown on screen
    """
    pairing_code = str(pairing_code).strip()
    if not pairing_code.isdigit() or len(pairing_code) != 6:
        return f"Invalid pairing code '{pairing_code}'. It must be exactly 6 digits as shown on the target device."

    pair_addr = f"{target_ip}:{pairing_port}"
    print(f"[ADB Pair] Running: adb pair {pair_addr} ...")

    try:
        res = subprocess.run(
            ["adb", "pair", pair_addr, pairing_code],
            capture_output=True, text=True,
            stdin=subprocess.DEVNULL,
            timeout=15
        )
        out = (res.stdout + res.stderr).strip()
    except subprocess.TimeoutExpired:
        return f"Pairing timed out connecting to {pair_addr}. Try again."
    except Exception as e:
        return f"Pairing failed with error: {e}"

    if "successfully" not in out.lower() and "paired" not in out.lower():
        return f"Pairing failed: {out}\nDouble-check the code and try again before it expires."

    # Pairing succeeded — try connecting on the standard connect port (usually
    # different from the pairing port) so we can capture the device serial for
    # future mDNS-based reconnects.
    try:
        connect_res = subprocess.run(["adb", "connect", target_ip], capture_output=True, text=True,
                                      stdin=subprocess.DEVNULL, timeout=10)
        if "connected to" in connect_res.stdout.lower():
            _try_remember_serial_for_target(target_ip)
    except Exception:
        pass

    return f"✅ Paired with {target_ip} successfully!"


def _is_serial(identifier: str) -> bool:
    """Returns True if identifier is a device serial (e.g. emulator-5554) rather than an IP:port."""
    import re as _re
    # IP addresses contain dots and optionally a colon+port: e.g. 192.168.1.5:5555
    return not bool(_re.match(r'^[\d.]+:\d+$', identifier)) and ':' not in identifier

def _resolve_target(target_ip: str) -> str:
    """Resolves a target identifier to the correct adb -s argument (no port appended for serials)."""
    if _is_serial(target_ip):
        return target_ip  # Serial ID like emulator-5554, use as-is
    return target_ip if ':' in target_ip else f'{target_ip}:5555'


# --- mDNS-based discovery for previously-paired devices ---
#
# Android's wireless debugging advertises itself over mDNS using service types:
#   _adb._tcp             - legacy TCP mode (adb tcpip <port>)
#   _adb-tls-pairing._tcp - pairing server active (device showing a 6-digit code)
#   _adb-tls-connect._tcp - TLS connect server active (already-paired device, ready
#                           to accept `adb connect`)
# Instance names are typically "adb-<serial>-<random>", so the device's serial
# number is embedded in the name and survives IP/port changes — making it the
# right key to recognize "this is the same phone I paired before", since both
# the IP and port can change between sessions.

def _remember_device_serial(serial: str, target: str):
    """Associates a device serial with the IP:port it was last seen at, so future
    mDNS scans can recognize the same physical device even after its IP or port
    changes."""
    try:
        data = {}
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
        known = data.get("known_serials", {})
        known[serial] = target
        data["known_serials"] = known
        data["default_target"] = target
        with open(STATE_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

def _get_known_serials() -> dict:
    """Returns the serial -> last-known-target map of previously paired devices."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f).get("known_serials", {})
        except Exception:
            pass
    return {}

def _extract_serial_from_instance(instance: str, service_type: str) -> str | None:
    """Extracts the device serial from an mDNS instance name.

    Per AOSP's adb_wifi.md, the instance name pattern differs by service type:
      - _adb._tcp:              "adb-<serial>"            (no random suffix)
      - _adb-tls-connect._tcp:  "adb-<serial>-<random>"   (random suffix appended)
      - _adb-tls-pairing._tcp:  varies; may have no usable serial at all
        (the pairing instance name can be e.g. "studio-g@<random>" with no serial)

    Serials can themselves contain hyphens, so we can't just split on the first
    hyphen — instead we strip the "adb-" prefix and, for service types known to
    append a random suffix, strip everything after the LAST hyphen instead.
    """
    if not instance.startswith("adb-"):
        return None
    remainder = instance[len("adb-"):]
    if "tls-connect" in service_type or "tls-pairing" in service_type:
        # Random suffix is appended after a final hyphen, e.g. "<serial>-M6yfz4"
        if "-" in remainder:
            return remainder.rsplit("-", 1)[0]
        return remainder
    # _adb._tcp (legacy TCP mode): no suffix, the remainder IS the serial
    return remainder


def _parse_mdns_services() -> list:
    """Runs `adb mdns services` and parses each discovered service into a dict:
    {"instance": str, "serial": str|None, "service_type": str, "target": "ip:port"}.
    Returns an empty list if mDNS discovery isn't supported/enabled or nothing
    is currently advertising (this is common — mDNS visibility is inconsistent
    across devices and adb versions, so callers should treat an empty result as
    "try the next fallback", not as a hard failure)."""
    import re as _re
    try:
        res = subprocess.run(["adb", "mdns", "services"], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=10)
    except Exception:
        return []

    services = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("list of discovered"):
            continue
        parts = line.split()
        if len(parts) != 3:
            continue
        instance, service_type, target = parts
        # Real adb output includes a trailing dot on the service type, e.g.
        # "_adb-tls-connect._tcp." — normalize it away so substring/equality
        # checks elsewhere don't need to special-case it.
        service_type = service_type.rstrip(".")
        if not _re.match(r'^[\d.]+:\d+$', target):
            continue
        serial = _extract_serial_from_instance(instance, service_type)
        services.append({
            "instance": instance,
            "serial": serial,
            "service_type": service_type,
            "target": target,
        })
    return services

def _mdns_reconnect(prefer_serial: str = "") -> str:
    """Attempts to reconnect to a previously-paired device by scanning mDNS for
    an _adb-tls-connect._tcp announcement, matching on device serial when known.
    Works regardless of which network/hotspot the device is on, unlike the
    nmap-based hotspot scan. Returns a human-readable result string; check for
    the "✅" prefix to confirm success.
    """
    services = _parse_mdns_services()
    if not services:
        return "No devices currently advertising ADB over mDNS. (mDNS discovery can be inconsistent — try `adb mdns check` to verify it's enabled, or fall back to a hotspot scan.)"

    # Both _adb-tls-connect._tcp (paired, TLS-secured) and the legacy _adb._tcp
    # (TCP mode, no pairing required) are directly connectable. Note: service_type
    # is already normalized (no trailing dot) by _parse_mdns_services above.
    connect_candidates = [s for s in services if "tls-connect" in s["service_type"] or s["service_type"] == "_adb._tcp"]
    if not connect_candidates:
        pairing_candidates = [s for s in services if "tls-pairing" in s["service_type"]]
        if pairing_candidates:
            return ("Found a device in pairing mode (showing a pairing code), but no "
                    "already-paired device ready to connect. Use adb_pair_device with the "
                    "IP/port/code shown on its screen first.")
        return "mDNS found services, but none were ADB-connectable devices."

    known_serials = _get_known_serials()

    # Prefer an exact serial match (explicitly requested, or any previously-known device)
    chosen = None
    if prefer_serial:
        chosen = next((s for s in connect_candidates if s["serial"] == prefer_serial), None)
    if not chosen:
        for s in connect_candidates:
            if s["serial"] and s["serial"] in known_serials:
                chosen = s
                break
    # No known match — if there's exactly one candidate, use it; otherwise ambiguous.
    if not chosen:
        if len(connect_candidates) == 1:
            chosen = connect_candidates[0]
        else:
            names = ", ".join(f"{s['serial'] or s['instance']} ({s['target']})" for s in connect_candidates)
            return f"Multiple unrecognized devices found via mDNS: {names}. Specify which one to connect to."

    target = chosen["target"]
    result = subprocess.run(["adb", "connect", target], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    out = result.stdout.strip()
    if "connected to" in out.lower() or "already connected" in out.lower():
        _set_default_adb_target(target)
        if chosen["serial"]:
            _remember_device_serial(chosen["serial"], target)
        return f"✅ Reconnected via mDNS to {target} (serial: {chosen['serial'] or 'unknown'})."
    return f"mDNS found {target} but connection failed: {out}"


def _ensure_adb_connected(target: str) -> bool:
    """Checks if the device is already in adb devices. For IP targets, tries to connect if missing.
    If direct IP connection fails, tries mDNS discovery (works on any shared network, not just our
    own hotspot), then finally falls back to the hotspot client scan."""
    import re as _re
    import os as _os
    debug = _os.environ.get("JARVIS_DEBUG_RAW") == "1"
    subprocess.run(["adb", "start-server"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    res = subprocess.run(["adb", "devices"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if debug:
        import sys as _sys
        print(f"[ADB_CHECK] target={target!r} returncode={res.returncode} stdout={res.stdout!r} stderr={res.stderr!r}", file=_sys.stderr, flush=True)
    for line in res.stdout.splitlines():
        if target in line and _re.search(r'\bdevice\b', line):
            if debug:
                print(f"[ADB_CHECK] matched on first check: {line!r}", file=_sys.stderr, flush=True)
            return True

    # For serial IDs (like emulator-5554), don't try to 'adb connect'
    if _is_serial(target):
        if debug:
            print(f"[ADB_CHECK] target classified as serial, no match found, returning False without fallback", file=_sys.stderr, flush=True)
        return False

    # For IP targets: try connecting directly
    subprocess.run(["adb", "connect", target], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    res2 = subprocess.run(["adb", "devices"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if debug:
        print(f"[ADB_CHECK] after 'adb connect {target}': stdout={res2.stdout!r}", file=_sys.stderr, flush=True)
    for line in res2.stdout.splitlines():
        if target in line and _re.search(r'\bdevice\b', line):
            if debug:
                print(f"[ADB_CHECK] matched after connect retry: {line!r}", file=_sys.stderr, flush=True)
            return True

    # FALLBACK 1: mDNS discovery. Network-agnostic — works whether the device is
    # on our hotspot, a home Wi-Fi network, or anywhere else mDNS multicast reaches.
    try:
        print(f"{COLOR_GRAY}[ADB Connection Fallback] Connection to {target} failed. Trying mDNS discovery...{COLOR_RESET}")
        mdns_res = _mdns_reconnect()
        if mdns_res.startswith("✅"):
            new_target = _get_default_adb_target()
            new_resolved = _resolve_target(new_target)
            res3 = subprocess.run(["adb", "devices"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
            for line in res3.stdout.splitlines():
                if new_resolved in line and _re.search(r'\bdevice\b', line):
                    return True
    except Exception as e:
        print(f"{COLOR_RED}[ADB Connection Fallback] mDNS reconnect error: {e}{COLOR_RESET}")

    # FALLBACK 2: If mDNS didn't find anything (common — mDNS visibility is
    # inconsistent), the IP or port might have changed on our own hotspot. Run
    # hotspot autoconnect to scan and refresh the state.
    try:
        from jarvis.tools.hotspot import hotspot_adb_autoconnect
        print(f"{COLOR_GRAY}[ADB Connection Fallback] mDNS found nothing. Attempting hotspot client scan...{COLOR_RESET}")
        autoconnect_res = hotspot_adb_autoconnect()
        if "✅ ADB connected to:" in autoconnect_res:
            # Re-read default target after scan updates the state
            new_target = _get_default_adb_target()
            new_resolved = _resolve_target(new_target)
            res4 = subprocess.run(["adb", "devices"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
            for line in res4.stdout.splitlines():
                if new_resolved in line and _re.search(r'\bdevice\b', line):
                    # Successfully auto-healed and reconnected!
                    return True
    except Exception as e:
        print(f"{COLOR_RED}[ADB Connection Fallback] Hotspot reconnect error: {e}{COLOR_RESET}")

    return False


def adb_mdns_reconnect(prefer_serial: str = "") -> str:
    """Tool entrypoint: scans mDNS for a previously-paired ADB device and reconnects
    to it directly, regardless of which network it's currently on. Use this when the
    user wants to reconnect to a known phone but its IP/port may have changed and it's
    not on this device's own hotspot (e.g. shared home Wi-Fi instead).

    Args:
        prefer_serial: optional device serial to target if multiple devices are
            discoverable at once. Leave blank to auto-pick a previously-known device.
    """
    return _mdns_reconnect(prefer_serial)



def adb_command(target_ip: str = "", action: str = "tap", params_json: str = "{}") -> str:
    """Executes a remote control command on an ADB-connected phone.
    
    Actions:
      - tap: params {"x": int, "y": int}
      - swipe: params {"x1": int, "y1": int, "x2": int, "y2": int, "duration_ms": int}
      - text: params {"text": str}
      - keyevent: params {"code": int} (e.g. 26=Power, 3=Home, 4=Back)
      - launch: params {"package": str}
      - shell: params {"cmd": str} (run arbitrary shell command)
    """
    import json
    try:
        if isinstance(params_json, dict):
            params = params_json
        elif isinstance(params_json, str):
            stripped = params_json.strip()
            if stripped.startswith("{"):
                params = json.loads(stripped)
            elif action == "text":
                params = {"text": params_json}
            elif action == "keyevent":
                params = {"code": int(stripped)} if stripped.isdigit() else json.loads(stripped)
            else:
                params = json.loads(stripped)
        elif isinstance(params_json, int):
            params = {"code": params_json} if action == "keyevent" else {"x": params_json}
        elif isinstance(params_json, list):
            if action in ("tap",) and len(params_json) >= 2:
                params = {"x": params_json[0], "y": params_json[1]}
            elif action == "swipe" and len(params_json) >= 4:
                params = {"x1": params_json[0], "y1": params_json[1],
                          "x2": params_json[2], "y2": params_json[3]}
            else:
                params = {}
        else:
            params = {}
        if not isinstance(params, dict):
            return f"Invalid parameters JSON: expected a dict, got {type(params).__name__}"
    except Exception as e:
        return f"Invalid parameters JSON: {e}"

    # Default target resolving
    if not target_ip or target_ip.lower() == "default":
        target_ip = _get_default_adb_target()

    # Resolve to correct adb -s format (don't append :5555 to serial IDs)
    target = _resolve_target(target_ip)
    
    # Auto-reconnect if link is disconnected
    if not _ensure_adb_connected(target):
        return f"Could not establish ADB link to {target}. Please ensure Wireless Debugging is active on that device."

    # Re-resolve in case the fallback autoconnect updated the default target IP/port!
    if not target_ip or target_ip.lower() == "default":
        target_ip = _get_default_adb_target()
        target = _resolve_target(target_ip)

    adb_base = ["adb", "-s", target, "shell"]

    if action == "tap":
        x = params.get("x", 0)
        y = params.get("y", 0)
        cmd = adb_base + ["input", "tap", str(x), str(y)]
    elif action == "swipe":
        x1 = params.get("x1", 0)
        y1 = params.get("y1", 0)
        x2 = params.get("x2", 0)
        y2 = params.get("y2", 0)
        dur = params.get("duration_ms", 300)
        cmd = adb_base + ["input", "swipe", str(x1), str(y1), str(x2), str(y2), str(dur)]
    elif action == "text":
        txt = params.get("text", "")
        # Escape spaces for adb input
        txt_escaped = txt.replace(" ", "%s")
        cmd = adb_base + ["input", "text", txt_escaped]
    elif action == "keyevent":
        code = params.get("code", 3)  # Default Home key
        cmd = adb_base + ["input", "keyevent", str(code)]
    elif action == "launch":
        pkg = params.get("package", "")
        cmd = adb_base + ["monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"]
    elif action == "shell":
        shell_cmd = params.get("cmd", "")
        cmd = adb_base + shell_cmd.split()
    else:
        return f"Unknown ADB action: {action}"

    res = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if res.returncode == 0:
        return f"Successfully executed ADB {action} on {target_ip}."
    return f"ADB Command Failed: {res.stderr.strip() or res.stdout.strip()}"

def adb_screenshot(target_ip: str = "", filename: str = "adb_screencap.png") -> str:
    """Takes a screenshot of the ADB target device and pulls it to the local Downloads folder."""
    if not target_ip or target_ip.lower() == "default":
        target_ip = _get_default_adb_target()
        
    target = _resolve_target(target_ip)
    if not _ensure_adb_connected(target):
        return f"Could not establish ADB link to {target}."
        
    # Re-resolve default target in case autoconnect triggered and changed the port/IP
    if not target_ip or target_ip.lower() == "default":
        target_ip = _get_default_adb_target()
        target = _resolve_target(target_ip)

        
    remote_path = f"/sdcard/Download/{filename}"
    local_dir = "/sdcard/Download"
    if not os.path.exists(local_dir):
        local_dir = os.path.expanduser("~/Downloads")
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, filename)
    
    # Snap screencap on target
    subprocess.run(["adb", "-s", target, "shell", "screencap", "-p", remote_path], stdin=subprocess.DEVNULL)
    # Pull it over to the local machine
    res = subprocess.run(["adb", "-s", target, "pull", remote_path, local_path], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    # Delete temporary file on remote
    subprocess.run(["adb", "-s", target, "shell", "rm", remote_path], stdin=subprocess.DEVNULL)
    
    if res.returncode == 0:
        return f"Screenshot successfully saved to {local_path}"
    return f"Failed to pull screenshot: {res.stderr.strip()}"


# --- Live Screen Mirroring (scrcpy over Termux:X11) ---
#
# Opens a real-time, interactive mirror window via scrcpy, rendered through
# Termux:X11. Requires the Termux:X11 app to already be running (it provides
# the X11 display surface — scrcpy has nowhere to draw its window otherwise).
# Touch input needs no special flags: tapping/swiping directly on the phone's
# screen inside the Termux:X11 window is translated by scrcpy into real touch
# events on the target device by default — this is standard scrcpy behavior,
# not something we need to configure.

MIRROR_PID_FILE = os.path.expanduser("~/.jarvis_scrcpy.pid")

def _scrcpy_available() -> bool:
    res = subprocess.run(["which", "scrcpy"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return bool(res.stdout.strip())

def adb_mirror_device(target_ip: str = "", orientation: str = "portrait") -> str:
    """Opens a live, interactive mirror of the ADB-connected phone's screen in a
    Termux:X11 GUI window using scrcpy. Tapping/swiping on the phone's screen
    inside the mirror window controls the target device directly, like using
    it normally — no separate input mode needed, this is scrcpy's default.

    Requires the Termux:X11 app to be running first (it provides the display
    the scrcpy window renders into).

    Args:
        target_ip: ADB target to mirror. Defaults to the current default target.
        orientation: "portrait" (default), "landscape", "upside_down", or
            "landscape_reverse". Controls --capture-orientation (locked with the
            "@" prefix) so the window doesn't flip around as the phone's sensor
            rotates. Note: scrcpy 3.0+ replaced the old --lock-video-orientation
            flag (which was broken on Android 14+) with --capture-orientation,
            expressed in degrees clockwise rather than the old 0-3 enum.
    """
    if not _scrcpy_available():
        return ("scrcpy isn't installed. Run `pkg install scrcpy` in Termux first.")

    if not target_ip or target_ip.lower() == "default":
        target_ip = _get_default_adb_target()

    target = _resolve_target(target_ip)
    if not _ensure_adb_connected(target):
        return f"Could not establish ADB link to {target}. Connect or reconnect the device first."

    # Re-resolve in case auto-reconnect (mDNS/hotspot) changed the target
    if not target_ip or target_ip.lower() == "default":
        target_ip = _get_default_adb_target()
        target = _resolve_target(target_ip)

    # Degrees clockwise, per current --capture-orientation syntax (scrcpy 3.0+).
    orientation_map = {
        "portrait": "0",
        "landscape": "90",
        "upside_down": "180",
        "landscape_reverse": "270",
    }
    degrees = orientation_map.get(orientation.lower().replace(" ", "_"), "0")

    # If a mirror session is already running, stop it first rather than
    # stacking multiple scrcpy windows.
    existing = _mirror_status()
    if "Mirroring is active" in existing:
        adb_stop_mirror()

    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")  # Termux:X11 default display

    cmd = [
        "scrcpy",
        "-s", target,
        f"--capture-orientation=@{degrees}",
        "--window-title=Jarvis Mirror",
        "--stay-awake",
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except FileNotFoundError:
        return "scrcpy isn't installed. Run `pkg install scrcpy` in Termux first."
    except Exception as e:
        return f"Failed to launch scrcpy: {e}"

    # Give it a moment to fail fast (e.g. no X11 display, device not authorized)
    # rather than reporting success on a process that's about to die.
    import time as _time
    _time.sleep(1.5)
    if proc.poll() is not None:
        stderr_out = ""
        try:
            stderr_out = proc.stderr.read().decode("utf-8", errors="ignore").strip()
        except Exception:
            pass
        hint = ""
        if "DISPLAY" in stderr_out or "cannot open display" in stderr_out.lower() or not stderr_out:
            hint = " Make sure the Termux:X11 app is open and running first — scrcpy needs it for its window."
        return f"scrcpy exited immediately (code {proc.returncode}).{hint}\n{stderr_out[:300]}"

    try:
        with open(MIRROR_PID_FILE, "w") as f:
            json.dump({"pid": proc.pid, "target": target}, f)
    except Exception:
        pass

    return f"✅ Mirroring {target} now in a {orientation} window. Tap and swipe on the mirror window like a normal phone screen. Say 'stop mirroring' to close it."


def _mirror_status() -> str:
    if not os.path.exists(MIRROR_PID_FILE):
        return "No mirror session is currently tracked."
    try:
        with open(MIRROR_PID_FILE, "r") as f:
            data = json.load(f)
        pid = data.get("pid")
        target = data.get("target", "unknown")
        if pid and _pid_alive(pid):
            return f"Mirroring is active for {target} (pid {pid})."
        return f"No active mirror (last session for {target} has ended)."
    except Exception:
        return "No mirror session is currently tracked."


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False
    except Exception:
        return False


def adb_stop_mirror() -> str:
    """Stops the currently running scrcpy mirror session, if any."""
    if not os.path.exists(MIRROR_PID_FILE):
        return "No mirror session is currently running."
    try:
        with open(MIRROR_PID_FILE, "r") as f:
            data = json.load(f)
        pid = data.get("pid")
        if pid and _pid_alive(pid):
            import signal
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
        os.remove(MIRROR_PID_FILE)
        return "Mirror session stopped."
    except Exception as e:
        return f"Could not cleanly stop mirror session: {e}"



# --- DLNA / UPnP Media Casting ---

def _discover_dlna_urls(timeout=2.0) -> list:
    """Discovers DLNA AVTransport rendering devices on local network."""
    devices = []
    # SSDP Discovery payload
    ssdp_request = (
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST: 239.255.255.250:1900\r\n"
        "MAN: \"ssdp:discover\"\r\n"
        "MX: 2\r\n"
        "ST: urn:schemas-upnp-org:service:AVTransport:1\r\n"
        "\r\n"
    )
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    
    # Broadcast to SSDP multicast address
    try:
        sock.sendto(ssdp_request.encode('utf-8'), ('239.255.255.250', 1900))
    except Exception:
        return []

    import time
    start = time.time()
    seen_locations = set()
    
    while time.time() - start < timeout:
        try:
            data, addr = sock.recvfrom(2048)
            response = data.decode('utf-8', errors='ignore')
            
            # Find Location header
            match = re.search(r'(?i)LOCATION:\s*(http://[^\r\n]+)', response)
            if match:
                loc = match.group(1).strip()
                if loc not in seen_locations:
                    seen_locations.add(loc)
                    # Parse friendly name and AVControl URL from XML
                    dev_info = _parse_upnp_description(loc)
                    if dev_info:
                        devices.append(dev_info)
        except socket.timeout:
            break
        except Exception:
            continue
            
    sock.close()
    return devices

def _parse_upnp_description(xml_url: str) -> dict | None:
    """Parses UPnP XML configuration to extract friendly name and control URLs."""
    try:
        req = urllib.request.Request(xml_url, headers={'User-Agent': 'JarvisDLNACaster/1.0'})
        with urllib.request.urlopen(req, timeout=3) as r:
            xml_data = r.read()
        
        # Parse XML namespaces safely
        root = ET.fromstring(xml_data)
        ns = {'upnp': 'urn:schemas-upnp-org:device-1-0'}
        
        # Get friendly name
        friendly_name_node = root.find('.//upnp:friendlyName', ns)
        friendly_name = friendly_name_node.text if friendly_name_node is not None else "Smart Device"
        
        # Extract base url for relative service control paths
        url_parsed = urllib.parse.urlparse(xml_url)
        base_url = f"{url_parsed.scheme}://{url_parsed.netloc}"
        
        # Locate AVTransport service
        control_url = None
        for service in root.findall('.//upnp:service', ns):
            service_type = service.find('upnp:serviceType', ns)
            if service_type is not None and "AVTransport" in service_type.text:
                control_node = service.find('upnp:controlURL', ns)
                if control_node is not None:
                    path = control_node.text
                    control_url = path if path.startswith('http') else base_url + path
                    break
                    
        if control_url:
            return {
                "name": friendly_name,
                "ip": url_parsed.hostname,
                "xml_url": xml_url,
                "control_url": control_url
            }
    except Exception:
        pass
    return None

def dlna_scan() -> str:
    """Scans the local network for DLNA-compatible Smart TVs, Nest Speakers, and screens."""
    devices = _discover_dlna_urls()
    if not devices:
        return "No DLNA or Smart TV casting devices found on the local network."
    
    lines = ["Found Casting Devices:"]
    for d in devices:
        lines.append(f"- {d['name']} (IP: {d['ip']}) - URL: {d['control_url']}")
    return "\n".join(lines)

def dlna_cast(target_ip: str, media_url: str, media_title: str = "Jarvis Cast") -> str:
    """Casts a video/music URL directly to a smart TV or network speaker using DLNA."""
    devices = _discover_dlna_urls(timeout=1.5)
    target_dev = None
    for d in devices:
        if d['ip'] == target_ip:
            target_dev = d
            break
            
    if not target_dev:
        return f"Casting device at IP {target_ip} is not currently discoverable."

    # DLNA SOAP headers and body payloads for Load URI and Play
    headers = {
        'Content-Type': 'text/xml; charset="utf-8"',
        'SOAPACTION': '"urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI"'
    }
    
    soap_body = (
        '<?xml version="1.0" encoding="utf-8"?>\r\n'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">\r\n'
        '  <s:Body>\r\n'
        '    <u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">\r\n'
        '      <InstanceID>0</InstanceID>\r\n'
        f'      <CurrentURI>{media_url}</CurrentURI>\r\n'
        f'      <CurrentURIMetaData>&lt;DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"&gt;&lt;item id="0" parentID="0" restricted="1"&gt;&lt;dc:title&gt;{media_title}&lt;/dc:title&gt;&lt;upnp:class&gt;object.item.videoItem&lt;/upnp:class&gt;&lt;/item&gt;&lt;/DIDL-Lite&gt;</CurrentURIMetaData>\r\n'
        '    </u:SetAVTransportURI>\r\n'
        '  </s:Body>\r\n'
        '</s:Envelope>\r\n'
    )
    
    try:
        # 1. Load Media URI
        req = urllib.request.Request(target_dev['control_url'], data=soap_body.encode('utf-8'), headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            response.read()
            
        # 2. Trigger Play Action
        headers['SOAPACTION'] = '"urn:schemas-upnp-org:service:AVTransport:1#Play"'
        play_body = (
            '<?xml version="1.0" encoding="utf-8"?>\r\n'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">\r\n'
            '  <s:Body>\r\n'
            '    <u:Play xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">\r\n'
            '      <InstanceID>0</InstanceID>\r\n'
            '      <Speed>1</Speed>\r\n'
            '    </u:Play>\r\n'
            '  </s:Body>\r\n'
            '</s:Envelope>\r\n'
        )
        req_play = urllib.request.Request(target_dev['control_url'], data=play_body.encode('utf-8'), headers=headers)
        with urllib.request.urlopen(req_play, timeout=5) as response_play:
            response_play.read()
            
        return f"Successfully casted media to {target_dev['name']} ({target_ip})."
    except Exception as e:
        return f"Failed to cast to DLNA device: {e}"

def dlna_stop(target_ip: str) -> str:
    """Stops playback on a casting TV or smart speaker."""
    devices = _discover_dlna_urls(timeout=1.5)
    target_dev = None
    for d in devices:
        if d['ip'] == target_ip:
            target_dev = d
            break
            
    if not target_dev:
        return f"Casting device at IP {target_ip} is not currently discoverable."

    headers = {
        'Content-Type': 'text/xml; charset="utf-8"',
        'SOAPACTION': '"urn:schemas-upnp-org:service:AVTransport:1#Stop"'
    }
    soap_body = (
        '<?xml version="1.0" encoding="utf-8"?>\r\n'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">\r\n'
        '  <s:Body>\r\n'
        '    <u:Stop xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">\r\n'
        '      <InstanceID>0</InstanceID>\r\n'
        '    </u:Stop>\r\n'
        '  </s:Body>\r\n'
        '</s:Envelope>\r\n'
    )
    try:
        req = urllib.request.Request(target_dev['control_url'], data=soap_body.encode('utf-8'), headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            response.read()
        return f"Stopped playback on {target_dev['name']} ({target_ip})."
    except Exception as e:
        return f"Failed to stop DLNA playback: {e}"
