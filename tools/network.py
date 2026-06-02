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
            params={
                "lat": lat,
                "lon": lon,
                "format": "jsonv2",
                "zoom": 18,
                "addressdetails": 1
            },
            headers={"User-Agent": "TermuxAIAssistant/1.0"},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            # Try to get a specific name (building, school, shop) or the full display name
            address_parts = data.get("address", {})
            landmark = address_parts.get("amenity") or address_parts.get("building") or address_parts.get("shop") or address_parts.get("school")
            if landmark:
                return f"{landmark}, {data.get('display_name')}"
            return data.get("display_name")
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        pass
    return None

def _find_nearby_landmarks(lat: float, lon: float, radius: int = 500) -> list:
    """Uses Overpass API to find schools, churches, and other points of interest nearby."""
    try:
        overpass_url = "https://overpass-api.de/api/interpreter"
        # Search for landmarks within given radius
        overpass_query = f"""
        [out:json][timeout:15];
        (
          node["amenity"](around:{radius},{lat},{lon});
          node["building"](around:{radius},{lat},{lon});
          node["shop"](around:{radius},{lat},{lon});
          way["amenity"](around:{radius},{lat},{lon});
          way["building"](around:{radius},{lat},{lon});
          way["shop"](around:{radius},{lat},{lon});
        );
        out body;
        """
        r = requests.get(overpass_url, params={'data': overpass_query}, timeout=15)
        if r.status_code == 200:
            elements = r.json().get("elements", [])
            landmarks = []
            for e in elements:
                tags = e.get("tags", {})
                name = tags.get("name")
                if name:
                    landmarks.append(name)
            return list(set(landmarks))[:5]  # Top 5 unique landmarks
    except Exception:
        pass
    return []

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
    landmarks = _find_nearby_landmarks(lat, lon, radius=500)
    
    provider_label = "GPS" if provider_used == "gps" else "Network (indoor estimate)"
    maps_url = f"https://maps.google.com/?q={lat},{lon}"
    
    output = []
    output.append(f"Coordinates: Latitude {lat}, Longitude {lon}")
    output.append(f"Accuracy: {acc} meters (via {provider_label})")
    
    if address:
        output.append(f"Address: {address}")
    
    if landmarks:
        output.append(f"Nearby landmarks: {', '.join(landmarks)}")
    else:
        output.append("Nearby landmarks: None found within 500m.")
        
    output.append(f"Maps: {maps_url}")
    
    return "\n".join(output)

