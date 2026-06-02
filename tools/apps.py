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

def open_app(package_name: str) -> str:
    """Launches an app using target-explicit component selection checking via -n."""
    if " → " in package_name:
        package_name = package_name.split(" → ")[-1].strip()

    package_name = package_name.strip()
    activity_cache = _load_activity_cache()

    # Hit 1: Explicitly Saved Cache Match
    if package_name in activity_cache:
        target_component = f"{package_name}/{activity_cache[package_name]}"
        result = subprocess.run(["am", "start", "-n", target_component], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        output = (result.stdout + result.stderr).strip()
        if "Error" not in output and "Exception" not in output and "unable to resolve" not in output.lower():
            return f"Opened {package_name} via cached structural entry point."

    # Hit 2: Pattern Brute-Force Probing Loop
    print(f"{COLOR_GRAY}[Probing activity matrix for execution paths inside '{package_name}'...]{COLOR_RESET}")
    
    patterns = [
        "MainActivity",
        "Main",
        "SplashActivity",
        "HomeActivity",
        "LauncherActivity",
        "app.MainActivity",
        "app.TermuxActivity",
        "ui.MainActivity",
        "ui.LauncherActivity"
    ]

    for suffix in patterns:
        # Test 1: Absolute layout path structure
        candidate = f"{package_name}.{suffix}" if not suffix.startswith(package_name) else suffix
        print(f"{COLOR_GRAY}[Probing Component: {package_name}/{candidate}]{COLOR_RESET}", end="\r")
        
        res = subprocess.run(["am", "start", "-n", f"{package_name}/{candidate}"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        out = (res.stdout + res.stderr).strip()
        
        if "Error" not in out and "Exception" not in out and "unable to resolve" not in out.lower():
            activity_cache[package_name] = candidate
            _save_activity_cache(activity_cache)
            return f"Successfully opened {package_name} using matching pattern class: {candidate}"
        
        # Test 2: Inverted short class context binding
        if "." in suffix:
            short_candidate = f".{suffix.split('.')[-1]}"
            res = subprocess.run(["am", "start", "-n", f"{package_name}/{short_candidate}"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
            out = (res.stdout + res.stderr).strip()
            if "Error" not in out and "Exception" not in out and "unable to resolve" not in out.lower():
                activity_cache[package_name] = short_candidate
                _save_activity_cache(activity_cache)
                return f"Successfully opened {package_name} using short pattern class: {short_candidate}"

    return f"Failed to execute structural launch mapping on {package_name}. Component configuration unresolvable."

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
