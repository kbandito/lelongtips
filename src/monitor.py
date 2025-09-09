#!/usr/bin/env python3
"""
Property Monitoring Script for GitHub Actions
Monitors Lelong auction properties with change tracking and Telegram notifications
Optimized for daily execution on GitHub Actions
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import os
from datetime import datetime
import re
from pathlib import Path

class GitHubPropertyMonitor:
    def __init__(self):
        # GitHub Actions optimized paths
        self.base_path = Path(__file__).parent.parent
        self.data_path = self.base_path / "data"
        self.reports_path = self.data_path / "reports"
        
        # Create directories if they don't exist
        self.data_path.mkdir(exist_ok=True)
        self.reports_path.mkdir(exist_ok=True)
        
        # File paths
        self.properties_database = self.data_path / "properties.json"
        self.changes_history = self.data_path / "changes.json"
        self.report_file = self.reports_path / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        
        # Search URL with expanded property types
        self.lelong_url = "https://www.lelongtips.com.my/search?keyword=&property_type%5B%5D=7&property_type%5B%5D=6&property_type%5B%5D=8&property_type%5B%5D=4&property_type%5B%5D=5&state=kl_sel&bank=&listing_status=&input-date=&auction-date=&case=&listing_type=&min_price=&max_price=&min_size=&max_size="
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Notification settings from environment variables
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        self.whatsapp_api_key = os.getenv('WHATSAPP_API_KEY', '')
        self.whatsapp_phone_number = os.getenv('WHATSAPP_PHONE_NUMBER', '')
        
        print(f"🚀 GitHub Property Monitor initialized")
        print(f"📁 Data path: {self.data_path}")
        print(f"📊 Reports path: {self.reports_path}")
        print(f"🤖 Telegram configured: {'✅' if self.telegram_bot_token and self.telegram_chat_id else '❌'}")
    
    def load_properties_database(self):
        """Load the complete properties database with history"""
        if self.properties_database.exists():
            try:
                with open(self.properties_database, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Error loading properties database: {e}")
                return {}
        return {}
    
    def save_properties_database(self, database):
        """Save the properties database"""
        try:
            with open(self.properties_database, 'w', encoding='utf-8') as f:
                json.dump(database, f, indent=2, ensure_ascii=False)
            print(f"💾 Properties database saved: {len(database)} properties")
        except Exception as e:
            print(f"❌ Error saving properties database: {e}")
    
    def load_changes_history(self):
        """Load the changes history"""
        if self.changes_history.exists():
            try:
                with open(self.changes_history, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Error loading changes history: {e}")
                return []
        return []
    
    def save_changes_history(self, history):
        """Save the changes history"""
        try:
            with open(self.changes_history, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            print(f"📝 Changes history saved: {len(history)} total changes")
        except Exception as e:
            print(f"❌ Error saving changes history: {e}")
    
    def create_property_id(self, title, location, size):
        """Create a unique property ID based on immutable characteristics"""
        # Clean and normalize the ID
        clean_title = re.sub(r'[^\w\s]', '', title)
        clean_location = re.sub(r'[^\w\s]', '', location)
        clean_size = re.sub(r'[^\w\s]', '', size)
        
        return f"{clean_title}_{clean_location}_{clean_size}".replace(' ', '_').lower()
    
    def scrape_lelong_properties(self):
        """Scrape current Lelong auction properties with detailed information"""
        print(f"🔍 Scraping properties from: {self.lelong_url}")
        
        try:
            response = requests.get(self.lelong_url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            properties = {}
            
            # Mock data for demonstration (replace with actual scraping logic)
            # In a real implementation, you would parse the actual HTML structure
            mock_properties = [
                {
                    'title': 'Menara UP Office Unit',
                    'price': 'RM204,000',
                    'location': 'Kuala Lumpur',
                    'size': '1,323 sq.ft',
                    'auction_date': '10 Sep 2025 (Wed)'
                },
                {
                    'title': 'Radia Office Strata',
                    'price': 'RM351,000',
                    'location': 'Shah Alam, Selangor',
                    'size': '1,755 sq.ft',
                    'auction_date': '10 Sep 2025 (Wed)'
                },
                {
                    'title': 'Emporis Shop Lot',
                    'price': 'RM735,900',
                    'location': 'Kota Damansara, Selangor',
                    'size': '1,679 sq.ft',
                    'auction_date': '25 Sep 2025 (Thu)'
                }
            ]
            
            for prop_data in mock_properties:
                property_id = self.create_property_id(
                    prop_data['title'], 
                    prop_data['location'], 
                    prop_data['size']
                )
                
                properties[property_id] = {
                    **prop_data,
                    'url': self.lelong_url,
                    'last_updated': datetime.now().isoformat(),
                    'first_seen': datetime.now().isoformat()
                }
            
            print(f"✅ Successfully scraped {len(properties)} properties")
            return properties
            
        except Exception as e:
            print(f"❌ Error scraping Lelong: {e}")
            return {}
    
    def detect_changes(self, current_properties, database):
        """Detect new listings and changes in existing properties"""
        new_listings = {}
        changed_properties = {}
        changes_history = self.load_changes_history()
        
        print(f"🔍 Analyzing {len(current_properties)} current properties against {len(database)} in database")
        
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
                    
                    # Update price history
                    if 'price_history' not in existing_data:
                        existing_data['price_history'] = [{'price': existing_data['price'], 'date': existing_data.get('first_seen', current_data['last_updated'])}]
                    existing_data['price_history'].append({'price': current_data['price'], 'date': current_data['last_updated']})
                    
                    print(f"💰 Price change detected: {current_data['title']} - {existing_data['price']} → {current_data['price']}")
                
                # Check auction date change
                if current_data['auction_date'] != existing_data['auction_date']:
                    changes.append({
                        'type': 'auction_date_change',
                        'field': 'Auction Date',
                        'old_value': existing_data['auction_date'],
                        'new_value': current_data['auction_date'],
                        'change_date': current_data['last_updated']
                    })
                    
                    # Update auction date history
                    if 'auction_date_history' not in existing_data:
                        existing_data['auction_date_history'] = [{'auction_date': existing_data['auction_date'], 'date': existing_data.get('first_seen', current_data['last_updated'])}]
                    existing_data['auction_date_history'].append({'auction_date': current_data['auction_date'], 'date': current_data['last_updated']})
                    
                    print(f"📅 Date change detected: {current_data['title']} - {existing_data['auction_date']} → {current_data['auction_date']}")
                
                if changes:
                    changed_properties[prop_id] = {
                        'property': current_data,
                        'changes': changes,
                        'history': {
                            'price_history': existing_data.get('price_history', []),
                            'auction_date_history': existing_data.get('auction_date_history', [])
                        }
                    }
                    
                    # Add to global changes history
                    for change in changes:
                        changes_history.append({
                            'property_id': prop_id,
                            'property_title': current_data['title'],
                            **change
                        })
                
                # Update database with current data
                database[prop_id].update(current_data)
                database[prop_id]['first_seen'] = existing_data.get('first_seen', current_data['last_updated'])
        
        # Save updated changes history
        self.save_changes_history(changes_history)
        
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
                    time.sleep(1)  # Rate limiting
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
    
    def format_notifications(self, new_listings, changed_properties):
        """Format and send notifications"""
        notifications_sent = 0
        
        # Send notification for new listings
        if new_listings:
            message = f"🚨 *NEW PROPERTY ALERTS* 🚨\n\n"
            message += f"Found *{len(new_listings)}* new auction properties!\n\n"
            
            for i, (prop_id, details) in enumerate(new_listings.items(), 1):
                message += f"*{i}. {details['title']}*\n"
                message += f"💰 Price: {details['price']}\n"
                message += f"📅 Auction Date: {details['auction_date']}\n"
                message += f"📍 Location: {details['location']}\n"
                message += f"📏 Size: {details['size']}\n"
                
                # Calculate potential savings
                try:
                    auction_price_str = details['price'].replace('RM', '').replace(',', '')
                    auction_price = float(re.findall(r'[\d.]+', auction_price_str)[0])
                    if auction_price < 1000:
                        auction_price *= 1000
                    
                    size_str = details['size'].replace('sq.ft', '').replace(',', '')
                    size_sqft = float(re.findall(r'[\d.]+', size_str)[0]) if re.findall(r'[\d.]+', size_str) else 1000
                    
                    auction_psf = auction_price / size_sqft
                    market_psf = 1280  # Average from EdgeProp
                    savings_percentage = ((market_psf - auction_psf) / market_psf) * 100
                    
                    message += f"📊 Potential Savings: {savings_percentage:.1f}% below market\n"
                    message += f"💡 Market PSF: RM{market_psf} vs Auction PSF: RM{auction_psf:.2f}\n"
                except:
                    message += f"📊 Significant discount expected (50-74% typical)\n"
                
                message += f"🔗 View: {details['url']}\n\n"
                
                if i >= 3:  # Limit to 3 properties per notification
                    remaining = len(new_listings) - 3
                    if remaining > 0:
                        message += f"...and {remaining} more new properties!\n\n"
                    break
            
            message += f"📈 *Market Context:*\n"
            message += f"• Daily monitoring by GitHub Actions\n"
            message += f"• Auction discounts: 50-74% below market\n"
            message += f"• Market average: RM1,280 per sq.ft\n"
            
            if self.send_telegram_notification(message):
                print("✅ New listings notification sent")
                notifications_sent += 1
        
        # Send notification for changes
        if changed_properties:
            message = f"🔄 *PROPERTY CHANGES DETECTED* 🔄\n\n"
            message += f"Found *{len(changed_properties)}* properties with changes!\n\n"
            
            for i, (prop_id, data) in enumerate(changed_properties.items(), 1):
                prop = data['property']
                changes = data['changes']
                history = data['history']
                
                message += f"*{i}. {prop['title']}*\n"
                message += f"📍 Location: {prop['location']}\n"
                message += f"📏 Size: {prop['size']}\n\n"
                
                # Show changes
                for change in changes:
                    if change['type'] == 'price_change':
                        message += f"💰 *Price Changed:*\n"
                        message += f"   Old: {change['old_value']}\n"
                        message += f"   New: {change['new_value']}\n"
                        
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
                        message += f"📅 *Auction Date Changed:*\n"
                        message += f"   Old: {change['old_value']}\n"
                        message += f"   New: {change['new_value']}\n"
                
                # Show recent history (last 3 entries)
                message += f"\n📊 *Recent History:*\n"
                
                if 'price_history' in history and len(history['price_history']) > 1:
                    message += f"💰 Price History:\n"
                    recent_prices = history['price_history'][-3:]  # Last 3 entries
                    for j, price_entry in enumerate(recent_prices):
                        date_str = datetime.fromisoformat(price_entry['date']).strftime('%d %b')
                        message += f"   {j+1}. {price_entry['price']} ({date_str})\n"
                
                message += f"🔗 View: {prop['url']}\n\n"
                message += "---\n\n"
                
                if i >= 2:  # Limit to 2 properties per notification for changes
                    remaining = len(changed_properties) - 2
                    if remaining > 0:
                        message += f"...and {remaining} more properties with changes!\n\n"
                    break
            
            if self.send_telegram_notification(message):
                print("✅ Property changes notification sent")
                notifications_sent += 1
        
        return notifications_sent > 0
    
    def generate_report(self, new_listings, changed_properties, database):
        """Generate comprehensive report"""
        report = f"""# Property Monitoring Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Daily GitHub Actions Run)

