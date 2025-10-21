# Consumer Contracts

**Purpose:** Consumer-defined expectations for FlatBuffers schemas

## Overview

This directory contains consumer contracts that define what fields and types consumers expect from provider schemas. Each contract represents a consumer's requirements for a specific schema version.

**Format:** YAML files following consumer-driven contract testing (Pact-style) pattern

## Contract Naming Convention

```
<schema_name>_v<major>.<minor>.<patch>.yaml
```

Examples:
- `agent_state_v1.0.0.yaml` - AgentState schema version 1.0.0
- `recall_request_v2.1.0.yaml` - RecallRequest schema version 2.1.0
- `task_announcement_v1.0.0.yaml` - TaskAnnouncement schema version 1.0.0

## Contract Structure

Every consumer contract must include:

```yaml
schema_name: string          # FlatBuffers schema name
consumer_version: string     # Consumer's version (SemVer)
provider_version: string     # Provider schema version consumer expects
contract_date: string        # ISO 8601 date

expectations:
  required_fields: [string]  # Fields consumer always expects
  optional_fields: [string]  # Fields consumer handles gracefully if missing
  deprecated_fields_used: [string]  # Deprecated fields consumer still uses
  type_expectations: dict    # Field → type mapping

compatibility:
  forward_compatible_with: [string]   # Older versions consumer can read
  backward_compatible_with: [string]  # Newer versions consumer can read
  breaking_changes_from: [string]     # Versions NOT compatible

test_scenarios: [object]     # Test cases for validation

example_data: dict           # Example valid payloads
```

## Creating a New Consumer Contract

### Step 1: Identify Consumer Requirements

```python
# Example: K1 Turn Executor consumes RecallResponse from K0 Bridge

consumer = "K1 Turn Executor"
schema = "RecallResponse"
consumer_version = "2.1.0"

# What does consumer REQUIRE?
required_fields = ['results', 'total_found', 'trace_id']

# What does consumer USE if present?
optional_fields = ['latency_ms', 'sources']

# What deprecated fields does consumer still use?
deprecated_fields_used = []  # None, consumer is modern
```

### Step 2: Write Contract YAML

```yaml
# recall_response_v2.1.0.yaml
schema_name: RecallResponse
consumer_version: "2.1.0"
provider_version: "2.1.0"
contract_date: "2025-10-13"

expectations:
  required_fields:
    - results
    - total_found
    - trace_id

  optional_fields:
    - latency_ms
    - sources

  deprecated_fields_used: []

  type_expectations:
    results: [MemoryItem]
    total_found: uint32
    trace_id: string
    latency_ms: uint32
    sources: [MemorySource]

compatibility:
  forward_compatible_with:
    - "2.0.0"  # Can read v2.0.0 (backward compatible)

  backward_compatible_with:
    - "2.2.0"  # Can read v2.2.0 (forward compatible)

  breaking_changes_from:
    - "1.x.x"  # MAJOR version change

test_scenarios:
  - name: "Minimal response (v2.0.0)"
    data:
      results: []
      total_found: 0
      trace_id: "test-123"
    expected: PASS

  - name: "Full response (v2.1.0)"
    data:
      results:
        - memory_id: "mem-abc"
          content: [98, 121, 116, 101, 115]  # bytes
          modality: "text"
      total_found: 1
      trace_id: "test-123"
      latency_ms: 150
      sources:
        - source_type: "episodic"
          hit_count: 1
    expected: PASS
```

### Step 3: Register Contract

Add contract to version control and update compatibility matrix:

```bash
# Add contract file
git add contracts/testing/consumer_contracts/recall_response_v2.1.0.yaml

# Update compatibility matrix
python scripts/update_compatibility_matrix.py \
  --schema RecallResponse \
  --version 2.1.0

# Commit
git commit -m "feat: Add RecallResponse v2.1.0 consumer contract"
```

## Contract Validation Rules

### Rule 1: Required Fields Cannot Be Removed

```yaml
# ❌ INVALID: Consumer expects 'session_id' but it's not in provider schema
expectations:
  required_fields:
    - session_id  # Provider removed this field

# Provider schema must add it back or consumer must update contract
```

### Rule 2: Optional Fields Have Defaults

```yaml
# ✅ VALID: Consumer handles missing optional fields
expectations:
  optional_fields:
    - time_range  # Consumer uses None if missing

# Consumer code:
# time_range = response.time_range if hasattr(response, 'time_range') else None
```

### Rule 3: Type Changes Are Breaking

