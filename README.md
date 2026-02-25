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
curl -sSL https://raw.githubusercontent.com/pagombin-do/pmm-integration/main/install.sh | sh
```

This will:

1. Install Python 3, pip, venv, and git (if not already present)
2. Clone the repository into `/opt/pmm-integration`
3. Create a Python virtual environment and install dependencies
4. Create and start a `pmm-integration` systemd service (localhost only)
5. Configure Nginx to reverse-proxy `/integration/` to the Flask backend
6. Print the public URL you can open in your browser

### Option B — Download and Review First

```bash
wget https://raw.githubusercontent.com/pagombin-do/pmm-integration/main/install.sh
chmod +x install.sh
less install.sh
sudo ./install.sh
```

### Option C — Manual Install

```bash
git clone https://github.com/pagombin-do/pmm-integration.git /opt/pmm-integration
cd /opt/pmm-integration

python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

python3 app.py
```

---

## Accessing the UI

After installation the app is served through the **existing Nginx** that ships
with the PMM Marketplace image — no extra ports or firewall rules are needed:

```
https://<your_droplet_public_ipv4>/integration/
```

### How it works

The PMM 1-Click image already runs Nginx on ports 80/443 to serve the PMM UI.
The installer adds a small location block that proxies `/integration/` to the
Flask backend on `127.0.0.1:5000`:

```
Browser                    Nginx (443)              Flask (127.0.0.1:5000)
  │                           │                           │
  ├── GET /integration/ ─────►├── proxy_pass ────────────►├── /
  │                           │   X-Script-Name:          │
  │◄──────────────────────────┤   /integration            │
```

The Flask app never listens on a public interface — all external traffic flows
through Nginx, sharing the same TLS certificate PMM already uses.

---

## Service Management

```bash
systemctl status  pmm-integration
journalctl -u pmm-integration -f
systemctl restart pmm-integration
systemctl stop    pmm-integration
```

---

## Updating

Re-run the installer — it pulls the latest code and restarts the service:

```bash
curl -sSL https://raw.githubusercontent.com/pagombin-do/pmm-integration/main/install.sh | sh
```

Or manually:

```bash
cd /opt/pmm-integration
git pull origin main
. venv/bin/activate
pip install -r requirements.txt
systemctl restart pmm-integration
```

---

## Environment Variables

| Variable                  | Description                              | Default                    |
|---------------------------|------------------------------------------|----------------------------|
| `PORT`                    | Internal listen port                     | `5000`                     |
| `LISTEN_HOST`             | Bind address                             | `127.0.0.1`               |
| `FLASK_DEBUG`             | Set to `1` for debug mode                | `0`                        |
| `FLASK_SECRET_KEY`        | Flask session secret                     | Random bytes               |
| `PMM_BASE_URL`            | PMM server base URL                      | `https://127.0.0.1:443`   |

To override a variable for the systemd service:

```bash
systemctl edit pmm-integration
```

Add overrides under `[Service]`, then `systemctl restart pmm-integration`.

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

## Nginx Configuration Details

The installer creates two things:

1. **`/etc/nginx/pmm-integration.conf`** — a location snippet:

```nginx
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
```

2. **An `include` directive** injected into the PMM Nginx server block
   (`/etc/nginx/conf.d/pmm.conf` or equivalent) that loads the snippet above.

A backup of the original config is saved before any modification. If the
installer cannot locate the Nginx config file it will print the snippet and
ask you to include it manually.

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

- The Flask backend listens only on `127.0.0.1` — it is not directly reachable
  from the internet.  All external access goes through Nginx with TLS.
- Rotate API tokens periodically and use least-privilege tokens when possible.
- Restrict DigitalOcean Trusted Sources to only the PMM Droplet IP.
- Change the default PMM `admin` password immediately after deployment.
