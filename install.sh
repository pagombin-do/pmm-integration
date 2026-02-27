#!/bin/sh
# ---------------------------------------------------------------------------
# PMM Integration Installer
#
# Safe to run multiple times.  On each invocation the script:
#   - detects whether a previous installation exists
#   - stops the running service before touching code or dependencies
#   - pulls the latest code (or re-clones if the repo is corrupt)
#   - rebuilds the venv only when Python or requirements change
#   - generates a self-signed TLS certificate (if one does not exist)
#   - writes / updates the systemd unit idempotently
#   - performs a health check after starting the service
#
# The app serves HTTPS directly on port 8443 — no Nginx required.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/pagombin-do/pmm-integration/main/install.sh | sh
# ---------------------------------------------------------------------------

set -eu

REPO_URL="https://github.com/pagombin-do/pmm-integration.git"
INSTALL_DIR="/opt/pmm-integration"
SERVICE_NAME="pmm-integration"
PORT="${PORT:-8443}"
BRANCH="add-pmm-config-support"
CERT_DIR="$INSTALL_DIR/certs"
VERSION_FILE="$INSTALL_DIR/.installed-version"
VENV_DIR="$INSTALL_DIR/venv"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

info()  { printf '\033[1;34m[INFO]\033[0m  %s\n' "$*"; }
ok()    { printf '\033[1;32m[OK]\033[0m    %s\n' "$*"; }
warn()  { printf '\033[1;33m[WARN]\033[0m  %s\n' "$*"; }
fail()  { printf '\033[1;31m[ERROR]\033[0m %s\n' "$*"; exit 1; }

