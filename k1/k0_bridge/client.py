# K0 Generic Client
# Transport-only, auth-only, retries-only
# Knows nothing about domains or queries


class K0GenericClient:
    def __init__(self, config):
        self.config = config
        # Initialize transport, auth, etc.

    async def send_envelope(self, envelope):
        # Send envelope via configured backend
        pass

    async def receive_response(self, request_id):
        # Receive response envelope
        pass
