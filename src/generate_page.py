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


def trim_property(prop):
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

    return {
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


def write_data_files(properties, changes_history, daily_stats):
    """Write separate JSON data files for the dashboard."""
    data_dir = os.path.join(DOCS_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)

    active = get_active_properties(properties)

    # active.json - trimmed active listings
    active_data = {}
    for pid, p in active.items():
        active_data[pid] = trim_property(p)

    with open(os.path.join(data_dir, "active.json"), "w") as f:
        json.dump(active_data, f, separators=(",", ":"))
    print(f"  active.json: {len(active_data)} properties")

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

    # Collect unique types and locations for filters
    types_set = set()
    locs_set = set()
    for p in active_data.values():
        if p["pt"]:
            types_set.add(p["pt"])
        if p["l"]:
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
  color: var(--accent);
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
.pill.type {{ background: var(--accent-light); color: var(--accent); }}
.pill.loc {{ background: #F3F4F6; color: var(--text-sec); }}
.pill.size {{ background: var(--green-light); color: var(--green); }}
.pill.date {{ background: var(--orange-light); color: var(--orange); }}
.pill.date.urgent {{ background: var(--red-light); color: var(--red); font-weight: 600; }}
.pill.discount {{ background: var(--green-light); color: var(--green); font-weight: 600; }}
.card-address {{
  color: var(--text-muted);
  font-size: 0.75rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.card-link {{
  display: inline-block;
  color: var(--accent);
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
  -webkit-overflow-scrolling: touch;
  margin: 0 -16px;
  padding: 0 16px;
}}
.data-table {{
  width: 100%;
  min-width: 700px;
  border-collapse: collapse;
  font-size: 0.8rem;
  background: var(--card-bg);
  border-radius: 10px;
  overflow: hidden;
  box-shadow: var(--shadow);
}}
.data-table thead {{ position: sticky; top: 42px; z-index: 50; }}
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
<div class="container">
  <header>
    <h1>Lelong<span>Tips</span></h1>
    <div class="scan-info">Last scan<br><strong>{esc(scan_date_display)} MYT</strong></div>
  </header>

  <div class="stats">
    <div class="stat s-blue">
      <div class="label">Active Listings</div>
      <div class="value blue" id="stat-active">{stats['active_count']:,}</div>
    </div>
    <div class="stat s-green">
      <div class="label">New (Latest)</div>
      <div class="value green" id="stat-new">{stats['new_count']}</div>
    </div>
    <div class="stat s-orange">
      <div class="label">Price Drops</div>
      <div class="value orange" id="stat-drops">{stats['drop_count']}</div>
    </div>
    <div class="stat s-purple">
      <div class="label">Avg Price</div>
      <div class="value purple" id="stat-avg">RM{stats['avg_price']:,}</div>
    </div>
  </div>

  <div class="tabs" id="tab-bar">
    <button class="tab active" data-tab="dashboard">Dashboard</button>
    <button class="tab" data-tab="new">New <span class="badge-count green">{stats['new_count']}</span></button>
    <button class="tab" data-tab="changes">Changes <span class="badge-count orange">{stats['changed_count']}</span></button>
    <button class="tab" data-tab="search">Search</button>
    <button class="tab" data-tab="table">Table</button>
  </div>

  <div id="tab-dashboard" class="tab-content active">
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
      Upcoming Auctions — Next 7 Days
    </div>
    <div id="upcoming">
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
      <input type="text" class="search-bar" id="search-all" placeholder="Search all active listings...">
    </div>
    <div class="filters" id="filters-type"></div>
    <div class="filters" id="filters-loc"></div>
    <div class="sort-row">
      <label>Sort:</label>
      <select class="sort-select" id="sort-all">
        <option value="price_asc">Price: Low to High</option>
        <option value="price_desc">Price: High to Low</option>
        <option value="date_asc">Auction Date</option>
        <option value="discount">Biggest Discount</option>
      </select>
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

  <footer>
    LelongTips Property Monitor &middot; Auto-updated every 3 days
  </footer>
</div>

<!-- Detail Modal -->
<div class="modal-backdrop" id="modal-backdrop">
  <div class="modal" id="modal">
    <div class="modal-handle"></div>
    <div id="modal-content"></div>
  </div>
</div>

<script id="__stats__" type="application/json">{inline_stats}</script>
<script id="__active__" type="application/json">{inline_active}</script>
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
  function schemeName(addr, title) {{
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
      ? '<img src="'+esc(p.img)+'" alt="" loading="lazy">'
      : getTypeIcon(p.pt);
    const discountHtml = p.d ? '<span class="pill discount">'+esc(p.d)+'</span>' : '';
    const spark = sparkline(p.ph);

    let badgeHtml = '';
    if (opts.isNew) badgeHtml = '<span class="card-badge new">NEW</span>';
    if (opts.isChanged) badgeHtml = '<span class="card-badge changed">CHANGED</span>';

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

    const scheme = schemeName(p.a, p.t);
    const displayTitle = scheme || p.a || p.t;

    return '<div class="card" data-id="'+esc(id)+'" onclick="window._openDetail(this.dataset.id)">'
      + '<div class="card-top">'
      + '<div class="card-img">'+imgHtml+'</div>'
      + '<div class="card-body">'
      + '<div class="card-header"><div class="card-title">'+esc(displayTitle)+badgeHtml+'</div><div class="card-price">'+esc(p.p)+spark+'</div></div>'
      + '<div class="card-meta">'
      + (p.pt ? '<span class="pill type">'+esc(p.pt)+'</span>' : '')
      + '<span class="pill loc">'+esc(p.l)+'</span>'
      + (p.s && p.s !== 'Size not specified' ? '<span class="pill size">'+esc(p.s)+'</span>' : '')
      + '<span class="pill date'+urgentClass+'">'+esc(p.ad)+' ('+daysText+')</span>'
      + discountHtml
      + '</div>'
      + (p.a && p.a !== p.t ? '<div class="card-address">'+esc(p.a)+'</div>' : '')
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
  function sortItems(items, sortBy) {{
    const sorters = {{
      price_asc: (a, b) => (a.prop.pv || 0) - (b.prop.pv || 0),
      price_desc: (a, b) => (b.prop.pv || 0) - (a.prop.pv || 0),
      date_asc: (a, b) => daysUntil(a.prop.ad) - daysUntil(b.prop.ad),
      discount: (a, b) => parseDiscount(b.prop.d) - parseDiscount(a.prop.d),
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

    // Type/location filters (search tab only)
    if (viewName === 'all') {{
      if (activeFilters.types.size > 0) {{
        items = items.filter(item => activeFilters.types.has(item.prop.pt));
      }}
      if (activeFilters.locs.size > 0) {{
        items = items.filter(item => activeFilters.locs.has(item.prop.l));
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
      const daysText = days <= 0 ? 'Today' : days === 1 ? '1d' : days + 'd';
      const urgClass = days <= 7 ? ' urgent' : '';
      const hist = p.hist || [];
      const hasHist = hist.length > 1;
      const rowId = 'tr-' + i;
      const expandBtn = hasHist
        ? '<button class="expand-btn" data-row="'+rowId+'" title="'+hist.length+' rounds">&#9654; '+hist.length+'</button>'
        : '';
      const scheme = schemeName(p.a, p.t);
      const nameHtml = scheme
        ? esc(scheme) + '<span class="td-scheme">'+esc(p.t)+'</span>'
        : esc(p.a || p.t);
      html += '<tr class="'+urgClass+'" id="'+rowId+'">'
        + '<td class="td-title" onclick="window._openDetail(\\\''+esc(item.id)+'\\\')">'+ expandBtn + nameHtml+'</td>'
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

  // --- Detail Modal ---
  window._openDetail = function(id) {{
    const p = allProps[id];
    if (!p) return;
    const days = daysUntil(p.ad);
    const daysText = days <= 0 ? 'Today' : days === 1 ? 'Tomorrow' : 'in ' + days + ' days';

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
        const w = 280, h = 80;
        const pts = vals.map((v, i) => {{
          const x = 10 + (i / (vals.length - 1)) * (w - 20);
          const y = h - 10 - ((v.v - min) / range) * (h - 20);
          return x.toFixed(1) + ',' + y.toFixed(1);
        }}).join(' ');
        const labels = vals.map((v, i) => {{
          const x = 10 + (i / (vals.length - 1)) * (w - 20);
          return '<text x="'+x.toFixed(1)+'" y="'+(h+12)+'" text-anchor="middle" fill="#9CA3AF" font-size="9">'+esc(v.d)+'</text>'
            + '<text x="'+x.toFixed(1)+'" y="'+(h - 10 - ((v.v - min) / range) * (h - 20) - 6).toFixed(1)+'" text-anchor="middle" fill="#4B5563" font-size="9">'+esc(v.p)+'</text>';
        }}).join('');
        priceChartHtml = '<div class="price-chart"><h3>Price History</h3>'
          + '<svg width="100%" viewBox="0 0 '+w+' '+(h+20)+'" preserveAspectRatio="xMidYMid meet">'
          + '<polyline points="'+pts+'" fill="none" stroke="#2563EB" stroke-width="2"/>'
          + labels + '</svg></div>';
      }}
    }}

    const imgHtml = p.img
      ? '<img src="'+esc(p.img)+'" style="width:100%;border-radius:10px;margin-bottom:12px" alt="">'
      : '';

    const modalScheme = schemeName(p.a, p.t);
    const modalTitle = modalScheme || p.a || p.t;

    const html = '<div class="modal-handle"></div>'
      + imgHtml
      + '<h2>'+esc(modalTitle)+'</h2>'
      + (modalScheme ? '<div style="color:var(--text-muted);font-size:0.8rem;margin:-8px 0 12px">'+esc(p.t)+'</div>' : '')
      + '<div class="detail-row"><span class="detail-label">Price</span><span class="detail-value" style="color:#2563EB;font-size:1.1rem">'+esc(p.p)+'</span></div>'
      + (p.d ? '<div class="detail-row"><span class="detail-label">Discount</span><span class="detail-value" style="color:#059669">'+esc(p.d)+'</span></div>' : '')
      + '<div class="detail-row"><span class="detail-label">Auction Date</span><span class="detail-value">'+esc(p.ad)+' <span style="color:#D97706">('+daysText+')</span></span></div>'
      + '<div class="detail-row"><span class="detail-label">Type</span><span class="detail-value">'+esc(p.pt)+'</span></div>'
      + '<div class="detail-row"><span class="detail-label">Location</span><span class="detail-value">'+esc(p.l)+'</span></div>'
      + (p.s && p.s !== 'Size not specified' ? '<div class="detail-row"><span class="detail-label">Size</span><span class="detail-value">'+esc(p.s)+'</span></div>' : '')
      + (p.a ? '<div class="detail-row"><span class="detail-label">Address</span><span class="detail-value" style="max-width:60%;text-align:right">'+esc(p.a)+'</span></div>' : '')
      + priceChartHtml
      + (p.u ? '<a class="card-link" href="'+esc(p.u)+'" target="_blank" rel="noopener" style="display:block;text-align:center;padding:10px;margin-top:12px;background:#EFF6FF;border-radius:8px;font-weight:600">View Original Listing &rarr;</a>' : '');

    document.getElementById('modal-content').innerHTML = html;
    document.getElementById('modal-backdrop').classList.add('open');
    document.body.style.overflow = 'hidden';
  }};

  document.getElementById('modal-backdrop').addEventListener('click', function(e) {{
    if (e.target === this) {{
      this.classList.remove('open');
      document.body.style.overflow = '';
    }}
  }});

  // Close on Escape
  document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') {{
      document.getElementById('modal-backdrop').classList.remove('open');
      document.body.style.overflow = '';
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

  // --- Debounce ---
  function debounce(fn, ms) {{
    let timer;
    return function() {{
      clearTimeout(timer);
      timer = setTimeout(fn, ms);
    }};
  }}

  // --- Load data (inlined at build time) ---
  function init() {{
    var stats = JSON.parse(document.getElementById('__stats__').textContent);
    var active = JSON.parse(document.getElementById('__active__').textContent);
    var changes = JSON.parse(document.getElementById('__changes__').textContent);
    statsData = stats;
    allProps = active;
    changesData = changes;

      // Pre-compute search strings
      const allEntries = Object.entries(active);
      for (const [id, p] of allEntries) {{
        p._search = buildSearchString(p);
      }}

      // --- Dashboard: Hot deals ---
      const hotDeals = allEntries
        .filter(([_, p]) => p.d)
        .sort((a, b) => parseDiscount(b[1].d) - parseDiscount(a[1].d))
        .slice(0, 5);
      const hotContainer = document.getElementById('hot-deals');
      if (hotDeals.length) {{
        hotContainer.innerHTML = hotDeals.map(([id, p]) => renderCard(id, p)).join('');
      }} else {{
        hotContainer.innerHTML = '<div class="empty"><p>No price drop data available yet</p></div>';
      }}

      // --- Dashboard: Upcoming auctions (next 7 days) ---
      const upcoming = allEntries
        .filter(([_, p]) => {{ const d = daysUntil(p.ad); return d >= 0 && d <= 7; }})
        .sort((a, b) => daysUntil(a[1].ad) - daysUntil(b[1].ad))
        .slice(0, 10);
      const upContainer = document.getElementById('upcoming');
      if (upcoming.length) {{
        upContainer.innerHTML = upcoming.map(([id, p]) => renderCard(id, p)).join('');
      }} else {{
        upContainer.innerHTML = '<div class="empty"><p>No auctions in the next 7 days</p></div>';
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

      // --- Search/browse tab ---
      const allItems = allEntries.map(([id, p]) => ({{ id, prop: p, _search: p._search }}));
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

      // --- Wire up load more ---
      document.getElementById('more-new').addEventListener('click', () => loadMore('new'));
      document.getElementById('more-changes').addEventListener('click', () => loadMore('changes'));
      document.getElementById('more-all').addEventListener('click', () => loadMore('all'));

  }}

  init();
}})();
</script>
</body>
</html>"""


if __name__ == "__main__":
    generate_page()
