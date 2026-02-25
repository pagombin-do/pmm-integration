#!/bin/sh
# ---------------------------------------------------------------------------
# PMM Integration Installer
# Downloads and installs the PMM Integration web application on a PMM server.
# Configures Nginx to reverse-proxy /integration/ to the Flask backend so the
# app is reachable at https://<droplet_ip>/integration/ with no extra ports.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/pagombin-do/pmm-integration/main/install.sh | sh
#
# Or download first, then run:
#   wget https://raw.githubusercontent.com/pagombin-do/pmm-integration/main/install.sh
#   chmod +x install.sh
#   ./install.sh
# ---------------------------------------------------------------------------

set -eu

REPO_URL="https://github.com/pagombin-do/pmm-integration.git"
INSTALL_DIR="/opt/pmm-integration"
SERVICE_NAME="pmm-integration"
PORT="${PORT:-5000}"
BRANCH="main"
NGINX_SNIPPET="/etc/nginx/pmm-integration.conf"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

info()  { printf '\033[1;34m[INFO]\033[0m  %s\n' "$*"; }
ok()    { printf '\033[1;32m[OK]\033[0m    %s\n' "$*"; }
warn()  { printf '\033[1;33m[WARN]\033[0m  %s\n' "$*"; }
fail()  { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

info "PMM Integration Installer"
echo "=============================================="

if [ "$(id -u)" -ne 0 ]; then
    fail "This installer must be run as root.  Try:  sudo sh install.sh"
fi

# ---------------------------------------------------------------------------
# Install system dependencies
# ---------------------------------------------------------------------------

info "Installing system dependencies..."

apt-get update -qq

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
. "$INSTALL_DIR/venv/bin/activate"

pip install --upgrade pip -q
pip install -r "$INSTALL_DIR/requirements.txt" -q

ok "Python dependencies installed."

# ---------------------------------------------------------------------------
# systemd service (listens on 127.0.0.1 only — Nginx proxies to it)
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
Environment=LISTEN_HOST=127.0.0.1
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
# Nginx reverse-proxy configuration
# ---------------------------------------------------------------------------

info "Configuring Nginx reverse proxy at /integration/ ..."

# Create the location snippet that will be included inside the server block
cat > "$NGINX_SNIPPET" <<'NGINX'
# PMM Integration reverse proxy — managed by install.sh
location /integration/ {
    proxy_pass         http://127.0.0.1:5000/;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Real-IP         $remote_addr;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
    proxy_set_header   X-Script-Name     /integration;
    proxy_http_version 1.1;
    proxy_read_timeout 90s;
}
NGINX

ok "Created Nginx snippet at $NGINX_SNIPPET"

# Find the Nginx config file that contains the PMM server block and inject
# an include directive if one does not already exist.
NGINX_CONF=""
for candidate in \
    /etc/nginx/conf.d/pmm.conf \
    /etc/nginx/conf.d/default.conf \
    /etc/nginx/nginx.conf; do
    if [ -f "$candidate" ]; then
        NGINX_CONF="$candidate"
        break
    fi
done

if [ -z "$NGINX_CONF" ]; then
    warn "Could not find an Nginx config file. Add the following manually"
    warn "inside your Nginx server block:"
    warn "  include $NGINX_SNIPPET;"
else
    if grep -qF "pmm-integration.conf" "$NGINX_CONF" 2>/dev/null; then
        ok "Nginx config already includes pmm-integration snippet."
    else
        info "Injecting include into $NGINX_CONF ..."
        cp "$NGINX_CONF" "${NGINX_CONF}.bak.$(date +%s)"

        # Insert the include directive just before the first server block's
        # closing brace.  We look for lines that have a location block or
        # that close the server block and inject before the final '}'.
        # Strategy: insert 'include ...' on the line before the LAST '}'.
        #
        # Using awk: find the last line that is just '}' (server-block close)
        # and insert the include directive before it.
        awk -v snippet="$NGINX_SNIPPET" '
        {
            lines[NR] = $0
        }
        END {
            last_brace = 0
            for (i = NR; i >= 1; i--) {
                if (lines[i] ~ /^[[:space:]]*\}[[:space:]]*$/) {
                    last_brace = i
                    break
                }
            }
            for (i = 1; i <= NR; i++) {
                if (i == last_brace) {
                    printf "    include %s;\n", snippet
                }
                print lines[i]
            }
        }
        ' "$NGINX_CONF" > "${NGINX_CONF}.tmp"

        mv "${NGINX_CONF}.tmp" "$NGINX_CONF"
        ok "Injected include into $NGINX_CONF"
    fi

    # Validate and reload
    if nginx -t 2>/dev/null; then
        nginx -s reload
        ok "Nginx configuration valid — reloaded."
    else
        warn "Nginx configuration test failed. Check with: nginx -t"
        warn "A backup of the original config was saved."
    fi
fi

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
echo "    https://${PUBLIC_IP}/integration/"
echo ""
echo "  The app is served through Nginx on the same port as PMM."
echo "  No extra firewall rules are needed."
echo ""
echo "  Service management:"
echo "    systemctl status  $SERVICE_NAME"
echo "    systemctl restart $SERVICE_NAME"
echo "    journalctl -u $SERVICE_NAME -f"
echo ""
echo "  Install directory: $INSTALL_DIR"
echo "  Nginx snippet:     $NGINX_SNIPPET"
echo "=============================================="
