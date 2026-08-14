import subprocess
import re
import socket
import os

# Hotspot DHCP ranges Android uses by default
HOTSPOT_SUBNETS = [
    "192.168.42", "192.168.43", "192.168.44", "192.168.45",
    "192.168.46", "192.168.47", "192.168.48", "192.168.49",
    "10.51.91"
]


def _run_adb_shell(cmd: str, serial: str = "emulator-5554") -> str:
    """Runs a shell command on the local device via ADB loopback."""
    res = subprocess.run(
        ["adb", "-s", serial, "shell", cmd],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10
    )
    return res.stdout.strip()

def hotspot_enable() -> str:
    """Enables the Wi-Fi hotspot (Personal Hotspot / Tethering) on this device via ADB."""
    # Try direct tethering toggle via ADB shell (works on most Samsung devices)
    out = _run_adb_shell("svc wifi enable; cmd tethering start-tethering -t 1")
    # Samsung-specific: settings put global tether_dun_required 0
    _run_adb_shell("settings put global tether_dun_required 0")
    # Enable wifi hotspot - works on Android 12+
    out2 = _run_adb_shell("cmd wifi start-softap")
    if "exception" in (out2 or "").lower():
        # Fallback: open the settings UI for manual toggle
        subprocess.run(
            ["am", "start", "-n", "com.android.settings/.TetherSettings"],
            stdin=subprocess.DEVNULL
        )
        return "Could not enable hotspot automatically. Opened Tethering Settings for manual toggle."
    return "Hotspot enabled. Waiting for clients to connect..."

def hotspot_disable() -> str:
    """Disables the Wi-Fi hotspot on this device."""
    out = _run_adb_shell("cmd wifi stop-softap")
    if "exception" in (out or "").lower():
        subprocess.run(
            ["am", "start", "-n", "com.android.settings/.TetherSettings"],
            stdin=subprocess.DEVNULL
        )
        return "Could not disable hotspot automatically. Opened Tethering Settings."
    return "Hotspot disabled."

def hotspot_open_settings() -> str:
    """Opens the Android Hotspot / Tethering settings screen."""
    subprocess.run(
        ["am", "start", "-n", "com.android.settings/.TetherSettings"],
        stdin=subprocess.DEVNULL
    )
    return "Opened Hotspot & Tethering Settings."

def _get_active_hotspot_subnets() -> list:
    """Parses dumpsys tethering to dynamically find the active hotspot subnets."""
    subnets = list(HOTSPOT_SUBNETS)
    try:
        out = _run_adb_shell("dumpsys tethering")
        # Extract active subnets from LinkAddresses or Routes, e.g. 10.69.30.0/24 or 10.69.30.66/24
        found = re.findall(r'(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}/\d+', out)
        for subnet in found:
            if subnet not in subnets:
                subnets.append(subnet)
    except Exception:
        pass
    return subnets

def hotspot_status() -> str:
    """Checks if the hotspot is currently active and returns connected client IPs."""
    out = _run_adb_shell("dumpsys tethering")
    # Check if swlan/softap interface is in tethered state
    is_active = bool(re.search(r'(swlan|softap|wlan)\d.*TetheredState', out))
    upstream = re.search(r'Current upstream interface.*?:\s*\[([^\]]*)\]', out)
    upstream_iface = upstream.group(1) if upstream else "unknown"

    if not is_active:
        return "Hotspot is currently INACTIVE."

    status = [f"Hotspot is ACTIVE (Upstream: {upstream_iface})"]

    # Try to read ARP table for connected clients
    arp = _run_adb_shell("cat /proc/net/arp")
    clients = []
    active_subnets = _get_active_hotspot_subnets()
    for line in arp.splitlines():
        parts = line.split()
        if len(parts) >= 6:
            ip = parts[0]
            hw = parts[3]
            device = parts[5]
            # Only show hotspot-range IPs
            if any(ip.startswith(subnet) for subnet in active_subnets):
                if hw not in ("00:00:00:00:00:00", ""):
                    clients.append(f"  - {ip}  (MAC: {hw}, Interface: {device})")

    if clients:
        status.append(f"Connected clients ({len(clients)}):")
        status.extend(clients)
    else:
        status.append("No clients currently connected or ARP table is empty.")
    return "\n".join(status)

