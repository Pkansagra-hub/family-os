# Cross-Domain Stress Tool Implementation

from k1.k0_bridge.client import K0GenericClient
from k1.k0_bridge.envelope_builder import EnvelopeBuilder


class K0CrossDomainStressTool:
    def __init__(self, client: K0GenericClient, envelope_builder: EnvelopeBuilder):
        self.client = client
        self.envelope_builder = envelope_builder

    async def execute(self, domains, time_range):
        envelope = self.envelope_builder.build_query_envelope(
            "cross_domain_stress", {"domains": domains, "time_range": time_range}
        )

        response = await self.client.send_envelope(envelope)
        return response.data
