#!/usr/bin/env python3
"""Generate a mobile-responsive HTML dashboard from scrape data."""

import json
import os
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
    import re
    m = re.search(r"[\d,]+", str(price_str))
    if m:
        return int(m.group().replace(",", ""))
    return 0


def generate_page():
    properties = load_json(os.path.join(DATA_DIR, "properties.json")) or {}
    changes_history = load_json(os.path.join(DATA_DIR, "changes.json")) or []
    daily_stats = load_json(os.path.join(DATA_DIR, "daily_stats.json")) or {}
    progress = load_json(os.path.join(DATA_DIR, "scraping_progress.json")) or {}

    # Latest and second-latest scan
    latest_scan = changes_history[-1] if changes_history else {}
    prev_scan = changes_history[-2] if len(changes_history) >= 2 else {}

    scan_date = latest_scan.get("scan_date", "N/A")
    if scan_date != "N/A":
        try:
            dt = datetime.fromisoformat(scan_date)
            scan_date_display = dt.strftime("%d %b %Y, %I:%M %p")
        except Exception:
            scan_date_display = scan_date[:19]
    else:
        scan_date_display = "N/A"

    prev_scan_date = prev_scan.get("scan_date", "")
    if prev_scan_date:
        try:
            dt = datetime.fromisoformat(prev_scan_date)
            prev_scan_display = dt.strftime("%d %b %Y")
        except Exception:
            prev_scan_display = prev_scan_date[:10]
    else:
        prev_scan_display = "N/A"

    # Current active listings (with valid future auction dates)
    now = datetime.now()
    active_count = 0
    for p in properties.values():
        ad = p.get("auction_date", "")
        try:
            import re
            m = re.match(r"(\d{1,2})\s+(\w{3})\s+(\d{4})", ad)
            if m:
                from datetime import datetime as dt2
                d = dt2.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %b %Y")
                if d >= now:
                    active_count += 1
        except Exception:
            pass

    # New listings from latest scan
    new_ids = latest_scan.get("new_listing_ids", [])
    new_listings = []
    for pid in new_ids:
        p = properties.get(pid)
        if p:
            new_listings.append({**p, "id": pid})

    # Sort new listings by price
    new_listings.sort(key=lambda x: x.get("price_value", 0))

    # Changed listings from latest scan
    change_records = latest_scan.get("changes", [])
    # Group changes by property_id
    changes_by_prop = {}
    for c in change_records:
        pid = c.get("property_id", "")
        if pid not in changes_by_prop:
            changes_by_prop[pid] = {
                "title": c.get("title", "Unknown"),
                "changes": [],
                "property": properties.get(pid, {}),
                "id": pid,
            }
        changes_by_prop[pid]["changes"].append(c)

    changed_listings = list(changes_by_prop.values())

    # Scan history for chart
    scan_history = []
    for entry in changes_history:
        sd = entry.get("scan_date", "")[:10]
        scan_history.append({
            "date": sd,
            "new": entry.get("new_listings_count", 0),
            "changed": entry.get("changed_properties_count", 0),
        })

    # Build HTML
    new_cards_html = build_new_cards(new_listings)
    changed_cards_html = build_changed_cards(changed_listings, properties)
    scan_history_json = json.dumps(scan_history)

    page_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LelongTips Dashboard</title>
<style>
:root {{
  --bg: #0f1117;
  --card: #1a1d27;
  --border: #2a2d3a;
  --text: #e4e4e7;
  --muted: #8b8d97;
  --accent: #6366f1;
  --green: #22c55e;
  --red: #ef4444;
  --orange: #f59e0b;
  --blue: #3b82f6;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}}
.container {{ max-width: 768px; margin: 0 auto; padding: 16px; }}
header {{
  padding: 20px 0 12px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 16px;
}}
header h1 {{ font-size: 1.4rem; font-weight: 700; }}
header .subtitle {{ color: var(--muted); font-size: 0.85rem; margin-top: 2px; }}

/* Stats Grid */
.stats {{
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 20px;
}}
.stat {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
}}
.stat .label {{ color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; }}
.stat .value {{ font-size: 1.5rem; font-weight: 700; margin-top: 2px; }}
.stat .value.green {{ color: var(--green); }}
.stat .value.orange {{ color: var(--orange); }}
.stat .value.blue {{ color: var(--blue); }}
.stat .value.accent {{ color: var(--accent); }}

/* Tabs */
.tabs {{
  display: flex;
  gap: 0;
  margin-bottom: 16px;
  background: var(--card);
  border-radius: 10px;
  border: 1px solid var(--border);
  overflow: hidden;
}}
.tab {{
  flex: 1;
  padding: 10px 8px;
  text-align: center;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  border: none;
  background: transparent;
  color: var(--muted);
  transition: all 0.2s;
}}
.tab.active {{
  background: var(--accent);
  color: #fff;
}}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}

