import socket
import threading
import json
import os
import subprocess
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from jarvis.config import COLOR_GRAY, COLOR_RESET

# Ports
UDP_PORT = 5005
HTTP_PORT = 5006

# Thread & Server instance tracking
_http_server = None
_udp_listener = None
_server_thread = None
_udp_thread = None
_running = False

# List of allowed remote commands for safety
ALLOWED_COMMANDS = {
    "vibrate": ["duration_ms"],
    "speak": ["text"],
    "torch": ["status"],
    "show_toast": ["message"],
    "get_battery_status": [],
    "set_volume": ["stream", "volume"],
    "get_volume": [],
    "play_media": ["file"],
    "stop_media": [],
    "pause_media": [],
    "get_location": []
}

def get_device_name() -> str:
    """Returns a friendly Android device model name."""
    try:
        model = subprocess.run(["getprop", "ro.product.model"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        name = model.stdout.strip()
        if name:
            return name
    except Exception:
        pass
    return socket.gethostname() or "Jarvis-Node"

def get_local_ip() -> str:
    """Gets the primary local IP address of the device."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't need to be reachable, just triggers OS interface selection
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

class JarvisLinkHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress stdout logs to not clutter Jarvis voice/text console
        pass

    def do_GET(self):
        if self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            # Fetch local device details
            from jarvis.tools.device import get_battery_status
            try:
                battery = json.loads(get_battery_status())
            except Exception:
                battery = {"error": "Could not read battery"}

            data = {
                "name": get_device_name(),
                "ip": get_local_ip(),
                "battery": battery,
                "status": "online"
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            payload = json.loads(post_data.decode("utf-8"))
        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(f"Invalid JSON: {e}".encode("utf-8"))
            return

        if self.path == "/api/message":
            sender = payload.get("sender", "Unknown Link")
            text = payload.get("text", "")
            
            # Respond first, then speak in background to avoid timeout
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success", "message": "Message received"}).encode("utf-8"))

            def _speak_msg():
                from jarvis.tools.media import speak
                from jarvis.tools.system import show_toast
                msg = f"Incoming message from {sender}: {text}"
                show_toast(f"Jarvis Link: {sender}")
                speak(msg)
            threading.Thread(target=_speak_msg, daemon=True).start()

        elif self.path == "/api/command":
            command = payload.get("command")
            args = payload.get("args", {})
            sender = payload.get("sender", "Unknown Link")
            
            if command not in ALLOWED_COMMANDS:
                self.send_response(403)
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": f"Command '{command}' is not allowed or supported over Jarvis Link."}).encode("utf-8"))
                return
                
            # Import tools dynamically to execute
            from jarvis.tools import TOOLS
            if command in TOOLS:
                try:
                    # Filter arguments for safety
                    safe_args = {k: v for k, v in args.items() if k in ALLOWED_COMMANDS[command]}
                    result = TOOLS[command](**safe_args)
                    
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "success", "result": result}).encode("utf-8"))
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
            else:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": "Tool function missing"}).encode("utf-8"))

        elif self.path == "/api/clipboard":
            text = payload.get("text", "")
            from jarvis.tools.system import set_clipboard, show_toast
            set_clipboard(text)
            show_toast("Clipboard synced from nearby phone")
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success"}).encode("utf-8"))

        elif self.path == "/api/file":
            filename = payload.get("filename", "received_file")
            file_data_hex = payload.get("data", "")
            
            try:
                import binascii
                file_bytes = binascii.unhexlify(file_data_hex)
                
                # Save to downloads
                dest_dir = "/sdcard/Download"
                if not os.path.exists(dest_dir):
                    dest_dir = os.path.expanduser("~/Downloads")
                os.makedirs(dest_dir, exist_ok=True)
                
                dest_path = os.path.join(dest_dir, f"jarvis_link_{filename}")
                with open(dest_path, "wb") as f:
                    f.write(file_bytes)
                
                from jarvis.tools.system import show_toast
                from jarvis.tools.media import speak
                show_toast(f"Received file: {filename}")
                speak(f"Received file {filename} from {payload.get('sender', 'nearby device')}")
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "path": dest_path}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def _run_udp_listener():
    """Listens for discovery broadcasts on port UDP_PORT."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Enable address reuse
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", UDP_PORT))
    except Exception as e:
        print(f"UDP Bind Error: {e}")
        return

    while _running:
        try:
            sock.settimeout(1.0)
            data, addr = sock.recvfrom(1024)
            msg = data.decode("utf-8")
            if msg.startswith("JARVIS_PING:"):
                # Format: JARVIS_PING:<IP>:<PORT>:<NAME>
                parts = msg.split(":", 3)
                if len(parts) == 4:
                    remote_ip = parts[1]
                    remote_port = int(parts[2])
                    remote_name = parts[3]
                    
                    # Respond with pong to the remote ip/port
                    pong_msg = f"JARVIS_PONG:{get_local_ip()}:{HTTP_PORT}:{get_device_name()}"
                    sock.sendto(pong_msg.encode("utf-8"), (remote_ip, UDP_PORT))
        except socket.timeout:
            continue
        except Exception:
            continue
    sock.close()

def _run_http_server():
    global _http_server
    try:
        _http_server = HTTPServer(("", HTTP_PORT), JarvisLinkHTTPHandler)
        _http_server.serve_forever()
    except Exception as e:
        print(f"HTTP Server error: {e}")

def link_start_server() -> str:
    """Starts the background servers for discovery and communication."""
    global _running, _server_thread, _udp_thread, _http_server
    if _running:
        return f"Jarvis Link Server is already running on {get_local_ip()}:{HTTP_PORT}"
    
    _running = True
    
    # Start HTTP
    _server_thread = threading.Thread(target=_run_http_server, daemon=True)
    _server_thread.start()
    
    # Start UDP Listener
    _udp_thread = threading.Thread(target=_run_udp_listener, daemon=True)
    _udp_thread.start()
    
    return f"Jarvis Link Server started successfully on {get_local_ip()}:{HTTP_PORT}. Local discovery active."

def link_status() -> str:
    """Returns the current status of the Jarvis Link Server."""
    if _running:
        return f"Jarvis Link: ACTIVE\nDevice Name: {get_device_name()}\nIP Address: {get_local_ip()}\nHTTP Port: {HTTP_PORT}\nUDP Discovery Port: {UDP_PORT}"
    return "Jarvis Link: INACTIVE"

def link_scan() -> str:
    """Scans the local network for other active Jarvis Link devices using UDP broadcasts."""
    # Ensure server is running (so we can listen for responses)
    if not _running:
        link_start_server()
        
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(1.5)
    
    # Bind to a temporary port to receive pongs
    try:
        sock.bind(("", 0))
    except Exception as e:
        return f"Scan failed: could not bind socket ({e})"
        
    ping_msg = f"JARVIS_PING:{get_local_ip()}:{HTTP_PORT}:{get_device_name()}"
    
    # Broadcast to network
    sock.sendto(ping_msg.encode("utf-8"), ("255.255.255.255", UDP_PORT))
    
    devices = []
    seen_ips = set()
    import time
    start_time = time.time()
    
    while time.time() - start_time < 1.5:
        try:
            data, addr = sock.recvfrom(1024)
            msg = data.decode("utf-8")
            if msg.startswith("JARVIS_PONG:"):
                # Format: JARVIS_PONG:<IP>:<PORT>:<NAME>
                parts = msg.split(":", 3)
                if len(parts) == 4:
                    ip = parts[1]
                    port = int(parts[2])
                    name = parts[3]
                    
                    if ip not in seen_ips and ip != get_local_ip():
                        seen_ips.add(ip)
                        devices.append({"name": name, "ip": ip, "port": port})
        except socket.timeout:
            break
        except Exception:
            continue
            
    sock.close()
    
    if not devices:
        return "No nearby Jarvis devices detected on the network."
        
    result_lines = ["Nearby Jarvis Link devices found:"]
    for d in devices:
        result_lines.append(f"- {d['name']} @ {d['ip']}:{d['port']}")
    return "\n".join(result_lines)

def link_send_message(target_ip: str, message: str) -> str:
    """Sends a text message payload to a nearby Jarvis device."""
    url = f"http://{target_ip}:{HTTP_PORT}/api/message"
    payload = {
        "sender": get_device_name(),
        "text": message
    }
    try:
        r = requests.post(url, json=payload, timeout=5)
        if r.status_code == 200:
            return f"Successfully sent transmission to {target_ip}: '{message}'"
        return f"Failed to send. Remote returned status {r.status_code}: {r.text}"
    except Exception as e:
        return f"Link connection error: {e}"

def link_send_command(target_ip: str, command: str, args_json: str = "{}") -> str:
    """Executes a command (like vibrate, torch, speak, battery) on a remote Jarvis device."""
    url = f"http://{target_ip}:{HTTP_PORT}/api/command"
    try:
        args = json.loads(args_json)
    except Exception as e:
        return f"Invalid arguments JSON: {e}"
        
    payload = {
        "sender": get_device_name(),
        "command": command,
        "args": args
    }
    try:
        r = requests.post(url, json=payload, timeout=5)
        if r.status_code == 200:
            res_data = r.json()
            return f"Remote Execution Succeeded:\n{res_data.get('result')}"
        return f"Remote Execution Failed: {r.text}"
    except Exception as e:
        return f"Link connection error: {e}"

def link_sync_clipboard(target_ip: str) -> str:
    """Syncs the current device's clipboard with the target device."""
    from jarvis.tools.system import get_clipboard
    clip = get_clipboard()
    if not clip:
        return "Local clipboard is empty."
        
    url = f"http://{target_ip}:{HTTP_PORT}/api/clipboard"
    payload = {
        "sender": get_device_name(),
        "text": clip
    }
    try:
        r = requests.post(url, json=payload, timeout=5)
        if r.status_code == 200:
            return f"Successfully synced clipboard to {target_ip}."
        return f"Failed to sync clipboard: {r.text}"
    except Exception as e:
        return f"Link connection error: {e}"

def link_send_file(target_ip: str, filepath: str) -> str:
    """Transfers a local file to the target device's download folder."""
    if not os.path.exists(filepath):
        return f"File '{filepath}' does not exist on this device."
        
    filename = os.path.basename(filepath)
    try:
        with open(filepath, "rb") as f:
            file_bytes = f.read()
        import binascii
        hex_data = binascii.hexlify(file_bytes).decode("utf-8")
    except Exception as e:
        return f"Failed to read file: {e}"
        
    url = f"http://{target_ip}:{HTTP_PORT}/api/file"
    payload = {
        "sender": get_device_name(),
        "filename": filename,
        "data": hex_data
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            return f"File '{filename}' successfully transmitted to {target_ip}."
        return f"Failed to transmit file: {r.text}"
    except Exception as e:
        return f"Link connection error: {e}"
