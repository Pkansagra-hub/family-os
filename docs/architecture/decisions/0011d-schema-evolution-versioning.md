---
adr_number: 0011d
title: Schema Evolution & Versioning
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer3_execution
- layer4_runtime
affected_modules: []
concerns:
- architecture
- compliance
- modularity
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0011
- ADR-0011a
- ADR-0011b
- ADR-0011c
- ADR-0011d
implementation_status: REJECTED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0011
  - ADR-0011a
  - ADR-0011b
  - ADR-0011c
  - ADR-0011d
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  affected_tests: []
---


# ADR-0011d: Schema Evolution & Versioning

**Status:** Accepted
**Date:** 2025-10-12
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0011: FlatBuffers Serialization](./0011-flatbuffers-serialization.md)

---

## Context

K1 Intelligence Module evolves rapidly with:
- **Frequent releases:** 2-week sprint cycles
- **Multiple deployments:** K1 runtime, K0 kernel, MCP servers, client applications
- **Long-lived sessions:** User sessions span hours/days
- **Backwards compatibility:** Old clients must work with new servers

**Schema Evolution Requirements:**
1. **Backward compatibility:** New code reads old data
2. **Forward compatibility:** Old code reads new data (ignore unknown fields)
3. **Field deprecation:** Gradual removal without breaking changes
4. **Version negotiation:** K1 ↔ K0 ↔ Clients agree on schema versions

This ADR defines schema evolution policies to ensure K1 maintains compatibility across releases.

---

## Decision

### 1. Schema Versioning Strategy

#### 1.1 File Identifier (4-Character Code)

**Principle:** Every root table has a 4-character file identifier for version validation.

**Format:** 4 uppercase ASCII characters (letters or digits)

**Purpose:**
1. **Schema validation:** Verify buffer contains expected schema
2. **Version identification:** Map file identifier to schema version
3. **Error handling:** Reject buffers with wrong identifier

**Example:**
```fbs
namespace k1.agent_fabric;

table AgentState {
  agent_id: string;
  state: AgentLifecycleState;
  memory_mb: uint32;
}

file_identifier "AGST";  // AGent STate
root_type AgentState;
```

**Validation:**
```python
import flatbuffers
from k1.schemas.generated.python.k1.agent_fabric import AgentState

def deserialize_agent_state(buf: bytes) -> AgentState.AgentState:
    """Deserialize AgentState with validation"""
    # Check file identifier (first 4 bytes after root offset)
    if len(buf) < 8:
        raise ValueError("Buffer too small")

    file_id = buf[4:8]
    if file_id != b"AGST":
        raise ValueError(f"Invalid file identifier: {file_id} (expected: AGST)")

    # Deserialize (zero-copy)
    return AgentState.AgentState.GetRootAs(buf, 0)
```

#### 1.2 Schema Version Registry

**Registry:** Map file identifiers to schema versions

**File:** `k1/schemas/SCHEMA_VERSIONS.md`

**Format:**
```markdown
# K1 FlatBuffers Schema Version Registry

| File ID | Schema | Version | Introduced | Deprecated | Removed |
|---------|--------|---------|------------|------------|---------|
| AGST | AgentState | 1.0 | v0.1.0 | - | - |
| AGST | AgentState | 1.1 | v0.3.0 | - | - |
| AGST | AgentState | 1.2 | v0.5.0 | - | - |
| TASK | TaskAnnouncement | 1.0 | v0.1.0 | - | - |
| PROP | Proposal | 1.0 | v0.1.0 | - | - |
| SELN | Selection | 1.0 | v0.1.0 | - | - |
| PLSK | PlanSketch | 1.0 | v0.2.0 | - | - |
| BLFS | Beliefs | 1.0 | v0.1.0 | - | - |
| SCBD | Scoreboard | 1.0 | v0.1.0 | - | - |
| ... | ... | ... | ... | ... | ... |
```

**Version Format:** `{major}.{minor}`
- **Major version:** Incompatible changes (extremely rare, requires migration)
- **Minor version:** Compatible changes (new fields, deprecations)

