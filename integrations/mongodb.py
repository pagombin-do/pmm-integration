"""MongoDB integration placeholder — not yet supported."""

from .base import BaseIntegration


class MongoDBIntegration(BaseIntegration):
    ENGINE_FILTER = "mongodb"
    DISPLAY_NAME = "MongoDB"
    SUPPORTED = False

    def build_pmm_add_cmd(self, pmm_admin, server_url, instance):
        raise NotImplementedError("MongoDB integration is not yet supported.")

    def post_add_instructions(self, instance):
        return ["MongoDB integration is not yet supported. Stay tuned for future updates."]
