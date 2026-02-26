"""MySQL integration with Percona PMM via DigitalOcean API."""

from .base import BaseIntegration


class MySQLIntegration(BaseIntegration):
    ENGINE_FILTER = "mysql"
    DISPLAY_NAME = "MySQL"
    SUPPORTED = True

    def build_pmm_add_cmd(self, pmm_admin, server_url, instance):
        return pmm_admin + [
            "add",
            "mysql",
            f"--username={instance['username']}",
            f"--password={instance['password']}",
            f"--host={instance['host']}",
            f"--port={instance['port']}",
            f"--service-name={instance['name']}",
            "--tls",
            "--tls-skip-verify",
            f"--server-url={server_url}",
            "--server-insecure-tls",
            "--query-source=perfschema",
        ]

    def post_add_instructions(self, instance):
        return {
            "steps": [],
            "note": (
                "No additional setup is required for DigitalOcean Managed MySQL. "
                "The monitoring user created via the DO API already has the "
                "necessary permissions for PMM to collect metrics and query "
                "analytics.\n\n"
                "Node Summary metrics (CPU, RAM, disk) are not available for "
                "DigitalOcean Managed MySQL because node_exporter cannot be "
                "installed on the managed host. Database metrics and query "
                "analytics will still be collected."
            ),
        }