#### 1.3 Root Type Declaration

**Principle:** Explicitly declare root table type in every schema file.

**Syntax:** `root_type {TableName};`

**Purpose:**
1. **Code generation:** Generates `GetRootAs{TableName}()` helper
2. **Documentation:** Clarifies which table is the entry point
3. **Validation:** Compiler ensures root type exists

**Example:**
```fbs
namespace k1.session_state;

table SessionState {
  session_id: string;
  beliefs: Beliefs;
  scoreboard: Scoreboard;
}

table Beliefs { /* ... */ }
table Scoreboard { /* ... */ }

file_identifier "SEST";
root_type SessionState;  // Explicit root declaration
```

---

### 2. Backward Compatibility Rules

#### 2.1 Allowed Changes (Backward Compatible)

**✅ Add optional field with default value:**
```fbs
// Version 1.0
table AgentState {
  agent_id: string;
  state: AgentLifecycleState;
}

// Version 1.1 (backward compatible)
table AgentState {
  agent_id: string;
  state: AgentLifecycleState;
  memory_mb: uint32 = 0;  // New field with default
}
```

**New code reads old data:**
```python
# Old buffer (v1.0): {agent_id: "xyz", state: ACTIVE}
# New code (v1.1):
state = AgentState.AgentState.GetRootAs(old_buf, 0)
print(state.MemoryMb())  # Returns 0 (default value)
```

**✅ Add new enum value at end:**
```fbs
// Version 1.0
enum AgentLifecycleState : uint8 {
  PENDING = 0,
  WARMING = 1,
  ACTIVE = 2
}

// Version 1.1 (backward compatible)
enum AgentLifecycleState : uint8 {
  PENDING = 0,
  WARMING = 1,
  ACTIVE = 2,
  IDLE = 3,      // New value
  DRAINING = 4,  // New value
  TERMINATED = 5 // New value
}
```

**✅ Add new table type:**
```fbs
// Version 1.0
table AgentState { /* ... */ }

// Version 1.1 (backward compatible)
table AgentState { /* ... */ }
table AgentMetrics { /* ... */ }  // New table
```

**✅ Add new union variant:**
```fbs
// Version 1.0
union PlanNodeType {
  LLMInference,
  ToolCall
}

// Version 1.1 (backward compatible)
union PlanNodeType {
  LLMInference,
  ToolCall,
  MemoryRead,   // New variant
  MemoryWrite   // New variant
}
```

**✅ Mark field as deprecated:**
```fbs
// Version 1.1
table AgentState {
  agent_id: string;
  state: AgentLifecycleState;
  memory_mb: uint32 (deprecated);  // Mark deprecated
  memory_bytes: uint64 = 0;        // Add replacement
}
```

#### 2.2 Forbidden Changes (Breaking Compatibility)

**❌ Remove field:**
```fbs
// Version 1.0
table AgentState {
  agent_id: string;
  state: AgentLifecycleState;
  memory_mb: uint32;
}

// Version 1.1 (BREAKING!)
table AgentState {
  agent_id: string;
  state: AgentLifecycleState;
  // memory_mb removed - BREAKS OLD CODE
}
```

**Impact:** Old code expects `memory_mb` field, crashes when accessing it.

**❌ Rename field:**
```fbs
// Version 1.0
table AgentState {
  agent_id: string;
}

// Version 1.1 (BREAKING!)
table AgentState {
  id: string;  // Renamed from agent_id - BREAKS OLD CODE
}
```

**Impact:** Old code looks for `agent_id`, finds nothing.

**❌ Change field type:**
```fbs
// Version 1.0
table AgentState {
  memory_mb: uint32;
}

// Version 1.1 (BREAKING!)
table AgentState {
  memory_mb: uint64;  // Changed type - BREAKS OLD CODE
}
```

**Impact:** Old code expects 32-bit int, reads 64-bit int incorrectly.

