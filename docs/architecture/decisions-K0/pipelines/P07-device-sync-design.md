# P07 Device Sync Pipeline - Design Specification

**Pipeline ID:** P07_DEVICE_SYNC
**Phase:** K0 Phase 2 (Multi-Device Sync)
**Status:** DESIGN
**Date:** 2025-11-18
**Owner:** K0 Architecture Team

**Related ADRs:**
- ADR-0050: Multi-Device Family Sync Strategy (Parent)
- ADR-0050a: SessionState Coherence Guarantees (Per-Device)
- ADR-0050b: CRDT Device-to-Device Merge Protocol
- ADR-0050c: LAN-First Sync Implementation (Phase 1)
- ADR-0050d: P2P E2EE Internet Sync (Phase 2)

---

## Executive Summary

P07_DEVICE_SYNC is the K0 pipeline responsible for syncing family memories and state across multiple devices using CRDT merge with LWW (Last-Write-Wins) conflict resolution. The pipeline operates in two phases:
- **Phase 1 (M2-M3):** LAN-first sync using mDNS discovery + TCP
- **Phase 2 (M4-M5):** P2P E2EE internet sync with automatic LAN fallback

The design is **table-agnostic** and can sync from any K0 table (hippocampus events, relationships, embeddings, etc.) using a pluggable data source architecture.

---

## Architecture Overview

### System Context

```
┌─────────────────────────────────────────────────────────┐
│             K0 Microkernel (Per Device)                  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ P07_DEVICE_SYNC Pipeline                          │  │
│  │                                                    │  │
│  │ ┌─────────────────────────────────────────────┐  │  │
│  │ │ Phase 1: LAN Sync (M2-M3)                   │  │  │
│  │ │ • mDNS Discovery                            │  │  │
│  │ │ • TCP P07 Sync Channel                      │  │  │
│  │ │ • CRDT Merge (LWW + Vector Clocks)          │  │  │
│  │ └─────────────────────────────────────────────┘  │  │
│  │                                                    │  │
│  │ ┌─────────────────────────────────────────────┐  │  │
│  │ │ Phase 2: Internet Sync (M4-M5)              │  │  │
│  │ │ • P2P E2EE Tunnels                          │  │  │
│  │ │ • Automatic LAN Preference                  │  │  │
│  │ │ • Network Detection                         │  │  │
│  │ └─────────────────────────────────────────────┘  │  │
│  │                                                    │  │
│  │ ┌─────────────────────────────────────────────┐  │  │
│  │ │ Pluggable Data Sources (Table-Agnostic)     │  │  │
│  │ │ • st_hipp_events (Phase 1 MVP)              │  │  │
│  │ │ • st_relationships                          │  │  │
│  │ │ • st_embedding_queue                        │  │  │
│  │ │ • st_retention_policy                       │  │  │
│  │ │ • st_wal (future)                           │  │  │
│  │ │ • st_cognitive_traces (future)              │  │  │
│  │ └─────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  Syncs via:                                             │
│  • K0 Bus: cognitive.device.sync.requested.v1          │
│  • K0 Syscalls: device_sync_read/write capabilities     │
│  • K0 Drivers: SyncCoordinator (local TCP/QUIC)        │
└─────────────────────────────────────────────────────────┘

                        ↓ ↑
              (mDNS/TCP/E2EE Tunnel)
                        ↓ ↑

┌─────────────────────────────────────────────────────────┐
│           Other Family Devices (Same Architecture)       │
│  • iPhone-mom, laptop-dad, tablet-kid, etc.             │
│  • Each runs full K0 with P07_DEVICE_SYNC               │
│  • CRDT merge ensures eventual consistency              │
└─────────────────────────────────────────────────────────┘
```

---

## Pipeline Specification

### Contract Definition

**Pipeline YAML Contract:** `k0/contracts/pipelines/p07_device_sync.yaml`

```yaml
pipeline_id: P07_DEVICE_SYNC
version: "1.0.0"
description: "Device-to-device sync for family memories using CRDT merge"
phase: 2  # Multi-device sync

# Bus Topics
declared_topics:
  - cognitive.device.sync.requested.v1      # Manual sync trigger
  - cognitive.device.discovered.v1          # mDNS peer discovery
  - cognitive.device.state_change.v1        # Device online/offline

exit_topics:
  - cognitive.device.sync.completed.v1      # Sync finished
  - cognitive.device.sync.failed.v1         # Sync error
  - cognitive.device.conflict.detected.v1   # CRDT merge conflict

# Syscall Capabilities (Least-Privilege)
required_caps:
  # Authentication & Trust
  - st_device_trust.read           # Verify peer devices
  - st_device_trust.write          # Add/revoke trusted devices
  - st_device_pairing_requests.read
  - st_device_pairing_requests.write
  - device_keys.read               # Sign handshakes

  # Data Source Access (read-only for sync)
  - st_hipp_events.read
  - st_relationships.read
  - st_embedding_queue.read
  - st_retention_policy.read

  # Sync Coordination (write for merge)
  - st_sync_state.write
  - st_sync_state.read
  - st_vector_clock.write
  - st_vector_clock.read

  # Conflict Resolution
  - st_sync_conflicts.write

  # Outbox for cross-device messages
  - st_outbox.write

# Runtime Configuration
concurrency: 1  # Sequential sync (avoid race conditions)
max_queue: 128  # Bounded backlog
backpressure_strategy: SHED_OLDEST  # Drop old sync requests if queue full

# Performance Budgets
sla:
  p95_latency_ms: 50   # LAN sync
  p99_latency_ms: 200  # Internet sync
  throughput_rps: 10   # 10 sync operations/sec per device

# Configuration Schema
config_schema:
  sync_interval_ms:
    type: integer
    default: 5000  # 5 seconds continuous sync
    description: "Interval between automatic sync attempts"

  discovery_interval_ms:
    type: integer
    default: 60000  # 1 minute
    description: "mDNS broadcast interval"

  data_sources:
    type: array
    description: "List of tables to sync (pluggable)"
    default:
      - table: st_hipp_events
        enabled: true
        priority: 1
        sync_strategy: INCREMENTAL  # Only changes since last sync
        batch_size: 100

      - table: st_relationships
        enabled: true
        priority: 2
        sync_strategy: FULL  # Full table sync (small size)
        batch_size: 50

      - table: st_embedding_queue
        enabled: false  # Phase 2
        priority: 3
        sync_strategy: INCREMENTAL
        batch_size: 50

  crdt_config:
    conflict_resolution: LWW  # Last-Write-Wins
    vector_clock_enabled: true
    device_id_ordering: ALPHABETICAL  # Canonical tiebreaker

  network:
    phase_1_lan:
      mdns_enabled: true
      tcp_port: 9000
      discovery_timeout_ms: 2000
      require_tls: true  # Always use TLS even on LAN

    phase_2_internet:
      e2ee_enabled: false  # Phase 2 only
      quic_enabled: false  # Phase 2 only
      fallback_to_lan: true

  # Authentication & Trust
  authentication:
    require_mutual_auth: true
    challenge_timeout_ms: 5000
    session_key_rotation_hours: 24
    cert_renewal_days: 90

  trust_store:
    pairing_request_ttl_minutes: 10
    auto_revoke_inactive_days: 180
    require_approval_for_pairing: true
```

