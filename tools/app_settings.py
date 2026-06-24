import subprocess
import re
from jarvis.tools.devices_ext import _get_default_adb_target, _resolve_target, _ensure_adb_connected

# --- App data / system settings access via ADB ---
#
# Covers things Termux:API has no command for: deeper battery diagnostics,
# arbitrary system settings (read AND write), and per-app package info.
#
# Scope, deliberately narrow:
#   - Read-only tools (battery, settings_get, app_info) carry no risk beyond
#     information disclosure to the person asking.
#   - Write tools (settings_put, clear_app_data) each take ONE explicit
#     named target (one setting key, or one named package) and do exactly
#     what's asked -- no bulk operations, no "clean up my phone" style
#     inference, no uninstalling, no touching another app's private data
#     beyond its own cache/settings via the standard `pm clear` mechanism.
#   - There is no app-discovery/recommendation logic here that decides
#     *which* app or setting to touch -- that judgment call stays with
#     whoever (person or LLM) calls the tool with a specific name/key.


def _resolve_local_target(target_ip: str = "") -> str | None:
    """Resolves the ADB target to use, defaulting to whatever's already
    connected. Returns None if no device link can be established."""
    if not target_ip or target_ip.lower() == "default":
        target_ip = _get_default_adb_target()
    target = _resolve_target(target_ip)
    if not _ensure_adb_connected(target):
        return None
    return target


# --- Battery diagnostics ---

_HEALTH_CODES = {
    "1": "Unknown",
    "2": "Good",
    "3": "Overheat",
    "4": "Dead",
    "5": "Over voltage",
    "6": "Unspecified failure",
    "7": "Cold",
}

_STATUS_CODES = {
    "1": "Unknown",
    "2": "Charging",
    "3": "Discharging",
    "4": "Not charging",
    "5": "Full",
}

_PLUGGED_CODES = {
    "0": "Not plugged in",
    "1": "AC charger",
    "2": "USB",
    "4": "Wireless",
}


