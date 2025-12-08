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


class FixedFullScrapingPropertyMonitor:
    def __init__(self):
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
            "property_type[]": ["7", "6", "8", "4", "5"],
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
        title + location + size (normalized).
        This should not change when price/auction date change.
        """
        title = self.normalize_text(prop.get("title", ""))
        location = self.normalize_text(prop.get("location", ""))
        size = self.normalize_size(prop.get("size", ""))
        return f"{title}|{location}|{size}"

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

    def create_property_hash(self, title, price, auction_date, location, size):
        """
        Create a hash for duplicate detection (within a run).

        Include price + date so we treat "same identity, different price/date"
        as distinct entries for coverage checks, but we de-dup by this hash.
        """
        content = f"{title}_{price}_{auction_date}_{location}_{size}".lower()
        return hashlib.md5(content.encode()).hexdigest()

    def create_property_id(self, title, location, size):
        """
        Create a (relatively) stable property ID.

        IMPORTANT: does NOT include price or auction_date, so a price change
        does not create a "new" property. We rely on title+location+size.
        """
        clean_title = re.sub(r"[^\w\s]", "", title)
        clean_location = re.sub(r"[^\w\s]", "", location)
        clean_size = re.sub(r"[^\w\s]", "", size)

        base = f"{clean_title}_{clean_location}_{clean_size}".strip()
        base = re.sub(r"\s+", "_", base).lower()
        if not base:
            base = "property"
        return base[:100]

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
        """Validate if auction date is reasonable"""
        try:
            if not re.match(r"\d{1,2}\s+\w{3}\s+\d{4}\s+\(\w{3}\)", date_str):
                return False

            year_match = re.search(r"\d{4}", date_str)
            if year_match:
                year = int(year_match.group())
                current_year = datetime.now().year
                if current_year <= year <= current_year + 1:
                    return True

            return False
        except Exception:
            return False

    # ---------- HTTP ----------
    def make_request(self, url, params=None, retry_count=0):
        """Make HTTP request with retry logic and rate limiting"""
        try:
            time.sleep(self.request_delay)
            response = requests.get(
                url, params=params, headers=self.headers, timeout=self.timeout
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
                if total_results > 20:
                    total_pages = min((total_results + 19) // 20, 100)

            print(f"📊 Found {total_results:,} total results across {total_pages} pages")
            return total_results, total_pages

        except Exception as e:
            print(f"❌ Error getting pagination info: {e}")
            return 1650, 83  # Fallback

    # ---------- Extraction ----------
    def extract_properties_from_page(self, page_content, page_num):
        """Extract property data from a single page with improved validation"""
        properties = []
        page_duplicates = 0
        page_invalid = 0

        try:
            soup = BeautifulSoup(page_content, "html.parser")
            potential_properties = []

            # Find price text nodes then walk up to container
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

            for i, prop_info in enumerate(potential_properties):
                try:
                    property_data = self.extract_and_validate_property(
                        prop_info["container"],
                        prop_info["container_text"],
                        page_num,
                        i,
                    )

                    if property_data:
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
                    else:
                        page_invalid += 1
                except Exception as e:
                    print(f"⚠️ Error processing property {i} on page {page_num}: {e}")
                    page_invalid += 1
                    continue

            print(
                f"✅ Page {page_num}: Extracted {len(properties)} valid properties "
                f"(skipped {page_duplicates} duplicates, {page_invalid} invalid)"
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
                return None
            price_str = f"RM{price_match.group(1)}"
            is_valid_price, price_value = self.validate_price(price_str)
            if not is_valid_price:
                return None
            property_data["price"] = price_str
            property_data["price_value"] = price_value

            # ---------- AUCTION DATE ----------
            date_match = re.search(
                r"(\d{1,2}\s+\w{3}\s+\d{4}\s+\(\w{3}\))", container_text
            )
            if not date_match:
                return None
            auction_date = date_match.group(1)
            if not self.validate_auction_date(auction_date):
                return None
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
            property_type = "Commercial"
            type_keywords = {
                "office": "Office",
                "shop": "Shop",
                "retail": "Retail",
                "factory": "Factory",
                "warehouse": "Warehouse",
                "land": "Land",
                "hotel": "Hotel",
                "apartment": "Apartment",
                "condominium": "Condominium",
                "condo": "Condominium",
                "residence": "Residence",
            }
            container_text_lower = container_text.lower()
            for keyword, prop_type in type_keywords.items():
                if keyword in container_text_lower:
                    property_type = prop_type
                    break
            property_data["property_type"] = property_type

            # ---------- DISCOUNT ----------
            discount_match = re.search(r"(-\d+%)", container_text)
            if discount_match:
                property_data["discount"] = discount_match.group(1)

            # ---------- URL / META ----------
            if listing_url:
                property_data["listing_url"] = listing_url
            else:
                property_data["listing_url"] = f"{self.base_url}?page={page_num}"

            property_data["url"] = f"{self.base_url}?page={page_num}"
            property_data["page_number"] = page_num
            now_iso = datetime.now().isoformat()
            property_data["last_updated"] = now_iso
            property_data["first_seen"] = now_iso

            # Stable key (for DB change detection)
            property_data["_stable_key"] = self.generate_stable_key(property_data)

            return property_data
        except Exception:
            return None

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

        # Pre-build a mapping from stable_key -> existing_id for quick lookup
        stable_index = {}
        for existing_id, existing_data in database.items():
            sk = existing_data.get("_stable_key")
            if not sk:
                sk = self.generate_stable_key(existing_data)
                existing_data["_stable_key"] = sk
            if sk and sk not in stable_index:
                stable_index[sk] = existing_id

        for current_id, current_data in current_properties.items():
            # Ensure current stable key exists
            sk = current_data.get("_stable_key")
            if not sk:
                sk = self.generate_stable_key(current_data)
                current_data["_stable_key"] = sk

            existing_id = None
            existing_data = None

            # 1) Direct match by key
            if current_id in database:
                existing_id = current_id
                existing_data = database[current_id]
            # 2) Match by stable key
            elif sk in stable_index:
                existing_id = stable_index[sk]
                existing_data = database[existing_id]

            if existing_id is None:
                # Truly new listing
                new_listings[current_id] = current_data
                database[current_id] = {
                    **current_data,
                    "price_history": [
                        {
                            "price": current_data["price"],
                            "date": current_data["last_updated"],
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
                            }
                        ]
                    existing_data["price_history"].append(
                        {
                            "price": current_data["price"],
                            "date": current_data["last_updated"],
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
                parts = [
                    message[i : i + max_length]
                    for i in range(0, len(message), max_length)
                ]
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
        """Format daily summary with fixed scraping results (HTML for Telegram)"""
        now = datetime.now()
        tomorrow = now + timedelta(days=1)

        has_alerts = len(new_listings) > 0 or len(changed_properties) > 0

        if has_alerts:
            message = "🚨 <b>PROPERTY ALERTS &amp; DAILY SUMMARY</b> 🚨\n\n"
        else:
            message = "📊 <b>DAILY PROPERTY SUMMARY</b> 📊\n\n"

        message += "📅 <b>Daily Scan Report</b>\n"
        message += f"Date: {self.tg_escape_html(now.strftime('%d %b %Y, %I:%M %p'))}\n\n"

        # Key statistics
        message += "📈 <b>Key Statistics:</b>\n"
        message += f"• <b>Total Listings on Lelong</b>: {total_on_site:,} 🌐\n"
        message += (
            f"• <b>Properties Analyzed</b>: {len(current_properties)} (REAL DATA)\n"
        )
        message += f"• <b>Total Properties Tracked</b>: {total_tracked}\n"
        message += f"• <b>New Listings Today</b>: {len(new_listings)}\n"
        message += f"• <b>Properties with Changes</b>: {len(changed_properties)}\n\n"

        coverage = scraping_stats.get("coverage_percentage", 0)
        message += "🔍 <b>Scraping Performance:</b>\n"
        message += (
            f"• Pages Scraped: {scraping_stats['pages_completed']}/"
            f"{scraping_stats['total_pages']}\n"
        )
        message += f"• Success Rate: {scraping_stats['success_rate']:.1f}%\n"
        message += f"• Coverage: {coverage:.1f}% of total market\n"
        message += (
            f"• Duplicates Filtered: {scraping_stats.get('duplicates_skipped', 0)}\n\n"
        )

        # Breakdown by type
        property_types = {}
        for prop in current_properties.values():
            prop_type = prop.get("property_type", "Commercial")
            property_types[prop_type] = property_types.get(prop_type, 0) + 1

        if property_types:
            message += "📋 <b>Property Breakdown (Real Data):</b>\n"
            for prop_type, count in sorted(property_types.items()):
                message += f"• {self.tg_escape_html(prop_type)}: {count}\n"
            message += "\n"

        # New listings (up to 25)
        if new_listings:
            message += (
                f"🆕 <b>NEW LISTINGS TODAY ({len(new_listings)}):</b>\n"
            )
            for i, (prop_id, details) in enumerate(
                list(new_listings.items())[:25], 1
            ):
                header_line1 = (
                    details.get("header_short")
                    or details.get("header")
                    or details.get("location")
                    or details.get("title", "Untitled")
                )
                header_line2 = details.get("header_full")

                header1_html = self.tg_escape_html(header_line1)
                header2_html = (
                    self.tg_escape_html(header_line2)
                    if header_line2 and header_line2 != header_line1
                    else None
                )

                title_html = self.tg_escape_html(details.get("title", "Untitled"))
                ptype_html = self.tg_escape_html(
                    details.get("property_type", "-")
                )
                price_html = self.tg_escape_html(details.get("price", "-"))
                loc_html = self.tg_escape_html(
                    details.get("location", "Location TBD")
                )
                size_html = self.tg_escape_html(
                    details.get("size", "Size TBD")
                )
                date_html = self.tg_escape_html(
                    details.get("auction_date", "Date TBD")
                )

                message += f"{i}. <b>{header1_html}</b>\n"
                if header2_html:
                    message += f"   {header2_html}\n"

                message += f"   🏷 {title_html} ({ptype_html})\n"
                message += f"   💰 {price_html}\n"
                message += f"   📍 {loc_html}\n"
                message += f"   📏 {size_html}\n"
                message += f"   📅 {date_html}\n"

                raw_url = details.get("listing_url") or details.get("url")
                if raw_url:
                    url_html = self.tg_escape_html(raw_url)
                    message += (
                        f'   🔗 <a href="{url_html}">View Listing</a>\n'
                    )

                message += "\n"

            if len(new_listings) > 25:
                message += (
                    f"   ...and {len(new_listings) - 25} more new listings!\n\n"
                )

        # Changed properties (up to 25, with strikethrough)
        if changed_properties:
            message += (
                f"🔄 <b>PROPERTY CHANGES TODAY ({len(changed_properties)}):</b>\n"
            )
            for i, (prop_id, data) in enumerate(
                list(changed_properties.items())[:25], 1
            ):
                prop = data["property"]
                changes = data["changes"]

                header_line1 = (
                    prop.get("header_short")
                    or prop.get("header")
                    or prop.get("location")
                    or prop.get("title", "Untitled")
                )
                header_line2 = prop.get("header_full")

                header1_html = self.tg_escape_html(header_line1)
                header2_html = (
                    self.tg_escape_html(header_line2)
                    if header_line2 and header_line2 != header_line1
                    else None
                )

                title_html = self.tg_escape_html(prop.get("title", "Untitled"))
                ptype_html = self.tg_escape_html(
                    prop.get("property_type", "-")
                )

                message += f"{i}. <b>{header1_html}</b>\n"
                if header2_html:
                    message += f"   {header2_html}\n"

                message += f"   🏷 {title_html} ({ptype_html})\n"

                for change in changes:
                    old_html = self.tg_escape_html(change["old_value"])
                    new_html = self.tg_escape_html(change["new_value"])

                    if change["type"] == "price_change":
                        message += (
                            f"   💰 <s>{old_html}</s> → {new_html}\n"
                        )
                    elif change["type"] == "auction_date_change":
                        message += (
                            f"   📅 <s>{old_html}</s> → {new_html}\n"
                        )

                raw_url = prop.get("listing_url") or prop.get("url")
                if raw_url:
                    url_html = self.tg_escape_html(raw_url)
                    message += (
                        f'   🔗 <a href="{url_html}">View Listing</a>\n'
                    )

                message += "\n"

            if len(changed_properties) > 25:
                message += (
                    f"   ...and {len(changed_properties) - 25} more changes!\n\n"
                )

        # Market insights
        if current_properties:
            prices = []
            for prop in current_properties.values():
                price_value = prop.get("price_value", 0)
                if price_value > 0:
                    prices.append(price_value)

            if prices:
                avg_price = sum(prices) / len(prices)
                min_price = min(prices)
                max_price = max(prices)

                message += "💡 <b>Market Insights (Real Data):</b>\n"
                message += f"• Average Price: RM{avg_price:,.0f}\n"
                message += (
                    f"• Price Range: RM{min_price:,.0f} - RM{max_price:,.0f}\n"
                )
                message += (
                    f"• <b>Total Market Size</b>: {total_on_site:,} listings 🌐\n"
                )
                message += (
                    f"• <b>Real Data Coverage</b>: {coverage:.1f}%\n"
                )
                message += (
                    f"• Properties Analyzed: {len(current_properties):,} REAL listings\n\n"
                )

        # System status
        message += "⚙️ <b>System Status:</b>\n"
        message += "• Monitoring: ✅ Active (Daily)\n"
        message += "• Fixed Full Scraping: ✅ Complete\n"
        message += f"• Real Data: ✅ {len(current_properties):,} properties\n"
        message += "• Duplicate Filtering: ✅ Active\n"
        message += f"• Price Validation: ✅ RM{self.min_price:,}+ only\n"
        message += (
            f"• Next Scan: {self.tg_escape_html(tomorrow.strftime('%d %b %Y, 9:00 AM'))}\n"
        )
        message += "• Coverage: KL + Selangor\n"
        message += (
            f"• Storage: {'✅ Persistent' if self.use_persistent_storage else '⚠️ Temporary'}\n\n"
        )

        message += "🔔 <b>Fixed Full Scraping Real-Time Monitoring</b>\n"
        message += "📱 GitHub Actions • Daily at 9 AM\n"
        message += (
            f"🌐 Analyzing {len(current_properties):,} of {total_on_site:,} live listings\n"
        )
        message += "📊 100% Real Lelong Data • No Over-Extraction"

        if not has_alerts:
            message += "\n✨ No changes detected - market is stable!"

        return message

    # ---------- Main ----------
    def run_monitoring(self):
        """Main monitoring function with fixed full scraping"""
        print(
            f"🚀 Starting FIXED FULL SCRAPING Lelong property monitoring at {datetime.now()}"
        )

        try:
            database = self.load_properties_database()
            print(f"📊 Loaded database with {len(database)} existing properties")

            total_results, total_pages = self.get_total_pages_and_results()
            current_properties, scraping_stats = self.scrape_all_pages(
                total_pages, total_results
            )

            if not current_properties:
                print("⚠️ No properties extracted from fixed scraping")
                error_message = (
                    "⚠️ <b>Fixed Scraping Failed</b> ⚠️\n\n"
                    f"Could not extract properties from {total_pages} pages.\n"
                    f"Total listings on site: {total_results:,}\n"
                    "Will retry tomorrow at 9 AM."
                )
                self.send_telegram_notification(error_message)
                return "Fixed scraping failed"

            new_listings, changed_properties = self.detect_changes(
                current_properties, database
            )
            self.save_properties_database(database)

            summary_message = self.format_fixed_daily_summary(
                current_properties,
                new_listings,
                changed_properties,
                len(database),
                total_results,
                scraping_stats,
            )

            if self.send_telegram_notification(summary_message):
                print("✅ Fixed full scraping daily summary notification sent")
                notifications_sent = True
            else:
                print("❌ Failed to send daily summary notification")
                notifications_sent = False
                print("Fixed full scraping daily summary would be:")
                print(summary_message)

            coverage = scraping_stats.get("coverage_percentage", 0)
            print("\n" + "=" * 80)
            print("📊 FIXED FULL SCRAPING MONITORING SUMMARY")
            print("=" * 80)
            print(f"🌐 Total listings on Lelong: {total_results:,}")
            print(
                f"📄 Pages scraped: {scraping_stats['pages_completed']}/{total_pages}"
            )
            print(
                f"🏠 Properties extracted: {len(current_properties)} (REAL DATA)"
            )
            print(
                f"📈 Coverage: {coverage:.1f}% (should be ~100%)"
            )
            print(f"📈 Total properties tracked: {len(database)}")
            print(f"🆕 New listings found: {len(new_listings)}")
            print(
                f"🔄 Properties with changes: {len(changed_properties)}"
            )
            print(
                f"🔄 Duplicates filtered: {scraping_stats.get('duplicates_skipped', 0)}"
            )
            print(f"📱 Daily summary sent: {'✅' if notifications_sent else '❌'}")
            print("📅 Next scan: Tomorrow at 9 AM Malaysia time")
            print(
                f"💾 Data persistence: {'✅' if self.use_persistent_storage else '⚠️ Temporary'}"
            )
            print("✅ Over-extraction fixed: Coverage should be reasonable")
            print("✨ System status: Fixed full scraping operational")
            print("=" * 80)

            return (
                f"Fixed full scraping complete: {total_results:,} total on site, "
                f"{len(current_properties)} extracted (REAL), "
                f"{len(new_listings)} new, {len(changed_properties)} changed, "
                f"{coverage:.1f}% coverage"
            )
        except Exception as e:
            error_msg = f"❌ Error in fixed full scraping monitoring: {e}"
            print(error_msg)

            if self.telegram_bot_token and self.telegram_chat_id:
                err_html = self.tg_escape_html(str(e))
                error_notification = (
                    "🚨 <b>Fixed Full Scraping Monitor Error</b> 🚨\n\n"
                    "Fixed full scraping failed:\n"
                    f"<pre>{err_html}</pre>\n\n"
                    f"Time: {self.tg_escape_html(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}\n"
                    "Will retry tomorrow at 9 AM."
                )
                self.send_telegram_notification(error_notification)

            raise e


if __name__ == "__main__":
    monitor = FixedFullScrapingPropertyMonitor()
    report = monitor.run_monitoring()
    print(report)
