#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# PMM Integration Installer
# Downloads and installs the PMM Integration web application on a PMM server.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/pagombin-do/pmm-integration/main/install.sh | bash
#
# Or download first, then run:
#   wget https://raw.githubusercontent.com/pagombin-do/pmm-integration/main/install.sh
#   chmod +x install.sh
#   ./install.sh
# ---------------------------------------------------------------------------

set -euo pipefail

REPO_URL="https://github.com/pagombin-do/pmm-integration.git"
INSTALL_DIR="/opt/pmm-integration"
SERVICE_NAME="pmm-integration"
PORT="${PORT:-5000}"
BRANCH="main"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

info()  { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
ok()    { echo -e "\033[1;32m[OK]\033[0m    $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
fail()  { echo -e "\033[1;31m[ERROR]\033[0m $*"; exit 1; }

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || return 1
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

info "PMM Integration Installer"
echo "=============================================="

if [ "$(id -u)" -ne 0 ]; then
    fail "This installer must be run as root.  Try:  sudo bash install.sh"
fi

# ---------------------------------------------------------------------------
# Install system dependencies
# ---------------------------------------------------------------------------

info "Installing system dependencies..."

apt-get update -qq

# Python 3 + pip + venv + git
apt-get install -y -qq python3 python3-pip python3-venv git > /dev/null 2>&1
ok "System dependencies installed."

# ---------------------------------------------------------------------------
# Clone / update the repository
# ---------------------------------------------------------------------------

if [ -d "$INSTALL_DIR/.git" ]; then
    info "Existing installation found at $INSTALL_DIR — pulling latest..."
    cd "$INSTALL_DIR"
    git fetch origin "$BRANCH"
    git reset --hard "origin/$BRANCH"
else
    info "Cloning repository into $INSTALL_DIR..."
    git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

ok "Application code ready at $INSTALL_DIR"

# ---------------------------------------------------------------------------
# Python virtual environment & dependencies
# ---------------------------------------------------------------------------

info "Setting up Python virtual environment..."

python3 -m venv "$INSTALL_DIR/venv"
source "$INSTALL_DIR/venv/bin/activate"

pip install --upgrade pip -q
pip install -r "$INSTALL_DIR/requirements.txt" -q

ok "Python dependencies installed."

# ---------------------------------------------------------------------------
# systemd service
# ---------------------------------------------------------------------------

info "Creating systemd service ($SERVICE_NAME)..."

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=PMM Integration Web Application
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/app.py
Environment=PORT=$PORT
Environment=PMM_BASE_URL=https://127.0.0.1:443
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" --quiet
systemctl restart "$SERVICE_NAME"

ok "Service $SERVICE_NAME enabled and started."

# ---------------------------------------------------------------------------
# Detect public IP
# ---------------------------------------------------------------------------

PUBLIC_IP=""
PUBLIC_IP=$(curl -sf --max-time 3 http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address 2>/dev/null || true)
if [ -z "$PUBLIC_IP" ]; then
    PUBLIC_IP=$(curl -sf --max-time 3 https://api.ipify.org 2>/dev/null || true)
fi
if [ -z "$PUBLIC_IP" ]; then
    PUBLIC_IP="<your_droplet_public_ipv4>"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

echo ""
echo "=============================================="
ok "Installation complete!"
echo ""
echo "  Open the PMM Integration UI in your browser:"
echo ""
echo "    http://${PUBLIC_IP}:${PORT}"
echo ""
echo "  Service management:"
echo "    systemctl status  $SERVICE_NAME"
echo "    systemctl restart $SERVICE_NAME"
echo "    journalctl -u $SERVICE_NAME -f"
echo ""
echo "  Install directory: $INSTALL_DIR"
echo "=============================================="
