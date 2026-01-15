# Actor ID Flow Trace: Entrypoint → P02 → P08 → P03

**Purpose**: Trace how `actor_id` flows through the system to understand the memory model architecture.

**Date**: 2026-01-13

---

## Tracing Log

### 1. Entrypoint: `k0/kernel/main.py`

**Role**: ASGI server launcher (uvicorn)

- Calls `create_app()` from `k0/kernel/app.py`
- No actor handling here - just server bootstrap

---

### 2. App Factory: `k0/kernel/app.py`

**Role**: Creates FastAPI app, wires routers

- Lines 1-120: Creates app, registers routers
- Routers: `command`, `query`, `sse`, `drivers`, `admin`, `observe`
- **Command router** handles envelope ingestion at `/k0/command.submit`

---

### 3. Command Port: `k0/ports/command.py`

**Role**: HTTP endpoint for envelope submission

**Key Model** (lines 62-116):

```python
class Envelope(BaseModel):
    actor: str  # <-- THIS IS THE FIELD
    tenant_id: str
    space_id: str
    device_id: str
    # ... other fields
```

**Flow** (lines 200-270):

1. `submit_command()` receives JSON payload
2. Validates with `Envelope.model_validate()`
3. Extracts `envelope_model.actor` → logs it
4. Passes to `MinimalGate.validate()` for validation
5. Evaluates policy with `evaluate_envelope()`
6. Creates `policy_stamp` attachment

**Observation**:

- `actor` field comes directly from the HTTP request body
- No transformation - raw value from client
- Stored in `envelope_dict["actor"]`

**Next**: Where does envelope go after validation?

---

### 4. WAL Entry & Outbox: `k0/ports/command.py` (continued)

**Lines 580-600 - WalEntry Creation**:

```python
wal_entry = WalEntry(
    tenant_id=envelope_dict["tenant_id"],
    space_id=envelope_dict["space_id"],
    topic=envelope_dict["topic"],
    envelope_json=canonical_json(_strip_body(envelope_dict)),
    # ... body, policy_stamp, etc.
)
```

**Lines 710-740 - Outbox Payload**:

```python
outbox_payload: dict[str, Any] = {
    "wal_pos": wal_pos,
    "tenant_id": envelope_dict["tenant_id"],
    "space_id": envelope_dict["space_id"],
    "actor": envelope_dict["actor"],  # <-- ACTOR FLOWS TO OUTBOX
    "device_id": envelope_dict["device_id"],
    # ... other fields
}
```

**Key Finding**:

- `actor` from envelope → stored in WAL (`envelope_json` column)
- `actor` from envelope → placed in `outbox_payload`
- Outbox entry triggers pipeline consumption

**Next**: How does pipeline consume from outbox?

---

### 5. Pipeline Runner: `k0/runtime/pipeline_runner.py`

**Role**: Executes P02 DAG stages with BusMessage

**Lines 300-330 - Envelope Parsing**:

```python
# Parse envelope: use enriched version (shared across parallel stages)
if self._enriched_envelope is not None:
    envelope_dict = self._enriched_envelope
else:
    envelope_dict = json.loads(message.payload.decode("utf-8"))

# Pass the enriched envelope to each module
args["envelope"] = envelope_dict
```

**Key Finding**:

- Outbox entry payload (contains `actor`) is decoded as JSON
- Passed to each module via `args["envelope"]`
- Modules receive envelope with `envelope["actor"]`

---

### 6. Row Builder: `k0/modules/builders/hipp_events_row.py`

**Role**: Assembles st_hipp_events row from all module outputs

**Lines 255-270 - Actor Mapping**:

```python
def map_actor_device_group(envelope, device_output, ingress_output):
    return {
        "actor_id": envelope.get("actor"),  # <-- THE CRITICAL MAPPING
        "actor_role": envelope.get("actor_role", "SELF"),
        "device_id": envelope.get("device_id"),
        # ...
    }
```