/* Property Cards */
.card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 10px;
}}
.card-header {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}}
.card-title {{
  font-weight: 600;
  font-size: 0.95rem;
  flex: 1;
  margin-right: 8px;
}}
.card-price {{
  font-weight: 700;
  color: var(--green);
  white-space: nowrap;
  font-size: 0.95rem;
}}
.card-meta {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}}
.badge {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(99, 102, 241, 0.15);
  color: var(--accent);
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 500;
}}
.badge.loc {{ background: rgba(59,130,246,0.15); color: var(--blue); }}
.badge.date {{ background: rgba(245,158,11,0.15); color: var(--orange); }}
.badge.size {{ background: rgba(34,197,94,0.15); color: var(--green); }}
.card-address {{
  color: var(--muted);
  font-size: 0.8rem;
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}}
.card-link {{
  display: inline-block;
  color: var(--accent);
  font-size: 0.8rem;
  text-decoration: none;
  font-weight: 500;
}}
.card-link:hover {{ text-decoration: underline; }}

/* Change indicators */
.change-item {{
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 0.82rem;
  border-top: 1px solid var(--border);
  margin-top: 6px;
  padding-top: 8px;
}}
.change-arrow {{ color: var(--muted); }}
.old-val {{ color: var(--red); text-decoration: line-through; }}
.new-val {{ color: var(--green); font-weight: 600; }}
.change-label {{ color: var(--muted); font-size: 0.75rem; }}

/* Scan History */
.history-row {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
  font-size: 0.85rem;
}}
.history-date {{ color: var(--muted); }}
.history-stats {{ display: flex; gap: 12px; }}
.history-new {{ color: var(--green); }}
.history-changed {{ color: var(--orange); }}

/* Search/filter */
.search-bar {{
  width: 100%;
  padding: 10px 14px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--text);
  font-size: 0.9rem;
  margin-bottom: 12px;
  outline: none;
}}
.search-bar:focus {{ border-color: var(--accent); }}
.search-bar::placeholder {{ color: var(--muted); }}

.count-label {{
  color: var(--muted);
  font-size: 0.8rem;
  margin-bottom: 10px;
}}

/* Footer */
footer {{
  text-align: center;
  color: var(--muted);
  font-size: 0.75rem;
  padding: 20px 0;
  border-top: 1px solid var(--border);
  margin-top: 20px;
}}

/* Responsive */
@media (max-width: 400px) {{
  .stats {{ grid-template-columns: repeat(2, 1fr); gap: 8px; }}
  .stat .value {{ font-size: 1.3rem; }}
  .container {{ padding: 12px; }}
}}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>LelongTips Dashboard</h1>
    <div class="subtitle">Last scan: {esc(scan_date_display)} MYT</div>
  </header>

  <div class="stats">
    <div class="stat">
      <div class="label">Total Tracked</div>
      <div class="value accent">{len(properties):,}</div>
    </div>
    <div class="stat">
      <div class="label">Active Listings</div>
      <div class="value blue">{active_count:,}</div>
    </div>
    <div class="stat">
      <div class="label">New (Latest)</div>
      <div class="value green">{latest_scan.get('new_listings_count', 0)}</div>
    </div>
    <div class="stat">
      <div class="label">Changed (Latest)</div>
      <div class="value orange">{latest_scan.get('changed_properties_count', 0)}</div>
    </div>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="showTab('new')">New ({len(new_listings)})</button>
    <button class="tab" onclick="showTab('changed')">Changed ({len(changed_listings)})</button>
    <button class="tab" onclick="showTab('history')">History</button>
  </div>

  <div id="tab-new" class="tab-content active">
    <input type="text" class="search-bar" placeholder="Search new listings..." oninput="filterCards('new', this.value)">
    <div class="count-label" id="new-count">Showing {len(new_listings)} listings</div>
    <div id="new-cards">
{new_cards_html}
    </div>
  </div>

  <div id="tab-changed" class="tab-content">
    <input type="text" class="search-bar" placeholder="Search changed listings..." oninput="filterCards('changed', this.value)">
    <div class="count-label" id="changed-count">Showing {len(changed_listings)} listings</div>
    <div id="changed-cards">
{changed_cards_html}
    </div>
  </div>

  <div id="tab-history" class="tab-content">
    <div class="card">
      <div style="font-weight:600; margin-bottom:10px;">Scan History</div>
      {"".join(build_history_rows(scan_history))}
    </div>
  </div>

  <footer>
    LelongTips Property Monitor &middot; Auto-updated every 3 days<br>
    Previous scan: {esc(prev_scan_display)}
  </footer>
