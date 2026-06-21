import subprocess
import json
import requests
import math
import re
from jarvis.config import COLOR_GRAY, COLOR_RESET

from bs4 import BeautifulSoup

def deep_read(url: str):
    """Reads and extracts the main text content from a webpage URL for deep research."""
    print(f"{COLOR_GRAY}[Deep reading {url}...]{COLOR_RESET}", end="\r")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return f"Error: Could not access page (Status {r.status_code})"
        
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Remove script, style, nav, footer to get clean content
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()
            
        # Focus on main content areas if they exist
        main_content = soup.find('main') or soup.find('article') or soup.find('div', class_=re.compile(r'content|main|body', re.I)) or soup
        
        text = main_content.get_text(separator='\n')
        
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        # Return a generous chunk for the AI to process (limit to 6000 chars to avoid context blowup)
        return f"Content of {url}:\n\n" + text[:6000]
    except Exception as e:
        return f"Error reading page: {e}"

def _haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def web_search(query: str):
    """Searches the internet via DuckDuckGo (Resilient Termux version)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    def fetch_results(search_url):
        try:
            r = requests.get(search_url, headers=headers, timeout=12)
            if r.status_code != 200:
                return []
            
            # Find result links and snippets
            # DuckDuckGo HTML format: <a class="result__a" href="URL">Title</a> ... <a class="result__snippet">Snippet</a>
            items = re.findall(r'class="result__a"[^>]*href="(.*?)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>', r.text, re.DOTALL)
            
            parsed = []
            for u_raw, t_raw, s_raw in items:
                u = u_raw.strip()
                # Handle relative URLs if any (though DDG usually provides full ones)
                if u.startswith('//'): u = 'https:' + u
                
                t = re.sub(r'<[^>]+>', '', t_raw).strip()
                s = re.sub(r'<[^>]+>', '', s_raw).strip()
                if t and s:
                    parsed.append(f"- {t}\n  URL: {u}\n  {s}")
                if len(parsed) >= 5:
                    break
            return parsed
        except Exception:
            return []

    print(f"{COLOR_GRAY}[Searching the web for '{query}'...]{COLOR_RESET}", end="\r")
    
    # Try with news filter first if keywords present
    news_keywords = ["news", "latest", "recent", "today", "updates"]
    is_news = any(word in query.lower() for word in news_keywords)
    
    results = []
    if is_news:
        results = fetch_results(f"https://html.duckduckgo.com/html/?q={query}&df=w")
    
    # Fallback to general search if news is empty or not requested
    if not results:
        results = fetch_results(f"https://html.duckduckgo.com/html/?q={query}")

    if not results:
        return f"I couldn't find any search results for '{query}'. Please try a different wording."

    header = "Latest Updates" if is_news else "Search Results"
    return f"{header} for '{query}':\n\n" + "\n\n".join(results)

def open_url(url: str):
    subprocess.run(["termux-open-url", url], stdin=subprocess.DEVNULL)
    return f"Opened URL: {url}"

def get_wifi_info():
    result = subprocess.run(["termux-wifi-connectioninfo"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def set_wifi(enabled):
    """Enables or disables WiFi. Handles both bool and string 'true'/'false'."""
    if isinstance(enabled, str):
        is_on = enabled.lower() in ["true", "on", "yes", "1"]
    else:
        is_on = bool(enabled)
        
    status = "true" if is_on else "false"
    subprocess.run(["termux-wifi-enable", status], stdin=subprocess.DEVNULL)
    return f"WiFi {'enabled' if is_on else 'disabled'}."

def scan_wifi():
    result = subprocess.run(["termux-wifi-scaninfo"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def _fetch_coordinates(provider: str, timeout: int) -> dict | None:
    try:
        # Note: 'once' might return cached results if the system hasn't updated recently.
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
        headers = {"User-Agent": "TermuxAIAssistant/1.0"}
        r = requests.get(overpass_url, params={'data': overpass_query}, headers=headers, timeout=15)
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
    acc = loc_data.get("accuracy", "?")

    # Log the baseline location to help debug "cached" or "wrong" distance issues
    header = f"Search Basis (Coords used for distance): {lat}, {lon} (Accuracy: {acc}m)\n"

    results = []

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
            seen = set()
            for item in items:
                name = item.get("display_name", "").split(",")[0].strip()
                if not name or name.lower() in seen:
                    continue
                seen.add(name.lower())
                i_lat = float(item["lat"])
                i_lon = float(item["lon"])
                dist_km = _haversine_distance(lat, lon, i_lat, i_lon)
                results.append({"name": name, "dist_val": dist_km, "dist_str": f"{dist_km:.2f}km"})
    except Exception:
        pass

    # --- Strategy 2: Overpass Fallback ---
    if not results:
        radius = 10000
        print(f"{COLOR_GRAY}[Nominatim empty, trying Overpass for '{query}'...]{COLOR_RESET}", end="\r")
        try:
            overpass_url = "https://overpass-api.de/api/interpreter"
            if "hospital" in query.lower():
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
                for e in elements:
                    tags = e.get("tags", {})
                    name = tags.get("name") or tags.get("amenity") or tags.get("shop") or tags.get("official_name")
                    if name:
                        e_lat = e.get("lat") or e.get("center", {}).get("lat")
                        e_lon = e.get("lon") or e.get("center", {}).get("lon")
                        dist_val = 999
                        dist_str = "?"
                        if e_lat and e_lon:
                            dist_km = _haversine_distance(lat, lon, e_lat, e_lon)
                            dist_val = dist_km
                            dist_str = f"{dist_km:.2f}km"
                        results.append({"name": name, "dist_val": dist_val, "dist_str": dist_str})
        except Exception as e:
            if not results:
                return header + f"Error searching for nearby places: {str(e)}"

    if not results:
        return header + f"No results found for '{query}' within 10km of your location."
    
    # Sort by distance and deduplicate
    results.sort(key=lambda x: x["dist_val"])
    unique_results = []
    seen = set()
    for r in results:
        if r["name"].lower() not in seen:
            unique_results.append(f"- {r['name']} ({r['dist_str']})")
            seen.add(r["name"].lower())
    
    return header + f"Found {len(unique_results)} results for '{query}' nearby (sorted by distance):\n" + "\n".join(unique_results[:10])

def get_device_info():
    result = subprocess.run(["termux-telephony-deviceinfo"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()

def get_cell_info():
    result = subprocess.run(["termux-telephony-cellinfo"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return result.stdout.strip()
