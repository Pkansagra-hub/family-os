---
adr_number: 0020d
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_date: null
implementation_phase: 'Phase 1 (Foundation)'
implementation_status: PLANNING
authors:
- K1 Architecture Team
title: LOCAL COLD Tier (L1a K1 SQLite) - Edge-First Offline-Safe Archive
affected_layers:
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k1.sessionstate.archive
- k1.sessionstate.sync
concerns:
- architecture
- cost
- observability
- performance
- privacy
- reliability
- scalability
- testing
propagation:
  affected_adrs:
  - ADR-0017
  - ADR-0018
  - ADR-0019
  - ADR-0020
  - ADR-0020a
  - ADR-0020b
  affected_tests:
  - tests/k1/sessionstate/test_local_cold.py
  - tests/k1/sessionstate/test_archive_sync.py
  triggers:
  - LOCAL COLD capacity changes
  - Reconstruction SLA changes
  - Async K0 sync policy changes
  - Offline-first behavior modifications
related_adrs:
- ADR-0017
- ADR-0017a
- ADR-0017d
- ADR-0018
- ADR-0018b
- ADR-0018c
- ADR-0019
- ADR-0020
- ADR-0020a
- ADR-0020b
- ADR-0020c
related_contracts:
- k1/contracts/sessionstate/archive_schema.json
- k1/contracts/sessionstate/sync_protocol.json
related_diagrams: []
research_citations:
- 'SQLite as Application File Format (SQLite.org, 2023)'
- 'Offline-First Web Applications (A List Apart, 2018)'
- 'CRDT-based Sync (Ditto, 2025)'
superseded_by: []
supersedes: []
---

# ADR-0020d: LOCAL COLD Tier (L1a K1 SQLite) - Edge-First Offline-Safe Archive

**Status:** ACCEPTED
**Date:** 2025-11-03
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0020 (Multi-Tier Storage)](0020-multi-tier-storage.md)
**Category:** Storage (Layer 5) - Local Archive Tier
**Related ADRs:**
- [ADR-0017 (SessionState 12-Section Design)](../03-layer2-orchestration/0017-sessionstate-6-section-design/0017.md)
- [ADR-0018 (3-Tier Eviction Strategy)](../05-layer4-runtime/0018-3-tier-eviction-strategy/0018.md)
- [ADR-0020a (Hot Tier - L1 RAM)](0020a-hot-tier-l1-ram-in-memory-management.md)
- [ADR-0020b (Warm Tier - L2 SSD)](0020b-warm-tier-l2-ssd-k0-wal-storage.md)
- [ADR-0020c (Cold Tier - L3 S3)](0020c-cold-tier-l3-object-s3-archive.md)

---

## Context

### Problem Statement

The existing ADR-0020 Multi-Tier Storage architecture defines 3 tiers:

| Tier | Storage | Network Required | Latency |
|------|---------|------------------|---------|
| L1 HOT | K1 RAM | No | <1ms |
| L2 WARM | K0 WAL (SSD) | **Yes** (K0 Bridge) | <50ms |
| L3 COLD | K0 S3 Object | **Yes** (K0 Bridge) | <500ms |

**Critical Gap:** Both L2 WARM and L3 COLD require K0 network connectivity. This creates a **single point of failure** for edge-first operation:

1. **No Offline Archive:** When K0 is unreachable, evicted WARM tier data is LOST
2. **Reconstruction Blocked:** SessionState recovery requires K0 access (network-dependent)
3. **Edge-First Violation:** K1 cannot operate fully offline as designed

**SessionState eviction path requires LOCAL COLD:**

```
HOT (K1 RAM 96KB)
    ↓ pressure threshold
WARM (K1 RAM - evictable sections)
    ↓ hard eviction at 128KB
LOCAL COLD (K1 SQLite - MISSING!)  ← THIS ADR FILLS THE GAP
    ↓ async sync when K0 available
K0 WARM (K0 WAL)
    ↓ 30-day retention
K0 COLD (K0 S3)
```

### Key Requirements

1. **Offline-First:** K1 must operate without K0 connectivity indefinitely
2. **Reconstruction SLA:** <50ms to reconstruct archived section (no network)
3. **WARM Section Storage:** Archive `beliefs_history`, `history_recent`, `persona`, `telemetry`
4. **Async K0 Sync:** Sync to K0 WARM when connectivity available (non-blocking)
5. **Capacity Management:** Local SQLite bounded (100MB default, configurable)

---

## Decision

We will implement **LOCAL COLD Tier (L1a K1 SQLite)** as an **edge-local archive** between K1 RAM and K0 WARM:

### Storage Tier Architecture (Updated)

