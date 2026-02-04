# K0-K1 Bridge

> **Status**: Planning
> **Module ID**: `bridge.core`
> **Layer**: Cross-Kernel Boundary (Between K0 and K1)
> **Location**: `bridge/` (root level - NOT inside K0 or K1)

---

## 1. Purpose

The K0-K1 Bridge is a **cross-kernel security gateway** that serves as the ONLY authorized communication channel between the two kernels AND the security boundary for all external connector access.

### Why Bridge Exists

1. **K0 and K1 are isolated** - They run independently with different concerns
2. **K1 has LLM agents** - These could be compromised via prompt injection or hallucinations
3. **External devices are dangerous** - Direct access could unlock doors, disable cameras, drain car batteries
4. **Security boundary required** - All cross-kernel and external calls MUST be authenticated, authorized, and audited

### Bridge Is NOT

- NOT a K1 component (K1 is the cognitive kernel)
- NOT a K0 component (K0 is the infrastructure kernel)
- NOT just a transport layer (it enforces security)
- NOT optional (all cross-kernel communication MUST go through Bridge)

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                                    K0-K1 BRIDGE                                          │
│                             (Cross-Kernel Security Gateway)                              │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  ┌─────────────────────────┐  ┌─────────────────────────┐  ┌─────────────────────────┐   │
│  │   KERNEL TRANSPORT      │  │   CONNECTOR SECURITY    │  │   DEVICE SYNC           │   │
│  │   (K0 ↔ K1 Comms)       │  │   (Tools → Devices)     │  │   (Family Devices)      │   │
│  ├─────────────────────────┤  ├─────────────────────────┤  ├─────────────────────────┤   │
│  │ PORT_QRY: Memory query  │  │ Tool Registration       │  │ mDNS Discovery (LAN)    │   │
│  │ PORT_CMD: Write cmds    │  │ OAuth/Credential Mgmt   │  │ P2P E2EE (Internet)     │   │
│  │ PORT_SSE: Event streams │  │ Rate Limiting           │  │ CRDT Merge (LWW)        │   │
│  │ PORT_OBS: Telemetry     │  │ Audit Logging           │  │ K0 P07 Pipeline         │   │
│  │ Envelope Builder        │  │                         │  │ Device Certificates     │   │
│  └─────────────────────────┘  └─────────────────────────┘  └─────────────────────────┘   │
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                    IFL (Interkernel Fabric Language) - BRIDGE OWNED                 │ │
│  ├─────────────────────────────────────────────────────────────────────────────────────┤ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │ │
│  │  │ IFL Gateway  │  │ IFL Core     │  │ IFL Schemas  │  │ IFL Adapters             │ │ │
│  │  │ • Security   │→ │ • Parser     │→ │ • Validate   │→ │ • HomeKitAdapter         │ │ │
│  │  │ • Auth       │  │ • Translator │  │ • Normalize  │  │ • NestAdapter            │ │ │
│  │  │ • Rate Limit │  │ • Registry   │  │ • Version    │  │ • TeslaAdapter           │ │ │
│  │  │ • Audit      │  │              │  │              │  │ • HealthKitAdapter       │ │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │ • SonosAdapter           │ │ │
│  │                                                        │ • RingAdapter            │ │ │
│  │                                                        │ • MqttAdapter            │ │ │
│  │                                                        │ • FamilySyncAdapter (P07)│ │ │
│  │                                                        └──────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                          │
│                              ┌──────────────────────┐                                    │
│                              │   SECURITY CORE      │                                    │
│                              ├──────────────────────┤                                    │
│                              │ • Capability Tokens  │                                    │
│                              │ • Request Signing    │                                    │
│                              │ • Audit Trail        │                                    │
│                              │ • Band Enforcement   │                                    │
│                              │ • E2EE Encryption    │                                    │
│                              └──────────────────────┘                                    │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
          │                             │                              │
          │ K0 Queries/Commands         │ Physical Devices             │ Device Sync
          ▼                             ▼                              ▼
