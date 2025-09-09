# 🚀 GitHub Actions Deployment Guide

This guide will help you deploy your property monitoring system to GitHub Actions for automated daily execution.

## 📋 Prerequisites

1. **GitHub Account**: You need a GitHub account
2. **Telegram Bot**: Set up a Telegram bot for notifications
3. **Basic Git Knowledge**: Ability to create repositories and push code

## 🎯 Quick Deployment (5 Minutes)

### Step 1: Create GitHub Repository

1. **Go to GitHub** and click "New Repository"
2. **Repository Name**: `property-monitor` (or any name you prefer)
3. **Visibility**: Private (recommended) or Public
4. **Initialize**: Don't initialize with README (we have our own files)
5. **Click "Create Repository"**

### Step 2: Upload Code to GitHub

**Option A: Using GitHub Web Interface (Easiest)**
1. **Download all files** from the `github_setup` folder
2. **Go to your new repository** on GitHub
3. **Click "uploading an existing file"**
4. **Drag and drop all files** from the github_setup folder
5. **Commit the files** with message "Initial property monitor setup"

**Option B: Using Git Commands**
```bash
# Clone your empty repository
git clone https://github.com/YOUR_USERNAME/property-monitor.git
cd property-monitor

# Copy all files from github_setup folder to this directory
# Then commit and push
git add .
git commit -m "Initial property monitor setup"
git push origin main
```

### Step 3: Set Up Telegram Bot

1. **Open Telegram** → Search `@BotFather`
2. **Send** `/newbot`
3. **Name**: "Property Monitor Bot"
4. **Username**: "your_property_monitor_bot" (must be unique)
5. **Copy the Bot Token** (looks like: `123456789:ABCdefGHI...`)

### Step 4: Get Your Chat ID

1. **Start a chat** with your new bot
2. **Send any message** (like "Hello")
3. **Visit this URL** in your browser (replace YOUR_BOT_TOKEN):
   ```
   https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates
   ```
4. **Find your Chat ID** (look for `"chat":{"id":` and copy the number)

### Step 5: Configure GitHub Secrets

1. **Go to your repository** on GitHub
2. **Click Settings** → **Secrets and variables** → **Actions**
3. **Click "New repository secret"**
4. **Add these secrets:**

   **Secret 1:**
   - Name: `TELEGRAM_BOT_TOKEN`
   - Value: Your bot token from Step 3

   **Secret 2:**
   - Name: `TELEGRAM_CHAT_ID`
   - Value: Your chat ID from Step 4

### Step 6: Enable GitHub Actions

1. **Go to the "Actions" tab** in your repository
2. **Click "I understand my workflows, go ahead and enable them"**
3. **You should see "Property Monitor" workflow**

### Step 7: Test the Setup

1. **Go to Actions tab** → **Click "Property Monitor"**
2. **Click "Run workflow"** → **Click the green "Run workflow" button**
3. **Wait for the workflow to complete** (should take 1-2 minutes)
4. **Check your Telegram** for a test notification!

## ✅ Verification Checklist

- [ ] Repository created and code uploaded
- [ ] Telegram bot created and tested
- [ ] GitHub Secrets configured (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
- [ ] GitHub Actions enabled
- [ ] Test workflow run successfully
- [ ] Received test notification in Telegram

## 📅 Automatic Schedule

Once set up, the system will:
- **Run daily at 9 AM Malaysia time** (1 AM UTC)
- **Check for new property listings**
- **Detect price and auction date changes**
- **Send Telegram notifications** for any changes
- **Store data persistently** in the repository

## 🔧 Customization

### Change Schedule
Edit `.github/workflows/monitor.yml`:
```yaml
schedule:
  - cron: '0 1 * * *'  # Daily at 9 AM Malaysia time
  # Change to '0 13 * * *' for 9 PM Malaysia time
  # Change to '0 1 * * 1' for weekly on Monday
```

### Add WhatsApp Notifications
Add these GitHub Secrets:
- `WHATSAPP_API_KEY`: Your WhatsApp API key
- `WHATSAPP_PHONE_NUMBER`: Your phone number

### Modify Search Criteria
Edit `src/monitor.py` and change the `lelong_url` variable to modify search parameters.

## 📊 Monitoring and Logs

### View Execution Logs
1. **Go to Actions tab** in your repository
2. **Click on any workflow run**
3. **Click on "monitor" job**
4. **View detailed logs** of the execution

### Check Generated Data
- **Property database**: `data/properties.json`
- **Change history**: `data/changes.json`
- **Reports**: `data/reports/` folder

### Download Reports
1. **Go to Actions tab** → **Click on a workflow run**
2. **Scroll down to "Artifacts"**
3. **Download "property-report-XXX"** to get the latest report

## 🆘 Troubleshooting

### No Notifications Received
1. **Check workflow logs** for errors
2. **Verify Telegram credentials** in repository secrets
3. **Test your bot** by sending a message manually
4. **Check if bot is blocked** or chat ID is wrong

### Workflow Fails
1. **Check the Actions logs** for specific error messages
2. **Verify all secrets are set correctly**
3. **Check if repository has proper permissions**

### No Property Data
1. **First run builds the initial database** (no changes detected)
2. **Changes are detected from the second run onwards**
3. **Check if the scraping logic needs updates**

## 🔒 Security Notes

- **Keep your bot token secret** - never share it publicly
- **Use private repository** if you want to keep your monitoring private
- **GitHub Secrets are encrypted** and safe to use
- **Regularly check your bot's activity** in Telegram

## 📞 Support

If you encounter issues:
1. **Check the GitHub Actions logs** first
2. **Verify your Telegram bot setup**
3. **Review this deployment guide**
4. **Check the main README.md** for additional information

---

**🎉 Congratulations! Your automated property monitoring system is now running on GitHub Actions!**

You'll receive daily notifications about new auction properties and any changes to existing listings. The system runs completely automatically - no manual intervention required!

