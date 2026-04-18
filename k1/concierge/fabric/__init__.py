"""
k1.concierge.fabric -- Concierge fabric port surface.

P4B.7: All POC mock capabilities, the in-memory ``CapabilityRegistry``,
``POCMockBridgeAdapter``, and ``contract_converter`` were moved to
``tests/fixtures/capabilities/`` -- they are test fixtures, not production
code. The real production fabric is wired through ``k1.fabric.factory``
and ``k1.bridge`` adapters (see ``k1/kernel/service.py``).

Only the port protocol (``IFabricPort``) remains in production.
"""

from k1.concierge.fabric.ports import IFabricPort

__all__ = ["IFabricPort"]
