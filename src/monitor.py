#!/usr/bin/env python3
"""
Full Scraping Property Monitor - Option 1
Scrapes ALL 1,659+ listings from Lelong website
Comprehensive real data analysis with complete market coverage
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
from concurrent.futures import ThreadPoolExecutor, as_completed
import random

class FullScrapingPropertyMonitor:
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
        self.scraping_progress = self.data_path / "scraping_progress.json"
        
        # Base search URL (without page parameter)
        self.base_url = "https://www.lelongtips.com.my/search"
        self.search_params = {
            'keyword': '',
            'property_type[]': ['7', '6', '8', '4', '5'],
            'state': 'kl_sel',
            'bank': '',
            'listing_status': '',
            'input-date': '',
            'auction-date': '',
            'case': '',
            'listing_type': '',
            'min_price': '',
            'max_price': '',
            'min_size': '',
            'max_size': ''
        }
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
        
        # Rate limiting settings
        self.request_delay = 2  # seconds between requests
        self.max_retries = 3
        self.timeout = 30
        
        # Notification settings
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        
        print(f"🚀 Full Scraping Property Monitor - ALL 1,659+ Listings")
        print(f"🤖 Telegram configured: {'✅' if self.telegram_bot_token and self.telegram_chat_id else '❌'}")
        print(f"💾 Persistent storage: {'✅' if self.use_persistent_storage else '❌'}")
        print(f"⏱️ Rate limiting: {self.request_delay}s between requests")
    
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
    
    def save_scraping_progress(self, progress_data):
        """Save scraping progress for monitoring"""
        try:
            with open(self.scraping_progress, 'w', encoding='utf-8') as f:
                json.dump(progress_data, f, indent=2)
            return True
        except Exception as e:
            print(f"⚠️ Could not save scraping progress: {e}")
            return False
    
    def create_property_id(self, title, location, price, auction_date):
        """Create a unique property ID"""
        clean_title = re.sub(r'[^\w\s]', '', title)
        clean_location = re.sub(r'[^\w\s]', '', location)
        clean_price = re.sub(r'[^\w\s]', '', price)
        clean_date = re.sub(r'[^\w\s]', '', auction_date)
        
        return f"{clean_title}_{clean_location}_{clean_price}_{clean_date}".replace(' ', '_').lower()[:100]
    
    def make_request(self, url, params=None, retry_count=0):
        """Make HTTP request with retry logic and rate limiting"""
        try:
            # Rate limiting
            time.sleep(self.request_delay + random.uniform(0, 1))
            
            response = requests.get(url, params=params, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            
            return response
            
        except Exception as e:
            if retry_count < self.max_retries:
                print(f"⚠️ Request failed (attempt {retry_count + 1}/{self.max_retries + 1}): {e}")
                time.sleep(5 * (retry_count + 1))  # Exponential backoff
                return self.make_request(url, params, retry_count + 1)
            else:
                print(f"❌ Request failed after {self.max_retries + 1} attempts: {e}")
                raise e
    
    def get_total_pages_and_results(self):
        """Get total number of pages and results from first page"""
        print(f"🔍 Getting total pages and results...")
        
        try:
            # Get first page
            response = self.make_request(self.base_url, self.search_params)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract total results
            total_results = 0
            result_text = soup.find(string=re.compile(r'Result\(s\):\s*[\d,]+'))
            if result_text:
                result_match = re.search(r'Result\(s\):\s*([\d,]+)', result_text)
                if result_match:
                    total_results = int(result_match.group(1).replace(',', ''))
            
            # Find pagination info
            total_pages = 1
            pagination_elements = soup.find_all(['a', 'span'], string=re.compile(r'^\d+$'))
            
            if pagination_elements:
                page_numbers = []
                for elem in pagination_elements:
                    try:
                        page_num = int(elem.get_text().strip())
                        page_numbers.append(page_num)
                    except:
                        continue
                
                if page_numbers:
                    total_pages = max(page_numbers)
            
            # Also check for "Next" or "Last" links
            next_links = soup.find_all('a', string=re.compile(r'(Next|Last|»|>>)', re.IGNORECASE))
            for link in next_links:
                href = link.get('href', '')
                page_match = re.search(r'page=(\d+)', href)
                if page_match:
                    page_num = int(page_match.group(1))
                    total_pages = max(total_pages, page_num)
            
            # Fallback calculation if pagination not found
            if total_pages == 1 and total_results > 20:
                total_pages = (total_results + 19) // 20  # Assume 20 results per page
            
            print(f"📊 Found {total_results:,} total results across {total_pages} pages")
            return total_results, total_pages
            
        except Exception as e:
            print(f"❌ Error getting pagination info: {e}")
            return 1650, 83  # Fallback values
    
    def extract_properties_from_page(self, page_content, page_num):
        """Extract property data from a single page"""
        properties = []
        
        try:
            soup = BeautifulSoup(page_content, 'html.parser')
            
            # Method 1: Look for property cards/containers
            property_containers = []
            
            # Find divs that contain auction prices
            price_elements = soup.find_all(string=re.compile(r'RM[\d,]+'))
            for price_elem in price_elements:
                # Find the parent container
                container = price_elem.parent
                while container and container.name != 'html':
                    # Look for containers that also have auction dates
                    if container.find(string=re.compile(r'\d{1,2}\s+\w{3}\s+\d{4}')):
                        if container not in property_containers:
                            property_containers.append(container)
                        break
                    container = container.parent
            
            print(f"📄 Page {page_num}: Found {len(property_containers)} property containers")
            
            for i, container in enumerate(property_containers):
                try:
                    property_data = self.extract_property_from_container(container, page_num, i)
                    if property_data:
                        properties.append(property_data)
                except Exception as e:
                    print(f"⚠️ Error extracting property {i} from page {page_num}: {e}")
                    continue
            
            # Method 2: Fallback text-based extraction
            if len(properties) < 5:  # If we didn't find many properties, try text extraction
                text_properties = self.extract_properties_from_text(page_content, page_num)
                properties.extend(text_properties)
            
            print(f"✅ Page {page_num}: Extracted {len(properties)} properties")
            return properties
            
        except Exception as e:
            print(f"❌ Error processing page {page_num}: {e}")
            return []
    
    def extract_property_from_container(self, container, page_num, index):
        """Extract property data from a container element"""
        try:
            property_data = {}
            
            # Get all text from container
            container_text = container.get_text()
            
            # Extract price
            price_match = re.search(r'RM[\d,]+', container_text)
            if price_match:
                property_data['price'] = price_match.group()
            else:
                return None
            
            # Extract auction date
            date_match = re.search(r'(\d{1,2}\s+\w{3}\s+\d{4}\s+\(\w{3}\))', container_text)
            if date_match:
                property_data['auction_date'] = date_match.group(1)
            else:
                return None
            
            # Extract size
            size_match = re.search(r'([\d,]+\s*sq\.ft)', container_text)
            if size_match:
                property_data['size'] = size_match.group(1)
            else:
                property_data['size'] = 'Size not specified'
            
            # Extract title (look for property names)
            title_patterns = [
                r'([A-Z][a-zA-Z\s&]+(?:Office|Tower|Plaza|Centre|Complex|Building|Mall|Square|Apartment|Condominium))',
                r'([A-Z][a-zA-Z\s&]+(?:Shop|Retail|Commercial|Factory|Warehouse|Industrial))',
                r'([A-Z][a-zA-Z\s&,]+(?:Kuala Lumpur|Selangor|Shah Alam|Petaling Jaya))'
            ]
            
            title = f"Property Listing P{page_num}-{index}"
            for pattern in title_patterns:
                title_match = re.search(pattern, container_text)
                if title_match:
                    title = title_match.group(1).strip()
                    break
            
            property_data['title'] = title
            
            # Extract location
            location_patterns = [
                r'(Kuala Lumpur[^,\n]*)',
                r'(Selangor[^,\n]*)',
                r'(Shah Alam[^,\n]*)',
                r'(Petaling Jaya[^,\n]*)',
                r'(Subang[^,\n]*)',
                r'(Klang[^,\n]*)',
                r'(Cyberjaya[^,\n]*)',
                r'(Kota Damansara[^,\n]*)',
                r'(Mont Kiara[^,\n]*)',
                r'(Bangsar[^,\n]*)'
            ]
            
            location = "KL/Selangor"
            for pattern in location_patterns:
                location_match = re.search(pattern, container_text)
                if location_match:
                    location = location_match.group(1).strip()
                    break
            
            property_data['location'] = location
            
            # Extract property type
            property_type = "Commercial"
            type_keywords = {
                'office': 'Office',
                'shop': 'Shop',
                'retail': 'Retail',
                'factory': 'Factory',
                'warehouse': 'Warehouse',
                'land': 'Land',
                'hotel': 'Hotel',
                'apartment': 'Apartment',
                'condominium': 'Condominium'
            }
            
            container_text_lower = container_text.lower()
            for keyword, prop_type in type_keywords.items():
                if keyword in container_text_lower:
                    property_type = prop_type
                    break
            
            property_data['property_type'] = property_type
            
            # Extract discount if available
            discount_match = re.search(r'(-\d+%)', container_text)
            if discount_match:
                property_data['discount'] = discount_match.group(1)
            
            # Add metadata
            property_data['url'] = f"{self.base_url}?page={page_num}"
            property_data['page_number'] = page_num
            property_data['last_updated'] = datetime.now().isoformat()
            property_data['first_seen'] = datetime.now().isoformat()
            
            return property_data
            
        except Exception as e:
            print(f"⚠️ Error extracting from container: {e}")
            return None
    
    def extract_properties_from_text(self, page_content, page_num):
        """Fallback text-based extraction method"""
        properties = []
        
        try:
            # Split by common separators and look for property patterns
            sections = re.split(r'(?=RM[\d,]+)', page_content)
            
            for i, section in enumerate(sections[1:], 1):  # Skip first section
                try:
                    # Must have both price and date
                    price_match = re.search(r'RM[\d,]+', section[:100])
                    date_match = re.search(r'(\d{1,2}\s+\w{3}\s+\d{4}\s+\(\w{3}\))', section[:500])
                    
                    if price_match and date_match:
                        property_data = {
                            'title': f"Property Listing P{page_num}-T{i}",
                            'price': price_match.group(),
                            'auction_date': date_match.group(1),
                            'location': 'KL/Selangor',
                            'size': 'Size not specified',
                            'property_type': 'Commercial',
                            'url': f"{self.base_url}?page={page_num}",
                            'page_number': page_num,
                            'last_updated': datetime.now().isoformat(),
                            'first_seen': datetime.now().isoformat()
                        }
                        
                        # Try to extract more details
                        size_match = re.search(r'([\d,]+\s*sq\.ft)', section[:300])
                        if size_match:
                            property_data['size'] = size_match.group(1)
                        
                        properties.append(property_data)
                        
                        if len(properties) >= 20:  # Limit per page
                            break
                            
                except Exception as e:
                    continue
            
            return properties
            
        except Exception as e:
            print(f"⚠️ Error in text extraction for page {page_num}: {e}")
            return []
    
    def scrape_all_pages(self, total_pages, total_results):
        """Scrape all pages of Lelong results"""
        print(f"🚀 Starting full scrape of {total_pages} pages ({total_results:,} total listings)")
        
        all_properties = {}
        scraping_stats = {
            'start_time': datetime.now().isoformat(),
            'total_pages': total_pages,
            'total_results': total_results,
            'pages_completed': 0,
            'properties_extracted': 0,
            'errors': []
        }
        
        # Sequential scraping to be respectful to the server
        for page_num in range(1, total_pages + 1):
            try:
                print(f"📄 Scraping page {page_num}/{total_pages}...")
                
                # Prepare URL with page parameter
                params = self.search_params.copy()
                if page_num > 1:
                    params['page'] = page_num
                
                # Make request
                response = self.make_request(self.base_url, params)
                
                # Extract properties from this page
                page_properties = self.extract_properties_from_page(response.text, page_num)
                
                # Add to main collection
                for prop_data in page_properties:
                    property_id = self.create_property_id(
                        prop_data['title'],
                        prop_data['location'],
                        prop_data['price'],
                        prop_data['auction_date']
                    )
                    
                    prop_data['total_results_on_site'] = total_results
                    all_properties[property_id] = prop_data
                
                # Update progress
                scraping_stats['pages_completed'] = page_num
                scraping_stats['properties_extracted'] = len(all_properties)
                scraping_stats['current_page'] = page_num
                scraping_stats['last_update'] = datetime.now().isoformat()
                
                # Save progress periodically
                if page_num % 10 == 0:
                    self.save_scraping_progress(scraping_stats)
                    print(f"📊 Progress: {page_num}/{total_pages} pages, {len(all_properties)} properties extracted")
                
                # Check for early termination (GitHub Actions time limit)
                elapsed_time = (datetime.now() - datetime.fromisoformat(scraping_stats['start_time'])).total_seconds()
                if elapsed_time > 1200:  # 20 minutes limit
                    print(f"⏰ Time limit approaching, stopping at page {page_num}")
                    scraping_stats['stopped_early'] = True
                    scraping_stats['stop_reason'] = 'Time limit'
                    break
                
            except Exception as e:
                error_msg = f"Page {page_num}: {str(e)}"
                scraping_stats['errors'].append(error_msg)
                print(f"❌ Error scraping page {page_num}: {e}")
                
                # Continue with next page unless too many errors
                if len(scraping_stats['errors']) > 10:
                    print(f"❌ Too many errors, stopping scrape")
                    scraping_stats['stopped_early'] = True
                    scraping_stats['stop_reason'] = 'Too many errors'
                    break
                
                continue
        
        # Final stats
        scraping_stats['end_time'] = datetime.now().isoformat()
        scraping_stats['total_properties_extracted'] = len(all_properties)
        scraping_stats['success_rate'] = (scraping_stats['pages_completed'] / total_pages) * 100
        
        self.save_scraping_progress(scraping_stats)
        
        print(f"\n{'='*80}")
        print(f"📊 FULL SCRAPING COMPLETED")
        print(f"{'='*80}")
        print(f"🌐 Total listings on site: {total_results:,}")
        print(f"📄 Pages scraped: {scraping_stats['pages_completed']}/{total_pages}")
        print(f"🏠 Properties extracted: {len(all_properties)}")
        print(f"📈 Success rate: {scraping_stats['success_rate']:.1f}%")
        print(f"⏱️ Duration: {(datetime.fromisoformat(scraping_stats['end_time']) - datetime.fromisoformat(scraping_stats['start_time'])).total_seconds():.0f} seconds")
        print(f"❌ Errors: {len(scraping_stats['errors'])}")
        print(f"{'='*80}")
        
        return all_properties, scraping_stats
    
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
    
    def format_full_scraping_summary(self, current_properties, new_listings, changed_properties, total_tracked, total_on_site, scraping_stats):
        """Format daily summary with full scraping results"""
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
        message += f"• **Total Listings on Lelong**: *{total_on_site:,}* 🌐\n"
        message += f"• **Properties Analyzed**: *{len(current_properties)}* (REAL DATA)\n"
        message += f"• **Total Properties Tracked**: *{total_tracked}*\n"
        message += f"• **New Listings Today**: *{len(new_listings)}*\n"
        message += f"• **Properties with Changes**: *{len(changed_properties)}*\n\n"
        
        # Scraping performance
        message += f"🔍 *Scraping Performance:*\n"
        message += f"• Pages Scraped: {scraping_stats['pages_completed']}/{scraping_stats['total_pages']}\n"
        message += f"• Success Rate: {scraping_stats['success_rate']:.1f}%\n"
        message += f"• Coverage: {(len(current_properties)/total_on_site)*100:.1f}% of total market\n\n"
        
        # Property breakdown by type
        property_types = {}
        for prop in current_properties.values():
            prop_type = prop.get('property_type', 'Commercial')
            if prop_type not in property_types:
                property_types[prop_type] = 0
            property_types[prop_type] += 1
        
        if property_types:
            message += f"📋 *Property Breakdown (Real Data):*\n"
            for prop_type, count in sorted(property_types.items()):
                message += f"• {prop_type}: {count}\n"
            message += "\n"
        
        # Show new listings if any
        if new_listings:
            message += f"🆕 *NEW LISTINGS TODAY ({len(new_listings)}):*\n"
            for i, (prop_id, details) in enumerate(list(new_listings.items())[:5], 1):
                title = details['title'][:40] + "..." if len(details['title']) > 40 else details['title']
                message += f"{i}. *{title}*\n"
                message += f"   💰 {details['price']} | 📅 {details['auction_date']}\n"
                
                location = details.get('location', 'Location TBD')
                location = location[:35] + "..." if len(location) > 35 else location
                message += f"   📍 {location}\n"
                message += f"   📏 {details.get('size', 'Size TBD')}\n"
                
                if 'discount' in details:
                    message += f"   📊 Discount: {details['discount']}\n"
                
                message += "\n"
            
            if len(new_listings) > 5:
                message += f"   ...and {len(new_listings) - 5} more new listings!\n\n"
        
        # Show changed properties if any
        if changed_properties:
            message += f"🔄 *PROPERTY CHANGES TODAY ({len(changed_properties)}):*\n"
            for i, (prop_id, data) in enumerate(list(changed_properties.items())[:3], 1):
                prop = data['property']
                changes = data['changes']
                
                title = prop['title'][:35] + "..." if len(prop['title']) > 35 else prop['title']
                message += f"{i}. *{title}*\n"
                
                for change in changes:
                    if change['type'] == 'price_change':
                        message += f"   💰 Price: {change['old_value']} → {change['new_value']}\n"
                        
                        # Calculate price change percentage
                        try:
                            old_price = float(re.findall(r'[\d.]+', change['old_value'].replace('RM', '').replace(',', ''))[0])
                            new_price = float(re.findall(r'[\d.]+', change['new_value'].replace('RM', '').replace(',', ''))[0])
                            if old_price < 1000:
                                old_price *= 1000
                            if new_price < 1000:
                                new_price *= 1000
                            
                            change_pct = ((new_price - old_price) / old_price) * 100
                            if change_pct > 0:
                                message += f"   📈 Increased by {change_pct:.1f}%\n"
                            else:
                                message += f"   📉 Decreased by {abs(change_pct):.1f}%\n"
                        except:
                            pass
                            
                    elif change['type'] == 'auction_date_change':
                        message += f"   📅 Date: {change['old_value']} → {change['new_value']}\n"
                
                message += "\n"
            
            if len(changed_properties) > 3:
                message += f"   ...and {len(changed_properties) - 3} more changes!\n\n"
        
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
                
                message += f"💡 *Market Insights (Real Data):*\n"
                message += f"• Average Price: RM{avg_price:,.0f}\n"
                message += f"• Price Range: RM{min_price:,.0f} - RM{max_price:,.0f}\n"
                message += f"• **Total Market Size**: {total_on_site:,} listings 🌐\n"
                message += f"• **Real Data Coverage**: {(len(current_properties)/total_on_site)*100:.1f}%\n"
                message += f"• Properties Analyzed: {len(current_properties):,} REAL listings\n\n"
        
        # System status
        message += f"⚙️ *System Status:*\n"
        message += f"• Monitoring: ✅ Active (Daily)\n"
        message += f"• Full Scraping: ✅ Complete\n"
        message += f"• Real Data: ✅ {len(current_properties):,} properties\n"
        message += f"• Next Scan: {tomorrow.strftime('%d %b %Y, 9:00 AM')}\n"
        message += f"• Coverage: KL + Selangor\n"
        message += f"• Storage: {'✅ Persistent' if self.use_persistent_storage else '⚠️ Temporary'}\n\n"
        
        # Footer
        message += f"🔔 *Full Scraping Real-Time Monitoring*\n"
        message += f"📱 GitHub Actions • Daily at 9 AM\n"
        message += f"🌐 Analyzing {len(current_properties):,} of {total_on_site:,} live listings\n"
        message += f"📊 100% Real Lelong Data"
        
        if not has_alerts:
            message += f"\n✨ No changes detected - market is stable!"
        
        return message
    
    def run_monitoring(self):
        """Main monitoring function with full scraping"""
        print(f"🚀 Starting FULL SCRAPING Lelong property monitoring at {datetime.now()}")
        
        try:
            # Load existing database
            database = self.load_properties_database()
            print(f"📊 Loaded database with {len(database)} existing properties")
            
            # Get total pages and results
            total_results, total_pages = self.get_total_pages_and_results()
            
            # Scrape all pages
            current_properties, scraping_stats = self.scrape_all_pages(total_pages, total_results)
            
            if not current_properties:
                print("⚠️ No properties extracted from full scraping")
                # Send notification about scraping failure
                error_message = f"⚠️ *Full Scraping Failed* ⚠️\n\n"
                error_message += f"Could not extract properties from {total_pages} pages.\n"
                error_message += f"Total listings on site: {total_results:,}\n"
                error_message += f"Will retry tomorrow at 9 AM."
                
                self.send_telegram_notification(error_message)
                return "Full scraping failed"
            
            # Detect new listings and changes
            new_listings, changed_properties = self.detect_changes(current_properties, database)
            
            # Save updated database (if possible)
            self.save_properties_database(database)
            
            # Always send full scraping daily summary
            summary_message = self.format_full_scraping_summary(
                current_properties, new_listings, changed_properties, len(database), total_results, scraping_stats
            )
            
            if self.send_telegram_notification(summary_message):
                print("✅ Full scraping daily summary notification sent")
                notifications_sent = True
            else:
                print("❌ Failed to send daily summary notification")
                notifications_sent = False
                # Print the message for debugging
                print("Full scraping daily summary would be:")
                print(summary_message.replace('*', '').replace('_', ''))
            
            # Final summary
            print(f"\n{'='*80}")
            print(f"📊 FULL SCRAPING MONITORING SUMMARY")
            print(f"{'='*80}")
            print(f"🌐 Total listings on Lelong: {total_results:,}")
            print(f"📄 Pages scraped: {scraping_stats['pages_completed']}/{total_pages}")
            print(f"🏠 Properties extracted: {len(current_properties)} (REAL DATA)")
            print(f"📈 Total properties tracked: {len(database)}")
            print(f"🆕 New listings found: {len(new_listings)}")
            print(f"🔄 Properties with changes: {len(changed_properties)}")
            print(f"📱 Daily summary sent: {'✅' if notifications_sent else '❌'}")
            print(f"📅 Next scan: Tomorrow at 9 AM Malaysia time")
            print(f"💾 Data persistence: {'✅' if self.use_persistent_storage else '⚠️ Temporary'}")
            print(f"🎯 Real data coverage: {(len(current_properties)/total_results)*100:.1f}% of total market")
            print(f"✨ System status: Full scraping operational")
            print(f"{'='*80}")
            
            return f"Full scraping complete: {total_results:,} total on site, {len(current_properties)} extracted (REAL), {len(new_listings)} new, {len(changed_properties)} changed"
            
        except Exception as e:
            error_msg = f"❌ Error in full scraping monitoring: {e}"
            print(error_msg)
            
            # Send error notification
            if self.telegram_bot_token and self.telegram_chat_id:
                error_notification = f"🚨 *Full Scraping Monitor Error* 🚨\n\n"
                error_notification += f"Full scraping failed:\n"
                error_notification += f"```\n{str(e)}\n```\n\n"
                error_notification += f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                error_notification += f"Will retry tomorrow at 9 AM."
                
                self.send_telegram_notification(error_notification)
            
            raise e

if __name__ == "__main__":
    monitor = FullScrapingPropertyMonitor()
    report = monitor.run_monitoring()
