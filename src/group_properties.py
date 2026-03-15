#!/usr/bin/env python3
"""Strict deduplication of properties.json.

Groups ~60K duplicate entries into unique properties using:
1. listing_id + size (composite key — same building can have many units)
2. Address + size matching (cross-match old entries to lid groups)
3. stable_key (title|location|size|address for remaining entries)

Drops unmatchable junk entries (e.g. "Property Listing P1-3" with no
listing_id, no address, no size).
"""

import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.path.dirname(__file__)).parent / "data"


def normalize_text(s):
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.strip().lower())


def normalize_size(s):
    if not s or s == "Size not specified":
        return ""
    digits = re.findall(r"\d+", s)
    num = "".join(digits) if digits else ""
    unit = "sqft" if ("sq.ft" in s.lower() or "sqft" in s.lower()) else ""
    return f"{num}{unit}"


def normalize_address(s):
    if not s:
        return ""
    s = normalize_text(s)
    s = re.sub(r"\s*,\s*", ", ", s)
    return s


def is_junk_entry(prop):
    """Entries that can't be reliably matched to anything."""
    title = prop.get("title", "")
    lid = prop.get("listing_id", "")
    addr = normalize_address(prop.get("header") or prop.get("header_full") or "")
    size = prop.get("size", "")
    has_size = size and size != "Size not specified"

    if lid:
        return False

    if addr and len(addr) > 20:
        return False

    if title.startswith("Property Listing"):
        return True

    generic_patterns = [
        r"^\d+(\.\d+)?\s+Storey\s+",
        r"^Office\s+(Unit|Lot)$",
        r"^Shop\s+(Lot|Unit)$",
        r"^Warehouse$",
        r"^Factory$",
    ]
    if not has_size:
        for pat in generic_patterns:
            if re.match(pat, title, re.IGNORECASE):
                return True

    return False


def merge_histories(entries):
    """Merge price_history and auction_date_history from multiple entries."""
    price_history = []
    auction_history = []
    seen_prices = set()
    seen_auctions = set()

    for _, p in entries:
        for ph in p.get("price_history", []):
            key = (ph.get("price", ""), ph.get("date", ""))
            if key not in seen_prices:
                seen_prices.add(key)
                price_history.append(ph)

        cur_price = p.get("price", "")
        cur_date = p.get("last_updated", "") or p.get("first_seen", "")
        if cur_price and (cur_price, cur_date) not in seen_prices:
            seen_prices.add((cur_price, cur_date))
            price_history.append({
                "price": cur_price,
                "date": cur_date,
                "url": p.get("listing_url", ""),
            })

        for ah in p.get("auction_date_history", []):
            key = (ah.get("auction_date", ""), ah.get("date", ""))
            if key not in seen_auctions:
                seen_auctions.add(key)
                auction_history.append(ah)

        cur_ad = p.get("auction_date", "")
        if cur_ad and (cur_ad, cur_date) not in seen_auctions:
            seen_auctions.add((cur_ad, cur_date))
            auction_history.append({
                "auction_date": cur_ad,
                "date": cur_date,
            })

    price_history.sort(key=lambda x: x.get("date", ""))
    auction_history.sort(key=lambda x: x.get("date", ""))

    def dedup_consecutive(history, value_key):
        result = []
        last_val = None
        for h in history:
            val = h.get(value_key, "")
            if val != last_val:
                result.append(h)
                last_val = val
        return result

    price_history = dedup_consecutive(price_history, "price")
    auction_history = dedup_consecutive(auction_history, "auction_date")

    return price_history, auction_history


def pick_best_entry(entries):
    """Pick the most complete entry as the canonical one."""
    def score(pid_prop):
        _, p = pid_prop
        s = 0
        if p.get("listing_id"):
            s += 100
        if p.get("header_full") or p.get("header"):
            s += 50
        if p.get("listing_url", "").startswith("https://www.lelongtips.com.my/property/"):
            s += 40
        if p.get("size") and p.get("size") != "Size not specified":
            s += 20
        if p.get("image_url"):
            s += 10
        if p.get("header_short"):
            s += 10
        title = p.get("title", "")
        if title and not title.startswith("Property Listing"):
            s += 30
        return s

    entries.sort(key=score, reverse=True)
    return entries[0]


