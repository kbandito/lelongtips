#!/bin/bash
# Setup script for Lelong Property Bot on a VM
# Run: bash deploy/setup.sh

set -e

echo "=== Lelong Property Bot - VM Setup ==="

# Install required system packages
echo "Installing system dependencies..."
sudo apt-get update && sudo apt-get install -y git python3 python3-pip python3-venv

# Setup directory
APP_DIR="/opt/lelong-bot"
sudo mkdir -p "$APP_DIR"
sudo chown "$USER:$USER" "$APP_DIR"

# Clone or update repo
if [ -d "$APP_DIR/repo" ]; then
    echo "Updating repository..."
    cd "$APP_DIR/repo" && git pull origin main
else
    echo "Cloning repository..."
    git clone https://github.com/kbandito/lelongtips.git "$APP_DIR/repo"
fi

# Create virtual environment
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install -r "$APP_DIR/repo/src/requirements.txt"

# Create .env file if it doesn't exist
ENV_FILE="$APP_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "Creating .env file..."
    cat > "$ENV_FILE" << 'ENVEOF'
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
GITHUB_REPO=kbandito/lelongtips
GITHUB_BRANCH=main
ENVEOF
    echo ""
    echo "IMPORTANT: Edit $ENV_FILE with your actual credentials:"
    echo "  nano $ENV_FILE"
    echo ""
fi

# Install systemd service
echo "Installing systemd service..."
sudo cp "$APP_DIR/repo/deploy/lelong-bot.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable lelong-bot
echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit credentials:  nano $ENV_FILE"
echo "  2. Start the bot:     sudo systemctl start lelong-bot"
echo "  3. Check status:      sudo systemctl status lelong-bot"
echo "  4. View logs:         journalctl -u lelong-bot -f"
