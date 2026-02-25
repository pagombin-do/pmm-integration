"""PostgreSQL integration with Percona PMM via DigitalOcean API."""

from .base import BaseIntegration


class PostgreSQLIntegration(BaseIntegration):
    ENGINE_FILTER = "pg"
    DISPLAY_NAME = "PostgreSQL"
    SUPPORTED = True

    def build_pmm_add_cmd(self, pmm_admin, server_url, instance):
        return pmm_admin + [
            "add",
            "postgresql",
            f"--username={instance['username']}",
            f"--password={instance['password']}",
            f"--host={instance['host']}",
            f"--port={instance['port']}",
            f"--service-name={instance['name']}",
            "--database=defaultdb",
            "--auto-discovery-limit=-1",
            "--tls",
            "--tls-skip-verify",
            f"--server-url={server_url}",
            "--server-insecure-tls",
            "--query-source=pgstatements",
        ]

    def post_add_instructions(self, instance):
        host = instance["host"]
        port = instance["port"]
        username = instance.get("username", "pmm_monitor")
        return [
            "Run the following on the PMM server to enable query analytics:",
            f'  apt install -y postgresql-client',
            (
                f'  psql "host={host} port={port} dbname=defaultdb user=doadmin sslmode=require" '
                f'-c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements; '
                f"GRANT SELECT ON pg_stat_statements TO {username}; "
                f'GRANT pg_read_all_stats TO {username};"'
            ),
            "",
            "Note: Node Summary metrics (CPU, RAM, disk) are not available for",
            "DigitalOcean Managed PostgreSQL because node_exporter cannot be",
            "installed on the managed host. Database metrics and query analytics",
            "will still be collected.",
        ]
