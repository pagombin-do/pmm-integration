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

    def pmm_admin_status(self, pmm_admin):
        """
        Run `pmm-admin status` and return (returncode, combined_output).
        IMPORTANT: `pmm-admin status` exits non-zero when pmm-agent is 'not set up'.
        """
        cmd = list(pmm_admin) + ["status"]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return proc.returncode, (proc.stdout or "")

    @staticmethod
    def _status_connected(status_output: str) -> bool:
        # Typical output includes: "Connected        : true"
        lo = (status_output or "").lower()
        return "connected" in lo and "true" in lo

    @staticmethod
    def _status_not_setup(status_output: str) -> bool:
        # Matches your exact output:
        # "pmm-agent is running, but not set up" + "Please run `pmm-admin config`..."
        lo = (status_output or "").lower()
        return (
            "pmm-agent is running, but not set up" in lo
            or "please run `pmm-admin config`" in lo
            or "please run 'pmm-admin config'" in lo
            or 'please run "pmm-admin config"' in lo
        )

    def ensure_pmm_client_configured(self, pmm_admin, node_name: str = "127.0.0.1"):
        """
        1) Run pmm-admin status
            - if Connected:true -> OK
            - if 'not set up' -> run pmm-admin config using password from setup screen
        2) Re-run status; require Connected:true before proceeding
        """
        if not self.password:
            return {"success": False, "message": "PMM Admin Password is required.", "output": ""}

        rc, out = self.pmm_admin_status(pmm_admin)

        if self._status_connected(out):
            return {"success": True, "output": out}

        if self._status_not_setup(out):
            # You requested this exact server-url shape:
            # https://admin:YOUR_PMM_PASSWORD@127.0.0.1:443
            server_url = self.build_server_url().rstrip("/")  # build_server_url adds '/', strip it here

            cfg_cmd = list(pmm_admin) + [
                "config",
                "--server-insecure-tls",
                f"--server-url={server_url}",
                node_name,
                "generic",
                "pmm3",
            ]

            cfg = subprocess.run(
                cfg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            cfg_out = cfg.stdout or ""

            rc2, out2 = self.pmm_admin_status(pmm_admin)
            if self._status_connected(out2):
                return {"success": True, "output": (cfg_out + "\n\n" + out2).strip()}

            return {
                "success": False,
                "message": "pmm-admin config ran, but PMM client is still not connected.",
                "output": (cfg_out + "\n\n" + out2).strip(),
            }

        return {
            "success": False,
            "message": "pmm-admin status returned an unexpected state (not connected / not set up).",
            "output": out,
        }


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
            return {
                "error": "user_exists",
                "username": username,
                "db_id": db_id,
                "db_name": db_name,
            }
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
    
        # NEW: run `pmm-admin status` first; if not set up, run `pmm-admin config ...`
        ensure = pmm.ensure_pmm_client_configured(pmm_admin)
        if not ensure.get("success"):
            return {
                "success": False,
                "message": ensure.get("message", "PMM client is not configured."),
                "output": ensure.get("output", ""),
            }
    
        server_url = pmm.build_server_url()
        cmd = self.build_pmm_add_cmd(pmm_admin, server_url, instance)
    
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, universal_newlines=True)
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
        """Remove a service from PMM.

        For postgresql and mysql the command is:
            pmm-admin remove <service-type> <service-name>
        For mongodb (future) it is just:
            pmm-admin remove <service-name>
        """
        pmm_admin = pmm.get_pmm_admin_cmd()
        if not pmm_admin:
            return {
                "success": False,
                "message": "pmm-admin not found. Install the PMM client or set PMM_ADMIN_CMD.",
            }

        if service_type in ("postgresql", "mysql"):
            cmd = pmm_admin + ["remove", service_type, service_name]
        else:
            cmd = pmm_admin + ["remove", service_name]

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