---

## Pipeline Stages (Module Architecture)

P07 is composed of **8 declarative modules** following K0 pipeline architecture:

### Stage 10: Device Discovery (M01 - device_discovery)
**Module:** `k0/modules/sync/device_discovery.py`
**Contract:** `k0/contracts/modules/sync.device_discovery.v1.yaml`

**Purpose:** Discover **AUTHORIZED** family devices on LAN (Phase 1) or internet (Phase 2)

**Input:** `cognitive.device.sync.requested.v1` or periodic trigger
**Output:** List of discovered **TRUSTED** peer devices with connection metadata

**⚠️ SECURITY NOTE:** Discovery is **two-phase**:
1. **Broadcast Discovery:** Find devices on network (unauthenticated)
2. **Trust Verification:** Validate device is in family trust store

**Logic:**
```python
async def run(message, context, **config):
    """
    M01: Device Discovery (with Trust Verification)

    Phase 1: mDNS broadcast + trust verification
    Phase 2: P2P directory service (encrypted) + trust verification

    Security Model:
    - mDNS discovers ANY FamilyOS device on network
    - Trust verification filters to ONLY family devices
    - Prevents unauthorized sync with stranger devices

    Returns:
        List of TRUSTED peer devices:
        {
            "device_id": "iphone-mom",
            "ip_address": "192.168.1.100",
            "port": 9000,
            "capabilities": ["sync", "crdt", "e2ee"],
            "last_seen": 1700000000,
            "online": true,
            "network_type": "LAN",  # or "INTERNET"
            "trust_status": "VERIFIED",
            "family_id": "family-abc123",
            "public_key_fingerprint": "sha256:abcd1234..."
        }
    """

    # Step 1: Discover all FamilyOS devices on network (unauthenticated)
    if config["phase_1_lan"]["mdns_enabled"]:
        # mDNS discovery (RFC 6762)
        discovered = await discover_via_mdns(
            service_type="_familyos._tcp.local.",
            timeout_ms=config["phase_1_lan"]["discovery_timeout_ms"]
        )
    else:
        # Phase 2: P2P E2EE directory
        discovered = await discover_via_p2p_directory()

    # Step 2: Filter to ONLY trusted family devices
    trusted_peers = []
    for peer in discovered:
        # Verify device is in family trust store
        trust_status = await verify_device_trust(
            context,
            device_id=peer["device_id"],
            family_id=context.family_id,
            public_key_fingerprint=peer.get("public_key_fingerprint")
        )

        if trust_status == "VERIFIED":
            peer["trust_status"] = "VERIFIED"
            peer["family_id"] = context.family_id
            trusted_peers.append(peer)
        else:
            logger.warning(
                f"Discovered device {peer['device_id']} but NOT in trust store - ignoring",
                extra={"peer_id": peer["device_id"], "trust_status": trust_status}
            )

    return {
        "discovered_peers": trusted_peers,
        "discovery_method": "mdns" if config["phase_1_lan"]["mdns_enabled"] else "p2p",
        "peer_count": len(trusted_peers),
        "untrusted_count": len(discovered) - len(trusted_peers)
    }


async def verify_device_trust(context, device_id, family_id, public_key_fingerprint):
    """
    Verify device is in family trust store.

    Checks:
    1. Device ID in st_device_trust table
    2. Family ID matches
    3. Public key fingerprint matches (if provided)
    4. Trust status is ACTIVE (not REVOKED)

    Returns: "VERIFIED", "NOT_FOUND", "REVOKED", "FAMILY_MISMATCH"
    """

    trust_record = await context.syscalls.query_device_trust(
        device_id=device_id,
        family_id=family_id,
        capability="st_device_trust.read"
    )

    if not trust_record:
        return "NOT_FOUND"

    if trust_record["family_id"] != family_id:
        return "FAMILY_MISMATCH"

    if trust_record["trust_status"] == "REVOKED":
        return "REVOKED"

    if public_key_fingerprint and trust_record["public_key_fingerprint"] != public_key_fingerprint:
        return "KEY_MISMATCH"

    return "VERIFIED"
```

---

### Stage 20: Connection Establishment (M02 - connection_manager)
**Module:** `k0/modules/sync/connection_manager.py`
**Contract:** `k0/contracts/modules/sync.connection_manager.v1.yaml`