service_is_active() {
    systemctl is-active "$SERVICE_NAME" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

info "PMM Integration Installer"
echo "=============================================="

if [ "$(id -u)" -ne 0 ]; then
    fail "This installer must be run as root.  Try:  sudo sh install.sh"
fi

INSTALL_MODE="fresh"
PREV_COMMIT=""
if [ -f "$VERSION_FILE" ]; then
    INSTALL_MODE="upgrade"
    PREV_COMMIT=$(cat "$VERSION_FILE" 2>/dev/null || true)
    info "Previous installation detected (${PREV_COMMIT:-unknown version})."
fi

# ---------------------------------------------------------------------------
# Stop the running service before we touch anything
# ---------------------------------------------------------------------------

if service_is_active; then
    info "Stopping running $SERVICE_NAME service..."
    systemctl stop "$SERVICE_NAME"
    ok "Service stopped."
fi

# ---------------------------------------------------------------------------
# System dependencies — skip apt-get if everything is already present
# ---------------------------------------------------------------------------

NEED_APT=false
for cmd in python3 git openssl; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        NEED_APT=true
        break
    fi
done

if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
    NEED_APT=true
fi

if [ "$NEED_APT" = true ]; then
    info "Installing system dependencies..."
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv git openssl > /dev/null 2>&1
    ok "System dependencies installed."
else
    ok "System dependencies already present — skipped."
fi

# ---------------------------------------------------------------------------
# Firewall — open the HTTPS port
# ---------------------------------------------------------------------------

if command -v ufw >/dev/null 2>&1; then
    if ufw status 2>/dev/null | grep -q "Status: active"; then
        if ufw status | grep -q "${PORT}/tcp"; then
            ok "Firewall already allows port ${PORT}/tcp — skipped."
        else
            info "Opening port ${PORT}/tcp in ufw..."
            ufw allow "${PORT}/tcp" >/dev/null
            ok "Firewall rule added: allow ${PORT}/tcp."
        fi
    else
        ok "ufw is not active — no firewall rule needed."
    fi
else
    ok "ufw not installed — skipping firewall configuration."
fi

# ---------------------------------------------------------------------------
# Clone / update the repository
# ---------------------------------------------------------------------------

repo_healthy() {
    [ -d "$INSTALL_DIR/.git" ] && \
    git -C "$INSTALL_DIR" rev-parse --git-dir >/dev/null 2>&1
}

if [ -d "$INSTALL_DIR" ] && ! repo_healthy; then
    warn "Repository at $INSTALL_DIR appears corrupt — removing and re-cloning."
    rm -rf "$INSTALL_DIR"
fi

if [ -d "$INSTALL_DIR/.git" ]; then
    info "Updating code from $BRANCH..."
    cd "$INSTALL_DIR"
    git fetch origin "$BRANCH" --depth 1
    git reset --hard "origin/$BRANCH"
    git clean -fdx --exclude=venv --exclude=certs --exclude=.installed-version --exclude=.requirements-hash
else
    info "Cloning repository into $INSTALL_DIR..."
    git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

NEW_COMMIT=$(git -C "$INSTALL_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
ok "Application code at commit $NEW_COMMIT"

if [ "$INSTALL_MODE" = "upgrade" ] && [ "$PREV_COMMIT" = "$NEW_COMMIT" ]; then
    info "Code is already at $NEW_COMMIT — no new changes."
fi

# ---------------------------------------------------------------------------
# Python virtual environment — rebuild only when necessary
# ---------------------------------------------------------------------------

venv_healthy() {
    [ -x "$VENV_DIR/bin/python3" ] && \
    "$VENV_DIR/bin/python3" -c "import flask" >/dev/null 2>&1
}

SYSTEM_PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "")
VENV_PY_VER=""
if [ -x "$VENV_DIR/bin/python3" ]; then
    VENV_PY_VER=$("$VENV_DIR/bin/python3" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "")
fi

REBUILD_VENV=false

if [ ! -d "$VENV_DIR" ]; then
    REBUILD_VENV=true
    info "No virtual environment found — creating."
elif [ "$SYSTEM_PY_VER" != "$VENV_PY_VER" ]; then
    REBUILD_VENV=true
    warn "Python version changed ($VENV_PY_VER -> $SYSTEM_PY_VER) — rebuilding venv."
elif ! venv_healthy; then
    REBUILD_VENV=true
    warn "Virtual environment appears broken — rebuilding."
fi

if [ "$REBUILD_VENV" = true ]; then
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

. "$VENV_DIR/bin/activate"

REQ_HASH=$(md5sum "$INSTALL_DIR/requirements.txt" 2>/dev/null | awk '{print $1}' || echo "none")
PREV_REQ_HASH=""
if [ -f "$INSTALL_DIR/.requirements-hash" ]; then
    PREV_REQ_HASH=$(cat "$INSTALL_DIR/.requirements-hash" 2>/dev/null || echo "")
fi

if [ "$REBUILD_VENV" = true ] || [ "$REQ_HASH" != "$PREV_REQ_HASH" ]; then
    info "Installing Python dependencies..."
    pip install --upgrade pip -q
    pip install -r "$INSTALL_DIR/requirements.txt" -q
    printf '%s' "$REQ_HASH" > "$INSTALL_DIR/.requirements-hash"
    ok "Python dependencies installed."
else
    ok "Python dependencies unchanged — skipped."
fi

# ---------------------------------------------------------------------------
# TLS certificate — generate a self-signed cert if none exists
# ---------------------------------------------------------------------------

CERT_FILE="$CERT_DIR/cert.pem"
KEY_FILE="$CERT_DIR/key.pem"

if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    ok "TLS certificate already exists — skipped."
else
    info "Generating self-signed TLS certificate..."
    mkdir -p "$CERT_DIR"

    PUBLIC_IP_FOR_CERT=$(curl -sf --max-time 3 http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address 2>/dev/null || true)
    if [ -z "$PUBLIC_IP_FOR_CERT" ]; then
        PUBLIC_IP_FOR_CERT=$(curl -sf --max-time 3 https://api.ipify.org 2>/dev/null || true)
    fi

    SAN_ENTRY=""
    if [ -n "$PUBLIC_IP_FOR_CERT" ]; then
        SAN_ENTRY="IP:${PUBLIC_IP_FOR_CERT},"
    fi

    openssl req -x509 -newkey rsa:2048 -nodes \
        -keyout "$KEY_FILE" \
        -out "$CERT_FILE" \
        -days 3650 \
        -subj "/CN=pmm-integration" \
        -addext "subjectAltName=${SAN_ENTRY}IP:127.0.0.1,DNS:localhost" \
        2>/dev/null

    chmod 600 "$KEY_FILE"
    ok "Self-signed TLS certificate generated (valid 10 years)."
fi

# ---------------------------------------------------------------------------
# systemd service
# ---------------------------------------------------------------------------

UNIT_CONTENTS="[Unit]
Description=PMM Integration Web Application
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/app.py
Environment=PORT=$PORT
Environment=LISTEN_HOST=0.0.0.0
Environment=TLS_CERT_DIR=$CERT_DIR
Environment=PMM_BASE_URL=https://127.0.0.1:443
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target"

UNIT_CHANGED=false
if [ -f "$UNIT_FILE" ]; then
    EXISTING_UNIT=$(cat "$UNIT_FILE")
    if [ "$EXISTING_UNIT" != "$UNIT_CONTENTS" ]; then
        UNIT_CHANGED=true
        info "Updating systemd unit file (contents changed)..."
    else
        ok "systemd unit file unchanged — skipped."
    fi
else
    UNIT_CHANGED=true
    info "Creating systemd unit file..."
fi

if [ "$UNIT_CHANGED" = true ]; then
    printf '%s\n' "$UNIT_CONTENTS" > "$UNIT_FILE"
    systemctl daemon-reload
    ok "systemd unit file written and daemon reloaded."
fi

systemctl enable "$SERVICE_NAME" --quiet 2>/dev/null || true

# ---------------------------------------------------------------------------
# Start service and health check
# ---------------------------------------------------------------------------

info "Starting $SERVICE_NAME service..."
systemctl start "$SERVICE_NAME"

HEALTHY=false
TRIES=0
MAX_TRIES=10
while [ "$TRIES" -lt "$MAX_TRIES" ]; do
    TRIES=$((TRIES + 1))
    sleep 1
    if curl -skf -o /dev/null "https://127.0.0.1:${PORT}/api/engines" 2>/dev/null; then
        HEALTHY=true
        break
    fi
done

if [ "$HEALTHY" = true ]; then
    ok "Service is running and responding (checked after ${TRIES}s)."
else
    warn "Service started but did not respond within ${MAX_TRIES}s."
    warn "Check logs with:  journalctl -u $SERVICE_NAME --no-pager -n 30"
fi

# ---------------------------------------------------------------------------
# Record installed version
# ---------------------------------------------------------------------------

printf '%s' "$NEW_COMMIT" > "$VERSION_FILE"

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
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "=============================================="
if [ "$INSTALL_MODE" = "upgrade" ]; then
    if [ "$PREV_COMMIT" = "$NEW_COMMIT" ]; then
        ok "Re-install complete (already at $NEW_COMMIT — no code changes)."
    else
        ok "Upgrade complete ($PREV_COMMIT -> $NEW_COMMIT)."
    fi
else
    ok "Fresh installation complete (version $NEW_COMMIT)."
fi
echo ""
echo "  Open the PMM Integration UI in your browser:"
echo ""
echo "    https://${PUBLIC_IP}:${PORT}/"
echo ""
echo "  The browser will show a certificate warning because the TLS"
echo "  certificate is self-signed. This is safe to accept."
echo ""
echo "  Service management:"
echo "    systemctl status  $SERVICE_NAME"
echo "    systemctl restart $SERVICE_NAME"
echo "    journalctl -u $SERVICE_NAME -f"
echo ""
echo "  Install directory: $INSTALL_DIR"
echo "  TLS certificate:   $CERT_DIR/"
echo "=============================================="