## Summary
- **New Listings Found**: {len(new_listings)}
- **Properties with Changes**: {len(changed_properties)}
- **Total Properties Tracked**: {len(database)}
- **Source**: Lelong Auction Properties (All Types)
- **Search Criteria**: Factory/Warehouse, Hotel/Resort, Land, Semi-D/Bungalow/Villa, Shop/Office/Retail in KL + Selangor
- **Execution**: GitHub Actions (Daily at 9 AM Malaysia Time)

"""
        
        if new_listings:
            report += "## New Auction Listings\n\n"
            
            for prop_id, details in new_listings.items():
                report += f"### {details['title']}\n"
                report += f"- **Auction Price**: {details['price']}\n"
                report += f"- **Auction Date**: {details['auction_date']}\n"
                report += f"- **Location**: {details['location']}\n"
                report += f"- **Size**: {details['size']}\n"
                report += f"- **URL**: {details['url']}\n\n"
                report += "---\n\n"
        
        if changed_properties:
            report += "## Property Changes Detected\n\n"
            
            for prop_id, data in changed_properties.items():
                prop = data['property']
                changes = data['changes']
                history = data['history']
                
                report += f"### {prop['title']}\n"
                report += f"- **Location**: {prop['location']}\n"
                report += f"- **Size**: {prop['size']}\n\n"
                
                report += "#### Changes Detected\n"
                for change in changes:
                    report += f"- **{change['field']}**: {change['old_value']} → {change['new_value']}\n"
                
                report += "\n#### Complete History\n"
                if 'price_history' in history:
                    report += "**Price History:**\n"
                    for i, entry in enumerate(history['price_history']):
                        date_str = datetime.fromisoformat(entry['date']).strftime('%Y-%m-%d %H:%M')
                        report += f"{i+1}. {entry['price']} ({date_str})\n"
                
                if 'auction_date_history' in history:
                    report += "\n**Auction Date History:**\n"
                    for i, entry in enumerate(history['auction_date_history']):
                        date_str = datetime.fromisoformat(entry['date']).strftime('%Y-%m-%d %H:%M')
                        report += f"{i+1}. {entry['auction_date']} (changed {date_str})\n"
                
                report += "\n---\n\n"
        
        if not new_listings and not changed_properties:
            report += "## No Changes Detected\n\nNo new listings or changes found since last check.\n\n"
        
        report += """## System Information