**❌ Remove enum value:**
```fbs
// Version 1.0
enum AgentLifecycleState : uint8 {
  PENDING = 0,
  WARMING = 1,
  ACTIVE = 2,
  DEPRECATED_STATE = 3
}

// Version 1.1 (BREAKING!)
enum AgentLifecycleState : uint8 {
  PENDING = 0,
  WARMING = 1,
  ACTIVE = 2
  // DEPRECATED_STATE removed - BREAKS OLD CODE
}
```

**Impact:** Old buffers with `DEPRECATED_STATE = 3` become invalid.

**❌ Change enum value:**
```fbs
// Version 1.0
enum AgentLifecycleState : uint8 {
  PENDING = 0,
  ACTIVE = 1
}

// Version 1.1 (BREAKING!)
enum AgentLifecycleState : uint8 {
  PENDING = 0,
  ACTIVE = 2  // Changed value - BREAKS OLD CODE
}
```

---

### 3. Forward Compatibility Rules

#### 3.1 Ignore Unknown Fields

**Principle:** Old code reading new data ignores unknown fields.

**Example:**
```fbs
// Version 1.0
table AgentState {
  agent_id: string;
  state: AgentLifecycleState;
}

// Version 1.1 (adds new fields)
table AgentState {
  agent_id: string;
  state: AgentLifecycleState;
  memory_mb: uint32 = 0;        // Unknown to v1.0
  capabilities: [Capability];   // Unknown to v1.0
}
```

**Old code (v1.0) reads new buffer (v1.1):**
```python
# New buffer (v1.1): {agent_id: "xyz", state: ACTIVE, memory_mb: 512, capabilities: [...]}
# Old code (v1.0):
state = AgentState.AgentState.GetRootAs(new_buf, 0)
print(state.AgentId())  # "xyz" - works
print(state.State())    # ACTIVE - works
# state.MemoryMb() - method doesn't exist in v1.0, never called
```

**FlatBuffers Mechanism:** Unknown fields are stored in vtable but never accessed by old code.

#### 3.2 Default Values for Missing Fields

**Principle:** New code reading old data uses default values for missing fields.

**Example:**
```python
# Old buffer (v1.0): {agent_id: "xyz", state: ACTIVE}
# New code (v1.1):
state = AgentState.AgentState.GetRootAs(old_buf, 0)
print(state.MemoryMb())  # Returns 0 (default value, field not in old buffer)
```

**FlatBuffers Mechanism:** Vtable lookup returns offset 0 for missing field → use default value.

#### 3.3 Handling Unknown Enum Values

**Principle:** Old code treats unknown enum values as invalid.

**Example:**
```fbs
// Version 1.0
enum AgentLifecycleState : uint8 {
  PENDING = 0,
  ACTIVE = 1
}

// Version 1.1
enum AgentLifecycleState : uint8 {
  PENDING = 0,
  ACTIVE = 1,
  IDLE = 2  // Unknown to v1.0
}
```

**Old code (v1.0) reads new buffer (v1.1 with IDLE state):**
```python
# New buffer: {agent_id: "xyz", state: 2 (IDLE)}
# Old code:
state = AgentState.AgentState.GetRootAs(new_buf, 0)
state_value = state.State()  # Returns 2

# Old code doesn't recognize 2 (IDLE)
if state_value == AgentLifecycleState.PENDING:
    print("Pending")
elif state_value == AgentLifecycleState.ACTIVE:
    print("Active")
else:
    print(f"Unknown state: {state_value}")  # Prints "Unknown state: 2"
```

**Mitigation:** Always have a default/fallback case for unknown enum values.

---

### 4. Field Deprecation Policy

#### 4.1 3-Release Grace Period

**Timeline:**
1. **Release N:** Add new field, mark old field as `(deprecated)`, update docs
2. **Release N+1:** Emit warnings when old field is accessed (optional)
3. **Release N+2:** Remove old field from generated code (schema file remains)
4. **Release N+3:** Remove old field from schema file

**Example:**

**Release v0.3.0 (Release N):**
```fbs
table AgentState {
  agent_id: string;
  state: AgentLifecycleState;
  memory_mb: uint32 (deprecated);  // Deprecated in v0.3.0
  memory_bytes: uint64 = 0;        // Added in v0.3.0
}
```

