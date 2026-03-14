#!/usr/bin/env python3
"""Reprocess all raw scrape snapshots to rebuild the properties database.

This script reads every snapshot in data/snapshots/ in chronological order
and rebuilds properties.json from scratch. Because it starts fresh each
time, fixing a matching bug means you just re-run this script — no data
is ever lost since the raw snapshots are the source of truth.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path


DATA_DIR = Path(os.path.dirname(__file__)).parent / "data"


def normalize_text(s):
    if not s:
        return ""
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def normalize_size(s):
    if not s:
        return ""
    s = s.lower()
    digits = re.findall(r"\d+", s)
    num = "".join(digits) if digits else ""
    unit = "sqft" if "sq.ft" in s or "sqft" in s else ""
    return f"{num}{unit}"


def generate_stable_key(prop):
    """Generate a unique identity key: title|location|size|address."""
    title = normalize_text(prop.get("title", ""))
    location = normalize_text(prop.get("location", ""))
    size = normalize_size(prop.get("size", ""))
    address = normalize_text(prop.get("header_full", "") or "")
    return f"{title}|{location}|{size}|{address}"


def create_property_id(title, location, size, address=""):
    """Create a stable property ID from title+location+size+address."""
    clean_title = re.sub(r"[^\w\s]", "", title)
    clean_location = re.sub(r"[^\w\s]", "", location)
    clean_size = re.sub(r"[^\w\s]", "", size)
    clean_address = re.sub(r"[^\w\s]", "", address or "")
    base = f"{clean_title}_{clean_location}_{clean_size}_{clean_address}".strip()
    base = re.sub(r"\s+", "_", base).lower()
    if not base:
        base = "property"
    return base[:150]


def load_snapshots(data_dir):
    """Load all snapshots sorted chronologically."""
    snapshots_dir = data_dir / "snapshots"
    if not snapshots_dir.exists():
        return []

    snapshot_files = sorted(snapshots_dir.glob("*.json"))
    snapshots = []
    for path in snapshot_files:
        try:
            with open(path) as f:
                data = json.load(f)
            snapshots.append(data)
            print(f"  Loaded {path.name}: {len(data.get('properties', {}))} properties")
        except Exception as e:
            print(f"  Error loading {path.name}: {e}")
    return snapshots


def match_property(prop, database, stable_index, listing_id_index, address_index):
    """Find an existing property in the database that matches this one.

    Returns (existing_id, existing_data) or (None, None).
    """
    sk = generate_stable_key(prop)
    cur_lid = prop.get("listing_id", "")
    cur_addr = normalize_text(prop.get("header_full", "") or "")
    cur_size = normalize_size(prop.get("size", ""))

    # 1) Match by listing_id — validate address matches
    if cur_lid and cur_lid in listing_id_index:
        candidate_id = listing_id_index[cur_lid]
        candidate = database[candidate_id]
        cand_addr = normalize_text(candidate.get("header_full", "") or "")
        if not cur_addr or not cand_addr or cur_addr == cand_addr:
            return candidate_id, candidate

    # 2) Match by stable key (includes address — very reliable)
    if sk in stable_index:
        return stable_index[sk], database[stable_index[sk]]

    # 3) Match by address + size
    if cur_addr and len(cur_addr) > 20 and cur_addr in address_index:
        candidate_id = address_index[cur_addr]
        candidate = database[candidate_id]
        cand_size = normalize_size(candidate.get("size", ""))
        if cur_size and cand_size and cur_size == cand_size:
            return candidate_id, candidate

    return None, None


def reprocess_all(data_dir=None):
    """Rebuild the properties database from all snapshots.

    Returns (database, new_listings_from_latest, changed_from_latest).
    """
    if data_dir is None:
        data_dir = DATA_DIR
    data_dir = Path(data_dir)

    print("Reprocessing all snapshots...")
    snapshots = load_snapshots(data_dir)
    if not snapshots:
        print("  No snapshots found")
        return {}, {}, {}

    database = {}
    stable_index = {}  # stable_key -> property_id
    listing_id_index = {}  # listing_id -> property_id
    address_index = {}  # normalized_address -> property_id

    # Track what changed in the LATEST snapshot (for notifications)
    new_listings = {}
    changed_properties = {}

    for snap_idx, snapshot in enumerate(snapshots):
        is_latest = snap_idx == len(snapshots) - 1
        scan_date = snapshot.get("scan_date", "")
        properties = snapshot.get("properties", {})
        print(f"  Processing {scan_date[:10]}: {len(properties)} properties"
              f"{' (latest)' if is_latest else ''}")

        # Reset latest-scan tracking
        if is_latest:
            new_listings = {}
            changed_properties = {}

        for raw_id, prop in properties.items():
            # Generate stable key and property ID
            sk = generate_stable_key(prop)
            prop_id = create_property_id(
                prop.get("title", ""),
                prop.get("location", ""),
                prop.get("size", ""),
                prop.get("header_full", ""),
            )

            existing_id, existing_data = match_property(
                prop, database, stable_index, listing_id_index, address_index
            )

            if existing_id is None:
                # New property
                database[prop_id] = {
                    **prop,
                    "_stable_key": sk,
                    "first_seen": prop.get("last_updated", scan_date),
                    "price_history": [
                        {
                            "price": prop.get("price", ""),
                            "date": prop.get("last_updated", scan_date),
                            "url": prop.get("listing_url", ""),
                        }
                    ],
                    "auction_date_history": [
                        {
                            "auction_date": prop.get("auction_date", ""),
                            "date": prop.get("last_updated", scan_date),
                        }
                    ],
                }
                stable_index[sk] = prop_id
                lid = prop.get("listing_id", "")
                if lid:
                    listing_id_index[lid] = prop_id
                addr = normalize_text(prop.get("header_full", "") or "")
                if addr and len(addr) > 20:
                    address_index[addr] = prop_id

                if is_latest:
                    new_listings[prop_id] = database[prop_id]
            else:
                # Existing property — check for changes
                changes = []

                if prop.get("price", "") != existing_data.get("price", ""):
                    changes.append({
                        "type": "price_change",
                        "field": "Auction Price",
                        "old_value": existing_data.get("price", ""),
                        "new_value": prop.get("price", ""),
                        "change_date": prop.get("last_updated", scan_date),
                    })
                    if "price_history" not in existing_data:
                        existing_data["price_history"] = []
                    existing_data["price_history"].append({
                        "price": prop.get("price", ""),
                        "date": prop.get("last_updated", scan_date),
                        "url": prop.get("listing_url", ""),
                    })

                if prop.get("auction_date", "") != existing_data.get("auction_date", ""):
                    changes.append({
                        "type": "auction_date_change",
                        "field": "Auction Date",
                        "old_value": existing_data.get("auction_date", ""),
                        "new_value": prop.get("auction_date", ""),
                        "change_date": prop.get("last_updated", scan_date),
                    })
                    if "auction_date_history" not in existing_data:
                        existing_data["auction_date_history"] = []
                    existing_data["auction_date_history"].append({
                        "auction_date": prop.get("auction_date", ""),
                        "date": prop.get("last_updated", scan_date),
                    })

                # Update with latest data but keep first_seen and histories
                first_seen = existing_data.get("first_seen", "")
                ph = existing_data.get("price_history", [])
                adh = existing_data.get("auction_date_history", [])
                old_sk = existing_data.get("_stable_key", sk)

                existing_data.update(prop)
                existing_data["first_seen"] = first_seen
                existing_data["price_history"] = ph
                existing_data["auction_date_history"] = adh
                existing_data["_stable_key"] = old_sk

                # Update listing_id index
                lid = prop.get("listing_id", "")
                if lid:
                    listing_id_index[lid] = existing_id

                if is_latest and changes:
                    changed_properties[existing_id] = {
                        "property": existing_data,
                        "changes": changes,
                    }

    print(f"  Database rebuilt: {len(database)} unique properties")
    return database, new_listings, changed_properties


if __name__ == "__main__":
    database, new_listings, changed_properties = reprocess_all()

    # Save the rebuilt database
    props_path = DATA_DIR / "properties.json"
    with open(props_path, "w") as f:
        json.dump(database, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(database)} properties to {props_path}")

    # Save changes history
    changes_path = DATA_DIR / "changes.json"
    existing_changes = []
    if changes_path.exists():
        try:
            with open(changes_path) as f:
                existing_changes = json.load(f)
        except Exception:
            pass

    change_records = []
    for pid, cdata in changed_properties.items():
        for c in cdata.get("changes", []):
            change_records.append({
                "property_id": pid,
                "title": cdata["property"].get("title", ""),
                **c,
            })

    entry = {
        "scan_date": datetime.now().isoformat(),
        "new_listings_count": len(new_listings),
        "changed_properties_count": len(changed_properties),
        "new_listing_ids": list(new_listings.keys()),
        "changes": change_records,
    }
    existing_changes.append(entry)
    with open(changes_path, "w") as f:
        json.dump(existing_changes, f, indent=2, ensure_ascii=False)

    # Save daily stats
    stats_path = DATA_DIR / "daily_stats.json"
    stats = {
        "date": datetime.now().isoformat(),
        "total_tracked": len(database),
        "new_listings": len(new_listings),
        "changed_properties": len(changed_properties),
    }
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"New: {len(new_listings)}, Changed: {len(changed_properties)}")