</div>

<script>
function showTab(name) {{
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.target.classList.add('active');
}}

function filterCards(tab, query) {{
  const q = query.toLowerCase();
  const container = document.getElementById(tab + '-cards');
  const cards = container.querySelectorAll('.card');
  let shown = 0;
  cards.forEach(card => {{
    const text = card.textContent.toLowerCase();
    const match = !q || text.includes(q);
    card.style.display = match ? '' : 'none';
    if (match) shown++;
  }});
  const countEl = document.getElementById(tab + '-count');
  if (countEl) countEl.textContent = 'Showing ' + shown + ' listings';
}}
</script>
</body>
</html>"""

    os.makedirs(DOCS_DIR, exist_ok=True)
    out_path = os.path.join(DOCS_DIR, "index.html")
    with open(out_path, "w") as f:
        f.write(page_html)
    print(f"Dashboard generated: {out_path}")
    print(f"  Total tracked: {len(properties):,}")
    print(f"  Active listings: {active_count:,}")
    print(f"  New: {len(new_listings)}, Changed: {len(changed_listings)}")


def build_new_cards(listings):
    cards = []
    for p in listings:
        title = esc(p.get("title", "Unknown"))
        price = esc(p.get("price", "N/A"))
        location = esc(p.get("location", "N/A"))
        size = esc(p.get("size", "N/A"))
        auction_date = esc(p.get("auction_date", "N/A"))
        prop_type = esc(p.get("property_type", ""))
        address = esc(p.get("header_full", p.get("header", "")))
        url = p.get("listing_url", p.get("url", ""))

        link_html = ""
        if url:
            link_html = f'<a class="card-link" href="{esc(url)}" target="_blank" rel="noopener">View listing &rarr;</a>'

        type_badge = ""
        if prop_type:
            type_badge = f'<span class="badge">{prop_type}</span>'

        cards.append(f"""    <div class="card" data-search>
      <div class="card-header">
        <div class="card-title">{title}</div>
        <div class="card-price">{price}</div>
      </div>
      <div class="card-meta">
        {type_badge}
        <span class="badge loc">{location}</span>
        <span class="badge size">{size}</span>
        <span class="badge date">{auction_date}</span>
      </div>
      {f'<div class="card-address">{address}</div>' if address and address != title else ''}
      {link_html}
    </div>""")
    return "\n".join(cards)


def build_changed_cards(changed_listings, properties):
    cards = []
    for item in changed_listings:
        prop = item.get("property", {})
        title = esc(prop.get("title", item.get("title", "Unknown")))
        price = esc(prop.get("price", "N/A"))
        location = esc(prop.get("location", "N/A"))
        size = esc(prop.get("size", "N/A"))
        auction_date = esc(prop.get("auction_date", "N/A"))
        url = prop.get("listing_url", prop.get("url", ""))

        link_html = ""
        if url:
            link_html = f'<a class="card-link" href="{esc(url)}" target="_blank" rel="noopener">View listing &rarr;</a>'

        changes_html = ""
        for c in item.get("changes", []):
            field = esc(c.get("field", ""))
            old_val = esc(c.get("old_value", ""))
            new_val = esc(c.get("new_value", ""))
            changes_html += f"""
      <div class="change-item">
        <span class="change-label">{field}:</span>
        <span class="old-val">{old_val}</span>
        <span class="change-arrow">&rarr;</span>
        <span class="new-val">{new_val}</span>
      </div>"""

        cards.append(f"""    <div class="card" data-search>
      <div class="card-header">
        <div class="card-title">{title}</div>
        <div class="card-price">{price}</div>
      </div>
      <div class="card-meta">
        <span class="badge loc">{location}</span>
        <span class="badge size">{size}</span>
        <span class="badge date">{auction_date}</span>
      </div>
      {link_html}
      {changes_html}
    </div>""")
    return "\n".join(cards)


def build_history_rows(scan_history):
    rows = []
    for entry in reversed(scan_history):
        rows.append(f"""      <div class="history-row">
        <span class="history-date">{esc(entry['date'])}</span>
        <div class="history-stats">
          <span class="history-new">+{entry['new']} new</span>
          <span class="history-changed">{entry['changed']} changed</span>
        </div>
      </div>""")
    return rows


if __name__ == "__main__":
    generate_page()
