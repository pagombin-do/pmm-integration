# PMM Integration — DigitalOcean Managed Databases

Web application for connecting DigitalOcean Managed Databases to
[Percona Monitoring and Management (PMM)](https://www.percona.com/software/database-tools/percona-monitoring-and-management).

## Supported Engines

| Engine     | Status        |
|------------|---------------|
| PostgreSQL | Supported     |
| MySQL      | Supported     |
| MongoDB    | Coming Soon   |

## Prerequisites

- A DigitalOcean account with an API token (write permissions recommended)
- A running PMM 3.x server (deployed via the
  [DigitalOcean 1-Click image](https://marketplace.digitalocean.com/apps/percona-monitoring-and-management))
- PMM client (`pmm-admin`) installed and registered on the PMM server
- Python 3.9+

---

## Installation

### Option A — One-Line Install (recommended)

SSH into your PMM Droplet as root and run:

```bash
curl -sSL https://raw.githubusercontent.com/pagombin-do/pmm-integration/main/install.sh | bash
```

This will:

1. Install Python 3, pip, venv, and git (if not already present)
2. Clone the repository into `/opt/pmm-integration`
3. Create a Python virtual environment and install dependencies
4. Create and start a `pmm-integration` systemd service on port **5000**
5. Print the public URL you can open in your browser

### Option B — Download and Review First

```bash
wget https://raw.githubusercontent.com/pagombin-do/pmm-integration/main/install.sh
chmod +x install.sh
# review the script
less install.sh
# run it
sudo ./install.sh
```

### Option C — Manual Install

```bash
# Clone the repo
git clone https://github.com/pagombin-do/pmm-integration.git /opt/pmm-integration
cd /opt/pmm-integration

# Create venv and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start the application
python3 app.py
```

---

## Accessing the UI

After installation the app listens on **`0.0.0.0:5000`** — accessible on the
Droplet's public IPv4 address:

```
http://<your_droplet_public_ipv4>:5000
```

The startup log will print the detected public IP automatically:

```
============================================================
  PMM Integration Web Application
  Listening on 0.0.0.0:5000
  Public URL:  http://203.0.113.42:5000
  Local URL:   http://127.0.0.1:5000
============================================================
```

> **Firewall note:** If you have a DigitalOcean Cloud Firewall or `ufw`
> enabled, ensure port **5000** (TCP) is open for inbound traffic from your
> IP address.

---

## Service Management

When installed via the install script, the app runs as a systemd service:

```bash
# Check status
systemctl status pmm-integration

# View live logs
journalctl -u pmm-integration -f

# Restart after config changes
systemctl restart pmm-integration

# Stop
systemctl stop pmm-integration
```

---

## Updating

SSH into the PMM Droplet and re-run the installer — it will pull the latest
code and restart the service:

```bash
curl -sSL https://raw.githubusercontent.com/pagombin-do/pmm-integration/main/install.sh | bash
```

Or manually:

```bash
cd /opt/pmm-integration
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
systemctl restart pmm-integration
```

---

## Environment Variables

| Variable                  | Description                              | Default                    |
|---------------------------|------------------------------------------|----------------------------|
| `PORT`                    | HTTP listen port                         | `5000`                     |
| `FLASK_DEBUG`             | Set to `1` for debug mode                | `0`                        |
| `FLASK_SECRET_KEY`        | Flask session secret                     | Random bytes               |
| `PMM_BASE_URL`            | PMM server base URL                      | `https://127.0.0.1:443`   |
| `DIGITALOCEAN_API_TOKEN`  | Pre-set DO token (skip UI prompt)        | —                          |
| `PMM_ADMIN_PASSWORD`      | Pre-set PMM password (skip UI prompt)    | —                          |

To override a variable for the systemd service, edit the unit file:

```bash
systemctl edit pmm-integration
```

Add overrides under `[Service]`, for example:

```ini
[Service]
Environment=PORT=8080
```

Then `systemctl restart pmm-integration`.

---

## How It Works

1. **Credentials** — Enter your DigitalOcean API token and PMM admin password.
   Both are validated against their respective APIs before proceeding.
2. **Engine** — Select the database engine (PostgreSQL, MySQL, or see MongoDB
   as "Coming Soon").  Optionally toggle the private (VPC) endpoint.
3. **Databases** — The app queries the DO API and lists your managed databases
   for the chosen engine.  Already-monitored databases are flagged.
4. **Monitoring User** — Create a `pmm_monitor` user automatically via the DO
   API (requires write-permission token), or provide existing credentials.
5. **Integrate** — The app runs `pmm-admin add` with TLS and query analytics
   enabled.  Post-integration steps are displayed so you can grant the
   necessary monitoring permissions on each database.

---

## Architecture

```
/opt/pmm-integration/
├── app.py                  # Flask application & API routes
├── install.sh              # One-line installer for PMM Droplets
├── requirements.txt        # Python dependencies
├── integrations/
│   ├── __init__.py         # Engine registry
│   ├── base.py             # PmmServer + BaseIntegration ABC
│   ├── postgresql.py       # PostgreSQL integration
│   ├── mysql.py            # MySQL integration
│   └── mongodb.py          # MongoDB placeholder
├── templates/
│   └── index.html          # Main HTML template
└── static/
    ├── css/style.css       # Application styles
    └── js/app.js           # Frontend logic
```

---

## Security Considerations

- The web UI transmits your DO API token and PMM password to the backend over
  the network.  In production, place the app behind a TLS reverse proxy
  (nginx, Caddy) or restrict access by IP with a firewall.
- Rotate API tokens periodically and use least-privilege tokens when possible.
- Restrict DigitalOcean Trusted Sources to only the PMM Droplet IP.
- Change the default PMM `admin` password immediately after deployment.