**Purpose:** Establish **AUTHENTICATED** TCP (Phase 1) or E2EE tunnel (Phase 2) to peer devices

**Input:** List of **TRUSTED** peers from M01
**Output:** Active **AUTHENTICATED** connection handles for each peer

**⚠️ SECURITY NOTE:** All connections use **mutual TLS authentication**:
- Each device has Ed25519 signing key (from provisioning)
- Handshake includes challenge-response authentication
- Connection rejected if authentication fails

**Logic:**
```python
async def run(message, context, **config):
    """
    M02: Connection Manager (with Mutual Authentication)

    Establishes AUTHENTICATED sync channels to trusted peers.
    Uses challenge-response handshake to prevent MITM attacks.

    Authentication Flow:
    1. TCP/TLS connection established
    2. Device A sends: {device_id, challenge, signature}
    3. Device B verifies signature against trust store public key
    4. Device B responds: {device_id, challenge_response, signature}
    5. Device A verifies response
    6. Connection authenticated ✅

    Returns:
        Active AUTHENTICATED connections:
        {
            "iphone-mom": SyncChannel(
                socket=...,
                handshake_complete=True,
                authenticated=True,
                peer_public_key="...",
                session_key="..."
            ),
            "laptop-dad": SyncChannel(...)
        }
    """

    discovered_peers = message["discovered_peers"]
    connections = {}

    for peer in discovered_peers:
        try:
            # Phase 1: TCP connection with TLS
            if peer["network_type"] == "LAN":
                conn = await establish_tcp_connection(
                    ip=peer["ip_address"],
                    port=peer["port"],
                    timeout_ms=config["phase_1_lan"]["discovery_timeout_ms"],
                    use_tls=True  # Always use TLS even on LAN
                )
            else:
                # Phase 2: E2EE tunnel (QUIC + TLS 1.3)
                conn = await establish_e2ee_tunnel(
                    peer_device_id=peer["device_id"],
                    peer_public_key=peer["public_key_fingerprint"]
                )

            # ===================================================================
            # AUTHENTICATION HANDSHAKE (Challenge-Response)
            # ===================================================================

            # Step 1: Generate challenge
            challenge = os.urandom(32)  # 256-bit random challenge

            # Step 2: Sign handshake with our device private key
            handshake_payload = {
                "device_id": context.device_id,
                "family_id": context.family_id,
                "challenge": challenge.hex(),
                "vector_clock": await get_vector_clock(context),
                "capabilities": ["sync", "crdt"],
                "timestamp": time.time_ms()
            }

            signature = await sign_with_device_key(
                context,
                payload=handshake_payload,
                key_type="ed25519"
            )

            handshake_payload["signature"] = signature

            # Step 3: Send handshake
            await conn.send_handshake(handshake_payload)

            # Step 4: Receive peer's handshake response
            peer_handshake = await conn.receive_handshake(timeout_ms=5000)

            # Step 5: Verify peer's signature against trust store
            peer_public_key = await get_peer_public_key(
                context,
                device_id=peer["device_id"],
                family_id=context.family_id
            )

            is_valid = await verify_signature(
                payload=peer_handshake,
                signature=peer_handshake["signature"],
                public_key=peer_public_key,
                algorithm="ed25519"
            )

            if not is_valid:
                logger.error(
                    f"Authentication failed: invalid signature from {peer['device_id']}",
                    extra={"peer_id": peer["device_id"], "family_id": context.family_id}
                )
                await conn.close()
                continue

            # Step 6: Verify challenge response
            expected_response = hashlib.sha256(challenge + peer["device_id"].encode()).digest()
            actual_response = bytes.fromhex(peer_handshake.get("challenge_response", ""))

            if expected_response != actual_response:
                logger.error(
                    f"Authentication failed: invalid challenge response from {peer['device_id']}"
                )
                await conn.close()
                continue

            # Step 7: Authentication successful ✅
            conn.authenticated = True
            conn.peer_public_key = peer_public_key
            conn.session_key = derive_session_key(challenge, peer_handshake["challenge"])

            connections[peer["device_id"]] = conn

            logger.info(
                f"✅ Authenticated connection to {peer['device_id']}",
                extra={
                    "peer_id": peer["device_id"],
                    "network_type": peer["network_type"],
                    "family_id": context.family_id
                }
            )

        except AuthenticationError as e:
            logger.error(f"Authentication failed for {peer['device_id']}: {e}")
        except ConnectionError as e:
            logger.warning(f"Failed to connect to {peer['device_id']}: {e}")

    return {
        "connections": connections,
        "authenticated_count": len(connections),
        "failed_count": len(discovered_peers) - len(connections)
    }


async def sign_with_device_key(context, payload, key_type="ed25519"):
    """Sign payload with device's private key from provisioning"""
    device_key = await context.syscalls.get_device_signing_key(
        device_id=context.device_id,
        capability="device_keys.read"
    )

    canonical_payload = json.dumps(payload, sort_keys=True).encode()
    signature = device_key.sign(canonical_payload)

    return signature.hex()


async def get_peer_public_key(context, device_id, family_id):
    """Get peer's public key from trust store"""
    trust_record = await context.syscalls.query_device_trust(
        device_id=device_id,
        family_id=family_id,
        capability="st_device_trust.read"
    )

    if not trust_record:
        raise AuthenticationError(f"Device {device_id} not in trust store")

    return trust_record["public_key"]
```

---

### Stage 30: Data Source Selector (M03 - data_source_selector)
**Module:** `k0/modules/sync/data_source_selector.py`
**Contract:** `k0/contracts/modules/sync.data_source_selector.v1.yaml`

