#!/usr/bin/env python3
"""Report what a given session cookie can actually see.

Run this from anywhere — your own machine, a VM, a VPS — to answer two
questions the CI runs could not separate:

  1. Do search-result CARDS unmask prices for a member, or only detail pages?
  2. Is the session tied to the IP it was created on?

Run it on your own machine first (same IP as the browser you logged in
with). If prices are unmasked there but masked from a server, the session is
IP-bound and the scraper has to run from that same network.

    LELONGTIPS_COOKIE='<lt_session value>' python check_session.py
"""

import os
import re
import sys
import urllib.parse

import requests
from bs4 import BeautifulSoup

ROOT = "https://www.lelongtips.com.my"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
MASKED = re.compile(r"RM\s?[\d,]*x+", re.IGNORECASE)
REAL = re.compile(r"RM\s?\d[\d,]{3,}(?![\dx,])", re.IGNORECASE)
DAY_DATE = re.compile(r"\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{4}")


def build_session(raw):
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    if not raw:
        print("No cookie supplied — checking as a guest (baseline).")
        return s
    pairs = []
    if "=" in raw:
        for part in raw.split(";"):
            part = part.strip()
            if "=" in part:
                n, _, v = part.partition("=")
                pairs.append((n.strip(), v.strip()))
    else:
        pairs.append(("lt_session", raw.strip()))
    for name, value in pairs:
        # Laravel cookies travel percent-encoded; re-encode a decoded paste.
        if "%" not in value and any(c in value for c in "+/="):
            value = urllib.parse.quote(value, safe="")
        for domain in ("www.lelongtips.com.my", ".lelongtips.com.my"):
            s.cookies.set(name, value, domain=domain)
        print(f"  cookie {name}: {len(value)} chars")
    return s


def summarise(html, label):
    """Print what this page reveals; returns True when prices are visible."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    masked = MASKED.findall(text)
    real = REAL.findall(text)
    greet = re.search(r"Hi\s+([A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,3})\s*,", text)
    print(f"\n{label}")
    print(f"  signed in as        : {greet.group(1) if greet else 'NOT SIGNED IN'}")
    print(f"  masked prices       : {len(masked)}  {masked[:3]}")
    print(f"  real prices         : {len(real)}  {real[:3]}")
    print(f"  'login to view'     : {text.lower().count('login to view')}")
    print(f"  day-precision dates : {len(DAY_DATE.findall(text))}  "
          f"{DAY_DATE.findall(text)[:2]}")
    return soup, bool(greet) and not masked and bool(real)


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from cookie_source import load_cookie, describe_source

    raw = sys.argv[1].strip() if len(sys.argv) > 1 else load_cookie()
    print("Checking what this session can see...")
    print(f"Cookie from: {'command line' if len(sys.argv) > 1 else describe_source()}")
    s = build_session(raw)

    try:
        r = s.get(f"{ROOT}/search",
                  params={"state": "kl_sel", "property_type[]": ["1", "2", "3"]},
                  timeout=45)
    except Exception as e:
        print(f"Request failed: {e}")
        return 1
    soup, prices_visible = summarise(
        r.text, f"SEARCH RESULTS PAGE (HTTP {r.status_code})"
    )

    a = soup.find("a", href=re.compile(r"/property/"))
    if a:
        url = a["href"]
        if url.startswith("/"):
            url = ROOT + url
        d = s.get(url, timeout=45)
        summarise(d.text, f"DETAIL PAGE (HTTP {d.status_code})")
        print(f"  {url[:100]}")

    print("\nHow to read this:")
    print("  Signed in + real prices on BOTH  -> the scraper can use this cookie.")
    print("  Signed in + cards masked, detail real -> cards never unmask; the")
    print("     scraper must read prices from detail pages.")
    print("  NOT signed in here, but fine in your browser -> the session is")
    print("     bound to the IP or device it was created on.")
    # 0 = prices visible, 2 = session not usable. Lets a script stop before
    # spending 35 minutes on a scrape that would collect nothing.
    return 0 if prices_visible else 2


if __name__ == "__main__":
    sys.exit(main())
