"""Base class for database engine integrations with Percona PMM."""

from __future__ import print_function

import os
import subprocess
from abc import ABC, abstractmethod
from urllib.parse import quote as urlquote

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning


requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

DO_API_BASE = "https://api.digitalocean.com/v2"


class PmmServer:
    """Interact with a local PMM server via its HTTP API and pmm-admin CLI."""

    def __init__(self, base_url="https://127.0.0.1:443", password=None):
        self.base_url = base_url.rstrip("/")
        self.password = password

    def list_services(self):
        endpoint = f"{self.base_url}/v1/management/services"
        r = requests.get(endpoint, verify=False, auth=("admin", self.password))
        r.raise_for_status()
        return r.json()

    def get_pmm_admin_cmd(self):
        env_cmd = os.environ.get("PMM_ADMIN_CMD")
        if env_cmd:
            return env_cmd.split()
        try:
            subprocess.check_output(
                ["pmm-admin", "--version"],
                stderr=subprocess.STDOUT,
                universal_newlines=True,
            )
            return ["pmm-admin"]
        except (OSError, subprocess.CalledProcessError):
            return None

    def build_server_url(self):
        override = os.environ.get("PMM_SERVER_URL_OVERRIDE")
        if override:
            url = override
        else:
            pass_enc = urlquote(self.password, safe="")
            host_part = self.base_url[8:] if self.base_url.startswith("https://") else self.base_url
            url = f"https://admin:{pass_enc}@{host_part}/"
        if not url.endswith("/"):
            url += "/"
        return url


class BaseIntegration(ABC):
    """Abstract base for a DigitalOcean-managed database integration."""

    ENGINE_FILTER: str = ""
    DISPLAY_NAME: str = ""
    SUPPORTED: bool = True

    @abstractmethod
    def build_pmm_add_cmd(self, pmm_admin, server_url, instance):
        """Return the full pmm-admin add command list."""

    @abstractmethod
    def post_add_instructions(self, instance):
        """Return a list of post-add instruction strings for the user."""

    def create_monitoring_user(self, do_token, db_id, db_name, username="pmm_monitor"):
        headers = {"Authorization": f"Bearer {do_token}"}
        payload = {"name": username}
        r = requests.post(
            f"{DO_API_BASE}/databases/{db_id}/users",
            headers=headers,
            json=payload,
        )
        if r.status_code == 409:
            existing = self._get_existing_user(do_token, db_id, username)
            if existing:
                return existing
            return {"error": f"User '{username}' already exists but could not retrieve details. Reset the user password in the DO control panel."}
        r.raise_for_status()
        user = r.json()["user"]
        return {"username": user["name"], "password": user["password"]}

    def _get_existing_user(self, do_token, db_id, username):
        headers = {"Authorization": f"Bearer {do_token}"}
        try:
            r = requests.get(
                f"{DO_API_BASE}/databases/{db_id}/users/{username}",
                headers=headers,
            )
            r.raise_for_status()
            user = r.json()["user"]
            pwd = user.get("password", "")
            if pwd:
                return {"username": user["name"], "password": pwd}
            return None
        except Exception:
            return None

    def add_to_pmm(self, pmm, instance):
        pmm_admin = pmm.get_pmm_admin_cmd()
        if not pmm_admin:
            return {
                "success": False,
                "message": "pmm-admin not found. Install the PMM client or set PMM_ADMIN_CMD.",
            }

        server_url = pmm.build_server_url()
        cmd = self.build_pmm_add_cmd(pmm_admin, server_url, instance)

        try:
            out = subprocess.check_output(
                cmd, stderr=subprocess.STDOUT, universal_newlines=True
            )
            return {"success": True, "output": out}
        except subprocess.CalledProcessError as exc:
            return {
                "success": False,
                "message": f"pmm-admin failed (exit {exc.returncode})",
                "output": exc.output,
            }
        except OSError as exc:
            return {"success": False, "message": str(exc)}

    @staticmethod
    def remove_from_pmm(pmm, service_type, service_name):
        """Remove a service from PMM.  service_type is one of:
        postgresql, mysql, mongodb, proxysql, haproxy, external."""
        pmm_admin = pmm.get_pmm_admin_cmd()
        if not pmm_admin:
            return {
                "success": False,
                "message": "pmm-admin not found. Install the PMM client or set PMM_ADMIN_CMD.",
            }

        server_url = pmm.build_server_url()
        cmd = pmm_admin + [
            "remove",
            service_type,
            service_name,
            "--force",
            f"--server-url={server_url}",
            "--server-insecure-tls",
        ]

        try:
            out = subprocess.check_output(
                cmd, stderr=subprocess.STDOUT, universal_newlines=True
            )
            return {"success": True, "output": out}
        except subprocess.CalledProcessError as exc:
            return {
                "success": False,
                "message": f"pmm-admin remove failed (exit {exc.returncode})",
                "output": exc.output,
            }
        except OSError as exc:
            return {"success": False, "message": str(exc)}
