"""Bridge Multi-Device Family Sync Module.

This module implements LAN-first device sync with P2P internet fallback.
Per ADR-0050c: Multi-Device Family Sync Strategy.

Phase 1 (M2-M3): LAN Sync
    - mDNS device discovery
    - CRDT merge with LWW
    - E2EE (AES256-GCM)
    - Device certificates (ED25519)

Phase 2 (M4-M5): P2P Internet Sync
    - Direct P2P tunnels
    - NAT traversal
    - Zero intermediary

All sync operations route through K0 P07 Sync/CRDT pipeline.
"""

from __future__ import annotations

from .local_outbox import LocalOutbox, OutboxQueueEntry

# Phase 1 sync components (planned -- not yet implemented).
# These will be real imports once the sync modules are built (MS-6):
#   from .certificates import CertificateManager
#   from .crdt import CRDTMerge
#   from .discovery import DeviceDiscovery
#   from .e2ee import E2EEncryption
#   from .sync_port import ISyncPort, SyncPortImpl

__all__ = [
    "LocalOutbox",
    "OutboxQueueEntry",
]