**Release v0.5.0 (Release N+1):**
```python
# Optional: Emit deprecation warnings
def get_memory_mb(state: AgentState) -> int:
    warnings.warn(
        "memory_mb is deprecated since v0.3.0, use memory_bytes instead",
        DeprecationWarning,
        stacklevel=2
    )
    return state.MemoryMb()
```

**Release v0.7.0 (Release N+2):**
```fbs
# Schema file still has memory_mb, but generated code omits it
table AgentState {
  agent_id: string;
  state: AgentLifecycleState;
  memory_mb: uint32 (deprecated);  # Still in schema for compatibility
  memory_bytes: uint64 = 0;
}
```

**Release v0.9.0 (Release N+3):**
```fbs
# Remove from schema file after 3 releases
table AgentState {
  agent_id: string;
  state: AgentLifecycleState;
  memory_bytes: uint64 = 0;
}
```

#### 4.2 Deprecation Documentation

**Changelog Entry:**
```markdown
## v0.3.0 (2025-10-12)

### Deprecated
- **AgentState.memory_mb:** Deprecated in favor of `memory_bytes` (uint64) for better precision. Will be removed in v0.9.0 (3 releases).

### Added
- **AgentState.memory_bytes:** Memory allocated in bytes (uint64). Use instead of `memory_mb`.
```

**Migration Guide:**
```markdown
# Migration Guide: AgentState.memory_mb → memory_bytes

## Old Code (v0.2.0)
```python
state = AgentState.AgentState.GetRootAs(buf, 0)
memory_mb = state.MemoryMb()  # uint32
```

## New Code (v0.3.0+)
```python
state = AgentState.AgentState.GetRootAs(buf, 0)
memory_bytes = state.MemoryBytes()  # uint64
memory_mb = memory_bytes // (1024 * 1024)  # Convert to MB if needed
```

## Compatibility
- **v0.3.0-v0.7.0:** Both `memory_mb` and `memory_bytes` available
- **v0.9.0+:** Only `memory_bytes` available
```

---

### 5. Migration Tooling

#### 5.1 Schema Diff Tool

**Purpose:** Detect changes between schema versions.

**Script:** `scripts/schema_diff.py`

```python
#!/usr/bin/env python3
"""Schema diff tool for FlatBuffers"""

import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Any

def parse_schema(schema_path: Path) -> Dict[str, Any]:
    """Parse FlatBuffers schema to JSON AST"""
    result = subprocess.run(
        ["flatc", "--schema", "--json", str(schema_path)],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise ValueError(f"Failed to parse {schema_path}: {result.stderr}")
    return json.loads(result.stdout)

def diff_tables(old_table: Dict, new_table: Dict) -> List[str]:
    """Compare two table definitions"""
    changes = []

    # Check field changes
    old_fields = {f["name"]: f for f in old_table.get("fields", [])}
    new_fields = {f["name"]: f for f in new_table.get("fields", [])}

    # Added fields
    added = set(new_fields.keys()) - set(old_fields.keys())
    for field_name in added:
        changes.append(f"  + Added field: {field_name} ({new_fields[field_name]['type']})")

    # Removed fields (BREAKING)
    removed = set(old_fields.keys()) - set(new_fields.keys())
    for field_name in removed:
        changes.append(f"  - BREAKING: Removed field: {field_name}")

    # Changed field types (BREAKING)
    for field_name in set(old_fields.keys()) & set(new_fields.keys()):
        old_type = old_fields[field_name]["type"]
        new_type = new_fields[field_name]["type"]
        if old_type != new_type:
            changes.append(f"  ! BREAKING: Changed {field_name} type: {old_type} -> {new_type}")

    return changes

def main():
    if len(sys.argv) != 3:
        print("Usage: schema_diff.py <old_schema.fbs> <new_schema.fbs>")
        sys.exit(1)

    old_path = Path(sys.argv[1])
    new_path = Path(sys.argv[2])

    old_schema = parse_schema(old_path)
    new_schema = parse_schema(new_path)

    # Compare tables
    old_tables = {t["name"]: t for t in old_schema.get("tables", [])}
    new_tables = {t["name"]: t for t in new_schema.get("tables", [])}

    has_changes = False
    has_breaking = False

    for table_name in sorted(set(old_tables.keys()) | set(new_tables.keys())):
        if table_name not in new_tables:
            print(f"- BREAKING: Removed table: {table_name}")
            has_changes = True
            has_breaking = True
        elif table_name not in old_tables:
            print(f"+ Added table: {table_name}")
            has_changes = True
        else:
            changes = diff_tables(old_tables[table_name], new_tables[table_name])
            if changes:
                print(f"~ Modified table: {table_name}")
                for change in changes:
                    print(change)
                    if "BREAKING" in change:
                        has_breaking = True
                has_changes = True

    if not has_changes:
        print("No changes detected")
        return 0

    if has_breaking:
        print("\n⚠️  BREAKING CHANGES DETECTED")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
```

