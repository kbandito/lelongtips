#!/usr/bin/env python3
"""
Setup and test script for GitHub Property Monitor
Run this locally to test before deploying to GitHub Actions
"""

import os
import sys
from pathlib import Path

def check_requirements():
    """Check if required packages are installed"""
    try:
        import requests
        import bs4
        print("✅ Required packages are installed")
        return True
    except ImportError as e:
        print(f"❌ Missing required package: {e}")
        print("Please install requirements: pip install -r src/requirements.txt")
        return False

def check_telegram_setup():
    """Check if Telegram credentials are configured"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if bot_token and chat_id:
        print("✅ Telegram credentials are configured")
        return True
    else:
        print("⚠️ Telegram credentials not found in environment variables")
        print("Set them with:")
        print("export TELEGRAM_BOT_TOKEN='your_bot_token'")
        print("export TELEGRAM_CHAT_ID='your_chat_id'")
        return False

def test_monitoring():
    """Test the monitoring script"""
    print("\n🧪 Testing monitoring script...")
    
    # Add src directory to path
    src_path = Path(__file__).parent / "src"
    sys.path.insert(0, str(src_path))
    
    try:
        from monitor import GitHubPropertyMonitor
        
        monitor = GitHubPropertyMonitor()
        print("✅ Monitor initialized successfully")
        
        # Test database operations
        database = monitor.load_properties_database()
        print(f"✅ Database loaded: {len(database)} properties")
        
        # Test scraping (this will use mock data)
        properties = monitor.scrape_lelong_properties()
        print(f"✅ Scraping test: {len(properties)} properties found")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing monitor: {e}")
        return False

def main():
    """Main setup function"""
    print("🚀 GitHub Property Monitor Setup")
    print("=" * 50)
    
    # Check requirements
    if not check_requirements():
        return False
    
    # Check Telegram setup
    telegram_ok = check_telegram_setup()
    
    # Test monitoring
    if not test_monitoring():
        return False
    
    print("\n✅ Setup complete!")
    
    if telegram_ok:
        print("\n🎯 Next steps:")
        print("1. Push this code to your GitHub repository")
        print("2. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to GitHub Secrets")
        print("3. Enable GitHub Actions in your repository")
        print("4. The monitoring will run daily at 9 AM Malaysia time")
    else:
        print("\n🎯 Next steps:")
        print("1. Set up your Telegram bot credentials")
        print("2. Run this setup script again to verify")
        print("3. Push to GitHub and configure secrets")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

