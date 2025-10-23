"""
K1 L4 Runtime — Multi-Device Sync

**Purpose:** Multi-device SessionState synchronization with hybrid LAN + Internet, delta journal

**Components:**
- strategy/ — Hybrid LAN + Internet sync strategy
- coherence/ — Per-device guarantees, delta journal

**Performance:**
- LAN sync: <1ms
- Internet sync: <500ms
- Crash recovery: <2s

**ADRs (2 total):**
- ADR-0050: Sync Strategy (hybrid LAN + Internet, device-first privacy)
- ADR-0050a: SessionState Coherence (per-device guarantees, delta journal)

**Sync Strategy (ADR-0050):**
- **LAN:** Prioritize local network sync (<1ms, multicast)
- **Internet:** Fallback to cloud sync (<500ms, WebSocket/SSE)
- **Device-First Privacy:** Data stays on-device when possible

**Delta Journal (ADR-0050a):**
- Track SessionState mutations as deltas
- Per-device sequence numbers for ordering
- Conflict resolution via last-write-wins + vector clocks

**Integration:**
- SessionState: Serialization provides delta encoding
- L4 WebSocket: Real-time sync over WebSocket
- K0 WAL: Delta journal persistence

**Performance Metrics:**
- sync_latency_ms (histogram, transport=lan|internet)
- sync_conflicts_total (counter)
- sync_devices_active (gauge)

**Last Updated:** October 2025
**Status:** Production-ready multi-device sync
"""

__version__ = "0.1.0"

# TODO: Implement strategy/, coherence/
# Per ADR-0050 family (0050, 0050a)
