# Envelope Builder
# Schema-driven envelope construction
# No domain knowledge


class EnvelopeBuilder:
    def __init__(self, schema_registry):
        self.schema_registry = schema_registry

    def build_query_envelope(self, query_type, params):
        # Build envelope from schema
        pass

    def build_command_envelope(self, command_type, params):
        # Build envelope from schema
        pass
