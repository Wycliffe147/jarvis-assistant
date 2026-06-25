import subprocess
import os
import xml.etree.ElementTree as ET
from jarvis.tools.devices_ext import _get_default_adb_target, _resolve_target, _ensure_adb_connected

# --- Read-only UI inspection ---
#
# This module only ever reads what is currently on screen. It has no tap,
# swipe, text-input, or click capability of any kind. It exists so Jarvis
# (or the person asking it questions) can find out what's on the screen
# right now -- e.g. "what does this dialog say", "what buttons are visible" --
# without taking any action on the person's behalf. Any actual interaction
# still has to go through the existing explicit, coordinate-based ADB tools
# (adb_command's tap/swipe/text), one deliberate action at a time.

DUMP_REMOTE_PATH = "/sdcard/jarvis_ui_dump.xml"


def _resolve_local_target(target_ip: str = "") -> str | None:
    """Resolves the ADB target to inspect, defaulting to whatever's already
    connected. Returns None if no device link can be established."""
    if not target_ip or target_ip.lower() == "default":
        target_ip = _get_default_adb_target()
    target = _resolve_target(target_ip)
    if not _ensure_adb_connected(target):
        return None
    return target


def _fetch_ui_xml(target: str) -> str | None:
    """Dumps the current UI hierarchy on the target device and returns the
    raw XML as a string, or None on failure."""
    dump_res = subprocess.run(
        ["adb", "-s", target, "shell", "uiautomator", "dump", DUMP_REMOTE_PATH],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=15
    )
    if dump_res.returncode != 0:
        return None

    cat_res = subprocess.run(
        ["adb", "-s", target, "shell", "cat", DUMP_REMOTE_PATH],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10
    )
    # Best-effort cleanup of the temp file on the device
    subprocess.run(
        ["adb", "-s", target, "shell", "rm", "-f", DUMP_REMOTE_PATH],
        stdin=subprocess.DEVNULL, timeout=10
    )

    if cat_res.returncode != 0 or not cat_res.stdout.strip():
        return None
    return cat_res.stdout


def _parse_elements(xml_data: str, only_interactive: bool) -> list[dict]:
    """Parses uiautomator XML into a flat list of element dicts. Each dict
    has: text, resource_id, class_name, bounds, clickable, scrollable."""
    elements = []
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError:
        return elements

    for node in root.iter("node"):
        text = node.attrib.get("text", "").strip()
        desc = node.attrib.get("content-desc", "").strip()
        resource_id = node.attrib.get("resource-id", "").strip()
        class_name = node.attrib.get("class", "").strip()
        clickable = node.attrib.get("clickable", "false") == "true"
        scrollable = node.attrib.get("scrollable", "false") == "true"
        bounds = node.attrib.get("bounds", "")

        # Skip nodes that carry no useful information at all
        if not text and not desc and not resource_id:
            continue
        if only_interactive and not (clickable or scrollable):
            continue

        elements.append({
            "text": text or desc,
            "resource_id": resource_id.split("/")[-1] if resource_id else "",
            "class_name": class_name.split(".")[-1] if class_name else "",
            "bounds": bounds,
            "clickable": clickable,
            "scrollable": scrollable,
        })
    return elements


def ui_dump(target_ip: str = "", only_interactive: bool = True) -> str:
    """Reads the current screen contents (read-only -- does not tap, type,
    or interact in any way). Returns a text list of visible text, labels,
    and buttons along with their on-screen positions, so Jarvis or the user
    can know what's currently displayed.

    Args:
        target_ip: ADB target to inspect. Leave blank to use the currently
            connected/default device.
        only_interactive: if True (default), only lists elements that are
            clickable or scrollable (buttons, links, lists). Set False to
            see every text label on screen, including plain static text.
    """
    target = _resolve_local_target(target_ip)
    if not target:
        return f"Could not establish an ADB link to inspect. Ensure Wireless Debugging is active and the device is connected."

    xml_data = _fetch_ui_xml(target)
    if not xml_data:
        return "Failed to read the screen contents. The device may be locked, asleep, or uiautomator failed to start."

    elements = _parse_elements(xml_data, only_interactive)
    if not elements:
        kind = "interactive elements" if only_interactive else "elements with text"
        return f"No {kind} found on the current screen."

    lines = [f"Found {len(elements)} element(s) on screen:"]
    for el in elements:
        parts = [f'"{el["text"]}"'] if el["text"] else []
        if el["resource_id"]:
            parts.append(f"id={el['resource_id']}")
        if el["class_name"]:
            parts.append(el["class_name"])
        tags = []
        if el["clickable"]:
            tags.append("clickable")
        if el["scrollable"]:
            tags.append("scrollable")
        if tags:
            parts.append(f"[{', '.join(tags)}]")
        if el["bounds"]:
            parts.append(f"at {el['bounds']}")
        lines.append("  - " + " ".join(parts))

    return "\n".join(lines)


