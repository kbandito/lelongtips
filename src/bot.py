#!/usr/bin/env python3
"""
Interactive Telegram Bot for Lelong Property Monitor
Responds to user commands with property search results and status updates.
Reads from the same data files used by the scraper.
"""

import json
import os
import re
import time
import html
import requests
from pathlib import Path
from datetime import datetime


class PropertyBot:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.api_url = f"https://api.telegram.org/bot{self.token}"

        # Data paths
        self.base_path = (
            Path(__file__).parent.parent
            if Path(__file__).parent.name == "src"
            else Path(__file__).parent
        )
        self.data_path = self.base_path / "data"
        self.properties_file = self.data_path / "properties.json"
        self.changes_file = self.data_path / "changes.json"
        self.stats_file = self.data_path / "daily_stats.json"
        self.progress_file = self.data_path / "scraping_progress.json"

        self.last_update_id = 0
        self.properties = {}
        self.load_data()

    def esc(self, text):
        """Escape text for Telegram HTML."""
        return html.escape(str(text), quote=True)

    def load_data(self):
        """Load all data files."""
        try:
            if self.properties_file.exists():
                with open(self.properties_file, "r", encoding="utf-8") as f:
                    self.properties = json.load(f)
            print(f"Loaded {len(self.properties)} properties")
        except Exception as e:
            print(f"Error loading properties: {e}")
            self.properties = {}

    def load_json(self, filepath):
        """Load a JSON file."""
        try:
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
        return None

    def send_message(self, chat_id, text):
        """Send a message, splitting if too long."""
        max_len = 4000
        parts = []
        while len(text) > max_len:
            split_at = text.rfind("\n", 0, max_len)
            if split_at == -1:
                split_at = max_len
            parts.append(text[:split_at])
            text = text[split_at:].lstrip("\n")
        parts.append(text)

        for part in parts:
            try:
                requests.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": part,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                    timeout=10,
                )
            except Exception as e:
                print(f"Error sending message: {e}")

    def parse_price(self, price_str):
        """Extract numeric price from string like 'RM 350,000'."""
        if not price_str:
            return 0
        nums = re.sub(r"[^\d.]", "", price_str)
        try:
            return float(nums)
        except ValueError:
            return 0

    def format_property(self, prop, idx=None):
        """Format a single property for display."""
        prefix = f"<b>{idx}.</b> " if idx else ""
        title = self.esc(prop.get("title", "Untitled"))
        price = self.esc(prop.get("price", "N/A"))
        location = self.esc(prop.get("location", "N/A"))
        size = self.esc(prop.get("size", "N/A"))
        ptype = self.esc(prop.get("property_type", "N/A"))
        auction = self.esc(prop.get("auction_date", "N/A"))
        url = prop.get("url") or prop.get("listing_url", "")

        msg = f"{prefix}<b>{title}</b>\n"
        msg += f"   Type: {ptype}\n"
        msg += f"   Price: {price}\n"
        msg += f"   Location: {location}\n"
        msg += f"   Size: {size}\n"
        msg += f"   Auction: {auction}\n"
        if url:
            msg += f'   <a href="{url}">View Listing</a>\n'
        return msg

    def cmd_help(self, chat_id):
        """Show available commands."""
        msg = "🤖 <b>Lelong Property Bot - Commands</b>\n\n"
        msg += "<b>Search:</b>\n"
        msg += "/search <i>keyword</i> - Search by keyword\n"
        msg += "/type <i>type</i> - Filter by type (factory, shop, land, hotel, office, warehouse, semid)\n"
        msg += "/under <i>price</i> - Properties under price (e.g. /under 500000)\n"
        msg += "/above <i>price</i> - Properties above price\n"
        msg += "/location <i>area</i> - Filter by location\n\n"
        msg += "<b>Status:</b>\n"
        msg += "/status - Latest scan statistics\n"
        msg += "/new - New listings from last scan\n"
        msg += "/changes - Recent property changes\n"
        msg += "/summary - Market summary by type\n"
        msg += "/reload - Reload data from files\n"
        self.send_message(chat_id, msg)

    def cmd_status(self, chat_id):
        """Show latest scan stats."""
        stats = self.load_json(self.stats_file)
        progress = self.load_json(self.progress_file)

        msg = "📊 <b>Latest Scan Status</b>\n\n"

        if stats:
            scan_date = stats.get("date", "Unknown")
            try:
                dt = datetime.fromisoformat(scan_date)
                scan_date = dt.strftime("%d %b %Y, %I:%M %p")
            except (ValueError, TypeError):
                pass
            msg += f"📅 Last Scan: {self.esc(scan_date)}\n"
            msg += f"📈 Total Listings: {stats.get('total_listings', 0):,}\n"
            msg += f"📁 Total Tracked: {stats.get('total_tracked', 0):,}\n"
            msg += f"🆕 New Listings: {stats.get('new_listings', 0)}\n"
            msg += f"🔄 Changes: {stats.get('changed_properties', 0)}\n\n"

        if progress:
            msg += "<b>Scraping Performance:</b>\n"
            msg += f"• Pages: {progress.get('pages_completed', 0)}/{progress.get('total_pages', 0)}\n"
            msg += f"• Properties: {progress.get('properties_extracted', 0):,}\n"
            msg += f"• Success: {progress.get('success_rate', 0):.1f}%\n"
            msg += f"• Coverage: {progress.get('coverage_percentage', 0):.1f}%\n"
            msg += f"• Duplicates Filtered: {progress.get('duplicates_skipped', 0):,}\n"

        if not stats and not progress:
            msg += "No scan data available yet."

        msg += f"\n\n💾 Database: {len(self.properties):,} properties"
        self.send_message(chat_id, msg)

    def cmd_new(self, chat_id):
        """Show new listings from last scan."""
        changes = self.load_json(self.changes_file)
        if not changes or not isinstance(changes, list) or len(changes) == 0:
            self.send_message(chat_id, "📭 No scan history available yet. Run the scraper first.")
            return

        last_scan = changes[-1]
        new_ids = last_scan.get("new_listing_ids", [])
        scan_date = last_scan.get("scan_date", "Unknown")
        try:
            dt = datetime.fromisoformat(scan_date)
            scan_date = dt.strftime("%d %b %Y, %I:%M %p")
        except (ValueError, TypeError):
            pass

        if not new_ids:
            self.send_message(chat_id, f"📭 No new listings found in last scan ({self.esc(scan_date)}).")
            return

        msg = f"🆕 <b>New Listings from {self.esc(scan_date)}</b>\n"
        msg += f"Found {len(new_ids)} new listing(s)\n\n"

        count = 0
        for pid in new_ids[:20]:
            prop = self.properties.get(pid)
            if prop:
                count += 1
                msg += self.format_property(prop, count) + "\n"

        if len(new_ids) > 20:
            msg += f"\n... and {len(new_ids) - 20} more"

        self.send_message(chat_id, msg)

    def cmd_changes(self, chat_id):
        """Show recent property changes."""
        changes = self.load_json(self.changes_file)
        if not changes or not isinstance(changes, list) or len(changes) == 0:
            self.send_message(chat_id, "📭 No change history available yet.")
            return

        last_scan = changes[-1]
        scan_date = last_scan.get("scan_date", "Unknown")
        try:
            dt = datetime.fromisoformat(scan_date)
            scan_date = dt.strftime("%d %b %Y, %I:%M %p")
        except (ValueError, TypeError):
            pass

        change_list = last_scan.get("changes", [])
        if not change_list:
            self.send_message(chat_id, f"✨ No property changes detected in last scan ({self.esc(scan_date)}).")
            return

        msg = f"🔄 <b>Property Changes from {self.esc(scan_date)}</b>\n"
        msg += f"Found {len(change_list)} change(s)\n\n"

        for i, change in enumerate(change_list[:20], 1):
            title = self.esc(change.get("title", "Unknown"))
            field = self.esc(change.get("field", ""))
            old_val = self.esc(change.get("old_value", ""))
            new_val = self.esc(change.get("new_value", ""))
            msg += f"<b>{i}. {title}</b>\n"
            msg += f"   {field}: <s>{old_val}</s> → <b>{new_val}</b>\n\n"

        if len(change_list) > 20:
            msg += f"... and {len(change_list) - 20} more"

        self.send_message(chat_id, msg)

    def cmd_search(self, chat_id, query):
        """Search properties by keyword."""
        if not query:
            self.send_message(chat_id, "Usage: /search <i>keyword</i>\nExample: /search shah alam factory")
            return

        query_lower = query.lower()
        terms = query_lower.split()
        results = []

        for pid, prop in self.properties.items():
            searchable = " ".join([
                prop.get("title", ""),
                prop.get("location", ""),
                prop.get("property_type", ""),
                prop.get("size", ""),
            ]).lower()
            if all(term in searchable for term in terms):
                results.append(prop)

        if not results:
            self.send_message(chat_id, f"🔍 No results for '<b>{self.esc(query)}</b>'")
            return

        # Sort by price
        results.sort(key=lambda p: self.parse_price(p.get("price", "")))

        msg = f"🔍 <b>Search: '{self.esc(query)}'</b>\n"
        msg += f"Found {len(results)} result(s)\n\n"

        for i, prop in enumerate(results[:15], 1):
            msg += self.format_property(prop, i) + "\n"

        if len(results) > 15:
            msg += f"\n... and {len(results) - 15} more. Refine your search."

        self.send_message(chat_id, msg)

    def cmd_type(self, chat_id, ptype):
        """Filter properties by type."""
        if not ptype:
            self.send_message(chat_id, "Usage: /type <i>type</i>\nTypes: factory, shop, land, hotel, office, warehouse, semid, bungalow, villa")
            return

        type_map = {
            "factory": "Factory",
            "warehouse": "Warehouse",
            "shop": "Shop",
            "office": "Office",
            "retail": "Retail",
            "land": "Land",
            "hotel": "Hotel",
            "resort": "Resort",
            "semid": "Semi-D",
            "semi-d": "Semi-D",
            "bungalow": "Bungalow",
            "villa": "Villa",
        }

        search_type = type_map.get(ptype.lower(), ptype)
        results = [
            prop for prop in self.properties.values()
            if search_type.lower() in prop.get("property_type", "").lower()
        ]

        if not results:
            self.send_message(chat_id, f"🔍 No '{self.esc(search_type)}' properties found.")
            return

        results.sort(key=lambda p: self.parse_price(p.get("price", "")))

        msg = f"🏢 <b>{self.esc(search_type)} Properties</b>\n"
        msg += f"Found {len(results)} result(s)\n\n"

        for i, prop in enumerate(results[:15], 1):
            msg += self.format_property(prop, i) + "\n"

        if len(results) > 15:
            msg += f"\n... and {len(results) - 15} more. Use /under or /location to narrow down."

        self.send_message(chat_id, msg)

    def cmd_under(self, chat_id, amount_str):
        """Properties under a certain price."""
        if not amount_str:
            self.send_message(chat_id, "Usage: /under <i>price</i>\nExample: /under 500000")
            return

        amount_str = amount_str.replace(",", "").replace("k", "000").replace("m", "000000")
        try:
            max_price = float(amount_str)
        except ValueError:
            self.send_message(chat_id, "Invalid price. Use numbers like: /under 500000 or /under 500k")
            return

        results = [
            prop for prop in self.properties.values()
            if 0 < self.parse_price(prop.get("price", "")) <= max_price
        ]

        results.sort(key=lambda p: self.parse_price(p.get("price", "")))

        if not results:
            self.send_message(chat_id, f"🔍 No properties under RM{max_price:,.0f}")
            return

        msg = f"💰 <b>Properties Under RM{max_price:,.0f}</b>\n"
        msg += f"Found {len(results)} result(s)\n\n"

        for i, prop in enumerate(results[:15], 1):
            msg += self.format_property(prop, i) + "\n"

        if len(results) > 15:
            msg += f"\n... and {len(results) - 15} more. Use /search or /type to narrow down."

        self.send_message(chat_id, msg)

    def cmd_above(self, chat_id, amount_str):
        """Properties above a certain price."""
        if not amount_str:
            self.send_message(chat_id, "Usage: /above <i>price</i>\nExample: /above 1000000")
            return

        amount_str = amount_str.replace(",", "").replace("k", "000").replace("m", "000000")
        try:
            min_price = float(amount_str)
        except ValueError:
            self.send_message(chat_id, "Invalid price. Use numbers like: /above 1000000 or /above 1m")
            return

        results = [
            prop for prop in self.properties.values()
            if self.parse_price(prop.get("price", "")) >= min_price
        ]

        results.sort(key=lambda p: self.parse_price(p.get("price", "")))

        if not results:
            self.send_message(chat_id, f"🔍 No properties above RM{min_price:,.0f}")
            return

        msg = f"💰 <b>Properties Above RM{min_price:,.0f}</b>\n"
        msg += f"Found {len(results)} result(s)\n\n"

        for i, prop in enumerate(results[:15], 1):
            msg += self.format_property(prop, i) + "\n"

        if len(results) > 15:
            msg += f"\n... and {len(results) - 15} more. Use /search or /type to narrow down."

        self.send_message(chat_id, msg)

    def cmd_location(self, chat_id, area):
        """Filter properties by location."""
        if not area:
            self.send_message(chat_id, "Usage: /location <i>area</i>\nExample: /location shah alam")
            return

        area_lower = area.lower()
        results = [
            prop for prop in self.properties.values()
            if area_lower in prop.get("location", "").lower()
        ]

        results.sort(key=lambda p: self.parse_price(p.get("price", "")))

        if not results:
            self.send_message(chat_id, f"🔍 No properties found in '{self.esc(area)}'")
            return

        msg = f"📍 <b>Properties in '{self.esc(area)}'</b>\n"
        msg += f"Found {len(results)} result(s)\n\n"

        for i, prop in enumerate(results[:15], 1):
            msg += self.format_property(prop, i) + "\n"

        if len(results) > 15:
            msg += f"\n... and {len(results) - 15} more. Use /under or /type to narrow down."

        self.send_message(chat_id, msg)

    def cmd_summary(self, chat_id):
        """Show market summary by property type."""
        type_stats = {}
        for prop in self.properties.values():
            ptype = prop.get("property_type", "Other")
            price = self.parse_price(prop.get("price", ""))
            if ptype not in type_stats:
                type_stats[ptype] = {"count": 0, "total_price": 0, "min": float("inf"), "max": 0}
            type_stats[ptype]["count"] += 1
            if price > 0:
                type_stats[ptype]["total_price"] += price
                type_stats[ptype]["min"] = min(type_stats[ptype]["min"], price)
                type_stats[ptype]["max"] = max(type_stats[ptype]["max"], price)

        msg = "📊 <b>Market Summary</b>\n"
        msg += f"Total: {len(self.properties):,} properties\n\n"

        for ptype, stats in sorted(type_stats.items(), key=lambda x: -x[1]["count"]):
            count = stats["count"]
            avg = stats["total_price"] / count if count > 0 and stats["total_price"] > 0 else 0
            min_p = stats["min"] if stats["min"] != float("inf") else 0
            max_p = stats["max"]

            msg += f"<b>{self.esc(ptype)}</b> ({count})\n"
            if avg > 0:
                msg += f"   Avg: RM{avg:,.0f} | Range: RM{min_p:,.0f} - RM{max_p:,.0f}\n"
            msg += "\n"

        self.send_message(chat_id, msg)

    def handle_message(self, message):
        """Process an incoming message."""
        chat_id = message["chat"]["id"]
        text = message.get("text", "").strip()

        if not text.startswith("/"):
            self.send_message(chat_id, "Send /help to see available commands.")
            return

        parts = text.split(maxsplit=1)
        command = parts[0].lower().split("@")[0]  # handle @botname suffix
        args = parts[1] if len(parts) > 1 else ""

        if command in ("/start", "/help"):
            self.cmd_help(chat_id)
        elif command == "/status":
            self.cmd_status(chat_id)
        elif command == "/new":
            self.cmd_new(chat_id)
        elif command == "/changes":
            self.cmd_changes(chat_id)
        elif command == "/search":
            self.cmd_search(chat_id, args)
        elif command == "/type":
            self.cmd_type(chat_id, args)
        elif command == "/under":
            self.cmd_under(chat_id, args)
        elif command == "/above":
            self.cmd_above(chat_id, args)
        elif command == "/location":
            self.cmd_location(chat_id, args)
        elif command == "/summary":
            self.cmd_summary(chat_id)
        elif command == "/reload":
            self.load_data()
            self.send_message(chat_id, f"🔄 Data reloaded: {len(self.properties):,} properties")
        else:
            self.send_message(chat_id, f"Unknown command. Send /help to see available commands.")

    def poll(self):
        """Long-poll for Telegram updates."""
        print(f"🤖 Bot started. Listening for commands...")
        print(f"💾 Database: {len(self.properties):,} properties")

        while True:
            try:
                resp = requests.get(
                    f"{self.api_url}/getUpdates",
                    params={"offset": self.last_update_id + 1, "timeout": 30},
                    timeout=35,
                )
                if resp.status_code != 200:
                    print(f"API error: {resp.status_code}")
                    time.sleep(5)
                    continue

                data = resp.json()
                for update in data.get("result", []):
                    self.last_update_id = update["update_id"]
                    if "message" in update:
                        self.handle_message(update["message"])

            except requests.exceptions.Timeout:
                continue
            except requests.exceptions.ConnectionError:
                print("Connection error, retrying in 5s...")
                time.sleep(5)
            except KeyboardInterrupt:
                print("\nBot stopped.")
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(5)


if __name__ == "__main__":
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        print("Set TELEGRAM_BOT_TOKEN environment variable")
        exit(1)
    bot = PropertyBot()
    bot.poll()