def get_battery_diagnostics(target_ip: str = "") -> str:
    """READ-ONLY. Returns deeper battery STATE info than the basic battery
    status tool: voltage, charge current, technology, and health. This does
    NOT identify what is consuming power -- Android's dumpsys battery has
    no per-app usage data. For "why is my battery draining" questions, this
    can report the battery's physical state but cannot name a cause; the
    person should be pointed to Settings > Battery > Battery usage on the
    device itself for an app-level breakdown.

    Args:
        target_ip: ADB target to inspect. Leave blank to use the default device.
    """
    target = _resolve_local_target(target_ip)
    if not target:
        return "Could not establish an ADB link. Ensure Wireless Debugging is active and the device is connected."

    res = subprocess.run(
        ["adb", "-s", target, "shell", "dumpsys", "battery"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10
    )
    if res.returncode != 0 or not res.stdout.strip():
        return "Failed to read battery diagnostics from the device."

    fields = {}
    for line in res.stdout.splitlines():
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()

    lines = ["Battery diagnostics:"]

    if "level" in fields:
        lines.append(f"  - Battery level: {fields['level']}%")

    if "voltage" in fields:
        try:
            mv = int(fields["voltage"])
            # dumpsys reports voltage in millivolts. ~3700-3900mV is normal
            # mid-range for a Li-ion phone battery; ~4200mV is near full;
            # below ~3500mV is low. Surfacing it in volts (not "high"/"low"
            # editorializing here) avoids the model inventing its own
            # interpretation of whether a given mV reading is normal.
            lines.append(f"  - Voltage: {mv / 1000:.3f} V")
        except ValueError:
            lines.append(f"  - Voltage (raw): {fields['voltage']}")

    if "temperature" in fields:
        try:
            tenths_c = int(fields["temperature"])
            lines.append(f"  - Temperature: {tenths_c / 10:.1f}°C")
        except ValueError:
            pass

    if "technology" in fields:
        lines.append(f"  - Battery technology: {fields['technology']}")

    if "health" in fields:
        health_label = _HEALTH_CODES.get(fields["health"], f"Unrecognized code ({fields['health']})")
        lines.append(f"  - Health: {health_label}")

    if "status" in fields:
        status_label = _STATUS_CODES.get(fields["status"], f"Unrecognized code ({fields['status']})")
        lines.append(f"  - Charging status: {status_label}")

    if "plugged" in fields:
        plugged_label = _PLUGGED_CODES.get(fields["plugged"], f"Unrecognized code ({fields['plugged']})")
        lines.append(f"  - Power source: {plugged_label}")

    if "Max charging current" in fields:
        lines.append(f"  - Max charging current: {fields['Max charging current']} µA")
    if "Max charging voltage" in fields:
        lines.append(f"  - Max charging voltage: {fields['Max charging voltage']} µV")

    if len(lines) == 1:
        return "Battery diagnostics command ran, but no recognizable fields were found."
    return "\n".join(lines)


# --- System settings: read and write ---

_VALID_NAMESPACES = {"system", "secure", "global"}


def get_system_setting(key: str, namespace: str = "system", target_ip: str = "") -> str:
    """READ-ONLY. Reads a single Android system setting by exact key name,
    e.g. key="screen_off_timeout" namespace="system". Use this to check the
    current value of a setting before changing it, or to answer "what's my
    screen timeout set to" type questions.

    Args:
        key: the exact settings key (e.g. "screen_off_timeout", "accelerometer_rotation").
        namespace: one of "system", "secure", "global". Defaults to "system".
        target_ip: ADB target. Leave blank to use the default device.
    """
    namespace = namespace.lower().strip()
    if namespace not in _VALID_NAMESPACES:
        return f"Invalid namespace '{namespace}'. Must be one of: system, secure, global."

    target = _resolve_local_target(target_ip)
    if not target:
        return "Could not establish an ADB link."

    res = subprocess.run(
        ["adb", "-s", target, "shell", "settings", "get", namespace, key],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10
    )
    value = res.stdout.strip()
    if not value or value.lower() == "null":
        return f"Setting '{key}' in namespace '{namespace}' is not set (null), or the key doesn't exist."
    return f"{namespace}.{key} = {value}"


def set_system_setting(key: str, value: str, namespace: str = "system", target_ip: str = "") -> str:
    """Writes a single Android system setting by exact key and value, e.g.
    key="screen_off_timeout" value="30000" (milliseconds) namespace="system".
    Changes exactly the one named key to exactly the one given value --
    nothing else is touched. Use get_system_setting first if unsure of the
    current value or expected format.

    Args:
        key: the exact settings key (e.g. "screen_off_timeout", "accelerometer_rotation").
        value: the new value to set, as a string (e.g. "30000", "1", "0").
        namespace: one of "system", "secure", "global". Defaults to "system".
        target_ip: ADB target. Leave blank to use the default device.
    """
    namespace = namespace.lower().strip()
    if namespace not in _VALID_NAMESPACES:
        return f"Invalid namespace '{namespace}'. Must be one of: system, secure, global."

    if not key or not key.strip():
        return "No setting key provided."

    target = _resolve_local_target(target_ip)
    if not target:
        return "Could not establish an ADB link."

    res = subprocess.run(
        ["adb", "-s", target, "shell", "settings", "put", namespace, key, str(value)],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10
    )
    if res.returncode != 0:
        return f"Failed to set '{key}': {res.stderr.strip() or res.stdout.strip()}"

    # Confirm by reading it back
    confirm = subprocess.run(
        ["adb", "-s", target, "shell", "settings", "get", namespace, key],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10
    )
    new_value = confirm.stdout.strip()
    return f"Set {namespace}.{key} = {value} (confirmed current value: {new_value})"


# --- Package / app info ---

def get_app_info(package: str, target_ip: str = "") -> str:
    """READ-ONLY. Returns version, install/update dates, and granted
    permissions for a single named installed package. Use search_launcher_apps
    first if you only know the app's display name, not its package identifier.

    Args:
        package: exact package identifier (e.g. "com.whatsapp").
        target_ip: ADB target. Leave blank to use the default device.
    """
    if not package or not package.strip():
        return "No package name provided."
    package = package.strip()

    target = _resolve_local_target(target_ip)
    if not target:
        return "Could not establish an ADB link."

    res = subprocess.run(
        ["adb", "-s", target, "shell", "dumpsys", "package", package],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=15
    )
    out = res.stdout
    if not out.strip():
        return f"No package found matching '{package}'."

    version_match = re.search(r"versionName=(\S+)", out)
    version_code_match = re.search(r"versionCode=(\d+)", out)
    first_install_match = re.search(r"firstInstallTime=([\d-]+ [\d:]+)", out)
    last_update_match = re.search(r"lastUpdateTime=([\d-]+ [\d:]+)", out)

    granted_perms = sorted(set(re.findall(r"^\s+(android\.permission\.\S+): granted=true", out, re.MULTILINE)))

    lines = [f"App info for {package}:"]
    if version_match:
        lines.append(f"  - Version: {version_match.group(1)}" + (f" (code {version_code_match.group(1)})" if version_code_match else ""))
    if first_install_match:
        lines.append(f"  - First installed: {first_install_match.group(1)}")
    if last_update_match:
        lines.append(f"  - Last updated: {last_update_match.group(1)}")
    if granted_perms:
        lines.append(f"  - Granted permissions ({len(granted_perms)}):")
        for p in granted_perms[:15]:
            lines.append(f"      - {p.replace('android.permission.', '')}")
        if len(granted_perms) > 15:
            lines.append(f"      ... and {len(granted_perms) - 15} more")

    if len(lines) == 1:
        return f"Found package '{package}' but could not parse version/permission details."
    return "\n".join(lines)


# --- Narrow, explicit-target app data control ---

def clear_app_data(package: str, target_ip: str = "") -> str:
    """Clears cache AND data for exactly ONE named installed package --
    equivalent to Settings > Apps > [App] > Storage > Clear Data. This logs
    the app out and resets it to a fresh-install state; it does not
    uninstall the app. Requires the exact package identifier; use
    search_launcher_apps first if only the display name is known. Does not
    accept multiple packages or wildcards -- one explicit target per call.

    Args:
        package: exact package identifier (e.g. "com.instagram.android").
        target_ip: ADB target. Leave blank to use the default device.
    """
    if not package or not package.strip():
        return "No package name provided."
    package = package.strip()

    target = _resolve_local_target(target_ip)
    if not target:
        return "Could not establish an ADB link."

    res = subprocess.run(
        ["adb", "-s", target, "shell", "pm", "clear", package],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=15
    )
    out = (res.stdout + res.stderr).strip()
    if "Success" in out:
        return f"Cleared cache and data for {package}."
    return f"Failed to clear data for {package}: {out or 'unknown error (package name may be wrong)'}"
