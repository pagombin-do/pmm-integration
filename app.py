"""
PMM Integration Web Application
================================
Web interface for connecting DigitalOcean Managed Databases to Percona PMM.
Supports PostgreSQL and MySQL, with MongoDB planned for a future release.

Serves HTTPS directly — no reverse proxy required.
"""

import os
import logging
import socket
import ssl

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from flask import Flask, jsonify, render_template, request

from integrations import ENGINE_MAP
from integrations.base import DO_API_BASE, PmmServer

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(32))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

PMM_BASE_URL = os.environ.get("PMM_BASE_URL", "https://127.0.0.1:443")


def get_public_ipv4():
    """Detect the droplet's public IPv4 via the DO metadata service, falling
    back to an external resolver, then to the default-route interface address."""
    try:
        r = requests.get(
            "http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address",
            timeout=2,
        )
        if r.status_code == 200 and r.text.strip():
            return r.text.strip()
    except Exception:
        pass

    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200 and r.text.strip():
                return r.text.strip()
        except Exception:
            continue

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        addr = s.getsockname()[0]
        s.close()
        return addr
    except Exception:
        return "0.0.0.0"


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# API — credentials validation
# ---------------------------------------------------------------------------


@app.route("/api/validate-token", methods=["POST"])
def validate_token():
    data = request.get_json(force=True)
    token = (data.get("do_token") or "").strip()
    if not token:
        return jsonify(ok=False, message="DigitalOcean API token is required."), 400

    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{DO_API_BASE}/account", headers=headers, timeout=15)
        if r.status_code == 401:
            return jsonify(ok=False, message="Invalid DigitalOcean API token."), 401
        r.raise_for_status()
        return jsonify(ok=True)
    except requests.RequestException as exc:
        return jsonify(ok=False, message=str(exc)), 502


@app.route("/api/validate-pmm", methods=["POST"])
def validate_pmm():
    data = request.get_json(force=True)
    password = data.get("pmm_password", "")
    if not password:
        return jsonify(ok=False, message="PMM admin password is required."), 400

    pmm = PmmServer(base_url=PMM_BASE_URL, password=password)
    try:
        pmm.list_services()
        return jsonify(ok=True)
    except requests.exceptions.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 401:
            return jsonify(ok=False, message="Invalid PMM admin password."), 401
        return jsonify(ok=False, message=str(exc)), 502
    except requests.RequestException as exc:
        return jsonify(ok=False, message=f"Cannot reach PMM server at {PMM_BASE_URL}: {exc}"), 502


# ---------------------------------------------------------------------------
# API — list databases
# ---------------------------------------------------------------------------


@app.route("/api/databases", methods=["POST"])
def list_databases():
    """Return DigitalOcean managed databases filtered by engine."""
    data = request.get_json(force=True)
    token = (data.get("do_token") or "").strip()
    engine = (data.get("engine") or "").strip()
    pmm_password = data.get("pmm_password", "")
    use_private = data.get("use_private", False)

    if not token:
        return jsonify(ok=False, message="DigitalOcean API token is required."), 400

    integration_cls = ENGINE_MAP.get(engine)
    if not integration_cls:
        return jsonify(ok=False, message=f"Unsupported engine: {engine}"), 400
    if not integration_cls.SUPPORTED:
        return jsonify(ok=False, message=f"{integration_cls.DISPLAY_NAME} is not yet supported."), 400

    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{DO_API_BASE}/databases", headers=headers, timeout=15)
        r.raise_for_status()
    except requests.RequestException as exc:
        return jsonify(ok=False, message=str(exc)), 502

    all_dbs = r.json().get("databases", [])
    engine_filter = integration_cls.ENGINE_FILTER
    filtered = [d for d in all_dbs if d.get("engine") == engine_filter]

    pmm = PmmServer(base_url=PMM_BASE_URL, password=pmm_password)
    monitored_map = {}
    try:
        svcs = pmm.list_services()
        for key in ("postgresql", "mysql", "mongodb", "services"):
            val = svcs.get(key)
            if isinstance(val, list):
                for s in val:
                    if isinstance(s, dict):
                        addr = s.get("address", "")
                        port = str(s.get("port", ""))
                        if addr:
                            monitored_map[f"{addr}:{port}"] = s.get("service_name", "")
    except Exception:
        pass

    results = []
    for db in filtered:
        conn = db.get("connection", {})
        priv = db.get("private_connection", {})

        if use_private and priv.get("host"):
            host = priv["host"]
            port = priv.get("port", conn.get("port", ""))
        else:
            host = conn.get("host", "")
            port = conn.get("port", "")

        addr_key = f"{host}:{port}"
        pmm_service_name = monitored_map.get(addr_key, "")

        results.append({
            "id": db["id"],
            "name": db["name"],
            "engine": db["engine"],
            "region": db.get("region", ""),
            "host": host,
            "port": port,
            "num_nodes": db.get("num_nodes", 1),
            "status": db.get("status", "unknown"),
            "monitored": bool(pmm_service_name),
            "pmm_service_name": pmm_service_name,
        })

    return jsonify(ok=True, databases=results)


# ---------------------------------------------------------------------------
# API — create monitoring user
# ---------------------------------------------------------------------------