**Purpose:** **TABLE-AGNOSTIC** - Select which tables to sync based on config

**Input:** Configuration from pipeline YAML
**Output:** List of data sources with sync strategies

**Logic:**
```python
async def run(message, context, **config):
    """
    M03: Data Source Selector (Table-Agnostic)

    Dynamically selects which tables to sync.
    Extensible to add new tables without code changes.

    Returns:
        List of data sources:
        [
            {
                "table": "st_hipp_events",
                "priority": 1,
                "sync_strategy": "INCREMENTAL",
                "batch_size": 100,
                "query": "SELECT * FROM st_hipp_events WHERE updated_at > ?"
            },
            {
                "table": "st_relationships",
                "priority": 2,
                "sync_strategy": "FULL",
                "batch_size": 50,
                "query": "SELECT * FROM st_relationships"
            }
        ]
    """

    data_sources = []

    for source_config in config["data_sources"]:
        if not source_config["enabled"]:
            continue

        # Build query based on sync strategy
        if source_config["sync_strategy"] == "INCREMENTAL":
            # Delta since last sync (watermark tracking)
            query = await build_incremental_query(
                table=source_config["table"],
                watermark=await get_sync_watermark(context, source_config["table"])
            )
        else:
            # Full table sync
            query = f"SELECT * FROM {source_config['table']}"

        data_sources.append({
            "table": source_config["table"],
            "priority": source_config["priority"],
            "sync_strategy": source_config["sync_strategy"],
            "batch_size": source_config["batch_size"],
            "query": query
        })

    # Sort by priority (lowest first)
    data_sources.sort(key=lambda x: x["priority"])

    return {"data_sources": data_sources}
```

---

### Stage 40: Delta Extraction (M04 - delta_extractor)
**Module:** `k0/modules/sync/delta_extractor.py`
**Contract:** `k0/contracts/modules/sync.delta_extractor.v1.yaml`

**Purpose:** Extract changes from selected data sources since last sync

**Input:** Data sources from M03
**Output:** Batched deltas ready for sync

**Logic:**
```python
async def run(message, context, **config):
    """
    M04: Delta Extractor

    Reads from multiple tables and extracts changes.
    Uses syscalls for least-privilege access.

    Returns:
        Deltas per table:
        {
            "st_hipp_events": [
                {"event_id": "evt-1", "row": {...}, "vector_clock": {...}},
                {"event_id": "evt-2", "row": {...}, "vector_clock": {...}}
            ],
            "st_relationships": [
                {"id": 1, "row": {...}, "vector_clock": {...}}
            ]
        }
    """

    data_sources = message["data_sources"]
    deltas = {}

    for source in data_sources:
        table = source["table"]

        # Use syscall for capability-gated read
        rows = await context.syscalls.execute_query(
            query=source["query"],
            params=[source.get("watermark")],
            capability=f"{table}.read"
        )

        # Attach vector clock to each row
        deltas[table] = []
        for row in rows:
            deltas[table].append({
                "row": dict(row),
                "vector_clock": await get_row_vector_clock(context, table, row),
                "timestamp": row.get("updated_at") or row.get("created_at")
            })

    return {
        "deltas": deltas,
        "total_changes": sum(len(v) for v in deltas.values())
    }
```

---

### Stage 50: CRDT Merge Preparation (M05 - crdt_prepare)
**Module:** `k0/modules/sync/crdt_prepare.py`
**Contract:** `k0/contracts/modules/sync.crdt_prepare.v1.yaml`

**Purpose:** Prepare deltas for CRDT merge (add device ID, timestamps)

**Input:** Extracted deltas from M04
**Output:** CRDT-ready change records

**Logic:**
```python
async def run(message, context, **config):
    """
    M05: CRDT Merge Preparation

    Wraps deltas with CRDT metadata per ADR-0050b.

    Returns:
        CRDT records:
        [
            {
                "table": "st_hipp_events",
                "record_id": "evt-1",
                "device_id": "iphone-mom",
                "timestamp": 1700000000000,
                "vector_clock": {"iphone-mom": 5, "laptop-dad": 3},
                "payload": {...}
            }
        ]
    """

    deltas = message["deltas"]
    crdt_records = []

    device_id = context.device_id

    for table, rows in deltas.items():
        for row_data in rows:
            crdt_records.append({
                "table": table,
                "record_id": extract_primary_key(table, row_data["row"]),
                "device_id": device_id,
                "timestamp": row_data["timestamp"],
                "vector_clock": row_data["vector_clock"],
                "payload": row_data["row"]
            })

    return {"crdt_records": crdt_records}
```

---

### Stage 60: Sync Transmission (M06 - sync_transmitter)
**Module:** `k0/modules/sync/sync_transmitter.py`
**Contract:** `k0/contracts/modules/sync.sync_transmitter.v1.yaml`

**Purpose:** Send CRDT records to peer devices via P07 channel

**Input:** CRDT records from M05, connections from M02
**Output:** Transmission status per peer

**Logic:**
```python
async def run(message, context, **config):
    """
    M06: Sync Transmitter

    Sends changes to all connected peers.
    Uses FlatBuffers serialization (ADR-0019).

    Returns:
        Transmission results:
        {
            "iphone-mom": {"sent": 10, "status": "SUCCESS"},
            "laptop-dad": {"sent": 10, "status": "SUCCESS"}
        }
    """

    crdt_records = message["crdt_records"]
    connections = message["connections"]

    # Build P07 sync message
    p07_message = build_p07_sync_message(
        sender_device_id=context.device_id,
        records=crdt_records,
        vector_clock=await get_vector_clock(context)
    )

    # Serialize with FlatBuffers
    payload = flatbuffers_encode(p07_message)

    results = {}
    for peer_id, conn in connections.items():
        try:
            await conn.send(payload)
            results[peer_id] = {"sent": len(crdt_records), "status": "SUCCESS"}
        except Exception as e:
            logger.error(f"Failed to send to {peer_id}: {e}")
            results[peer_id] = {"sent": 0, "status": "FAILED", "error": str(e)}

    return {"transmission_results": results}
```

