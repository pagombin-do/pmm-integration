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

1. Install Python 3, pip, venv, git, and openssl (if not already present)
2. Clone the repository into `/opt/pmm-integration`
3. Create a Python virtual environment and install dependencies
4. Generate a self-signed TLS certificate (valid 10 years)
5. Create and start a `pmm-integration` systemd service on port **8443**
6. Print the public HTTPS URL you can open in your browser

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

# Generate a self-signed TLS certificate
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout certs/key.pem -out certs/cert.pem \
    -days 3650 -subj "/CN=pmm-integration" \
    -addext "subjectAltName=IP:127.0.0.1,DNS:localhost"

python3 app.py
```

---

## Accessing the UI

After installation the app serves HTTPS directly on port **8443**:

```
https://<your_droplet_public_ipv4>:8443/
```

Your browser will show a certificate warning because the TLS certificate is
self-signed. This is expected and safe to accept.

> **Firewall note:** If you have a DigitalOcean Cloud Firewall or `ufw`
> enabled, ensure port **8443** (TCP) is open for inbound traffic.

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

Re-run the installer — it pulls the latest code and restarts the service.
The TLS certificate and venv are preserved unless they need rebuilding:

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
| `PORT`                    | HTTPS listen port                        | `8443`                     |
| `LISTEN_HOST`             | Bind address                             | `0.0.0.0`                 |
| `TLS_CERT_DIR`            | Directory containing cert.pem / key.pem  | `./certs`                  |
| `FLASK_DEBUG`             | Set to `1` for debug mode                | `0`                        |
| `FLASK_SECRET_KEY`        | Flask session secret                     | Random bytes               |
| `PMM_BASE_URL`            | PMM server base URL                      | `https://127.0.0.1:443`   |

To override a variable for the systemd service:

```bash
systemctl edit pmm-integration
```

Add overrides under `[Service]`, then `systemctl restart pmm-integration`.

---

## TLS Certificate

The installer generates a self-signed certificate at
`/opt/pmm-integration/certs/` with a 10-year validity. To replace it with
your own certificate:

```bash
cp /path/to/your/cert.pem /opt/pmm-integration/certs/cert.pem
cp /path/to/your/key.pem  /opt/pmm-integration/certs/key.pem
chmod 600 /opt/pmm-integration/certs/key.pem
systemctl restart pmm-integration
```

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
├── app.py                  # Flask application & API routes (serves HTTPS)
├── install.sh              # One-line installer for PMM Droplets
├── requirements.txt        # Python dependencies
├── certs/                  # TLS certificate (generated at install time)
│   ├── cert.pem
│   └── key.pem
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

- The app serves HTTPS with a self-signed certificate. Replace it with a
  proper certificate for production use, or restrict access by IP.
- Rotate API tokens periodically and use least-privilege tokens when possible.
- Restrict DigitalOcean Trusted Sources to only the PMM Droplet IP.
- Change the default PMM `admin` password immediately after deployment.
