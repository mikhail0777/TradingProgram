#!/usr/bin/env bash

echo "===================================================="
echo "          Trading Bot Deployment Update Script      "
echo "===================================================="

# Pull latest changes from git
echo "--> Pulling latest changes from Git..."
git pull

# Install/update packages
echo "--> Updating python packages inside venv..."
./venv/bin/pip install -r requirements.txt

# Restart services
echo "--> Restarting trading services..."
sudo systemctl restart trading-bot.service
sudo systemctl restart trading-dashboard.service

echo "===================================================="
echo "✅ Deployment updated successfully!"
echo "===================================================="
