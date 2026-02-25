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
- PMM client (`pmm-admin`) installed on the PMM server
- Python 3.9+

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

The UI is available at **http://localhost:5000**.

### Environment Variables

| Variable                  | Description                              | Default                    |
|---------------------------|------------------------------------------|----------------------------|
| `PORT`                    | HTTP listen port                         | `5000`                     |
| `FLASK_DEBUG`             | Set to `1` for debug mode                | `0`                        |
| `FLASK_SECRET_KEY`        | Flask session secret                     | Random bytes               |
| `PMM_BASE_URL`            | PMM server base URL                      | `https://127.0.0.1:443`   |
| `DIGITALOCEAN_API_TOKEN`  | Pre-set DO token (skip UI prompt)        | —                          |
| `PMM_ADMIN_PASSWORD`      | Pre-set PMM password (skip UI prompt)    | —                          |

## Production Deployment

```bash
gunicorn app:app --bind 0.0.0.0:5000 --workers 2
```

## How It Works

1. **Credentials** — Enter your DigitalOcean API token and PMM admin password.
2. **Engine** — Select the database engine (PostgreSQL or MySQL).
3. **Databases** — The app queries the DO API and lists your managed databases.
4. **Monitoring User** — Create a `pmm_monitor` user automatically via the DO API,
   or provide existing credentials.
5. **Integrate** — The app runs `pmm-admin add` with TLS and query analytics enabled.

After integration, follow the post-integration steps shown in the UI to grant
the necessary monitoring permissions on each database.

## Architecture

```
workspace/
├── app.py                  # Flask application & API routes
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