┌──────────────────────┐  ┌─────────────────────────────┐  ┌─────────────────────────────┐
│     K0 KERNEL        │  │      PHYSICAL DEVICES       │  │    OTHER FAMILY DEVICES     │
│                      │  ├─────────────────────────────┤  │                             │
│ • Storage (WAL,Vec)  │  │ Philips Hue • Nest • Tesla  │  │  ┌─────────┐  ┌─────────┐   │
│ • Pipelines (P01-20) │  │ Sonos • Ring • Apple Watch  │  │  │ iPhone  │  │ Laptop  │   │
│ • Memory Consolidate │  │ IoT Sensors • Smart Locks   │  │  │ K0 + K1 │  │ K0 + K1 │   │
│ • Query Aggregation  │  │                             │  │  └─────────┘  └─────────┘   │
│ • P07 CRDT Sync      │  │                             │  │  ┌─────────┐  ┌─────────┐   │
└──────────────────────┘  │                             │  │  │ Tablet  │  │  Hub    │   │
                          │                             │  │  │ K0 + K1 │  │ K0 + K1 │   │
                          └─────────────────────────────┘  │  └─────────┘  └─────────┘   │
                                                           └─────────────────────────────┘
```

---

## 3. Three Primary Responsibilities

### 3.1 Kernel Transport (K0 ↔ K1)

Memory and storage communication between the kernels.

| Port | Direction | Purpose | Example |
| ---- | --------- | ------- | ------- |
| PORT_QRY | K1 → K0 → K1 | Query memory, recall | "Retrieve last 10 conversations" |
| PORT_CMD | K1 → K0 | Write/ingest memory | "Store this new episode" |
| PORT_SSE | K0 → K1 | Real-time event stream | "Memory consolidation complete" |
| PORT_OBS | K1 → K0 | Telemetry/observability | "Session latency metrics" |

#### Kernel Transport Flow

```
K1 Component (e.g., SessionState COLD tier)
        │
        │ archive_to_cold(session_data)
        ▼
┌───────────────────────────────────────┐
│ Bridge: Kernel Transport              │
├───────────────────────────────────────┤
│ 1. Validate caller capability token   │
│ 2. Build envelope (JSON or FlatBuffer)│
│ 3. Sign request                       │
│ 4. Send via PORT_CMD                  │
│ 5. Await acknowledgment               │
│ 6. Log to audit trail                 │
└───────────────────────────────────────┘
        │
        ▼
K0 Pipeline (P02: Write / Ingest)
```

### 3.2 Connector Security (Tools → External)

Security gateway for all tool/connector calls to external devices and services.

#### Why Tools Cannot Call Devices Directly

```
                    DANGEROUS (Never allowed)
                    ─────────────────────────
K1 Agent ───────X───────────► Philips Hue API
(Could be compromised)         (Turns off lights at 3am)

K1 Agent ───────X───────────► Nest API
(Prompt injection)             (Sets heat to 100F)

K1 Agent ───────X───────────► Smart Lock API
(Hallucination)                (Unlocks front door)


                    SAFE (Required path)
                    ────────────────────
K1 Agent ──► Bridge IFL ──► Device
             │
             ├─ Verify tool registered
             ├─ Check OAuth valid
             ├─ Validate action allowed
             ├─ Translate via IFL Core
             ├─ Route to correct Adapter
             ├─ Log for audit
             └─ Rate limit
```

#### Connector Security Flow

```
K1 Workflow Tool (e.g., PhilipsHueTool.set_brightness)
        │
        │ execute(device_id="hue-1", brightness=50)
        ▼
