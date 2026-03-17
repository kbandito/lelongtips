#!/usr/bin/env python3
"""
Fixed Full Scraping Property Monitor - Option A
Eliminates over-extraction and duplicates to get real properties
Improved property identification and validation
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import os
from datetime import datetime, timedelta
import re
import tempfile
from pathlib import Path
import urllib.parse
import hashlib
import html  # for Telegram HTML escaping


def categorize_property_type(title):
    """Categorize property from title into one of:
    Landed, High-rise, Commercial, Industrial, Land.

    The source website labels everything broadly (e.g. "Commercial" for houses).
    This function derives the correct category from the actual property title,
    which describes the physical property type (e.g. "2 Storey Semi Detached House").
    """
    t = re.sub(r"\[.*?\]", "", title, flags=re.DOTALL).strip().lower()

    # ── Landed Residential ──────────────────────────────────────
    if re.search(r"(semi.?detached|detached)\s*(house|home|plot|lot)", t):
        return "Landed"
    if re.search(r"bungalow", t):
        return "Landed"
    if re.search(r"terrace\s*house", t):
        return "Landed"
    if re.search(r"cluster\s*(semi|house|design)", t):
        return "Landed"
    if re.search(r"link\s*(semi|house|bungalow)", t):
        return "Landed"
    if re.search(r"town\s*(house|villa)", t):
        return "Landed"
    if re.search(r"villa\b", t):
        return "Landed"
    if re.search(r"\d+\.?\d*\s*storey\s*(semi|detached|cluster|link|zero)", t):
        return "Landed"
    if t.rstrip().endswith("house") or t.rstrip().endswith("houses"):
        return "Landed"
    if re.search(r"(detached|semi|terrace|house|bungalow)\s*(plot|lot)\b", t):
        return "Landed"
    if re.search(r"residential\s*(lot|plot|building|terrace)", t):
        return "Landed"
    if re.search(r"vacant\s*(semi|detached|residential|terrace)", t):
        return "Landed"
    if re.search(r"housing\s*(lot|plot|land)", t):
        return "Landed"

    # ── High-rise Residential ───────────────────────────────────
    if re.search(
        r"apartment|condominium|condo\b|flat\b|penthouse|service\s+suite", t
    ):
        return "High-rise"
    if re.search(r"\bsoho\b", t):
        return "High-rise"
    if re.search(r"residence\b", t) and "land" not in t:
        return "High-rise"
    if re.search(r"resid(ential|ence)", t) and "land" not in t:
        return "High-rise"

    # ── Industrial (before Commercial — factories have "shop" in address) ─
    if re.search(r"factory|warehouse|industrial", t):
        return "Industrial"

    # ── Land ────────────────────────────────────────────────────
    if re.search(r"\bland\b", t):
        return "Land"
    if re.search(r"vacant\s*(plot|lot|building)", t):
        return "Land"
    if re.search(r"parcels?\s+of", t):
        return "Land"
    if re.search(r"residential\s*land", t):
        return "Land"

    # ── Commercial ──────────────────────────────────────────────
    if re.search(r"shop", t):
        return "Commercial"
    if re.search(r"office|sofo|sovo|business\s*(suite|centre|center)", t):
        return "Commercial"
    if re.search(r"retail", t):
        return "Commercial"
    if re.search(r"hotel", t):
        return "Commercial"
    if re.search(r"commercial", t):
        return "Commercial"
    if re.search(r"(mall|plaza|complex|square|kiosk)\b", t):
        return "Commercial"
    if re.search(r"strata|stratified", t):
        return "Commercial"
    if re.search(r"convention\s*hall", t):
        return "Commercial"

    return "Commercial"  # default fallback


class FixedFullScrapingPropertyMonitor:
    def __init__(self):
        # Set to False to skip expired auction dates; True to collect all listings
        self.include_expired = os.environ.get("INCLUDE_EXPIRED", "true").lower() != "false"

        # Try to use repository data directory, fall back to temp if no write permissions
        self.base_path = (
            Path(__file__).parent.parent
            if Path(__file__).parent.name == "src"
            else Path(__file__).parent
        )
        self.data_path = self.base_path / "data"

        # Create data directory if possible, otherwise use temp
        try:
            self.data_path.mkdir(exist_ok=True)
            self.use_persistent_storage = True
            print(f"📁 Using persistent storage: {self.data_path}")
        except Exception:
            self.data_path = Path(tempfile.mkdtemp())
            self.use_persistent_storage = False
            print(f"📁 Using temporary storage: {self.data_path}")

        # File paths
        self.properties_database = self.data_path / "properties.json"
        self.changes_history = self.data_path / "changes.json"
        self.daily_stats = self.data_path / "daily_stats.json"
        self.scraping_progress = self.data_path / "scraping_progress.json"

        # Base search URL (without page parameter)
        self.base_url = "https://www.lelongtips.com.my/search"
        self.root_url = "https://www.lelongtips.com.my"
        self.search_params = {
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

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

        # Session for authenticated scraping (persists cookies)
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.logged_in = False

        # Rate limiting settings
        self.request_delay = 2  # seconds between requests
        self.max_retries = 3
        self.timeout = 30

        # Validation settings
        self.min_price = 50000  # Minimum valid price RM50,000
        self.max_price = 500000000  # Maximum valid price RM500M

        # Duplicate detection (within a run)
        self.seen_property_hashes = set()

        # Notification settings
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

        print("🚀 Fixed Full Scraping Property Monitor - Eliminates Over-Extraction")
        print(
            f"🤖 Telegram configured: "
            f"{'✅' if self.telegram_bot_token and self.telegram_chat_id else '❌'}"
        )
        print(f"💾 Persistent storage: {'✅' if self.use_persistent_storage else '❌'}")
        print(f"⏱️ Rate limiting: {self.request_delay}s between requests")
        print(f"💰 Price validation: RM{self.min_price:,} - RM{self.max_price:,}")

    # ---------- Utility ----------
    def tg_escape_html(self, text):
        """Escape text for Telegram HTML parse_mode."""
        return html.escape(str(text), quote=True)

    def normalize_text(self, s):
        if not s:
            return ""
        s = s.strip().lower()
        s = re.sub(r"\s+", " ", s)
        return s

    def normalize_size(self, s):
        if not s:
            return ""
        s = s.lower()
        # extract digits
        digits = re.findall(r"\d+", s)
        num = "".join(digits) if digits else ""
        # keep unit rough
        unit = "sqft" if "sq.ft" in s or "sqft" in s else ""
        return f"{num}{unit}"

    def generate_stable_key(self, prop):
        """
        Generate a stable identity key for a property:
        title + location + size + address (normalized).
        This should not change when price/auction date change.
        Address is critical to distinguish properties with generic titles
        like 'Shop Office' or 'Retail Lot'.
        """
        title = self.normalize_text(prop.get("title", ""))
        location = self.normalize_text(prop.get("location", ""))
        size = self.normalize_size(prop.get("size", ""))
        address = self.normalize_text(prop.get("header_full", "") or "")
        return f"{title}|{location}|{size}|{address}"

    # ---------- DB ----------
    def load_properties_database(self):
        """Load the properties database"""
        if self.properties_database.exists():
            try:
                with open(self.properties_database, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Error loading properties database: {e}")
        return {}

    def save_properties_database(self, database):
        """Save the properties database"""
        try:
            with open(self.properties_database, "w", encoding="utf-8") as f:
                json.dump(database, f, indent=2, ensure_ascii=False)
            print(f"💾 Properties database saved: {len(database)} properties")
            return True
        except Exception as e:
            print(f"⚠️ Could not save properties database: {e}")
            return False

    def save_scraping_progress(self, progress_data):
        """Save scraping progress for monitoring"""
        try:
            with open(self.scraping_progress, "w", encoding="utf-8") as f:
                json.dump(progress_data, f, indent=2)
            return True
        except Exception as e:
            print(f"⚠️ Could not save scraping progress: {e}")
            return False

    def save_changes_history(self, new_listings, changed_properties):
        """Save changes history for tracking over time"""
        try:
            existing = []
            if self.changes_history.exists():
                with open(self.changes_history, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                    if not isinstance(existing, list):
                        existing = []

            entry = {
                "scan_date": datetime.now().isoformat(),
                "new_listings_count": len(new_listings),
                "changed_properties_count": len(changed_properties),
                "new_listing_ids": list(new_listings.keys()),
                "changes": [],
            }

            for prop_id, data in changed_properties.items():
                for change in data.get("changes", []):
                    entry["changes"].append(
                        {
                            "property_id": prop_id,
                            "title": data["property"].get("title", "Unknown"),
                            "type": change["type"],
                            "field": change["field"],
                            "old_value": change["old_value"],
                            "new_value": change["new_value"],
                            "change_date": change["change_date"],
                        }
                    )

            existing.append(entry)

            with open(self.changes_history, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            print(f"💾 Changes history saved: {len(entry['changes'])} changes recorded")
            return True
        except Exception as e:
            print(f"⚠️ Could not save changes history: {e}")
            return False

    def save_daily_stats(self, current_properties, new_listings, changed_properties, total_tracked):
        """Save scan statistics"""
        try:
            stats = {
                "date": datetime.now().isoformat(),
                "total_listings": len(current_properties),
                "total_tracked": total_tracked,
                "new_listings": len(new_listings),
                "changed_properties": len(changed_properties),
            }
            with open(self.daily_stats, "w", encoding="utf-8") as f:
                json.dump(stats, f, indent=2)
            print(f"💾 Scan stats saved")
            return True
        except Exception as e:
            print(f"⚠️ Could not save scan stats: {e}")
            return False

    def create_property_hash(self, title, price, auction_date, location, size):
        """
        Create a hash for duplicate detection (within a run).

        Include price + date so we treat "same identity, different price/date"
        as distinct entries for coverage checks, but we de-dup by this hash.
        """
        content = f"{title}_{price}_{auction_date}_{location}_{size}".lower()
        return hashlib.md5(content.encode()).hexdigest()

    def create_property_id(self, title, location, size, address=""):
        """
        Create a (relatively) stable property ID.

        IMPORTANT: does NOT include price or auction_date, so a price change
        does not create a "new" property. We rely on title+location+size+address.
        """
        clean_title = re.sub(r"[^\w\s]", "", title)
        clean_location = re.sub(r"[^\w\s]", "", location)
        clean_size = re.sub(r"[^\w\s]", "", size)
        clean_address = re.sub(r"[^\w\s]", "", address or "")

        base = f"{clean_title}_{clean_location}_{clean_size}_{clean_address}".strip()
        base = re.sub(r"\s+", "_", base).lower()
        if not base:
            base = "property"
        return base[:150]

    # ---------- Validation ----------
    def validate_price(self, price_str):
        """Validate if price is reasonable for property auction"""
        try:
            price_clean = re.sub(r"[^\d.]", "", price_str)
            if not price_clean:
                return False, 0

            price = float(price_clean)
            if price < 1000:
                price *= 1000  # Convert to full amount

            if self.min_price <= price <= self.max_price:
                return True, int(price)
            else:
                return False, int(price)
        except Exception:
            return False, 0

    def validate_auction_date(self, date_str):
        """Validate if auction date is reasonable.
        In INCLUDE_EXPIRED mode, accept any parseable date.
        In normal mode, only accept future/current auction dates.
        """
        try:
            if not re.match(r"\d{1,2}\s+\w{3}\s+\d{4}\s+\(\w{3}\)", date_str):
                return False

            if self.include_expired:
                # Accept any valid-format date regardless of how old
                return True

            # Normal mode: accept only upcoming or current-year auctions
            date_no_day = re.sub(r"\s*\(\w{3}\)", "", date_str).strip()
            try:
                auction_dt = datetime.strptime(date_no_day, "%d %b %Y")
                # Accept if auction date is today or in the future
                return auction_dt.date() >= datetime.now().date()
            except ValueError:
                pass

            return False
        except Exception:
            return False

    # ---------- LOGIN ----------
    def login(self):
        """Login to lelongtips.com.my using Playwright browser, then transfer cookies to requests session."""
        email = os.getenv("LELONGTIPS_EMAIL", "")
        password = os.getenv("LELONGTIPS_PASSWORD", "")
        if not email or not password:
            print("⚠️ No LELONGTIPS_EMAIL/PASSWORD set, scraping as guest")
            return False

        print(f"🔐 Login: attempting with Playwright (email={email[:3]}***{email[email.index('@'):]}) ...")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("🔐 Playwright not installed, falling back to requests login")
            return self._login_requests(email, password)

        login_url = f"{self.root_url}/login"

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = context.new_page()

                # Navigate to login page
                page.goto(login_url, wait_until="networkidle", timeout=30000)
                print(f"🔐 Login page loaded: {page.url}")

                # Find the login form — it contains a password input
                password_input = page.locator('input[type="password"]')
                login_form = password_input.locator('xpath=ancestor::form')

                # Fill in the login form fields scoped to the correct form
                login_form.locator('input[name="email"], input[type="email"]').fill(email)
                password_input.fill(password)

                # Click the submit button within the login form
                submit_btn = login_form.locator('button[type="submit"], input[type="submit"]')
                with page.expect_navigation(wait_until="networkidle", timeout=30000):
                    submit_btn.click()

                final_url = page.url
                print(f"🔐 After login: {final_url}")

                self.logged_in = "/login" not in final_url

                if self.logged_in:
                    # Transfer browser cookies to requests session
                    cookies = context.cookies()
                    for cookie in cookies:
                        self.session.cookies.set(
                            cookie["name"],
                            cookie["value"],
                            domain=cookie.get("domain", ""),
                            path=cookie.get("path", "/"),
                        )
                    print(f"🔐 Login: ✅ success — transferred {len(cookies)} cookies to session")
                else:
                    # Try to capture error message from the page
                    for sel in [".alert-danger", ".invalid-feedback", ".error"]:
                        els = page.query_selector_all(sel)
                        for el in els:
                            txt = el.inner_text().strip()
                            if txt:
                                print(f"🔐 Page error: {txt}")
                    print("🔐 Login: ❌ failed")

                browser.close()

            return self.logged_in

        except Exception as e:
            print(f"🔐 Playwright login failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _login_requests(self, email, password):
        """Fallback login using plain requests (no JS support)."""
        login_url = f"{self.root_url}/login"
        try:
            resp = self.session.get(login_url, timeout=self.timeout)
            soup = BeautifulSoup(resp.content, "html.parser")
            csrf_input = soup.find("input", {"name": "_token"})
            token = csrf_input["value"] if csrf_input else ""

            data = {"_token": token, "email": email, "password": password}
            resp = self.session.post(
                login_url, data=data, timeout=self.timeout, allow_redirects=True
            )
            self.logged_in = resp.ok and "/login" not in resp.url
            print(f"🔐 Requests login: {'✅ success' if self.logged_in else '❌ failed'}")
            return self.logged_in
        except Exception as e:
            print(f"🔐 Requests login failed: {e}")
            return False

    # ---------- HTTP ----------
    def make_request(self, url, params=None, retry_count=0):
        """Make HTTP request with retry logic and rate limiting"""
        try:
            time.sleep(self.request_delay)
            response = self.session.get(
                url, params=params, timeout=self.timeout
            )
            response.raise_for_status()
            return response
        except Exception as e:
            if retry_count < self.max_retries:
                print(
                    f"⚠️ Request failed (attempt {retry_count + 1}/"
                    f"{self.max_retries + 1}): {e}"
                )
                time.sleep(5 * (retry_count + 1))
                return self.make_request(url, params, retry_count + 1)
            else:
                print(f"❌ Request failed after {self.max_retries + 1} attempts: {e}")
                raise e

    def get_total_pages_and_results(self):
        """Get total number of pages and results from first page"""
        print("🔍 Getting total pages and results...")

        try:
            response = self.make_request(self.base_url, self.search_params)
            soup = BeautifulSoup(response.content, "html.parser")

            total_results = 0
            result_text = soup.find(string=re.compile(r"Result\(s\):\s*[\d,]+"))
            if result_text:
                result_match = re.search(r"Result\(s\):\s*([\d,]+)", result_text)
                if result_match:
                    total_results = int(result_match.group(1).replace(",", ""))

            total_pages = 1
            pagination_links = soup.find_all("a", href=re.compile(r"page=\d+"))
            page_numbers = []

            for link in pagination_links:
                href = link.get("href", "")
                page_match = re.search(r"page=(\d+)", href)
                if page_match:
                    page_num = int(page_match.group(1))
                    page_numbers.append(page_num)

            if page_numbers:
                total_pages = max(page_numbers)
            else:
                # 12 listings per page
                if total_results > 12:
                    total_pages = min((total_results + 11) // 12, 600)

            print(f"📊 Found {total_results:,} total results across {total_pages} pages")
            return total_results, total_pages

        except Exception as e:
            print(f"❌ Error getting pagination info: {e}")
            return 7000, 590  # Fallback (~7000 listings, 12 per page)

    # ---------- Extraction ----------
    def extract_properties_from_page(self, page_content, page_num):
        """Extract property data from a single page with improved validation"""
        properties = []
        page_duplicates = 0
        page_invalid = 0

        try:
            soup = BeautifulSoup(page_content, "html.parser")
            potential_properties = []

            # Strategy 1: find listing cards via /property/ links with stretched-link
            # Each listing card has exactly one <a class="stretched-link" href="/property/...">
            property_links = soup.find_all(
                "a",
                href=re.compile(r"/property/"),
                class_=re.compile(r"stretched-link"),
            )

            seen_containers = set()  # track by element id to avoid duplicates
            for link in property_links:
                try:
                    container = link.parent
                    container_attempts = 0

                    while container and container.name != "html" and container_attempts < 6:
                        container_text = container.get_text()

                        has_price = bool(re.search(r"RM[\d,]+", container_text))
                        has_date = bool(
                            re.search(
                                r"\d{1,2}\s+\w{3}\s+\d{4}\s+\(\w{3}\)", container_text
                            )
                        )

                        if has_price and has_date:
                            # Prefer smallest container: check it doesn't contain
                            # multiple prices (which would mean it wraps several cards)
                            price_count = len(re.findall(r"RM[\d,]+", container_text))
                            if price_count > 2:
                                # Container too large (multiple listings), keep walking
                                container = container.parent
                                container_attempts += 1
                                continue

                            # Deduplicate by actual DOM element identity
                            elem_id = id(container)
                            if elem_id not in seen_containers:
                                seen_containers.add(elem_id)
                                container_hash = hashlib.md5(
                                    container_text.encode()
                                ).hexdigest()
                                if container_hash not in [
                                    p.get("container_hash") for p in potential_properties
                                ]:
                                    potential_properties.append(
                                        {
                                            "container": container,
                                            "container_text": container_text,
                                            "container_hash": container_hash,
                                        }
                                    )
                            break

                        container = container.parent
                        container_attempts += 1
                except Exception:
                    continue

            # Strategy 2 (fallback): walk up from RM price text nodes
            if not potential_properties:
                price_elements = soup.find_all(string=re.compile(r"RM[\d,]+"))

                for price_elem in price_elements:
                    try:
                        container = price_elem.parent
                        container_attempts = 0

                        while container and container.name != "html" and container_attempts < 10:
                            container_text = container.get_text()

                            has_price = bool(re.search(r"RM[\d,]+", container_text))
                            has_date = bool(
                                re.search(
                                    r"\d{1,2}\s+\w{3}\s+\d{4}\s+\(\w{3}\)", container_text
                                )
                            )

                            if has_price and has_date:
                                container_hash = hashlib.md5(
                                    container_text.encode()
                                ).hexdigest()
                                if container_hash not in [
                                    p.get("container_hash") for p in potential_properties
                                ]:
                                    potential_properties.append(
                                        {
                                            "container": container,
                                            "container_text": container_text,
                                            "container_hash": container_hash,
                                        }
                                    )
                                break

                            container = container.parent
                            container_attempts += 1
                    except Exception:
                        continue

            print(
                f"📄 Page {page_num}: "
                f"Found {len(potential_properties)} potential property containers"
            )

            rejection_reasons = {}
            for i, prop_info in enumerate(potential_properties):
                try:
                    property_data = self.extract_and_validate_property(
                        prop_info["container"],
                        prop_info["container_text"],
                        page_num,
                        i,
                    )

                    if isinstance(property_data, dict):
                        prop_hash = self.create_property_hash(
                            property_data["title"],
                            property_data["price"],
                            property_data["auction_date"],
                            property_data["location"],
                            property_data["size"],
                        )

                        if prop_hash not in self.seen_property_hashes:
                            self.seen_property_hashes.add(prop_hash)
                            property_data["property_hash"] = prop_hash
                            properties.append(property_data)
                        else:
                            page_duplicates += 1
                    elif isinstance(property_data, str):
                        # Rejection reason string
                        rejection_reasons[property_data] = rejection_reasons.get(property_data, 0) + 1
                        page_invalid += 1
                    else:
                        rejection_reasons["unknown"] = rejection_reasons.get("unknown", 0) + 1
                        page_invalid += 1
                except Exception as e:
                    print(f"⚠️ Error processing property {i} on page {page_num}: {e}")
                    page_invalid += 1
                    continue

            reason_str = ""
            if rejection_reasons:
                reason_str = " | rejected: " + ", ".join(
                    f"{k}={v}" for k, v in sorted(rejection_reasons.items())
                )
            print(
                f"✅ Page {page_num}: Extracted {len(properties)} valid properties "
                f"(skipped {page_duplicates} duplicates, {page_invalid} invalid{reason_str})"
            )
            return properties

        except Exception as e:
            print(f"❌ Error processing page {page_num}: {e}")
            return []

    def extract_and_validate_property(self, container, container_text, page_num, index):
        """Extract and validate property data from container node + text"""
        try:
            property_data = {}

            # ---------- HEADER / ADDRESS ----------
            header_short = None  # e.g. "Plaza Haji Taib, Kuala Lumpur"
            header_full = None  # e.g. "Plaza Haji Taib, 42, Lorong ..."

            # Build list of ancestor nodes that likely represent the card
            search_nodes = []
            node = container
            steps = 0
            while node is not None and node.name != "html" and steps < 6:
                search_nodes.append(node)
                node = node.parent
                steps += 1

            try:
                for node in search_nodes:
                    # Short header, e.g. "Plaza Haji Taib, Kuala Lumpur"
                    if not header_short:
                        p_tag = node.find(
                            "p", class_=re.compile(r"text-muted", re.IGNORECASE)
                        )
                        if p_tag:
                            txt = p_tag.get_text(strip=True)
                            if txt:
                                header_short = txt

                    # Full address, e.g. "Plaza Haji Taib, 42, Lorong Haji Taib ..."
                    if not header_full:
                        h5_tag = node.find(
                            "h5", class_=re.compile(r"fw-bold", re.IGNORECASE)
                        )
                        if h5_tag:
                            txt = h5_tag.get_text(separator=" ", strip=True)
                            if txt:
                                header_full = txt

                    # Old layout: Unit No., Jalan Tasik Raja Lumu...
                    if not header_full:
                        h3_tag = node.find(
                            "h3", class_=re.compile(r"fw-bold", re.IGNORECASE)
                        )
                        if h3_tag:
                            txt = h3_tag.get_text(separator=" ", strip=True)
                            txt = re.sub(
                                r"\s*Login to view\s*",
                                "",
                                txt,
                                flags=re.IGNORECASE,
                            )
                            txt = re.sub(
                                r"^\s*Unit No\.\s*,?\s*",
                                "",
                                txt,
                                flags=re.IGNORECASE,
                            )
                            txt = txt.strip(" ,")
                            if txt:
                                header_full = txt

            except Exception:
                pass

            if header_short:
                property_data["header_short"] = header_short
            if header_full:
                property_data["header_full"] = header_full
            if header_full:
                property_data["header"] = header_full
            elif header_short:
                property_data["header"] = header_short

            # ---------- URL / LINK ----------
            listing_url = None
            listing_title = None
            try:
                # Collect <a> tags from all search_nodes to cover entire card
                anchors = []
                for n in search_nodes:
                    anchors.extend(n.find_all("a", href=True))

                candidates = []
                for a in anchors:
                    href = a.get("href", "")
                    if not href:
                        continue
                    # Skip login / javascript / anchors
                    if "/login" in href or href.startswith("#") or href.lower().startswith(
                        "javascript:"
                    ):
                        continue

                    full_url = urllib.parse.urljoin(self.root_url, href)

                    title_attr = a.get("title") or ""
                    link_text = a.get_text(strip=True) or ""
                    if title_attr and title_attr.lower() == "login to view":
                        title_attr = ""
                    if link_text and link_text.lower() == "login to view":
                        link_text = ""

                    # Priority:
                    # 3 - /property/ and class has stretched-link
                    # 2 - /property/ anywhere
                    # 1 - other link (fallback)
                    priority = 1
                    classes = a.get("class", [])
                    class_str = " ".join(classes).lower() if classes else ""

                    if "/property/" in href:
                        priority = 2
                        if "stretched-link" in class_str:
                            priority = 3

                    candidates.append(
                        (priority, full_url, title_attr.strip(), link_text.strip())
                    )

                if candidates:
                    # Pick highest priority
                    candidates.sort(key=lambda x: x[0], reverse=True)
                    best = candidates[0]
                    listing_url = best[1]
                    # Prefer non-empty title_attr; else link_text
                    if best[2]:
                        listing_title = best[2]
                    elif best[3]:
                        listing_title = best[3]

            except Exception:
                pass

            # ---------- PRICE ----------
            price_match = re.search(r"RM([\d,]+)", container_text)
            if not price_match:
                return "no_price"
            price_str = f"RM{price_match.group(1)}"
            is_valid_price, price_value = self.validate_price(price_str)
            if not is_valid_price:
                return "bad_price"
            property_data["price"] = price_str
            property_data["price_value"] = price_value

            # ---------- AUCTION DATE ----------
            date_match = re.search(
                r"(\d{1,2}\s+\w{3}\s+\d{4}\s+\(\w{3}\))", container_text
            )
            if not date_match:
                return "no_date"
            auction_date = date_match.group(1)
            if not self.validate_auction_date(auction_date):
                return "expired"
            property_data["auction_date"] = auction_date

            # ---------- SIZE ----------
            size_match = re.search(r"([\d,]+\s*sq\.ft)", container_text)
            if size_match:
                property_data["size"] = size_match.group(1)
            else:
                property_data["size"] = "Size not specified"

            # ---------- TITLE (TYPE / LABEL) ----------
            title = None
            if listing_title:
                title = listing_title
            else:
                # Pattern like "3 Storey Shop Office"
                m_storey = re.search(
                    r"\d+\s+Storey\s+Shop\s+Office", container_text, flags=re.IGNORECASE
                )
                if m_storey:
                    title = m_storey.group(0).strip().title()
                else:
                    title_patterns = [
                        r"([A-Z][a-zA-Z\s&]+(?:Office|Tower|Plaza|Centre|Center|Complex|Building|Mall|Square))",
                        r"([A-Z][a-zA-Z\s&]+(?:Apartment|Condominium|Residence|Suites|Condo))",
                        r"([A-Z][a-zA-Z\s&]+(?:Shop|Retail|Commercial|Store))",
                        r"([A-Z][a-zA-Z\s&]+(?:Factory|Warehouse|Industrial|Plant))",
                        r"([A-Z][a-zA-Z\s&,]+(?:Land|Plot|Lot))",
                        r"(Taman\s+[A-Z][a-zA-Z\s&]+)",
                        r"(Bandar\s+[A-Z][a-zA-Z\s&]+)",
                        r"(Menara\s+[A-Z][a-zA-Z\s&]+)",
                    ]
                    for pattern in title_patterns:
                        title_match = re.search(pattern, container_text)
                        if title_match:
                            candidate_title = title_match.group(1).strip()
                            if (
                                5 <= len(candidate_title) <= 100
                                and not re.match(r"^\d+$", candidate_title)
                            ):
                                title = candidate_title
                                break

            if not title:
                title = f"Property Listing P{page_num}-{index}"
            property_data["title"] = title

            # ---------- LOCATION ----------
            location_patterns = [
                r"(Kuala Lumpur[^,\n.]*)",
                r"(Selangor[^,\n.]*)",
                r"(Shah Alam[^,\n.]*)",
                r"(Petaling Jaya[^,\n.]*)",
                r"(Subang[^,\n.]*)",
                r"(Klang[^,\n.]*)",
                r"(Cyberjaya[^,\n.]*)",
                r"(Kota Damansara[^,\n.]*)",
                r"(Mont Kiara[^,\n.]*)",
                r"(Bangsar[^,\n.]*)",
                r"(Kajang[^,\n.]*)",
                r"(Puchong[^,\n.]*)",
                r"(Ampang[^,\n.]*)",
                r"(Cheras[^,\n.]*)",
            ]
            location = "KL/Selangor"
            for pattern in location_patterns:
                location_match = re.search(pattern, container_text)
                if location_match:
                    candidate_location = location_match.group(1).strip()
                    if len(candidate_location) <= 100:
                        location = candidate_location
                        break
            property_data["location"] = location

            # ---------- PROPERTY TYPE ----------
            property_data["property_type"] = categorize_property_type(title)

            # ---------- DISCOUNT ----------
            discount_match = re.search(r"(-\d+%)", container_text)
            if discount_match:
                property_data["discount"] = discount_match.group(1)

            # ---------- IMAGE ----------
            image_url = None
            try:
                for node in search_nodes:
                    img_tags = node.find_all("img", src=True)
                    for img in img_tags:
                        src = img.get("src", "")
                        if any(skip in src.lower() for skip in [
                            "logo", "icon", "avatar", "pixel", "blank",
                            "spacer", "tracking", "1x1"
                        ]):
                            continue
                        if src.startswith("data:"):
                            continue
                        image_url = urllib.parse.urljoin(self.root_url, src)
                        break
                    if image_url:
                        break
                # Check lazy-loaded images
                if not image_url:
                    for node in search_nodes:
                        for img in node.find_all("img", attrs={"data-src": True}):
                            src = img["data-src"]
                            if not src.startswith("data:"):
                                image_url = urllib.parse.urljoin(
                                    self.root_url, src
                                )
                                break
                        if image_url:
                            break
            except Exception:
                pass
            if image_url:
                property_data["image_url"] = image_url

            # ---------- URL / META ----------
            if listing_url:
                property_data["listing_url"] = listing_url
            else:
                property_data["listing_url"] = f"{self.base_url}?page={page_num}"

            # Extract listing_id from /property/<base64id>/... URL
            listing_id = None
            if listing_url and "/property/" in listing_url:
                parts = listing_url.split("/property/")
                if len(parts) > 1:
                    listing_id = parts[1].split("/")[0]
            if listing_id:
                property_data["listing_id"] = listing_id

            property_data["url"] = f"{self.base_url}?page={page_num}"
            property_data["page_number"] = page_num
            now_iso = datetime.now().isoformat()
            property_data["last_updated"] = now_iso
            property_data["first_seen"] = now_iso

            # Stable key (for DB change detection)
            property_data["_stable_key"] = self.generate_stable_key(property_data)

            return property_data
        except Exception as e:
            return f"error:{e}"

    # ---------- Scraping loop ----------
    def scrape_all_pages(self, total_pages, total_results):
        """Scrape all pages of Lelong results with improved validation"""
        print(
            f"🚀 Starting fixed full scrape of {total_pages} pages "
            f"({total_results:,} total listings)"
        )

        all_properties = {}
        scraping_stats = {
            "start_time": datetime.now().isoformat(),
            "total_pages": total_pages,
            "total_results": total_results,
            "pages_completed": 0,
            "properties_extracted": 0,
            "duplicates_skipped": 0,
            "invalid_skipped": 0,
            "errors": [],
        }

        self.seen_property_hashes = set()

        for page_num in range(1, total_pages + 1):
            try:
                print(f"📄 Scraping page {page_num}/{total_pages}...")

                params = self.search_params.copy()
                if page_num > 1:
                    params["page"] = page_num

                response = self.make_request(self.base_url, params)
                page_properties = self.extract_properties_from_page(
                    response.text, page_num
                )

                for prop_data in page_properties:
                    property_id = self.create_property_id(
                        prop_data["title"],
                        prop_data["location"],
                        prop_data["size"],
                        prop_data.get("header_full", ""),
                    )
                    prop_data["total_results_on_site"] = total_results
                    all_properties[property_id] = prop_data

                scraping_stats["pages_completed"] = page_num
                scraping_stats["properties_extracted"] = len(all_properties)
                scraping_stats["duplicates_skipped"] = (
                    len(self.seen_property_hashes) - len(all_properties)
                )
                scraping_stats["current_page"] = page_num
                scraping_stats["last_update"] = datetime.now().isoformat()

                # 🔎 DEBUG
                print(
                    f"🔎 DEBUG: After page {page_num}, "
                    f"unique_properties={len(all_properties)}, "
                    f"hashes_seen={len(self.seen_property_hashes)}, "
                    f"duplicates_skipped={scraping_stats['duplicates_skipped']}"
                )

                # Periodic progress save
                if page_num % 10 == 0:
                    self.save_scraping_progress(scraping_stats)
                    coverage = (
                        (len(all_properties) / total_results) * 100
                        if total_results
                        else 0
                    )
                    print(
                        f"📊 Progress: {page_num}/{total_pages} pages, "
                        f"{len(all_properties)} properties extracted "
                        f"({coverage:.1f}% coverage)"
                    )

                # Time limit guard (e.g. GitHub Actions 20 min)
                elapsed_time = (
                    datetime.now()
                    - datetime.fromisoformat(scraping_stats["start_time"])
                ).total_seconds()
                if elapsed_time > 1200:
                    print(f"⏰ Time limit approaching, stopping at page {page_num}")
                    scraping_stats["stopped_early"] = True
                    scraping_stats["stop_reason"] = "Time limit"
                    break

            except Exception as e:
                error_msg = f"Page {page_num}: {str(e)}"
                scraping_stats["errors"].append(error_msg)
                print(f"❌ Error scraping page {page_num}: {e}")

                if len(scraping_stats["errors"]) > 10:
                    print("❌ Too many errors, stopping scrape")
                    scraping_stats["stopped_early"] = True
                    scraping_stats["stop_reason"] = "Too many errors"
                    break
                continue

        scraping_stats["end_time"] = datetime.now().isoformat()
        scraping_stats["total_properties_extracted"] = len(all_properties)
        scraping_stats["success_rate"] = (
            (scraping_stats["pages_completed"] / total_pages) * 100
            if total_pages
            else 0
        )
        scraping_stats["coverage_percentage"] = (
            (len(all_properties) / total_results) * 100 if total_results else 0
        )

        self.save_scraping_progress(scraping_stats)

        print("\n" + "=" * 80)
        print("📊 FIXED FULL SCRAPING COMPLETED")
        print("=" * 80)
        print(f"🌐 Total listings on site: {total_results:,}")
        print(
            f"📄 Pages scraped: {scraping_stats['pages_completed']}/{total_pages}"
        )
        print(f"🏠 Properties extracted: {len(all_properties)}")
        print(
            f"📈 Coverage: {scraping_stats['coverage_percentage']:.1f}%"
        )
        print(f"🔄 Duplicates skipped: {scraping_stats['duplicates_skipped']}")
        print(
            "⏱️ Duration: "
            f"{(datetime.fromisoformat(scraping_stats['end_time']) - datetime.fromisoformat(scraping_stats['start_time'])).total_seconds():.0f} seconds"
        )
        print(f"❌ Errors: {len(scraping_stats['errors'])}")
        print(f"✅ Success rate: {scraping_stats['success_rate']:.1f}%")
        print("=" * 80)

        return all_properties, scraping_stats

    # ---------- Change detection ----------
    def detect_changes(self, current_properties, database):
        """
        Detect new listings and changes in existing properties.

        NEW listing:
          - No existing DB record with same stable key (title+location+size)

        CHANGED listing:
          - There is a DB record with same stable key, and price/date differ.
        """
        new_listings = {}
        changed_properties = {}

        print(
            f"🔍 Analyzing {len(current_properties)} current vs {len(database)} stored properties"
        )

        # Pre-build indexes for matching
        stable_index = {}  # stable_key -> existing_id
        listing_id_index = {}  # listing_id -> existing_id
        address_index = {}  # normalized_address -> existing_id
        for existing_id, existing_data in database.items():
            sk = existing_data.get("_stable_key")
            if not sk:
                sk = self.generate_stable_key(existing_data)
                existing_data["_stable_key"] = sk
            if sk and sk not in stable_index:
                stable_index[sk] = existing_id

            # Index by listing_id (URL base64 ID) — most reliable
            lid = existing_data.get("listing_id")
            if lid and lid not in listing_id_index:
                listing_id_index[lid] = existing_id

            # Index by normalized address
            addr = existing_data.get("header_full", "")
            if addr:
                norm_addr = self.normalize_text(addr)
                if norm_addr and len(norm_addr) > 20 and norm_addr not in address_index:
                    address_index[norm_addr] = existing_id

        for current_id, current_data in current_properties.items():
            # Ensure current stable key exists
            sk = current_data.get("_stable_key")
            if not sk:
                sk = self.generate_stable_key(current_data)
                current_data["_stable_key"] = sk

            existing_id = None
            existing_data = None

            cur_lid = current_data.get("listing_id")
            cur_addr = self.normalize_text(
                current_data.get("header_full", "") or ""
            )
            cur_size = self.normalize_size(current_data.get("size", ""))

            # 1) Match by listing_id — but validate address matches
            #    listing_ids can be shared across different properties
            if cur_lid and cur_lid in listing_id_index:
                candidate_id = listing_id_index[cur_lid]
                candidate = database[candidate_id]
                cand_addr = self.normalize_text(
                    candidate.get("header_full", "") or ""
                )
                # Accept if addresses match, or if one side has no address
                if (
                    not cur_addr
                    or not cand_addr
                    or cur_addr == cand_addr
                ):
                    existing_id = candidate_id
                    existing_data = candidate

            # 2) Direct match by property_id key
            if not existing_id and current_id in database:
                candidate = database[current_id]
                cand_addr = self.normalize_text(
                    candidate.get("header_full", "") or ""
                )
                if (
                    not cur_addr
                    or not cand_addr
                    or cur_addr == cand_addr
                ):
                    existing_id = current_id
                    existing_data = candidate

            # 3) Match by stable key (now includes address, much safer)
            if not existing_id and sk in stable_index:
                existing_id = stable_index[sk]
                existing_data = database[existing_id]

            # 4) Match by address + size (same address, same size = same unit)
            if not existing_id and cur_addr and len(cur_addr) > 20:
                if cur_addr in address_index:
                    candidate_id = address_index[cur_addr]
                    candidate = database[candidate_id]
                    cand_size = self.normalize_size(
                        candidate.get("size", "")
                    )
                    if cur_size and cand_size and cur_size == cand_size:
                        existing_id = candidate_id
                        existing_data = candidate

            if existing_id is None:
                # Truly new listing
                new_listings[current_id] = current_data
                database[current_id] = {
                    **current_data,
                    "price_history": [
                        {
                            "price": current_data["price"],
                            "date": current_data["last_updated"],
                            "url": current_data.get("listing_url", ""),
                        }
                    ],
                    "auction_date_history": [
                        {
                            "auction_date": current_data["auction_date"],
                            "date": current_data["last_updated"],
                        }
                    ],
                }
                database[current_id]["_stable_key"] = sk
                stable_index[sk] = current_id
                if cur_lid:
                    listing_id_index[cur_lid] = current_id
            else:
                # Existing property - check for changes
                changes = []
                # Make sure existing_data has stable key
                if "_stable_key" not in existing_data:
                    existing_data["_stable_key"] = sk

                # Price change
                if current_data["price"] != existing_data["price"]:
                    changes.append(
                        {
                            "type": "price_change",
                            "field": "Auction Price",
                            "old_value": existing_data["price"],
                            "new_value": current_data["price"],
                            "change_date": current_data["last_updated"],
                        }
                    )

                    if "price_history" not in existing_data:
                        existing_data["price_history"] = [
                            {
                                "price": existing_data["price"],
                                "date": existing_data.get(
                                    "first_seen", current_data["last_updated"]
                                ),
                                "url": existing_data.get("listing_url", ""),
                            }
                        ]
                    existing_data["price_history"].append(
                        {
                            "price": current_data["price"],
                            "date": current_data["last_updated"],
                            "url": current_data.get("listing_url", ""),
                        }
                    )

                # Auction date change
                if current_data["auction_date"] != existing_data["auction_date"]:
                    changes.append(
                        {
                            "type": "auction_date_change",
                            "field": "Auction Date",
                            "old_value": existing_data["auction_date"],
                            "new_value": current_data["auction_date"],
                            "change_date": current_data["last_updated"],
                        }
                    )

                    if "auction_date_history" not in existing_data:
                        existing_data["auction_date_history"] = [
                            {
                                "auction_date": existing_data["auction_date"],
                                "date": existing_data.get(
                                    "first_seen", current_data["last_updated"]
                                ),
                            }
                        ]
                    existing_data["auction_date_history"].append(
                        {
                            "auction_date": current_data["auction_date"],
                            "date": current_data["last_updated"],
                        }
                    )

                if changes:
                    # Merge data so we keep nice original titles if any
                    prop_snapshot = {**existing_data, **current_data}
                    if existing_data.get("title") and str(
                        current_data.get("title", "")
                    ).startswith("Property Listing P"):
                        prop_snapshot["title"] = existing_data["title"]

                    changed_properties[existing_id] = {
                        "property": prop_snapshot,
                        "changes": changes,
                        "history": {
                            "price_history": existing_data.get("price_history", []),
                            "auction_date_history": existing_data.get(
                                "auction_date_history", []
                            ),
                        },
                    }

                # Update DB with latest snapshot
                database[existing_id].update(current_data)
                database[existing_id]["first_seen"] = existing_data.get(
                    "first_seen", current_data["last_updated"]
                )
                database[existing_id]["_stable_key"] = sk
                # Propagate listing_id to existing record
                if cur_lid:
                    database[existing_id]["listing_id"] = cur_lid

        print(
            f"📊 Analysis complete: {len(new_listings)} new, {len(changed_properties)} changed"
        )
        return new_listings, changed_properties

    # ---------- Telegram ----------
    def send_telegram_notification(self, message):
        """Send notification via Telegram using HTML parse_mode"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            print("⚠️ Telegram credentials not configured")
            return False

        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            max_length = 4000

            if len(message) > max_length:
                # Split on newline boundaries to avoid breaking HTML tags
                parts = []
                remaining = message
                while len(remaining) > max_length:
                    split_at = remaining.rfind("\n", 0, max_length)
                    if split_at == -1:
                        split_at = max_length
                    parts.append(remaining[:split_at])
                    remaining = remaining[split_at:].lstrip("\n")
                parts.append(remaining)
                for i, part in enumerate(parts):
                    data = {
                        "chat_id": self.telegram_chat_id,
                        "text": f"<b>Part {i+1}/{len(parts)}</b>\n\n{part}",
                        "parse_mode": "HTML",
                    }
                    response = requests.post(url, data=data, timeout=10)
                    if response.status_code != 200:
                        print(
                            f"❌ Telegram error for part {i+1}: "
                            f"{response.status_code} {response.text}"
                        )
                        return False
                    time.sleep(1)
                return True
            else:
                data = {
                    "chat_id": self.telegram_chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                }
                response = requests.post(url, data=data, timeout=10)
                if response.status_code != 200:
                    print(
                        f"❌ Telegram error: {response.status_code} {response.text}"
                    )
                return response.status_code == 200

        except Exception as e:
            print(f"❌ Error sending Telegram notification: {e}")
            return False

    def format_fixed_daily_summary(
        self,
        current_properties,
        new_listings,
        changed_properties,
        total_tracked,
        total_on_site,
        scraping_stats,
    ):
        """Format scan summary for Telegram (HTML). Compact, scannable format."""
        now = datetime.now()
        next_scan = now + timedelta(days=3)
        esc = self.tg_escape_html
        has_alerts = len(new_listings) > 0 or len(changed_properties) > 0

        # Header
        if has_alerts:
            msg = f"🚨 <b>LELONG SCAN</b> — {esc(now.strftime('%d %b %Y'))}\n\n"
        else:
            msg = f"📊 <b>LELONG SCAN</b> — {esc(now.strftime('%d %b %Y'))}\n\n"

        # Headline stats
        msg += (
            f"<b>{total_tracked:,}</b> tracked · "
            f"<b>{len(new_listings)}</b> new · "
            f"<b>{len(changed_properties)}</b> changed\n"
        )

        # New listings (top 5, compact)
        if new_listings:
            msg += f"\n🆕 <b>NEW ({len(new_listings)}):</b>\n"
            for i, (prop_id, d) in enumerate(list(new_listings.items())[:5], 1):
                title = esc(d.get("title", "Untitled"))
                loc = esc(d.get("location", ""))
                ptype = esc(d.get("property_type", ""))
                size = esc(d.get("size", ""))
                price = esc(d.get("price", ""))
                auction = esc(d.get("auction_date", ""))
                url = d.get("listing_url") or d.get("url", "")

                msg += f"\n{i}. <b>{title}</b>"
                if loc:
                    msg += f" — {loc}"
                msg += "\n"

                details = [x for x in [ptype, size, price, auction] if x and x != "-"]
                if details:
                    msg += f"   {' · '.join(details)}\n"

                if url:
                    msg += f'   <a href="{esc(url)}">View listing</a>\n'

            if len(new_listings) > 5:
                msg += f"\n   <i>+{len(new_listings) - 5} more — send /new to see all</i>\n"

        # Changed properties (top 5, compact)
        if changed_properties:
            msg += f"\n🔄 <b>CHANGES ({len(changed_properties)}):</b>\n"
            for i, (prop_id, data) in enumerate(list(changed_properties.items())[:5], 1):
                prop = data["property"]
                changes = data["changes"]
                title = esc(prop.get("title", "Untitled"))
                url = prop.get("listing_url") or prop.get("url", "")

                loc = esc(prop.get("location", ""))
                size = esc(prop.get("size", ""))
                ptype = esc(prop.get("property_type", ""))

                msg += f"\n{i}. <b>{title}</b>"
                if loc:
                    msg += f" — {loc}"
                msg += "\n"

                meta = [x for x in [ptype, size] if x and x != "-" and x != "Size not specified"]
                if meta:
                    msg += f"   {' · '.join(meta)}\n"

                for change in changes:
                    old = esc(change["old_value"])
                    new = esc(change["new_value"])
                    if change["type"] == "price_change":
                        msg += f"   💰 <s>{old}</s> → <b>{new}</b>\n"
                    elif change["type"] == "auction_date_change":
                        msg += f"   📅 <s>{old}</s> → <b>{new}</b>\n"

                if url:
                    msg += f'   <a href="{esc(url)}">View listing</a>\n'

            if len(changed_properties) > 5:
                msg += f"\n   <i>+{len(changed_properties) - 5} more — send /changes to see all</i>\n"

        # No alerts
        if not has_alerts:
            msg += "\n✨ No new listings or changes — market is stable.\n"

        # Footer
        msg += f"\n⏭ Next scan: {esc(next_scan.strftime('%d %b %Y, 9:00 PM'))}\n"
        msg += "🔍 Send /help to search properties"

        return msg

    # ---------- Main ----------
    def save_snapshot(self, properties, scraping_stats):
        """Save raw scrape snapshot to data/snapshots/YYYY-MM-DD.json"""
        snapshots_dir = self.data_path / "snapshots"
        snapshots_dir.mkdir(exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        snapshot_path = snapshots_dir / f"{date_str}.json"
        snapshot = {
            "scan_date": datetime.now().isoformat(),
            "scraping_stats": scraping_stats,
            "properties": properties,
        }
        with open(snapshot_path, "w") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
        print(f"Snapshot saved: {snapshot_path} ({len(properties)} properties)")
        return snapshot_path

    def run_monitoring(self):
        """Main monitoring function: scrape, save snapshot, then reprocess."""
        print(
            f"Starting scrape at {datetime.now()}"
        )

        # Attempt login for full details (unit numbers in addresses)
        self.login()

        try:
            total_results, total_pages = self.get_total_pages_and_results()
            current_properties, scraping_stats = self.scrape_all_pages(
                total_pages, total_results
            )

            if not current_properties:
                print("No properties extracted")
                error_message = (
                    "<b>Scraping Failed</b>\n\n"
                    f"Could not extract properties from {total_pages} pages.\n"
                    f"Total listings on site: {total_results:,}\n"
                    "Will retry in 3 days."
                )
                self.send_telegram_notification(error_message)
                return "Scraping failed"

            # Save raw snapshot — this is the source of truth
            self.save_snapshot(current_properties, scraping_stats)

            # Reprocess all snapshots to rebuild database
            from reprocess import reprocess_all
            database, new_listings, changed_properties = reprocess_all(
                self.data_path
            )

            # Save derived data files
            self.save_properties_database(database)
            self.save_changes_history(new_listings, changed_properties)
            self.save_daily_stats(
                current_properties, new_listings, changed_properties, len(database)
            )

            summary_message = self.format_fixed_daily_summary(
                current_properties,
                new_listings,
                changed_properties,
                len(database),
                total_results,
                scraping_stats,
            )

            if self.send_telegram_notification(summary_message):
                print("Summary notification sent")
            else:
                print("Failed to send notification")
                print(summary_message)

            coverage = scraping_stats.get("coverage_percentage", 0)
            print(f"\nScrape complete: {len(current_properties)} extracted, "
                  f"{len(new_listings)} new, {len(changed_properties)} changed, "
                  f"{coverage:.1f}% coverage, {len(database)} total tracked")

            return (
                f"Scrape complete: {total_results:,} on site, "
                f"{len(current_properties)} extracted, "
                f"{len(new_listings)} new, {len(changed_properties)} changed"
            )
        except Exception as e:
            print(f"Error: {e}")
            if self.telegram_bot_token and self.telegram_chat_id:
                err_html = self.tg_escape_html(str(e))
                error_notification = (
                    "<b>Scraping Error</b>\n\n"
                    f"<pre>{err_html}</pre>\n\n"
                    f"Time: {self.tg_escape_html(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}\n"
                    "Will retry in 3 days."
                )
                self.send_telegram_notification(error_notification)
            raise e


if __name__ == "__main__":
    monitor = FixedFullScrapingPropertyMonitor()
    report = monitor.run_monitoring()
    print(report)