| **Tier** | **Location** | **Storage** | **Network** | **Latency** | **Capacity** | **Use Case** |
|----------|--------------|-------------|-------------|-------------|--------------|--------------|
| **L1 HOT** | K1 (edge) | RAM (Python dict) | No | <1ms | 96KB/session | Active SessionState |
| **L1a LOCAL COLD** | K1 (edge) | **SQLite** | **No** | **<10ms** | **100MB total** | **Evicted WARM sections** |
| **L2 WARM** | K0 (cloud) | WAL (SSD) | Yes | <50ms | 100MB | SessionState recovery |
| **L3 COLD** | K0 (cloud) | S3 Object | Yes | <500ms | Unlimited | Long-term archive |

### SQLite Tables

```sql
-- K1 LOCAL COLD SQLite schema

-- Archived beliefs (evicted from beliefs_history WARM section)
CREATE TABLE st_beliefs_archive (
    session_id TEXT NOT NULL,
    belief_id TEXT NOT NULL,
    fact_key TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    source TEXT NOT NULL,           -- 'explicit', 'inferred', 'imported'
    confidence REAL NOT NULL,       -- 0.0-1.0
    created_at TEXT NOT NULL,       -- ISO8601
    evicted_at TEXT NOT NULL,       -- When moved to LOCAL COLD
    synced_to_k0 INTEGER DEFAULT 0, -- 0=pending, 1=synced
    PRIMARY KEY (session_id, belief_id)
);

-- Archived turn history (evicted from history_recent WARM section)
CREATE TABLE st_history_archive (
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    role TEXT NOT NULL,             -- 'user', 'assistant', 'system', 'tool'
    content_summary TEXT NOT NULL,  -- Compressed/summarized (not full content)
    intent TEXT,
    tool_calls TEXT,                -- JSON array of tool_call_ids
    created_at TEXT NOT NULL,
    evicted_at TEXT NOT NULL,
    synced_to_k0 INTEGER DEFAULT 0,
    PRIMARY KEY (session_id, turn_id)
);

-- Archived narrative events (evicted from narrative_active HOT section under pressure)
CREATE TABLE st_narrative_archive (
    session_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,       -- 'scene_change', 'topic_shift', 'emotion_peak'
    description TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    evicted_at TEXT NOT NULL,
    synced_to_k0 INTEGER DEFAULT 0,
    PRIMARY KEY (session_id, event_id)
);

-- Archived telemetry (evicted from telemetry WARM section)
CREATE TABLE st_telemetry_archive (
    session_id TEXT NOT NULL,
    metric_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,      -- 'ttft_ms', 'e2e_ms', 'token_count'
    value REAL NOT NULL,
    labels TEXT,                    -- JSON key-value pairs
    recorded_at TEXT NOT NULL,
    evicted_at TEXT NOT NULL,
    synced_to_k0 INTEGER DEFAULT 0,
    PRIMARY KEY (session_id, metric_id)
);

-- Sync queue for async K0 uploads
CREATE TABLE st_sync_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,       -- 'st_beliefs_archive', etc.
    session_id TEXT NOT NULL,
    record_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    retry_count INTEGER DEFAULT 0,
    last_error TEXT
);

-- Indexes for efficient queries
CREATE INDEX idx_beliefs_session ON st_beliefs_archive(session_id);
CREATE INDEX idx_beliefs_sync ON st_beliefs_archive(synced_to_k0) WHERE synced_to_k0 = 0;
CREATE INDEX idx_history_session ON st_history_archive(session_id);
CREATE INDEX idx_history_turn ON st_history_archive(session_id, turn_number);
CREATE INDEX idx_sync_queue_pending ON st_sync_queue(created_at) WHERE retry_count < 3;
```

### Performance Targets (P95)

| Operation | Target | Rationale |
|-----------|--------|-----------|
| `archive_section(session_id, section)` | <10ms | SQLite INSERT (local disk) |
| `reconstruct_section(session_id, section)` | **<50ms** | SQLite SELECT + deserialize (no network) |
| `reconstruct_full_session(session_id)` | **<100ms** | All sections from SQLite |
| `sync_to_k0(batch)` | <500ms | Async batch upload (non-blocking) |
| **Capacity** | **100MB** | ~2000 sessions archived |

### Reconstruction SLA Comparison

| Tier | Latency | Network Required | Offline-Safe |
|------|---------|------------------|--------------|
| L1 HOT (RAM) | <1ms | No | Yes |
| **L1a LOCAL COLD (SQLite)** | **<50ms** | **No** | **Yes** |
| L2 WARM (K0 WAL) | <50ms | Yes | No |
| L3 COLD (K0 S3) | <500ms | Yes | No |

