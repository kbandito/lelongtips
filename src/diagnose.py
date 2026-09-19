#!/usr/bin/env python3
"""Structural diagnostic for lelongtips.com.my.

Round 2. Round 1 established that /search returns a byte-identical shell for
every page, with no listing anchors even after full browser rendering, that the
page mentions a captcha, and that login fails. This round answers the two
questions that follow:

  1. Why does login fail — wrong credentials, a changed form, or a captcha?
  2. Where do listings come from now — an XHR/JSON endpoint, or nothing
     without a session?

Run in CI; the runner has direct internet access.
"""

import json
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
CAPTCHA_MARKERS = [
    "g-recaptcha", "grecaptcha", "recaptcha/api.js", "data-sitekey",
    "cf-turnstile", "challenges.cloudflare.com", "hcaptcha",
]


def banner(t):
    print("\n" + "=" * 70)
    print(t)
    print("=" * 70)


def context_hits(html, needle, width=160, limit=4):
    """Show what surrounds a keyword, so 'mentions captcha' becomes specific."""
    out = []
    for m in re.finditer(re.escape(needle), html, re.IGNORECASE):
        s = max(0, m.start() - width // 2)
        out.append(re.sub(r"\s+", " ", html[s:s + width]))
        if len(out) >= limit:
            break
    return out


def inspect_login_page():
    banner("LOGIN PAGE STRUCTURE")
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    r = s.get(f"{ROOT}/login", timeout=45)
    print(f"GET /login -> HTTP {r.status_code}, {len(r.text)} bytes, final={r.url}")
    soup = BeautifulSoup(r.text, "html.parser")

    for marker in CAPTCHA_MARKERS:
        if marker.lower() in r.text.lower():
            print(f"  CAPTCHA MARKER: {marker}")
            for c in context_hits(r.text, marker, limit=2):
                print(f"      ...{c}...")

    forms = soup.find_all("form")
    print(f"  forms on page: {len(forms)}")
    for i, f in enumerate(forms):
        fields = [(inp.get("name"), inp.get("type")) for inp in f.find_all(("input", "select"))]
        print(f"    form[{i}] action={f.get('action')!r} method={f.get('method')!r}")
        print(f"      fields: {fields}")
    tok = soup.find("input", {"name": "_token"})
    print(f"  csrf _token present: {bool(tok)}")
    return s


def try_requests_login(s):
    """Attempt the plain-POST login and report exactly what comes back."""
    banner("LOGIN ATTEMPT (requests + CSRF)")
    email = os.getenv("LELONGTIPS_EMAIL", "")
    password = os.getenv("LELONGTIPS_PASSWORD", "")
    if not email or not password:
        print("no credentials in env — skipping")
        return None
    print(f"  using email: {email[:3]}***{email[email.index('@'):] if '@' in email else ''}")
    r = s.get(f"{ROOT}/login", timeout=45)
    soup = BeautifulSoup(r.text, "html.parser")
    tok = soup.find("input", {"name": "_token"})
    data = {"email": email, "password": password}
    if tok:
        data["_token"] = tok.get("value", "")
    r2 = s.post(f"{ROOT}/login", data=data, timeout=45, allow_redirects=True)
    print(f"  POST /login -> HTTP {r2.status_code}, final={r2.url}, {len(r2.text)} bytes")
    soup2 = BeautifulSoup(r2.text, "html.parser")
    for sel in [".alert", ".alert-danger", ".invalid-feedback", ".error", ".text-danger"]:
        for el in soup2.select(sel):
            txt = el.get_text(" ", strip=True)
            if txt:
                print(f"  page message [{sel}]: {txt[:200]}")
    # Laravel often reflects validation errors in the session-flash markup
    for kw in ["credentials do not match", "These credentials", "too many attempts",
               "verify", "suspend", "expired", "captcha"]:
        if kw.lower() in r2.text.lower():
            print(f"  keyword {kw!r} present in response")
            for c in context_hits(r2.text, kw, limit=1):
                print(f"      ...{c}...")
    ok = "/login" not in r2.url
    print(f"  login {'OK' if ok else 'FAILED'}")
    return ok


def inspect_search_with_browser():
    """Watch what the search page actually loads — the definitive data source."""
    banner("SEARCH PAGE: NETWORK TRACE (browser)")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright unavailable")
        return
    calls = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_context(user_agent=UA).new_page()

            def on_response(resp):
                try:
                    ct = resp.headers.get("content-type", "")
                    calls.append((resp.status, ct.split(";")[0], resp.url))
                except Exception:
                    pass

            page.on("response", on_response)
            page.goto(f"{ROOT}/search?page=1", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(4000)
            html = page.content()
            body_text = page.inner_text("body")
            shot = "data/diagnostics/search.png"
            page.screenshot(path=shot, full_page=False)
            browser.close()
    except Exception as e:
        print(f"browser run failed: {e}")
        return

    print(f"  requests made: {len(calls)}")
    print("  --- same-origin / JSON responses ---")
    for status, ct, url in calls:
        if "lelongtips" in url and not re.search(r"\.(png|jpg|jpeg|gif|svg|woff2?|ttf|ico)(\?|$)", url, re.I):
            print(f"    {status} {ct:28s} {url[:130]}")
    print("  --- any json anywhere ---")
    for status, ct, url in calls:
        if "json" in ct:
            print(f"    {status} {ct:28s} {url[:130]}")

    banner("SEARCH PAGE: WHAT A USER SEES")
    print(re.sub(r"\n{2,}", "\n", body_text)[:2500])

    banner("SEARCH PAGE: MARKUP PROBES")
    for marker in CAPTCHA_MARKERS:
        if marker.lower() in html.lower():
            print(f"  CAPTCHA MARKER: {marker}")
            for c in context_hits(html, marker, limit=2):
                print(f"      ...{c}...")
    for fw, probe in [("Livewire", "wire:id"), ("Inertia", 'data-page='),
                      ("Vue app root", 'id="app"'), ("Alpine", "x-data")]:
        if probe in html:
            print(f"  framework probe: {fw} ({probe})")
    # Endpoint hints embedded in inline scripts
    urls = set(re.findall(r"""["']((?:/|https?://[^"']*lelongtips[^"']*)[^"']*(?:search|listing|propert|api)[^"']*)["']""", html, re.I))
    print(f"  candidate endpoints referenced in markup ({len(urls)}):")
    for u in sorted(urls)[:25]:
        print(f"    {u[:150]}")
    print("\n  login/gate wording:")
    for kw in ["login to view", "please login", "sign in", "register", "subscribe", "member"]:
        hits = context_hits(html, kw, limit=1)
        for c in hits:
            print(f"    [{kw}] ...{c}...")


def main():
    os.makedirs("data/diagnostics", exist_ok=True)
    s = inspect_login_page()
    try_requests_login(s)
    inspect_search_with_browser()

    banner("SEARCH AFTER LOGIN (requests session)")
    r = s.get(f"{ROOT}/search?page=1", timeout=45)
    soup = BeautifulSoup(r.text, "html.parser")
    anchors = soup.find_all("a", href=re.compile(r"/property/"))
    print(f"  HTTP {r.status_code}, {len(r.text)} bytes")
    print(f"  a[href*=/property/]: {len(anchors)}")
    print(f"  RM prices in text  : {len(re.findall(r'RM[ ]?[0-9,]+', soup.get_text(' ')))}")
    with open("data/diagnostics/search_after_login.html", "w", encoding="utf-8") as fh:
        fh.write(r.text)
    print("\ndiagnostic complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
