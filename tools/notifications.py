import subprocess
import re
from jarvis.tools.devices_ext import _get_default_adb_target, _resolve_target, _ensure_adb_connected

# --- Read-only notification access ---
#
# This module only ever reads currently-posted notifications. It has no
# dismiss, reply, mark-as-read, or notification-action capability of any
# kind -- including the inline action buttons some notifications expose
# (e.g. "Reply", "Mark as read", "Archive"). It exists so Jarvis can answer
# questions like "what's my latest notification" or "read my last WhatsApp
# message" without taking any action on the person's behalf. Any future
# action-taking on notifications is a deliberate, separate decision, not an
# extension of this file.
#
# Implementation note: this uses `adb shell dumpsys notification`, a
# developer diagnostics dump, not a proper NotificationListenerService. It's
# good enough for on-demand "what does it say" queries but is verbose,
# occasionally truncates long text, and is not a real-time push mechanism.


def _resolve_local_target(target_ip: str = "") -> str | None:
    """Resolves the ADB target to inspect, defaulting to whatever's already
    connected. Returns None if no device link can be established."""
    if not target_ip or target_ip.lower() == "default":
        target_ip = _get_default_adb_target()
    target = _resolve_target(target_ip)
    if not _ensure_adb_connected(target):
        return None
    return target


def _fetch_notification_dump(target: str) -> str | None:
    """Runs dumpsys notification on the target device and returns the raw
    text output, or None on failure."""
    res = subprocess.run(
        ["adb", "-s", target, "shell", "dumpsys", "notification", "--noredact"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=15
    )
    if res.returncode != 0 or not res.stdout.strip():
        return None
    return res.stdout


def _parse_notifications(dump_text: str) -> list[dict]:
    """Parses dumpsys notification output into a flat list of notification
    dicts. Each dict has: app (package name), title, text, when (raw
    timestamp ms if found). Best-effort -- dumpsys output format is not a
    stable public API and varies across Android versions/OEMs."""
    notifications = []

    # NotificationRecord blocks start with a line like:
    #   NotificationRecord(0x08696ef6: pkg=com.google.android.apps.messaging ...
    # Package name is its own "pkg=" field, not embedded in "key=". Title
    # and text live inside the extras Bundle dump further down, in the form
    #   android.title=String (Airtel)
    #   android.text=String (some message text)
    # The value can contain almost anything (including parentheses), so we
    # match everything up to the end of that specific line rather than
    # trying to balance parens.
    blocks = re.split(r"(?=NotificationRecord\()", dump_text)

    for block in blocks:
        pkg_match = re.search(r"NotificationRecord\([^:]*:\s*pkg=(\S+)", block)
        if not pkg_match:
            continue
        app = pkg_match.group(1).strip()

        title_match = re.search(r"android\.title=String \((.*)\)\s*$", block, re.MULTILINE)
        text_match = re.search(r"android\.text=String \((.*)\)\s*$", block, re.MULTILINE)
        when_match = re.search(r"when=(\d+)", block)

        title = title_match.group(1).strip() if title_match else ""
        text = text_match.group(1).strip() if text_match else ""

        # Skip entries that yielded no readable content at all (e.g.
        # purely structural/group-summary records, ongoing foreground
        # service notifications with no visible title/text, etc.)
        if not title and not text:
            continue

        notifications.append({
            "app": app,
            "title": title,
            "text": text,
            "when": when_match.group(1) if when_match else "",
        })

    return notifications


def list_notifications(target_ip: str = "", app_filter: str = "", limit: int = 10) -> str:
    """Reads currently-posted notifications (read-only -- does not dismiss,
    open, reply to, or otherwise act on any of them). Returns a list of
    app, title, and message text for each notification currently showing.

    Args:
        target_ip: ADB target to inspect. Leave blank to use the currently
            connected/default device.
        app_filter: optional partial package name to filter by (e.g.
            "whatsapp" matches "com.whatsapp"). Leave blank for all apps.
        limit: maximum number of notifications to return (most recent
            first), default 10.
    """
    target = _resolve_local_target(target_ip)
    if not target:
        return "Could not establish an ADB link to inspect. Ensure Wireless Debugging is active and the device is connected."

    dump_text = _fetch_notification_dump(target)
    if dump_text is None:
        return "Failed to read notifications from the device."

    notifications = _parse_notifications(dump_text)

    if app_filter:
        filt = app_filter.lower().strip()
        notifications = [n for n in notifications if filt in n["app"].lower()]

    if not notifications:
        scope = f" matching '{app_filter}'" if app_filter else ""
        return f"No notifications{scope} currently showing."

    # Most recent first, where a timestamp was found
    notifications.sort(key=lambda n: int(n["when"]) if n["when"].isdigit() else 0, reverse=True)
    notifications = notifications[:max(1, limit)]

    lines = [f"Found {len(notifications)} notification(s):"]
    for n in notifications:
        parts = [f"[{n['app']}]"]
        if n["title"]:
            parts.append(f'"{n["title"]}"')
        if n["text"]:
            parts.append(f"- {n['text']}")
        lines.append("  " + " ".join(parts))

    return "\n".join(lines)


def get_latest_notification(target_ip: str = "", app_filter: str = "", **_ignored) -> str:
    """Reads only the single most recent notification (read-only -- does
    not dismiss, open, or reply to it). Useful for "what's my latest
    notification" or "read my last WhatsApp message".

    Args:
        target_ip: ADB target to inspect. Leave blank to use the default device.
        app_filter: optional partial package name to filter by (e.g.
            "whatsapp" matches "com.whatsapp"). Leave blank for any app.
    """
    target = _resolve_local_target(target_ip)
    if not target:
        return "Could not establish an ADB link to inspect."

    dump_text = _fetch_notification_dump(target)
    if dump_text is None:
        return "Failed to read notifications from the device."

    notifications = _parse_notifications(dump_text)

    if app_filter:
        filt = app_filter.lower().strip()
        notifications = [n for n in notifications if filt in n["app"].lower()]

    if not notifications:
        scope = f" from '{app_filter}'" if app_filter else ""
        return f"No notification{scope} currently showing."

    notifications.sort(key=lambda n: int(n["when"]) if n["when"].isdigit() else 0, reverse=True)
    latest = notifications[0]

    parts = [f"[{latest['app']}]"]
    if latest["title"]:
        parts.append(f'"{latest["title"]}"')
    if latest["text"]:
        parts.append(f"- {latest['text']}")
    return " ".join(parts)