┌───────────────────────────────────────┐
│ Bridge: Connector Security + IFL      │
├───────────────────────────────────────┤
│ 1. Verify PhilipsHueTool is registered│
│ 2. Check tool has valid OAuth token   │
│ 3. Validate action against policy     │
│ 4. Check rate limits                  │
│ 5. IFL Core: Parse & Translate        │
│ 6. IFL Adapter: Route to HomeKit      │
│ 7. Send to physical device            │
│ 8. Log action to audit trail          │
│ 9. Return response to tool            │
└───────────────────────────────────────┘
        │
        ▼
Philips Hue Bridge → Light Bulb
```

### 3.3 Device Sync (Multi-Device Family Sync)

**The third responsibility**: Synchronizing K0 memory across family devices (phones, tablets, laptops).

> **Reference**: [ADR-0050c: Multi-Device Family Sync Strategy](../docs/architecture/decisions-K1/06-layer5-infrastructure/0050-multi-device-family-sync-strategy/0050c-multi-device-family-sync-strategy.md)

#### Why Device Sync is Critical

FamilyOS is **device-first, privacy-first**:

- Every family device runs its own K0 + K1 (full dual-kernel)
- Family data NEVER leaves family devices (no cloud)
- Devices must sync memories across the family

#### Device Sync Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       MULTI-DEVICE FAMILY SYNC                              │
│                       (Via Bridge → K0 P07 Pipeline)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  PHASE 1: LAN SYNC (Same WiFi)            PHASE 2: INTERNET SYNC            │
│  ┌───────────────────────────┐            ┌───────────────────────────┐     │
│  │ • mDNS Device Discovery   │            │ • P2P E2EE Tunnel         │     │
│  │ • Direct TCP Connection   │            │ • Device Certificates     │     │
│  │ • Latency: <1ms           │            │ • Latency: <500ms         │     │
│  │ • No internet required    │            │ • AES256-GCM Encryption   │     │
│  └───────────────────────────┘            └───────────────────────────┘     │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    CRDT MERGE (Last-Write-Wins)                       │  │
│  │  • Conflict resolution by timestamp + device ID                       │  │
│  │  • Automatic convergence across all devices                           │  │
│  │  • K0 P07 Pipeline handles merge operations                           │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Device Sync Flow

```
Device A (Mom's iPhone) writes memory
        │
        │ k0.write(memory_item)  # Local write
        ▼
┌───────────────────────────────────────┐
│ Bridge: Device Sync                   │
├───────────────────────────────────────┤
│ 1. Detect other devices (mDNS/P2P)    │
│ 2. Wrap change in sync envelope       │
│ 3. Sign with device certificate       │
│ 4. E2EE encrypt (if internet)         │
│ 5. Broadcast to family devices        │
└───────────────────────────────────────┘
        │
        ▼ (LAN: <1ms, Internet: <500ms)
┌───────────────────────────────────────┐
│ Device B (Dad's Laptop) receives      │
├───────────────────────────────────────┤
│ 1. Verify sender certificate          │
│ 2. Decrypt (if E2EE)                  │
│ 3. CRDT merge (LWW conflict resolve)  │
│ 4. Update local K0                    │
│ 5. Notify local K1 of changes         │
└───────────────────────────────────────┘
```

#### CRDT Conflict Resolution

```
Scenario: Simultaneous writes from two devices

Mom writes: "Birthday party 3pm" on iPhone at 14:00:00.001
Dad writes: "Birthday party 2pm" on Laptop at 14:00:00.002

Resolution (Last-Write-Wins by timestamp + device order):
  1. Compare timestamps: iPhone (001) < Laptop (002)
  2. iPhone timestamp is earlier → iPhone wins
  3. Result: "Birthday party 3pm" (Mom's version)
  4. Both devices converge to same state within <100ms
```

#### Sync Modes

| Mode | When | Latency | Method |
| ---- | ---- | ------- | ------ |
| LAN (Phase 1) | Same WiFi | <1ms | mDNS + TCP |
| Internet (Phase 2) | Remote | <500ms | P2P E2EE tunnel |
| Offline | No connection | N/A | Queue until sync |
| Manual | User-triggered | Varies | Explicit sync button |

#### Privacy Guarantees

| Guarantee | How |
| --------- | --- |
| Zero cloud | Direct device-to-device only |
| E2EE | AES256-GCM end-to-end encryption |
| Device certs | ED25519 signatures |
| No intermediary | No relay server |
| Family-owned | All data stays in family |

---

## 4. Security Model

### 4.1 Capability Tokens

Every caller (K1 component or tool) must present a capability token:

```python
@dataclass
class CapabilityToken:
    issuer: str              # "bridge.security"
    subject: str             # "k1.sessionstate" or "tool.philips_hue"
    capabilities: list[str]  # ["storage.read", "storage.write"]
    band: PrivacyBand        # GREEN, AMBER, RED, BLACK
    issued_at: datetime
    expires_at: datetime
    signature: bytes         # HMAC-SHA256
```

### 4.2 Privacy Bands

| Band | Description | Bridge Behavior |
| ---- | ----------- | --------------- |
| GREEN | Non-sensitive | Full access, standard logging |
| AMBER | Personal | Logged, 90-day retention |
| RED | Sensitive | Masked in logs, 30-day retention |
| BLACK | Ephemeral | Never persisted, no logging |

### 4.3 Tool Registration

Tools MUST register with Bridge before use:

```python
# Tool registration (at startup or first use)
bridge.register_tool(
    tool_id="philips_hue",
    display_name="Philips Hue Light Control",
    capabilities=["device.lights.read", "device.lights.write"],
    auth_config=OAuthConfig(
        provider="philips",
        client_id="xxx",
        scopes=["lights:read", "lights:write"]
    ),
    policy=ToolPolicy(
        rate_limit_per_minute=60,
        allowed_actions=["get_state", "set_brightness", "set_color"],
        blocked_actions=["factory_reset", "unpair"]
    )
)
```

### 4.4 Audit Trail

All Bridge operations are logged:

```json
{
    "event_id": "br-2026-02-01-abc123",
    "timestamp": "2026-02-01T15:30:00Z",
    "caller": "k1.workflow.night_routine",
    "tool": "philips_hue",
    "action": "set_brightness",
    "device_id": "hue-living-room-1",
    "parameters": {"brightness": 20},
    "result": "success",
    "latency_ms": 45,
    "band": "GREEN"
}
```

---

## 5. Interfaces (Ports)

### 5.1 Kernel Query Port

```python
class IKernelQueryPort(Protocol):
    """Query K0 for memory recall."""

    async def query(
        self,
        query: QueryEnvelope,
        token: CapabilityToken
    ) -> QueryResponse:
        """Execute memory query against K0."""
        ...

    async def multi_query(
        self,
        queries: list[QueryEnvelope],
        token: CapabilityToken
    ) -> list[QueryResponse]:
        """Execute multiple queries in batch."""
        ...
```

### 5.2 Kernel Command Port

```python
class IKernelCommandPort(Protocol):
    """Send write commands to K0."""

    async def command(
        self,
        command: CommandEnvelope,
        token: CapabilityToken
    ) -> CommandReceipt:
        """Execute write command against K0."""
        ...

    async def batch_command(
        self,
        commands: list[CommandEnvelope],
        token: CapabilityToken
    ) -> list[CommandReceipt]:
        """Execute multiple commands atomically."""
        ...
```

### 5.3 Kernel SSE Port

```python
class IKernelSSEPort(Protocol):
    """Subscribe to K0 event streams."""

    async def subscribe(
        self,
        topics: list[str],
        token: CapabilityToken,
        handler: Callable[[Event], Awaitable[None]]
    ) -> Subscription:
        """Subscribe to K0 events."""
        ...

    async def unsubscribe(
        self,
        subscription: Subscription
    ) -> None:
        """Unsubscribe from events."""
        ...
```

### 5.4 Connector Gateway Port

```python
class IConnectorGatewayPort(Protocol):
    """Gateway for tool calls to external devices/services."""

    async def execute(
        self,
        tool_id: str,
        action: str,
        parameters: dict,
        token: CapabilityToken
    ) -> ConnectorResponse:
        """Execute tool action through security gateway."""
        ...

    async def register_tool(
        self,
        tool_config: ToolConfig
    ) -> ToolRegistration:
        """Register a new tool with the gateway."""
        ...

    async def refresh_credentials(
        self,
        tool_id: str
    ) -> CredentialStatus:
        """Refresh OAuth/API credentials for a tool."""
        ...
```

---

## 6. Envelope Format

### 6.1 Query Envelope

```python
@dataclass
class QueryEnvelope:
    envelope_id: str              # UUID
    trace_id: str                 # Cognitive trace ID
    query_type: str               # "recall", "search", "aggregate"
    payload: dict                 # Query-specific data
    requested_at: datetime
    timeout_ms: int               # Max wait time
    priority: Priority            # REALTIME, INTERACTIVE, BACKGROUND
```

### 6.2 Command Envelope

```python
@dataclass
class CommandEnvelope:
    envelope_id: str              # UUID
    trace_id: str                 # Cognitive trace ID
    command_type: str             # "write", "archive", "delete"
    target_pipeline: str          # "P02", "P03", etc.
    payload: bytes                # FlatBuffer or JSON
    band: PrivacyBand
    requested_at: datetime
```

### 6.3 Connector Request

```python
@dataclass
class ConnectorRequest:
    request_id: str               # UUID
    trace_id: str                 # Cognitive trace ID
    tool_id: str                  # Registered tool ID
    action: str                   # Action to perform
    device_id: str | None         # Target device (if applicable)
    parameters: dict              # Action parameters
    timeout_ms: int
    requested_at: datetime
```

---

## 7. Integration Points

### 7.1 K1 SessionState → Bridge

SessionState uses Bridge for COLD tier archival:

```python
# In SessionState's K0BridgeAdapter (implements IStoragePort)
class K0BridgeStorageAdapter(IStoragePort):
    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        self.token = bridge.acquire_token(
            subject="k1.sessionstate",
            capabilities=["storage.read", "storage.write"]
        )

    async def archive(self, session_id: str, data: bytes) -> ArchiveReceipt:
        envelope = CommandEnvelope(
            command_type="archive",
            target_pipeline="P02",
            payload=data,
            band=PrivacyBand.AMBER
        )
        return await self.bridge.command(envelope, self.token)

    async def restore(self, session_id: str) -> bytes:
        envelope = QueryEnvelope(
            query_type="recall",
            payload={"session_id": session_id}
        )
        response = await self.bridge.query(envelope, self.token)
        return response.data
```

### 7.2 K1 Tools → Bridge IFL → Devices

Tools use Bridge for external device access. Bridge owns the entire IFL stack:

```python
# In a workflow tool
class PhilipsHueTool(BaseTool):
    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        self.token = bridge.acquire_token(
            subject="tool.philips_hue",
            capabilities=["device.lights.read", "device.lights.write"]
        )

    async def set_brightness(self, device_id: str, level: int) -> bool:
        response = await self.bridge.execute_connector(
            tool_id="philips_hue",
            action="set_brightness",
            parameters={"device_id": device_id, "brightness": level},
            token=self.token
        )
        return response.success
```

### 7.3 Bridge IFL → Physical Devices

Bridge owns IFL entirely - IFL Gateway, Core, and Adapters all live in Bridge:

```
K1 Tool ──► Bridge IFL Gateway ──► IFL Core ──► IFL Adapter ──► Physical Device
                   │                   │              │
                   │                   │              ├── HealthKitAdapter → Apple Watch
                   ├── Security        │              ├── HomeKitAdapter → Philips Hue
                   ├── Rate Limit      ├── Parser     ├── NestAdapter → Thermostat
                   ├── OAuth Check     ├── Translator ├── TeslaAdapter → Tesla API
                   └── Audit Log       └── Schemas    ├── SonosAdapter → Speakers
                                                      └── MqttAdapter → IoT Sensors
```

---

## 8. Example: "Night Mode On" End-to-End

User says: **"Enable night mode"**

```
Step 1: K1 Concierge receives user input
────────────────────────────────────────
Concierge FSM: DIALOGUE → Intent: night_routine
Creates workflow with sub-agents

Step 2: Planner creates parallel actions
────────────────────────────────────────
PlannerAgent outputs:
  - Action 1: LightingAgent → PhilipsHueTool.set_scene("night")
  - Action 2: ClimateAgent → NestTool.set_temperature(68)
  - Action 3: MusicAgent → SonosTool.play_ambient()

Step 3: Each tool calls Bridge (NOT devices directly)
────────────────────────────────────────

PhilipsHueTool.set_scene("night")
        │
        ▼
┌───────────────────────────────────────┐
│ Bridge.execute_connector()            │
├───────────────────────────────────────┤
│ 1. Validate PhilipsHueTool registered │   ✓
│ 2. Check OAuth token valid            │   ✓
│ 3. Check action "set_scene" allowed   │   ✓
│ 4. Check rate limit (< 60/min)        │   ✓
│ 5. Log to audit trail                 │   ✓
│ 6. Forward to K0 IFL                  │   ✓
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│ K0 IFL: HomeKitAdapter                │
│ Translates to Philips Hue Bridge API  │
│ PUT /api/groups/1/action              │
│ {"scene": "night"}                    │
└───────────────────────────────────────┘
        │
        ▼
Philips Hue Bridge → Lights dim to 20%

Step 4: Parallel execution for Nest and Sonos
────────────────────────────────────────
(Same flow through Bridge → IFL → Device)

Step 5: Responses aggregate back to Concierge
────────────────────────────────────────
Concierge: "Night mode enabled. Lights dimmed,
            temperature set to 68F, ambient music playing."
```

---

## 9. Directory Structure

```
bridge/
├── README.md                    # This file (source of truth)
├── __init__.py                  # Package exports
│
├── core/                        # Core bridge components
│   ├── __init__.py
│   ├── bridge.py                # Main Bridge class
│   ├── security.py              # CapabilityToken, signing
│   └── audit.py                 # Audit trail logging
│
├── kernel/                      # K0 ↔ K1 transport
│   ├── __init__.py
│   ├── query_port.py            # IKernelQueryPort implementation
│   ├── command_port.py          # IKernelCommandPort implementation
│   ├── sse_port.py              # IKernelSSEPort implementation
│   └── envelope.py              # Envelope builders
│
├── connector/                   # Tool → Device security
│   ├── __init__.py
│   ├── gateway.py               # IConnectorGatewayPort implementation
│   ├── registry.py              # Tool registration
│   ├── credentials.py           # OAuth/credential management
│   └── rate_limiter.py          # Rate limiting
│
├── codecs/                      # Serialization
│   ├── __init__.py
│   ├── json_codec.py            # JSON serialization
│   └── flatbuffer_codec.py      # FlatBuffer serialization
│
├── adapters/                    # Backend adapters
│   ├── __init__.py
│   ├── http_adapter.py          # HTTP transport to K0
│   ├── grpc_adapter.py          # gRPC transport (future)
│   └── mock_adapter.py          # Testing adapter
│
├── sync/                        # Multi-device family sync
│   ├── __init__.py
│   ├── discovery.py             # mDNS device discovery (Phase 1)
│   ├── crdt.py                  # CRDT merge engine (LWW)
│   ├── e2ee.py                  # End-to-end encryption (AES256-GCM)
│   ├── p2p.py                   # P2P internet tunnels (Phase 2)
│   ├── certificates.py          # Device certificate management (ED25519)
│   └── sync_port.py             # ISyncPort implementation
│
├── contracts/                   # Bridge contracts
│   ├── bridge.contract.yaml     # Module contract
│   └── schemas/                 # JSON/FlatBuffer schemas
│       ├── query_envelope.json
│       ├── command_envelope.json
│       └── connector_request.json
│
├── docs/                        # Documentation
│   ├── SECURITY.md              # Security model details
│   ├── INTEGRATION.md           # How to integrate
│   └── AUDIT.md                 # Audit trail format
│
└── tests/                       # Bridge tests
    ├── test_security.py
    ├── test_kernel_transport.py
    └── test_connector_gateway.py
```

---

## 10. Related Documents

| Document | Purpose |
| -------- | ------- |
| [k0/docs/ifl.md](../k0/docs/ifl.md) | Interkernel Fabric Language (IFL) details |
| [k1/sessionstate/README.md](../k1/sessionstate/README.md) | SessionState source of truth |
| [docs/plans/sessionstate-implementation-plan.md](../docs/plans/sessionstate-implementation-plan.md) | Implementation roadmap |
| [architecture_diagrams/k0/k0_with_interkernel_fabric.mmd](../architecture_diagrams/k0/k0_with_interkernel_fabric.mmd) | IFL architecture diagram |
| [architecture_diagrams/k0/k0_source_of_truth_postgresql.mmd](../architecture_diagrams/k0/k0_source_of_truth_postgresql.mmd) | K0 P07 Sync/CRDT pipeline |
| [governance/k0/k0_architecture_master.md](../governance/k0/k0_architecture_master.md) | K0 architecture master |
| [docs/architecture/decisions/0050c-multi-device-family-sync-strategy.md](../docs/architecture/decisions/0050c-multi-device-family-sync-strategy.md) | Multi-device sync ADR |

---

## 11. ADRs

| ADR | Title | Status |
| --- | ----- | ------ |
| ADR-0025 | K0-K1 Bridge Architecture | Planned |
| ADR-0026 | Connector Security Model | Planned |
| ADR-0027 | Capability Token Design | Planned |
| ADR-0028 | Audit Trail Requirements | Planned |
| [ADR-0050c](../docs/architecture/decisions/0050c-multi-device-family-sync-strategy.md) | Multi-Device Family Sync Strategy | Accepted |
| ADR-0029 | Device Certificate Management | Planned |
| ADR-0030 | CRDT Merge Strategy | Planned |

---

## 12. Implementation Status

| Component | Status | Notes |
| --------- | ------ | ----- |
| README.md | Done | This document |
| core/bridge.py | Planned | Main orchestrator |
| kernel/query_port.py | Planned | K0 query transport |
| kernel/command_port.py | Planned | K0 command transport |
| connector/gateway.py | Planned | Tool security gateway |
| connector/registry.py | Planned | Tool registration |
| security.py | Planned | Capability tokens |
| audit.py | Planned | Audit logging |
| sync/discovery.py | Planned (M2) | mDNS LAN discovery |
| sync/crdt.py | Planned (M2) | CRDT merge engine |
| sync/e2ee.py | Planned (M3) | E2EE encryption |
| sync/certificates.py | Planned (M3) | Device certificates |
| sync/p2p.py | Planned (M4) | P2P internet sync |

---

## 13. Development Priority

1. **Kernel Transport First** - K1 SessionState needs COLD tier archival
2. **Security Core** - Capability tokens, signing
3. **LAN Sync (Phase 1)** - mDNS discovery, CRDT merge, E2EE (M2-M3)
4. **Connector Gateway** - When workflows/tools are ready
5. **P2P Internet Sync (Phase 2)** - Remote device sync (M4-M5)
6. **IFL Integration** - Connect to K0 device adapters

---

*Created: 2026-02-01*
*Last Updated: 2026-02-01*
*Owner: Cross-Kernel Team*