---

## Implementation

### LocalColdTier Class

```python
# k1/sessionstate/archive/local_cold.py
"""LOCAL COLD Tier - Edge-First Offline-Safe Archive"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ArchiveConfig:
    """Configuration for LOCAL COLD tier"""
    db_path: Path = Path("~/.k1/sessionstate/archive.db").expanduser()
    max_capacity_mb: int = 100
    sync_batch_size: int = 100
    sync_interval_seconds: int = 300  # 5 minutes


class LocalColdTier:
    """
    LOCAL COLD tier for edge-first SessionState archival.

    Features:
    - SQLite-based local storage (no network dependency)
    - <50ms reconstruction SLA
    - Async sync to K0 when available
    - Bounded capacity with LRU eviction
    """

    def __init__(self, config: Optional[ArchiveConfig] = None):
        self.config = config or ArchiveConfig()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database with schema"""
        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(
            str(self.config.db_path),
            isolation_level=None,  # Autocommit
            check_same_thread=False
        )
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._create_tables()

    def _create_tables(self) -> None:
        """Create archive tables if not exist"""
        # Tables defined in Decision section above
        pass  # Implementation follows schema above

    async def archive_beliefs(
        self,
        session_id: str,
        beliefs: List[Dict[str, Any]]
    ) -> int:
        """
        Archive evicted beliefs to LOCAL COLD.

        Args:
            session_id: Session identifier
            beliefs: List of belief records from beliefs_history

        Returns:
            Number of beliefs archived
        """
        evicted_at = datetime.utcnow().isoformat()
        cursor = self.conn.executemany(
            """
            INSERT OR REPLACE INTO st_beliefs_archive
            (session_id, belief_id, fact_key, fact_value, source,
             confidence, created_at, evicted_at, synced_to_k0)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            [
                (session_id, b["belief_id"], b["fact_key"], b["fact_value"],
                 b["source"], b["confidence"], b["created_at"], evicted_at)
                for b in beliefs
            ]
        )
        # Queue for async K0 sync
        self._queue_for_sync("st_beliefs_archive", session_id,
                             [b["belief_id"] for b in beliefs])
        return len(beliefs)

    async def reconstruct_beliefs(
        self,
        session_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Reconstruct archived beliefs for session.

        SLA: <50ms (no network)

        Args:
            session_id: Session identifier
            limit: Maximum beliefs to retrieve

        Returns:
            List of belief records
        """
        cursor = self.conn.execute(
            """
            SELECT belief_id, fact_key, fact_value, source,
                   confidence, created_at, evicted_at
            FROM st_beliefs_archive
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, limit)
        )
        return [
            {
                "belief_id": row[0],
                "fact_key": row[1],
                "fact_value": row[2],
                "source": row[3],
                "confidence": row[4],
                "created_at": row[5],
                "evicted_at": row[6],
            }
            for row in cursor.fetchall()
        ]

    async def archive_history(
        self,
        session_id: str,
        turns: List[Dict[str, Any]]
    ) -> int:
        """Archive evicted turn history to LOCAL COLD"""
        evicted_at = datetime.utcnow().isoformat()
        cursor = self.conn.executemany(
            """
            INSERT OR REPLACE INTO st_history_archive
            (session_id, turn_id, turn_number, role, content_summary,
             intent, tool_calls, created_at, evicted_at, synced_to_k0)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            [
                (session_id, t["turn_id"], t["turn_number"], t["role"],
                 t.get("content_summary", ""), t.get("intent"),
                 json.dumps(t.get("tool_calls", [])), t["created_at"], evicted_at)
                for t in turns
            ]
        )
        self._queue_for_sync("st_history_archive", session_id,
                             [t["turn_id"] for t in turns])
        return len(turns)

    async def reconstruct_history(
        self,
        session_id: str,
        limit: int = 40
    ) -> List[Dict[str, Any]]:
        """
        Reconstruct archived turn history for session.

        SLA: <50ms (no network)
        Supports 40-turn policy: returns most recent 40 turns from archive.
        """
        cursor = self.conn.execute(
            """
            SELECT turn_id, turn_number, role, content_summary,
                   intent, tool_calls, created_at, evicted_at
            FROM st_history_archive
            WHERE session_id = ?
            ORDER BY turn_number DESC
            LIMIT ?
            """,
            (session_id, limit)
        )
        return [
            {
                "turn_id": row[0],
                "turn_number": row[1],
                "role": row[2],
                "content_summary": row[3],
                "intent": row[4],
                "tool_calls": json.loads(row[5]) if row[5] else [],
                "created_at": row[6],
                "evicted_at": row[7],
            }
            for row in cursor.fetchall()
        ]

    def _queue_for_sync(
        self,
        table_name: str,
        session_id: str,
        record_ids: List[str]
    ) -> None:
        """Queue records for async K0 sync"""
        created_at = datetime.utcnow().isoformat()
        self.conn.executemany(
            """
            INSERT INTO st_sync_queue (table_name, session_id, record_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            [(table_name, session_id, rid, created_at) for rid in record_ids]
        )
```

