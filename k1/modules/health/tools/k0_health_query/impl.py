# Health Query Tool Implementation
# Calls K0 through generic bridge

from k1.k0_bridge.client import K0GenericClient
from k1.k0_bridge.envelope_builder import EnvelopeBuilder


class K0HealthQueryTool:
    def __init__(self, client: K0GenericClient, envelope_builder: EnvelopeBuilder):
        self.client = client
        self.envelope_builder = envelope_builder

    async def execute(self, query_type, params):
        # Build envelope using schema
        envelope = self.envelope_builder.build_query_envelope(
            "health_query", {"query_type": query_type, "params": params}
        )

        # Send via generic client
        response_envelope = await self.client.send_envelope(envelope)

        # Decode and return
        return response_envelope.data
