#!/bin/bash
# Lelong scraper runner for VM cron job
# Runs the scraper and reloads the bot data afterward

set -e

LOGFILE="/opt/lelong-bot/scraper.log"
REPO_DIR="/opt/lelong-bot/repo"
VENV="/opt/lelong-bot/venv/bin/python"

# Load environment variables
set -a
source /opt/lelong-bot/.env
set +a

echo "$(date) - Starting scraper run..." >> "$LOGFILE"

# Run the scraper
cd "$REPO_DIR"
$VENV src/monitor.py >> "$LOGFILE" 2>&1

echo "$(date) - Scraper completed." >> "$LOGFILE"

# Restart bot to pick up fresh data
systemctl restart lelong-bot
echo "$(date) - Bot restarted with fresh data." >> "$LOGFILE"