---

### Stage 70: Sync Reception & Merge (M07 - sync_receiver)
**Module:** `k0/modules/sync/sync_receiver.py`
**Contract:** `k0/contracts/modules/sync.sync_receiver.v1.yaml`

**Purpose:** Receive changes from peers and merge using CRDT logic

**Input:** Incoming P07 messages from peers
**Output:** Merge results with conflict details

**Logic:**
```python
async def run(message, context, **config):
    """
    M07: Sync Receiver & CRDT Merge

    Receives changes from peers and applies CRDT merge (ADR-0050b).
    LWW with device ID tiebreaker.

    Returns:
        Merge results:
        {
            "merged_count": 10,
            "conflicts_resolved": 2,
            "skipped": 0,
            "conflicts": [
                {
                    "table": "st_hipp_events",
                    "record_id": "evt-1",
                    "winner": "iphone-mom",
                    "loser": "laptop-dad",
                    "resolution": "LWW"
                }
            ]
        }
    """

    connections = message["connections"]

    merge_results = {
        "merged_count": 0,
        "conflicts_resolved": 0,
        "skipped": 0,
        "conflicts": []
    }

    for peer_id, conn in connections.items():
        # Receive incoming changes
        incoming_payload = await conn.receive()
        incoming_message = flatbuffers_decode(incoming_payload)

        for record in incoming_message["records"]:
            # Get local version
            local_record = await get_local_record(
                context,
                table=record["table"],
                record_id=record["record_id"]
            )

            # CRDT merge (LWW + device ID ordering)
            winner = crdt_merge(
                local=local_record,
                incoming=record,
                conflict_resolution=config["crdt_config"]["conflict_resolution"]
            )

            if winner == "incoming":
                # Apply incoming change
                await context.syscalls.upsert_record(
                    table=record["table"],
                    record=record["payload"],
                    capability=f"{record['table']}.write"
                )
                merge_results["merged_count"] += 1

            elif winner == "conflict":
                # Log conflict for observability
                merge_results["conflicts"].append({
                    "table": record["table"],
                    "record_id": record["record_id"],
                    "winner": local_record["device_id"],
                    "loser": record["device_id"],
                    "resolution": "LWW"
                })
                merge_results["conflicts_resolved"] += 1

            else:
                # Local version wins, skip
                merge_results["skipped"] += 1

    return merge_results
```

---

### Stage 80: Watermark Update (M08 - watermark_updater)
**Module:** `k0/modules/sync/watermark_updater.py`
**Contract:** `k0/contracts/modules/sync.watermark_updater.v1.yaml`

**Purpose:** Update sync watermarks for incremental sync

**Input:** Merge results from M07
**Output:** Updated watermark timestamps per table

**Logic:**
```python
async def run(message, context, **config):
    """
    M08: Watermark Updater

    Tracks "last synced timestamp" per table for incremental sync.

    Returns:
        Updated watermarks:
        {
            "st_hipp_events": 1700000000000,
            "st_relationships": 1700000000000
        }
    """

    merge_results = message
    data_sources = message["data_sources"]

    watermarks = {}

    for source in data_sources:
        table = source["table"]

        # Get max timestamp from merged records
        max_timestamp = await get_max_synced_timestamp(context, table)

        # Update watermark in sync state table
        await context.syscalls.upsert_watermark(
            table=table,
            timestamp=max_timestamp,
            capability="st_sync_state.write"
        )

        watermarks[table] = max_timestamp

    return {"watermarks": watermarks}
```

---

## Database Schema Extensions

### New Tables for Sync State & Device Trust

**Migration:** `k0/contracts/sql/migrations/0025_device_sync_tables.sql`