def ui_find_text(query: str, target_ip: str = "") -> str:
    """Reads the current screen (read-only) and reports whether any visible
    text or button matches the given query, along with its position. Does
    not tap or interact with anything -- purely informational, e.g. to
    answer 'is there a Save button on screen right now'.

    Args:
        query: text to search for, case-insensitive, partial match allowed.
        target_ip: ADB target to inspect. Leave blank to use the default device.
    """
    target = _resolve_local_target(target_ip)
    if not target:
        return "Could not establish an ADB link to inspect."

    xml_data = _fetch_ui_xml(target)
    if not xml_data:
        return "Failed to read the screen contents."

    elements = _parse_elements(xml_data, only_interactive=False)
    query_lower = query.lower().strip()
    matches = [el for el in elements if query_lower in el["text"].lower()]

    if not matches:
        return f"No element matching '{query}' was found on the current screen."

    lines = [f"Found {len(matches)} match(es) for '{query}':"]
    for el in matches:
        descriptor = f'"{el["text"]}"'
        if el["resource_id"]:
            descriptor += f" (id={el['resource_id']})"
        state = "clickable" if el["clickable"] else "not clickable"
        lines.append(f"  - {descriptor}, {state}, at {el['bounds']}")
    return "\n".join(lines)


def input_my_screen(action: str = "tap", params_json: str = "{}") -> str:
    """Sends touch/keyboard input to THIS phone's screen via ADB.

    This is the host-device counterpart to adb_command — same actions, same
    params format, but always targets this phone. Use after ui_dump or
    read_my_screen to act on what Jarvis sees. Combine them to navigate any
    app autonomously: read → decide → tap → read again → repeat.

    Actions:
      tap        {\"x\": int, \"y\": int}
                 Tap a pixel coordinate. Get coordinates from ui_dump's
                 \"at [x1,y1][x2,y2]\" bounds — use the centre of the range.

      swipe      {\"x1\": int, \"y1\": int, \"x2\": int, \"y2\": int, \"duration_ms\": int}
                 Swipe between two points. duration_ms controls speed
                 (default 300). Use for scrolling, pull-to-refresh, sliders.

      text       {\"text\": str}
                 Type text into the focused field. Tap the field first.
                 Spaces are handled automatically.

      keyevent   {\"code\": int}
                 Send a hardware key. Common codes:
                   3 = Home, 4 = Back, 24 = Volume Up, 25 = Volume Down,
                   26 = Power/Screen, 66 = Enter, 187 = Recents,
                   111 = Escape, 67 = Backspace

      long_press {\"x\": int, \"y\": int, \"duration_ms\": int}
                 Long-press at a coordinate (default 800ms). Use for
                 context menus, drag handles, text selection.

      shell      {\"cmd\": str}
                 Run an arbitrary adb shell command on this device.
                 Use sparingly — prefer the typed actions above.
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
                # LLM passed the text value directly instead of {"text": "..."}
                params = {"text": params_json}
            elif action in ("tap", "long_press"):
                # Shouldn't be a bare string, but handle gracefully
                params = json.loads(stripped) if stripped.startswith("{") else {}
            elif action == "keyevent":
                # LLM passed the code as a bare string
                params = {"code": int(stripped)} if stripped.isdigit() else json.loads(stripped)
            else:
                params = json.loads(stripped)
        elif isinstance(params_json, int):
            # LLM passed a bare int — most likely a keyevent code
            params = {"code": params_json} if action == "keyevent" else {"x": params_json}
        elif isinstance(params_json, list):
            # LLM passed [x, y] — map to tap/swipe coords
            if action in ("tap", "long_press") and len(params_json) >= 2:
                params = {"x": params_json[0], "y": params_json[1]}
            elif action == "swipe" and len(params_json) >= 4:
                params = {"x1": params_json[0], "y1": params_json[1],
                          "x2": params_json[2], "y2": params_json[3]}
            else:
                params = {}
        else:
            params = {}
        if not isinstance(params, dict):
            return f"Invalid params_json: expected a JSON object (dict), got {type(params).__name__}. Example: '{{\"code\": 3}}'"
    except Exception as e:
        return f"Invalid params_json: {e}"

    target = _resolve_local_target()
    if not target:
        return (
            "Could not establish a local ADB link. "
            "Make sure Wireless Debugging is enabled in Developer Options."
        )

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
        # adb input text treats spaces literally only when quoted correctly;
        # replacing with %s is the reliable cross-shell approach.
        txt_escaped = txt.replace(" ", "%s")
        cmd = adb_base + ["input", "text", txt_escaped]

    elif action == "keyevent":
        code = params.get("code", 3)
        cmd = adb_base + ["input", "keyevent", str(code)]

    elif action == "long_press":
        x = params.get("x", 0)
        y = params.get("y", 0)
        dur = params.get("duration_ms", 800)
        # long-press = swipe from the same point to itself with a long duration
        cmd = adb_base + ["input", "swipe", str(x), str(y), str(x), str(y), str(dur)]

    elif action == "shell":
        shell_cmd = params.get("cmd", "")
        cmd = adb_base + shell_cmd.split()

    else:
        return (
            f"Unknown action '{action}'. "
            "Valid actions: tap, swipe, text, keyevent, long_press, shell."
        )

    res = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if res.returncode == 0:
        return f"input_my_screen: {action} executed successfully."
    return f"input_my_screen failed: {res.stderr.strip() or res.stdout.strip()}"


def _parse_bounds(bounds: str) -> tuple[int, int, int, int] | None:
    """Parses a uiautomator bounds string '[x1,y1][x2,y2]' into (x1, y1, x2, y2).
    Returns None if the string cannot be parsed."""
    import re
    m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))


def ui_tap_element(query: str, target_ip: str = "", match_by: str = "text",
                   occurrence: int = 1) -> str:
    """Finds an element on the current screen by text or resource-id and taps
    its exact center. This is the PREFERRED way to tap buttons, search bars,
    and input fields — it eliminates coordinate math errors entirely.

    Args:
        query:      The text label or resource-id fragment to match.
                    Examples: "Search", "search_bar", "search_edit_text"
        target_ip:  ADB target. Leave blank for this device.
        match_by:   "text" to match against visible labels/content-desc (default),
                    "id"   to match against the resource-id fragment.
        occurrence: Which match to tap when multiple elements match (1 = first).

    Returns a status string. On success: 'Tapped "<label>" at (cx, cy).'
    On failure: a description of what went wrong.

    Workflow example for searching YouTube:
        ui_tap_element("Search")          # taps the search bar by label
        input_my_screen("text", {"text": "lofi hip hop"})
        input_my_screen("keyevent", {"code": 66})   # Enter
    """
    target = _resolve_local_target(target_ip)
    if not target:
        return "Could not establish an ADB link."

    xml_data = _fetch_ui_xml(target)
    if not xml_data:
        return "Failed to read the screen contents."

    elements = _parse_elements(xml_data, only_interactive=False)
    query_lower = query.lower().strip()

    if match_by == "id":
        matches = [el for el in elements
                   if query_lower in el["resource_id"].lower()]
    else:
        matches = [el for el in elements
                   if query_lower in el["text"].lower()]

    if not matches:
        # Second-pass: try both fields before giving up
        matches = [el for el in elements
                   if query_lower in el["text"].lower()
                   or query_lower in el["resource_id"].lower()]

    if not matches:
        return (f"No element matching '{query}' found on screen. "
                f"Call ui_dump to see what's available.")

    idx = max(0, occurrence - 1)
    if idx >= len(matches):
        idx = len(matches) - 1
    el = matches[idx]

    coords = _parse_bounds(el["bounds"])
    if not coords:
        return (f"Found element '{el['text'] or el['resource_id']}' but "
                f"could not parse its bounds: {el['bounds']}")

    x1, y1, x2, y2 = coords
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2

    import subprocess as _sp
    adb_base = ["adb", "-s", target, "shell"]
    res = _sp.run(adb_base + ["input", "tap", str(cx), str(cy)],
                  capture_output=True, text=True, stdin=_sp.DEVNULL)
    if res.returncode != 0:
        return f"Tap failed: {res.stderr.strip() or res.stdout.strip()}"

    label = el["text"] or el["resource_id"] or query
    return f'Tapped "{label}" at ({cx}, {cy}).'
