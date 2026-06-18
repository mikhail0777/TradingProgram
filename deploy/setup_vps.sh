#!/usr/bin/env bash

# Enforce running with sudo
if [ "$EUID" -ne 0 ]; then
  echo "❌ Please run this script with sudo (e.g., sudo bash deploy/setup_vps.sh)"
  exit 1
fi

# Detect non-root user and directory
REAL_USER=${SUDO_USER:-$(whoami)}
APP_DIR=$(pwd)

echo "===================================================="
echo "      Autonomous Trading Bot VPS Setup Script       "
echo "===================================================="
echo "Detected User:      $REAL_USER"
echo "Detected Directory: $APP_DIR"
echo ""

# Prompt for Domain or IP
read -p "Enter your public Domain or IP Address (e.g. trading.yourdomain.com or 192.168.1.1): " DOMAIN_OR_IP
if [ -z "$DOMAIN_OR_IP" ]; then
    echo "❌ Domain or IP cannot be empty. Exiting."
    exit 1
fi

echo "--> Installing system packages (python3-venv, nginx, certbot)..."
apt-get update
apt-get install -y python3-pip python3-venv git nginx certbot python3-certbot-nginx

echo "--> Creating Python virtual environment..."
python3 -m venv venv
chown -R "$REAL_USER":"$REAL_USER" venv

echo "--> Installing requirements inside virtual environment..."
sudo -u "$REAL_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip
sudo -u "$REAL_USER" "$APP_DIR/venv/bin/pip" install -r requirements.txt

# Ensure .env exists
if [ ! -f .env ]; then
    echo "--> Creating default .env from .env.example..."
    sudo -u "$REAL_USER" cp .env.example .env
    echo "⚠️ Created template .env file. Please edit it later to configure API keys!"
fi

echo "--> Configuring systemd services..."
# Replace placeholders and write to /etc/systemd/system/
sed -e "s|{{USER}}|$REAL_USER|g" -e "s|{{APP_DIR}}|$APP_DIR|g" deploy/trading_bot.service > /etc/systemd/system/trading_bot.service
sed -e "s|{{USER}}|$REAL_USER|g" -e "s|{{APP_DIR}}|$APP_DIR|g" deploy/trading_dashboard.service > /etc/systemd/system/trading_dashboard.service

# Reload systemd and enable/start services
systemctl daemon-reload
systemctl enable trading-bot.service trading-dashboard.service
systemctl restart trading-bot.service trading-dashboard.service

echo "--> Configuring Nginx reverse proxy..."
sed -e "s|{{DOMAIN_OR_IP}}|$DOMAIN_OR_IP|g" deploy/nginx.conf > /etc/nginx/sites-available/trading_bot
ln -sf /etc/nginx/sites-available/trading_bot /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Reload Nginx
nginx -t && systemctl restart nginx

# Optional SSL via certbot if it looks like a domain (contains dots and alphabetic extension)
if [[ "$DOMAIN_OR_IP" =~ \.[a-zA-Z]{2,}$ ]]; then
    echo "--> Domain detected! Setting up SSL with Let's Encrypt Certbot..."
    certbot --nginx -d "$DOMAIN_OR_IP" --non-interactive --agree-tos --email "admin@$DOMAIN_OR_IP"
fi

echo ""
echo "===================================================="
echo "✅ Setup Complete!"
echo "• Bot logs can be viewed with: journalctl -u trading_bot.service -f"
echo "• UI logs can be viewed with: journalctl -u trading_dashboard.service -f"
echo "• Your dashboard is available at: http://$DOMAIN_OR_IP"
echo "===================================================="
