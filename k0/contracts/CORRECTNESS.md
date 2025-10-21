# K0 Kernel Correctness Contract

> **Scope**: Durable commit path, replay primitives, Outbox/DLQ semantics, schema lifecycle gatekeeping.
> **Audience**: Kernel engineers, reviewers, and operators validating invariants via Ward suites and perf harnesses.

---

## 1. Core Invariants (I1–I6)

| ID | Assertion | Enforcement | Validation |
| -- | --------- | ----------- | ---------- |
| **I1** | `st_wal.pos` is strictly increasing; every commit creates exactly one row in `st_receipts` with `wal_pos == st_wal.pos`. | SQLite AUTOINCREMENT + Unit of Work writes receipts in the same transaction. | `tests/correctness/test_invariants.py::test_wal_receipt_monotonicity` replay and crash harness.
| **I2** | `idem_ledger.idem_key` uniquely maps to a committed `receipt_id`; conflicting commits are rejected pre-WAL. | Minimal Gate recomputes the canonical BLAKE3 digest over `[tenant_id, space_id, actor, topic, schema_uri, schema_version, payload_sha256]`, rejects malformed or mismatched client digests, and the UNIQUE constraint prevents double inserts. Duplicates return `409 IDEMPOTENT_DUPLICATE`, emit `command_idem_duplicate`, and increment `command_idempotency_duplicates_total`. | `tests/correctness/test_idem_collisions.py` using concurrent submits and crash injection.
| **I3** | `st_outbox.fingerprint` is unique per driver; requeues preserve fingerprint and bump `requeue_seq`, all scoped by `{tenant_id, space_id}`. | UNIQUE index `uq_outbox_idem` on `(tenant_id, space_id, driver, fingerprint, requeue_seq)` plus `idx_outbox_space`; kernel preserves fingerprint when cloning from DLQ. | `tests/dlq/test_requeue_idempotence.py` ensures idempotent apply.
| **I4** | `st_offsets.offset` is monotone per `(subscriber_id, topic, space_id, tenant_id)` across replay and snapshot restore. | PRIMARY KEY `(subscriber_id, topic, space_id, tenant_id)` with monotonic updates; snapshot restore applies `MAX(offset, replay_offset)` per `{tenant_id, space_id}`. | `tests/correctness/test_offsets_monotonic.py` with snapshot/replay cycle.
| **I5** | Snapshot watermark `W` fences state: snapshot includes all WAL rows with `pos ≤ W`; replay resumes at `W + 1`. | `SNAPSHOT_BEGIN(W)` and `SNAPSHOT_COMMIT(W)` markers in WAL + restore guard. | `tests/snapshots/test_watermark_protocol.py` ensures ports stay closed until commit marker observed.
| **I6** | Schema state drives deterministic admission: `{state, now}` pair maps to a single Gate/Replay outcome. | Minimal Gate + Replay runner consult schema_registry state machine. | Deny matrix below + `tests/schemas/test_state_matrix.py`.
| **I7** | Every envelope carries `{tenant_id, space_id, device_id}` matching provisioned records; missing/mismatched values are rejected pre-WAL. | Provisioning ledger (`st_devices`) + Minimal Gate actor/space validation; `k0ctl provision` emits signed entries. | `tests/security/test_space_binding.py` attempts spoofed tenants/devices.

---

## 2. Canonical Serialization

