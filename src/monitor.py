#!/usr/bin/env python3
"""
Real Property Monitoring Script with Actual Lelong Scraping
Scrapes real data from Lelong website showing actual 1,600+ listings
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

class RealPropertyMonitor:
    def __init__(self):
        # Try to use repository data directory, fall back to temp if no write permissions
        self.base_path = Path(__file__).parent.parent if Path(__file__).parent.name == 'src' else Path(__file__).parent
        self.data_path = self.base_path / "data"
        
        # Create data directory if possible, otherwise use temp
        try:
            self.data_path.mkdir(exist_ok=True)
            self.use_persistent_storage = True
            print(f"📁 Using persistent storage: {self.data_path}")
        except:
            self.data_path = Path(tempfile.mkdtemp())
            self.use_persistent_storage = False
            print(f"📁 Using temporary storage: {self.data_path}")
        
        # File paths
        self.properties_database = self.data_path / "properties.json"
        self.changes_history = self.data_path / "changes.json"
        self.daily_stats = self.data_path / "daily_stats.json"
        
        # Search URL
        self.lelong_url = "https://www.lelongtips.com.my/search?keyword=&property_type%5B%5D=7&property_type%5B%5D=6&property_type%5B%5D=8&property_type%5B%5D=4&property_type%5B%5D=5&state=kl_sel&bank=&listing_status=&input-date=&auction-date=&case=&listing_type=&min_price=&max_price=&min_size=&max_size="
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # Notification settings
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        
        print(f"🚀 Real Property Monitor with Actual Lelong Scraping")
        print(f"🤖 Telegram configured: {'✅' if self.telegram_bot_token and self.telegram_chat_id else '❌'}")
        print(f"💾 Persistent storage: {'✅' if self.use_persistent_storage else '❌'}")
    
    def load_properties_database(self):
        """Load the properties database"""
        if self.properties_database.exists():
            try:
                with open(self.properties_database, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Error loading properties database: {e}")
        return {}
    
    def save_properties_database(self, database):
        """Save the properties database"""
        try:
            with open(self.properties_database, 'w', encoding='utf-8') as f:
                json.dump(database, f, indent=2, ensure_ascii=False)
            print(f"💾 Properties database saved: {len(database)} properties")
            return True
        except Exception as e:
            print(f"⚠️ Could not save properties database: {e}")
            return False
    
    def create_property_id(self, title, location, size, auction_date):
        """Create a unique property ID"""
        clean_title = re.sub(r'[^\w\s]', '', title)
        clean_location = re.sub(r'[^\w\s]', '', location)
        clean_size = re.sub(r'[^\w\s]', '', size)
        clean_date = re.sub(r'[^\w\s]', '', auction_date)
        
        return f"{clean_title}_{clean_location}_{clean_size}_{clean_date}".replace(' ', '_').lower()[:100]
    
    def extract_property_data(self, property_element):
        """Extract property data from a single property element"""
        try:
            property_data = {}
            
            # Extract auction price
            price_element = property_element.find('h4', string=lambda text: text and 'Auction Price' in text)
            if price_element:
                price_text = price_element.get_text(strip=True)
                price_match = re.search(r'RM[\d,]+', price_text)
                if price_match:
                    property_data['price'] = price_match.group()
            
            # Extract auction date
            date_element = property_element.find('h4', string=lambda text: text and 'Auction Date' in text)
            if date_element:
                # Look for the next element that contains the date
                next_element = date_element.find_next()
                if next_element:
                    date_text = next_element.get_text(strip=True)
                    # Match pattern like "10 Sep 2025 (Wed)"
                    date_match = re.search(r'\d{1,2}\s+\w{3}\s+\d{4}\s+\(\w{3}\)', date_text)
                    if date_match:
                        property_data['auction_date'] = date_match.group()
            
            # Extract property title and location
            title_elements = property_element.find_all(['h3', 'h4', 'h5', 'strong'])
            for element in title_elements:
                text = element.get_text(strip=True)
                if text and not any(keyword in text.lower() for keyword in ['auction price', 'auction date', 'rm', 'sq.ft']):
                    if 'title' not in property_data:
                        property_data['title'] = text
                    elif 'location' not in property_data and len(text) > 20:
                        property_data['location'] = text
                        break
            
            # Extract size
            size_elements = property_element.find_all(string=re.compile(r'\d+[\s,]*sq\.ft'))
            for size_text in size_elements:
                size_match = re.search(r'[\d,]+\s*sq\.ft', size_text)
                if size_match:
                    property_data['size'] = size_match.group()
                    break
            
            # Extract discount percentage
            discount_elements = property_data.find_all(string=re.compile(r'-\d+%'))
            for discount_text in discount_elements:
                discount_match = re.search(r'-\d+%', discount_text)
                if discount_match:
                    property_data['discount'] = discount_match.group()
                    break
            
            # Extract property type from context
            property_type_keywords = {
                'office': 'Office',
                'shop': 'Shop',
                'retail': 'Retail',
                'factory': 'Factory',
                'warehouse': 'Warehouse',
                'land': 'Land',
                'hotel': 'Hotel',
                'resort': 'Resort'
            }
            
            full_text = property_element.get_text().lower()
            for keyword, prop_type in property_type_keywords.items():
                if keyword in full_text:
                    property_data['property_type'] = prop_type
                    break
            
            # Set defaults for missing data
            if 'title' not in property_data:
                property_data['title'] = 'Property Listing'
            if 'location' not in property_data:
                property_data['location'] = 'KL/Selangor'
            if 'size' not in property_data:
                property_data['size'] = 'Size not specified'
            if 'property_type' not in property_data:
                property_data['property_type'] = 'Commercial'
            
            return property_data
            
        except Exception as e:
            print(f"⚠️ Error extracting property data: {e}")
            return None
    
    def scrape_lelong_properties(self):
        """Scrape real Lelong auction properties"""
        print(f"🔍 Scraping properties from: {self.lelong_url}")
        
        try:
            # Make request to Lelong
            response = requests.get(self.lelong_url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            print(f"✅ Successfully fetched page (Status: {response.status_code})")
            
            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract total results count
            result_text = soup.find(string=re.compile(r'Result\(s\):\s*[\d,]+'))
            total_results = 0
            if result_text:
                result_match = re.search(r'Result\(s\):\s*([\d,]+)', result_text)
                if result_match:
                    total_results = int(result_match.group(1).replace(',', ''))
                    print(f"📊 Total results found: {total_results:,}")
            
            # Find property containers - look for elements containing auction prices
            property_containers = []
            
            # Method 1: Look for elements containing "Auction Price"
            auction_price_elements = soup.find_all(string=re.compile(r'Auction Price'))
            for element in auction_price_elements:
                # Find the parent container
                container = element.find_parent()
                while container and container.name not in ['div', 'article', 'section']:
                    container = container.find_parent()
                if container and container not in property_containers:
                    property_containers.append(container)
            
            # Method 2: Look for price patterns directly
            price_elements = soup.find_all(string=re.compile(r'RM[\d,]+'))
            for element in price_elements:
                container = element.find_parent()
                while container and container.name not in ['div', 'article', 'section']:
                    container = container.find_parent()
                if container and container not in property_containers:
                    # Check if this container also has auction date
                    if container.find(string=re.compile(r'\d{1,2}\s+\w{3}\s+\d{4}')):
                        property_containers.append(container)
            
            print(f"🏠 Found {len(property_containers)} property containers")
            
            # Extract property data
            properties = {}
            extracted_count = 0
            
            for container in property_containers[:50]:  # Limit to first 50 for testing
                property_data = self.extract_property_data(container)
                
                if property_data and 'price' in property_data and 'auction_date' in property_data:
                    property_id = self.create_property_id(
                        property_data.get('title', ''),
                        property_data.get('location', ''),
                        property_data.get('size', ''),
                        property_data.get('auction_date', '')
                    )
                    
                    properties[property_id] = {
                        **property_data,
                        'url': self.lelong_url,
                        'last_updated': datetime.now().isoformat(),
                        'first_seen': datetime.now().isoformat(),
                        'total_results_on_site': total_results
                    }
                    extracted_count += 1
            
            print(f"✅ Successfully extracted {extracted_count} properties from {total_results:,} total listings")
            return properties, total_results
            
        except Exception as e:
            print(f"❌ Error scraping Lelong: {e}")
            return {}, 0
    
    def detect_changes(self, current_properties, database):
        """Detect new listings and changes in existing properties"""
        new_listings = {}
        changed_properties = {}
        
        print(f"🔍 Analyzing {len(current_properties)} current vs {len(database)} stored properties")
        
        for prop_id, current_data in current_properties.items():
            if prop_id not in database:
                # New property
                new_listings[prop_id] = current_data
                database[prop_id] = {
                    **current_data,
                    'price_history': [{'price': current_data['price'], 'date': current_data['last_updated']}],
                    'auction_date_history': [{'auction_date': current_data['auction_date'], 'date': current_data['last_updated']}]
                }
                print(f"🆕 New property: {current_data['title']}")
            else:
                # Existing property - check for changes
                existing_data = database[prop_id]
                changes = []
                
                # Check price change
                if current_data['price'] != existing_data['price']:
                    changes.append({
                        'type': 'price_change',
                        'field': 'Auction Price',
                        'old_value': existing_data['price'],
                        'new_value': current_data['price'],
                        'change_date': current_data['last_updated']
                    })
                    
                    if 'price_history' not in existing_data:
                        existing_data['price_history'] = [{'price': existing_data['price'], 'date': existing_data.get('first_seen', current_data['last_updated'])}]
                    existing_data['price_history'].append({'price': current_data['price'], 'date': current_data['last_updated']})
                    
                    print(f"💰 Price change: {current_data['title']} - {existing_data['price']} → {current_data['price']}")
                
                # Check auction date change
                if current_data['auction_date'] != existing_data['auction_date']:
                    changes.append({
                        'type': 'auction_date_change',
                        'field': 'Auction Date',
                        'old_value': existing_data['auction_date'],
                        'new_value': current_data['auction_date'],
                        'change_date': current_data['last_updated']
                    })
                    
                    if 'auction_date_history' not in existing_data:
                        existing_data['auction_date_history'] = [{'auction_date': existing_data['auction_date'], 'date': existing_data.get('first_seen', current_data['last_updated'])}]
                    existing_data['auction_date_history'].append({'auction_date': current_data['auction_date'], 'date': current_data['last_updated']})
                    
                    print(f"📅 Date change: {current_data['title']} - {existing_data['auction_date']} → {current_data['auction_date']}")
                
                if changes:
                    changed_properties[prop_id] = {
                        'property': current_data,
                        'changes': changes,
                        'history': {
                            'price_history': existing_data.get('price_history', []),
                            'auction_date_history': existing_data.get('auction_date_history', [])
                        }
                    }
                
                # Update database with current data
                database[prop_id].update(current_data)
                database[prop_id]['first_seen'] = existing_data.get('first_seen', current_data['last_updated'])
        
        print(f"📊 Analysis complete: {len(new_listings)} new, {len(changed_properties)} changed")
        return new_listings, changed_properties
    
    def send_telegram_notification(self, message):
        """Send notification via Telegram"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            print("⚠️ Telegram credentials not configured")
            return False
            
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            
            # Split long messages if needed
            max_length = 4000
            if len(message) > max_length:
                parts = [message[i:i+max_length] for i in range(0, len(message), max_length)]
                for i, part in enumerate(parts):
                    data = {
                        'chat_id': self.telegram_chat_id,
                        'text': f"Part {i+1}/{len(parts)}:\n\n{part}",
                        'parse_mode': 'Markdown'
                    }
                    response = requests.post(url, data=data, timeout=10)
                    if response.status_code != 200:
                        print(f"❌ Telegram error for part {i+1}: {response.status_code}")
                        return False
                    time.sleep(1)
                return True
            else:
                data = {
                    'chat_id': self.telegram_chat_id,
                    'text': message,
                    'parse_mode': 'Markdown'
                }
                response = requests.post(url, data=data, timeout=10)
                return response.status_code == 200
                
        except Exception as e:
            print(f"❌ Error sending Telegram notification: {e}")
            return False
    
    def format_real_daily_summary(self, current_properties, new_listings, changed_properties, total_tracked, total_on_site):
        """Format daily summary with real Lelong data"""
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        
        # Determine if there are alerts
        has_alerts = len(new_listings) > 0 or len(changed_properties) > 0
        
        if has_alerts:
            message = f"🚨 *PROPERTY ALERTS & DAILY SUMMARY* 🚨\n\n"
        else:
            message = f"📊 *DAILY PROPERTY SUMMARY* 📊\n\n"
        
        message += f"📅 *Daily Scan Report*\n"
        message += f"Date: {now.strftime('%d %b %Y, %I:%M %p')}\n\n"
        
        # KEY STATISTICS (What the user requested)
        message += f"📈 *Key Statistics:*\n"
        message += f"• **Total Listings on Lelong**: *{total_on_site:,}*\n"
        message += f"• **Properties Analyzed**: *{len(current_properties)}*\n"
        message += f"• **Total Properties Tracked**: *{total_tracked}*\n"
        message += f"• **New Listings Today**: *{len(new_listings)}*\n"
        message += f"• **Properties with Changes**: *{len(changed_properties)}*\n\n"
        
        # Property breakdown by type
        property_types = {}
        for prop in current_properties.values():
            prop_type = prop.get('property_type', 'Commercial')
            if prop_type not in property_types:
                property_types[prop_type] = 0
            property_types[prop_type] += 1
        
        if property_types:
            message += f"📋 *Property Breakdown (Analyzed):*\n"
            for prop_type, count in sorted(property_types.items()):
                message += f"• {prop_type}: {count}\n"
            message += "\n"
        
        # Show new listings if any
        if new_listings:
            message += f"🆕 *NEW LISTINGS TODAY ({len(new_listings)}):*\n"
            for i, (prop_id, details) in enumerate(list(new_listings.items())[:3], 1):
                message += f"{i}. *{details['title'][:50]}...*\n" if len(details['title']) > 50 else f"{i}. *{details['title']}*\n"
                message += f"   💰 {details['price']} | 📅 {details['auction_date']}\n"
                message += f"   📍 {details.get('location', 'Location TBD')[:40]}...\n" if len(details.get('location', '')) > 40 else f"   📍 {details.get('location', 'Location TBD')}\n"
                message += f"   📏 {details.get('size', 'Size TBD')}\n\n"
            
            if len(new_listings) > 3:
                message += f"   ...and {len(new_listings) - 3} more new listings!\n\n"
        
        # Show changed properties if any
        if changed_properties:
            message += f"🔄 *PROPERTY CHANGES TODAY ({len(changed_properties)}):*\n"
            for i, (prop_id, data) in enumerate(list(changed_properties.items())[:2], 1):
                prop = data['property']
                changes = data['changes']
                
                title = prop['title'][:40] + "..." if len(prop['title']) > 40 else prop['title']
                message += f"{i}. *{title}*\n"
                
                for change in changes:
                    if change['type'] == 'price_change':
                        message += f"   💰 Price: {change['old_value']} → {change['new_value']}\n"
                    elif change['type'] == 'auction_date_change':
                        message += f"   📅 Date: {change['old_value']} → {change['new_value']}\n"
                
                message += "\n"
            
            if len(changed_properties) > 2:
                message += f"   ...and {len(changed_properties) - 2} more changes!\n\n"
        
        # Market insights
        if current_properties:
            prices = []
            for prop in current_properties.values():
                try:
                    price_str = prop['price'].replace('RM', '').replace(',', '')
                    price = float(re.findall(r'[\d.]+', price_str)[0])
                    if price < 1000:
                        price *= 1000
                    prices.append(price)
                except:
                    continue
            
            if prices:
                avg_price = sum(prices) / len(prices)
                min_price = min(prices)
                max_price = max(prices)
                
                message += f"💡 *Market Insights (Analyzed Sample):*\n"
                message += f"• Average Price: RM{avg_price:,.0f}\n"
                message += f"• Price Range: RM{min_price:,.0f} - RM{max_price:,.0f}\n"
                message += f"• Total Market Size: {total_on_site:,} listings\n"
                message += f"• Analysis Coverage: {(len(current_properties)/total_on_site)*100:.1f}%\n\n"
        
        # System status
        message += f"⚙️ *System Status:*\n"
        message += f"• Monitoring: ✅ Active (Daily)\n"
        message += f"• Next Scan: {tomorrow.strftime('%d %b %Y, 9:00 AM')}\n"
        message += f"• Coverage: KL + Selangor\n"
        message += f"• Data Source: Real Lelong Scraping\n"
        message += f"• Storage: {'✅ Persistent' if self.use_persistent_storage else '⚠️ Temporary'}\n\n"
        
        # Footer
        message += f"🔔 *Real-Time Lelong Monitoring*\n"
        message += f"📱 GitHub Actions • Daily at 9 AM\n"
        message += f"🌐 Tracking {total_on_site:,} live auction listings"
        
        if not has_alerts:
            message += f"\n✨ No changes detected - market is stable!"
        
        return message
    
    def run_monitoring(self):
        """Main monitoring function with real Lelong scraping"""
        print(f"🚀 Starting real Lelong property monitoring at {datetime.now()}")
        
        try:
            # Load existing database
            database = self.load_properties_database()
            print(f"📊 Loaded database with {len(database)} existing properties")
            
            # Scrape current listings from real Lelong
            current_properties, total_on_site = self.scrape_lelong_properties()
            
            if not current_properties:
                print("⚠️ No properties extracted from scraping")
                # Send notification about scraping issue
                error_message = f"⚠️ *Daily Property Scan* ⚠️\n\n"
                error_message += f"Could not extract property data from Lelong.\n"
                error_message += f"Total listings on site: {total_on_site:,}\n"
                error_message += f"Extracted: 0\n\n"
                error_message += f"This might indicate:\n"
                error_message += f"• Website structure changes\n"
                error_message += f"• Anti-scraping measures\n"
                error_message += f"• Network issues\n\n"
                error_message += f"Will retry tomorrow at 9 AM."
                
                self.send_telegram_notification(error_message)
                return "No properties extracted"
            
            # Detect new listings and changes
            new_listings, changed_properties = self.detect_changes(current_properties, database)
            
            # Save updated database (if possible)
            self.save_properties_database(database)
            
            # Always send real daily summary
            summary_message = self.format_real_daily_summary(
                current_properties, new_listings, changed_properties, len(database), total_on_site
            )
            
            if self.send_telegram_notification(summary_message):
                print("✅ Real daily summary notification sent")
                notifications_sent = True
            else:
                print("❌ Failed to send daily summary notification")
                notifications_sent = False
                # Print the message for debugging
                print("Real daily summary would be:")
                print(summary_message.replace('*', '').replace('_', ''))
            
            # Summary
            print(f"\n{'='*80}")
            print(f"📊 REAL LELONG MONITORING SUMMARY")
            print(f"{'='*80}")
            print(f"🌐 Total listings on Lelong: {total_on_site:,}")
            print(f"📊 Properties analyzed: {len(current_properties)}")
            print(f"📈 Total properties tracked: {len(database)}")
            print(f"🆕 New listings found: {len(new_listings)}")
            print(f"🔄 Properties with changes: {len(changed_properties)}")
            print(f"📱 Daily summary sent: {'✅' if notifications_sent else '❌'}")
            print(f"📅 Next scan: Tomorrow at 9 AM Malaysia time")
            print(f"💾 Data persistence: {'✅' if self.use_persistent_storage else '⚠️ Temporary'}")
            print(f"🎯 Analysis coverage: {(len(current_properties)/total_on_site)*100:.1f}% of total listings")
            print(f"{'='*80}")
            
            return f"Real monitoring complete: {total_on_site:,} total on site, {len(current_properties)} analyzed, {len(new_listings)} new, {len(changed_properties)} changed"
            
        except Exception as e:
            error_msg = f"❌ Error in real monitoring: {e}"
            print(error_msg)
            
            # Send error notification
            if self.telegram_bot_token and self.telegram_chat_id:
                error_notification = f"🚨 *Real Property Monitor Error* 🚨\n\n"
                error_notification += f"Real Lelong scraping failed:\n"
                error_notification += f"```\n{str(e)}\n```\n\n"
                error_notification += f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                error_notification += f"Will retry tomorrow at 9 AM."
                
                self.send_telegram_notification(error_notification)
            
            raise e

if __name__ == "__main__":
    monitor = RealPropertyMonitor()
    report = monitor.run_monitoring()
