import subprocess
from jarvis.config import COLOR_GRAY, COLOR_RESET
from jarvis.cache.activity_cache import _load_activity_cache, _save_activity_cache

def list_apps(search_query: str = "") -> str:
    """Lists installed third-party user apps using native shell cmd framework."""
    result = subprocess.run(["cmd", "package", "list", "packages", "-3"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    packages = [line.replace("package:", "").strip() for line in result.stdout.splitlines() if line]
    
    if search_query:
        matches = [p for p in packages if search_query.lower() in p.lower()]
        if not matches:
            result_all = subprocess.run(["cmd", "package", "list", "packages"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
            all_packages = [line.replace("package:", "").strip() for line in result_all.stdout.splitlines() if line]
            matches = [p for p in all_packages if search_query.lower() in p.lower()]
            
        if not matches:
            return f"No installed apps found matching '{search_query}'."
        return "\n".join(matches[:15])
        
    return "\n".join(packages[:20])

def _get_foreground_package() -> str:
    """Returns the package name of the app currently in the foreground, or '' on failure.
    Uses 'dumpsys activity top' (faster, more reliable than 'dumpsys window windows')
    with a fallback to window focus parsing.
    """
    try:
        # Primary: dumpsys activity top — first non-empty TASK line gives the package
        res = subprocess.run(
            ["adb", "shell", "dumpsys", "activity", "top"],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=5
        )
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith("TASK") and " " in line:
                # Format: "TASK com.whatsapp id=123 userId=0"
                pkg = line.split()[1]
                if "." in pkg:
                    return pkg
    except Exception:
        pass

    try:
        # Fallback: mCurrentFocus from window manager
        res = subprocess.run(
            ["adb", "shell", "dumpsys", "window", "windows"],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=5
        )
        for line in res.stdout.splitlines():
            if "mCurrentFocus" in line and "Window{" in line:
                token = line.strip().split()[-1].rstrip("}")
                return token.split("/")[0]
    except Exception:
        pass

    return ""


def _wait_for_app_ready(package_name: str, timeout: float = 10.0, poll_interval: float = 0.4) -> str | None:
    """Polls until the target package is in the foreground AND the UI tree has
    rendered meaningful content. Returns a ui_dump snapshot when ready, or None on timeout.
    All calls are local ADB — no API calls consumed.
    """
    import time
    from jarvis.tools.ui_inspect import ui_dump

    deadline = time.time() + timeout
    while time.time() < deadline:
        fg = _get_foreground_package()
        if fg == package_name:
            snapshot = ui_dump(only_interactive=False)
            is_termux_shell = "terminal_toolbar" in snapshot or "ESC" in snapshot[:200]
            has_content = snapshot.startswith("Found") and not is_termux_shell
            element_count = 0
            if has_content:
                try:
                    element_count = int(snapshot.split("Found")[1].split("element")[0].strip())
                except Exception:
                    pass
            if has_content and element_count >= 3:
                return snapshot
        time.sleep(poll_interval)
    return None


def _is_app_running(package_name: str) -> bool:
    """Returns True if the app has a live process — meaning it is already running
    in the background or foreground and does not need a cold launch."""
    try:
        res = subprocess.run(
            ["adb", "shell", "pidof", package_name],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=5
        )
        return bool(res.stdout.strip())
    except Exception:
        return False


def _bring_to_front(package_name: str) -> bool:
    """Brings an already-running app to the foreground exactly as the user left it,
    without resetting its back stack. Uses FLAG_ACTIVITY_REORDER_TO_FRONT so an
    open chat, image viewer, etc. stays open rather than jumping to the home screen.
    Returns True if the intent fired without error.
    """
    res = subprocess.run(
        [
            "am", "start",
            "-a", "android.intent.action.MAIN",
            "-c", "android.intent.category.LAUNCHER",
            "--activity-reorder-to-front",
            package_name,
        ],
        capture_output=True, text=True, stdin=subprocess.DEVNULL
    )
    out = (res.stdout + res.stderr).strip()
    return "Error" not in out and "Exception" not in out


def open_app(package_name: str) -> str:
    """Brings an app to the foreground and waits until it has fully rendered.

    If the app is already running, it is brought forward exactly as the user
    left it (open chat, image, etc.) — the back stack is NOT reset.
    If the app is not running, it is cold-launched via component probing.

    Returns a ui_dump snapshot of the screen so the model can act immediately
    without a separate ui_dump call.
    """
    if " → " in package_name:
        package_name = package_name.split(" → ")[-1].strip()

    package_name = package_name.strip()
    launched = False

    # --- Path A: app already running — bring it forward without resetting state ---
    if _is_app_running(package_name):
        print(f"{COLOR_GRAY}[{package_name} already running — bringing to foreground...]{COLOR_RESET}")
        if _bring_to_front(package_name):
            launched = True
        # If bring-to-front failed for some reason, fall through to cold launch

    # --- Path B: cold launch via component probing ---
    if not launched:
        activity_cache = _load_activity_cache()

        # Hit 1: cached activity component
        if package_name in activity_cache:
            target_component = f"{package_name}/{activity_cache[package_name]}"
            result = subprocess.run(["am", "start", "-n", target_component], capture_output=True, text=True, stdin=subprocess.DEVNULL)
            output = (result.stdout + result.stderr).strip()
            if "Error" not in output and "Exception" not in output and "unable to resolve" not in output.lower():
                launched = True

        # Hit 2: brute-force pattern probing
        if not launched:
            print(f"{COLOR_GRAY}[Probing activity matrix for execution paths inside '{package_name}'...]{COLOR_RESET}")
            patterns = [
                "MainActivity", "Main", "SplashActivity", "HomeActivity", "LauncherActivity",
                "app.MainActivity", "app.TermuxActivity", "ui.MainActivity", "ui.LauncherActivity"
            ]
            for suffix in patterns:
                candidate = f"{package_name}.{suffix}" if not suffix.startswith(package_name) else suffix
                print(f"{COLOR_GRAY}[Probing Component: {package_name}/{candidate}]{COLOR_RESET}", end="\r")

                res = subprocess.run(["am", "start", "-n", f"{package_name}/{candidate}"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
                out = (res.stdout + res.stderr).strip()
                if "Error" not in out and "Exception" not in out and "unable to resolve" not in out.lower():
                    activity_cache[package_name] = candidate
                    _save_activity_cache(activity_cache)
                    launched = True
                    break

                if "." in suffix:
                    short_candidate = f".{suffix.split('.')[-1]}"
                    res = subprocess.run(["am", "start", "-n", f"{package_name}/{short_candidate}"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
                    out = (res.stdout + res.stderr).strip()
                    if "Error" not in out and "Exception" not in out and "unable to resolve" not in out.lower():
                        activity_cache[package_name] = short_candidate
                        _save_activity_cache(activity_cache)
                        launched = True
                        break

    if not launched:
        return f"Failed to launch {package_name}: no matching activity found."

    print(f"{COLOR_GRAY}[Waiting for {package_name} to render...]{COLOR_RESET}")
    snapshot = _wait_for_app_ready(package_name)

    if snapshot:
        return (
            f"App ready. Current screen state (no need to call ui_dump again):\n{snapshot}"
        )

    return (
        f"Launched {package_name} but it has not fully rendered yet. "
        f"Call ui_dump once to check the current screen state before acting."
    )

def search_launcher_apps(query: str) -> str:
    """Resolve app package name from query using known-packages table + cmd package list fallback."""
    print(f"{COLOR_GRAY}[Searching for app matching '{query}'...]{COLOR_RESET}")

    KNOWN_PACKAGES = {
        "youtube":     "com.google.android.youtube",
        "whatsapp":    "com.whatsapp",
        "chrome":      "com.android.chrome",
        "maps":        "com.google.android.apps.maps",
        "gmail":       "com.google.android.gm",
        "spotify":     "com.spotify.music",
        "facebook":    "com.facebook.katana",
        "instagram":   "com.instagram.android",
        "telegram":    "org.telegram.messenger",
        "tiktok":      "com.zhiliaoapp.musically",
        "snapchat":    "com.snapchat.android",
        "discord":     "com.discord",
        "zoom":        "us.zoom.videomeetings",
        "netflix":     "com.netflix.mediaclient",
        "twitter":     "com.twitter.android",
        "x":           "com.twitter.android",
        "settings":    "com.android.settings",
        "calculator":  "com.samsung.android.calculator",
        "camera":      "com.sec.android.app.camera",
        "gallery":     "com.sec.android.gallery3d",
        "calendar":    "com.samsung.android.calendar",
        "clock":       "com.samsung.android.clock",
        "contacts":    "com.samsung.android.contacts",
        "messages":    "com.samsung.android.messaging",
        "phone":       "com.samsung.android.dialer",
        "dialer":      "com.samsung.android.dialer",
        "browser":     "com.sec.android.app.sbrowser",
        "samsung browser": "com.sec.android.app.sbrowser",
        "files":       "com.sec.android.app.myfiles",
        "my files":    "com.sec.android.app.myfiles",
        "play store":  "com.android.vending",
        "store":       "com.android.vending",
        "music":       "com.samsung.android.music",
        "muso":        "com.muso.musicplayer",
        "termux":      "com.termux",
        "drive":       "com.google.android.apps.docs",
        "docs":        "com.google.android.apps.docs.editors.docs",
        "sheets":      "com.google.android.apps.docs.editors.sheets",
        "meet":        "com.google.android.apps.meetings",
        "photos":      "com.google.android.apps.photos",
        "keep":        "com.google.android.keep",
        "pay":         "com.samsung.android.spay",
    }

    query_lower = query.lower().strip()

    # Fast-path: exact keyword match
    for keyword, pkg in KNOWN_PACKAGES.items():
        if keyword in query_lower or query_lower in keyword:
            print(f"{COLOR_GRAY}[Known package hit: {pkg}]{COLOR_RESET}")
            return f"{pkg} → {pkg}"

    # Fallback: scan cmd package list and match against package segments
    try:
        result = subprocess.run(
            ["cmd", "package", "list", "packages"],
            capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL
        )
        all_packages = [
            line.replace("package:", "").strip()
            for line in result.stdout.splitlines()
            if line.startswith("package:")
        ]

        query_norm = query_lower.replace(" ", "").replace("-", "")
        matches = []
        for pkg in all_packages:
            pkg_segments = pkg.lower().split(".")
            pkg_flat     = pkg.lower().replace(".", "")
            if any(query_norm in seg for seg in pkg_segments) or query_norm in pkg_flat:
                matches.append(pkg)

        if not matches:
            return f"Error: Could not find any launchable app registry entries matching '{query}'."

        return "\n".join(f"{p} → {p}" for p in matches[:10])

    except subprocess.TimeoutExpired:
        return "Error: Package list query timed out."
    except Exception as e:
        return f"Error searching launcher matrix: {e}"
