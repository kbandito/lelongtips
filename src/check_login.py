#!/usr/bin/env python3
"""Answer one question: what does logging in actually unlock?

Guests see a masked price ("RM98,xxx"), a month-only auction date and no
street address. If a login restores any of those, reserve-price tracking is
recoverable; if it does not, guest-mode scraping is all there is.

Credentials come from the environment so they stay out of the repository and
out of the logs. Run it from CI, where the site is reachable.
"""

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
SEARCH_PARAMS = {
    "property_type[]": ["1", "2", "3", "4", "5", "6", "7", "8"],
    "state": "kl_sel",
}
MASKED = re.compile(r"RM\s?[\d,]*x+", re.IGNORECASE)
REAL_PRICE = re.compile(r"RM\s?\d[\d,]{3,}(?![\dx,])", re.IGNORECASE)
DAY_DATE = re.compile(r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}")


def banner(t):
    print("\n" + "=" * 68)
    print(t)
    print("=" * 68)


def login_with_browser(email, password):
    """Log in with a real browser so the page's own reCAPTCHA v3 script runs.

    The login form posts a hidden captToken that the site fills via
    grecaptcha.execute(). A plain HTTP POST cannot produce it, so the click
    has to happen in a browser that executed the page's JavaScript.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        headless = os.getenv("HEADLESS", "").strip().lower() not in ("0", "false", "no")
        print(f"  browser mode: {'headless' if headless else 'headed (xvfb)'}")
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(user_agent=UA, locale="en-MY")
        page = ctx.new_page()
        page.goto(f"{ROOT}/login", wait_until="networkidle", timeout=60000)

        pw = page.locator('input[type="password"]').first
        form = pw.locator("xpath=ancestor::form")
        form.locator('input[name="email"], input[type="email"]').first.fill(email)
        pw.fill(password)

        # Give reCAPTCHA v3 a moment to populate the hidden token.
        page.wait_for_timeout(3000)
        token = page.evaluate(
            "() => { const e = document.querySelector('input[name=captToken]');"
            " return e ? (e.value || '').length : -1; }"
        )
        print(f"  captToken length before submit: {token} "
              f"({'populated' if token and token > 0 else 'EMPTY — reCAPTCHA did not run'})")

        def token_len():
            try:
                return page.evaluate(
                    "() => { const e = document.querySelector('input[name=captToken]');"
                    " return e ? (e.value || '').length : -1; }"
                )
            except Exception:
                return -2

        form.locator('button[type="submit"], input[type="submit"]').first.click()
        # The site calls grecaptcha.execute() from its submit handler, so the
        # token only appears after the click.
        for _ in range(10):
            page.wait_for_timeout(1000)
            if token_len() > 0:
                break
        print(f"  captToken length after submit : {token_len()}")
        try:
            page.wait_for_load_state("networkidle", timeout=45000)
        except Exception:
            pass
        page.wait_for_timeout(3000)

        final_url = page.url
        ok = "/login" not in final_url
        print(f"  post-login url: {final_url}")
        print(f"  login {'SUCCEEDED' if ok else 'FAILED'}")
        if not ok:
            body = page.inner_text("body")[:1500]
            flat = re.sub(r"\s+", " ", body)
            for kw in ["credential", "incorrect", "invalid", "captcha",
                       "verify", "attempt", "suspend", "expire"]:
                m = re.search(kw, flat, re.IGNORECASE)
                if m:
                    start = max(0, m.start() - 90)
                    snippet = flat[start:m.start() + 90]
                    print(f"  [{kw}] ...{snippet}...")
        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        browser.close()
        return ok, cookies


def report_visibility(session, label):
    banner(f"WHAT IS VISIBLE: {label}")
    r = session.get(f"{ROOT}/search", params=SEARCH_PARAMS, timeout=45)
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    print(f"  HTTP {r.status_code}, {len(r.text)} bytes")

    masked = MASKED.findall(text)
    real = [p for p in REAL_PRICE.findall(text) if "x" not in p.lower()]
    print(f"  masked prices (RM98,xxx) : {len(masked)}  {masked[:3]}")
    print(f"  real prices              : {len(real)}  {real[:3]}")
    print(f"  'Login to view'          : {text.lower().count('login to view')}")
    days = DAY_DATE.findall(text)
    print(f"  day-precision dates      : {len(days)}  {days[:3]}")

    a = soup.find("a", href=re.compile(r"/property/"))
    if not a:
        print("  no listing anchors")
        return
    url = a["href"]
    if url.startswith("/"):
        url = ROOT + url
    d = session.get(url, timeout=45)
    dt = BeautifulSoup(d.text, "html.parser").get_text(" ", strip=True)
    print(f"\n  detail page: HTTP {d.status_code}, {len(d.text)} bytes")
    print(f"    'Locked' occurrences   : {dt.count('Locked')}")
    print(f"    'Unlock Premium'       : {'yes' if 'Unlock Premium' in dt else 'no'}")
    for label_ in ["Reserve Price", "Auction Price", "Auction Date", "Auctioneer",
                   "Auction Venue", "Solicitor", "Address"]:
        i = dt.find(label_)
        print(f"    [{label_}] "
              + (f"...{dt[i:i + 110]}..." if i >= 0 else "(not present)"))


def main():
    email = os.getenv("LELONGTIPS_EMAIL", "")
    password = os.getenv("LELONGTIPS_PASSWORD", "")
    banner("CREDENTIALS")
    if not email or not password:
        print("  LELONGTIPS_EMAIL / LELONGTIPS_PASSWORD not set — cannot test login")
        return 1
    masked_email = email[:3] + "***" + (email[email.index("@"):] if "@" in email else "")
    print(f"  account: {masked_email}")

    guest = requests.Session()
    guest.headers.update({"User-Agent": UA})
    report_visibility(guest, "logged OUT (baseline)")

    banner("LOGIN ATTEMPT (browser, so reCAPTCHA v3 can run)")
    try:
        ok, cookies = login_with_browser(email, password)
    except Exception as e:
        print(f"  login error: {e}")
        return 1
    if not ok:
        print("\nLogin failed — nothing further to compare.")
        return 1

    member = requests.Session()
    member.headers.update({"User-Agent": UA})
    for k, v in cookies.items():
        member.cookies.set(k, v, domain="www.lelongtips.com.my")
    report_visibility(member, "logged IN")

    print("\nCompare the two blocks above: if 'real prices' is still 0 and "
          "'masked prices' is unchanged, this account does not unlock prices.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