```sql
-- ====================================================================
-- Migration 0025: Device Sync State & Trust Tables
-- ====================================================================
-- Purpose: Track sync state, vector clocks, conflicts, and device trust for P07
-- Related: ADR-0050, ADR-0050b, P07_DEVICE_SYNC pipeline
-- Security: Prevents unauthorized sync with non-family devices
-- ====================================================================

BEGIN;

-- ====================================================================
-- Table 0: Device Trust Store (AUTHENTICATION)
-- ====================================================================
-- Purpose: Whitelist of trusted family devices authorized to sync
-- Security: Prevents unauthorized K0 instances from syncing
-- Populated during device pairing flow (QR code, NFC, manual entry)
-- ====================================================================

CREATE TABLE IF NOT EXISTS st_device_trust (
  id INTEGER PRIMARY KEY AUTOINCREMENT,

  -- Device identification
  device_id TEXT NOT NULL UNIQUE,
  family_id TEXT NOT NULL,

  -- Device metadata
  device_name TEXT NOT NULL,           -- "Mom's iPhone", "Dad's Laptop"
  device_type TEXT NOT NULL,           -- "iOS", "Android", "macOS", "Windows"
  owner_name TEXT NOT NULL,            -- "Mom", "Dad", "Kid"

  -- Cryptographic trust
  public_key TEXT NOT NULL,            -- Ed25519 public key (from provisioning)
  public_key_fingerprint TEXT NOT NULL UNIQUE,  -- sha256 fingerprint
  cert_expiry INTEGER,                 -- Certificate expiration (Unix ms)

  -- Trust status
  trust_status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(trust_status IN ('ACTIVE', 'PENDING', 'REVOKED')),
  trust_level TEXT NOT NULL DEFAULT 'FULL' CHECK(trust_level IN ('FULL', 'READ_ONLY', 'LIMITED')),

  -- Pairing metadata
  paired_at INTEGER NOT NULL,          -- When device was added to trust store
  paired_by_device_id TEXT,            -- Which device added this one
  pairing_method TEXT NOT NULL,        -- "QR_CODE", "NFC", "MANUAL", "FAMILY_INVITE"

  -- Revocation
  revoked_at INTEGER,
  revoked_by_device_id TEXT,
  revocation_reason TEXT,

  -- Audit
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,

  FOREIGN KEY (family_id) REFERENCES families(family_id)
);

CREATE INDEX idx_device_trust_family ON st_device_trust(family_id);
CREATE INDEX idx_device_trust_status ON st_device_trust(trust_status);
CREATE INDEX idx_device_trust_fingerprint ON st_device_trust(public_key_fingerprint);


-- ====================================================================
-- Table 0b: Device Pairing Requests (AUTHORIZATION FLOW)
-- ====================================================================
-- Purpose: Track pending device pairing requests (before adding to trust store)
-- Flow: New device → generates QR code → existing device scans → approves → adds to trust
-- ====================================================================

CREATE TABLE IF NOT EXISTS st_device_pairing_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,

  -- Request identification
  request_id TEXT NOT NULL UNIQUE,
  requesting_device_id TEXT NOT NULL,
  family_id TEXT NOT NULL,

  -- Device metadata
  device_name TEXT NOT NULL,
  device_type TEXT NOT NULL,
  owner_name TEXT NOT NULL,

  -- Cryptographic verification
  public_key TEXT NOT NULL,
  public_key_fingerprint TEXT NOT NULL,
  challenge TEXT NOT NULL,             -- Random challenge for verification
  challenge_response TEXT,             -- Response from approving device

  -- Request status
  status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED')),

  -- Approval
  approved_by_device_id TEXT,
  approved_at INTEGER,

  -- Rejection
  rejected_by_device_id TEXT,
  rejected_at INTEGER,
  rejection_reason TEXT,

  -- Expiration (pairing requests expire after 10 minutes)
  expires_at INTEGER NOT NULL,

  -- Audit
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE INDEX idx_pairing_requests_family_status ON st_device_pairing_requests(family_id, status);
CREATE INDEX idx_pairing_requests_expires ON st_device_pairing_requests(expires_at);


-- ====================================================================
-- Continue with existing sync tables...
-- ====================================================================

-- Table 1: Sync State (watermarks per table per peer)
CREATE TABLE IF NOT EXISTS st_sync_state (
  id INTEGER PRIMARY KEY AUTOINCREMENT,

  -- Peer identification
  local_device_id TEXT NOT NULL,
  peer_device_id TEXT NOT NULL,

  -- Table being synced
  table_name TEXT NOT NULL,

  -- Watermark tracking (incremental sync)
  last_sync_timestamp INTEGER NOT NULL,  -- Unix ms
  last_sync_at INTEGER NOT NULL,         -- Unix ms (when sync happened)

  -- Sync metadata
  sync_strategy TEXT NOT NULL CHECK(sync_strategy IN ('INCREMENTAL', 'FULL')),
  records_synced INTEGER NOT NULL DEFAULT 0,
  conflicts_resolved INTEGER NOT NULL DEFAULT 0,

  -- Version tracking
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,

  UNIQUE(local_device_id, peer_device_id, table_name)
);

CREATE INDEX idx_sync_state_device_table ON st_sync_state(local_device_id, table_name);
CREATE INDEX idx_sync_state_last_sync ON st_sync_state(last_sync_at DESC);


-- Table 2: Vector Clocks (causal ordering per device)
CREATE TABLE IF NOT EXISTS st_vector_clock (
  id INTEGER PRIMARY KEY AUTOINCREMENT,

  -- Device identification
  device_id TEXT NOT NULL,
  table_name TEXT NOT NULL,
  record_id TEXT NOT NULL,

  -- Vector clock entries (JSON map: {device_id: clock_value})
  vector_clock_json TEXT NOT NULL,

  -- Timestamp tracking
  logical_timestamp INTEGER NOT NULL,
  wall_clock_timestamp INTEGER NOT NULL,

  -- Metadata
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,

  UNIQUE(device_id, table_name, record_id)
);

CREATE INDEX idx_vector_clock_device ON st_vector_clock(device_id);
CREATE INDEX idx_vector_clock_table_record ON st_vector_clock(table_name, record_id);


-- Table 3: Sync Conflicts (CRDT merge conflicts for debugging)
CREATE TABLE IF NOT EXISTS st_sync_conflicts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,

  -- Conflict identification
  conflict_id TEXT NOT NULL UNIQUE,
  table_name TEXT NOT NULL,
  record_id TEXT NOT NULL,

  -- Conflicting versions
  local_device_id TEXT NOT NULL,
  local_timestamp INTEGER NOT NULL,
  local_payload_json TEXT NOT NULL,

  peer_device_id TEXT NOT NULL,
  peer_timestamp INTEGER NOT NULL,
  peer_payload_json TEXT NOT NULL,

  -- Resolution
  winner_device_id TEXT NOT NULL,
  resolution_strategy TEXT NOT NULL,  -- "LWW", "DEVICE_ORDER", "MANUAL"
  resolved_at INTEGER NOT NULL,

  -- Metadata
  created_at INTEGER NOT NULL
);

CREATE INDEX idx_sync_conflicts_table_record ON st_sync_conflicts(table_name, record_id);
CREATE INDEX idx_sync_conflicts_resolved ON st_sync_conflicts(resolved_at DESC);

COMMIT;
```

---

## Device Pairing Flow (Trust Establishment)

### How Devices Join the Family Trust Store

**Scenario:** Mom has iPhone (already trusted). Dad gets new laptop and wants to sync.

