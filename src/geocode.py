"""Batch geocode property addresses using Nominatim (OpenStreetMap).

Geocodes addresses at build time and caches results in data/geocode_cache.json.
Only new/uncached addresses are geocoded on each run.
"""

import json
import os
import re
import time
import sys

from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "geocode_cache.json")
PROPERTIES_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "properties.json")

# Default center: KL
DEFAULT_LAT = 3.1390
DEFAULT_LNG = 101.6869


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def extract_postcode(address):
    m = re.search(r"\b(\d{5})\b", address)
    return m.group(1) if m else None


def extract_state(address):
    addr_lower = address.lower()
    for state in [
        "Kuala Lumpur", "Selangor", "Johor", "Penang", "Perak", "Kedah",
        "Kelantan", "Terengganu", "Pahang", "Negeri Sembilan",
        "Melaka", "Sabah", "Sarawak", "Putrajaya", "Labuan",
    ]:
        if state.lower() in addr_lower:
            return state
    return "Malaysia"


def geocode_address(geocoder, address):
    """Try geocoding with fallback chain: full → street+postcode → postcode+state."""
    # Attempt 1: Full address
    try:
        loc = geocoder(address + ", Malaysia")
        if loc:
            return loc.latitude, loc.longitude, "full"
    except Exception:
        pass

    # Attempt 2: Postcode + state
    postcode = extract_postcode(address)
    state = extract_state(address)
    if postcode:
        try:
            loc = geocoder(f"{postcode}, {state}, Malaysia")
            if loc:
                return loc.latitude, loc.longitude, "postcode"
        except Exception:
            pass

    # Attempt 3: State only
    try:
        loc = geocoder(f"{state}, Malaysia")
        if loc:
            return loc.latitude, loc.longitude, "state"
    except Exception:
        pass

    return DEFAULT_LAT, DEFAULT_LNG, "default"


def main():
    with open(PROPERTIES_FILE, "r") as f:
        properties = json.load(f)

    # Collect unique addresses from active (non-expired) properties
    addresses = set()
    for p in properties.values():
        if p.get("expired"):
            continue
        addr = (p.get("header_full") or "").strip()
        if addr and len(addr) > 5:
            addresses.add(addr)

    print(f"  Total unique active addresses: {len(addresses)}")

    cache = load_cache()
    uncached = [a for a in addresses if a not in cache]

    if not uncached:
        print("  All addresses already geocoded (cache hit)")
        save_cache(cache)
        return

    print(f"  Need to geocode: {len(uncached)} new addresses")

    geolocator = Nominatim(user_agent="lelongtips-property-monitor/1.0")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1)

    success = 0
    failed = 0
    for i, addr in enumerate(uncached):
        lat, lng, quality = geocode_address(geocode, addr)
        cache[addr] = {"lat": lat, "lng": lng, "q": quality}
        if quality != "default":
            success += 1
        else:
            failed += 1

        if (i + 1) % 50 == 0 or i == len(uncached) - 1:
            print(f"  Progress: {i+1}/{len(uncached)} ({success} ok, {failed} default)")
            save_cache(cache)  # Save periodically

    save_cache(cache)
    print(f"  Geocoding complete: {success} resolved, {failed} defaulted")


if __name__ == "__main__":
    main()
