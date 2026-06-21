import socket
import subprocess
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from jarvis.config import COLOR_GRAY, COLOR_RESET

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
        with open(STATE_FILE, "w") as f:
            json.dump({"default_target": target}, f)
    except:
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
    return out

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

def _ensure_adb_connected(target: str) -> bool:
    """Checks if the device is already in adb devices. For IP targets, tries to connect if missing.
    If direct IP connection fails, attempts to run the auto-hotspot reconnect logic to discover a new port."""
    import re as _re
    subprocess.run(["adb", "start-server"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    res = subprocess.run(["adb", "devices"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    for line in res.stdout.splitlines():
        if target in line and _re.search(r'\bdevice\b', line):
            return True

    # For serial IDs (like emulator-5554), don't try to 'adb connect'
    if _is_serial(target):
        return False

    # For IP targets: try connecting directly
    subprocess.run(["adb", "connect", target], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    res2 = subprocess.run(["adb", "devices"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    for line in res2.stdout.splitlines():
        if target in line and _re.search(r'\bdevice\b', line):
            return True

    # FALLBACK: If direct connection fails, the IP or port might have changed.
    # Run hotspot autoconnect to scan and refresh the state.
    try:
        from jarvis.tools.hotspot import hotspot_adb_autoconnect
        print(f"[ADB Connection Fallback] Connection to {target} failed. Attempting hotspot client scan...")
        autoconnect_res = hotspot_adb_autoconnect()
        if "✅ ADB connected to:" in autoconnect_res:
            # Re-read default target after scan updates the state
            new_target = _get_default_adb_target()
            new_resolved = _resolve_target(new_target)
            res3 = subprocess.run(["adb", "devices"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
            for line in res3.stdout.splitlines():
                if new_resolved in line and _re.search(r'\bdevice\b', line):
                    # Successfully auto-healed and reconnected!
                    return True
    except Exception as e:
        print(f"[ADB Connection Fallback] Reconnect error: {e}")

    return False



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
        params = json.loads(params_json)
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
        cmd = adb_base + ["input", "text", f"'{txt_escaped}'"]
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
