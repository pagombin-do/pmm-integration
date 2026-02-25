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
        host = instance["host"]
        port = instance["port"]
        username = instance.get("username", "pmm_monitor")
        return [
            "Run the following on the PMM server to grant monitoring permissions:",
            f"  apt install -y mysql-client",
            (
                f"  mysql -h {host} -P {port} -u doadmin -p --ssl-mode=REQUIRED "
                f'-e "GRANT SELECT, PROCESS, REPLICATION CLIENT ON *.* TO \'{username}\'@\'%\'; '
                f"GRANT SELECT ON performance_schema.* TO '{username}'@'%';\""
            ),
            "",
            "Note: Node Summary metrics (CPU, RAM, disk) are not available for",
            "DigitalOcean Managed MySQL because node_exporter cannot be installed",
            "on the managed host. Database metrics and query analytics will still",
            "be collected.",
        ]