def create_property_id(prop):
    """Create a clean, stable property ID."""
    title = re.sub(r"[^\w\s]", "", prop.get("title", ""))
    location = re.sub(r"[^\w\s]", "", prop.get("location", ""))
    size = re.sub(r"[^\w\s]", "", prop.get("size", ""))
    base = f"{title}_{location}_{size}".strip()
    base = re.sub(r"\s+", "_", base).lower()
    if not base or base == "__":
        base = "property"
    return base[:120]


def _make_group_key(prop):
    """Create composite grouping key: listing_id + normalized_size.

    The website reuses listing_ids for different units at the same building
    (e.g. 12 different shop lots at Berjaya Times Square share one listing_id
    but have sizes from 689 to 19,999 sq.ft). So listing_id alone is NOT
    enough — we must include size.
    """
    lid = prop.get("listing_id", "")
    size = normalize_size(prop.get("size", ""))
    return f"{lid}|{size}"


def group_properties(input_path=None, output_path=None):
    if input_path is None:
        input_path = DATA_DIR / "properties.json"
    if output_path is None:
        output_path = DATA_DIR / "properties.json"

    with open(input_path) as f:
        raw = json.load(f)

    print(f"Input: {len(raw)} entries")

    # ── Phase 0: Drop junk entries ──────────────────────────────
    junk_count = 0
    clean = {}
    for pid, p in raw.items():
        if is_junk_entry(p):
            junk_count += 1
        else:
            clean[pid] = p
    print(f"Dropped {junk_count} unmatchable junk entries")
    print(f"Remaining: {len(clean)} entries")

    # ── Phase 1: Group by listing_id + size ─────────────────────
    lid_groups = defaultdict(list)       # "listing_id|size" → [(pid, prop)]
    no_lid = []                          # entries without listing_id
    for pid, p in clean.items():
        lid = p.get("listing_id", "")
        if lid:
            gk = _make_group_key(p)
            lid_groups[gk].append((pid, p))
        else:
            no_lid.append((pid, p))

    print(f"\nPhase 1 — listing_id+size grouping:")
    print(f"  {len(lid_groups)} unique groups (from {sum(len(v) for v in lid_groups.values())} entries)")
    print(f"  {len(no_lid)} entries without listing_id")

    # ── Phase 2: Build address+size index from lid groups ───────
    # Map (normalized_address, normalized_size) → group_key
    addr_size_to_gk = {}
    for gk, entries in lid_groups.items():
        for _, p in entries:
            addr = normalize_address(p.get("header") or p.get("header_full") or "")
            size = normalize_size(p.get("size", ""))
            if addr and len(addr) > 20 and size:
                addr_size_to_gk[(addr, size)] = gk

    # Also index by just address for entries without size
    addr_to_gk = {}
    for gk, entries in lid_groups.items():
        for _, p in entries:
            addr = normalize_address(p.get("header") or p.get("header_full") or "")
            size = normalize_size(p.get("size", ""))
            if addr and len(addr) > 20:
                addr_to_gk[addr] = gk

    print(f"\nPhase 2 — address cross-matching:")
    print(f"  {len(addr_size_to_gk)} unique (address, size) pairs from lid groups")

    cross_matched = 0
    still_no_lid = []
    for pid, p in no_lid:
        addr = normalize_address(p.get("header") or p.get("header_full") or "")
        size = normalize_size(p.get("size", ""))
        matched = False

        # Prefer address+size match (more specific)
        if addr and size and (addr, size) in addr_size_to_gk:
            gk = addr_size_to_gk[(addr, size)]
            lid_groups[gk].append((pid, p))
            cross_matched += 1
            matched = True
        # Fall back to address-only match if no-lid entry has no size
        elif addr and not size and addr in addr_to_gk:
            gk = addr_to_gk[addr]
            lid_groups[gk].append((pid, p))
            cross_matched += 1
            matched = True

        if not matched:
            still_no_lid.append((pid, p))

    print(f"  Cross-matched {cross_matched} entries to lid groups by address+size")
    print(f"  Remaining unmatched: {len(still_no_lid)}")

    # ── Phase 3: Group remaining by stable_key ──────────────────
    sk_groups = defaultdict(list)
    for pid, p in still_no_lid:
        title = normalize_text(p.get("title", ""))
        location = normalize_text(p.get("location", ""))
        size = normalize_size(p.get("size", ""))
        addr = normalize_address(p.get("header") or p.get("header_full") or "")
        sk = f"{title}|{location}|{size}|{addr}"
        sk_groups[sk].append((pid, p))

    print(f"\nPhase 3 — stable_key grouping:")
    print(f"  {len(sk_groups)} unique stable_keys (from {len(still_no_lid)} entries)")

    # ── Phase 4: Try to match sk groups to lid groups by title+size ─
    lid_title_size = {}  # (norm_title, norm_size) → group_key
    for gk, entries in lid_groups.items():
        best_pid, best_prop = pick_best_entry(list(entries))
        title = normalize_text(best_prop.get("title", ""))
        size = normalize_size(best_prop.get("size", ""))
        if title and not title.startswith("property listing") and size:
            key = (title, size)
            if key not in lid_title_size:
                lid_title_size[key] = gk

    cross_matched_ts = 0
    final_sk_groups = {}
    for sk, entries in sk_groups.items():
        best_pid, best_prop = pick_best_entry(list(entries))
        title = normalize_text(best_prop.get("title", ""))
        size = normalize_size(best_prop.get("size", ""))
        key = (title, size)
        if key in lid_title_size:
            gk = lid_title_size[key]
            lid_groups[gk].extend(entries)
            cross_matched_ts += len(entries)
        else:
            final_sk_groups[sk] = entries

    print(f"\nPhase 4 — title+size cross-matching:")
    print(f"  Cross-matched {cross_matched_ts} entries to lid groups")
    print(f"  Final independent stable_key groups: {len(final_sk_groups)}")

    # ── Phase 5: Build final database ───────────────────────────
    database = {}

    def add_group_to_database(entries):
        best_pid, best_prop = pick_best_entry(entries)
        price_history, auction_history = merge_histories(entries)

        first_seen = min(
            (p.get("first_seen", "") or p.get("last_updated", "") for _, p in entries),
            default=""
        )
        last_updated = max(
            (p.get("last_updated", "") or p.get("first_seen", "") for _, p in entries),
            default=""
        )

        prop_id = create_property_id(best_prop)
        base_id = prop_id
        counter = 2
        while prop_id in database:
            prop_id = f"{base_id}_{counter}"
            counter += 1

        title = normalize_text(best_prop.get("title", ""))
        location = normalize_text(best_prop.get("location", ""))
        size = normalize_size(best_prop.get("size", ""))
        addr = normalize_address(
            best_prop.get("header_full", "") or best_prop.get("header", "") or ""
        )
        sk = f"{title}|{location}|{size}|{addr}"

        database[prop_id] = {
            **best_prop,
            "_stable_key": sk,
            "first_seen": first_seen,
            "last_updated": last_updated,
            "price_history": price_history,
            "auction_date_history": auction_history,
        }

    total_lid = len(lid_groups)
    total_sk = len(final_sk_groups)

    for entries in lid_groups.values():
        add_group_to_database(entries)

    for entries in final_sk_groups.values():
        add_group_to_database(entries)

    print(f"\n{'=' * 50}")
    print(f"RESULT: {len(database)} unique properties")
    print(f"  From listing_id+size groups: {total_lid}")
    print(f"  From stable_key groups: {total_sk}")
    print(f"  Reduction: {len(raw)} -> {len(database)} "
          f"({100 - len(database) / len(raw) * 100:.1f}% reduction)")

    now = datetime.now()
    active = sum(
        1 for p in database.values()
        if _parse_date(p.get("auction_date", ""))
        and _parse_date(p.get("auction_date", "")) >= now
    )
    expired = len(database) - active
    print(f"  Active (future auction): {active}")
    print(f"  Expired (past auction): {expired}")

    with open(output_path, "w") as f:
        json.dump(database, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {output_path}")

    return database


def _parse_date(s):
    s = re.sub(r"\s*\(.*?\)\s*", " ", s).strip()
    for fmt in ["%d %b %Y", "%d %B %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None


if __name__ == "__main__":
    group_properties()
