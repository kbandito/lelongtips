#!/usr/bin/env python3
"""Structural diagnostic for lelongtips.com.my search results.

Round 3. Rounds 1-2 probed a bare /search?page=1, which the site answers with
"the search has no or too few filters" — that was a flaw in the probe, not the
scraper: monitor.py sends state=kl_sel plus property_type[] and its last run
parsed 8,350 results over 696 pages. So the query works and extraction is what
fails. This round replays monitor.py's exact parameters and dumps the real
listing markup.
"""

import os
import re
import sys

import requests
from bs4 import BeautifulSoup

ROOT = "https://www.lelongtips.com.my"
BASE = f"{ROOT}/search"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)

# Copied verbatim from monitor.py so the probe and the scraper agree.
SEARCH_PARAMS = {
    "keyword": "",
    "property_type[]": ["1", "2", "3", "4", "5", "6", "7", "8"],
    "state": "kl_sel",
    "bank": "",
    "listing_status": "",
    "input-date": "",
    "auction-date": "",
    "case": "",
    "listing_type": "",
    "min_price": "",
    "max_price": "",
    "min_size": "",
    "max_size": "",
}

DATE_VARIANTS = {
    "strict '12 Jun 2026 (Fri)'": re.compile(r"\d{1,2}\s+\w{3}\s+\d{4}\s+\(\w{3}\)"),
    "no weekday '12 Jun 2026'": re.compile(r"\d{1,2}\s+\w{3}\s+\d{4}"),
    "numeric '12/06/2026'": re.compile(r"\d{1,2}/\d{1,2}/\d{4}"),
}
PRICE = re.compile(r"RM\s?[\d,]+")


def banner(t):
    print("\n" + "=" * 70)
    print(t)
    print("=" * 70)


def analyse(html, label, dump=None):
    banner(f"STRUCTURE: {label}")
    if dump:
        with open(dump, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"saved {dump}")
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    print(f"bytes={len(html)}")

    m = re.search(r"Result\(s\):\s*([\d,]+)", text)
    print(f"  Result(s) parsed: {m.group(1) if m else 'NOT FOUND'}")
    if "too few filters" in text.lower():
        print("  !! site says: no or too few filters")

    anchors = soup.find_all("a", href=re.compile(r"/property/"))
    stretched = soup.find_all("a", href=re.compile(r"/property/"),
                              class_=re.compile("stretched-link"))
    print(f"  a[href*=/property/]                : {len(anchors)}")
    print(f"  a[href*=/property/].stretched-link : {len(stretched)}  <-- strategy 1")
    cls = {}
    for a in anchors:
        k = " ".join(a.get("class") or []) or "(no class)"
        cls[k] = cls.get(k, 0) + 1
    for k, v in sorted(cls.items(), key=lambda x: -x[1])[:8]:
        print(f"      {v:4d}  class={k!r}")

    print(f"  RM prices in text : {len(PRICE.findall(text))}")
    for name, rx in DATE_VARIANTS.items():
        hits = rx.findall(text)
        print(f"  date {name:28s}: {len(hits):4d}  {hits[:2]}")

    if not anchors:
        print("  no listing anchors — page text follows:")
        print("  " + text[:1200])
        return

    # The card: walk up from the first listing anchor to the node holding a price
    a = anchors[0]
    print(f"\n  first listing href: {a.get('href')[:140]}")
    node, hops = a, 0
    while node.parent is not None and node.parent.name != "html" and hops < 8:
        node = node.parent
        hops += 1
        if PRICE.search(node.get_text(" ", strip=True)):
            break
    print(f"  price found {hops} hops above the anchor")
    print(f"\n  --- CARD OUTER HTML (3000 chars) ---")
    print(str(node)[:3000])
    print(f"\n  --- CARD TEXT ---")
    print(node.get_text(" | ", strip=True)[:900])

    # What the existing extractor needs: price AND strict date in one container
    txt = node.get_text(" ", strip=True)
    strict = DATE_VARIANTS["strict '12 Jun 2026 (Fri)'"]
    has_price = bool(PRICE.search(txt))
    has_date = bool(strict.search(txt))
    print(f"\n  container has price      : {has_price}")
    print(f"  container has strict date: {has_date}")
    print("  -> extractor requires BOTH; whichever is False is why 0 were extracted")


def main():
    os.makedirs("data/diagnostics", exist_ok=True)
    s = requests.Session()
    s.headers.update({"User-Agent": UA})

    for page in (1, 2):
        params = dict(SEARCH_PARAMS)
        if page > 1:
            params["page"] = page
        banner(f"GET {BASE} (monitor.py params, page={page})")
        r = s.get(BASE, params=params, timeout=45)
        print(f"HTTP {r.status_code}  {r.url[:180]}")
        analyse(r.text, f"scraper params page {page}",
                f"data/diagnostics/scraper_page{page}.html")

    # Is the strict-date format still used anywhere on a detail page?
    banner("DETAIL PAGE PROBE")
    params = dict(SEARCH_PARAMS)
    r = s.get(BASE, params=params, timeout=45)
    soup = BeautifulSoup(r.text, "html.parser")
    a = soup.find("a", href=re.compile(r"/property/"))
    if a:
        url = a.get("href")
        if url.startswith("/"):
            url = ROOT + url
        d = s.get(url, timeout=45)
        print(f"GET {url[:140]} -> HTTP {d.status_code}, {len(d.text)} bytes")
        dt = BeautifulSoup(d.text, "html.parser").get_text(" ", strip=True)
        for name, rx in DATE_VARIANTS.items():
            print(f"  date {name:28s}: {rx.findall(dt)[:3]}")
        for label in ["Auction Date", "Reserve Price", "Built Up", "Land Area",
                      "Bank", "Auctioneer", "Lawyer"]:
            i = dt.find(label)
            if i >= 0:
                print(f"  [{label}] ...{dt[i:i+120]}...")
        with open("data/diagnostics/detail.html", "w", encoding="utf-8") as fh:
            fh.write(d.text)
    else:
        print("  no listing anchor to follow")

    print("\ndiagnostic complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