**Usage:**
```bash
# Compare two schema versions
python scripts/schema_diff.py \
    k1/schemas/agent_fabric/agent_state_v1.0.fbs \
    k1/schemas/agent_fabric/agent_state_v1.1.fbs

# Output:
# ~ Modified table: AgentState
#   + Added field: memory_bytes (uint64)
#   + Added field: capabilities ([Capability])
```

#### 5.2 Buffer Migration Tool

**Purpose:** Migrate old buffers to new schema versions.

**Script:** `scripts/migrate_buffer.py`

```python
#!/usr/bin/env python3
"""Buffer migration tool for FlatBuffers"""

import sys
from pathlib import Path
import flatbuffers

def migrate_agent_state_v1_to_v2(old_buf: bytes) -> bytes:
    """Migrate AgentState from v1.0 (memory_mb) to v1.1 (memory_bytes)"""
    from k1.schemas.v1_0.agent_fabric import AgentState as AgentStateV1
    from k1.schemas.v1_1.agent_fabric import AgentState as AgentStateV2

    # Read old buffer
    old_state = AgentStateV1.AgentState.GetRootAs(old_buf, 0)

    # Create new buffer
    builder = flatbuffers.Builder(256)

    # Copy fields
    agent_id = builder.CreateString(old_state.AgentId().decode())

    # Migrate memory_mb -> memory_bytes
    memory_bytes = old_state.MemoryMb() * 1024 * 1024 if old_state.MemoryMb() else 0

    # Build new state
    AgentStateV2.Start(builder)
    AgentStateV2.AddAgentId(builder, agent_id)
    AgentStateV2.AddState(builder, old_state.State())
    AgentStateV2.AddMemoryBytes(builder, memory_bytes)
    new_state = AgentStateV2.End(builder)

    builder.Finish(new_state, file_identifier=b"AGST")
    return bytes(builder.Output())

def main():
    if len(sys.argv) != 3:
        print("Usage: migrate_buffer.py <input.bin> <output.bin>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    # Read old buffer
    old_buf = input_path.read_bytes()

    # Migrate
    new_buf = migrate_agent_state_v1_to_v2(old_buf)

    # Write new buffer
    output_path.write_bytes(new_buf)
    print(f"Migrated {input_path} -> {output_path}")

if __name__ == "__main__":
    main()
```

---

### 6. Version Negotiation Protocol

#### 6.1 K1 ↔ K0 Version Negotiation

**Handshake Protocol:**
1. K1 sends INIT message with supported schema versions
2. K0 responds with selected schema versions
3. Both parties use agreed versions for subsequent communication

**INIT Message:**
```fbs
table InitMessage {
  k1_version: string;                    // "0.5.0"
  supported_schemas: [SchemaVersion];    // List of supported schemas
}

table SchemaVersion {
  file_identifier: string;  // "AGST"
  min_version: string;      // "1.0"
  max_version: string;      // "1.2"
}

file_identifier "INIT";
root_type InitMessage;
```

