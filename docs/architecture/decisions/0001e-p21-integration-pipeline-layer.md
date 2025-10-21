# ADR-0001e: P21+ Integration Pipeline Layer

**Status:** ✅ **COMPLETED** (2025-10-12)
**Date:** 2025-10-12
**Last Updated:** 2025-10-12
**Deciders:** K1 Architecture Team
**Technical Story:** Define how K1 hosts third-party integrations (P21+ pipelines) while keeping K0 pure and stable
**Parent ADR:** [ADR-0001: K0/K1 Kernel Split](0001-k0-k1-kernel-split.md)
**Related ADRs:**
- [ADR-0001a: K0 Bridge Communication Protocol](0001a-k0-bridge-communication-protocol.md)
- [ADR-0002: Actor Model for Agent Isolation](0002-actor-model-agent-isolation.md)
- [ADR-0010: Capability-Based Security](0010-capability-based-security.md)

---

## Executive Summary

K1 Intelligence Module acts as an **integration host** for third-party services (P21+ pipelines) while K0 Memory Module remains **pure and frozen** (P01-P20 cognitive pipelines only). This ADR defines:

1. **Integration architecture:** P21+ hosted in K1, K0 remains stable with P01-P20 only
2. **Manifest-driven registration:** YAML manifests declare capabilities, permissions, versions
3. **Security architecture:** PEP enforcement, egress proxy, secrets management, capability-based access
4. **Sandboxing & isolation:** MCP/WASM/process-level isolation for untrusted integrations
5. **Lifecycle management:** Manifest loading, circuit breakers, DLQ, quarantine
6. **Example integrations:** P21-P30 (Philips Hue, Bank of America, Google Calendar, Weather, IoT, etc.)

**Key Principle:** K0 is the **cognitive core** (memory operations only, stable, frozen). K1 is the **extensible shell** (integrations, external services, evolving). This separation ensures K0 stability while enabling K1 extensibility.

**Design Inspiration:** Memory Kernel ADR-010 (Integration Pipeline Layer) - adapted for K1 hosting model.

---

## Context

### The Integration Challenge

**K1 Intelligence Module needs to integrate with external services:**
- **IoT Devices:** Smart lights (Philips Hue), thermostats (Nest), sensors
- **Cloud Services:** Google Calendar, Bank of America, Weather APIs
- **Voice Assistants:** Alexa, Google Home bridges
- **Health Devices:** Apple Health, Fitbit
- **Custom Extensions:** User-defined integrations (IFTTT-style automation)

**Problem: Where do integrations live?**

**Option 1: Integrations in K0 (memory_kernel ADR-010 original design)**
- ❌ **Problem:** K0 becomes bloated and unstable
- ❌ **Problem:** K0 pipeline count grows unbounded (P01-P∞)
- ❌ **Problem:** K0 security surface area expands (external API keys, OAuth)
- ❌ **Problem:** K0 version churn (integration updates break memory operations)

