#!/usr/bin/env python3
"""Generate a mobile-responsive HTML dashboard from scrape data."""

import json
import os
import re
import html
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")


def load_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def esc(text):
    return html.escape(str(text)) if text else ""


def format_price(price_str):
    """Extract numeric value for sorting."""
    m = re.search(r"[\d,]+", str(price_str))
    if m:
        return int(m.group().replace(",", ""))
    return 0


def normalize_location(loc):
    """Clean noisy location strings."""
    if not loc:
        return "KL/Selangor"
    # Strip everything from first [ or ] onward
    loc = re.split(r"[\[\]]", loc)[0].strip()
    # Strip trailing punctuation/semicolons and noise
    loc = re.sub(r"[;,\s]+$", "", loc)
    # Truncate at common noise patterns
    loc = re.split(r"\s+with\s+", loc, flags=re.IGNORECASE)[0].strip()
    loc = re.split(r"\s*&\s+(?!Selangor)", loc)[0].strip()
    # Normalize semicolons to just first part
    if ";" in loc:
        loc = loc.split(";")[0].strip()
    if not loc or len(loc) < 3:
        return "KL/Selangor"
    return loc


def parse_auction_date(ad_str):
    """Parse auction date string, return datetime or None."""
    m = re.match(r"(\d{1,2})\s+(\w{3})\s+(\d{4})", ad_str)
    if m:
        try:
            return datetime.strptime(
                f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %b %Y"
            )
        except Exception:
            pass
    return None


def get_active_properties(properties):
    """Filter to only active listings (future auction dates)."""
    now = datetime.now()
    active = {}
    for pid, p in properties.items():
        ad = p.get("auction_date", "")
        d = parse_auction_date(ad)
        if d and d >= now:
            active[pid] = p
    return active


def extract_price_value(price_str):
    """Extract numeric value from a price string like 'RM1,234,000'."""
    m = re.search(r"[\d,]+", str(price_str))
    if m:
        return int(m.group().replace(",", ""))
    return 0


def is_valid_price(price_str):
    """Check if a price string looks like a real property price (>= RM10,000)."""
    return extract_price_value(price_str) >= 10000


def trim_property(prop, geocode_cache=None, scheme_cache=None):
    """Reduce property to essential fields with short keys."""
    ph = prop.get("price_history", [])

    # Filter out corrupted price entries and keep last 5 valid ones
    listing_url = prop.get("listing_url", "")
    valid_ph = []
    for h in ph:
        price = h.get("price", "")
        if is_valid_price(price):
            entry = {
                "p": price,
                "d": h.get("date", "")[:10],
            }
            # Use the entry's own URL, or fall back to the property's current URL
            url = h.get("url", "") or listing_url
            if url:
                entry["u"] = url
            valid_ph.append(entry)
    trimmed_ph = valid_ph[-5:]

    # Use current price if valid, otherwise fall back to latest valid from history.
    # If no valid history exists, use price_value (monitor.py already multiplied
    # truncated prices by 1000) and format it.
    current_price = prop.get("price", "")
    current_pv = prop.get("price_value", 0)
    if not is_valid_price(current_price):
        if valid_ph:
            current_price = valid_ph[-1]["p"]
            current_pv = extract_price_value(current_price)
        elif current_pv >= 10000:
            current_price = f"RM{current_pv:,}"

    # Build combined auction history from price + auction_date histories
    # Each entry represents a snapshot: date seen, price, auction date, url
    adh = prop.get("auction_date_history", [])
    # Merge all events by date into snapshots
    snapshots = {}  # date -> {price, auction_date, url}
    for h in ph:
        d = h.get("date", "")[:10]
        if not d:
            continue
        if d not in snapshots:
            snapshots[d] = {}
        price = h.get("price", "")
        if is_valid_price(price):
            snapshots[d]["p"] = price
        snapshots[d]["u"] = h.get("url", "") or listing_url
    for h in adh:
        d = h.get("date", "")[:10]
        if not d:
            continue
        if d not in snapshots:
            snapshots[d] = {}
        ad_val = h.get("auction_date", "")
        # Strip day-of-week in parens
        ad_clean = re.split(r"\s*\(", ad_val)[0].strip()
        if ad_clean:
            snapshots[d]["ad"] = ad_clean
        if "u" not in snapshots[d]:
            snapshots[d]["u"] = listing_url

    # Build sorted history, carrying forward last known values
    history = []
    last_price = ""
    last_ad = ""
    for d in sorted(snapshots.keys()):
        s = snapshots[d]
        if "p" in s:
            last_price = s["p"]
        if "ad" in s:
            last_ad = s["ad"]
        entry = {"d": d}
        if last_price:
            entry["p"] = last_price
        if last_ad:
            entry["ad"] = last_ad
        url = s.get("u", "")
        if url:
            entry["u"] = url
        history.append(entry)

    # Deduplicate consecutive identical entries (same price + auction date)
    deduped = []
    for h in history:
        if deduped and h.get("p") == deduped[-1].get("p") and h.get("ad") == deduped[-1].get("ad"):
            continue
        deduped.append(h)
    # Keep last 10
    trimmed_hist = deduped[-10:]

    result = {
        "t": prop.get("title", ""),
        "p": current_price,
        "pv": current_pv,
        "l": normalize_location(prop.get("location", "")),
        "s": prop.get("size", ""),
        "ad": re.split(r"\s*\(", prop.get("auction_date", ""))[0].strip(),
        "pt": prop.get("property_type", ""),
        "d": prop.get("discount", ""),
        "u": prop.get("listing_url", ""),
        "img": prop.get("image_url", ""),
        "a": (prop.get("header_full", "") or "")[:120],
        "ph": trimmed_ph,
        "hist": trimmed_hist if len(trimmed_hist) > 1 else [],
    }
    addr = (prop.get("header_full") or "").strip()
    # Add geocode if available
    if geocode_cache:
        geo = geocode_cache.get(addr)
        if geo and geo.get("q") != "default":
            result["lat"] = round(geo["lat"], 5)
            result["lng"] = round(geo["lng"], 5)
    # Add scheme/project name: prefer AI-extracted, fallback to header_short
    scheme = ""
    if scheme_cache:
        scheme = scheme_cache.get(addr, "")
    if not scheme:
        scheme = prop.get("scheme_name", "")
    if not scheme:
        hs = prop.get("header_short", "")
        if "," in hs:
            scheme = hs.rsplit(",", 1)[0].strip()
    if scheme:
        result["sn"] = scheme
    return result


def write_data_files(properties, changes_history, daily_stats):
    """Write separate JSON data files for the dashboard."""
    data_dir = os.path.join(DOCS_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)

    # Load geocode cache if available
    geocode_cache_path = os.path.join(DATA_DIR, "geocode_cache.json")
    geocode_cache = None
    if os.path.exists(geocode_cache_path):
        with open(geocode_cache_path, "r") as f:
            geocode_cache = json.load(f)

    # Load scheme name cache if available
    scheme_cache_path = os.path.join(DATA_DIR, "scheme_cache.json")
    scheme_cache = None
    if os.path.exists(scheme_cache_path):
        with open(scheme_cache_path, "r") as f:
            scheme_cache = json.load(f)

    active = get_active_properties(properties)

    # active.json - trimmed ALL listings (active + expired for search)
    active_data = {}
    for pid, p in properties.items():
        trimmed = trim_property(p, geocode_cache, scheme_cache)
        # Mark expired listings
        ad = p.get("auction_date", "")
        d = parse_auction_date(ad)
        if d and d < datetime.now():
            trimmed["exp"] = 1
        active_data[pid] = trimmed

    with open(os.path.join(data_dir, "active.json"), "w") as f:
        json.dump(active_data, f, separators=(",", ":"))
    print(f"  active.json: {len(active_data)} properties ({len(active)} active, {len(active_data) - len(active)} expired)")

    # changes.json - latest scan changes
    latest_scan = changes_history[-1] if changes_history else {}
    changes_data = {
        "new_ids": latest_scan.get("new_listing_ids", []),
        "changes": latest_scan.get("changes", []),
        "scan_date": latest_scan.get("scan_date", ""),
    }
    with open(os.path.join(data_dir, "changes.json"), "w") as f:
        json.dump(changes_data, f, separators=(",", ":"))

    # stats.json - dashboard statistics
    scan_history = []
    for entry in changes_history:
        scan_history.append({
            "d": entry.get("scan_date", "")[:10],
            "n": entry.get("new_listings_count", 0),
            "c": entry.get("changed_properties_count", 0),
        })

    # Compute price stats from active listings
    prices = [p.get("price_value", 0) for p in active.values() if p.get("price_value", 0) > 0]
    avg_price = int(sum(prices) / len(prices)) if prices else 0

    # Count properties with price drops
    drop_count = sum(1 for p in active.values() if p.get("discount"))

    # Collect unique types and locations for filters (from all properties)
    types_set = set()
    locs_set = set()
    for p in active_data.values():
        if p.get("pt"):
            types_set.add(p["pt"])
        if p.get("l"):
            locs_set.add(p["l"])

    stats_data = {
        "total_tracked": len(properties),
        "active_count": len(active),
        "new_count": latest_scan.get("new_listings_count", 0),
        "changed_count": latest_scan.get("changed_properties_count", 0),
        "avg_price": avg_price,
        "drop_count": drop_count,
        "scan_date": latest_scan.get("scan_date", ""),
        "prev_scan_date": changes_history[-2].get("scan_date", "") if len(changes_history) >= 2 else "",
        "scan_history": scan_history,
        "types": sorted(types_set),
        "locations": sorted(locs_set),
    }
    with open(os.path.join(data_dir, "stats.json"), "w") as f:
        json.dump(stats_data, f, separators=(",", ":"))

    return stats_data, active_data, changes_data


def generate_page():
    properties = load_json(os.path.join(DATA_DIR, "properties.json")) or {}
    changes_history = load_json(os.path.join(DATA_DIR, "changes.json")) or []
    daily_stats = load_json(os.path.join(DATA_DIR, "daily_stats.json")) or {}

    os.makedirs(DOCS_DIR, exist_ok=True)

    # Write data files
    stats, active_data, changes_data = write_data_files(
        properties, changes_history, daily_stats
    )

    # Format scan date for initial display
    scan_date = stats.get("scan_date", "N/A")
    if scan_date and scan_date != "N/A":
        try:
            dt = datetime.fromisoformat(scan_date)
            scan_date_display = dt.strftime("%d %b %Y, %I:%M %p")
        except Exception:
            scan_date_display = scan_date[:19]
    else:
        scan_date_display = "N/A"

    # Inline JSON data into the HTML
    inline_stats = json.dumps(stats, separators=(",", ":"))
    inline_active = json.dumps(active_data, separators=(",", ":"))
    inline_changes = json.dumps(changes_data, separators=(",", ":"))

    page_html = build_html(stats, scan_date_display,
                           inline_stats, inline_active, inline_changes)

    out_path = os.path.join(DOCS_DIR, "index.html")
    with open(out_path, "w") as f:
        f.write(page_html)
    print(f"Dashboard generated: {out_path}")
    print(f"  Total tracked: {stats['total_tracked']:,}")
    print(f"  Active listings: {stats['active_count']:,}")
    print(f"  New: {stats['new_count']}, Changed: {stats['changed_count']}")


def build_html(stats, scan_date_display, inline_stats, inline_active, inline_changes):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LelongTips Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #F8F9FA;
  --card-bg: #FFFFFF;
  --border: #E5E7EB;
  --text: #111827;
  --text-sec: #4B5563;
  --text-muted: #9CA3AF;
  --accent: #2563EB;
  --accent-light: #EFF6FF;
  --green: #059669;
  --green-light: #ECFDF5;
  --red: #DC2626;
  --red-light: #FEF2F2;
  --orange: #D97706;
  --orange-light: #FFFBEB;
  --purple: #7C3AED;
  --shadow: 0 1px 3px rgba(0,0,0,0.08);
  --shadow-lg: 0 4px 12px rgba(0,0,0,0.12);
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}}
.container {{ max-width: 768px; margin: 0 auto; padding: 16px; }}

/* Header */
header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 0 14px;
  margin-bottom: 16px;
}}
header h1 {{ font-size: 1.3rem; font-weight: 700; color: var(--text); }}
header h1 span {{ color: var(--accent); }}
.scan-info {{ color: var(--text-muted); font-size: 0.75rem; text-align: right; }}