### Async K0 Sync Manager

```python
# k1/sessionstate/sync/k0_sync_manager.py
"""Async K0 Sync Manager - Non-blocking sync to K0 WARM tier"""

import asyncio
import logging
from typing import Optional
from datetime import datetime

from k1.sessionstate.archive.local_cold import LocalColdTier
from k1.connectors.k0_bridge import K0Bridge

logger = logging.getLogger(__name__)


class K0SyncManager:
    """
    Manages async sync from LOCAL COLD to K0 WARM tier.

    Behavior:
    - Runs every 5 minutes (configurable)
    - Non-blocking (background task)
    - Retries with exponential backoff
    - Continues operating if K0 unreachable
    """

    def __init__(
        self,
        local_cold: LocalColdTier,
        k0_bridge: Optional[K0Bridge] = None,
        sync_interval_seconds: int = 300
    ):
        self.local_cold = local_cold
        self.k0_bridge = k0_bridge
        self.sync_interval = sync_interval_seconds
        self._running = False

    async def start(self) -> None:
        """Start async sync background task"""
        self._running = True
        asyncio.create_task(self._sync_loop())
        logger.info("K0SyncManager started (interval=%ds)", self.sync_interval)

    async def stop(self) -> None:
        """Stop async sync background task"""
        self._running = False
        logger.info("K0SyncManager stopped")

    async def _sync_loop(self) -> None:
        """Background sync loop"""
        while self._running:
            try:
                await self._sync_batch()
            except Exception as e:
                logger.warning("K0 sync failed (will retry): %s", e)
            await asyncio.sleep(self.sync_interval)

    async def _sync_batch(self) -> int:
        """
        Sync a batch of pending records to K0.

        Returns:
            Number of records synced
        """
        if not self.k0_bridge or not self.k0_bridge.is_connected():
            logger.debug("K0 unreachable, skipping sync")
            return 0

        # Get pending sync items
        cursor = self.local_cold.conn.execute(
            """
            SELECT id, table_name, session_id, record_id
            FROM st_sync_queue
            WHERE retry_count < 3
            ORDER BY created_at
            LIMIT ?
            """,
            (self.local_cold.config.sync_batch_size,)
        )
        pending = cursor.fetchall()

        if not pending:
            return 0

        synced_count = 0
        for item in pending:
            item_id, table_name, session_id, record_id = item
            try:
                # Fetch record from local archive
                record = await self._fetch_record(table_name, session_id, record_id)
                if record:
                    # Upload to K0 WARM
                    await self.k0_bridge.upload_archive_record(
                        table_name, session_id, record
                    )
                    # Mark as synced
                    self.local_cold.conn.execute(
                        f"UPDATE {table_name} SET synced_to_k0 = 1 "
                        f"WHERE session_id = ? AND {self._pk_column(table_name)} = ?",
                        (session_id, record_id)
                    )
                    # Remove from queue
                    self.local_cold.conn.execute(
                        "DELETE FROM st_sync_queue WHERE id = ?",
                        (item_id,)
                    )
                    synced_count += 1
            except Exception as e:
                # Increment retry count
                self.local_cold.conn.execute(
                    "UPDATE st_sync_queue SET retry_count = retry_count + 1, "
                    "last_error = ? WHERE id = ?",
                    (str(e), item_id)
                )

        if synced_count > 0:
            logger.info("Synced %d records to K0", synced_count)
        return synced_count

    def _pk_column(self, table_name: str) -> str:
        """Get primary key column for table"""
        pk_map = {
            "st_beliefs_archive": "belief_id",
            "st_history_archive": "turn_id",
            "st_narrative_archive": "event_id",
            "st_telemetry_archive": "metric_id",
        }
        return pk_map.get(table_name, "id")

    async def _fetch_record(
        self,
        table_name: str,
        session_id: str,
        record_id: str
    ) -> Optional[dict]:
        """Fetch record from local archive by ID"""
        pk_col = self._pk_column(table_name)
        cursor = self.local_cold.conn.execute(
            f"SELECT * FROM {table_name} WHERE session_id = ? AND {pk_col} = ?",
            (session_id, record_id)
        )
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return None
```