**Option 2: Integrations in K1 (this ADR's decision)**
- ✅ **Benefit:** K0 remains pure and stable (P01-P20 frozen)
- ✅ **Benefit:** K1 acts as integration host (sandboxed, isolated)
- ✅ **Benefit:** K1 security surface area isolated from K0
- ✅ **Benefit:** K1 can evolve rapidly, K0 evolves slowly

**Decision:** Host all third-party integrations (P21+) in K1, keep K0 frozen at P01-P20.

---

## Decision

We establish K1 as the **Integration Host** for P21+ pipelines:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   K1 Intelligence Module (Integration Host)             │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                  Integration Registry (Manifest-Driven)           │ │
│  │  ┌────────────────────────────────────────────────────────────┐  │ │
│  │  │  P21: Philips Hue (smart_light.yaml)                       │  │ │
│  │  │  P22: Bank of America (bank_oauth.yaml)                    │  │ │
│  │  │  P23: Google Calendar (calendar_oauth.yaml)                │  │ │
│  │  │  P24: Weather APIs (weather_api.yaml)                      │  │ │
│  │  │  P25: Map/Location APIs (maps_api.yaml)                    │  │ │
│  │  │  P26: IoT Sensors (iot_sensors.yaml)                       │  │ │
│  │  │  P27: Email Integration (email_oauth.yaml)                 │  │ │
│  │  │  P28: Voice Assistants (voice_bridge.yaml)                 │  │ │
│  │  │  P29: Health Devices (health_sync.yaml)                    │  │ │
│  │  │  P30: Custom Extensions (custom_*.yaml)                    │  │ │
│  │  └────────────────────────────────────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                  Integration Executor (Sandboxed)                 │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────┐  │ │
│  │  │  MCP Sandbox │  │ WASM Sandbox │  │Process Sandbox│  │ DLQ  │  │ │
│  │  │  (Model      │  │ (WebAssembly │  │ (Separate    │  │(Dead │  │ │
│  │  │   Context    │  │  isolation)  │  │  processes)  │  │Letter│  │ │
│  │  │   Protocol)  │  │              │  │              │  │Queue)│  │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────┘  │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                  Security Layer (PEP + Egress Proxy)              │ │
│  │  • PEP (Policy Evaluation Point): Capability checks              │ │
│  │  • Egress Proxy: Control outbound network access                 │ │
│  │  • Secrets Manager: API keys, OAuth tokens (encrypted at rest)   │ │
│  │  • Capability Model: Least privilege (declare upfront)           │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                  Lifecycle Manager (Circuit Breaker + Quarantine) │ │
│  │  • Manifest Loader: Load YAML manifests at startup/hot reload    │ │
│  │  • Circuit Breaker: 3 failures → open for 60s                    │ │
│  │  • Quarantine: Isolate misbehaving integrations                  │ │
│  │  • DLQ Retry: Exponential backoff (1s, 2s, 4s, 8s)               │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                  Observability (Metrics + Audit Log)              │ │
│  │  • Integration metrics (success rate, latency, errors)           │ │
│  │  • cognitive_trace_id propagation                                │ │
│  │  • Integration audit log (all calls logged)                      │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘

                                    ↓ Optional
                                    ↓ K0 Bridge Client (if integration needs memory)
                                    ↓ P01 (Query) or P02 (Write)

┌─────────────────────────────────────────────────────────────────────────┐
│                   K0 Memory Module (Pure Cognitive Core)                │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │  P01-P20: Core Cognitive Pipelines (FROZEN, STABLE)              │ │
│  │  • P01: RecallQuery (multi-store retrieval)                      │ │
│  │  • P02: MemoryWrite (episodic, semantic, procedural)             │ │
│  │  • P03-P20: Cognitive operations (affect, attention, working mem)│ │
│  │  • NO INTEGRATIONS (no P21+, no external APIs, no OAuth)         │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│  Characteristics:                                                       │
│  • Pure: Memory operations only, no external services                  │
│  • Stable: P01-P20 frozen, minimal version churn                       │
│  • Secure: No external API keys, no OAuth tokens                       │
│  • Reliable: No integration failures affect K0 operations              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Integration Architecture

### 1.1 Pipeline Allocation

| Pipeline Range | Hosted In | Purpose | Stability |
|----------------|-----------|---------|-----------|
| **P01-P20** | K0 Memory Module | Core cognitive operations | FROZEN (stable, rarely updated) |
| **P21-P30** | K1 Intelligence Module | First-party integrations | EVOLVING (frequent updates) |
| **P31+** | K1 Intelligence Module | Third-party/custom integrations | DYNAMIC (user-installed) |

### 1.2 K0 Pipelines (P01-P20) - FROZEN

**Purpose:** Pure memory operations, brain-inspired cognitive processes.

| Pipeline | Name | Purpose |
|----------|------|---------|
| **P01** | RecallQuery | Multi-store retrieval (FTS, Vector, KG, Episodic) |
| **P02** | MemoryWrite | Write to episodic, semantic, procedural memories |
| **P03** | AttentionGate | Thalamic filter (relevance, importance) |
| **P04** | HippocampusProcessing | DG→CA3→CA1 (pattern separation, completion) |
| **P05** | ProspectiveTriggers | Reminders, scheduled events |
| **P06** | FeedbackIntegration | Explicit/implicit/behavioral feedback |
| **P07** | Sync/CRDT | Multi-device sync, conflict resolution |
| **P08** | AffectModulation | Emotional bias, mood integration |
| **P09** | WorkingMemoryBoost | Recent memory prioritization |
| **P10** | PIIDetection | Privacy-sensitive data detection |
| **P11** | GoalManagement | Goal CRUD operations |
| **P12** | HabitTracking | Routine detection and reinforcement |
| **P13** | SocialBeliefUpdate | Theory of mind, relationship models |
| **P14** | SelfModelUpdate | Trait updates, preference learning |
| **P15** | ConsolidationScheduler | Memory consolidation (Hippocampus→Cortex) |
| **P16** | ForgetScheduler | Retention policies, archiving |
| **P17** | InferenceEngine | Implicit knowledge derivation |
| **P18** | PersonalizationSync | Persona state sync to K1 |
| **P19** | ObservabilityExport | Metrics, traces, logs |
| **P20** | HealthCheck | K0 liveness, readiness probes |

**Characteristics:**
- **No external dependencies** (no HTTP calls, no OAuth)
- **Deterministic** (same input → same output)
- **Fast** (<200ms P95 for Smart Lane)
- **Stable** (version frozen, minimal updates)

### 1.3 K1 Integrations (P21+) - EVOLVING

**Purpose:** Third-party integrations, external services, user-installed extensions.

| Pipeline | Name | Provider | Purpose |
|----------|------|----------|---------|
| **P21** | SmartLightControl | Philips Hue | Control smart lights (on/off, brightness, color) |
| **P22** | BankAccountSync | Bank of America | Fetch account balances, transactions (OAuth) |
| **P23** | CalendarSync | Google Calendar | Sync events, create reminders (OAuth) |
| **P24** | WeatherForecast | OpenWeatherMap | Fetch local weather data (API key) |
| **P25** | MapGeocoding | Google Maps | Geocoding, routing, location search (API key) |
| **P26** | IoTSensorData | Home IoT | Temperature, motion, energy sensors (MQTT) |
| **P27** | EmailIntegration | Gmail/Outlook | Send emails, fetch inbox (OAuth) |
| **P28** | VoiceBridge | Alexa/Google Home | Bridge to voice assistants (webhooks) |
| **P29** | HealthDataSync | Apple Health/Fitbit | Sync steps, sleep, heart rate (OAuth) |
| **P30** | CustomExtension | User-defined | IFTTT-style automation (user code) |
| **P31+** | Third-Party Apps | App Store | Marketplace integrations (sandboxed) |

**Characteristics:**
- **External dependencies** (HTTP APIs, OAuth, API keys)
- **Non-deterministic** (network failures, rate limits)
- **Slow** (<3000ms P95 timeout)
- **Evolving** (frequent updates, new integrations)

---

## 2. Manifest-Driven Registration

### 2.1 Integration Manifest Format

**File:** `integrations/philips_hue/smart_light.yaml`

```yaml
# Integration Manifest for Philips Hue Smart Lights
manifest_version: 1.0
integration_id: philips_hue_smart_light
name: "Philips Hue Smart Light Control"
version: 1.2.0
author: "K1 Team"
description: "Control Philips Hue smart lights (on/off, brightness, color)"

# Capabilities Required (Capability-Based Security)
capabilities:
  - network.http_client         # Outbound HTTP to Hue Bridge
  - secrets.read                # Read Hue Bridge API key
  - k0_memory.query             # Optional: Query K0 for user preferences

# Secrets (Encrypted at Rest)
secrets:
  - name: hue_bridge_api_key
    type: api_key
    description: "Philips Hue Bridge API key"
    required: true

# Configuration
configuration:
  hue_bridge_ip:
    type: string
    default: "192.168.1.100"
    description: "IP address of Philips Hue Bridge"

  timeout_ms:
    type: integer
    default: 3000
    description: "HTTP timeout in milliseconds"

# Sandboxing
sandboxing:
  type: process                # process | mcp | wasm
  max_memory_mb: 128           # Memory limit
  max_cpu_percent: 50          # CPU limit
  network_policy: egress_only  # Egress only (no inbound connections)

# Lifecycle
lifecycle:
  startup_order: 10            # Load after core integrations
  hot_reload: true             # Support hot reload without restart
  circuit_breaker:
    failure_threshold: 3       # Open circuit after 3 failures
    timeout_ms: 60000          # Wait 60s before retry

# Endpoints (exposed to K1 agents)
endpoints:
  - name: turn_on
    method: POST
    path: /lights/{light_id}/state
    parameters:
      - name: light_id
        type: integer
        required: true
      - name: brightness
        type: integer
        range: [0, 254]
        default: 254
      - name: color
        type: string
        enum: [red, green, blue, white]
        default: white
    timeout_ms: 3000

  - name: turn_off
    method: POST
    path: /lights/{light_id}/state
    parameters:
      - name: light_id
        type: integer
        required: true
    timeout_ms: 3000

# Observability
observability:
  metrics:
    - name: hue_api_calls_total
      type: counter
      labels: [endpoint, status]
    - name: hue_api_latency_ms
      type: histogram
      buckets: [100, 500, 1000, 3000]

  trace_propagation: true      # Propagate cognitive_trace_id

# Dependencies
dependencies:
  - integration_id: k0_bridge
    version: ">=1.0.0"
    optional: true
```

### 2.2 Manifest Loading Process

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 1: Manifest Discovery (Startup)                                   │
├─────────────────────────────────────────────────────────────────────────┤
│ K1 Integration Manager: Scan integrations/ directory                   │
│ Found: integrations/philips_hue/smart_light.yaml                       │
│ Found: integrations/bank_oauth/bank_account.yaml                       │
│ Found: integrations/google_calendar/calendar_sync.yaml                 │
│ ...                                                                     │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ Step 2: Manifest Validation (Schema Check)                             │
├─────────────────────────────────────────────────────────────────────────┤
│ Validate: smart_light.yaml against ManifestSchema v1.0                 │
│ Check: Required fields (integration_id, name, version, capabilities)   │
│ Check: Capabilities valid (network.http_client exists)                 │
│ Check: Sandboxing policy valid (process isolation supported)           │
│ Result: ✅ VALID                                                        │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ Step 3: Capability Approval (PEP Check)                                │
├─────────────────────────────────────────────────────────────────────────┤
│ Integration: philips_hue_smart_light                                   │
│ Capabilities Requested:                                                │
│   - network.http_client (APPROVED - standard integration capability)  │
│   - secrets.read (APPROVED - integration needs API key)               │
│   - k0_memory.query (APPROVED - optional, for user preferences)       │
│ PEP Decision: ✅ GRANT ALL                                             │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ Step 4: Secrets Loading (Encrypted Storage)                            │
├─────────────────────────────────────────────────────────────────────────┤
│ Secret Required: hue_bridge_api_key                                    │
│ Secrets Manager: Load from encrypted storage (AES-256)                 │
│ Secret Value: "<REDACTED>" (logged as [REDACTED])                      │
│ Inject: Environment variable HUE_BRIDGE_API_KEY                        │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ Step 5: Sandbox Initialization (Process Isolation)                     │
├─────────────────────────────────────────────────────────────────────────┤
│ Sandboxing Type: process (separate process per integration)            │
│ Spawn: integrations/philips_hue/main.py (Python subprocess)            │
│ Limits: max_memory_mb=128, max_cpu_percent=50                          │
│ Network Policy: egress_only (outbound HTTP only)                       │
│ Process ID: 12345                                                       │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ Step 6: Integration Registration (Endpoints Exposed)                   │
├─────────────────────────────────────────────────────────────────────────┤
│ Register Endpoints:                                                    │
│   - POST /integrations/philips_hue/turn_on                             │
│   - POST /integrations/philips_hue/turn_off                            │
│ Timeout: 3000ms per call                                               │
│ Circuit Breaker: 3 failures → open for 60s                             │
│ Status: ✅ READY                                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Security Architecture

### 3.1 Policy Evaluation Point (PEP)

**Purpose:** Enforce capability-based access control at K1 ingress.

**PEP Decision Flow:**
```
┌─────────────────────────────────────────────────────────────────────────┐
│ Integration Request                                                     │
├─────────────────────────────────────────────────────────────────────────┤
│ Integration: philips_hue_smart_light                                   │
│ Action: HTTP POST to Hue Bridge (192.168.1.100:80)                     │
│ Capability Required: network.http_client                               │
│                                                                         │
│ PEP Check:                                                              │
│ 1. Is "network.http_client" in integration manifest? ✅ YES             │
│ 2. Is "network.http_client" approved by user? ✅ YES                    │
│ 3. Is destination IP allowed (egress_only policy)? ✅ YES (192.168.*)   │
│                                                                         │
│ PEP Decision: ✅ ALLOW                                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

**Capability Types:**

| Capability | Purpose | Risk Level |
|------------|---------|------------|
| **network.http_client** | Outbound HTTP requests | MEDIUM |
| **network.mqtt_client** | MQTT pub/sub (IoT) | MEDIUM |
| **secrets.read** | Read API keys, OAuth tokens | HIGH |
| **k0_memory.query** | Query K0 (P01) | HIGH |
| **k0_memory.write** | Write to K0 (P02) | HIGH |
| **filesystem.read** | Read files (sandboxed) | LOW |
| **filesystem.write** | Write files (sandboxed) | MEDIUM |
| **custom_code.execute** | Execute user code (WASM) | HIGH |

### 3.2 Egress Proxy

**Purpose:** Control outbound network access from integrations.

**Egress Proxy Rules:**
```yaml
# Egress Proxy Configuration
egress_policy:
  default: deny                # Default deny all outbound connections

  allow_list:
    - integration: philips_hue_smart_light
      destinations:
        - 192.168.1.100:80     # Hue Bridge (local network)
        - 192.168.1.0/24:*     # Entire local network (any port)

    - integration: bank_oauth
      destinations:
        - api.bankofamerica.com:443   # Bank API (HTTPS only)

    - integration: google_calendar
      destinations:
        - www.googleapis.com:443      # Google APIs (HTTPS only)

    - integration: weather_api
      destinations:
        - api.openweathermap.org:443  # Weather API (HTTPS only)
```

**Egress Proxy Enforcement:**
```
Integration → Egress Proxy → Destination
            ↓ Check allow_list
            ↓ If allowed: Forward request
            ↓ If denied: Return 403 Forbidden
```

### 3.3 Secrets Management

**Purpose:** Securely store API keys, OAuth tokens for integrations.

**Secrets Storage:**
- **Encryption:** AES-256-GCM (Galois/Counter Mode)
- **Key Derivation:** PBKDF2 (100,000 iterations, SHA-256)
- **Storage:** SQLite encrypted database (`secrets.db`)
- **Access:** Capability-based (integrations with `secrets.read` capability only)

**Secrets API:**
```python
# Secrets Manager API
class SecretsManager:
    def store_secret(self, integration_id: str, secret_name: str, secret_value: str):
        """Store secret (encrypted at rest)"""
        encrypted_value = aes_gcm_encrypt(secret_value, self.master_key)
        self.db.execute(
            "INSERT INTO secrets (integration_id, secret_name, encrypted_value) VALUES (?, ?, ?)",
            (integration_id, secret_name, encrypted_value)
        )

    def load_secret(self, integration_id: str, secret_name: str) -> str:
        """Load secret (decrypt on read)"""
        # Check capability: integration has secrets.read permission
        if not self.pep.check_capability(integration_id, "secrets.read"):
            raise PermissionError(f"Integration {integration_id} lacks secrets.read capability")

        row = self.db.execute(
            "SELECT encrypted_value FROM secrets WHERE integration_id=? AND secret_name=?",
            (integration_id, secret_name)
        ).fetchone()

        if not row:
            raise ValueError(f"Secret {secret_name} not found for integration {integration_id}")

        return aes_gcm_decrypt(row[0], self.master_key)
```

---

## 4. Sandboxing & Isolation

### 4.1 Sandbox Types

| Sandbox Type | Isolation Level | Performance | Use Case |
|--------------|-----------------|-------------|----------|
| **MCP (Model Context Protocol)** | MEDIUM | Fast | Trusted integrations (LLM tools) |
| **WASM (WebAssembly)** | HIGH | Fast | User code, custom extensions |
| **Process** | HIGH | Medium | Third-party binaries, OAuth services |

### 4.2 MCP Sandboxing

**Purpose:** Sandbox LLM tool calls (e.g., calendar.get, email.send) using MCP protocol.

**MCP Architecture:**
```
K1 Agent (LLM) → MCP Gateway → MCP Server (Integration) → External Service
              ↓ JSON-RPC 2.0
              ↓ Tool call schema validation
              ↓ Capability check (PEP)
```

**Example: Google Calendar Integration (MCP)**
```json
// MCP Tool Call (JSON-RPC 2.0)
{
  "jsonrpc": "2.0",
  "method": "calendar.create_event",
  "params": {
    "summary": "Emma's soccer practice",
    "start": "2024-10-16T16:00:00Z",
    "end": "2024-10-16T17:00:00Z",
    "location": "Riverside Park"
  },
  "id": 1
}

// MCP Response
{
  "jsonrpc": "2.0",
  "result": {
    "event_id": "evt_abc123",
    "status": "confirmed"
  },
  "id": 1
}
```

### 4.3 WASM Sandboxing

**Purpose:** Sandbox user-defined code (custom extensions) using WebAssembly.

**WASM Architecture:**
```
K1 Integration Host → WASM Runtime (Wasmtime) → User Code (WASM) → Restricted API
                    ↓ Memory isolation
                    ↓ No network access (unless capability granted)
                    ↓ No file system access (unless capability granted)
```

**Example: Custom Extension (WASM)**
```rust
// User-defined custom extension (Rust compiled to WASM)
#[wasm_bindgen]
pub fn custom_logic(input: String) -> String {
    // User code runs in WASM sandbox
    // Limited to: CPU, memory (128MB), no network, no file system
    let processed = input.to_uppercase();
    format!("Processed: {}", processed)
}
```

### 4.4 Process-Level Isolation

**Purpose:** Sandbox third-party binaries (OAuth services, bank APIs) in separate processes.

**Process Isolation:**
```
K1 Integration Host → Spawn subprocess → Integration binary → External Service
                    ↓ Resource limits (cgroups)
                    ↓ Network policy (iptables)
                    ↓ Seccomp filter (syscall restrictions)
```

**Resource Limits (cgroups):**
- **Memory:** 128MB per integration
- **CPU:** 50% of one core
- **Network:** Egress only (no inbound connections)
- **File System:** Read-only except `/tmp` (sandboxed)

---

## 5. Lifecycle Management

### 5.1 Circuit Breaker

**Purpose:** Isolate failing integrations to prevent cascading failures.

**Circuit Breaker States:**
```
CLOSED (normal) → OPEN (3 failures) → HALF-OPEN (test recovery) → CLOSED
                ↓ 60s timeout
                ↓ Retry
```

**Example: Philips Hue Circuit Breaker**
```
Turn 1: Call Hue API → Timeout (3000ms) → Failure 1
Turn 2: Call Hue API → Timeout (3000ms) → Failure 2
Turn 3: Call Hue API → Timeout (3000ms) → Failure 3 → Circuit OPEN
Turn 4-10: Circuit OPEN, return error immediately (no API call)
Turn 11 (60s later): Circuit HALF-OPEN, retry API call
  - Success → Circuit CLOSED (normal operation)
  - Failure → Circuit OPEN (wait another 60s)
```

### 5.2 Dead Letter Queue (DLQ)

**Purpose:** Retry failed integration calls with exponential backoff.

**DLQ Retry Policy:**
```
Failure → DLQ → Retry after 1s → Failure → Retry after 2s → Failure → Retry after 4s → Failure → Retry after 8s → Give up
```

**Example: Bank API Call Failed**
```
Turn 1: Call Bank API → Network error → Send to DLQ
DLQ: Retry after 1s → Network error → Send to DLQ
DLQ: Retry after 2s → Network error → Send to DLQ
DLQ: Retry after 4s → Network error → Send to DLQ
DLQ: Retry after 8s → Network error → Give up, log error
```

### 5.3 Quarantine Mechanism

**Purpose:** Isolate misbehaving integrations (excessive failures, resource abuse).

**Quarantine Triggers:**
- **Excessive failures:** >10 failures in 1 minute
- **Resource abuse:** Memory >128MB, CPU >50% sustained
- **Security violations:** Attempting to access unauthorized capabilities

**Quarantine Actions:**
1. Kill integration process
2. Move manifest to `integrations_quarantined/`
3. Notify user: "Philips Hue integration quarantined due to excessive failures"
4. Require user approval to re-enable

---

## 6. Example Integrations

### 6.1 P21: Philips Hue Smart Light Control

**Manifest:** `integrations/philips_hue/smart_light.yaml`

**Endpoints:**
- `POST /integrations/philips_hue/turn_on` - Turn on light (brightness, color)
- `POST /integrations/philips_hue/turn_off` - Turn off light

**Example Usage (K1 Agent):**
```python
# Planner Agent calls Philips Hue integration
response = await integration_client.call(
    integration_id="philips_hue_smart_light",
    endpoint="turn_on",
    params={"light_id": 1, "brightness": 200, "color": "warm_white"}
)
# Response: {"status": "success", "light_id": 1, "state": "on"}
```

### 6.2 P22: Bank of America Account Sync (OAuth)

**Manifest:** `integrations/bank_oauth/bank_account.yaml`

**OAuth Flow:**
1. User initiates: "Link my bank account"
2. K1 redirects to Bank of America OAuth consent page
3. User approves, Bank returns authorization code
4. K1 exchanges code for access token (stored in Secrets Manager)
5. K1 can now fetch account balances, transactions

**Endpoints:**
- `GET /integrations/bank_oauth/accounts` - List accounts
- `GET /integrations/bank_oauth/transactions?account_id=123` - Get transactions

**Example Usage:**
```python
# Researcher Agent fetches bank balance
response = await integration_client.call(
    integration_id="bank_oauth",
    endpoint="accounts",
    params={}
)
# Response: {"accounts": [{"id": "123", "name": "Checking", "balance": 5432.10}]}
```

### 6.3 P23: Google Calendar Sync (OAuth)

**Manifest:** `integrations/google_calendar/calendar_sync.yaml`

**OAuth Flow:** (Similar to Bank of America)

**Endpoints:**
- `GET /integrations/google_calendar/events` - List upcoming events
- `POST /integrations/google_calendar/create_event` - Create new event
- `DELETE /integrations/google_calendar/delete_event?event_id=abc` - Delete event

**Example Usage:**
```python
# Planner Agent creates calendar event
response = await integration_client.call(
    integration_id="google_calendar",
    endpoint="create_event",
    params={
        "summary": "Emma's soccer practice",
        "start": "2024-10-16T16:00:00Z",
        "end": "2024-10-16T17:00:00Z",
        "location": "Riverside Park"
    }
)
# Response: {"event_id": "evt_abc123", "status": "confirmed"}
```

---

## Consequences

### Positive ✅

**✅ K0 Stability:**
- K0 remains pure (P01-P20 only, no integrations)
- K0 security surface area minimal (no API keys, no OAuth)
- **Result:** K0 can be frozen, minimal version churn

**✅ K1 Extensibility:**
- K1 hosts all integrations (P21+)
- Manifest-driven registration (transparent, auditable)
- **Result:** Easy to add new integrations without K0 changes

**✅ Security Isolation:**
- PEP enforces capability-based access
- Egress proxy controls outbound network
- Secrets encrypted at rest
- **Result:** Production-grade security for untrusted integrations

**✅ Sandboxing:**
- MCP/WASM/process isolation
- Resource limits (memory, CPU, network)
- **Result:** Misbehaving integrations cannot crash K1

**✅ Resilience:**
- Circuit breakers isolate failures
- DLQ retries failed calls
- Quarantine mechanism removes bad integrations
- **Result:** K1 remains operational even with failing integrations

**✅ Observability:**
- Integration metrics (success rate, latency, errors)
- cognitive_trace_id propagation
- **Result:** Full visibility into integration health

---

### Negative ⚠️

**⚠️ Integration Complexity:**
- Manifest-driven registration adds overhead
- Developers must declare capabilities upfront
- **Mitigation:** Provide manifest templates, examples, CLI tooling for manifest generation

**⚠️ Performance Overhead:**
- Process isolation adds latency (~10ms per call)
- WASM compilation adds startup delay (~100ms)
- **Mitigation:** Use MCP for low-latency integrations, cache WASM modules

**⚠️ Secrets Management:**
- Storing API keys, OAuth tokens in encrypted database
- Key rotation requires user re-authentication
- **Mitigation:** Automated key rotation for supported providers, user notification for manual rotation

**⚠️ OAuth Flow Complexity:**
- OAuth redirect flow requires web server (K1 API Gateway)
- Token refresh logic required for long-lived integrations
- **Mitigation:** OAuth library abstracts complexity, automatic token refresh

**⚠️ Integration Versioning:**
- Manifest versioning adds complexity
- Deprecation policy required for breaking changes
- **Mitigation:** Semantic versioning (1.0.0 → 2.0.0), deprecation notices (90-day warning)

---

## Summary

**P21+ Integration Pipeline Layer Complete** ✅

K1 Intelligence Module acts as **integration host** for third-party services (P21+), keeping K0 Memory Module **pure and stable** (P01-P20 only). Architecture includes:

1. **Integration Architecture:** P21+ in K1, P01-P20 in K0 (frozen)
2. **Manifest-Driven Registration:** YAML manifests declare capabilities, permissions, versions
3. **Security Architecture:** PEP enforcement, egress proxy, secrets management, capability-based access
4. **Sandboxing:** MCP/WASM/process isolation with resource limits
5. **Lifecycle Management:** Circuit breakers, DLQ, quarantine for resilience
6. **Example Integrations:** Philips Hue, Bank of America OAuth, Google Calendar OAuth

**Status:** Architecture approved, ready for Phase 3 implementation (Weeks 10-15).

**Key Resources:**
- [ADR-0001a: K0 Bridge Communication Protocol](0001a-k0-bridge-communication-protocol.md)
- [ADR-0002: Actor Model for Agent Isolation](0002-actor-model-agent-isolation.md)
- [ADR-0010: Capability-Based Security](0010-capability-based-security.md)

---

## Implementation

### Phase 1: Manifest System & PEP (Weeks 10-11)
- [ ] Define manifest schema (YAML v1.0)
- [ ] Implement manifest loader (validation, capability approval)
- [ ] Implement PEP (Policy Evaluation Point)
- [ ] Implement Secrets Manager (AES-256-GCM encryption)
- [ ] Unit tests (WARD framework)

### Phase 2: Sandboxing & Isolation (Weeks 12-13)
- [ ] Implement MCP sandboxing (JSON-RPC 2.0)
- [ ] Implement WASM sandboxing (Wasmtime runtime)
- [ ] Implement process isolation (cgroups, iptables, seccomp)
- [ ] Implement egress proxy (allow_list enforcement)
- [ ] Integration tests

### Phase 3: Lifecycle & Sample Integrations (Weeks 14-15)
- [ ] Implement circuit breaker (3 failures → open for 60s)
- [ ] Implement DLQ (exponential backoff: 1s, 2s, 4s, 8s)
- [ ] Implement quarantine mechanism
- [ ] Create 4 sample integrations:
  - P21: Philips Hue (smart lights, local network)
  - P22: Bank of America (OAuth, financial data)
  - P23: Google Calendar (OAuth, event sync)
  - P24: Weather API (OpenWeatherMap, API key)
- [ ] Integration tests with K0 Bridge Client
- [ ] Performance benchmarking (<3000ms P95 per integration call)

---

## Success Metrics

**Performance:**
- ✅ Integration call latency <3000ms P95
- ✅ Circuit breaker recovery <60s
- ✅ DLQ retry latency: 1s, 2s, 4s, 8s (exponential backoff)
- ✅ Manifest loading <100ms (startup)

**Security:**
- ✅ PEP capability enforcement (100% of calls checked)
- ✅ Egress proxy enforcement (100% of outbound requests filtered)
- ✅ Secrets encrypted at rest (AES-256-GCM)
- ✅ Sandboxing active (MCP/WASM/process isolation)

**Resilience:**
- ✅ Circuit breaker isolation (failing integrations don't crash K1)
- ✅ DLQ success rate >90% (after retries)
- ✅ Quarantine mechanism (misbehaving integrations removed)

**Observability:**
- ✅ Integration metrics (success rate, latency, errors) exported to Prometheus
- ✅ cognitive_trace_id propagated through all integration calls
- ✅ Integration audit log (all calls logged with trace ID)

---

## References

- [ADR-0001: K0/K1 Kernel Split](0001-k0-k1-kernel-split.md)
- [ADR-0001a: K0 Bridge Communication Protocol](0001a-k0-bridge-communication-protocol.md)
- [ADR-0002: Actor Model for Agent Isolation](0002-actor-model-agent-isolation.md)
- [ADR-0010: Capability-Based Security](0010-capability-based-security.md)
- [Memory Kernel ADR-010: Integration Pipeline Layer](https://github.com/your-org/memory_kernel/docs/adr-010)
- [Model Context Protocol (MCP) Specification](https://modelcontextprotocol.io)
- [WebAssembly System Interface (WASI)](https://wasi.dev)

---

**Document Version:** 1.0
**Status:** Completed
**Next Review:** 2025-10-26 (after Phase 1 implementation)
