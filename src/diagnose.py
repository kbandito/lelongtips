#!/usr/bin/env python3
"""Structural diagnostic for the lelongtips search page.

Answers one question: what does the listing markup look like *today*, and which
extraction strategies still match it? Run in CI (the runner has direct internet
access) and read the output in the job log.

    python src/diagnose.py [--pages 2] [--dump-dir data/diagnostics]
"""

import argparse
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

ROOT = "https://www.lelongtips.com.my"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# The date shape the current extractor insists on: "12 Jun 2026 (Fri)"
DATE_STRICT = re.compile(r"\d{1,2}\s+\w{3}\s+\d{4}\s+\(\w{3}\)")
# Looser shapes that would indicate the site changed its date rendering
DATE_VARIANTS = {
    "strict '12 Jun 2026 (Fri)'": DATE_STRICT,
    "no weekday '12 Jun 2026'": re.compile(r"\d{1,2}\s+\w{3}\s+\d{4}"),
    "numeric '12/06/2026'": re.compile(r"\d{1,2}/\d{1,2}/\d{4}"),
    "iso '2026-06-12'": re.compile(r"\d{4}-\d{2}-\d{2}"),
    "long '12 June 2026'": re.compile(r"\d{1,2}\s+[A-Z][a-z]{3,8}\s+\d{4}"),
}
PRICE = re.compile(r"RM\s?[\d,]+")
PROPERTY_HREF = re.compile(r"/property/")


def banner(t):
    print("\n" + "=" * 70)
    print(t)
    print("=" * 70)


def login_cookies():
    """Log in with Playwright if credentials are present; return a cookie dict."""
    email = os.getenv("LELONGTIPS_EMAIL", "")
    password = os.getenv("LELONGTIPS_PASSWORD", "")
    if not email or not password:
        print("no credentials in env — diagnosing as guest")
        return {}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed — diagnosing as guest")
        return {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_context(user_agent=UA).new_page()
            page.goto(f"{ROOT}/login", wait_until="networkidle", timeout=45000)
            pw = page.locator('input[type="password"]')
            form = pw.locator("xpath=ancestor::form")
            form.locator('input[name="email"], input[type="email"]').fill(email)
            pw.fill(password)
            btn = form.locator('button[type="submit"], input[type="submit"]')
            try:
                with page.expect_navigation(wait_until="networkidle", timeout=45000):
                    btn.click()
            except Exception as e:
                print(f"  login navigation did not settle: {e}")
            print(f"  post-login url: {page.url}")
            ok = "/login" not in page.url
            print(f"  login {'OK' if ok else 'FAILED'}")
            jar = {c["name"]: c["value"] for c in page.context.cookies()}
            browser.close()
            return jar
    except Exception as e:
        print(f"  login error: {e}")
        return {}


def report(html, label, dump_path=None):
    banner(f"STRUCTURE: {label}")
    if dump_path:
        with open(dump_path, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"raw html saved to {dump_path}")

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else "(none)"
    text = soup.get_text(" ", strip=True)
    print(f"bytes={len(html)}  <title>={title!r}")

    # Is this a login wall or a JS shell rather than server-rendered listings?
    for probe, note in [
        ("login", "page mentions 'login'"),
        ("Result(s):", "result count present"),
        ("cloudflare", "cloudflare mentioned"),
        ("captcha", "captcha mentioned"),
    ]:
        if probe.lower() in html.lower():
            print(f"  [probe] {note}")
    m = re.search(r"Result\(s\):\s*([\d,]+)", text)
    print(f"  result count parsed: {m.group(1) if m else 'NOT FOUND'}")

    # Anchor census — the backbone of any extraction strategy
    all_prop = soup.find_all("a", href=PROPERTY_HREF)
    stretched = soup.find_all("a", href=PROPERTY_HREF, class_=re.compile("stretched-link"))
    print(f"\n  a[href*=/property/]                 : {len(all_prop)}")
    print(f"  a[href*=/property/].stretched-link  : {len(stretched)}   <-- current strategy 1")
    classes = {}
    for a in all_prop:
        key = " ".join(a.get("class") or []) or "(no class)"
        classes[key] = classes.get(key, 0) + 1
    for k, v in sorted(classes.items(), key=lambda x: -x[1])[:8]:
        print(f"      {v:4d}  class={k!r}")

    # Text-shape census — the other half of the current gating condition
    print(f"\n  RM price matches in text : {len(PRICE.findall(text))}")
    for name, rx in DATE_VARIANTS.items():
        hits = rx.findall(text)
        flag = "   <-- current strategy requires this" if rx is DATE_STRICT else ""
        print(f"  date {name:28s}: {len(hits):4d}{flag}")
        if hits:
            print(f"      sample: {hits[:3]}")

    # Embedded structured data would be a far more stable source than CSS
    lds = soup.find_all("script", type="application/ld+json")
    print(f"\n  <script type=application/ld+json> : {len(lds)}")
    for s in lds[:2]:
        print(f"      {(s.string or '')[:300]}")
    nxt = soup.find("script", id="__NEXT_DATA__")
    print(f"  __NEXT_DATA__ present            : {bool(nxt)}")
    for var in ["window.__INITIAL_STATE__", "window.__NUXT__", 'id="app"', "v-cloak"]:
        if var in html:
            print(f"  [probe] {var} present (client-rendered?)")

    # Show one real card so selectors can be written against fact, not memory
    if all_prop:
        a = all_prop[0]
        print(f"\n  first /property/ anchor href:\n      {a.get('href')}")
        node = a
        for _ in range(6):
            if node.parent is None or node.parent.name == "html":
                break
            node = node.parent
            t = node.get_text(" ", strip=True)
            if PRICE.search(t):
                break
        print(f"\n  --- ancestor card outerHTML (first 2500 chars) ---")
        print(str(node)[:2500])
        print(f"\n  --- that card's text ---")
        print(node.get_text(" | ", strip=True)[:800])
    else:
        print("\n  NO /property/ anchors at all — page is a wall, a redirect, or JS-rendered")
        print("  --- first 1500 chars of body ---")
        print(html[:1500])


def rendered_html(url, cookies):
    """Fetch with a real browser, to compare against the raw HTTP response."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=UA)
            if cookies:
                ctx.add_cookies([
                    {"name": k, "value": v, "domain": "www.lelongtips.com.my", "path": "/"}
                    for k, v in cookies.items()
                ])
            page = ctx.new_page()
            page.goto(url, wait_until="networkidle", timeout=60000)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        print(f"  playwright render failed: {e}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--dump-dir", default="data/diagnostics")
    args = ap.parse_args()
    os.makedirs(args.dump_dir, exist_ok=True)

    banner("LOGIN")
    jar = login_cookies()

    sess = requests.Session()
    sess.headers.update({"User-Agent": UA})
    for k, v in jar.items():
        sess.cookies.set(k, v, domain="www.lelongtips.com.my")

    for n in range(1, args.pages + 1):
        url = f"{ROOT}/search?page={n}"
        banner(f"GET {url}")
        try:
            r = sess.get(url, timeout=45)
            print(f"HTTP {r.status_code}  final_url={r.url}")
            report(r.text, f"requests page {n}", os.path.join(args.dump_dir, f"page{n}.html"))
        except Exception as e:
            print(f"request failed: {e}")
            continue

        if n == 1:
            html = rendered_html(url, jar)
            if html:
                report(html, "playwright-rendered page 1",
                       os.path.join(args.dump_dir, "page1_rendered.html"))

    print("\ndiagnostic complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
