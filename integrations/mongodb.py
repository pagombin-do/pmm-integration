"""MongoDB integration with Percona PMM via DigitalOcean API.

Connects to the cluster using the SRV connection string, runs rs.status()
to discover each replica-set member, then adds every member individually
with pmm-admin add mongodb.
"""

import subprocess
from urllib.parse import quote_plus

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

from .base import BaseIntegration


class MongoDBIntegration(BaseIntegration):
    ENGINE_FILTER = "mongodb"
    DISPLAY_NAME = "MongoDB"
    SUPPORTED = True

    def _get_rs_members(self, srv_host, username, password):
        """Connect via SRV URI, run rs.status(), return (rs_name, members_list).

        Each member is a dict with keys 'host' and 'port'.
        """
        uri = (
            f"mongodb+srv://{quote_plus(username)}:{quote_plus(password)}"
            f"@{srv_host}/admin?tls=true&authSource=admin"
        )

        client = MongoClient(uri, serverSelectionTimeoutMS=10000)
        try:
            status = client.admin.command("replSetGetStatus")
        finally:
            client.close()

        rs_name = status.get("set", "")
        members = []
        for m in status.get("members", []):
            name = m.get("name", "")
            if ":" in name:
                h, p = name.rsplit(":", 1)
                members.append({"host": h, "port": p})
            else:
                members.append({"host": name, "port": "27017"})

        return rs_name, members

    def build_pmm_add_cmd(self, pmm_admin, server_url, instance):
        """Build the command for a single replica-set member.

        The instance dict must include 'member_host', 'member_port',
        and 'cluster' in addition to the standard fields.
        """
        member_host = instance['member_host']
        service_name = member_host.split(".")[0]

        return pmm_admin + [
            "add",
            "mongodb",
            f"--username={instance['username']}",
            f"--password={instance['password']}",
            f"--host={member_host}",
            f"--port={instance['member_port']}",
            f"--service-name={service_name}",
            f"--cluster={instance['cluster']}",
            "--enable-all-collectors",
            "--tls",
        ]

    def add_to_pmm(self, pmm, instance):
        """Discover replica-set members via rs.status() and add each one."""
        pmm_admin = pmm.get_pmm_admin_cmd()
        if not pmm_admin:
            return {
                "success": False,
                "message": "pmm-admin not found. Install the PMM client or set PMM_ADMIN_CMD.",
            }

        srv_host = instance["host"]
        username = instance["username"]
        password = instance["password"]

        try:
            rs_name, members = self._get_rs_members(srv_host, username, password)
        except (ConnectionFailure, OperationFailure) as exc:
            return {
                "success": False,
                "message": f"Could not connect to MongoDB or run rs.status(): {exc}",
            }
        except Exception as exc:
            return {
                "success": False,
                "message": f"Error discovering replica-set members: {exc}",
            }

        if not members:
            return {"success": False, "message": "rs.status() returned no members."}

        server_url = pmm.build_server_url()
        member_results = []
        all_ok = True

        for m in members:
            member_instance = {
                **instance,
                "member_host": m["host"],
                "member_port": m["port"],
                "cluster": rs_name,
            }
            cmd = self.build_pmm_add_cmd(pmm_admin, server_url, member_instance)

            try:
                out = subprocess.check_output(
                    cmd, stderr=subprocess.STDOUT, universal_newlines=True
                )
                member_results.append({
                    "member": f"{m['host']}:{m['port']}",
                    "success": True,
                    "output": out,
                })
            except subprocess.CalledProcessError as exc:
                all_ok = False
                member_results.append({
                    "member": f"{m['host']}:{m['port']}",
                    "success": False,
                    "output": exc.output,
                })
            except OSError as exc:
                all_ok = False
                member_results.append({
                    "member": f"{m['host']}:{m['port']}",
                    "success": False,
                    "output": str(exc),
                })

        combined_output = []
        combined_output.append(f"Replica set: {rs_name}")
        combined_output.append(f"Members discovered: {len(members)}")
        combined_output.append("")
        for mr in member_results:
            status = "OK" if mr["success"] else "FAILED"
            combined_output.append(f"[{status}] {mr['member']}")
            if mr["output"]:
                for line in mr["output"].strip().splitlines():
                    combined_output.append(f"  {line}")
            combined_output.append("")

        return {
            "success": all_ok,
            "message": "" if all_ok else "Some members failed to add.",
            "output": "\n".join(combined_output),
            "member_results": member_results,
        }

    def post_add_instructions(self, instance):
        return {
            "steps": [],
            "note": (
                "No additional setup is required for DigitalOcean Managed MongoDB. "
                "Each replica-set member has been added individually to PMM.\n\n"
                "Node Summary metrics (CPU, RAM, disk) are not available for "
                "DigitalOcean Managed MongoDB because node_exporter cannot be "
                "installed on the managed host. Database metrics will still "
                "be collected."
            ),
        }