#### Step 1: Dad's Laptop Generates Pairing Request

```python
# Dad's laptop (new device)
pairing_request = {
    "request_id": str(uuid.uuid4()),
    "requesting_device_id": "laptop-dad",
    "family_id": "family-abc123",  # From family invite or manual entry
    "device_name": "Dad's Laptop",
    "device_type": "macOS",
    "owner_name": "Dad",
    "public_key": device_public_key,
    "public_key_fingerprint": sha256(device_public_key),
    "challenge": os.urandom(32).hex(),
    "expires_at": time.time_ms() + (10 * 60 * 1000)  # 10 minutes
}

# Store locally and generate QR code
qr_code_data = {
    "type": "DEVICE_PAIRING",
    "request_id": pairing_request["request_id"],
    "device_id": "laptop-dad",
    "public_key_fingerprint": pairing_request["public_key_fingerprint"],
    "challenge": pairing_request["challenge"]
}

# Display QR code on Dad's laptop screen
display_qr_code(qr_code_data)
```

#### Step 2: Mom Scans QR Code with iPhone (Trusted Device)

```python
# Mom's iPhone (already in trust store)
scanned_data = scan_qr_code()

# Verify this is a pairing request
if scanned_data["type"] != "DEVICE_PAIRING":
    raise ValueError("Invalid QR code")

# Fetch pairing request details
# (laptop broadcasts request via mDNS or uploads to local P2P directory)
pairing_request = await fetch_pairing_request(scanned_data["request_id"])

# Show approval UI to Mom
ui.show_pairing_approval_dialog(
    device_name=pairing_request["device_name"],
    owner_name=pairing_request["owner_name"],
    device_type=pairing_request["device_type"]
)
```

#### Step 3: Mom Approves Pairing

```python
# Mom clicks "Approve" button
if user_approves:
    # Sign the challenge with Mom's device key (proof of approval)
    approval_signature = sign_with_device_key(
        context,
        payload={
            "request_id": pairing_request["request_id"],
            "approving_device_id": "iphone-mom",
            "challenge_response": hashlib.sha256(
                bytes.fromhex(pairing_request["challenge"]) +
                b"iphone-mom"
            ).hex()
        }
    )

    # Add Dad's laptop to trust store (local + broadcast to family)
    await context.syscalls.add_device_to_trust(
        device_id=pairing_request["requesting_device_id"],
        family_id=pairing_request["family_id"],
        public_key=pairing_request["public_key"],
        device_name=pairing_request["device_name"],
        trust_status="ACTIVE",
        paired_by_device_id="iphone-mom",
        pairing_method="QR_CODE",
        capability="st_device_trust.write"
    )

    # Broadcast trust update to all family devices
    await broadcast_trust_update(pairing_request)

    ui.show_success("Dad's Laptop added to family!")
```

#### Step 4: Dad's Laptop Receives Trust Confirmation

```python
# Laptop receives trust confirmation via P07 sync
trust_update = await wait_for_trust_confirmation(timeout=30)

if trust_update["trust_status"] == "ACTIVE":
    # Now trusted! Can discover and sync with family devices
    ui.show_success("Paired with family! Syncing now...")

    # Start P07_DEVICE_SYNC pipeline
    await execute_pipeline("P07_DEVICE_SYNC")
else:
    ui.show_error("Pairing failed or rejected")
```

### Trust Revocation (Device Lost/Stolen)

```python
# Mom's iPhone - revoke Dad's old laptop (stolen)
await context.syscalls.revoke_device_trust(
    device_id="laptop-dad-old",
    family_id="family-abc123",
    revoked_by_device_id="iphone-mom",
    revocation_reason="Device stolen",
    capability="st_device_trust.write"
)

# Broadcast revocation to all family devices
await broadcast_trust_revocation("laptop-dad-old")

# Old laptop will be rejected on next sync attempt
# (M01 device_discovery will filter it out)
```

---

## Driver: SyncCoordinator

**Driver Implementation:** `k0/drivers/sync_coordinator.py`
**Alias:** `st_sync` → `SyncCoordinator`

**Purpose:** Low-level TCP/QUIC transport for device-to-device sync

```python
from k0.drivers.base import BaseDriver

class SyncCoordinator(BaseDriver):
    """
    SyncCoordinator Driver

    Manages TCP (Phase 1) or QUIC (Phase 2) connections for sync.
    Used by P07_DEVICE_SYNC pipeline modules.

    Capabilities:
    - Connection pooling
    - Automatic reconnection
    - Keep-alive heartbeats
    - Backpressure handling
    """

    async def establish_connection(self, peer_ip: str, peer_port: int):
        """Establish TCP connection to peer"""
        pass

    async def send_message(self, connection, payload: bytes):
        """Send FlatBuffers-serialized message"""
        pass

    async def receive_message(self, connection) -> bytes:
        """Receive message from peer"""
        pass

    async def close_connection(self, connection):
        """Gracefully close connection"""
        pass
```

---

## Observability & Metrics

### Prometheus Metrics

```yaml
metrics:
  # Discovery
  - name: "p07_device_discovery_latency"
    type: histogram
    buckets: [10, 50, 100, 200, 500]
    labels: [discovery_method, peer_count]

  # Connection
  - name: "p07_active_connections"
    type: gauge
    labels: [peer_device_id, network_type]

  # Sync Transmission
  - name: "p07_sync_transmission_latency"
    type: histogram
    buckets: [5, 10, 20, 50, 100, 200]
    labels: [peer_device_id, table_name]

  - name: "p07_records_synced_total"
    type: counter
    labels: [table_name, sync_strategy, outcome]

  # CRDT Merge
  - name: "p07_crdt_merge_latency"
    type: histogram
    buckets: [1, 5, 10, 20, 50]
    labels: [table_name, conflict_resolution]

  - name: "p07_conflicts_resolved_total"
    type: counter
    labels: [table_name, resolution_strategy, winner_device]

  # Watermark
  - name: "p07_watermark_lag_seconds"
    type: gauge
    labels: [table_name, peer_device_id]

  # Errors
  - name: "p07_sync_errors_total"
    type: counter
    labels: [stage, error_type, peer_device_id]
```