/* Stats Grid */
.stats {{
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}}
.stat {{
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px;
  box-shadow: var(--shadow);
  border-left: 4px solid var(--border);
}}
.stat.s-blue {{ border-left-color: var(--accent); }}
.stat.s-green {{ border-left-color: var(--green); }}
.stat.s-orange {{ border-left-color: var(--orange); }}
.stat.s-purple {{ border-left-color: var(--purple); }}
.stat .label {{ color: var(--text-muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 500; }}
.stat .value {{ font-size: 1.5rem; font-weight: 700; margin-top: 2px; }}
.stat .value.blue {{ color: var(--accent); }}
.stat .value.green {{ color: var(--green); }}
.stat .value.orange {{ color: var(--orange); }}
.stat .value.purple {{ color: var(--purple); }}

/* Dashboard cards */
.dash-grid {{
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  margin-bottom: 16px;
}}
.dash-card {{
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px;
  box-shadow: var(--shadow);
}}
.dash-card-title {{
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}}
.legend-item {{
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  font-size: 0.78rem;
}}
.legend-dot {{
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex-shrink: 0;
}}
.legend-item.clickable:hover {{ background: var(--accent-light); border-radius: 6px; }}
.week-bar-row.clickable:hover {{ background: var(--accent-light); border-radius: 6px; }}
.legend-label {{ color: var(--text-sec); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.legend-count {{ font-weight: 600; color: var(--text); font-size: 0.75rem; }}
.legend-pct {{ color: var(--text-muted); font-size: 0.7rem; width: 36px; text-align: right; }}

.week-bar-row {{
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}}
.week-label {{
  font-size: 0.7rem;
  color: var(--text-muted);
  width: 90px;
  flex-shrink: 0;
  text-align: right;
}}
.week-bar-bg {{
  flex: 1;
  height: 20px;
  background: #F3F4F6;
  border-radius: 4px;
  overflow: hidden;
  position: relative;
}}
.week-bar-fill {{
  height: 100%;
  border-radius: 4px;
  background: var(--accent);
  transition: width 0.3s;
}}
.week-bar-count {{
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text);
  width: 32px;
  text-align: right;
}}
@media(min-width: 600px) {{
  .dash-grid {{ grid-template-columns: 1fr 1fr; }}
}}

/* Tabs */
.tabs {{
  display: flex;
  gap: 0;
  margin-bottom: 14px;
  background: var(--card-bg);
  border-radius: 10px;
  border: 1px solid var(--border);
  overflow: hidden;
  box-shadow: var(--shadow);
  position: sticky;
  top: 0;
  z-index: 100;
}}
.tab {{
  flex: 1;
  padding: 10px 6px;
  text-align: center;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  border: none;
  background: transparent;
  color: var(--text-muted);
  transition: all 0.2s;
  position: relative;
}}
.tab.active {{
  color: var(--accent);
  background: var(--accent-light);
}}
.tab .badge-count {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  font-size: 0.65rem;
  font-weight: 700;
  margin-left: 3px;
  vertical-align: middle;
}}
.tab .badge-count.green {{ background: var(--green-light); color: var(--green); }}
.tab .badge-count.orange {{ background: var(--orange-light); color: var(--orange); }}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}

/* Search & Filters */
.search-wrap {{
  position: relative;
  margin-bottom: 10px;
}}
.search-wrap svg {{
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
}}
.search-bar {{
  width: 100%;
  padding: 10px 14px 10px 38px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--text);
  font-size: 0.9rem;
  font-family: inherit;
  outline: none;
  transition: border-color 0.2s;
}}
.search-bar:focus {{ border-color: var(--accent); box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }}
.search-bar::placeholder {{ color: var(--text-muted); }}

.filters {{
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 8px;
  margin-bottom: 10px;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}}
.filters::-webkit-scrollbar {{ display: none; }}
.chip {{
  display: inline-flex;
  align-items: center;
  padding: 5px 12px;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  border: 1px solid var(--border);
  background: var(--card-bg);
  color: var(--text-sec);
  transition: all 0.15s;
  user-select: none;
}}
.chip:hover {{ border-color: var(--accent); }}
.chip.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}

.sort-row {{
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}}
.sort-row label {{ font-size: 0.75rem; color: var(--text-muted); font-weight: 500; }}
.sort-select {{
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid var(--border);
  font-size: 0.75rem;
  font-family: inherit;
  color: var(--text-sec);
  background: var(--card-bg);
  cursor: pointer;
}}

.count-label {{
  color: var(--text-muted);
  font-size: 0.75rem;
  margin-bottom: 10px;
  font-weight: 500;
}}