* **Envelope canonical JSON**: UTF-8 encoded, sorted keys, no insignificant whitespace. Any client-submitted envelope failing canonicalization is rejected with `REJECTED_KERNEL_GATE(reason=CANONICALIZATION_ERROR)`.
* **Idempotency key**: Derived from canonical JSON array `[tenant_id, space_id, actor, topic, schema_uri, schema_version, payload_sha256]` without extra spacing. Control characters are escaped per RFC 8259. Forbidden fields (`ts`, `sig`, transport headers, device metadata)` MUST NOT influence the derivation; Gate recomputes the array server-side.
* **Body hashing**: `payload_sha256` computed over raw body bytes prior to decompression or schema parsing.
* **Receipt binding**: `receipt_id`, `idem_key`, `wal_pos`, `commit_ts`, `payload_sha256`, `mls_group_id`, `key_version`, and `obligations` (if present) are serialized as canonical JSON before signing. Downstream services verify both signature and canonical encoding.

---

## 3. Schema State × Call Path Deny Matrix

| Schema state | Command submit | Replay | Snapshot restore | Notes |
| ------------ | -------------- | ------ | ---------------- | ----- |
| `REGISTERED` | `400 REJECTED_KERNEL_GATE` (reason=`SCHEMA_NOT_ACTIVE`) | Not visible | Included only if explicitly promoted | Registration step only. |
| `ACTIVE` | Accept | Replay continues | Included | Default steady state. |
| `DEPRECATED` and `now < sunset_at` | Accept with warning header `X-Schema-Sunset` | Replay allowed | Included | PEP logs advisory. |
| `DEPRECATED` and `now ≥ sunset_at` | `400 REJECTED_KERNEL_GATE` (reason=`SCHEMA_SUNSET`) | Replay allowed | Included | Replay never mutates; commit blocked. |
| `BLOCKED` | `400 REJECTED_KERNEL_GATE` (reason=`SCHEMA_BLOCKED`) | **Replay HALTS** at first blocked row; operator unlock required. | Restore refused until unblocked | Security incident workflow. |

Replay runner emits `schema_state_violation` metric and halts when encountering `BLOCKED` rows.

---

## 4. Snapshot Watermark Protocol

1. Emit `SNAPSHOT_BEGIN{watermark=W, snapshot_id}` to `st_wal`.
2. Flush snapshot artifacts (WAL up to `W`, offsets, idem ledger digest, schema digest) atomically.
3. After successful persistence, emit `SNAPSHOT_COMMIT{watermark=W, snapshot_id}`.
4. Restore refuses to open ports unless the last marker for the snapshot is `SNAPSHOT_COMMIT`.
5. Operators must never prune WAL segments with unfinished snapshots; the retention job checks for dangling `SNAPSHOT_BEGIN` markers.

Metrics: `snapshot_open_transactions`, `snapshot_dangling_markers`. Alerts fire when commit markers are missing for >5 minutes.

---

## 5. Signature Verification & Revocation Ordering

* Gate enforces `sig_verify_timeout_ms` (default 5 ms) and per-tenant verification rate caps from `config/kernel.yaml`.
* PEP consults the revocation cache **before** Gate validation; cache TTL defaults to 5 minutes with proactive refresh on revocation.
* Revocation race handling: if PEP denies due to stale cache during commit, the Unit of Work aborts and the request surfaces `403 PEP_DENY(reason=KEY_REVOKED)`.
* Receipts attach `mls_group_id` and `key_version`; Ward tests verify the pair matches the active MLS session for `{tenant_id, space_id}` and that SSE fan-out enforces the same key lineage.

---

## 6. Correctness Test Harness Map

| Suite | Purpose |
| ----- | ------- |
| `tests/correctness/test_invariants.py` | Validates WAL/receipt monotonicity, Outbox uniqueness, and offset ordering under crash/replay. |
| `tests/snapshots/test_watermark_protocol.py` | Enforces watermark markers and port gating behaviour. |
| `tests/security/test_sig_revocation.py` | Verifies PEP/Gate ordering under revocation races. |
| `tests/dlq/test_requeue_idempotence.py` | Guards DLQ → Outbox cloning semantics. |
| `tests/qos/test_starvation_bounds.py` | Proves scheduler fairness per band and per tenant.
| `tests/security/test_space_binding.py` | Validates tenant/space/device provisioning and Gate enforcement. |

All suites use Ward with real drivers; no mocks or sleeps. Crash injection uses the kernel fault harness documented in the README.

---

## 7. References

* `k0/README.md` — Sections 5, 6, 8, 9, 15, 19, 22 for operational context.
* `config/kernel.yaml` — Retention, gate caps, signature budgets, hot reload versions.
* `contracts/jsonschema/*.json` — Envelope, receipt, error schema definitions.
* `drivers/conformance/` — Driver SPI compliance fixtures.
* `perf/` — Golden workload definitions aligning with SLO enforcement.
* `cli/k0ctl.py` — Provisioning, config reload, and fault injection commands (see `provision --tenant --space --device`).