---

## Testing Strategy

### WARD Integration Tests

**Test File:** `tests/integration/test_p07_device_sync.py`

```python
from ward import test, fixture

@fixture
async def multi_device_setup():
    """3-device test environment"""
    devices = {
        "iphone-mom": await create_test_kernel("iphone-mom"),
        "laptop-dad": await create_test_kernel("laptop-dad"),
        "tablet-kid": await create_test_kernel("tablet-kid")
    }
    yield devices
    await teardown_kernels(devices)


@test("P07 discovers peers on LAN via mDNS")
async def _(devices=multi_device_setup):
    # iPhone discovers laptop and tablet
    result = await devices["iphone-mom"].execute_pipeline(
        "P07_DEVICE_SYNC",
        trigger="cognitive.device.sync.requested.v1"
    )

    assert result["stage_10_device_discovery"]["peer_count"] == 2
    assert "laptop-dad" in result["discovered_peers"]
    assert "tablet-kid" in result["discovered_peers"]


@test("P07 syncs st_hipp_events across devices <50ms")
async def _(devices=multi_device_setup):
    # Write memory on iPhone
    await devices["iphone-mom"].k0.write({
        "event_id": "evt-1",
        "text": "Family dinner",
        "updated_at": time.time_ms()
    })

    # Trigger sync
    start = time.time()
    await devices["iphone-mom"].execute_pipeline("P07_DEVICE_SYNC")

    # Wait for sync to laptop
    await wait_for_sync(devices["laptop-dad"], timeout=1.0)
    latency_ms = (time.time() - start) * 1000

    # Verify latency
    assert latency_ms < 50

    # Verify data on laptop
    event = await devices["laptop-dad"].k0.read("evt-1")
    assert event["text"] == "Family dinner"


@test("P07 resolves CRDT conflicts with LWW + device ordering")
async def _(devices=multi_device_setup):
    # Simultaneous writes (same timestamp)
    ts = time.time_ms()

    await devices["iphone-mom"].k0.write({
        "event_id": "evt-1",
        "text": "Party at 3pm",
        "timestamp": ts
    })

    await devices["laptop-dad"].k0.write({
        "event_id": "evt-1",
        "text": "Party at 2pm",
        "timestamp": ts
    })

    # Sync both devices
    await asyncio.gather(
        devices["iphone-mom"].execute_pipeline("P07_DEVICE_SYNC"),
        devices["laptop-dad"].execute_pipeline("P07_DEVICE_SYNC")
    )

    # Wait for convergence
    await asyncio.sleep(1.0)

    # Both should have same value (iphone-mom wins per device ordering)
    iphone_event = await devices["iphone-mom"].k0.read("evt-1")
    laptop_event = await devices["laptop-dad"].k0.read("evt-1")

    assert iphone_event["text"] == laptop_event["text"]
    assert iphone_event["text"] == "Party at 3pm"  # iphone < laptop alphabetically


@test("P07 syncs multiple tables (table-agnostic)")
async def _(devices=multi_device_setup):
    # Write to st_hipp_events
    await devices["iphone-mom"].k0.write_hipp_event({
        "event_id": "evt-1",
        "text": "Memory 1"
    })

    # Write to st_relationships
    await devices["iphone-mom"].k0.write_relationship({
        "person_id": "person_mom",
        "related_person_id": "person_dad",
        "relationship_type": "SPOUSE_OF"
    })

    # Sync
    result = await devices["iphone-mom"].execute_pipeline("P07_DEVICE_SYNC")

    # Verify both tables synced
    assert "st_hipp_events" in result["deltas"]
    assert "st_relationships" in result["deltas"]
    assert result["total_changes"] == 2
```

---

## Phase Rollout Plan

### Phase 1 (M2-M3): LAN Sync
- **Week 1-2:** Modules M01-M04 (discovery, connection, data source, delta extraction)
- **Week 3:** Modules M05-M08 (CRDT prepare, transmit, receive, watermark)
- **Week 4:** Integration testing (3-6 devices)
- **Week 5:** Observability, metrics, production readiness

### Phase 2 (M4-M5): Internet Sync
- **Week 1-2:** E2EE tunnel infrastructure
- **Week 3:** Network detection (LAN vs internet preference)
- **Week 4:** Phase 1 + Phase 2 integration
- **Week 5:** Cross-region testing, GA rollout

---

## Extensibility: Adding New Tables

**Example: Adding `st_cognitive_traces` sync**

1. **Update pipeline YAML config:**
```yaml
data_sources:
  - table: st_cognitive_traces
    enabled: true
    priority: 4
    sync_strategy: INCREMENTAL
    batch_size: 50
```

2. **Grant syscall capabilities:**
```yaml
required_caps:
  - st_cognitive_traces.read
```

3. **No code changes needed** - M03-M08 are table-agnostic!

---

## Success Criteria

- ✅ LAN sync <50ms P95
- ✅ Internet sync <200ms P95
- ✅ CRDT conflicts resolved deterministically
- ✅ 3-10 device families supported
- ✅ Zero data loss during sync
- ✅ Table-agnostic (can add new tables via config)
- ✅ Privacy-first (no cloud intermediary)

---

**Last Updated:** 2025-11-18
**Status:** DESIGN COMPLETE - Ready for Implementation
**Next Steps:** Create pipeline contract YAML, implement modules M01-M08
