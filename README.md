# 🏢 Property Auction Monitor

Automated daily monitoring of Lelong auction properties in KL + Selangor with change tracking and Telegram notifications.

## 🚀 Features

- **Daily Monitoring**: Automatically checks for new listings every day at 9 AM (UTC+8)
- **Change Tracking**: Monitors price changes and auction date changes with complete history
- **Telegram Notifications**: Instant alerts for new listings and property changes
- **Comprehensive Coverage**: Monitors 5 property types (Factory/Warehouse, Hotel/Resort, Land, Semi-D/Bungalow/Villa, Shop/Office/Retail)
- **Investment Analysis**: Calculates potential savings and market comparisons
- **Persistent Storage**: Maintains complete property database and change history

## 📱 Notification Examples

### New Listings
```
🚨 NEW PROPERTY ALERTS 🚨

Found 1 new auction property!

1. Menara UP Office Unit
💰 Price: RM204,000
📅 Auction Date: 10 Sep 2025 (Wed)
📍 Location: Kuala Lumpur
📏 Size: 1,323 sq.ft
📊 Potential Savings: 74% below market
💡 Market PSF: RM1,280 vs Auction PSF: RM154.23
```

### Property Changes
```
🔄 PROPERTY CHANGES DETECTED 🔄

Found 1 property with changes!

1. Radia Office Strata
📍 Location: Shah Alam, Selangor
📏 Size: 1,755 sq.ft

💰 Price Changed:
   Old: RM351,000
   New: RM320,000
   📉 Decreased by 8.8%

📊 Complete History:
💰 Price History:
   1. RM380,000 (28 Aug 2025)
   2. RM351,000 (03 Sep 2025)
   3. RM320,000 (08 Sep 2025)
```

## ⚙️ Setup Instructions

### 1. Fork This Repository
Click the "Fork" button to create your own copy of this repository.

### 2. Set Up Telegram Bot
1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Choose a name: "Property Monitor Bot"
4. Choose username: "your_property_monitor_bot" (must be unique)
5. Copy the Bot Token
6. Start a chat with your bot and send any message
7. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
8. Find your Chat ID in the response

### 3. Configure GitHub Secrets
Go to your repository → Settings → Secrets and variables → Actions

Add these secrets:
- `TELEGRAM_BOT_TOKEN`: Your bot token from BotFather
- `TELEGRAM_CHAT_ID`: Your chat ID from the getUpdates URL

### 4. Enable GitHub Actions
1. Go to the "Actions" tab in your repository
2. Click "I understand my workflows, go ahead and enable them"
3. The monitoring will start running automatically

### 5. Test the Setup (Optional)
You can manually trigger the workflow:
1. Go to Actions tab
2. Click "Property Monitor"
3. Click "Run workflow"
4. Check your Telegram for notifications

## 📊 How It Works

1. **Daily Execution**: GitHub Actions runs the monitoring script every day at 9 AM (UTC+8)
2. **Data Persistence**: Property database and change history are stored in the repository
3. **Change Detection**: Compares current data with previous data to detect changes
4. **Notifications**: Sends Telegram messages for new listings and changes
5. **Reporting**: Generates detailed reports with market analysis

## 📁 Repository Structure

```
├── .github/workflows/
│   └── monitor.yml          # GitHub Actions workflow
├── src/
│   ├── monitor.py           # Main monitoring script
│   └── requirements.txt     # Python dependencies
├── data/
│   ├── properties.json      # Property database (auto-generated)
│   ├── changes.json         # Change history (auto-generated)
│   └── reports/             # Generated reports (auto-generated)
├── README.md               # This file
└── .gitignore             # Git ignore file
```

## 🔧 Customization

### Change Monitoring Frequency
Edit `.github/workflows/monitor.yml`:
```yaml
schedule:
  - cron: '0 1 * * *'  # Daily at 9 AM UTC+8 (1 AM UTC)
```

### Modify Search Criteria
Edit `src/monitor.py` to change the search URL or add filters.

### Add More Notification Channels
The script supports both Telegram and WhatsApp. Add WhatsApp credentials to GitHub Secrets to enable WhatsApp notifications.

## 📈 Market Intelligence

The system provides valuable insights:
- **Price Trends**: Track how auction prices change over time
- **Market Timing**: Identify patterns in auction scheduling
- **Investment Opportunities**: Compare auction prices with market rates
- **Portfolio Tracking**: Monitor multiple properties simultaneously

## 🆘 Troubleshooting

### No Notifications Received
1. Check GitHub Actions logs for errors
2. Verify Telegram bot token and chat ID in repository secrets
3. Ensure your bot is not blocked

### Workflow Not Running
1. Check if GitHub Actions are enabled in your repository
2. Verify the cron schedule syntax
3. Check repository permissions

### Missing Data
1. The first run builds the initial database
2. Changes are only detected from the second run onwards
3. Check the `data/` directory for generated files

## 📞 Support

If you encounter issues:
1. Check the GitHub Actions logs
2. Verify your Telegram bot setup
3. Review the troubleshooting section above

## 📄 License

This project is open source and available under the MIT License.

---

**Happy Property Hunting! 🏠💰**

