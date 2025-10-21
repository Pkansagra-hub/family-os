# End-to-End Test Suite

## 📁 Structure

```
tests/
├── sdk/
│   ├── __init__.py
│   └── k0_client.py         # K0 Python SDK (sync + async)
└── integration/
    └── test_e2e_flows.py    # E2E black-box test suite
```

## 🎯 Purpose

The E2E test suite validates the complete K0 kernel workflow using only public HTTP APIs. Tests are **black-box**: they interact with the kernel exclusively through HTTP ports, ensuring production-like behavior.

## 🧩 Components

### K0 Python SDK (`tests/sdk/k0_client.py`)

Production-quality HTTP client for K0 kernel. Provides:

- **Synchronous API** (`K0Client`) - for tests and blocking integrations
- **Asynchronous API** (`K0AsyncClient`) - for concurrent operations
- **All ports covered**:
  - Command port (`/k0/command.submit`)
  - Query port (`/k0/query.recall`)
  - SSE port (`/k0/sse.subscribe`, `/k0/sse.ack`)
  - Observability port (`/healthz`, `/readyz`, `/metrics`)

**Example usage:**

```python
from tests.sdk import K0Client, CommandReceipt

client = K0Client(base_url="http://localhost:8000")

# Submit command
response = client.submit_command(envelope={
    "cognitive_trace_id": "trace-123",
    "tenant_id": "tenant-alpha",
    "space_id": "space-main",
    "topic": "test.action",
    "body": {"action": "create"},
    "schema": {"uri": "schema://test", "version": "1.0"},
    "device_id": "device-1",
    "key_version": "1",
    "device_sig": "...",
})

if response.ok:
    receipt = CommandReceipt.from_response(response)
    print(f"Committed at WAL position {receipt.wal_pos}")

# Query recall
query_response = client.query_recall(
    tenant_id="tenant-alpha",
    space_id="space-main",
    selectors=[{"topic": "test.action", "limit": 10}],
)

# SSE subscribe
for event in client.sse_subscribe("tenant-alpha", "space-main", ["test.*"]):
    print(f"Event: {event['topic']} at pos {event['wal_pos']}")
    break  # Stop after first event

client.close()
```

### E2E Test Suite (`tests/integration/test_e2e_flows.py`)

Comprehensive Ward-based tests covering:

1. **Observability Port**
   - Health and readiness checks
   - Metrics endpoint (Prometheus format)

2. **Command Port**
   - Command submission → receipt issuance
   - WAL persistence verification
   - Idempotency enforcement
   - Signature validation
   - Outbox entry creation

3. **Query Port**
   - Selector execution
   - Bundle and trace responses
   - Budget tracking and exhaustion

4. **SSE Port**
   - Event delivery from WAL
   - Subscriber offset persistence
   - Acknowledgment workflow

5. **Full E2E Flow**
   - Command → Query → SSE → Ack in sequence
   - Verification at each step

6. **Error Paths**
   - Invalid signatures
   - Missing provisioning
   - Schema violations
   - Budget exhaustion

## 🧪 Running Tests

### Run all E2E tests

```powershell
python -m ward test --path tests/integration/test_e2e_flows.py
```

### Run specific test

```powershell
python -m ward test --path tests/integration/test_e2e_flows.py --search "complete flow"
```

### Run with verbose output

```powershell
python -m ward test --path tests/integration/test_e2e_flows.py --show-diff-symbols
```

## 📊 Coverage

E2E tests validate:

- ✅ **All HTTP ports** (command, query, SSE, observability)
- ✅ **Complete workflows** (end-to-end user journeys)
- ✅ **State persistence** (WAL, receipts, outbox, offsets)
- ✅ **Error handling** (gate rejection, budget exhaustion, invalid inputs)
- ✅ **Idempotency** (duplicate submissions)
- ✅ **Security** (signature verification, provisioning checks)

## 🏗️ Test Environment

Each test uses a `e2e_env` fixture providing:

- **Temporary SQLite database** (isolated per test)
- **Running kernel instance** (FastAPI TestClient)
- **Provisioned device** with signing key
- **Registered schema**
- **K0 SDK client** (wrapping TestClient for API calls)

Environment is fully torn down after each test (database deleted, connections closed).

## 🔍 Black-Box Philosophy

Tests follow strict black-box principles:

1. **No internal imports** (except for fixture setup)
2. **HTTP-only interactions** (via K0 SDK client)
3. **Public API validation** (responses, status codes, headers)
4. **Direct DB checks** only for state verification (not for operations)

This ensures tests validate **production behavior** rather than implementation details.

## 🚀 Next Steps

### Epic 9.1.2: Performance Baseline

- Load testing with `perf/profiles/*.yaml`
- Throughput and latency baselines
- QoS budget behavior under stress

### Epic 9.1.3: Chaos Engineering

- WAL fsync failures
- Scheduler tightening scenarios
- Network partition simulation

## 📚 References

- **Contracts Playbook**: `docs/development/contracts-playbook.md`
- **K0 Plan**: `k0/plan.md` (Milestone 9)
- **OpenAPI Spec**: `k0/contracts/openapi.k0.yaml`
- **JSON Schemas**: `k0/contracts/jsonschema/`

## 🧑‍💻 Contributing

When adding new E2E tests:

1. Use the `e2e_env` fixture for environment setup
2. Follow black-box principles (HTTP-only interactions)
3. Verify state changes via public APIs where possible
4. Include both happy path and error path tests
5. Document test purpose and assertions clearly
6. Update this README with new coverage areas

## 🐛 Troubleshooting

### Test failures

If tests fail:

1. Check kernel logs (observability emitter)
2. Inspect database state (use `connection_scope()`)
3. Verify fixture setup (device provisioning, schema registration)
4. Check HTTP responses for error details

### Fixture issues

If fixtures fail to initialize:

- Ensure `storage.sql` exists and is valid
- Check temporary directory permissions
- Verify all required kernel dependencies are installed

### SSE subscription hangs

SSE tests use `iter_lines()` which will block if no events arrive:

- Always submit commands before subscribing
- Break after consuming expected number of events
- Use timeout mechanisms for production tests