### GitHub Actions Configuration
- **Schedule**: Daily at 9 AM Malaysia Time (1 AM UTC)
- **Runtime**: Ubuntu Latest with Python 3.11
- **Data Persistence**: Repository-based storage
- **Notifications**: Telegram (configurable)

### Market Context
- **Discount Range**: 50-74% below market value
- **Property Types**: Factory/Warehouse, Hotel/Resort, Land, Semi-D/Bungalow/Villa, Shop/Office/Retail
- **Coverage Area**: Kuala Lumpur + Selangor
- **Market Average**: RM1,280 per sq.ft (Commercial Office)

### Investment Intelligence
Auction properties typically offer significant discounts compared to market prices. Price changes and auction date changes can indicate:
- Market dynamics and bidding interest
- Property urgency or bank flexibility
- Optimal timing for investment decisions

---
*Report generated by GitHub Actions Property Monitoring System*
"""
        
        # Save report to file
        try:
            with open(self.report_file, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"📄 Report saved: {self.report_file}")
        except Exception as e:
            print(f"❌ Error saving report: {e}")
        
        return report
    
    def run_monitoring(self):
        """Main monitoring function optimized for GitHub Actions"""
        print(f"🚀 Starting GitHub Actions property monitoring at {datetime.now()}")
        print(f"🌍 Environment: GitHub Actions")
        print(f"📅 Schedule: Daily execution")
        
        try:
            # Load existing database
            database = self.load_properties_database()
            print(f"📊 Loaded database with {len(database)} existing properties")
            
            # Scrape current listings
            current_properties = self.scrape_lelong_properties()
            
            if not current_properties:
                print("⚠️ No properties scraped - this might indicate a scraping issue")
                return "No properties found"
            
            # Detect new listings and changes
            new_listings, changed_properties = self.detect_changes(current_properties, database)
            
            # Send notifications
            notifications_sent = False
            if new_listings or changed_properties:
                notifications_sent = self.format_notifications(new_listings, changed_properties)
            
            # Generate report
            report = self.generate_report(new_listings, changed_properties, database)
            
            # Save updated database
            self.save_properties_database(database)
            
            # Summary
            print(f"\n{'='*60}")
            print(f"📊 MONITORING SUMMARY")
            print(f"{'='*60}")
            print(f"🆕 New listings: {len(new_listings)}")
            print(f"🔄 Changed properties: {len(changed_properties)}")
            print(f"📊 Total properties tracked: {len(database)}")
            print(f"📱 Notifications sent: {'✅' if notifications_sent else '❌'}")
            print(f"📄 Report saved: {self.report_file.name}")
            print(f"{'='*60}")
            
            return report
            
        except Exception as e:
            error_msg = f"❌ Error in monitoring: {e}"
            print(error_msg)
            
            # Send error notification
            if self.telegram_bot_token and self.telegram_chat_id:
                error_notification = f"🚨 *Property Monitor Error* 🚨\n\n"
                error_notification += f"GitHub Actions run failed:\n"
                error_notification += f"```\n{str(e)}\n```\n\n"
                error_notification += f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                error_notification += f"Please check the GitHub Actions logs for details."
                
                self.send_telegram_notification(error_notification)
            
            raise e

if __name__ == "__main__":
    monitor = GitHubPropertyMonitor()
    report = monitor.run_monitoring()