def search_nearby(query: str):
    """Searches for specific places (e.g., 'hospital', 'pharmacy', 'restaurant') nearby."""
    # First get current coordinates
    print(f"{COLOR_GRAY}[Getting current location...]{COLOR_RESET}", end="\r")
    loc_data = _fetch_coordinates("gps", timeout=20)
    if loc_data is None:
        loc_data = _fetch_coordinates("network", timeout=10)
    
    if loc_data is None:
        return "Error: Could not determine location to perform nearby search."
    
    lat = loc_data["latitude"]
    lon = loc_data["longitude"]

    # --- Strategy 1: Nominatim (fast, ~1-2s) ---
    print(f"{COLOR_GRAY}[Searching via Nominatim for '{query}'...]{COLOR_RESET}", end="\r")
    try:
        delta = 0.09  # ~10km bounding box
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": query,
                "format": "jsonv2",
                "limit": 10,
                "viewbox": f"{lon-delta},{lat+delta},{lon+delta},{lat-delta}",
                "bounded": 1,
                "addressdetails": 0,
            },
            headers={"User-Agent": "TermuxAIAssistant/1.0"},
            timeout=12,
        )
        if r.status_code == 200:
            items = r.json()
            if items:
                results = []
                seen = set()
                for item in items:
                    name = item.get("display_name", "").split(",")[0].strip()
                    if not name or name.lower() in seen:
                        continue
                    seen.add(name.lower())
                    i_lat = float(item["lat"])
                    i_lon = float(item["lon"])
                    d_lat = (i_lat - lat) * 111
                    d_lon = (i_lon - lon) * 111 * 0.98
                    dist_km = (d_lat**2 + d_lon**2)**0.5
                    results.append({"name": name, "dist_val": dist_km, "dist_str": f"{dist_km:.1f}km"})
                
                if results:
                    results.sort(key=lambda x: x["dist_val"])
                    unique_results = [f"- {r['name']} ({r['dist_str']})" for r in results]
                    return f"Found {len(unique_results)} results for '{query}' nearby (via Nominatim):\n" + "\n".join(unique_results[:10])
    except Exception:
        pass

    # --- Strategy 2: Overpass (Comprehensive fallback, ~10-20s) ---
    radius = 10000
    print(f"{COLOR_GRAY}[Nominatim empty, trying Overpass within 10km...]{COLOR_RESET}", end="\r")
    
    try:
        overpass_url = "https://overpass-api.de/api/interpreter"
        
        # Use more efficient specific keys for common searches
        if "hospital" in query.lower():
            # Specifically search for medical amenities which is much faster than regex
            overpass_query = f"""
            [out:json][timeout:30];
            (
              node(around:{radius},{lat},{lon})["amenity"~"hospital|clinic|doctors|health_post",i];
              way(around:{radius},{lat},{lon})["amenity"~"hospital|clinic|doctors|health_post",i];
              node(around:{radius},{lat},{lon})["name"~"hospital|clinic|medical|health",i];
              way(around:{radius},{lat},{lon})["name"~"hospital|clinic|medical|health",i];
            );
            out center;
            """
        else:
            # For general queries, use a slightly more focused regex
            overpass_query = f"""
            [out:json][timeout:30];
            (
              node(around:{radius},{lat},{lon})["amenity"~"{query}",i];
              node(around:{radius},{lat},{lon})["shop"~"{query}",i];
              node(around:{radius},{lat},{lon})["name"~"{query}",i];
              way(around:{radius},{lat},{lon})["amenity"~"{query}",i];
              way(around:{radius},{lat},{lon})["shop"~"{query}",i];
              way(around:{radius},{lat},{lon})["name"~"{query}",i];
            );
            out center;
            """
        
        headers = {"User-Agent": "TermuxAIAssistant/1.0"}
        r = requests.get(overpass_url, params={'data': overpass_query}, headers=headers, timeout=30)
        if r.status_code == 200:
            elements = r.json().get("elements", [])
            results = []
            for e in elements:
                tags = e.get("tags", {})
                name = tags.get("name") or tags.get("amenity") or tags.get("shop") or tags.get("official_name")
                if name:
                    # Calculate approximate distance
                    e_lat = e.get("lat") or e.get("center", {}).get("lat")
                    e_lon = e.get("lon") or e.get("center", {}).get("lon")
                    dist_val = 999
                    dist_str = "?"
                    if e_lat and e_lon:
                        d_lat = (e_lat - lat) * 111
                        d_lon = (e_lon - lon) * 111 * 0.98
                        dist_km = (d_lat**2 + d_lon**2)**0.5
                        dist_val = dist_km
                        dist_str = f"{dist_km:.1f}km"
                    
                    results.append({"name": name, "dist_val": dist_val, "dist_str": dist_str})
            
            if not results:
                return f"No results found for '{query}' within 10km of your location."
            
            # Sort by distance
            results.sort(key=lambda x: x["dist_val"])
            unique_results = []
            seen = set()
            for r in results:
                if r["name"].lower() not in seen:
                    unique_results.append(f"- {r['name']} ({r['dist_str']})")
                    seen.add(r["name"].lower())
            
            return f"Found {len(unique_results)} results for '{query}' nearby (via Overpass):\n" + "\n".join(unique_results[:10])
    except Exception as e:
        return f"Error searching for nearby places: {str(e)}"
    return "No results found."

def get_device_info():
    result = subprocess.run(["termux-telephony-deviceinfo"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def get_cell_info():
    result = subprocess.run(["termux-telephony-cellinfo"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()