---

## Eviction Integration

When ADR-0018 3-Tier Eviction triggers WARM section eviction:

### Eviction Flow

```
SessionState (HOT 48KB + WARM 48KB = 96KB)
              ↓
         [Pressure: >85%]
              ↓
         Tier 1: SOFT EVICTION
         - Compress telemetry (WARM)
         - Summarize history_recent (WARM)
              ↓
         [Pressure: >100%]
              ↓
         Tier 2: HARD EVICTION
         - Evict beliefs_history → LOCAL COLD (this ADR)
         - Evict persona → LOCAL COLD (this ADR)
         - Evict history_recent (compressed) → LOCAL COLD (this ADR)
              ↓
         [Async: K0 Available]
              ↓
         K0SyncManager syncs LOCAL COLD → K0 WARM
```

### Integration with SessionStateManager

```python
# k1/sessionstate/manager.py (excerpt)

async def _evict_to_local_cold(self, section: str) -> None:
    """Evict WARM section to LOCAL COLD tier"""
    session_id = self._current_session_id

    if section == "beliefs_history":
        beliefs = self._state.beliefs_history.to_archive_format()
        await self.local_cold.archive_beliefs(session_id, beliefs)
        self._state.beliefs_history.clear()

    elif section == "history_recent":
        turns = self._state.history_recent.to_archive_format()
        await self.local_cold.archive_history(session_id, turns)
        self._state.history_recent.clear()

    elif section == "persona":
        # Persona archived as beliefs with source='persona'
        persona_beliefs = self._state.persona.to_belief_format()
        await self.local_cold.archive_beliefs(session_id, persona_beliefs)
        self._state.persona.clear()

    logger.info("Evicted %s to LOCAL COLD", section)
```

---

## Consequences

### Positive

1. **Edge-First Compliance:** K1 operates fully offline (no K0 dependency for eviction/reconstruction)
2. **Fast Reconstruction:** <50ms SLA (local SQLite vs <500ms network to K0)
3. **Data Durability:** Evicted data survives K0 outages
4. **Async Sync:** Non-blocking K0 sync when available

### Negative

1. **Local Storage Requirement:** 100MB additional disk on edge device
2. **Sync Complexity:** Conflict resolution needed if K0 has different version
3. **Capacity Bounded:** 100MB limit requires LRU eviction within LOCAL COLD

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| SQLite corruption | WAL mode + periodic VACUUM + backup |
| Disk full | LRU eviction within LOCAL COLD (oldest unsynced first) |
| Sync conflicts | K0 timestamp wins (server authority) |
| Stale data | Sync queue TTL (7 days max pending) |

---

## Final Decision

**LOCAL COLD Tier (L1a K1 SQLite)** is ACCEPTED as the edge-first offline-safe archive tier between K1 RAM and K0 WARM.

### Key Properties

| Property | Value |
|----------|-------|
| **Tier ID** | L1a LOCAL COLD |
| **Storage** | K1 SQLite (local disk) |
| **Network** | No (edge-only) |
| **Latency** | <10ms write, <50ms read |
| **Capacity** | 100MB (configurable) |
| **Sections Archived** | beliefs_history, history_recent, persona, telemetry, narrative (under pressure) |
| **Sync to K0** | Async, 5-minute interval, non-blocking |
| **Offline-Safe** | Yes (primary design goal) |

### Updated Storage Tier Hierarchy

```
L1 HOT      (K1 RAM)        <1ms     96KB    Active SessionState
L1a LOCAL   (K1 SQLite)     <50ms    100MB   Evicted WARM sections (OFFLINE-SAFE)
L2 WARM     (K0 WAL)        <50ms    100MB   SessionState recovery (network)
L3 COLD     (K0 S3)         <500ms   ∞       Long-term archive (network)
```

---

## Related ADRs

- **ADR-0017:** SessionState 12-Section Design (defines HOT/WARM sections)
- **ADR-0018:** 3-Tier Eviction Strategy (defines when to evict to LOCAL COLD)
- **ADR-0020:** Multi-Tier Storage (parent ADR, defines L1/L2/L3)
- **ADR-0020a:** Hot Tier L1 RAM (eviction source)
- **ADR-0020b:** Warm Tier L2 K0 WAL (sync destination)
- **ADR-0020c:** Cold Tier L3 S3 (long-term archive)

---

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| SQLite schema | PLANNING | Tables defined above |
| LocalColdTier class | PLANNING | Core archival logic |
| K0SyncManager | PLANNING | Async sync to K0 |
| SessionStateManager integration | PLANNING | Eviction hook |
| Tests | PLANNING | Unit + integration |