```yaml
# ❌ BREAKING: Consumer expects uint32, provider changed to int64
type_expectations:
  total_found: uint32  # Consumer expects this

# Provider schema changed:
# table RecallResponse {
#   total_found: int64;  # BREAKING CHANGE - requires MAJOR version bump
# }
```

### Rule 4: Deprecated Fields Have Timeline

```yaml
# ✅ VALID: Consumer uses deprecated field but acknowledges deprecation
deprecated_fields_used:
  - legacy_query_format  # Deprecated in v2.1.0, removed in v3.0.0

# Consumer must migrate off deprecated fields before MAJOR version bump
```

## Example Consumer Contracts

### Example 1: AgentState v1.0.0

```yaml
schema_name: AgentState
consumer_version: "1.0.0"
provider_version: "1.0.0"
contract_date: "2025-01-01"

expectations:
  required_fields:
    - agent_id
    - state
    - memory_mb
    - version
    - timestamp
    - trace_id

  optional_fields:
    - capabilities
    - metadata

  type_expectations:
    agent_id: string
    state: AgentStateEnum
    memory_mb: uint32
    version: uint16
    timestamp: int64
    trace_id: string
    capabilities: [string]
    metadata: [ubyte]

example_data:
  valid:
    agent_id: "agent-123"
    state: ACTIVE
    memory_mb: 500
    version: 1
    timestamp: 1697234567000
    trace_id: "trace-abc"
    capabilities: ["TOOL_CALL", "CLARIFICATION"]
```

### Example 2: TaskAnnouncement v1.0.0

```yaml
schema_name: TaskAnnouncement
consumer_version: "1.0.0"
provider_version: "1.0.0"
contract_date: "2025-01-01"

expectations:
  required_fields:
    - task_id
    - intent
    - required_capabilities
    - timeout_ms
    - trace_id

  optional_fields:
    - context
    - constraints

  type_expectations:
    task_id: string
    intent: string
    required_capabilities: [string]
    timeout_ms: uint32
    trace_id: string
    context: [ubyte]
    constraints: [ubyte]

example_data:
  minimal:
    task_id: "task-xyz"
    intent: "plan_activity"
    required_capabilities: ["TOOL_CALL"]
    timeout_ms: 5000
    trace_id: "trace-abc"

  full:
    task_id: "task-xyz"
    intent: "plan_activity"
    required_capabilities: ["TOOL_CALL", "CLARIFICATION"]
    timeout_ms: 5000
    trace_id: "trace-abc"
    context: [98, 121, 116, 101, 115]
    constraints: [98, 121, 116, 101, 115]
```

## Contract Versioning Strategy

### When to Update Consumer Contract

1. **Consumer adds new requirement** → Create new contract version (e.g., v1.0.0 → v1.1.0)
2. **Consumer stops using optional field** → Update existing contract (PATCH bump)
3. **Consumer changes type expectation** → Create new contract with MAJOR version bump
4. **Provider schema evolves** → Validate existing contract still works

### Version Mapping

```yaml
consumer_versions:
  "1.0.0":
    compatible_with_provider: ["1.0.0", "1.1.0", "1.2.0"]
    incompatible_with_provider: ["2.0.0+"]

  "2.0.0":
    compatible_with_provider: ["2.0.0", "2.1.0", "2.2.0"]
    incompatible_with_provider: ["1.x.x"]
```

## Testing Contracts

### Manual Testing

```python
from contracts.testing.test_contract import ContractTest

# Load contract
contract_path = Path("consumer_contracts/recall_response_v2.1.0.yaml")
test = ContractTest("RecallResponse", "2.1.0", "2.1.0", contract_path)

# Test forward compatibility
compatible, msg = test.test_forward_compatibility()
print(f"Forward compatible: {compatible} - {msg}")

# Test backward compatibility
compatible, msg = test.test_backward_compatibility()
print(f"Backward compatible: {compatible} - {msg}")
```

### Automated Testing (CI/CD)

```bash
# Run contract tests for all schemas
python contracts/testing/test_all_contracts.py

# Run contract tests for specific schema
python contracts/testing/test_contract.py --schema RecallResponse --version 2.1.0

# Generate compatibility matrix
python contracts/testing/generate_matrix.py --output compatibility_matrix/
```

## Related Documentation

- **Provider Contracts:** `../provider_contracts/` - FlatBuffers schema definitions
- **Compatibility Matrix:** `../compatibility_matrix/` - Test results
- **Testing Framework:** `../README.md` - Contract testing overview
- **ADR-0013d:** Consumer-driven contract testing specification

---

**Last Updated:** 2025-10-13

**Total Contracts:** 0 (pending implementation)
**Coverage:** 0/76 schemas (0%)
