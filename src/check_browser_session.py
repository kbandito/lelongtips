#!/usr/bin/env python3
"""Load the site in a real browser carrying the session cookie.

Two explanations fit the evidence so far: the session is tied to the IP that
created it, or the site serves guest content to anything that does not look
like a browser. A plain HTTP client fails both ways, so it cannot tell them
apart. Chromium with the same cookie, from the same machine, isolates it:

  real prices here  -> the client was the problem, not the location, and the
                       scraper can use a browser from anywhere
  still masked      -> the session really is tied to the network it came from
"""

import os
import re
import sys
import urllib.parse

ROOT = "https://www.lelongtips.com.my"
SEARCH = f"{ROOT}/search?state=kl_sel&property_type%5B%5D=1&property_type%5B%5D=2"
MASKED = re.compile(r"RM\s?[\d,]*x+", re.IGNORECASE)
REAL = re.compile(r"RM\s?\d[\d,]{3,}(?![\dx,])", re.IGNORECASE)


def cookie_pairs(raw):
    pairs = []
    if "=" in raw:
        for part in raw.split(";"):
            part = part.strip()
            if "=" in part:
                n, _, v = part.partition("=")
                pairs.append((n.strip(), v.strip()))
    else:
        pairs.append(("lt_session", raw.strip()))
    out = []
    for name, value in pairs:
        if "%" not in value and any(c in value for c in "+/="):
            value = urllib.parse.quote(value, safe="")
        out.append((name, value))
    return out


def report(page, label):
    text = page.inner_text("body")
    masked = MASKED.findall(text)
    real = REAL.findall(text)
    greet = re.search(r"Hi\s+([A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,3})\s*,", text)
    print(f"\n{label}")
    print(f"  url            : {page.url[:110]}")
    print(f"  signed in as   : {greet.group(1) if greet else 'NOT SIGNED IN'}")
    print(f"  masked prices  : {len(masked)}  {masked[:3]}")
    print(f"  real prices    : {len(real)}  {real[:3]}")
    print(f"  'login to view': {text.lower().count('login to view')}")
    return len(real) > 0 and len(masked) == 0


def main():
    raw = os.getenv("LELONGTIPS_COOKIE", "").strip()
    if not raw:
        print("LELONGTIPS_COOKIE not set")
        return 1
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/140.0.0.0 Safari/537.36"),
            locale="en-MY",
            timezone_id="Asia/Kuala_Lumpur",
            viewport={"width": 1440, "height": 900},
        )
        cookies = [
            {"name": n, "value": v, "domain": ".lelongtips.com.my", "path": "/"}
            for n, v in cookie_pairs(raw)
        ]
        print(f"injecting {len(cookies)} cookie(s): "
              + ", ".join(f"{c['name']} ({len(c['value'])} chars)" for c in cookies))
        ctx.add_cookies(cookies)

        page = ctx.new_page()
        page.goto(SEARCH, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)
        ok = report(page, "SEARCH RESULTS (real browser + cookie)")

        link = page.query_selector('a[href*="/property/"]')
        if link:
            href = link.get_attribute("href")
            if href.startswith("/"):
                href = ROOT + href
            page.goto(href, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(2000)
            report(page, "DETAIL PAGE (real browser + cookie)")

        page.screenshot(path="data/diagnostics/browser_session.png", full_page=False)
        browser.close()

    print("\nVERDICT: " + (
        "the cookie works in a browser — the HTTP client was the problem, "
        "not the location. No VM needed; drive the scrape with a browser."
        if ok else
        "still masked in a real browser from this machine — the session is "
        "tied to the network that created it. The scraper must run from there."
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