/* Property Cards */
.card {{
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px;
  margin-bottom: 10px;
  box-shadow: var(--shadow);
  cursor: pointer;
  transition: box-shadow 0.15s;
}}
.card:hover {{ box-shadow: var(--shadow-lg); }}
.card-top {{
  display: flex;
  gap: 12px;
}}
.card-img {{
  width: 80px;
  height: 60px;
  border-radius: 8px;
  overflow: hidden;
  flex-shrink: 0;
  background: #F3F4F6;
  display: flex;
  align-items: center;
  justify-content: center;
}}
.card-img img {{
  width: 100%;
  height: 100%;
  object-fit: cover;
}}
.card-img svg {{ color: var(--text-muted); }}
.card-body {{ flex: 1; min-width: 0; }}
.card-header {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 6px;
  gap: 8px;
}}
.card-title {{
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}}
.card-price {{
  font-weight: 700;
  color: var(--text);
  white-space: nowrap;
  font-size: 0.9rem;
}}
.card-meta {{
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 6px;
}}
.pill {{
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 0.7rem;
  font-weight: 500;
}}
.pill.type {{ background: #F3F4F6; color: var(--text-sec); }}
.pill.loc {{ background: #F3F4F6; color: var(--text-sec); }}
.pill.size {{ background: #F3F4F6; color: var(--text-sec); }}
.pill.date {{ background: #F3F4F6; color: var(--text-sec); }}
.pill.date.urgent {{ background: var(--red-light); color: var(--red); font-weight: 600; }}
.pill.discount {{ background: var(--green-light); color: var(--green); font-weight: 600; }}
.card-subtitle {{
  color: var(--text-muted);
  font-size: 0.75rem;
  font-weight: 500;
  margin-top: 2px;
}}
.card-address {{
  color: var(--text-muted);
  font-size: 0.75rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.card-view-link {{
  display: inline-block;
  font-size: 0.75rem;
  color: var(--text-sec);
  text-decoration: none;
  font-weight: 600;
  margin-top: 6px;
}}
.card-view-link:hover {{
  text-decoration: underline;
}}
.card-link {{
  display: inline-block;
  color: var(--text-sec);
  font-size: 0.75rem;
  text-decoration: none;
  font-weight: 500;
  margin-top: 4px;
}}
.card-link:hover {{ text-decoration: underline; }}

/* New/Changed badges on cards */
.card-badge {{
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 600;
  margin-left: 6px;
  vertical-align: middle;
}}
.card-badge.new {{ background: var(--green-light); color: var(--green); }}
.card-badge.changed {{ background: var(--orange-light); color: var(--orange); }}
.card-badge.notable {{ background: #F3F4F6; color: var(--text-sec); }}
.card-badge.expired {{ background: #F3F4F6; color: #6B7280; }}
.pill.expired {{ background: #F3F4F6; color: #6B7280; font-weight: 600; }}
.card.is-expired {{ opacity: 0.7; }}
.card.is-expired:hover {{ opacity: 1; }}
.card.expanded {{ box-shadow: var(--shadow-lg); border-color: var(--accent); }}
.card-expand {{
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
  animation: expandIn 0.2s ease-out;
}}
@keyframes expandIn {{
  from {{ opacity: 0; max-height: 0; }}
  to {{ opacity: 1; max-height: 1200px; }}
}}
.card-expand .detail-top {{
  display: flex;
  gap: 10px;
  margin-bottom: 8px;
}}
.card-expand .detail-thumb {{
  width: 100px;
  height: 75px;
  object-fit: cover;
  border-radius: 8px;
  flex-shrink: 0;
}}
.card-expand .detail-info {{ flex: 1; min-width: 0; }}
.card-expand .detail-row {{
  display: flex;
  justify-content: space-between;
  padding: 3px 0;
  font-size: 0.8rem;
}}
.card-expand .detail-label {{ color: var(--text-sec); font-size: 0.75rem; }}
.card-expand .detail-value {{ font-weight: 500; text-align: right; font-size: 0.8rem; color: var(--text); }}
.card-expand .detail-addr {{
  font-size: 0.72rem;
  color: var(--text-muted);
  margin-bottom: 6px;
  line-height: 1.3;
}}
.card-expand .detail-map {{
  margin: 6px 0;
  border-radius: 8px;
  overflow: hidden;
  height: 120px;
}}
.card-expand .detail-map-frame {{
  width: 100%;
  height: 120px;
  border: none;
  border-radius: 8px;
}}
.card-expand .price-chart {{
  margin: 6px 0;
  padding: 6px;
  background: var(--bg);
  border-radius: 8px;
}}
.card-expand .price-chart h3 {{ font-size: 0.72rem; color: var(--text-sec); margin-bottom: 4px; font-weight: 600; }}
.card-expand .detail-same-scheme {{
  margin: 6px 0;
  padding: 6px;
  background: var(--bg);
  border-radius: 8px;
}}
.card-expand .detail-same-scheme h3 {{ font-size: 0.72rem; color: var(--text-sec); margin-bottom: 4px; font-weight: 600; }}
.same-scheme-item {{
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 0;
  border-bottom: 1px solid var(--border);
  font-size: 0.75rem;
  cursor: pointer;
}}
.same-scheme-item:last-child {{ border-bottom: none; }}
.same-scheme-item:hover {{ background: rgba(37,99,235,0.05); }}
.ss-title {{ flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.ss-size {{ font-size: 0.65rem; color: var(--text-muted); margin-left: 4px; }}
.ss-price {{ font-weight: 600; white-space: nowrap; }}
.ss-date {{ color: var(--text-muted); white-space: nowrap; font-size: 0.7rem; }}

/* Photo lightbox */
.card-img img {{ cursor: zoom-in; }}
.photo-lightbox {{
  display: none;
  position: fixed;
  inset: 0;
  z-index: 10000;
  background: rgba(0,0,0,0.85);
  align-items: center;
  justify-content: center;
  cursor: zoom-out;
}}
.photo-lightbox.open {{ display: flex; }}
.photo-lightbox img {{
  max-width: 92vw;
  max-height: 90vh;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}}

/* Same-scheme expand detail */
.ss-expand {{
  padding: 8px 0 4px;
  border-top: 1px solid var(--border);
  animation: expandIn 0.15s ease-out;
}}
.ss-detail-row {{
  display: flex;
  justify-content: space-between;
  padding: 2px 0;
  font-size: 0.75rem;
}}
.ss-detail-label {{ color: var(--text-muted); font-size: 0.72rem; }}
.ss-detail-value {{ font-weight: 500; text-align: right; font-size: 0.75rem; }}
.ss-view-link {{
  display: inline-block;
  font-size: 0.72rem;
  color: var(--accent);
  text-decoration: none;
  font-weight: 600;
  margin-top: 4px;
}}
.ss-view-link:hover {{ text-decoration: underline; }}

/* Table inline detail */
.table-detail-row td {{
  padding: 0 !important;
  border-bottom: 2px solid var(--accent) !important;
}}
.table-detail-content {{
  padding: 14px 16px;
  background: #F9FAFB;
  animation: expandIn 0.2s ease-out;
}}
.table-detail-content .detail-row {{
  display: flex;
  justify-content: space-between;
  padding: 5px 0;
  border-bottom: 1px solid var(--border);
  font-size: 0.8rem;
}}
.table-detail-content .detail-label {{ color: var(--text-muted); }}
.table-detail-content .detail-value {{ font-weight: 500; text-align: right; }}
.table-detail-content .price-chart {{
  margin: 10px 0;
  padding: 10px;
  background: var(--card-bg);
  border-radius: 8px;
}}
.table-detail-content .price-chart h3 {{ font-size: 0.78rem; color: var(--text-muted); margin-bottom: 6px; font-weight: 600; }}

/* Bookmark filters */
.bm-add-btn {{
  margin-left: auto;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 50%;
  width: 22px;
  height: 22px;
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}}
.bm-add-btn:hover {{ opacity: 0.8; }}
.bm-input-row {{
  display: flex;
  gap: 8px;
}}
.bm-input-row .search-bar {{ flex: 1; }}
.bm-save-btn {{
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 8px 16px;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}}
.bm-save-btn:hover {{ opacity: 0.8; }}
.bm-list {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}}
.bm-chip {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--accent-light);
  color: var(--accent);
  border-radius: 20px;
  font-size: 0.78rem;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s;
}}
.bm-chip:hover {{ border-color: var(--accent); background: #DBEAFE; }}
.bm-chip .bm-delete {{
  font-size: 0.7rem;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0 2px;
  border-radius: 50%;
}}
.bm-chip .bm-delete:hover {{ color: var(--red); }}
.bm-chip .bm-count {{
  font-size: 0.65rem;
  background: var(--accent);
  color: #fff;
  padding: 1px 5px;
  border-radius: 10px;
}}
.data-table tr.is-expired td {{ color: var(--text-muted); }}
.data-table tr.is-expired .td-price {{ color: var(--text-muted); }}
.filter-row {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}}
.filter-row label {{ font-size: 0.75rem; color: var(--text-muted); font-weight: 500; white-space: nowrap; }}
.filter-row select, .filter-row input {{
  padding: 5px 8px;
  border-radius: 6px;
  border: 1px solid var(--border);
  font-size: 0.75rem;
  font-family: inherit;
  color: var(--text-sec);
  background: var(--card-bg);
}}
.filter-row input[type="number"] {{ width: 100px; }}
@media(max-width: 600px) {{
  .filter-row {{ gap: 6px; }}
  .filter-row input[type="number"] {{ width: 80px; }}
}}

/* Change indicators */
.change-item {{
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 0.78rem;
  border-top: 1px solid var(--border);
  margin-top: 6px;
  padding-top: 8px;
}}
.change-label {{ color: var(--text-muted); font-size: 0.7rem; font-weight: 500; }}
.old-val {{ color: var(--red); text-decoration: line-through; font-size: 0.78rem; }}
.new-val {{ color: var(--green); font-weight: 600; font-size: 0.78rem; }}
.change-arrow {{ color: var(--text-muted); font-size: 0.7rem; }}

/* Sparkline */
.sparkline {{ display: inline-block; vertical-align: middle; margin-left: 4px; }}

/* Hot deals & upcoming sections */
.section-title {{
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--text);
  margin: 16px 0 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}}
.section-title svg {{ color: var(--text-muted); }}

/* Scan history chart */
.history-card {{
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px;
  box-shadow: var(--shadow);
}}
.history-row {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  font-size: 0.8rem;
}}
.history-row:last-child {{ border-bottom: none; }}
.history-date {{ color: var(--text-muted); font-size: 0.75rem; }}
.history-stats {{ display: flex; gap: 12px; }}
.history-new {{ color: var(--green); font-weight: 500; font-size: 0.75rem; }}
.history-changed {{ color: var(--orange); font-weight: 500; font-size: 0.75rem; }}

/* Load more */
.load-more {{
  display: block;
  width: 100%;
  padding: 10px;
  margin: 10px 0;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--card-bg);
  color: var(--accent);
  font-size: 0.85rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  text-align: center;
}}
.load-more:hover {{ background: var(--accent-light); }}

/* Modal */
.modal-backdrop {{
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.4);
  z-index: 1000;
  align-items: flex-end;
  justify-content: center;
}}
.modal-backdrop.open {{ display: flex; }}
.modal {{
  background: var(--card-bg);
  border-radius: 16px 16px 0 0;
  width: 100%;
  max-width: 768px;
  max-height: 85vh;
  overflow-y: auto;
  padding: 20px;
  animation: slideUp 0.25s ease-out;
}}
@keyframes slideUp {{
  from {{ transform: translateY(100%); }}
  to {{ transform: translateY(0); }}
}}
.modal-handle {{
  width: 40px;
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  margin: 0 auto 16px;
}}
.modal-close {{
  position: absolute;
  top: 16px;
  right: 16px;
  background: none;
  border: none;
  font-size: 1.2rem;
  cursor: pointer;
  color: var(--text-muted);
  padding: 4px;
}}
.modal h2 {{ font-size: 1.1rem; font-weight: 700; margin-bottom: 12px; }}
.modal .detail-row {{
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  font-size: 0.85rem;
}}
.modal .detail-label {{ color: var(--text-muted); }}
.modal .detail-value {{ font-weight: 500; text-align: right; }}
.modal .price-chart {{
  margin: 16px 0;
  padding: 12px;
  background: var(--bg);
  border-radius: 10px;
}}
.modal .price-chart h3 {{ font-size: 0.8rem; color: var(--text-muted); margin-bottom: 8px; font-weight: 600; }}

/* Empty state */
.empty {{
  text-align: center;
  padding: 40px 20px;
  color: var(--text-muted);
}}
.empty svg {{ margin-bottom: 12px; }}
.empty p {{ font-size: 0.85rem; }}

/* Skeleton loading */
.skeleton {{
  background: linear-gradient(90deg, #F3F4F6 25%, #E5E7EB 50%, #F3F4F6 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 8px;
}}
@keyframes shimmer {{
  0% {{ background-position: 200% 0; }}
  100% {{ background-position: -200% 0; }}
}}
.skeleton-card {{
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px;
  margin-bottom: 10px;
}}
.skeleton-line {{
  height: 14px;
  margin-bottom: 8px;
}}
.skeleton-line.w60 {{ width: 60%; }}
.skeleton-line.w40 {{ width: 40%; }}
.skeleton-line.w80 {{ width: 80%; }}

/* Footer */
footer {{
  text-align: center;
  color: var(--text-muted);
  font-size: 0.7rem;
  padding: 20px 0;
  border-top: 1px solid var(--border);
  margin-top: 20px;
}}

@media (max-width: 400px) {{
  .stats {{ gap: 8px; }}
  .stat .value {{ font-size: 1.3rem; }}
  .container {{ padding: 12px; }}
  .card-img {{ width: 64px; height: 48px; }}
}}

/* Table view */
.table-wrap {{
  overflow-x: auto;
  overflow-y: auto;
  max-height: 75vh;
  -webkit-overflow-scrolling: touch;
  margin: 0 -16px;
  padding: 0 16px;
}}
.data-table {{
  width: 100%;
  min-width: 700px;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 0.8rem;
  background: var(--card-bg);
  border-radius: 10px;
  box-shadow: var(--shadow);
}}
.data-table thead th {{ position: sticky; top: 0; z-index: 50; }}
.data-table th {{
  background: var(--accent-light);
  color: var(--text-sec);
  font-weight: 600;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  padding: 10px 8px;
  text-align: left;
  white-space: nowrap;
  border-bottom: 2px solid var(--border);
  user-select: none;
}}
.data-table th.sortable {{ cursor: pointer; }}
.data-table th.sortable:hover {{ background: #DBEAFE; }}
.data-table th.sorted-asc::after {{ content: ' \\25B2'; font-size: 0.6rem; }}
.data-table th.sorted-desc::after {{ content: ' \\25BC'; font-size: 0.6rem; }}
.data-table td {{
  padding: 8px 8px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
  white-space: nowrap;
}}
.data-table tr:hover td {{ background: #F9FAFB; }}
.data-table tr.urgent td {{ background: var(--orange-light); }}
.data-table .td-title {{
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 600;
  color: var(--text);
  cursor: pointer;
}}
.data-table .td-title .td-scheme {{
  display: block;
  font-size: 0.7rem;
  font-weight: 400;
  color: var(--text-sec);
  overflow: hidden;
  text-overflow: ellipsis;
}}
.data-table .td-title:hover {{ color: var(--accent); }}
.data-table .td-price {{ color: var(--accent); font-weight: 700; }}
.data-table .td-discount {{ color: var(--green); font-weight: 600; }}
.data-table .td-days {{ font-size: 0.7rem; color: var(--text-muted); }}
.data-table .link-cell a {{
  color: var(--accent);
  text-decoration: none;
  font-size: 0.75rem;
}}
.data-table .link-cell a:hover {{ text-decoration: underline; }}
.data-table .expand-btn {{
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.7rem;
  color: var(--accent);
  padding: 2px 4px;
  border-radius: 4px;
  transition: transform 0.15s;
}}
.data-table .expand-btn:hover {{ background: var(--accent-light); }}
.data-table .expand-btn.open {{ transform: rotate(90deg); }}
.data-table .hist-row td {{
  background: #F9FAFB;
  padding: 4px 8px;
  font-size: 0.72rem;
  color: var(--text-sec);
  border-bottom: 1px solid #F3F4F6;
}}
.data-table .hist-row .hist-label {{
  color: var(--text-muted);
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}}
.data-table .hist-row .hist-changed {{
  background: var(--orange-light);
  color: var(--orange);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 600;
}}
@media(max-width: 600px) {{
  .table-wrap {{ margin: 0 -12px; padding: 0 12px; }}
  .data-table {{ font-size: 0.72rem; }}
  .data-table th, .data-table td {{ padding: 6px 5px; }}
  .data-table .td-title {{ max-width: 120px; }}
}}
</style>
</head>
<body>
<div id="loading-overlay" style="display:flex;position:fixed;inset:0;z-index:9999;background:var(--bg);align-items:center;justify-content:center;flex-direction:column;gap:12px">
  <div style="width:36px;height:36px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite"></div>
  <div style="font-size:0.85rem;color:var(--text-sec);font-weight:500">Loading properties...</div>
</div>
<style>@keyframes spin{{from{{transform:rotate(0deg)}}to{{transform:rotate(360deg)}}}}</style>
<div class="photo-lightbox" id="photo-lightbox" onclick="this.classList.remove('open')"><img id="photo-lightbox-img" src="" alt=""></div>
<div class="container">
  <header>
    <h1>Lelong<span>Tips</span></h1>
    <div class="scan-info">Last scan<br><strong>{esc(scan_date_display)} MYT</strong></div>
  </header>

  <div class="stats">
    <div class="stat s-blue" style="grid-column: 1 / -1">
      <div class="label">Active Listings</div>
      <div class="value blue" id="stat-active">{stats['active_count']:,}</div>
    </div>
  </div>

  <div class="dash-grid">
    <div class="dash-card">
      <div class="dash-card-title">Listings by Type</div>
      <div id="type-chart" style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">
        <canvas id="pie-chart" width="120" height="120" style="flex-shrink:0"></canvas>
        <div id="type-legend" style="flex:1;min-width:0"></div>
      </div>
    </div>
    <div class="dash-card">
      <div class="dash-card-title">Auctions by Week</div>
      <div id="week-chart"></div>
    </div>
  </div>

  <div class="tabs" id="tab-bar">
    <button class="tab active" data-tab="dashboard">Dashboard</button>
    <button class="tab" data-tab="new">New <span class="badge-count green">{stats['new_count']}</span></button>
    <button class="tab" data-tab="changes">Changes <span class="badge-count orange">{stats['changed_count']}</span></button>
    <button class="tab" data-tab="search">Search</button>
    <button class="tab" data-tab="table">Table</button>
    <button class="tab" data-tab="map">Map</button>
  </div>

  <div id="tab-dashboard" class="tab-content active">
    <div class="section-title">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M2 3C2 2.4 2.4 2 3 2H5L6 3H13C13.6 3 14 3.4 14 4V12C14 12.6 13.6 13 13 13H3C2.4 13 2 12.6 2 12V3Z" fill="currentColor"/></svg>
      Saved Filters
      <button class="bm-add-btn" id="bm-add" title="Add bookmark">+</button>
    </div>
    <div id="bm-input-wrap" style="display:none;margin-bottom:12px">
      <div class="bm-input-row">
        <input type="text" id="bm-query" class="search-bar" placeholder="e.g. landed under 500k in Selangor, condos KL above 300k...">
        <button class="bm-save-btn" id="bm-save">Save</button>
      </div>
      <div id="bm-preview" style="display:none;margin-top:6px;font-size:0.75rem;color:var(--text-muted)"></div>
    </div>
    <div id="bm-list" class="bm-list"></div>

    <div class="section-title">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 1L10 5.5L15 6.2L11.5 9.5L12.4 14.5L8 12L3.6 14.5L4.5 9.5L1 6.2L6 5.5L8 1Z" fill="currentColor"/></svg>
      Hot Deals — Biggest Price Drops
    </div>
    <div id="hot-deals">
      <div class="skeleton-card"><div class="skeleton skeleton-line w60"></div><div class="skeleton skeleton-line w40"></div></div>
      <div class="skeleton-card"><div class="skeleton skeleton-line w80"></div><div class="skeleton skeleton-line w40"></div></div>
    </div>

    <div class="section-title">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M13 2H3C2.4 2 2 2.4 2 3V13C2 13.6 2.4 14 3 14H13C13.6 14 14 13.6 14 13V3C14 2.4 13.6 2 13 2ZM5 12H4V7H5V12ZM8.5 12H7.5V4H8.5V12ZM12 12H11V9H12V12Z" fill="currentColor"/></svg>
      Notable Listings
    </div>
    <div id="notable" style="font-size:0.72rem;color:var(--text-muted);margin-bottom:8px">Multi-round auctions with declining prices</div>
    <div id="notable-cards">
      <div class="skeleton-card"><div class="skeleton skeleton-line w60"></div><div class="skeleton skeleton-line w40"></div></div>
    </div>

    <div class="section-title">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M14 2H2V4H14V2ZM14 6H2V8H14V6ZM14 10H2V12H14V10Z" fill="currentColor"/></svg>
      Scan History
    </div>
    <div id="scan-history" class="history-card"></div>
  </div>

  <div id="tab-new" class="tab-content">
    <div class="search-wrap">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M11 11L14 14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      <input type="text" class="search-bar" id="search-new" placeholder="Search new listings...">
    </div>
    <div class="filters" id="filters-new"></div>
    <div class="sort-row">
      <label>Sort:</label>
      <select class="sort-select" id="sort-new">
        <option value="price_asc">Price: Low to High</option>
        <option value="price_desc">Price: High to Low</option>
        <option value="date_asc">Auction Date</option>
      </select>
    </div>
    <div class="count-label" id="count-new">Loading...</div>
    <div id="cards-new"></div>
    <button class="load-more" id="more-new" style="display:none">Load more</button>
  </div>

  <div id="tab-changes" class="tab-content">
    <div class="search-wrap">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M11 11L14 14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      <input type="text" class="search-bar" id="search-changes" placeholder="Search changed listings...">
    </div>
    <div class="count-label" id="count-changes">Loading...</div>
    <div id="cards-changes"></div>
    <button class="load-more" id="more-changes" style="display:none">Load more</button>
  </div>

  <div id="tab-search" class="tab-content">
    <div class="search-wrap">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M11 11L14 14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      <input type="text" class="search-bar" id="search-all" placeholder="Search all listings...">
    </div>
    <div class="filters" id="filters-type"></div>
    <div class="filters" id="filters-loc"></div>
    <div class="filter-row">
      <label>Status:</label>
      <select id="filter-status">
        <option value="all">All</option>
        <option value="active" selected>Active Only</option>
        <option value="expired">Expired Only</option>
      </select>
      <label>Price:</label>
      <input type="number" id="filter-price-min" placeholder="Min" min="0" step="10000">
      <span style="color:var(--text-muted);font-size:0.75rem">-</span>
      <input type="number" id="filter-price-max" placeholder="Max" min="0" step="10000">
    </div>
    <div class="filter-row">
      <label>Size (sq.ft):</label>
      <input type="number" id="filter-size-min" placeholder="Min" min="0" step="100">
      <span style="color:var(--text-muted);font-size:0.75rem">-</span>
      <input type="number" id="filter-size-max" placeholder="Max" min="0" step="100">
      <label>Auction in:</label>
      <select id="filter-date-range">
        <option value="">Any time</option>
        <option value="7">Next 7 days</option>
        <option value="14">Next 14 days</option>
        <option value="30">Next 30 days</option>
        <option value="60">Next 60 days</option>
        <option value="90">Next 90 days</option>
      </select>
      <label>Discount:</label>
      <select id="filter-discount">
        <option value="">Any</option>
        <option value="10">10%+</option>
        <option value="20">20%+</option>
        <option value="30">30%+</option>
        <option value="40">40%+</option>
        <option value="50">50%+</option>
      </select>
    </div>
    <div class="filter-row">
      <label>Sort:</label>
      <select class="sort-select" id="sort-all">
        <option value="price_asc">Price: Low to High</option>
        <option value="price_desc">Price: High to Low</option>
        <option value="date_asc">Auction Date</option>
        <option value="discount">Biggest Discount</option>
        <option value="size_desc">Size: Large to Small</option>
        <option value="size_asc">Size: Small to Large</option>
      </select>
      <button class="chip" id="filter-reset" style="background:#FEE2E2;color:#DC2626;font-size:0.7rem;padding:4px 10px">Reset All</button>
    </div>
    <div class="count-label" id="count-all">Loading...</div>
    <div id="cards-all"></div>
    <button class="load-more" id="more-all" style="display:none">Load more</button>
  </div>

  <div id="tab-table" class="tab-content">
    <div class="search-wrap">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M11 11L14 14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      <input type="text" class="search-bar" id="search-table" placeholder="Filter table...">
    </div>
    <div class="filter-row">
      <label>Status:</label>
      <select id="filter-table-status">
        <option value="all">All</option>
        <option value="active" selected>Active Only</option>
        <option value="expired">Expired Only</option>
      </select>
    </div>
    <div class="count-label" id="count-table">Loading...</div>
    <div class="table-wrap">
      <table class="data-table" id="data-table">
        <thead>
          <tr>
            <th data-sort="title" class="sortable">Property</th>
            <th data-sort="price" class="sortable">Price</th>
            <th data-sort="type" class="sortable">Type</th>
            <th data-sort="location" class="sortable">Location</th>
            <th data-sort="size" class="sortable">Size</th>
            <th data-sort="auction" class="sortable sorted-asc">Auction</th>
            <th data-sort="discount" class="sortable">Disc.</th>
            <th>Link</th>
          </tr>
        </thead>
        <tbody id="table-body"></tbody>
      </table>
    </div>
    <button class="load-more" id="more-table" style="display:none">Load more</button>
  </div>

  <div id="tab-map" class="tab-content">
    <div class="filter-row" style="margin-bottom:10px">
      <label>Type:</label>
      <select id="map-filter-type"><option value="">All Types</option></select>
      <label>Status:</label>
      <select id="map-filter-status">
        <option value="active" selected>Active Only</option>
        <option value="all">All</option>
        <option value="expired">Expired Only</option>
      </select>
      <span id="map-count" style="font-size:0.75rem;color:var(--text-muted);margin-left:auto"></span>
    </div>
    <div id="property-map" style="height:70vh;border-radius:12px;border:1px solid var(--border)"></div>
  </div>

  <footer>
    LelongTips Property Monitor &middot; Auto-updated every 3 days
  </footer>
</div>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>

<script id="__stats__" type="application/json">{inline_stats}</script>
<script id="__active__" type="application/json">null</script>
<script id="__changes__" type="application/json">{inline_changes}</script>

<script>
(function() {{
  'use strict';

  // --- State ---
  let allProps = {{}};
  let changesData = {{}};
  let statsData = null;
  const PAGE_SIZE = 20;
  const views = {{
    new: {{ items: [], displayed: 0 }},
    changes: {{ items: [], displayed: 0 }},
    all: {{ items: [], displayed: 0 }},
    table: {{ items: [], displayed: 0 }},
  }};
  let activeFilters = {{ types: new Set(), locs: new Set() }};

  // --- Helpers ---
  function esc(s) {{ return s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : ''; }}

  function parseDate(s) {{
    if (!s) return null;
    const months = {{Jan:0,Feb:1,Mar:2,Apr:3,May:4,Jun:5,Jul:6,Aug:7,Sep:8,Oct:9,Nov:10,Dec:11}};
    const m = s.match(/(\d{{1,2}})\s+(\w{{3}})\s+(\d{{4}})/);
    if (m) return new Date(+m[3], months[m[2]]||0, +m[1]);
    return null;
  }}

  const parseAuctionDate = parseDate;

  function daysUntil(dateStr) {{
    const d = parseDate(dateStr);
    if (!d) return 999;
    const now = new Date();
    now.setHours(0,0,0,0);
    return Math.ceil((d - now) / 86400000);
  }}

  function parseDiscount(d) {{
    if (!d) return 0;
    const m = d.match(/-(\d+)/);
    return m ? parseInt(m[1]) : 0;
  }}

  // --- Type icons (SVG) ---
  const typeIcons = {{
    Office: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="4" y="3" width="16" height="18" rx="1"/><line x1="9" y1="7" x2="15" y2="7"/><line x1="9" y1="11" x2="15" y2="11"/><line x1="9" y1="15" x2="12" y2="15"/></svg>',
    Shop: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 9l1.5-5h15L21 9M3 9v11h18V9M3 9h18"/><rect x="9" y="14" width="6" height="6"/></svg>',
    Retail: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 9l1.5-5h15L21 9M3 9v11h18V9M3 9h18"/><rect x="9" y="14" width="6" height="6"/></svg>',
    Residence: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 12l9-8 9 8"/><rect x="5" y="12" width="14" height="9"/><rect x="9" y="15" width="6" height="6"/></svg>',
    Factory: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 21V11l5-4v4l5-4v4l5-4v14H4z"/></svg>',
    Land: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 20h20M5 20c0-4 3-7 7-12 4 5 7 8 7 12"/></svg>',
    Commercial: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="5" width="18" height="16" rx="1"/><line x1="8" y1="9" x2="16" y2="9"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="12" y2="17"/></svg>',
  }};
  function getTypeIcon(type) {{ return typeIcons[type] || typeIcons.Commercial; }}

  // --- Sparkline ---
  function sparkline(ph) {{
    if (!ph || ph.length < 2) return '';
    const vals = ph.map(h => {{
      const m = String(h.p).match(/[\d,]+/);
      return m ? parseInt(m[0].replace(/,/g,'')) : 0;
    }}).filter(v => v > 0);
    if (vals.length < 2) return '';
    const min = Math.min(...vals), max = Math.max(...vals);
    const range = max - min || 1;
    const w = 50, h = 16;
    const pts = vals.map((v, i) => {{
      const x = (i / (vals.length - 1)) * w;
      const y = h - ((v - min) / range) * (h - 2) - 1;
      return x.toFixed(1) + ',' + y.toFixed(1);
    }}).join(' ');
    const color = vals[vals.length-1] <= vals[0] ? '#059669' : '#DC2626';
    return '<span class="sparkline"><svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'"><polyline points="'+pts+'" fill="none" stroke="'+color+'" stroke-width="1.5"/></svg></span>';
  }}

  // Extract scheme/building name from address string
  function schemeName(addr, title, aiScheme) {{
    // Use AI-extracted scheme name if available
    if (aiScheme) return aiScheme;
    if (!addr || addr === title) return '';
    const paren = addr.match(/\(([^)]+)\)/);
    const named = addr.match(/(?:,\s*)?([A-Z][A-Za-z\s]+(?:Park|Centre|Point|Plaza|Place|Heights|Residences?|Tower|City|Garden|Court|Square|Perdagangan|Komersial|Damansara|Business|Mall|Complex|Kompleks)[A-Za-z\s]*)/);
    if (named) return named[1].trim();
    if (paren) return paren[1].trim();
    const parts = addr.split(',').map(function(s) {{ return s.trim(); }});
    for (let k = 0; k < parts.length && k < 3; k++) {{
      const seg = parts[k];
      if (seg && !/^\d/.test(seg) && !/^(Lot|Block|No\.|Unit|Level|Ground|First|Second)\b/i.test(seg) && seg.length > 5) {{
        return seg.length > 50 ? seg.substring(0, 47) + '...' : seg;
      }}
    }}
    return parts[0] || '';
  }}

  // --- Card rendering ---
  function renderCard(id, p, opts) {{
    opts = opts || {{}};
    const days = daysUntil(p.ad);
    const urgentClass = days <= 7 ? ' urgent' : '';
    const daysText = days <= 0 ? 'Today' : days === 1 ? 'Tomorrow' : 'in ' + days + 'd';
    const imgHtml = p.img
      ? '<img src="'+esc(p.img)+'" alt="" loading="lazy" onclick="event.stopPropagation();window._showPhoto(this.src)">'
      : getTypeIcon(p.pt);
    const discountHtml = p.d ? '<span class="pill discount">'+esc(p.d)+'</span>' : '';
    const spark = sparkline(p.ph);

    const isExpired = !!p.exp;
    const daysLabel = isExpired ? 'Expired' : daysText;
    let badgeHtml = '';
    if (opts.isNew) badgeHtml = '<span class="card-badge new">NEW</span>';
    else if (opts.isChanged) badgeHtml = '<span class="card-badge changed">CHANGED</span>';
    else if (opts.notableBadge) badgeHtml = '<span class="card-badge notable">'+esc(opts.notableBadge)+'</span>';
    else if (isExpired) badgeHtml = '<span class="card-badge expired">EXPIRED</span>';

    let changesHtml = '';
    if (opts.changes && opts.changes.length) {{
      for (const c of opts.changes) {{
        changesHtml += '<div class="change-item">'
          + '<span class="change-label">'+esc(c.field)+':</span> '
          + '<span class="old-val">'+esc(c.old_value)+'</span> '
          + '<span class="change-arrow">&rarr;</span> '
          + '<span class="new-val">'+esc(c.new_value)+'</span>'
          + '</div>';
      }}
    }}

    const scheme = schemeName(p.a, p.t, p.sn);
    const displayTitle = scheme || p.a || p.t;
    const showSubtitle = p.t && displayTitle !== p.t;
    const linkHtml = p.u ? '<a class="card-view-link" href="'+esc(p.u)+'" target="_blank" rel="noopener" onclick="event.stopPropagation()">View Listing &rarr;</a>' : '';

    const expClass = isExpired ? ' is-expired' : '';
    return '<div class="card'+expClass+'" data-id="'+esc(id)+'" onclick="window._openDetail(this.dataset.id)">'
      + '<div class="card-top">'
      + '<div class="card-img">'+imgHtml+'</div>'
      + '<div class="card-body">'
      + '<div class="card-header"><div class="card-title">'+esc(displayTitle)+badgeHtml+'</div><div class="card-price">'+esc(p.p)+spark+'</div></div>'
      + (showSubtitle ? '<div class="card-subtitle">'+esc(p.t)+'</div>' : '')
      + '<div class="card-meta">'
      + (p.pt ? '<span class="pill type">'+esc(p.pt)+'</span>' : '')
      + '<span class="pill loc">'+esc(p.l)+'</span>'
      + (p.s && p.s !== 'Size not specified' ? '<span class="pill size">'+esc(p.s)+'</span>' : '')
      + '<span class="pill '+(isExpired ? 'expired' : 'date'+urgentClass)+'">'+esc(p.ad)+' ('+daysLabel+')</span>'
      + discountHtml
      + '</div>'
      + (p.a && p.a !== p.t ? '<div class="card-address">'+esc(p.a)+'</div>' : '')
      + linkHtml
      + '</div></div>'
      + changesHtml
      + '</div>';
  }}

  function renderCards(containerId, items, start, count, opts) {{
    const container = document.getElementById(containerId);
    let html = '';
    const end = Math.min(start + count, items.length);
    for (let i = start; i < end; i++) {{
      const item = items[i];
      html += renderCard(item.id, item.prop, item.opts || opts || {{}});
    }}
    if (start === 0) container.innerHTML = html;
    else container.insertAdjacentHTML('beforeend', html);
    return end;
  }}

  // --- Sorting ---
  function parseSize(s) {{
    const m = (s || '').replace(/,/g, '').match(/([\d.]+)/);
    return m ? parseFloat(m[1]) : 0;
  }}
  function sortItems(items, sortBy) {{
    const sorters = {{
      price_asc: (a, b) => (a.prop.pv || 0) - (b.prop.pv || 0),
      price_desc: (a, b) => (b.prop.pv || 0) - (a.prop.pv || 0),
      date_asc: (a, b) => daysUntil(a.prop.ad) - daysUntil(b.prop.ad),
      discount: (a, b) => parseDiscount(b.prop.d) - parseDiscount(a.prop.d),
      size_desc: (a, b) => parseSize(b.prop.s) - parseSize(a.prop.s),
      size_asc: (a, b) => parseSize(a.prop.s) - parseSize(b.prop.s),
    }};
    items.sort(sorters[sortBy] || sorters.price_asc);
  }}

  // --- Search & Filter ---
  function buildSearchString(p) {{
    return (p.t + ' ' + p.a + ' ' + p.l + ' ' + p.pt + ' ' + p.p + ' ' + p.s).toLowerCase();
  }}

  function filterAndRender(viewName) {{
    const view = views[viewName];
    const searchEl = document.getElementById('search-' + (viewName === 'all' ? 'all' : viewName));
    const query = searchEl ? searchEl.value.toLowerCase().trim() : '';
    const sortEl = document.getElementById('sort-' + (viewName === 'all' ? 'all' : viewName));
    const sortBy = sortEl ? sortEl.value : 'price_asc';

    let items = view.sourceItems || [];

    // Text filter
    if (query) {{
      const tokens = query.split(/\s+/);
      items = items.filter(item => {{
        const s = item._search;
        return tokens.every(t => s.includes(t));
      }});
    }}

    // Type/location/status/price filters (search tab only)
    if (viewName === 'all') {{
      if (activeFilters.types.size > 0) {{
        items = items.filter(item => activeFilters.types.has(item.prop.pt));
      }}
      if (activeFilters.locs.size > 0) {{
        items = items.filter(item => activeFilters.locs.has(item.prop.l));
      }}
      // Status filter
      const statusVal = document.getElementById('filter-status').value;
      if (statusVal === 'active') {{
        items = items.filter(item => !item.prop.exp);
      }} else if (statusVal === 'expired') {{
        items = items.filter(item => !!item.prop.exp);
      }}
      // Price range filter
      const minPrice = parseInt(document.getElementById('filter-price-min').value) || 0;
      const maxPrice = parseInt(document.getElementById('filter-price-max').value) || 0;
      if (minPrice > 0) {{
        items = items.filter(item => (item.prop.pv || 0) >= minPrice);
      }}
      if (maxPrice > 0) {{
        items = items.filter(item => (item.prop.pv || 0) <= maxPrice);
      }}
      // Size range filter
      const minSize = parseInt(document.getElementById('filter-size-min').value) || 0;
      const maxSize = parseInt(document.getElementById('filter-size-max').value) || 0;
      if (minSize > 0 || maxSize > 0) {{
        items = items.filter(item => {{
          const m = (item.prop.s || '').replace(/,/g, '').match(/([\d.]+)/);
          if (!m) return false;
          const sz = parseFloat(m[1]);
          if (minSize > 0 && sz < minSize) return false;
          if (maxSize > 0 && sz > maxSize) return false;
          return true;
        }});
      }}
      // Auction date range filter
      const dateRange = parseInt(document.getElementById('filter-date-range').value) || 0;
      if (dateRange > 0) {{
        items = items.filter(item => {{
          const d = daysUntil(item.prop.ad);
          return d >= 0 && d <= dateRange;
        }});
      }}
      // Discount filter
      const minDiscount = parseInt(document.getElementById('filter-discount').value) || 0;
      if (minDiscount > 0) {{
        items = items.filter(item => parseDiscount(item.prop.d) >= minDiscount);
      }}
      // Week date range filter (from dashboard click)
      if (window._weekFilter) {{
        const wf = window._weekFilter;
        items = items.filter(item => {{
          const ad = parseAuctionDate(item.prop.ad);
          return ad && ad >= wf.start && ad <= wf.end;
        }});
      }}
    }}

    // Sort
    sortItems(items, sortBy);

    view.items = items;
    view.displayed = 0;

    const containerId = 'cards-' + (viewName === 'all' ? 'all' : viewName);
    const countEl = document.getElementById('count-' + (viewName === 'all' ? 'all' : viewName));
    const moreBtn = document.getElementById('more-' + (viewName === 'all' ? 'all' : viewName));

    view.displayed = renderCards(containerId, items, 0, PAGE_SIZE);
    if (countEl) countEl.textContent = 'Showing ' + Math.min(view.displayed, items.length) + ' of ' + items.length + ' listings';
    if (moreBtn) moreBtn.style.display = view.displayed < items.length ? '' : 'none';

    if (items.length === 0) {{
      document.getElementById(containerId).innerHTML = '<div class="empty"><svg width="48" height="48" viewBox="0 0 48 48" fill="none"><circle cx="24" cy="24" r="20" stroke="#E5E7EB" stroke-width="2"/><path d="M17 20h14M17 26h8" stroke="#9CA3AF" stroke-width="2" stroke-linecap="round"/></svg><p>No listings found</p></div>';
    }}
  }}

  function loadMore(viewName) {{
    const view = views[viewName];
    const containerId = 'cards-' + (viewName === 'all' ? 'all' : viewName);
    const moreBtn = document.getElementById('more-' + (viewName === 'all' ? 'all' : viewName));
    const countEl = document.getElementById('count-' + (viewName === 'all' ? 'all' : viewName));
    view.displayed = renderCards(containerId, view.items, view.displayed, PAGE_SIZE);
    if (countEl) countEl.textContent = 'Showing ' + Math.min(view.displayed, view.items.length) + ' of ' + view.items.length + ' listings';
    if (moreBtn) moreBtn.style.display = view.displayed < view.items.length ? '' : 'none';
  }}

  // --- Table view ---
  const TABLE_PAGE = 50;
  let tableItems = [];
  let tableDisplayed = 0;
  let tableSortCol = 'auction';
  let tableSortDir = 'asc';

  function parseSize(s) {{
    if (!s) return 0;
    const m = s.match(/[\d,]+/);
    return m ? parseInt(m[0].replace(/,/g,'')) : 0;
  }}

  function sortTable(items, col, dir) {{
    const mul = dir === 'asc' ? 1 : -1;
    const sorters = {{
      title: (a,b) => mul * a.prop.t.localeCompare(b.prop.t),
      price: (a,b) => mul * ((a.prop.pv||0) - (b.prop.pv||0)),
      type: (a,b) => mul * (a.prop.pt||'').localeCompare(b.prop.pt||''),
      location: (a,b) => mul * (a.prop.l||'').localeCompare(b.prop.l||''),
      size: (a,b) => mul * (parseSize(a.prop.s) - parseSize(b.prop.s)),
      auction: (a,b) => mul * (daysUntil(a.prop.ad) - daysUntil(b.prop.ad)),
      discount: (a,b) => mul * (parseDiscount(a.prop.d) - parseDiscount(b.prop.d)),
    }};
    items.sort(sorters[col] || sorters.auction);
  }}

  function renderTableRows(items, start, count) {{
    const tbody = document.getElementById('table-body');
    let html = '';
    const end = Math.min(start + count, items.length);
    for (let i = start; i < end; i++) {{
      const item = items[i];
      const p = item.prop;
      const days = daysUntil(p.ad);
      const isExp = !!p.exp;
      const daysText = isExp ? 'Expired' : days <= 0 ? 'Today' : days === 1 ? '1d' : days + 'd';
      const rowClass = isExp ? ' is-expired' : (days <= 7 ? ' urgent' : '');
      const hist = p.hist || [];
      const hasHist = hist.length > 1;
      const rowId = 'tr-' + i;
      const expandBtn = hasHist
        ? '<button class="expand-btn" data-row="'+rowId+'" title="'+hist.length+' rounds">&#9654; '+hist.length+'</button>'
        : '';
      const scheme = schemeName(p.a, p.t, p.sn);
      const nameHtml = scheme
        ? esc(scheme) + '<span class="td-scheme">'+esc(p.t)+'</span>'
        : esc(p.a || p.t);
      const expBadge = isExp ? ' <span class="pill expired" style="font-size:0.6rem;padding:1px 5px">EXPIRED</span>' : '';
      html += '<tr class="'+rowClass+'" id="'+rowId+'" data-pid="'+esc(item.id)+'">'
        + '<td class="td-title" onclick="window._toggleTableDetail(this.parentElement)">'+ expandBtn + nameHtml + expBadge+'</td>'
        + '<td class="td-price">'+esc(p.p)+'</td>'
        + '<td>'+esc(p.pt)+'</td>'
        + '<td>'+esc(p.l)+'</td>'
        + '<td>'+esc(p.s && p.s !== 'Size not specified' ? p.s : '-')+'</td>'
        + '<td>'+esc(p.ad)+' <span class="td-days">('+daysText+')</span></td>'
        + '<td class="td-discount">'+esc(p.d || '-')+'</td>'
        + '<td class="link-cell">'+(p.u ? '<a href="'+esc(p.u)+'" target="_blank" rel="noopener">View</a>' : '-')+'</td>'
        + '</tr>';
      // Hidden history sub-rows showing each previous auction round
      if (hasHist) {{
        for (let j = 0; j < hist.length - 1; j++) {{
          const h = hist[j];
          const prev = j > 0 ? hist[j-1] : null;
          const priceChanged = prev && h.p && prev.p && h.p !== prev.p;
          const adChanged = prev && h.ad && prev.ad && h.ad !== prev.ad;
          const pCell = h.p ? (priceChanged ? '<span class="hist-changed">'+esc(h.p)+'</span>' : esc(h.p)) : '<span style="color:var(--text-muted)">-</span>';
          const adCell = h.ad ? (adChanged ? '<span class="hist-changed">'+esc(h.ad)+'</span>' : esc(h.ad)) : '-';
          const link = h.u ? '<a href="'+esc(h.u)+'" target="_blank" rel="noopener" style="color:var(--accent);text-decoration:none;font-size:0.7rem">View</a>' : '-';
          html += '<tr class="hist-row" data-parent="'+rowId+'" style="display:none">'
            + '<td style="padding-left:28px">'+esc(scheme || p.t)+'<br><span class="hist-label">'+esc(h.d)+'</span></td>'
            + '<td>'+pCell+'</td>'
            + '<td>'+esc(p.pt)+'</td>'
            + '<td>'+esc(p.l)+'</td>'
            + '<td>'+esc(p.s && p.s !== 'Size not specified' ? p.s : '-')+'</td>'
            + '<td>'+adCell+'</td>'
            + '<td></td>'
            + '<td class="link-cell">'+link+'</td>'
            + '</tr>';
        }}
      }}
    }}
    if (start === 0) tbody.innerHTML = html;
    else tbody.insertAdjacentHTML('beforeend', html);
    return end;
  }}

  function filterTable() {{
    const query = (document.getElementById('search-table').value || '').toLowerCase().trim();
    let items = views.table.sourceItems || [];
    if (query) {{
      const tokens = query.split(/\s+/);
      items = items.filter(item => {{
        const s = item._search;
        return tokens.every(t => s.includes(t));
      }});
    }}
    const statusVal = document.getElementById('filter-table-status').value;
    if (statusVal === 'active') {{
      items = items.filter(item => !item.prop.exp);
    }} else if (statusVal === 'expired') {{
      items = items.filter(item => !!item.prop.exp);
    }}
    sortTable(items, tableSortCol, tableSortDir);
    tableItems = items;
    tableDisplayed = renderTableRows(items, 0, TABLE_PAGE);
    const countEl = document.getElementById('count-table');
    const moreBtn = document.getElementById('more-table');
    if (countEl) countEl.textContent = 'Showing ' + Math.min(tableDisplayed, items.length) + ' of ' + items.length + ' listings';
    if (moreBtn) moreBtn.style.display = tableDisplayed < items.length ? '' : 'none';
    if (items.length === 0) {{
      document.getElementById('table-body').innerHTML = '<tr><td colspan="8" style="text-align:center;padding:24px;color:var(--text-muted)">No listings found</td></tr>';
    }}
  }}

  // Table header click → sort
  document.getElementById('data-table').querySelector('thead').addEventListener('click', function(e) {{
    const th = e.target.closest('th[data-sort]');
    if (!th) return;
    const col = th.dataset.sort;
    if (tableSortCol === col) {{
      tableSortDir = tableSortDir === 'asc' ? 'desc' : 'asc';
    }} else {{
      tableSortCol = col;
      tableSortDir = 'asc';
    }}
    // Update header classes
    this.querySelectorAll('th').forEach(h => h.classList.remove('sorted-asc','sorted-desc'));
    th.classList.add('sorted-' + tableSortDir);
    filterTable();
  }});

  document.getElementById('search-table').addEventListener('input', function() {{
    filterTable();
  }});
  document.getElementById('filter-table-status').addEventListener('change', function() {{
    filterTable();
  }});

  document.getElementById('more-table').addEventListener('click', function() {{
    tableDisplayed = renderTableRows(tableItems, tableDisplayed, TABLE_PAGE);
    const countEl = document.getElementById('count-table');
    if (countEl) countEl.textContent = 'Showing ' + Math.min(tableDisplayed, tableItems.length) + ' of ' + tableItems.length + ' listings';
    if (tableDisplayed >= tableItems.length) this.style.display = 'none';
  }});

  // Expand/collapse history sub-rows
  document.getElementById('table-body').addEventListener('click', function(e) {{
    const btn = e.target.closest('.expand-btn');
    if (!btn) return;
    e.stopPropagation();
    const rowId = btn.dataset.row;
    const isOpen = btn.classList.toggle('open');
    const subRows = this.querySelectorAll('tr[data-parent="'+rowId+'"]');
    subRows.forEach(function(r) {{ r.style.display = isOpen ? '' : 'none'; }});
  }});

  // --- Tabs ---
  document.getElementById('tab-bar').addEventListener('click', function(e) {{
    const btn = e.target.closest('.tab');
    if (!btn) return;
    const tab = btn.dataset.tab;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + tab).classList.add('active');
  }});

  // --- Inline Detail Expansion ---
  function buildDetailHtml(p, currentId) {{
    const days = daysUntil(p.ad);
    const daysText = days <= 0 ? 'Today' : days === 1 ? 'Tomorrow' : 'in ' + days + 'd';

    // Compact price history sparkline (inline, no large chart)
    let priceChartHtml = '';
    if (p.ph && p.ph.length > 1) {{
      const vals = p.ph.map(h => {{
        const m = String(h.p).match(/[\d,]+/);
        return {{ v: m ? parseInt(m[0].replace(/,/g,'')) : 0, d: h.d, p: h.p }};
      }}).filter(h => h.v > 0);
      if (vals.length > 1) {{
        const min = Math.min(...vals.map(v=>v.v));
        const max = Math.max(...vals.map(v=>v.v));
        const range = max - min || 1;
        const w = 280, h = 50;
        const pts = vals.map((v, i) => {{
          const x = 10 + (i / (vals.length - 1)) * (w - 20);
          const y = h - 8 - ((v.v - min) / range) * (h - 16);
          return x.toFixed(1) + ',' + y.toFixed(1);
        }}).join(' ');
        const labels = vals.map((v, i) => {{
          const x = 10 + (i / (vals.length - 1)) * (w - 20);
          return '<text x="'+x.toFixed(1)+'" y="'+(h+10)+'" text-anchor="middle" fill="#9CA3AF" font-size="8">'+esc(v.d)+'</text>';
        }}).join('');
        priceChartHtml = '<div class="price-chart"><h3>Price History</h3>'
          + '<svg width="100%" viewBox="0 0 '+w+' '+(h+14)+'" preserveAspectRatio="xMidYMid meet">'
          + '<polyline points="'+pts+'" fill="none" stroke="#4B5563" stroke-width="2"/>'
          + labels + '</svg></div>';
      }}
    }}

    // No image in detail (user clicks thumbnail for fullscreen instead)
    const imgHtml = '';

    // Map (OpenStreetMap embed if coords available)
    let mapHtml = '';
    if (p.lat && p.lng) {{
      mapHtml = '<div class="detail-map">'
        + '<a href="https://www.google.com/maps?q='+p.lat+','+p.lng+'" target="_blank" rel="noopener" onclick="event.stopPropagation()">'
        + '<img src="https://staticmap.thisplace.org/map?center='+p.lat+','+p.lng+'&zoom=15&size=300x120&markers='+p.lat+','+p.lng+'" '
        + 'onerror="window._mapFallback(this,'+p.lat+','+p.lng+')" '
        + 'alt="Map" style="width:100%;height:120px;object-fit:cover;border-radius:8px">'
        + '</a></div>';
    }} else if (p.a) {{
      const mapQ = encodeURIComponent(p.a);
      mapHtml = '<div class="detail-map">'
        + '<iframe class="detail-map-frame" src="https://www.openstreetmap.org/export/embed.html?query='+mapQ+'" loading="lazy"></iframe>'
        + '</div>';
    }}

    // Same scheme properties
    let sameSchemeHtml = '';
    const scheme = schemeName(p.a, p.t, p.sn);
    if (scheme) {{
      const others = [];
      for (const [oid, op] of Object.entries(allProps)) {{
        if (oid === currentId || op.exp) continue;
        const os = schemeName(op.a, op.t, op.sn);
        if (os && os === scheme) others.push({{ id: oid, p: op }});
        if (others.length >= 10) break;
      }}
      if (others.length > 0) {{
        sameSchemeHtml = '<div class="detail-same-scheme"><h3>'+esc(scheme)+' — Other Auctions ('+others.length+')</h3>';
        for (const o of others) {{
          const od = daysUntil(o.p.ad);
          const odText = od <= 0 ? 'Today' : od + 'd';
          const ssId = 'ss-' + esc(o.id);
          const ssSize = o.p.s && o.p.s !== 'Size not specified' ? o.p.s : '';
          sameSchemeHtml += '<div class="same-scheme-item" data-ssid="'+ssId+'" onclick="event.stopPropagation();window._toggleSchemeDetail(this)">'
            + '<span class="ss-title">'+esc(o.p.t)+(ssSize ? ' <span class="ss-size">'+esc(ssSize)+'</span>' : '')+'</span>'
            + '<span class="ss-price">'+esc(o.p.p)+(o.p.d ? ' <span style="font-size:0.65rem;color:var(--green)">'+esc(o.p.d)+'</span>' : '')+'</span>'
            + '<span class="ss-date">'+esc(o.p.ad)+' ('+odText+')</span>'
            + '</div>'
            + '<div class="ss-expand" id="'+ssId+'" style="display:none">'
            + '<div class="ss-detail-row"><span class="ss-detail-label">Type</span><span class="ss-detail-value">'+esc(o.p.pt)+'</span></div>'
            + '<div class="ss-detail-row"><span class="ss-detail-label">Location</span><span class="ss-detail-value">'+esc(o.p.l)+'</span></div>'
            + (o.p.s && o.p.s !== 'Size not specified' ? '<div class="ss-detail-row"><span class="ss-detail-label">Size</span><span class="ss-detail-value">'+esc(o.p.s)+'</span></div>' : '')
            + (o.p.a ? '<div class="ss-detail-row"><span class="ss-detail-label">Address</span><span class="ss-detail-value" style="text-align:right;max-width:65%;font-size:0.7rem">'+esc(o.p.a)+'</span></div>' : '')
            + (o.p.u ? '<a class="ss-view-link" href="'+esc(o.p.u)+'" target="_blank" rel="noopener" onclick="event.stopPropagation()">View Listing &rarr;</a>' : '')
            + '</div>';
        }}
        sameSchemeHtml += '</div>';
      }}
    }}

    return '<div class="detail-top">'
      + imgHtml
      + '<div class="detail-info">'
      + '<div class="detail-row"><span class="detail-label">Price</span><span class="detail-value" style="font-weight:700">'+esc(p.p)+(p.d ? ' <span style="font-size:0.75rem;color:var(--green)">('+esc(p.d)+')</span>' : '')+'</span></div>'
      + '<div class="detail-row"><span class="detail-label">Auction</span><span class="detail-value">'+esc(p.ad)+' <span style="font-size:0.75rem">('+daysText+')</span></span></div>'
      + '<div class="detail-row"><span class="detail-label">Type</span><span class="detail-value">'+esc(p.pt)+'</span></div>'
      + (p.s && p.s !== 'Size not specified' ? '<div class="detail-row"><span class="detail-label">Size</span><span class="detail-value">'+esc(p.s)+'</span></div>' : '')
      + '</div></div>'
      + (p.a ? '<div class="detail-addr">'+esc(p.a)+'</div>' : '')
      + mapHtml
      + priceChartHtml
      + sameSchemeHtml
      + (p.u ? '<a class="card-link" href="'+esc(p.u)+'" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="display:block;text-align:center;padding:8px;margin-top:8px;background:#F3F4F6;border-radius:8px;font-weight:600;font-size:0.85rem;color:var(--text)">View Original Listing &rarr;</a>' : '');
  }}

  window._toggleSchemeDetail = function(el) {{
    var ssid = el.dataset.ssid;
    if (!ssid) return;
    var detail = document.getElementById(ssid);
    if (!detail) return;
    detail.style.display = detail.style.display === 'none' ? '' : 'none';
  }};

  window._showPhoto = function(src) {{
    var lb = document.getElementById('photo-lightbox');
    document.getElementById('photo-lightbox-img').src = src;
    lb.classList.add('open');
  }};

  window._mapFallback = function(img, lat, lng) {{
    var wrap = img.parentElement.parentElement;
    var f = document.createElement('iframe');
    f.className = 'detail-map-frame';
    f.src = 'https://www.openstreetmap.org/export/embed.html?bbox=' + (lng-0.01) + ',' + (lat-0.01) + ',' + (lng+0.01) + ',' + (lat+0.01) + '&marker=' + lat + ',' + lng + '&layer=mapnik';
    wrap.innerHTML = '';
    wrap.appendChild(f);
  }};

  window._openDetail = function(id) {{
    const p = allProps[id];
    if (!p) return;

    // Find the card that was clicked
    const card = document.querySelector('.card[data-id="'+CSS.escape(id)+'"]');
    if (!card) return;

    // If already expanded, collapse it
    const existing = card.querySelector('.card-expand');
    if (existing) {{
      existing.remove();
      card.classList.remove('expanded');
      return;
    }}

    // Collapse any other expanded card
    document.querySelectorAll('.card-expand').forEach(el => el.remove());
    document.querySelectorAll('.card.expanded').forEach(el => el.classList.remove('expanded'));

    // Create expansion panel
    const expandDiv = document.createElement('div');
    expandDiv.className = 'card-expand';
    expandDiv.innerHTML = buildDetailHtml(p, id);
    expandDiv.addEventListener('click', function(e) {{ e.stopPropagation(); }});
    card.appendChild(expandDiv);
    card.classList.add('expanded');
    // Scroll the expanded card into view
    setTimeout(function() {{ card.scrollIntoView({{ behavior: 'smooth', block: 'start' }}); }}, 50);
  }};

  // Table inline detail expansion
  window._toggleTableDetail = function(tr) {{
    const pid = tr.dataset.pid;
    const p = allProps[pid];
    if (!p) return;

    // Check if already expanded
    const existing = tr.nextElementSibling;
    if (existing && existing.classList.contains('table-detail-row')) {{
      existing.remove();
      return;
    }}

    // Remove any other open detail rows
    document.querySelectorAll('.table-detail-row').forEach(el => el.remove());

    // Insert detail row after current row
    const detailTr = document.createElement('tr');
    detailTr.className = 'table-detail-row';
    const td = document.createElement('td');
    td.colSpan = 8;
    td.innerHTML = '<div class="table-detail-content">' + buildDetailHtml(p) + '</div>';
    detailTr.appendChild(td);
    tr.after(detailTr);
  }};

  // Close expanded card on Escape
  document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') {{
      document.querySelectorAll('.card-expand').forEach(el => el.remove());
      document.querySelectorAll('.card.expanded').forEach(el => el.classList.remove('expanded'));
      document.querySelectorAll('.table-detail-row').forEach(el => el.remove());
    }}
  }});

  // --- Build filter chips ---
  function buildFilterChips(containerId, items, filterSet, onChange) {{
    const container = document.getElementById(containerId);
    let html = '';
    for (const item of items) {{
      html += '<button class="chip" data-val="'+esc(item)+'">'+esc(item)+'</button>';
    }}
    container.innerHTML = html;
    container.addEventListener('click', function(e) {{
      const chip = e.target.closest('.chip');
      if (!chip) return;
      const val = chip.dataset.val;
      if (filterSet.has(val)) {{
        filterSet.delete(val);
        chip.classList.remove('active');
      }} else {{
        filterSet.add(val);
        chip.classList.add('active');
      }}
      onChange();
    }});
  }}

  // --- Switch to search tab with filter ---
  function switchToSearch(opts) {{
    // Switch tab
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    const searchBtn = document.querySelector('[data-tab="search"]');
    searchBtn.classList.add('active');
    document.getElementById('tab-search').classList.add('active');

    // Clear existing filters
    activeFilters.types.clear();
    activeFilters.locs.clear();
    document.querySelectorAll('#filters-type .chip').forEach(c => c.classList.remove('active'));
    document.querySelectorAll('#filters-loc .chip').forEach(c => c.classList.remove('active'));

    // Apply type filter
    if (opts && opts.type) {{
      activeFilters.types.add(opts.type);
      document.querySelectorAll('#filters-type .chip').forEach(c => {{
        if (c.dataset.val === opts.type) c.classList.add('active');
      }});
    }}

    // Apply date range filter via search box
    if (opts && opts.dateRange) {{
      // Store week range for filtering
      window._weekFilter = opts.dateRange;
    }} else {{
      window._weekFilter = null;
    }}

    // Set status to active
    document.getElementById('filter-status').value = 'active';

    filterAndRender('all');
    window.scrollTo(0, 0);
  }}

  // --- Debounce ---
  function debounce(fn, ms) {{
    let timer;
    return function() {{
      clearTimeout(timer);
      timer = setTimeout(fn, ms);
    }};
  }}

  // --- Load data (inlined at build time) ---
  async function init() {{
    var stats = JSON.parse(document.getElementById('__stats__').textContent);
    var changes = JSON.parse(document.getElementById('__changes__').textContent);
    statsData = stats;
    changesData = changes;

    // Show loading overlay while fetching property data
    var loadingEl = document.getElementById('loading-overlay');
    if (loadingEl) loadingEl.style.display = 'flex';

    // Load property data asynchronously (avoid 4MB inline JSON blocking page load)
    var active;
    try {{
      var resp = await fetch('data/active.json');
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      active = await resp.json();
    }} catch(e) {{
      // Fallback: try inline data, or retry with absolute path
      try {{
        var inl = document.getElementById('__active__').textContent.trim();
        if (inl && inl !== 'null') {{
          active = JSON.parse(inl);
        }} else {{
          // Try with base path prefix (GitHub Pages)
          var base = document.querySelector('base');
          var prefix = base ? base.href : window.location.pathname.replace(/\/[^/]*$/, '/');
          var resp2 = await fetch(prefix + 'data/active.json');
          if (!resp2.ok) throw new Error('HTTP ' + resp2.status);
          active = await resp2.json();
        }}
      }} catch(e2) {{
        if (loadingEl) {{
          loadingEl.innerHTML = '<div style="text-align:center;padding:2rem"><p style="font-size:1.1rem;font-weight:600;margin-bottom:8px">Failed to load property data</p><p style="color:var(--text-sec);font-size:0.85rem">Try refreshing, or open via a web server (not file://)</p></div>';
        }}
        return;
      }}
    }}
    allProps = active || {{}};
    if (loadingEl) loadingEl.style.display = 'none';

      // Pre-compute search strings
      const allEntries = Object.entries(active);
      for (const [id, p] of allEntries) {{
        p._search = buildSearchString(p);
      }}

      // --- Dashboard: Type breakdown pie chart ---
      // Deduplicate active entries (prefer ones with size info)
      const _actSorted = allEntries.filter(([_, p]) => !p.exp).sort((a, b) => (a[1].sz ? 0 : 1) - (b[1].sz ? 0 : 1));
      const _actSeen = new Set();
      const activeEntries = _actSorted.filter(([_, p]) => {{
        const key = (p.t || '') + '|' + (p.pv || '') + '|' + (p.ad || '') + '|' + (p.a || '');
        if (_actSeen.has(key)) return false;
        _actSeen.add(key);
        return true;
      }});
      const typeCounts = {{}};
      for (const [_, p] of activeEntries) {{
        const t = p.pt || 'Other';
        typeCounts[t] = (typeCounts[t] || 0) + 1;
      }}
      const typeEntries = Object.entries(typeCounts).sort((a, b) => b[1] - a[1]);
      const totalActive = activeEntries.length;
      const pieColors = ['#2563EB', '#10B981', '#F59E0B', '#8B5CF6', '#EF4444', '#06B6D4', '#EC4899', '#6366F1'];

      // Draw pie chart on canvas
      const canvas = document.getElementById('pie-chart');
      if (canvas && canvas.getContext) {{
        const ctx = canvas.getContext('2d');
        const cx = 60, cy = 60, r = 55;
        let startAngle = -Math.PI / 2;
        typeEntries.forEach(([type, count], i) => {{
          const sliceAngle = (count / totalActive) * 2 * Math.PI;
          ctx.beginPath();
          ctx.moveTo(cx, cy);
          ctx.arc(cx, cy, r, startAngle, startAngle + sliceAngle);
          ctx.closePath();
          ctx.fillStyle = pieColors[i % pieColors.length];
          ctx.fill();
          startAngle += sliceAngle;
        }});
        // White center for donut effect
        ctx.beginPath();
        ctx.arc(cx, cy, r * 0.55, 0, 2 * Math.PI);
        ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--card-bg').trim() || '#fff';
        ctx.fill();
        // Center text
        ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--text').trim() || '#111';
        ctx.font = 'bold 16px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(totalActive.toLocaleString(), cx, cy - 6);
        ctx.font = '9px Inter, sans-serif';
        ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || '#888';
        ctx.fillText('active', cx, cy + 10);
      }}

      // Legend (clickable - switches to search with type filter)
      const legendEl = document.getElementById('type-legend');
      if (legendEl) {{
        legendEl.innerHTML = typeEntries.map(([type, count], i) => {{
          const pct = totalActive > 0 ? ((count / totalActive) * 100).toFixed(1) : '0';
          return '<div class="legend-item clickable" data-type="'+esc(type)+'" style="cursor:pointer">'
            + '<div class="legend-dot" style="background:'+pieColors[i % pieColors.length]+'"></div>'
            + '<span class="legend-label">'+esc(type)+'</span>'
            + '<span class="legend-count">'+count+'</span>'
            + '<span class="legend-pct">'+pct+'%</span>'
            + '</div>';
        }}).join('');
        legendEl.addEventListener('click', function(e) {{
          const item = e.target.closest('.legend-item');
          if (item && item.dataset.type) switchToSearch({{ type: item.dataset.type }});
        }});
      }}

      // Pie chart click detection
      if (canvas) {{
        canvas.style.cursor = 'pointer';
        canvas.addEventListener('click', function(e) {{
          const rect = canvas.getBoundingClientRect();
          const x = e.clientX - rect.left - 60;
          const y = e.clientY - rect.top - 60;
          const angle = Math.atan2(y, x);
          const dist = Math.sqrt(x*x + y*y);
          if (dist < 55 * 0.55 || dist > 55) return; // clicked center or outside
          let normAngle = angle + Math.PI / 2;
          if (normAngle < 0) normAngle += 2 * Math.PI;
          let cumAngle = 0;
          for (const [type, count] of typeEntries) {{
            cumAngle += (count / totalActive) * 2 * Math.PI;
            if (normAngle <= cumAngle) {{
              switchToSearch({{ type: type }});
              return;
            }}
          }}
        }});
      }}

      // --- Dashboard: Auctions by week chart ---
      const weekData = {{}};
      const now = new Date();
      const weekStart = new Date(now); weekStart.setDate(now.getDate() - now.getDay() + 1); // Monday
      weekStart.setHours(0,0,0,0);
      // Build 8 weeks
      for (let w = 0; w < 8; w++) {{
        const wStart = new Date(weekStart); wStart.setDate(weekStart.getDate() + w * 7);
        const wEnd = new Date(wStart); wEnd.setDate(wStart.getDate() + 6);
        const label = wStart.toLocaleDateString('en-GB', {{ day: 'numeric', month: 'short' }})
          + ' - ' + wEnd.toLocaleDateString('en-GB', {{ day: 'numeric', month: 'short' }});
        weekData[label] = {{ start: wStart, end: wEnd, count: 0 }};
      }}
      for (const [_, p] of activeEntries) {{
        const ad = parseAuctionDate(p.ad);
        if (!ad) continue;
        for (const [label, w] of Object.entries(weekData)) {{
          if (ad >= w.start && ad <= w.end) {{
            w.count++;
            break;
          }}
        }}
      }}
      const weekEntries = Object.entries(weekData);
      const maxWeek = Math.max(...weekEntries.map(([_, w]) => w.count), 1);
      const weekEl = document.getElementById('week-chart');
      if (weekEl) {{
        weekEl.innerHTML = weekEntries.map(([label, w], idx) => {{
          const pct = (w.count / maxWeek * 100).toFixed(0);
          const isThisWeek = w.start <= now && now <= w.end;
          const barColor = isThisWeek ? 'var(--accent)' : '#93C5FD';
          return '<div class="week-bar-row clickable" data-week="'+idx+'" style="cursor:pointer">'
            + '<span class="week-label"'+(isThisWeek ? ' style="font-weight:600;color:var(--accent)"' : '')+'>'+esc(label)+'</span>'
            + '<div class="week-bar-bg"><div class="week-bar-fill" style="width:'+pct+'%;background:'+barColor+'"></div></div>'
            + '<span class="week-bar-count">'+w.count+'</span>'
            + '</div>';
        }}).join('');
        weekEl.addEventListener('click', function(e) {{
          const row = e.target.closest('.week-bar-row');
          if (!row) return;
          const idx = parseInt(row.dataset.week);
          const [, w] = weekEntries[idx];
          if (w && w.count > 0) switchToSearch({{ dateRange: {{ start: w.start, end: w.end }} }});
        }});
      }}

      // --- Dashboard: Hot deals ---
      const hotDeals = activeEntries
        .filter(([_, p]) => p.d)
        .sort((a, b) => parseDiscount(b[1].d) - parseDiscount(a[1].d))
        .slice(0, 5);
      const hotContainer = document.getElementById('hot-deals');
      if (hotDeals.length) {{
        hotContainer.innerHTML = hotDeals.map(([id, p]) => renderCard(id, p)).join('');
      }} else {{
        hotContainer.innerHTML = '<div class="empty"><p>No price drop data available yet</p></div>';
      }}

      // --- Dashboard: Notable listings (multi-round auctions with price drops) ---
      function notableScore(p) {{
        let score = 0;
        const hist = p.hist || [];
        const ph = p.ph || [];
        // More auction rounds = more notable
        if (hist.length > 1) score += hist.length * 10;
        // Price drop from first to last
        if (ph.length >= 2) {{
          const parseP = s => {{ const m = String(s).match(/[\d,]+/); return m ? parseInt(m[0].replace(/,/g,'')) : 0; }};
          const first = parseP(ph[0].p);
          const last = parseP(ph[ph.length-1].p);
          if (first > 0 && last > 0 && last < first) {{
            const dropPct = (first - last) / first * 100;
            score += dropPct * 2;
          }}
        }}
        // Has discount info
        if (p.d) score += 15;
        return score;
      }}
      const seenNotable = new Set();
      const notable = activeEntries
        .filter(([id, p]) => {{
          if (p.exp) return false;
          const s = notableScore(p);
          if (s <= 0) return false;
          const key = (p.t || '') + '|' + (p.pv || '') + '|' + (p.ad || '');
          if (seenNotable.has(key)) return false;
          seenNotable.add(key);
          return true;
        }})
        .sort((a, b) => notableScore(b[1]) - notableScore(a[1]))
        .slice(0, 8);
      const notableContainer = document.getElementById('notable-cards');
      if (notable.length) {{
        notableContainer.innerHTML = notable.map(([id, p]) => {{
          const hist = p.hist || [];
          const ph = p.ph || [];
          let badge = '';
          if (hist.length > 1) badge = hist.length + ' rounds';
          if (ph.length >= 2) {{
            const parseP = s => {{ const m = String(s).match(/[\d,]+/); return m ? parseInt(m[0].replace(/,/g,'')) : 0; }};
            const first = parseP(ph[0].p);
            const last = parseP(ph[ph.length-1].p);
            if (first > 0 && last > 0 && last < first) {{
              const dropPct = ((first - last) / first * 100).toFixed(0);
              badge += (badge ? ', ' : '') + dropPct + '% lower';
            }}
          }}
          return renderCard(id, p, {{ isChanged: false, isNew: false, changes: [], notableBadge: badge }});
        }}).join('');
      }} else {{
        notableContainer.innerHTML = '<div class="empty"><p>No notable listings found</p></div>';
      }}

      // --- Dashboard: Scan history ---
      const historyContainer = document.getElementById('scan-history');
      const history = stats.scan_history || [];
      if (history.length) {{
        historyContainer.innerHTML = history.slice(-15).reverse().map(h =>
          '<div class="history-row">'
          + '<span class="history-date">'+esc(h.d)+'</span>'
          + '<div class="history-stats">'
          + '<span class="history-new">+'+h.n+' new</span>'
          + '<span class="history-changed">'+h.c+' changed</span>'
          + '</div></div>'
        ).join('');
      }}

      // --- New listings tab ---
      const newIds = new Set(changes.new_ids || []);
      const newItems = [];
      for (const id of newIds) {{
        if (active[id]) {{
          newItems.push({{ id, prop: active[id], _search: active[id]._search, opts: {{ isNew: true }} }});
        }}
      }}
      views.new.sourceItems = newItems;
      filterAndRender('new');

      // --- Changes tab ---
      const changeRecords = changes.changes || [];
      const changesByProp = {{}};
      for (const c of changeRecords) {{
        const pid = c.property_id || '';
        if (!changesByProp[pid]) changesByProp[pid] = [];
        changesByProp[pid].push(c);
      }}
      const changedItems = [];
      for (const [pid, chgs] of Object.entries(changesByProp)) {{
        if (active[pid]) {{
          changedItems.push({{ id: pid, prop: active[pid], _search: active[pid]._search, opts: {{ isChanged: true, changes: chgs }} }});
        }}
      }}
      views.changes.sourceItems = changedItems;
      filterAndRender('changes');

      // --- Search/browse tab (deduplicated) ---
      // Prefer entries with size info; dedup by title+price+auction_date+address
      const allSorted = allEntries.slice().sort((a, b) => {{
        const aHas = a[1].sz ? 0 : 1;
        const bHas = b[1].sz ? 0 : 1;
        return aHas - bHas;
      }});
      const seenAll = new Set();
      const allItems = allSorted.filter(([id, p]) => {{
        const key = (p.t || '') + '|' + (p.pv || '') + '|' + (p.ad || '') + '|' + (p.a || '');
        if (seenAll.has(key)) return false;
        seenAll.add(key);
        return true;
      }}).map(([id, p]) => ({{ id, prop: p, _search: p._search }}));
      views.all.sourceItems = allItems;

      // --- Table tab ---
      views.table.sourceItems = allItems;
      filterTable();

      // Build filter chips
      buildFilterChips('filters-type', stats.types || [], activeFilters.types, () => filterAndRender('all'));
      buildFilterChips('filters-loc', stats.locations || [], activeFilters.locs, () => filterAndRender('all'));

      // Build type filter chips for new tab
      const newTypes = [...new Set(newItems.map(i => i.prop.pt).filter(Boolean))].sort();
      const newTypeFilters = new Set();
      const filtersNewEl = document.getElementById('filters-new');
      if (newTypes.length > 1) {{
        buildFilterChips('filters-new', newTypes, newTypeFilters, function() {{
          // Re-filter new items with type filter
          if (newTypeFilters.size > 0) {{
            views.new.sourceItems = newItems.filter(i => newTypeFilters.has(i.prop.pt));
          }} else {{
            views.new.sourceItems = newItems;
          }}
          filterAndRender('new');
        }});
      }}

      filterAndRender('all');

      // --- Wire up search inputs ---
      const searchNew = document.getElementById('search-new');
      const searchChanges = document.getElementById('search-changes');
      const searchAll = document.getElementById('search-all');
      if (searchNew) searchNew.addEventListener('input', debounce(() => filterAndRender('new'), 300));
      if (searchChanges) searchChanges.addEventListener('input', debounce(() => filterAndRender('changes'), 300));
      if (searchAll) searchAll.addEventListener('input', debounce(() => filterAndRender('all'), 300));

      // --- Wire up sort ---
      const sortNew = document.getElementById('sort-new');
      const sortAll = document.getElementById('sort-all');
      if (sortNew) sortNew.addEventListener('change', () => filterAndRender('new'));
      if (sortAll) sortAll.addEventListener('change', () => filterAndRender('all'));

      // --- Wire up filters ---
      document.getElementById('filter-status').addEventListener('change', () => filterAndRender('all'));
      document.getElementById('filter-price-min').addEventListener('input', debounce(() => filterAndRender('all'), 500));
      document.getElementById('filter-price-max').addEventListener('input', debounce(() => filterAndRender('all'), 500));
      document.getElementById('filter-size-min').addEventListener('input', debounce(() => filterAndRender('all'), 500));
      document.getElementById('filter-size-max').addEventListener('input', debounce(() => filterAndRender('all'), 500));
      document.getElementById('filter-date-range').addEventListener('change', () => filterAndRender('all'));
      document.getElementById('filter-discount').addEventListener('change', () => filterAndRender('all'));
      document.getElementById('filter-reset').addEventListener('click', function() {{
        activeFilters.types.clear();
        activeFilters.locs.clear();
        document.querySelectorAll('#filters-type .chip, #filters-loc .chip').forEach(c => c.classList.remove('active'));
        document.getElementById('filter-status').value = 'active';
        document.getElementById('filter-price-min').value = '';
        document.getElementById('filter-price-max').value = '';
        document.getElementById('filter-size-min').value = '';
        document.getElementById('filter-size-max').value = '';
        document.getElementById('filter-date-range').value = '';
        document.getElementById('filter-discount').value = '';
        document.getElementById('search-all').value = '';
        document.getElementById('sort-all').value = 'price_asc';
        window._weekFilter = null;
        filterAndRender('all');
      }});

      // --- Wire up load more ---
      document.getElementById('more-new').addEventListener('click', () => loadMore('new'));
      document.getElementById('more-changes').addEventListener('click', () => loadMore('changes'));
      document.getElementById('more-all').addEventListener('click', () => loadMore('all'));

      // --- Map tab (lazy init) ---
      let mapInited = false;
      let leafletMap = null;
      let markerCluster = null;

      // Populate map type filter
      const mapTypeSelect = document.getElementById('map-filter-type');
      if (mapTypeSelect) {{
        const types = [...new Set(allEntries.map(([_,p]) => p.pt).filter(Boolean))].sort();
        types.forEach(t => {{
          const opt = document.createElement('option');
          opt.value = t;
          opt.textContent = t;
          mapTypeSelect.appendChild(opt);
        }});
      }}

      function initMap() {{
        if (mapInited) return;
        mapInited = true;
        leafletMap = L.map('property-map').setView([3.139, 101.6869], 10);
        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
          maxZoom: 19
        }}).addTo(leafletMap);
        markerCluster = L.markerClusterGroup({{ chunkedLoading: true, maxClusterRadius: 50 }});
        leafletMap.addLayer(markerCluster);
        refreshMapMarkers();

        document.getElementById('map-filter-type').addEventListener('change', refreshMapMarkers);
        document.getElementById('map-filter-status').addEventListener('change', refreshMapMarkers);
      }}

      function refreshMapMarkers() {{
        if (!markerCluster) return;
        markerCluster.clearLayers();
        const typeFilter = document.getElementById('map-filter-type').value;
        const statusFilter = document.getElementById('map-filter-status').value;
        let count = 0;
        const markers = [];
        for (const [id, p] of allEntries) {{
          if (!p.lat || !p.lng) continue;
          if (typeFilter && p.pt !== typeFilter) continue;
          if (statusFilter === 'active' && p.exp) continue;
          if (statusFilter === 'expired' && !p.exp) continue;
          const scheme = schemeName(p.a, p.t, p.sn);
          const title = scheme || p.a || p.t;
          const marker = L.marker([p.lat, p.lng]);
          marker.bindPopup(
            '<div style="min-width:180px">'
            + '<strong style="font-size:0.85rem">'+esc(title)+'</strong>'
            + '<div style="font-weight:700;margin:4px 0">'+esc(p.p)+'</div>'
            + '<div style="font-size:0.75rem;color:#4B5563">'
            + (p.pt ? '<span style="background:#F3F4F6;padding:2px 6px;border-radius:4px;margin-right:4px">'+esc(p.pt)+'</span>' : '')
            + (p.s && p.s !== 'Size not specified' ? esc(p.s) : '')
            + '</div>'
            + '<div style="font-size:0.72rem;color:#4B5563;margin-top:4px">'+esc(p.ad)+'</div>'
            + (p.u ? '<a href="'+esc(p.u)+'" target="_blank" rel="noopener" style="font-size:0.75rem;color:#111827;text-decoration:underline;display:block;margin-top:6px">View Listing &rarr;</a>' : '')
            + '</div>'
          );
          markers.push(marker);
          count++;
        }}
        markerCluster.addLayers(markers);
        document.getElementById('map-count').textContent = count + ' properties on map';
      }}

      // Lazy-init map when tab clicked
      const origTabHandler = document.getElementById('tab-bar');
      origTabHandler.addEventListener('click', function(e) {{
        const btn = e.target.closest('.tab');
        if (btn && btn.dataset.tab === 'map') {{
          setTimeout(function() {{
            initMap();
            if (leafletMap) leafletMap.invalidateSize();
          }}, 100);
        }}
      }});

      // --- Bookmark filter system ---
      const BM_KEY = 'lelongtips_bookmarks';

      function parseFilterQuery(query) {{
        const q = query.toLowerCase().trim();
        const filter = {{ label: query, search: '' }};

        // Type detection
        const typeMap = {{
          'landed': 'Landed', 'house': 'Landed', 'houses': 'Landed', 'bungalow': 'Landed',
          'terrace': 'Landed', 'semi-d': 'Landed', 'semi detached': 'Landed',
          'condo': 'High-rise', 'condos': 'High-rise', 'condominium': 'High-rise',
          'apartment': 'High-rise', 'high-rise': 'High-rise', 'highrise': 'High-rise',
          'flat': 'High-rise', 'soho': 'High-rise',
          'commercial': 'Commercial', 'shop': 'Commercial', 'office': 'Commercial', 'retail': 'Commercial',
          'industrial': 'Industrial', 'factory': 'Industrial', 'warehouse': 'Industrial',
          'land': 'Land',
        }};
        for (const [keyword, type] of Object.entries(typeMap)) {{
          if (q.includes(keyword)) {{
            filter.type = type;
            break;
          }}
        }}

        // Price extraction
        const pricePatterns = [
          /under\s+(?:rm\s*)?(\d[\d,.]*)\s*(k|m)?/i,
          /below\s+(?:rm\s*)?(\d[\d,.]*)\s*(k|m)?/i,
          /less\s+than\s+(?:rm\s*)?(\d[\d,.]*)\s*(k|m)?/i,
          /max\s+(?:rm\s*)?(\d[\d,.]*)\s*(k|m)?/i,
          /above\s+(?:rm\s*)?(\d[\d,.]*)\s*(k|m)?/i,
          /over\s+(?:rm\s*)?(\d[\d,.]*)\s*(k|m)?/i,
          /more\s+than\s+(?:rm\s*)?(\d[\d,.]*)\s*(k|m)?/i,
          /min\s+(?:rm\s*)?(\d[\d,.]*)\s*(k|m)?/i,
          /(\d[\d,.]*)\s*(k|m)?\s*(?:to|-)\s*(?:rm\s*)?(\d[\d,.]*)\s*(k|m)?/i,
        ];

        function parseNum(n, unit) {{
          let v = parseFloat(n.replace(/,/g, ''));
          if (unit === 'k' || unit === 'K') v *= 1000;
          if (unit === 'm' || unit === 'M') v *= 1000000;
          return v;
        }}

        // Range pattern (e.g., "200k to 500k")
        const rangeMatch = q.match(/(?:rm\s*)?(\d[\d,.]*)\s*(k|m)?\s*(?:to|-)\s*(?:rm\s*)?(\d[\d,.]*)\s*(k|m)?/i);
        if (rangeMatch) {{
          filter.minPrice = parseNum(rangeMatch[1], rangeMatch[2]);
          filter.maxPrice = parseNum(rangeMatch[3], rangeMatch[4]);
        }} else {{
          // Under/below
          const underMatch = q.match(/(?:under|below|less\s+than|max|budget)\s+(?:rm\s*)?(\d[\d,.]*)\s*(k|m)?/i);
          if (underMatch) filter.maxPrice = parseNum(underMatch[1], underMatch[2]);
          // Above/over
          const overMatch = q.match(/(?:above|over|more\s+than|min|from)\s+(?:rm\s*)?(\d[\d,.]*)\s*(k|m)?/i);
          if (overMatch) filter.minPrice = parseNum(overMatch[1], overMatch[2]);
        }}

        // Location detection (states + common cities/areas)
        const locations = ['kuala lumpur', 'kl', 'selangor', 'johor', 'penang', 'perak',
          'kedah', 'kelantan', 'terengganu', 'pahang', 'negeri sembilan', 'melaka',
          'sabah', 'sarawak', 'putrajaya', 'labuan', 'kl/selangor',
          'petaling jaya', 'shah alam', 'subang jaya', 'puchong', 'ampang',
          'cheras', 'kepong', 'setapak', 'wangsa maju', 'bangsar',
          'mont kiara', 'damansara', 'cyberjaya', 'kajang', 'semenyih',
          'rawang', 'klang', 'johor bahru', 'ipoh', 'george town',
          'kota kinabalu', 'kuching', 'seremban', 'melaka', 'alor setar'];
        // Sort by length descending so longer names match first (e.g., "petaling jaya" before "jaya")
        locations.sort((a, b) => b.length - a.length);
        for (const loc of locations) {{
          if (q.includes(loc)) {{
            filter.location = loc === 'kl' ? 'Kuala Lumpur' : loc.split(' ').map(w => w[0].toUpperCase() + w.slice(1)).join(' ');
            // For city-level locations, use as search text since they appear in address, not location field
            if (!['kuala lumpur', 'kl', 'selangor', 'johor', 'penang', 'perak', 'kedah', 'kelantan',
              'terengganu', 'pahang', 'negeri sembilan', 'melaka', 'sabah', 'sarawak', 'putrajaya', 'labuan', 'kl/selangor'].includes(loc)) {{
              filter.citySearch = loc;
            }}
            break;
          }}
        }}

        // Remaining text as search keywords (strip parsed parts)
        let remainder = q;
        // Strip recognized tokens
        for (const key of Object.keys(typeMap)) remainder = remainder.replace(new RegExp('\\\\b' + key + 's?\\\\b', 'gi'), '');
        remainder = remainder.replace(/\b(?:under|below|above|over|less|more|than|max|min|from|budget|rm|in)\b\s*/gi, '');
        remainder = remainder.replace(/\d[\d,.]*\s*[km]?\s*(?:to|-)\s*\d[\d,.]*\s*[km]?/gi, '');
        remainder = remainder.replace(/\d[\d,.]*\s*[km]?/gi, '');
        for (const loc of locations) remainder = remainder.replace(new RegExp(loc, 'gi'), '');
        remainder = remainder.replace(/\s+/g, ' ').trim();
        if (remainder.length > 2) filter.search = remainder;

        return filter;
      }}

      function loadBookmarks() {{
        try {{ return JSON.parse(localStorage.getItem(BM_KEY)) || []; }}
        catch {{ return []; }}
      }}

      function saveBookmarks(bms) {{
        localStorage.setItem(BM_KEY, JSON.stringify(bms));
      }}

      function countMatchingItems(filter) {{
        let items = allItems.filter(i => !i.prop.exp);
        if (filter.type) items = items.filter(i => i.prop.pt === filter.type);
        if (filter.minPrice) items = items.filter(i => (i.prop.pv || 0) >= filter.minPrice);
        if (filter.maxPrice) items = items.filter(i => (i.prop.pv || 0) <= filter.maxPrice);
        if (filter.location && !filter.citySearch) {{
          const loc = filter.location.toLowerCase();
          items = items.filter(i => (i.prop.l || '').toLowerCase().includes(loc));
        }}
        // City-level search matches against address/search string
        if (filter.citySearch) {{
          const city = filter.citySearch.toLowerCase();
          items = items.filter(i => (i._search || '').includes(city));
        }}
        if (filter.search) {{
          const tokens = filter.search.toLowerCase().split(/\s+/);
          items = items.filter(i => tokens.every(t => (i._search || '').includes(t)));
        }}
        return items.length;
      }}

      function applyBookmark(filter) {{
        // Clear existing
        activeFilters.types.clear();
        activeFilters.locs.clear();
        document.querySelectorAll('#filters-type .chip, #filters-loc .chip').forEach(c => c.classList.remove('active'));
        window._weekFilter = null;

        // Apply type
        if (filter.type) {{
          activeFilters.types.add(filter.type);
          document.querySelectorAll('#filters-type .chip').forEach(c => {{
            if (c.dataset.val === filter.type) c.classList.add('active');
          }});
        }}

        // Apply price
        document.getElementById('filter-price-min').value = filter.minPrice || '';
        document.getElementById('filter-price-max').value = filter.maxPrice || '';

        // Apply search text (include city name if city-level search)
        const searchParts = [];
        if (filter.citySearch) searchParts.push(filter.citySearch);
        if (filter.search) searchParts.push(filter.search);
        document.getElementById('search-all').value = searchParts.join(' ');

        // Reset new filters
        document.getElementById('filter-size-min').value = '';
        document.getElementById('filter-size-max').value = '';
        document.getElementById('filter-date-range').value = '';
        document.getElementById('filter-discount').value = '';

        // Set status to active
        document.getElementById('filter-status').value = 'active';

        // Switch to search tab
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
        document.querySelector('[data-tab="search"]').classList.add('active');
        document.getElementById('tab-search').classList.add('active');

        filterAndRender('all');
        window.scrollTo(0, 0);
      }}

      function renderBookmarks() {{
        const bms = loadBookmarks();
        const container = document.getElementById('bm-list');
        if (!bms.length) {{
          container.innerHTML = '<span style="font-size:0.75rem;color:var(--text-muted)">No saved filters yet. Click + to add one.</span>';
          return;
        }}
        container.innerHTML = bms.map((bm, i) => {{
          const count = countMatchingItems(bm);
          return '<div class="bm-chip" data-idx="'+i+'">'
            + '<span class="bm-text">'+esc(bm.label)+'</span>'
            + '<span class="bm-count">'+count+'</span>'
            + '<span class="bm-delete" data-del="'+i+'" title="Delete">&times;</span>'
            + '</div>';
        }}).join('');
      }}

      // Bookmark UI events
      document.getElementById('bm-add').addEventListener('click', function() {{
        const wrap = document.getElementById('bm-input-wrap');
        wrap.style.display = wrap.style.display === 'none' ? '' : 'none';
        if (wrap.style.display !== 'none') document.getElementById('bm-query').focus();
      }});

      document.getElementById('bm-query').addEventListener('input', debounce(function() {{
        const q = this.value.trim();
        if (!q) {{ document.getElementById('bm-preview').style.display = 'none'; return; }}
        const filter = parseFilterQuery(q);
        const parts = [];
        if (filter.type) parts.push('Type: ' + filter.type);
        if (filter.minPrice) parts.push('Min: RM' + filter.minPrice.toLocaleString());
        if (filter.maxPrice) parts.push('Max: RM' + filter.maxPrice.toLocaleString());
        if (filter.location) parts.push('Location: ' + filter.location);
        if (filter.search) parts.push('Keywords: ' + filter.search);
        const count = countMatchingItems(filter);
        const preview = document.getElementById('bm-preview');
        preview.style.display = '';
        preview.innerHTML = parts.join(' &middot; ') + ' &mdash; <strong>' + count + ' listings</strong>';
      }}, 300));

      document.getElementById('bm-save').addEventListener('click', function() {{
        const q = document.getElementById('bm-query').value.trim();
        if (!q) return;
        const filter = parseFilterQuery(q);
        const bms = loadBookmarks();
        bms.push(filter);
        saveBookmarks(bms);
        document.getElementById('bm-query').value = '';
        document.getElementById('bm-preview').style.display = 'none';
        document.getElementById('bm-input-wrap').style.display = 'none';
        renderBookmarks();
      }});

      document.getElementById('bm-query').addEventListener('keydown', function(e) {{
        if (e.key === 'Enter') document.getElementById('bm-save').click();
      }});

      document.getElementById('bm-list').addEventListener('click', function(e) {{
        const del = e.target.closest('.bm-delete');
        if (del) {{
          e.stopPropagation();
          const idx = parseInt(del.dataset.del);
          const bms = loadBookmarks();
          bms.splice(idx, 1);
          saveBookmarks(bms);
          renderBookmarks();
          return;
        }}
        const chip = e.target.closest('.bm-chip');
        if (chip) {{
          const idx = parseInt(chip.dataset.idx);
          const bms = loadBookmarks();
          if (bms[idx]) applyBookmark(bms[idx]);
        }}
      }});

      renderBookmarks();

  }}

  init();
}})();
</script>
</body>
</html>"""


if __name__ == "__main__":
    generate_page()