**Example:**
```python
# K1 sends INIT to K0
builder = flatbuffers.Builder(1024)

# Supported schemas
versions = [
    {"file_id": "AGST", "min": "1.0", "max": "1.2"},
    {"file_id": "TASK", "min": "1.0", "max": "1.1"},
    {"file_id": "K0TE", "min": "1.0", "max": "1.0"},
]

schema_versions = []
for v in versions:
    file_id = builder.CreateString(v["file_id"])
    min_ver = builder.CreateString(v["min"])
    max_ver = builder.CreateString(v["max"])

    SchemaVersion.Start(builder)
    SchemaVersion.AddFileIdentifier(builder, file_id)
    SchemaVersion.AddMinVersion(builder, min_ver)
    SchemaVersion.AddMaxVersion(builder, max_ver)
    schema_versions.append(SchemaVersion.End(builder))

# Create vector
InitMessage.StartSupportedSchemasVector(builder, len(schema_versions))
for sv in reversed(schema_versions):
    builder.PrependUOffsetTRelative(sv)
supported_schemas = builder.EndVector()

# Create message
k1_version = builder.CreateString("0.5.0")
InitMessage.Start(builder)
InitMessage.AddK1Version(builder, k1_version)
InitMessage.AddSupportedSchemas(builder, supported_schemas)
init_msg = InitMessage.End(builder)

builder.Finish(init_msg, file_identifier=b"INIT")
k0_bridge.send(bytes(builder.Output()))

# K0 responds with ACK containing selected versions
ack_buf = k0_bridge.receive()
ack = AckMessage.AckMessage.GetRootAs(ack_buf, 0)
selected_versions = {
    sv.FileIdentifier().decode(): sv.SelectedVersion().decode()
    for sv in ack.SelectedSchemas()
}
# {"AGST": "1.1", "TASK": "1.0", "K0TE": "1.0"}
```

#### 6.2 Client ↔ K1 Version Negotiation

**HTTP Header-Based Negotiation:**
```http
POST /v1/sessions HTTP/1.1
Host: k1.example.com
Content-Type: application/flatbuffers
X-Schema-Version: SEST:1.2

<SessionState FlatBuffer (v1.2)>
```

**Response:**
```http
HTTP/1.1 200 OK
Content-Type: application/flatbuffers
X-Schema-Version: SEST:1.2

<SessionState FlatBuffer (v1.2)>
```

**Version Mismatch:**
```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "schema_version_mismatch",
  "message": "Client requested SEST:1.5, server supports SEST:1.0-1.2",
  "supported_versions": ["1.0", "1.1", "1.2"]
}
```

---

## Consequences

### Positive

1. **Seamless Evolution:** Add fields without breaking old code (backward/forward compatible)
2. **Gradual Deprecation:** 3-release grace period allows smooth migration
3. **Automated Validation:** CI/CD detects breaking changes before merge
4. **Version Safety:** File identifiers prevent protocol mismatches

### Negative

1. **Schema Discipline:** Team must follow strict compatibility rules (training required)
2. **Deprecation Overhead:** 3-release grace period adds tracking burden
3. **Migration Complexity:** Complex schema changes require custom migration scripts

### Risks

1. **Accidental Breaking Changes:** Developer removes field without realizing impact (mitigation: CI validation)
2. **Version Drift:** Different deployments use incompatible schema versions (mitigation: version negotiation)
3. **Migration Bugs:** Custom migration scripts may have bugs (mitigation: comprehensive testing)

---

## References

- **FlatBuffers Schema Evolution:** https://google.github.io/flatbuffers/flatbuffers_guide_writing_schema.html#schema-evolution
- **Protocol Versioning Best Practices:** https://docs.microsoft.com/en-us/azure/architecture/best-practices/api-design#versioning
- **ADR-0011a:** FlatBuffers Schema Design Principles
- **ADR-0011b:** FlatBuffers Code Generation & Integration
- **ADR-0011c:** Serialization Performance & Zero-Copy

---

**Status:** ✅ Accepted
**Related ADRs:**
- ADR-0011a: FlatBuffers Schema Design Principles
- ADR-0011b: FlatBuffers Code Generation & Integration
- ADR-0011c: Serialization Performance & Zero-Copy