def hotspot_scan_clients() -> str:
    """Scans for devices connected to this phone's hotspot using ARP + nmap ping sweep."""
    # Check which subnet is active via tethering
    out = _run_adb_shell("dumpsys tethering")
    is_active = bool(re.search(r'(swlan|softap|wlan)\d.*TetheredState', out))
    if not is_active:
        return "Hotspot is not active. Enable it first with hotspot_enable()."

    # First try ARP table (instant, no extra tools needed)
    arp = _run_adb_shell("cat /proc/net/arp")
    clients = []
    seen_ips = set()
    active_subnets = _get_active_hotspot_subnets()
    for line in arp.splitlines():
        parts = line.split()
        if len(parts) >= 6:
            ip = parts[0]
            hw = parts[3]
            if any(ip.startswith(s) for s in active_subnets) and hw not in ("00:00:00:00:00:00", ""):
                if ip not in seen_ips:
                    seen_ips.add(ip)
                    clients.append({"ip": ip, "mac": hw})

    # If ARP is empty, use fast parallel TCP socket probes across all known hotspot subnets
    if not clients:
        import threading
        found_lock = threading.Lock()

        def probe_host(ip):
            """Checks if a host is reachable by trying to open a TCP socket on port 5555 or 80."""
            for port in [5555, 80, 8080]:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.5)
                    result = s.connect_ex((ip, port))
                    s.close()
                    if result == 0:
                        with found_lock:
                            if ip not in seen_ips:
                                seen_ips.add(ip)
                                clients.append({"ip": ip, "mac": "?"})
                        return
                except Exception:
                    pass

        threads = []
        for subnet in active_subnets[:4]:
            for i in range(1, 255):
                ip = f"{subnet}.{i}"
                t = threading.Thread(target=probe_host, args=(ip,), daemon=True)
                threads.append(t)
                t.start()
        for t in threads:
            t.join(timeout=2.0)

    if not clients:
        return "No hotspot clients detected. Ensure the other device is connected to your hotspot."

    lines = [f"Found {len(clients)} client(s) on hotspot:"]
    for c in clients:
        lines.append(f"  - IP: {c['ip']}   MAC: {c['mac']}")
    return "\n".join(lines)

def _find_adb_port(ip: str) -> int | None:
    """Scans a device IP for its active ADB wireless debugging port."""
    import threading
    found_port = [None]
    lock = threading.Lock()

    # Step 1: Check classic ports first (instant)
    for p in [5555, 5037]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.2)
            res = s.connect_ex((ip, p))
            s.close()
            if res == 0:
                return p
        except:
            pass

    # Step 2: Android wireless debugging random ports are 30000-50000.
    # To avoid thread exhaustion, we'll scan in parallel chunks.
    ports = list(range(33000, 46000))
    chunk_size = 500
    
    def worker(port_chunk):
        for port in port_chunk:
            if found_port[0] is not None:
                return
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.15)
                res = s.connect_ex((ip, port))
                s.close()
                if res == 0:
                    with lock:
                        if found_port[0] is None:
                            found_port[0] = port
                    return
            except:
                pass

    threads = []
    for i in range(0, len(ports), chunk_size):
        chunk = ports[i:i+chunk_size]
        t = threading.Thread(target=worker, args=(chunk,), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=5.0)

    return found_port[0]


def hotspot_adb_autoconnect() -> str:
    """Scans for hotspot clients and automatically connects to them via ADB wireless debugging."""
    scan_result = hotspot_scan_clients()
    if "No hotspot" in scan_result or "not active" in scan_result:
        return scan_result

    # Extract IPs from scan
    ips = re.findall(r'IP:\s*([\d.]+)', scan_result)
    if not ips:
        return f"Scan returned results but no IPs could be parsed:\n{scan_result}"

    connected = []
    failed = []
    no_port = []

    for ip in ips:
        # Scan for the actual ADB wireless debugging port (NOT just 5555)
        port = _find_adb_port(ip)
        if not port:
            no_port.append(ip)
            continue

        addr = f"{ip}:{port}"
        res = subprocess.run(
            ["adb", "connect", addr],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=5
        )
        out = res.stdout.strip()
        if "connected to" in out.lower():
            connected.append(addr)
            # Save as default external target
            try:
                import json
                state_file = os.path.expanduser("~/.jarvis_adb_state.json")
                with open(state_file, "w") as f:
                    json.dump({"default_target": addr}, f)
            except Exception:
                pass
        else:
            failed.append(f"{addr} ({out})")

    lines = [scan_result, ""]
    if connected:
        lines.append(f"✅ ADB connected to: {', '.join(connected)}")
    if no_port:
        lines.append(f"⚠️  No open ADB port found on: {', '.join(no_port)}")
        lines.append("   → Enable Wireless Debugging on those devices first.")
    if failed:
        lines.append(f"❌ Port found but connection refused on: {', '.join(failed)}")
    return "\n".join(lines)