**🔴 CRITICAL FINDING**:

```
envelope["actor"] → st_hipp_events.actor_id
```

**This is where `actor-test-{index}` becomes the stored `actor_id`!**

**Next**: Where does actor flow to P03 consolidation?

---

### 7. P03 R4 KG Consolidator: `k0/pipelines/p03/phases/r4_kg_consolidator.py`

**Role**: Extracts social relationships from events

**Lines 1628-1629 - Self Actor Resolution**:

```python
actor_id = getattr(event, "actor_id", None)
self_actor_id = actor_id or f"SELF_{space_id}"
```

**Lines 1729 - Relationship Data Building**:

```python
relationship_data[rel_key] = {
    "actor_a_id": self_actor_id,  # <-- USES EVENT'S actor_id
    "actor_b_id": participant_id,
    "actor_b_name": participant_name,
    # ...
}
```

**Lines 1873 - SocialRelationship Creation**:

```python
relationship = SocialRelationship(
    relationship_id=f"social_{rel_hash}",
    actor_a_id=data["actor_a_id"],  # <-- FROM self_actor_id
    actor_b_id=data["actor_b_id"],
    # ...
)
```

**🔴 ROOT CAUSE IDENTIFIED**:

```
Event 1:  actor_id = "actor-test-1"  → self_actor_id = "actor-test-1"
Event 2:  actor_id = "actor-test-2"  → self_actor_id = "actor-test-2"
Event 56: actor_id = "actor-test-56" → self_actor_id = "actor-test-56"

Each event creates relationships like:
  "actor-test-1" → "Emma"
  "actor-test-2" → "Emma"
  "actor-test-3" → "Emma"
  ...

Result: 56 DIFFERENT people all know Emma!
Instead of: ONE person (Prince) knows Emma with 56 interactions!
```

---

## Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ACTOR_ID FLOW TRACE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. HTTP Request                                                            │
│     └── {"actor": "actor-test-{index}", ...}                               │
│                         ↓                                                   │
│  2. command.py (Envelope Model)                                             │
│     └── envelope_model.actor = "actor-test-{index}"                        │
│                         ↓                                                   │
│  3. WalEntry + OutboxEntry                                                  │
│     └── outbox_payload["actor"] = envelope_dict["actor"]                   │
│                         ↓                                                   │
│  4. BusMessage (P02 Pipeline)                                               │
│     └── envelope["actor"] = "actor-test-{index}"                           │
│                         ↓                                                   │
│  5. hipp_events_row.py (Builder)                                            │
│     └── "actor_id": envelope.get("actor")                                  │
│                         ↓                                                   │
│  6. st_hipp_events (P02 Storage)                                            │
│     └── actor_id = "actor-test-{index}"                                    │
│                         ↓                                                   │
│  7. P03 R4 KG Consolidator                                                  │
│     └── self_actor_id = event.actor_id = "actor-test-{index}"              │
│                         ↓                                                   │
│  8. SocialRelationship                                                      │
│     └── actor_a_id = self_actor_id = "actor-test-{index}"                  │
│                         ↓                                                   │
│  9. st_social (P03 Storage)                                                 │
│     └── actor_a_id = "actor-test-{index}"                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Fix Points

| Layer | File | Fix Required |
|-------|------|--------------|
| **Entry** | `k0/deploy/submit_test_events.py` | Change `f"actor-test-{index}"` to constant `"Prince"` |
| **Entry** | `k0/deploy/submit_diverse_events.py` | Same fix |
| **Config** | NEW: `k0/config/memory_model.yaml` | Define single_user vs household mode |
| **P03** | `k0/pipelines/p03/phases/r4_kg_consolidator.py` | For household mode: respect per-event actor_id |

---

## Conclusion

**The system works correctly** - it faithfully preserves actor_id from entry to consolidation.

**The problem is test data** - submit_test_events.py generates 56 unique actor_ids instead of one user.

**Fix**: Change test generators to use consistent actor_id for single-user mode.