@app.route("/api/create-user", methods=["POST"])
def create_user():
    data = request.get_json(force=True)
    token = (data.get("do_token") or "").strip()
    db_id = data.get("db_id", "")
    db_name = data.get("db_name", "")
    engine = data.get("engine", "pg")
    username = data.get("username", "pmm_monitor")

    if not token or not db_id:
        return jsonify(ok=False, message="Missing required fields."), 400

    integration_cls = ENGINE_MAP.get(engine)
    if not integration_cls:
        return jsonify(ok=False, message=f"Unsupported engine: {engine}"), 400

    integration = integration_cls()
    try:
        result = integration.create_monitoring_user(token, db_id, db_name, username)
        if "error" in result:
            return jsonify(
                ok=False,
                error_code=result["error"],
                username=result.get("username", username),
                db_name=result.get("db_name", db_name),
                db_id=result.get("db_id", db_id),
            ), 409
        return jsonify(ok=True, username=result["username"], password=result["password"])
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 500
        msg = "HTTP error creating user."
        try:
            msg = exc.response.json().get("message", msg)
        except Exception:
            pass
        return jsonify(ok=False, message=msg), status
    except Exception as exc:
        return jsonify(ok=False, message=str(exc)), 500


# ---------------------------------------------------------------------------
# API — add database to PMM
# ---------------------------------------------------------------------------


@app.route("/api/integrate", methods=["POST"])
def integrate():
    data = request.get_json(force=True)
    pmm_password = data.get("pmm_password", "")
    engine = data.get("engine", "pg")
    instance = data.get("instance", {})

    required = ("name", "host", "port", "username", "password")
    missing = [k for k in required if not instance.get(k)]
    if missing or not pmm_password:
        return jsonify(ok=False, message=f"Missing fields: {', '.join(missing) or 'pmm_password'}"), 400

    integration_cls = ENGINE_MAP.get(engine)
    if not integration_cls:
        return jsonify(ok=False, message=f"Unsupported engine: {engine}"), 400
    if not integration_cls.SUPPORTED:
        return jsonify(ok=False, message=f"{integration_cls.DISPLAY_NAME} is not yet supported."), 400

    integration = integration_cls()
    pmm = PmmServer(base_url=PMM_BASE_URL, password=pmm_password)
    result = integration.add_to_pmm(pmm, instance)
    post_steps = integration.post_add_instructions(instance)

    return jsonify(
        ok=result["success"],
        message=result.get("message", ""),
        output=result.get("output", ""),
        post_steps=post_steps,
    )


# ---------------------------------------------------------------------------
# API — remove database from PMM
# ---------------------------------------------------------------------------


PMM_SERVICE_TYPE_MAP = {
    "pg": "postgresql",
    "postgresql": "postgresql",
    "mysql": "mysql",
    "mongodb": "mongodb",
}


@app.route("/api/remove", methods=["POST"])
def remove():
    data = request.get_json(force=True)
    pmm_password = data.get("pmm_password", "")
    service_name = data.get("service_name", "").strip()
    engine = data.get("engine", "").strip()

    if not pmm_password or not service_name or not engine:
        return jsonify(ok=False, message="Missing pmm_password, service_name, or engine."), 400

    service_type = PMM_SERVICE_TYPE_MAP.get(engine)
    if not service_type:
        return jsonify(ok=False, message=f"Unsupported engine: {engine}"), 400

    from integrations.base import BaseIntegration

    pmm = PmmServer(base_url=PMM_BASE_URL, password=pmm_password)
    result = BaseIntegration.remove_from_pmm(pmm, service_type, service_name)

    return jsonify(
        ok=result["success"],
        message=result.get("message", ""),
        output=result.get("output", ""),
    )


# ---------------------------------------------------------------------------
# API — supported engines metadata
# ---------------------------------------------------------------------------


@app.route("/api/engines", methods=["GET"])
def engines():
    info = []
    for key, cls in ENGINE_MAP.items():
        if key == cls.ENGINE_FILTER:
            info.append({
                "id": cls.ENGINE_FILTER,
                "name": cls.DISPLAY_NAME,
                "supported": cls.SUPPORTED,
            })
    return jsonify(engines=info)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8443))
    host = os.environ.get("LISTEN_HOST", "0.0.0.0")
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    public_ip = get_public_ipv4()

    cert_dir = os.environ.get("TLS_CERT_DIR", os.path.join(os.path.dirname(__file__), "certs"))
    cert_file = os.path.join(cert_dir, "cert.pem")
    key_file = os.path.join(cert_dir, "key.pem")

    ssl_ctx = None
    if os.path.isfile(cert_file) and os.path.isfile(key_file):
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(cert_file, key_file)
        proto = "https"
    else:
        log.warning("TLS certificate not found at %s — falling back to HTTP.", cert_dir)
        proto = "http"

    print(f"\n{'=' * 60}")
    print(f"  PMM Integration Web Application")
    print(f"  Listening on {host}:{port}")
    print(f"  Public URL:  {proto}://{public_ip}:{port}/")
    print(f"  Local URL:   {proto}://127.0.0.1:{port}/")
    print(f"{'=' * 60}\n")

    app.run(host=host, port=port, debug=debug, ssl_context=ssl_ctx)
