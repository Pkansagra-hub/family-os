
# K0 Kernel — Production README

> **Status**: Design baseline agreed
> **Scope**: Authoritative microkernel for MemoryOS — durability, policy, QoS, receipts, replay, and driver SPI.
> **Non‑Goals**: Cognitive planning, hippocampal algorithms, user‑space services, or direct engine IO outside K0.

K0 is the **only durable commit surface** of MemoryOS. All writes pass through:

**`PEP@syscall → Minimal Gate → Idempotency Ledger → UnitOfWork (UoW) → WAL → Receipts/Offsets/Outbox/DLQ → Bus/SSE`**.
  payload_sha256 TEXT,
Reads go through the **Query Port** with hints provided by user‑space; K0 enforces **hard budgets** and **global fairness**. K0 exposes four ports at a **privileged boundary** and talks to engines only through **driver aliases** (`st_*`) bound to concrete drivers via the **Alias Map**.

---

## 0) TL;DR

* **ACID cohort** (SQLite WAL + optional FTS5) commits synchronously in one transaction; the **Outbox** captures async intents.
* **Async cohort** (vector/embeddings, KG, blob) converges **idempotently** via indexers after the commit.
* **Replay correctness**: replayers validate envelopes using the Schema Registry and rebuild offsets/receipts deterministically.
* **SSE**: topic ACL + cursors, with backpressure and catch‑up on restart.

---

## Quickstart

### Local run with `k0ctl`

1. Install dependencies into a virtual environment:

  ```powershell
  python -m pip install -r requirements.txt
  ```

2. (Optional) Adjust `k0/config/kernel.yaml`. The new `server` block controls the bind address, port, log level, and graceful shutdown timeout.

3. Start the kernel runtime:

  ```powershell
  python -m k0.cli.k0ctl serve --host 127.0.0.1 --log-level debug
  ```

  Omit `--host` or `--log-level` to fall back to the values defined in the configuration file. Supply `--config <path>` to point at an alternate YAML file, or include repeated `--set dotted.path=value` overrides for ad-hoc adjustments (for example `--set server.port=9090`).

### Apply storage migrations

Run database migrations before the first boot (and whenever `k0/contracts/sql` changes):

```powershell
python -m k0.cli.k0ctl migrate
```

-- Provisioned devices ledger (device bindings only)

### Optional: systemd unit

Deployments that rely on `systemd` can wrap `k0ctl` directly:
  mls_group_id TEXT NOT NULL,
  provisioned_ts TEXT NOT NULL
);

-- Device keys with rotation support (ADR 001)
CREATE TABLE IF NOT EXISTS st_device_keys (
  device_id TEXT NOT NULL,
  key_version TEXT NOT NULL,
  verify_key TEXT NOT NULL,
  key_state TEXT NOT NULL DEFAULT 'ACTIVE'
    CHECK(key_state IN ('PENDING','ACTIVE','ROTATING','REVOKED')),
  registered_ts TEXT NOT NULL,
  activated_ts TEXT,
  rotated_ts TEXT,
  revoked_ts TEXT,
  grace_expires_ts TEXT,
  revocation_reason TEXT,
  PRIMARY KEY(device_id, key_version),
  FOREIGN KEY(device_id) REFERENCES st_devices(device_id)
Description=K0 Kernel
After=network.target

[Service]
Type=simple
Environment=PYTHONPATH=/opt/memory_kernel
WorkingDirectory=/opt/memory_kernel
ExecStart=/opt/memory_kernel/.venv/Scripts/python.exe -m k0.cli.k0ctl \
  driver TEXT NOT NULL,
  op_kind TEXT NOT NULL,
Restart=on-failure
  fingerprint TEXT NOT NULL,
[Install]
WantedBy=multi-user.target
```

The unit reuses the same graceful shutdown semantics exposed by the runtime harness, so `systemctl stop k0` drains outstanding requests before exiting.
CREATE TABLE IF NOT EXISTS st_dlq (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wal_pos INTEGER,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  driver TEXT NOT NULL,
  op_kind TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  payload BLOB NOT NULL,
  reason TEXT NOT NULL,
  retries INTEGER NOT NULL DEFAULT 0,
  requeue_seq INTEGER NOT NULL DEFAULT 0,
  first_failure_ts TEXT NOT NULL,
  last_failure_ts TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'PENDING'
    CHECK(state IN ('PENDING','REQUEUED','QUARANTINED'))
);

-- Schema registry with audit trail (ADR 002)
CREATE TABLE IF NOT EXISTS schema_registry (
  schema_uri TEXT NOT NULL,
  version TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('REGISTERED','ACTIVE','DEPRECATED','BLOCKED')),
  operator_id TEXT,
  blocked_ts TEXT,
  blocked_reason TEXT,
  unblocked_ts TEXT,
  PRIMARY KEY(schema_uri, version)
);

-- Indexes
DROP INDEX IF EXISTS idx_outbox_fingerprint_space;
CREATE INDEX IF NOT EXISTS idx_wal_space_pos ON st_wal(space_id, pos);
CREATE INDEX IF NOT EXISTS idx_wal_tenant_topic ON st_wal(tenant_id, topic, pos);
CREATE INDEX IF NOT EXISTS idx_receipts_space ON st_receipts(space_id, wal_pos);
CREATE INDEX IF NOT EXISTS idx_receipts_walpos ON st_receipts(wal_pos);
CREATE INDEX IF NOT EXISTS idx_outbox_space ON st_outbox(space_id, requeue_seq, id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_outbox_idem ON st_outbox(tenant_id, space_id, driver, fingerprint, requeue_seq);
CREATE INDEX IF NOT EXISTS idx_dlq_space ON st_dlq(space_id, first_failure_ts);
CREATE INDEX IF NOT EXISTS idx_device_keys_state ON st_device_keys(device_id, key_state);
```

`st_devices` backs the provisioning ledger consumed by Minimal Gate checks (see §15) and is populated exclusively through `k0ctl provision`. Additional tables (episodic, semantic, FTS, KG, blobs) are accessed through **driver aliases** and implemented in `drivers/*`.

## Bootup Playbook (Docker Compose)

The repository ships with a fully wired local stack that runs the kernel alongside the observability suite (Prometheus, Grafana, Tempo). Use this flow whenever you need the kernel plus telemetry for end-to-end testing or when coordinating with K1.

### Directory Map

```text
k0/deployment/compose/generated/local-single-node/
├── docker-compose.yml                 # Kernel service (pulls k0-kernel-local image)
├── local-single-node-telemetry.yml    # Prometheus, Grafana, Alertmanager, Tempo
├── env/
│   └── k0.env                         # Environment overrides for the kernel
├── data/                              # SQLite volume (mounted into /data)
├── secrets/                           # Device keys and sensitive material
├── telemetry/
│   ├── prometheus.yml                 # Scrape targets + rules path
│   ├── grafana/                       # Provisioning + dashboards
│   └── tempo.yaml                     # Tempo configuration (OTLP ports 4317/4318)
└── generated/
  ├── dashboards/                    # Grafana JSON dashboards
  └── rules/                         # Prometheus alerting rules
```

### Boot Sequence

> Run commands from the repo root (`d:\familyos`). PowerShell examples shown; use `&&` instead of `;` in bash shells.

1. **Build the local kernel image** (only required after code changes):

  ```powershell
  docker build -t k0-kernel-local:latest .
  ```

1. **Seed the SQLite database** (idempotent; safe to re-run after nuking `data/`):

  ```powershell
  python k0/scripts/bootstrap_local_kernel.py --database k0/deployment/compose/generated/local-single-node/data/k0_kernel.db
  ```

1. **Start the kernel and telemetry stack:**

  ```powershell
  Set-Location k0/deployment/compose/generated/local-single-node
  docker compose -f docker-compose.yml -f local-single-node-telemetry.yml up -d
  ```

1. **Verify readiness:**

  ```powershell
  curl.exe http://localhost:8080/healthz     # kernel
  curl.exe http://localhost:9090/-/ready     # Prometheus
  curl.exe http://localhost:3200/status      # Tempo
  ```

1. **Grafana dashboard access:**

  * Browse to `http://localhost:3000`
  * Default credentials: `admin / ChangeMe!`

1. **Shut down the stack:**

  ```powershell
  docker compose -f docker-compose.yml -f local-single-node-telemetry.yml down
  ```

### Coordination with K1

* Keep the compose project running when developing multi-agent flows; point K1 observability exporters at `http://localhost:4317` (gRPC) or `http://localhost:4318` (HTTP) for shared traces.
* `tempo.yaml` already exposes Prometheus remote write; K1 metrics can reuse the same Prometheus instance by adding scrape configs in `telemetry/prometheus.yml`.
* For integrated bring-up, launch the K1 stack after step 3 and confirm both kernels register in shared dashboards (Grafana folder `Kernel / Local Single Node`).

### Troubleshooting

* `pull access denied for k0-kernel-local`: rebuild the image (step 1) and rerun compose.
* `database locked`: stop the stack, remove `data/k0_kernel.db-journal`, rerun the bootstrap script, then restart compose.
* Tempo status dumps the full config when queried; search for `ready=true` near the top to confirm collector health.

### 6.2 WAL Retention & Snapshots

* **Retention horizon**: maintain WAL segments for the longer of **7 days** or **10 million events**. Segments older than the horizon are pruned only after a successful snapshot.
* **Nightly snapshots**: persist a compressed checkpoint containing `st_wal` up to a `watermark`, `st_offsets`, `idem_ledger`, and `schema_registry` digests. Snapshots are versioned and stored according to the tenancy policy (per-tenant path when isolated). Each snapshot marks `SNAPSHOT_BEGIN{watermark}` before capture and finalizes with `SNAPSHOT_COMMIT{watermark}` when durable; retention workers refuse to prune segments with dangling begin markers.
* **Restore flow**: load the latest snapshot → restore offsets/ledger tables → ensure the latest watermark has a matching commit marker → replay WAL from `watermark + 1` through current tip. Replay success requires `replay_parity_failures == 0` before opening ports.
* **Compaction**: during snapshot creation, run SQLite `VACUUM` on `st_outbox`, `st_dlq`, and derivative tables to control file growth. Compaction respects ongoing transactions via snapshot isolation.
* **Per-space replay**: `idx_wal_space_pos` and `idx_receipts_space` allow selective restore for a single `{tenant_id, space_id}`; `k0ctl replay --tenant <tenant_id> --space <space_id>` replays only that namespace, emitting `merge.applied` events for CRDT reconciliation.

Topic-specific retention overrides live in `config/kernel.yaml` under `retention.topics`. Defaults: `ui.*` keeps 2 days or 1 million events (whichever first), `policy.*` extends to 30 days or 20 million events, and `infra.sanitized.*` retains 14 days. Per-space overrides live under `retention.spaces` (e.g., `shared:household` keeps 30 days while `personal:*` keeps 14). All other topics inherit the global horizon (7 days / 10 million events).

### 6.3 Tenancy Model
K0 is a **microkernel** with four ABIs (Ports): **Command**, **Query**, **SSE**, **Observability**. It runs **policy at syscall**, validates envelopes at a **Minimal Gate**, enforces **exactly‑once durability** using an **Idempotency Ledger**, and persists **WAL/Receipts/Offsets/Outbox/DLQ**. All cognition (attention/hippocampus/workspace/etc.) and pipelines **P01–P20** are **outside** K0, consuming kernel‑published topics through the bus/SSE.

> **Action isolation**: Any “action” system (P04) receives **advisory** signals only; it never executes synchronously in K0.

> **Kernel timers (allowed)**: exactly two kernel-owned timers exist — `snapshot.schedule` for nightly WAL checkpoints and `qos.tighten.schedule` (`T-15/T/T+5`) that feeds the scheduler service. All other prospective timers live in user-space pipelines (P05/P07) to avoid kernel creep.
> **Space binding**: every envelope the kernel commits includes explicit `{tenant_id, space_id, device_id}` verified against provisioning records; clients may default these in SDKs but the Gate never infers or substitutes values.

---

## 2) Language & Platform

**Primary language:** **Python 3.12** for the kernel process, ports, policy, and SPI shims — matches the surrounding stack and file layout, keeps iteration fast, and uses stable SQLite/FTS5 bindings.

**Runtime & libs**

* HTTP layer: **FastAPI + Uvicorn (h11/uvloop)**. SSE via ASGI streaming.
* Storage: **SQLite ≥ 3.45** (WAL mode), **FTS5**, **JSON1**.
* Crypto: **libsodium (ed25519)** for device signatures; **BLAKE3** for hashing (idem keys, payload hashes).
* Tracing & Metrics: **OpenTelemetry** (OTLP) + **Prometheus** client.
* Concurrency: **asyncio** with a bounded internal scheduler implementing **W‑DRR**.

**Optional accelerators (future ADR)**

* **Rust** extensions via **pyo3** for signature verification or WAL checksum hot spots; ABI stable to Python.
* Vector/ANN drivers may be separate processes (gRPC) under the same alias mapping.

> Kernel drivers and aliases (`st_epi`, `st_sem`, `st_fts`, `st_vector`, `st_kg_dom`, `st_blob`, etc.) bind at runtime via `drivers/alias_map.yaml`.

### Telemetry quickstart (OpenTelemetry + Prometheus)

Kernel 4.4 introduces real telemetry exporters. Every request receives or propagates an `X-Cognitive-Trace-Id` header, is wrapped in an OpenTelemetry span, and records basic HTTP attributes. Metrics are collected via the embedded Prometheus registry.

**Configure tracing:** By default OTLP export is disabled, so spans emit to the console only. Provide a collector endpoint when you have one available:

```yaml
# config/kernel.yaml
telemetry:
  otlp_endpoint: "https://collector.internal:4318"  # keep null to disable remote export
  otlp_headers:
    Authorization: "Bearer <token>"
  trace_sample_ratio: 0.25  # keep <=1.0
```

> Environment overrides follow the same hierarchy; e.g. `K0_KERNEL_TELEMETRY__OTLP_ENDPOINT=https://collector:4318`.

When an OTLP endpoint is present the kernel streams spans using the HTTP exporter; failures automatically fall back to console emission so telemetry never blocks request handling.

**Metrics exporter:** the in-process Prometheus registry defaults to the namespace `k0_kernel`. Adjust via `telemetry.metrics_namespace` if you need to align with existing dashboards. The `/metrics` port serializes `app.state.metrics_exporter.latest()` with the Prometheus `CONTENT_TYPE_LATEST` header for scrape targets.

**Operational probes:**

* `GET /healthz` — liveness probe returning kernel status and version metadata.
* `GET /readyz` — readiness probe gated on schema migrations and WAL replay completion. Responds with `503` until both prerequisites are complete.
* `GET /metrics` — Prometheus scrape target reflecting health/readiness gauges and request counters.

**Trace propagation:** clients should include `X-Cognitive-Trace-Id` alongside standard `traceparent` headers. The middleware ensures the value is attached to baggage (`cognitive_trace_id`) so any downstream bus/event handler can log or emit it without manual plumbing.

**Structured logging:** the kernel emits JSON logs with automatic PII redaction and the active `cognitive_trace_id`. Extend the default redaction list or change the mask token via telemetry settings:

```yaml
# config/kernel.yaml
telemetry:
  log_sensitive_keys:
    - tenant_id
    - device_id
  log_mask: "***"
```

All FastAPI, Uvicorn, and CLI logs flow through this formatter, so tenants and device identifiers are hidden even when supplied via `logger.extra`. Observability events inherit the active cognitive trace when they omit one explicitly, keeping metrics and structured logs aligned for debugging.

#### Structured logging & trace correlation

- **HTTP & ports:** `telemetry_chain` seeds `cognitive_trace_id`, `http_method`, `http_route`, and redacted tenant/space/device identifiers. Command/query/SSE handlers immediately merge envelope or payload metadata so rejections still emit traceable logs.
- **Async boundaries:** Bus dispatch middleware binds `bus_topic`, `bus_offset`, and `bus_band` before emitting spans; SSE acknowledgements capture subscriber identifiers while traversing QoS and scheduler hooks.
- **Regression coverage:** `python -m ward test --path tests/obs/test_logging.py` exercises formatter redaction, HTTP middleware propagation/reset, command envelope binding, SSE acknowledgements, and bus dispatch cleanup.
- **Operational playbook:** See `docs/development/runbooks/logging-troubleshooting.md` for end-to-end verification steps (redaction checks, trace stitching across sinks, and escalation workflow).

---

## 3) SLOs, SLIs & Error Budgets

**Scope of SLOs**: single‑node K0 instance (edge or hub), excluding user‑space handlers and async indexers.

| Surface          | SLI                    | SLO (P50/P95/P99)                                   | Notes                                                     |
| ---------------- | ---------------------- | --------------------------------------------------- | --------------------------------------------------------- |
| `command.submit` | submit→receipt latency | ≤25ms / ≤150ms / ≤400ms                             | Receipt after ACID commit; excludes async outbox drains.  |
| `query.recall`   | time to first byte     | ≤60ms / ≤250ms / ≤600ms                             | Enforced budgets: fanout ≤3, top‑k ≤8, store slice ≤75ms. |
| SSE publish      | commit→visible on SSE  | ≤120ms / ≤250ms / ≤600ms                            | Includes fan‑out and ACL checks.                          |
| Replay           | cold start catch‑up    | ≥10k events/s sustained                             | Deterministic revalidation via Schema Registry.           |
| Availability     | monthly                | `command.submit` 99.95%, `query` 99.9%, `SSE` 99.9% | Single instance; replicas raise this.                     |
| Durability       | WAL commit             | **0 or 1** outcome per idem key                     | Exactly‑once across crash/retry.                          |

**Error budget policy**: Exceeding monthly budget triggers **automatic QoS tightening** (lower fanout/top‑k) and blocks non‑critical schema upgrades until green for 72h.

**Security SLO**: PEP decision path ≤2ms P95; all denials recorded with obligations.

### Versioning & Compatibility

* **Ports & Schemas** follow Semantic Versioning. Every `schema_uri` version published in the registry **MUST** be SemVer-compliant.
* The Schema Registry serves versions **N** and **N+1** concurrently; Gate rejects versions > N+1 and PEP emits warnings for calls using N-1 during the configured sunset window.
* Port clients MUST announce supported versions via headers; Gate negotiates at admission and enforces the SemVer contract.
* Driver SPI changes ship behind capability bits; additive operations extend the bitset, while breaking changes require a new driver alias to keep existing deployments stable.

---

## 4) Kernel ABI (Syscalls)

### 4.1 Command Port

```
POST /k0/command.submit
Body: Envelope + Body (binary or JSON)
→ 200 OK {receipt_id, offsets, commit_ts}
→ 409 IDEMPOTENT_DUPLICATE {receipt_id}
→ 403 PEP_DENY | 400 REJECTED_KERNEL_GATE
→ 429 QOS_BUDGET_EXCEEDED (cross-port arbitration defers writes under sustained backlog)
```

**Path:** `PEP@syscall → Minimal Gate → Idempotency → UoW (ACID+Outbox) → WAL → Receipts/Offsets/Outbox → SSE`.

Minimal Gate canonicalises the envelope, recomputes `payload_sha256` strictly from the raw body bytes (never from `envelope_json`), and rejects any mismatch before the Unit of Work. WAL persists that value (or `NULL` if no body) alongside the envelope.

### 4.2 Query Port

```
POST /k0/query.recall
Body: {selectors, fanout_hints, qos_hints}
→ 200 OK {bundle, trace, budgets}
```

K0 enforces **hard budgets**; user‑space provides **soft hints**.

If a recall request exhausts its allocated fanout or time slice, the kernel returns `429 QOS_BUDGET_EXCEEDED` with an error envelope describing `budgets.limit`, `budgets.used`, and `budgets.policy`. Partial results accumulated before the budget breach are included in `bundle` unless the caller opts into `fail_fast=true` in the request body.

### 4.3 SSE Port

```
GET  /k0/sse.subscribe?topics=…&space_id=…&tenant_id=…&cursor_token=…
POST /k0/sse.ack {cursor}
```

Topic‑level ACLs, **per‑subscriber cursors**, and backpressure.

*Headers*: clients **MUST** include `X-SSE-Subscriber` with their stable subscriber identifier. `X-SSE-Roles` declares ACL roles and defaults to `household_device` when omitted. `X-SSE-Band` continues to steer QoS arbitration (`GREEN`/`AMBER`/`RED`).

`cursor_token` is a base64url string encoding canonical JSON `{subscriber_id, topic, space_id, tenant_id, offset}`. Clients obtain the token from SSE dispatch headers (or synthesize it from the last ack) and treat it as opaque; the kernel rejects tokens whose decoded `{space_id, tenant_id}` mismatch the query parameters. *Delivery semantics*: topics are delivered **at-least-once** per subscriber with monotonic offsets. Cursors are keyed on `{subscriber_id, topic, space_id, tenant_id}` to prevent cross-space or cross-tenant fan-out. Clients **MUST** acknowledge the highest processed offset using the schema in §5.10. If a subscriber breaches QoS budgets, K0 responds with HTTP `429` and an error envelope containing `budgets`. Cursors expire after **14 days** of inactivity; expired cursors require a cold catch-up replay starting from the retained snapshot watermark.
*HTTP 429 semantics*: the initial `GET /k0/sse.subscribe` may immediately return `429 QOS_BUDGET_EXCEEDED` if the subscriber’s budget is exhausted. Active streams can also be terminated with an HTTP 429 response; clients **SHOULD** back off, persist their last acknowledged cursor, and retry once budgets recover. `POST /k0/sse.ack` follows the same policy—budget exhaustion yields `429` with an error envelope, and the client **MUST NOT** advance its local cursor until an ack succeeds.
*Backpressure tiers*: when `lag_ms > 2000` or `pending_events > 5000`, K0 emits a `lag-warning` SSE advisory. Above `lag_ms > 5000` or `pending_events > 20000`, deliveries throttle by 50 %. Beyond `lag_ms > 15000` or `pending_events > 50000`, the kernel disconnects with `429` and requires explicit `sse.ack` to resume.

Advisories stream as `event: advisory` records preceding the subsequent `trace` events. Payloads include `{type, subscriber_id, tenant_id, space_id, lag_ms, pending_events, ack_offsets, topics[]}`; `throttled` advisories add `throttle_ratio=0.5`. When the hard shed tier triggers, the kernel terminates the stream with `429 SSE_BACKPRESSURE (reason=BACKPRESSURE_SHED)` and surfaces the same metrics in the error envelope so clients can durably persist their last cursor before retrying.

#### Post-commit bus dispatch (minimal contract)

* **Ordering** — within each topic, commit order equals publish order; offsets are strictly monotonic.
* **Delivery** — the bus and SSE facades deliver events **at-least-once**. There are **no synchronous handlers** on the commit path; dispatch happens after WAL durability.
* **Backpressure** — dispatch respects QoS arbitration; slow subscribers cannot stall commit because work yielding occurs outside the Unit of Work.

### 4.4 Observability Port

```
POST /k0/obs.emit {metrics|spans|logs}
```

Correlates with receipts and `cognitive_trace_id`.

---

## 5) Contracts & Schemas (publish in `contracts/`)

The normative invariants that guarantee durability, replay, and admission correctness are captured in `contracts/CORRECTNESS.md`. Every contract change **must** update that spec and the associated Ward suites listed therein.

### 5.1 Envelope (JSON Schema, minimal)

```json
{
  "$id": "envelope.schema.json",
  "type": "object",
  "required": ["cognitive_trace_id","tenant_id","space_id","topic","schema_uri","schema_version","actor","device_id","band","policy_version","ts","sig"],
  "properties": {
    "cognitive_trace_id": {"type":"string","format":"uuid"},
    "tenant_id": {"type":"string"},
    "topic": {"type":"string","pattern":"^(memory|events|ui|policy|infra\\.sanitized|privacy|intelligence\\.advisory)\\..+"},
    "schema_uri": {"type":"string","format":"uri"},
    "schema_version": {"type":"string"},
    "actor": {"type":"string"},
    "device_id": {"type":"string"},
    "space_id": {"type":"string"},
    "band": {"type":"string","enum":["GREEN","AMBER","RED"]},
    "policy_version": {"type":"string"},
    "ts": {"type":"string","format":"date-time"},
    "sig": {"type":"string"},
    "payload_sha256": {"type":"string","pattern":"^[0-9a-f]{64}$"},
    "idem_key": {"type":"string"}
  }
}
```

**Gate checks** (constant‑time where applicable): presence, version allow‑list via **Schema Registry**, payload hash, signature verify, size caps, idem key shape. **Reject before WAL** on any failure.

**Gate.PayloadHash contract (normative)**

```yaml
Gate.PayloadHash:
  field: payload_sha256
  computed_over: raw_body_bytes   # NOT envelope_json
  presence:
    - If body is present → payload_sha256 MUST be present and MUST match.
    - If body is absent  → payload_sha256 MUST be absent.
  on_mismatch: REJECTED_KERNEL_GATE
WAL.Write:
  st_wal.payload_sha256 := Gate.PayloadHash.value (or NULL)
```

Size caps are enforced before WAL: `max_envelope_bytes=64_000`, `max_body_bytes=4_194_304` (4 MiB), and signature verification must complete within `5ms`. Submissions exceeding these defaults are rejected with `REJECTED_KERNEL_GATE` (`reason=LIMIT_EXCEEDED`). Operators can tune the caps in `config/kernel.yaml` (see Appendix D).

**Canonical JSON requirements**

* Envelopes carrying signing or hashing material MUST be UTF-8 encoded with lexicographically sorted keys and no insignificant whitespace. Clients submitting non-canonical JSON are rejected with `REJECTED_KERNEL_GATE(reason=CANONICALIZATION_ERROR)`.
* The canonical idempotency derivation array is `[tenant_id, space_id, actor, topic, schema_uri, schema_version, payload_sha256]` serialized with RFC 8259 escaping rules; control characters are escaped, and delimiters are fixed (no commas removed or added).
* Fields like `ts`, `sig`, transport headers, and optional attributes are explicitly excluded from the derivation by the Gate; clients that pre-compute an `idem_key` must match the canonical result or be rejected.
* `payload_sha256` is computed over the raw body bytes before compression or schema decoding; `NULL` indicates the envelope carried no body.
* Minimal Gate validates `{tenant_id, space_id, device_id}` against provisioned records; missing or mismatched values surface `REJECTED_KERNEL_GATE(reason=SPACE_MISMATCH)`.

### 5.2 Receipt

```json
{
  "$id": "receipt.schema.json",
  "type": "object",
  "required": ["receipt_id","idem_key","wal_pos","commit_ts","payload_sha256","mls_group_id","key_version","device_sig"],
  "properties": {
    "receipt_id":{"type":"string","format":"uuid"},
    "idem_key":{"type":"string"},
    "wal_pos":{"type":"integer","minimum":0},
    "commit_ts":{"type":"string","format":"date-time"},
    "payload_sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},
    "mls_group_id":{"type":"string"},
    "key_version":{"type":"string"},
    "device_sig":{"type":"string"},
    "obligations":{"type":"array","items":{"type":"string"}}
  }
}
```

Canonical signing order: `[receipt_id, idem_key, wal_pos, commit_ts, payload_sha256, mls_group_id, key_version, obligations]` encoded as canonical JSON (UTF-8, sorted keys, no insignificant whitespace) before ed25519 signing. `mls_group_id` and `key_version` **MUST** be populated for every `band=GREEN` submission so MLS lineage is provable end-to-end.

### 5.3 Offsets/Cursor

```json
{
  "$id":"offset.cursor.schema.json",
  "type":"object",
  "required":["subscriber_id","topic","space_id","tenant_id","offset","ts"],
  "properties":{
    "subscriber_id":{"type":"string"},
    "topic":{"type":"string"},
    "space_id":{"type":"string"},
    "tenant_id":{"type":"string"},
    "offset":{"type":"integer","minimum":0},
    "ts":{"type":"string","format":"date-time"}
  }
}
```

### 5.4 PEP preflight contract (`pep.schema.json`)

Defines inputs (band, ABAC attributes, caps) and outputs (admit/deny, obligations set), executed **at syscall**.

### 5.5 OpenAPI (excerpt)

```yaml
openapi: 3.1.0
info: {title: K0 Ports, version: 1.0.0}
paths:
  /k0/command.submit:
    post:
      requestBody: {content: {application/json: {schema: {$ref: "./jsonschema/envelope.schema.json"}}}}
      responses:
        "200": {description: Receipt, content: {application/json: {schema: {$ref: "./jsonschema/receipt.schema.json"}}}}
        "409": {description: Idempotent duplicate}
        "403": {description: PEP deny}
        "400": {description: Gate reject, content: {application/json: {schema: {$ref: "./jsonschema/error.schema.json"}}}}
        "429": {description: QoS budget exceeded, content: {application/json: {schema: {$ref: "./jsonschema/error.schema.json"}}}}
  /k0/query.recall:
    post:
      requestBody: {content: {application/json: {schema: {$ref: "./jsonschema/query.recall.request.json"}}}}
      responses:
        "200": {description: Bundle, content: {application/json: {schema: {$ref: "./jsonschema/query.recall.response.json"}}}}
        "429": {description: QoS budget exceeded, content: {application/json: {schema: {$ref: "./jsonschema/error.schema.json"}}}}
  /k0/sse.subscribe:
    get:
      parameters:
        - {in: query, name: topics, required: true, schema: {type: string}, description: Comma-separated list of topic prefixes}
        - {in: query, name: space_id, required: true, schema: {type: string}, description: Space namespace binding the stream}
        - {in: query, name: tenant_id, required: true, schema: {type: string}, description: Tenant namespace binding the stream}
        - {in: query, name: cursor_token, required: false, schema: {type: string}, description: Base64url token encoding {subscriber_id, topic, space_id, tenant_id, offset}}
      responses:
        "200": {description: SSE stream}
        "429": {description: QoS budget exceeded, content: {application/json: {schema: {$ref: "./jsonschema/error.schema.json"}}}}
  /k0/sse.ack:
    post:
      requestBody: {content: {application/json: {schema: {$ref: "./jsonschema/sse.ack.request.json"}}}}
      responses:
        "204": {description: Ack accepted}
        "429": {description: QoS budget exceeded, content: {application/json: {schema: {$ref: "./jsonschema/error.schema.json"}}}}
  /k0/obs.emit: {post: {responses: {"204": {description: accepted}}}}
```

### 5.6 AsyncAPI (topics)

Expose **`memory.*`**, **`events.*`**, **`ui.*`**, **`policy.*` (admin)**, **`infra.sanitized.*` (admin)**, **`privacy.*` (privacy/compliance)**, **`intelligence.advisory.*`** with offset semantics and delivery guarantees; ACLs enforced via K0.SSE driver.

| Topic prefix | Durability | ACL class | Notes |
| ------------- | ---------- | --------- | ----- |
| `memory.*` | WAL + snapshot | Household devices | Primary episodic/semantic writes |
| `events.*` | WAL + outbox | System services | Infrastructure auditing, observability |
| `ui.*` | WAL (short retention) | UI clients | Fan-out limited (top-k ≤ 4) |
| `policy.*` | WAL + DLQ | Security operators only | Contains obligations/redaction outcomes |
| `infra.sanitized.*` | WAL (sanitized) | Ops/SRE | Redacted infrastructure metrics |
| `infra.snapshot.*` | Snapshot manifest + WAL watermark | Ops/SRE (retention stewards) | Announces snapshot windows, watermark checkpoints |
| `privacy.*` | WAL + encrypted blob | Privacy/compliance | Holds redaction receipts and consent updates |
| `intelligence.advisory.*` | WAL + SSE | Advisory consumers (P04) | Read-only advisory signals |

```json
{
  "$id": "infra.snapshot.event.json",
  "type": "object",
  "required": ["type", "watermark", "snapshot_id"],
  "properties": {
    "type": {"type": "string", "enum": ["BEGIN", "COMMIT"]},
    "watermark": {"type": "integer", "minimum": 0},
    "snapshot_id": {"type": "string"}
  }
}
```

Tooling **MUST** validate that `watermark` matches the corresponding WAL markers and that `snapshot_id` aligns with snapshot artifacts.

### 5.7 Schema Registry Lifecycle

* **States**: schemas move through `REGISTERED → ACTIVE → DEPRECATED`; emergency blocks flip status to `BLOCKED` and trigger gate rejects. Promotion automatically enforces an N/N+1 window by demoting the previous `ACTIVE` version to `DEPRECATED` and blocking any older `DEPRECATED` entries.
* **Registration**: only trusted operators (or signed CI bundles) run `k0ctl schema register --uri … --version … --sha256 …`. Registrations enter the registry as `REGISTERED`, are cached in-process, and may be activated immediately with `--activate` once validation completes.
* **Promotion**: Minimal Gate accepts only `ACTIVE` schemas; promotion happens via `k0ctl schema promote --uri … --version …`. The command promotes the requested version, marks the prior `ACTIVE` version as `DEPRECATED`, and blocks older superseded entries so replay surfaces at most N/N+1.
* **Blocking & rollback**: `k0ctl schema block --uri … --version … [--reason …]` flips status to `BLOCKED` for emergency stops. Existing WAL entries stay durable; future submissions are rejected before WAL. Reactivation is performed by re-promoting a healthy version after root cause analysis.
* **Audit trail**: every transition appends to an audit table and emits an Observability event so security can trace who changed what and when. (Pending future work to expose CLI-visible metadata.)

Typical operator flow:

```shell
k0ctl schema register --uri https://contracts.family-ai.dev/schemas/memory.snapshot.json --version 1.0.0 --sha256 <digest>
k0ctl schema promote --uri https://contracts.family-ai.dev/schemas/memory.snapshot.json --version 1.0.0
k0ctl schema register --uri https://contracts.family-ai.dev/schemas/memory.snapshot.json --version 1.1.0 --sha256 <digest> --activate
k0ctl schema block --uri https://contracts.family-ai.dev/schemas/memory.snapshot.json --version 1.0.0 --reason "sunset window elapsed"
```

| Registry state | Command port behaviour | Replay behaviour | Sunset window |
| -------------- | ---------------------- | ---------------- | ------------- |
| `REGISTERED` | Reject (`REJECTED_KERNEL_GATE`) until promoted | Not visible | N/A |
| `ACTIVE` | Accept new writes and include in idempotency ledger | Replay allowed | N/A |
| `DEPRECATED` | Accept new writes until `sunset_at`; after that return `REJECTED_KERNEL_GATE` | Replay allowed indefinitely | Configurable per schema |
| `BLOCKED` | Immediate `REJECTED_KERNEL_GATE` | Replay halted; operator intervention required | N/A |

Sunset windows are declared in `contracts/policy/pep.schema.json` and surfaced to operators via `k0ctl schema inspect`.

### 5.8 Error Envelope (JSON Schema)

```json
{
  "$id": "error.schema.json",
  "type": "object",
  "required": ["error"],
  "properties": {
    "error": {
      "type": "object",
      "required": ["code", "reason", "trace_id", "component"],
      "properties": {
        "code": {"type": "string"},
        "reason": {"type": "string", "pattern": "^[A-Z0-9_]+$"},
        "trace_id": {"type": "string", "format": "uuid"},
        "component": {"type": "string"},
        "hint": {"type": "string"},
        "budgets": {
          "type": "object",
          "additionalProperties": {
            "type": "integer",
            "minimum": 0
          }
        },
        "details": {
          "type": "object",
          "additionalProperties": true
        }
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

All error responses **MUST** conform to this envelope. `component` pinpoints the rejecting subsystem (for example `kernel.gate`, `kernel.policy`, or `kernel.qos`). When QoS budgets are exceeded, the kernel returns HTTP `429` with a populated `budgets` object and a `details.cap` describing the constrained resource.

### 5.9 Query Recall Schema

```json
{
  "$id": "query.recall.request.json",
  "type": "object",
  "required": ["selectors","space_id"],
  "properties": {
    "selectors": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "topic": {"type": "string"},
          "limit": {"type": "integer", "minimum": 1}
        },
        "additionalProperties": false
      }
    },
    "space_id": {"type": "string"},
    "fanout_hints": {"type": "object"},
    "qos_hints": {"type": "object"}
  }
}
```

```json
{
  "$id": "query.recall.response.json",
  "type": "object",
  "required": ["bundle", "trace", "budgets"],
  "properties": {
    "bundle": {"type": "object"},
    "trace": {"type": "object"},
    "budgets": {
      "type": "object",
      "required": ["fanout", "time_slice"],
      "properties": {
        "fanout": {"type": "integer", "minimum": 0},
        "time_slice": {"type": "integer", "minimum": 0},
        "policy": {"type": "string"}
      }
    }
  }
}
```

`space_id` scopes the recall to a single namespace; the kernel rejects requests where selectors reference topics outside the declared space to prevent cross-space leakage.

### 5.10 SSE Ack Schema

```json
{
  "$id": "sse.ack.request.json",
  "type": "object",
  "required": ["subscriber_id", "topic", "space_id", "tenant_id", "offset"],
  "properties": {
    "subscriber_id": {"type": "string"},
    "topic": {"type": "string"},
    "space_id": {"type": "string"},
    "tenant_id": {"type": "string"},
    "offset": {"type": "integer", "minimum": 0},
    "ack_ts": {"type": "string", "format": "date-time"}
  }
}
```


`tenant_id` and `space_id` are required across the envelope, offsets, and SSE acks; the kernel refuses to infer defaults and reconciles all replay/sync per `{tenant_id, space_id}`.

---

## 6) Storage Layout (ACID & Async)

**ACID cohort (single txn)**: SQLite tables for episodic/semantic/receipts/offsets/outbox + optional FTS shadow tables.
**Async cohort**: vector/embeddings/KG/blob updated idempotently via Outbox + Indexer. **Aliases** decouple user‑space from engines; indexers apply operations via the **Driver SPI**.

### 6.1 SQL DDL (core)

```sql
-- WAL (append-only)
CREATE TABLE IF NOT EXISTS st_wal (
  pos INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  topic TEXT NOT NULL,
  envelope_json TEXT NOT NULL,
  body BLOB,
  payload_sha256 TEXT,
  schema_uri TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  idem_key TEXT,
  device_id TEXT NOT NULL,
  commit_ts TEXT NOT NULL
);

-- Idempotency ledger
CREATE TABLE IF NOT EXISTS idem_ledger (
  idem_key TEXT PRIMARY KEY,
  receipt_id TEXT NOT NULL,
  first_seen_ts TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('COMMITTED','REJECTED')),
  expiry_ts TEXT
);

-- Receipts
CREATE TABLE IF NOT EXISTS st_receipts (
  receipt_id TEXT PRIMARY KEY,
  idem_key TEXT NOT NULL,
  wal_pos INTEGER NOT NULL,
  commit_ts TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  mls_group_id TEXT NOT NULL,
  key_version TEXT NOT NULL,
  device_sig TEXT NOT NULL
);

-- Offsets (per topic/subscriber)
CREATE TABLE IF NOT EXISTS st_offsets (
  subscriber_id TEXT NOT NULL,
  topic TEXT NOT NULL,
  space_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  offset INTEGER NOT NULL,
  updated_ts TEXT NOT NULL,
  PRIMARY KEY(subscriber_id, topic, space_id, tenant_id)
);

-- Provisioned devices ledger (device bindings only)
CREATE TABLE IF NOT EXISTS st_devices (
  device_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  mls_group_id TEXT NOT NULL,
  provisioned_ts TEXT NOT NULL
);

-- Device keys with rotation support (ADR 001)
CREATE TABLE IF NOT EXISTS st_device_keys (
  device_id TEXT NOT NULL,
  key_version TEXT NOT NULL,
  verify_key TEXT NOT NULL,
  key_state TEXT NOT NULL DEFAULT 'ACTIVE'
    CHECK(key_state IN ('PENDING','ACTIVE','ROTATING','REVOKED')),
  registered_ts TEXT NOT NULL,
  activated_ts TEXT,
  rotated_ts TEXT,
  revoked_ts TEXT,
  grace_expires_ts TEXT,
  revocation_reason TEXT,
  PRIMARY KEY(device_id, key_version),
  FOREIGN KEY(device_id) REFERENCES st_devices(device_id)
);

-- Outbox (async intents)
CREATE TABLE IF NOT EXISTS st_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wal_pos INTEGER NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  driver TEXT NOT NULL,
  op_kind TEXT NOT NULL,
  payload BLOB NOT NULL,
  fingerprint TEXT NOT NULL,
  requeue_seq INTEGER NOT NULL DEFAULT 0,
  retries INTEGER NOT NULL DEFAULT 0,
  last_error TEXT
);

CREATE TABLE IF NOT EXISTS st_dlq (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wal_pos INTEGER,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  driver TEXT NOT NULL,
  op_kind TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  payload BLOB NOT NULL,
  reason TEXT NOT NULL,
  retries INTEGER NOT NULL DEFAULT 0,
  requeue_seq INTEGER NOT NULL DEFAULT 0,
  first_failure_ts TEXT NOT NULL,
  last_failure_ts TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'PENDING'
    CHECK(state IN ('PENDING','REQUEUED','QUARANTINED'))
);

-- Schema registry with audit trail (ADR 002)
CREATE TABLE IF NOT EXISTS schema_registry (
  schema_uri TEXT NOT NULL,
  version TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('REGISTERED','ACTIVE','DEPRECATED','BLOCKED')),
  operator_id TEXT,
  blocked_ts TEXT,
  blocked_reason TEXT,
  unblocked_ts TEXT,
  PRIMARY KEY(schema_uri, version)
);

-- Indexes
DROP INDEX IF EXISTS idx_outbox_fingerprint_space;
CREATE INDEX IF NOT EXISTS idx_wal_space_pos ON st_wal(space_id, pos);
CREATE INDEX IF NOT EXISTS idx_wal_tenant_topic ON st_wal(tenant_id, topic, pos);
CREATE INDEX IF NOT EXISTS idx_receipts_space ON st_receipts(space_id, wal_pos);
CREATE INDEX IF NOT EXISTS idx_receipts_walpos ON st_receipts(wal_pos);
CREATE INDEX IF NOT EXISTS idx_outbox_space ON st_outbox(space_id, requeue_seq, id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_outbox_idem ON st_outbox(tenant_id, space_id, driver, fingerprint, requeue_seq);
CREATE INDEX IF NOT EXISTS idx_dlq_space ON st_dlq(space_id, first_failure_ts);
CREATE INDEX IF NOT EXISTS idx_device_keys_state ON st_device_keys(device_id, key_state);
```

`st_devices` backs the provisioning ledger consumed by Minimal Gate checks (see §15) and is populated exclusively through `k0ctl provision`. Additional tables (episodic, semantic, FTS, KG, blobs) are accessed through **driver aliases** and implemented in `drivers/*`.

### 6.2 WAL Retention & Snapshots

* **Retention horizon**: maintain WAL segments for the longer of **7 days** or **10 million events**. Segments older than the horizon are pruned only after a successful snapshot.
* **Nightly snapshots**: persist a compressed checkpoint containing `st_wal` up to a `watermark`, `st_offsets`, `idem_ledger`, and `schema_registry` digests. Snapshots are versioned and stored according to the tenancy policy (per-tenant path when isolated). Each snapshot marks `SNAPSHOT_BEGIN{watermark}` before capture and finalizes with `SNAPSHOT_COMMIT{watermark}` when durable; retention workers refuse to prune segments with dangling begin markers.
* **Restore flow**: load the latest snapshot → restore offsets/ledger tables → ensure the latest watermark has a matching commit marker → replay WAL from `watermark + 1` through current tip. Replay success requires `replay_parity_failures == 0` before opening ports.
* **Compaction**: during snapshot creation, run SQLite `VACUUM` on `st_outbox`, `st_dlq`, and derivative tables to control file growth. Compaction respects ongoing transactions via snapshot isolation.
* **Per-space replay**: `idx_wal_space_pos` and `idx_receipts_space` allow selective restore for a single `{tenant_id, space_id}`; `k0ctl replay --tenant <tenant_id> --space <space_id>` replays only that namespace, emitting `merge.applied` events for CRDT reconciliation.

Topic-specific retention overrides live in `config/kernel.yaml` under `retention.topics`. Defaults: `ui.*` keeps 2 days or 1 million events (whichever first), `policy.*` extends to 30 days or 20 million events, and `infra.sanitized.*` retains 14 days. Per-space overrides live under `retention.spaces` (e.g., `shared:household` keeps 30 days while `personal:*` keeps 14). All other topics inherit the global horizon (7 days / 10 million events).

### 6.3 Tenancy Model

K0 supports two deployment modes:

* **Logical tenancy (default edge mode)**: a shared SQLite database with tenancy columns (`tenant_id`, `space_id`) and strict row-level predicates enforced inside the Unit of Work. QoS budgets are partitioned per tenant in `qos/defaults.yaml`.
* **Physical tenancy (hub/server mode)**: each tenant binds to an isolated SQLite database path with dedicated WAL and snapshot schedule. The alias map is tenant-scoped, ensuring storage-level separation.

Operators **MUST** choose the appropriate isolation model during provisioning; switching modes requires draining traffic and replaying from WAL into the new layout.

Regardless of mode, WAL, receipts, offsets, and outbox rows retain both `tenant_id` and `space_id`. Secondary indexes (`idx_wal_space_pos`, `idx_receipts_space`) support selective replay, DSAR exports, and conflict resolution per space. SSE cursors and QoS budgets also partition on `space_id` to prevent cross-space bleed.

---

## 7) Driver SPI & Alias Map

**SPI (per driver)**

* **ACID:** `open(config) → handle`, `begin/commit/rollback(handle)`, `append/read/scan`.
* **Async:** `prepare(payload) → op`, `apply(op)`, `fingerprint(op)` (must be deterministic and side‑effect free).
* **Lifecycle:** `seal/gc/replay_range`.

**Aliases** decouple logic from concrete engines and match your diagrams’ store names (`st_epi`, `st_sem`, `st_fts`, `st_vector`, `st_kg_dom`, `st_blob`, …). Bindings live in `drivers/alias_map.yaml`.

### Driver handshakes

* **Endpoint**: `POST /k0/driver.handshake` registers or refreshes a driver session for a specific alias. The request body aligns with `jsonschema/driver.handshake.request.json` and returns `driver.handshake.response.json` on success.
* **Transports**: HTTP drivers provide an `endpoint` (e.g., `https://indexer.local/apply`) that the kernel invokes with JSON-encoded outbox entries. gRPC drivers supply an authority/target (e.g., `dns:///indexer:7443`) and use the session metadata to establish their own channel.
* **Session lease**: Each handshake issues a 5-minute lease (`lease_seconds=300`) and a 32-character hex `session_id`. Renewals replace the active session and rotate the HTTP adapter without disrupting in-flight work.
* **Headers & payloads**: HTTP adapters deliver outbox payloads as canonical JSON with a `payload_base64` field and include `X-K0-Driver-Session: <session_id>` for auditing. Non-2xx responses or network errors trigger the standard retry/DLQ flow.
* **Metrics**: Every accepted handshake increments `k0_driver_handshakes_total{alias,transport}`; remote apply attempts reuse the existing outbox success/retry/quarantine metrics.

---

## 8) QoS & Budgets

K0 runs a **global, work‑conserving W‑DRR scheduler** implemented in `qos/scheduler.py`. All ports enqueue work into the shared scheduler with metadata `{band, port, payload_size, trace}` and receive **permission tokens** before executing.

* **Band weights**: defaults of `GREEN=8`, `AMBER=4`, `RED=1` keep policy bands fair; per-port multipliers (e.g., `command=1.1`, `query=1.0`, `sse=0.9`) are applied when the queue is under stress so writes stay ahead of recalls with minimal starvation.
* **Write budgets**: concurrency caps, size thresholds, and fast-lane boosts for GREEN actors. Scheduler blocks new writes once WAL/fsync pressure crosses configured thresholds.
* **Read budgets**: fanout ≤ 3 stores, top‑k ≤ 8, per-store slice ≤ 75 ms, query concurrency caps; tokens expire if a store exceeds its slice so lagging stores cannot monopolize time.
* **Dynamic tightening**: when error budgets erode or SSE lag spikes, PEP/Risk services push an update via the scheduler API to lower fanout/top‑k or shift band weights; releases of new weights are versioned in `qos/defaults.yaml`.
* **Cross-port arbitration**: when `sse_lag_ms p95 > 2000` for 5 minutes, the scheduler automatically promotes SSE work by applying a `sse=1.2` multiplier and caps new `query` tokens to prevent backlog. If lag persists > 15 minutes, command port submissions for AMBER/RED tenants receive temporary deferrals (`429` with budgets) until backlog clears.

**Fairness guarantees**: the scheduler maintains a deficit counter per `{band, port}` queue. Every dispatch cycle increments counters by `weight × quantum` (default quantum: 4). A queue is eligible when `deficit ≥ cost(payload_size)`. After serving, the deficit is reduced by the actual cost; unused deficit carries over, guaranteeing eventual service. Starvation bounds: any queue with enqueued work receives a token within `ceil(total_weight / weight_queue)` cycles. The metrics `scheduler_queue_depth{band,port}`, `scheduler_starvation_bound` (theoretical), and `scheduler_starvation_cycles` (observed) are emitted on every tick; `scheduler_starvation_cycles` must remain ≤ 2 × the theoretical bound.

Budgets and active scheduler weights surface as **SSE observability** so operators can correlate policy changes with latency.

Tenant isolation harness: Ward suite `tests/qos/test_starvation_bounds.py` runs opposing workloads (write-heavy vs read-heavy tenants) and asserts that P95 latency does not degrade beyond the documented budget share while `scheduler_starvation_cycles` remains within the bound defined in `contracts/CORRECTNESS.md`.

---

## 9) Idempotency, Receipts, Replay, DLQ

* **Idempotency**: deterministic `idem_key` from stable envelope fields (and optional client key). Dedup **before UoW**. The canonical derivation **MUST** follow the table below:

| Field order | Description | Notes |
| ----------- | ----------- | ----- |
| 1 | `tenant_id` | UTF-8 string |
| 2 | `space_id` | UTF-8 string |
| 3 | `actor` | UTF-8 string |
| 4 | `topic` | UTF-8 string |
| 5 | `schema_uri` | Canonical URI string |
| 6 | `schema_version` | String |
| 7 | `payload_sha256` | Hex digest of SHA-256 over raw body bytes |

The concatenation is encoded as canonical JSON array without whitespace, then hashed with **BLAKE3**. Fields such as `ts`, `sig`, and any transport headers are **excluded**. If a client supplies an `idem_key`, the kernel **MUST** validate it matches the canonical derivation; mismatches are rejected with `REJECTED_KERNEL_GATE`.
In the (theoretical) case of a BLAKE3 collision, the kernel treats the submission as `REJECTED_KERNEL_GATE`, emits the `idem_collision_detected` incident signal, and records a security event before persisting anything to the WAL.
Gate-level validation recomputes the canonical digest for every request and surfaces `REJECTED_KERNEL_GATE(reason=IDEM_KEY_INVALID)` when the client provides a malformed digest and `REJECTED_KERNEL_GATE(reason=IDEM_KEY_MISMATCH)` when the supplied value diverges from the canonical derivation.
Duplicate submissions that reach the command port return **HTTP 409 `IDEMPOTENT_DUPLICATE`** with the existing receipt metadata. Each duplicate increments the `command_idempotency_duplicates_total` counter and emits a `command_idem_duplicate` observability event annotated with the envelope’s `cognitive_trace_id`, `{tenant_id, space_id}`, and the persisted receipt identifier.
* **Receipts**: device‑signed with **ed25519** over canonical JSON (sorted keys, UTF-8, no whitespace). The signing payload is `{receipt_id, idem_key, wal_pos, commit_ts, payload_sha256, mls_group_id, key_version, obligations}`; the signer key version is embedded as `device_sig.key_version` for rotation audits. If signing fails after a successful ACID commit, the kernel persists the receipt payload, emits `receipt_sign_error` telemetry, and immediately places an advisory event on the Outbox so the client can re-fetch and sign locally.
* **Outbox fingerprints**: each Outbox entry stores `{tenant_id, space_id, driver, op_kind, payload}` hashed via `blake3` (sorted keys) to guarantee idempotent `apply()`; `requeue_seq` defaults to 0 and increments with each replay-triggered requeue.
* **Outbox retry schedule**: exponential backoff starting at 250 ms with factor 2.0 and ±20 % jitter, capped at 5 attempts before the entry moves to DLQ with the last error context and `outbox_retry_exhausted{driver}` is emitted.

| Attempt | Target delay (ms) | Notes |
| ------- | ----------------- | ----- |
| 1       | 250               | jitter ±20 % |
| 2       | 500               | jitter ±20 % |
| 3       | 1 000             | jitter ±20 % |
| 4       | 2 000             | jitter ±20 % |
| 5       | 4 000             | final attempt before DLQ |

* **Indexer handshake**: indexers acknowledge successful application by deleting the Outbox row within the same transaction (or via an authenticated callback); missing acks keep the entry pending and increment `retries`.
* **Replay**: cold replayer validates envelopes via the **Schema Registry**, rebuilds offsets, and replays Outbox entries through the same SPI so async cohorts converge. Replay succeeds only when the following invariants hold: `count(st_wal.topic) == count(st_receipts.topic)`, each Outbox fingerprint applied ≤ 1, and the highest offset per subscriber matches the WAL watermark. Violations increment `replay_parity_failures` and prevent ports from re-opening.
* **DLQ**: only semantically valid but failing entries; kernel‑invalid items never enter the WAL. Each entry moves through `PENDING → RETRYING → QUARANTINED`. Operators can transition to `REQUEUED` via `k0ctl dlq requeue`, which preserves the original fingerprint, increments `requeue_seq`, and writes the pair `(fingerprint, requeue_seq)` back into the Outbox row. Drivers MUST treat `(fingerprint, requeue_seq)` as their idempotency key. DLQ entries record fingerprint, last error, first/last failure timestamps, and retry count to aid replay diagnostics.

All invariants governing WAL/receipt monotonicity, outbox uniqueness, snapshot watermarks, and schema gating are codified in `contracts/CORRECTNESS.md` and enforced by Ward suites under `tests/correctness/`, `tests/snapshots/`, and `tests/dlq/`.

---

## 10) Security & Policy

* **PEP@syscall**: band/caps/ABAC preflight; any redaction obligations are attached to receipts and/or outbox.
* **SSE ACL**: topic allow/deny by role/age/device; `intelligence.*` and `policy.*` require elevated scopes.
* **Keying**: MLS groups/key material are **outside** the write commit path; K0 validates device signatures on envelopes/receipts and logs the key version used.
* **Key lifecycle**: security maintains an authoritative key registry; rotations accept overlapping versions for a grace window (default 30 minutes for GREEN, immediate for RED). Revocations propagate through PEP obligations, cached key allow-lists expire every **5 minutes**, and the kernel rejects further writes once a key is marked revoked.
  * Failure mapping: signature mismatch → `REJECTED_KERNEL_GATE`, schema status violations (`REGISTERED`, `DEPRECATED` beyond sunset, `BLOCKED`) → `REJECTED_KERNEL_GATE`, revoked key or ABAC/band/cap breaches → `PEP_DENY` with obligation to rotate credentials or adjust policy.
* **Obligations**: PEP can request "re-encrypt with MLS group" or "force device re-auth" obligations; kernel records them with the receipt so downstream services can act.
* **Signature throughput caps**: `config/kernel.yaml` enforces per-tenant limits on signature verifications per second; attempts beyond the cap surface `REJECTED_KERNEL_GATE(reason=SIG_BUDGET)`.
* **MLS provenance**: receipts include `mls_group_id` and `key_version`, and SSE fan-out ensures all subscribers for a space use the same MLS lineage; mismatches trigger `REJECTED_KERNEL_GATE(reason=MLS_MISMATCH)`.

---

## 11) Observability

SLIs are exported via Prometheus and OTEL and correlated on `cognitive_trace_id`:

* **Latency**: submit→receipt, recall, SSE end‑to‑end, replay catch‑up.
* **Correctness**: `kernel_gate_rejects`, `idem_duplicates_blocked`, `replay_parity_failures`, `dlq_size`.
* **QoS**: per-user budget usage, queue depth, active scheduler weights, `scheduler_starvation_bound`, `scheduler_starvation_cycles`, and tenant-partitioned queue metrics for drift detection.
* **Snapshots**: `snapshot_open_transactions`, `snapshot_dangling_markers`, and watermark gauges to confirm `SNAPSHOT_BEGIN/COMMIT` pairs.
* **Spaces**: per-`space_id` WAL replay lag, SSE backlog, and sync counters (`space_replay_lag_ms`, `space_merge_events_applied`).
* **Security**: `pep_denies`, `advisory_bypass_attempts`.
* **Backpressure**: `sse_lag_ms`, `throttled_subscribers`, and `scheduler_tightening_events` surface when we shed slow consumers.

Alerting thresholds:

* `scheduler_tightening_events > 3/hr` → page SRE.
* `sse_lag_ms{p95} > 2000` for 5 minutes → high priority incident.
* `key_rotation_events{event="revoked"} > 0` → security on-call.
* `replay_parity_failures > 0` → block command port and initiate incident response.
* `snapshot_dangling_markers > 0` for >5 minutes → page storage SRE.

---

## 12) Folder Structure (authoritative) & What’s in Each File

```
k0/
├─ ports/
│  ├─ command.py            # submit(); PEP→Gate→Idem→UoW; 200/409/403/400 mapping
│  ├─ query.py              # recall(); enforces budgets; fans out via alias adapters
│  ├─ sse.py                # subscribe()/ack(); ACL, cursors, backpressure
│  └─ observe.py            # obs.emit(); OTEL/Prometheus exporters
│
├─ policy/
│  ├─ pep_syscall.py        # ABAC/caps/bands; obligation emission
│  └─ redaction.py          # obligation tracking + outbox hooks
│
├─ gate/
│  ├─ schema_registry.py    # uri→version→hash; ACTIVE/N+1 policy
│  └─ minimal_gate.py       # envelope presence/hash/sig/size; reject before WAL
│
├─ idem/
│  └─ ledger.py             # idem key hash; lookup/set; expiry GC
│
├─ uow/
│  ├─ unit_of_work.py       # context manager; ACID writes + staged Outbox (single txn)
│  └─ connection_pool.py    # per-driver pools, leases, timeouts
│
├─ storage/
│  ├─ wal.py                # append-only log, segmenting, fsync strategy
│  ├─ receipts.py           # device-signed receipts; correlation to WAL pos
│  ├─ offsets.py            # per topic/subscriber cursors
│  ├─ outbox.py             # async intents with deterministic fingerprints
│  ├─ dlq.py                # DLQ insert/replay fences
│  └─ replayer.py           # cold replay; parity checks; offsets rebuild
│
├─ drivers/                 # SPI implementations
│  ├─ sqlite.py             # ACID tables, tx hooks, FTS shadow mgmt
│  ├─ fts5.py               # FTS integration (optional in-tx)
│  ├─ faiss.py              # vector ops (async apply)
│  ├─ sqlite_kg.py          # graph tables & ops
│  ├─ blob_localfs.py       # content-addressed blobs
│  ├─ alias_map.yaml        # alias→driver binding
│  └─ conformance/          # driver SPI fuzz + crash harnesses
│
├─ qos/
│  ├─ scheduler.py          # W-DRR; enforcement of hard budgets
│  └─ defaults.yaml         # fanout/topk/time-slices; per-tenant overrides
│
├─ sse/
│  ├─ server.py             # ASGI SSE mux; cursors; acks; heartbeats
│  └─ acl.yaml              # topic ACL rules
│
├─ bus/
│  ├─ core.py               # post-commit dispatch to facades
│  └─ middleware.py         # timestamps, tracing
│
├─ obs/
│  ├─ metrics.py            # Prom counters/histograms
│  └─ tracing.py            # OTEL spans/ids
│
├─ config/
│  ├─ kernel.yaml           # band limits, thresholds, retry/DLQ policy
│  └─ logging.yaml          # structured logs; sinks
│
├─ contracts/
│  ├─ openapi.k0.yaml       # Ports API
│  ├─ asyncapi.events.yaml  # Topics & offset semantics
│  ├─ jsonschema/
│  │  ├─ envelope.schema.json
│  │  └─ receipt.schema.json
│  ├─ CORRECTNESS.md        # invariants, deny matrix, snapshot protocol
│  └─ policy/pep.schema.json
│
├─ cli/
│  └─ k0ctl.py              # admin: register schema, replay, reindex
│
├─ tests/
│  ├─ test_gate.py
│  ├─ test_idem.py
│  ├─ test_uow_acid.py
│  ├─ test_outbox_indexer.py
│  ├─ test_replay.py
│  ├─ test_sse_acl.py
│  ├─ test_qos.py
│  ├─ correctness/          # WAL/receipt/outbox invariants
│  ├─ snapshots/            # watermark protocol
│  └─ security/             # revocation race coverage
├─ perf/
│  ├─ profiles/             # workload definitions (small/medium/large)
│  └─ dashboards/           # grafana + alert configs; see render.py + generated assets
└─ README.md
```

> The above aligns with your API planes, bus facade, storage primitives, and pipeline boundaries; cognition remains outside the kernel (P01–P20 consumers), consistent with the diagrams.

---

## 13) Error Surface & Taxonomy

* **400 `REJECTED_KERNEL_GATE`** — envelope/schema/signature/size invalid; not written to WAL.
* **403 `PEP_DENY`** — policy deny or unmet obligations; not written to WAL.
* **409 `IDEMPOTENT_DUPLICATE`** — idem key already committed; response returns existing `receipt_id`.
* **429 `QOS_BUDGET_EXCEEDED`** — hard budget exhausted; body follows the error envelope with populated `budgets`.
* **5xx** — kernel internal (ACID failure → automatic rollback); outbox failures do **not** affect commit.

All errors are trace‑correlated and attach `cognitive_trace_id`.

Schema/catalog violations, payload hash mismatches, and size cap breaches surface as `REJECTED_KERNEL_GATE`; band/cap/ABAC denials, revocations, or policy obligations surface as `PEP_DENY`.

---

## 14) End‑to‑End Flows

### 14.1 Write (Command → Durable)

`App → PEP@syscall → MinimalGate → Idempotency → UoW (ACID) → WAL → Receipts/Offsets/Outbox → SSE → Indexers (async)`.

Commit finishes before any user‑space handling; effects flow via bus/SSE and outbox indexers.

### 14.2 Recall (Query → Bundle)

`App → Query Port → QoS (hard budgets) → user‑space retrieval (soft hints) → store adapters → fused bundle`.

---

## 15) Configuration (defaults)

* **`config/kernel.yaml`**: bands, thresholds (fast‑lane confidence = 0.90; relax to 0.85 under GREEN pressure for WRITE/RECALL), retry budgets, DLQ policy, signature verification caps, and watermark retention settings.
  * `database.path`: filesystem location for the kernel SQLite datastore. Override via the layered loader (`K0_KERNEL_DATABASE__PATH`) or CLI flags when deploying to dedicated volumes.
  * `server.host` / `server.port` / `server.log_level` / `server.timeout_graceful_shutdown`: runtime host binding, port, log verbosity, and shutdown drain window used by the embedded Uvicorn harness. These values feed both `k0.kernel.main` and `k0ctl serve` unless overridden at the CLI.
* **`qos/defaults.yaml`**: fanout/top‑k/time slices/concurrency caps + band weights and port multipliers.
* **`sse/acl.yaml`**: topic allow/deny per role.
* **`drivers/*/config.yaml`**: engine‑specific limits.
* **`cli/k0ctl.py`**: operator workflows for schema promotion, replay, DLQ drains, scheduler tuning, and hot configuration reload (`k0ctl config reload`) which applies updated YAMLs atomically and emits `config.changed` on the bus.

### 15.1 Layered runtime settings loader

The `KernelSettings` model in `k0/kernel/config.py` resolves configuration in three layers, merging them into a single validated document:

1. **Base YAML file** — defaults to `config/kernel.yaml` or an explicit path supplied via `K0_KERNEL_CONFIG_FILE` (env) or `--config` (CLI).
2. **Environment overrides** — variables prefixed with `K0_KERNEL_` are mapped into nested keys using double underscores (`__`) as separators (e.g. `K0_KERNEL_QOS__FANOUT_MAX=5`). Values are YAML-parsed when possible, with comma-delimited fallbacks for simple lists.
3. **Programmatic/CLI overrides** — explicit dictionaries passed to the loader (e.g. CLI flag parsing) take final precedence.

The loader validates retention/QoS bounds via Pydantic models and records the resolved YAML path in `settings.config_file`. This keeps operators free to promote the same code into different topologies by altering environment variables or CLI flags without mutating the checked-in YAML baseline.

---

## 16) Security Notes

* **Device keys & MLS groups** are managed by security services; K0 validates signatures on ingress and on receipts, records key version, and enforces revocation directives with immediate gate rejects.
* **Sanitized infra/privacy topics** are exposed to SSE with ACLs; **intelligence.advisory** is read‑only to P04.
* **Rotation resilience**: overlapping key windows allow clients to switch keys without downtime; Observability emits `key_rotation_events` metrics whenever the active key set changes.

---

## 17) Test Matrix (minimum to ship)

* Gate rejects malformed/missing/sig‑bad; WAL remains clean.
* Idempotency dedup under concurrency and crash.
* UoW atomicity across ACID cohort.
* Outbox idempotence (retries) and DLQ fencing; include indexer handshake success/failure coverage.
* Replay parity with WAL; offsets restoration; SSE catch‑up under churn. Cold replay tests must drive the Outbox to convergence and assert `replay_parity_failures == 0`.
* QoS hard budgets under contention; fairness validated with real concurrent tasks (no sleeps). Introduce forced WAL fsync failures and scheduler stress hooks to verify crash recovery.
* SSE ACL denies prohibited topics; admin mirrors work. Add backpressure scenarios that throttle and shed slow subscribers without simulation sleeps.
* Correctness suite covering invariants in `contracts/CORRECTNESS.md`: WAL/receipt monotonicity, offsets ordering, snapshot watermark guards, schema deny matrix.
* Snapshot watermark protocol tests ensure `SNAPSHOT_BEGIN/COMMIT` pairs are present before reopening ports.
* Security revocation race tests verify PEP denies stale keys before commit, even under cache TTL expiry.
* Space binding tests ensure `{tenant_id, space_id, device_id}` triples cannot be spoofed and SSE cursors remain isolated by space.

---

## 18) Deployment Modes

* **Edge device**: single process with local SQLite/FTS; lightweight async workers; E2EE sync lives in user‑space P12.
* **Hub/server**: per‑tenant K0; drivers may point to external engines; keep Outbox/Indexer close to engines.

---

## 19) Operations Runbook (abridged)

* **Replay from cold**: `k0ctl replay --from 0` → verify `replay_parity_failures == 0`.
* **Schema upgrade**: register N+1, run `k0ctl schema activate`, observe green roll‑out, deprecate N after 7 days, and record the audit ID.
* **Backpressure**: if SSE lag > threshold, use `k0ctl scheduler tighten --profile backpressure` to adjust weights, throttle offending subscribers, and notify them with advisory SSE events.
* **Cursor hygiene**: weekly `k0ctl sse cleanup --older-than 14d` prunes inactive cursors; outliers trigger targeted replay instructions to clients.
* **DLQ**: drain with `k0ctl dlq requeue --filter…`; errors beyond N escalate. DLQ reports include fingerprint + last error for investigation.
* **Snapshot & restore**: nightly `k0ctl snapshot create` captures WAL watermark + offsets. Restore with `k0ctl snapshot restore --id <snapshot>` followed by `k0ctl replay --from watermark+1`.
* **Selective replay**: when only a single space needs recovery, run `k0ctl replay --space <space_id> --from watermark+1`; the command uses `idx_wal_space_pos` to stream relevant events and emits `merge.applied` topics for downstream CRDT reconciliation.
* **Migrations**: run `k0ctl migrate apply` during maintenance windows; migrations pause command port writes, take a snapshot, run DDL, replay WAL, and reopen ports once Ward migration suite passes.
* **Config reload**: use `k0ctl config reload --version <tag>` to atomically apply `alias_map.yaml`, `qos/defaults.yaml`, and `config/kernel.yaml`. The kernel emits a `config.changed` event carrying the applied version and blocks reload if new configs fail schema validation or invariants defined in `contracts/CORRECTNESS.md`.
* **Provisioning**: `k0ctl provision --tenant <tenant_id> --space <space_id> --device <device_id> --mls-group <mls_group_id> --key-version <key_version> [--ts <iso8601>]` writes a signed config row to `st_devices` (see SPI docs) so devices cannot spoof tenancy/space boundaries. Provisioning is idempotent and emits a `provisioned` event containing the MLS group binding and key material fingerprint.

---

## 20) Roadmap & Delivery Plan (12 weeks, 3 milestones)

**M1 (Weeks 1–4): Commit Path & Receipts**

* Ports (Command/Obs), PEP@syscall, Minimal Gate, Idempotency, UoW (SQLite WAL), Receipts/Offsets.
* Tests: gate, idem, uow, receipts.

**M2 (Weeks 5–8): SSE & Replay & QoS**

* SSE server (ACL, cursors, ack), global scheduler (W‑DRR), cold replayer, DLQ.
* Tests: sse_acl, qos, replay, dlq; load testing to SLO.

**M3 (Weeks 9–12): Async Cohort & Hardening**

* Outbox/indexers (vector/KG/blob) via SPI; OpenAPI/AsyncAPI/JSON Schemas finalized; CLI; runbooks.
* Security/observability hardening; property‑based crash/recovery tests.

> Cognitive blocks (attention/hippocampus/workspace) stay **out of K0**, consuming kernel topics, consistent with your merged architecture.

---

## 21) Deep Design Notes — Toward Desktop-Class Kernel

### Scheduler contract

- **Weights & bands:** Assign base weights per policy band (GREEN > AMBER > RED) and apply small per-port modifiers (e.g., +10 % for command writes during high load) to keep a single global fairness model. Persist weights in `qos/defaults.yaml` so PEP can tighten or relax budgets dynamically.
- **Placement:** Centralize the W-DRR scheduler in `qos/scheduler.py` as a shared service. Ports enqueue work with metadata (band, port, payload size); the scheduler yields permission tokens back to the port handlers. That keeps admission control consistent and simplifies instrumentation.
- **Testing:** Build stress fixtures that enqueue mixed-band workloads and assert bounded latency, starvation avoidance, and total fairness (e.g., no queue waits beyond 2× the expected share).

### Schema registry lifecycle

- **Workflow:** Only K0 operators (or automated CI with signed release bundles) call `k0ctl schema register`. New schemas arrive in `REGISTERED` state, move to `ACTIVE` once validation passes, and old versions shift to `DEPRECATED`.
- **Blocking & rollback:** If a schema is marked `BLOCKED`, Minimal Gate rejects any payload referencing it with `REJECTED_KERNEL_GATE`. For rollback, provide `k0ctl schema block --reason=...` and `k0ctl schema reactivate`.
- **Auditing:** Store `registered_by`, `approved_by`, timestamps, and SHA256 of schema artifacts. Emit audit logs via Observability port and replicate to an append-only table for forensic review.
- **Enforcement:** Minimal Gate consults the registry for `(schema_uri, version)` and ensures payload hash matches registered SHA. PEP denies submissions pointing to DEPRECATED+1 before ACTIVE N+1 is ready.

### Outbox fingerprinting & retries

- **Payload contracts:** Standardize per-driver payload schemas under `contracts/outbox/<driver>.schema.json`. For example, vector ops include `{doc_id, embedding_sha, vector}`.
- **Fingerprints:** Use `blake3` of driver name + op kind + deterministic payload fields (sorted keys) to ensure retries are idempotent.
- **Retries:** Implement exponential backoff capped at N attempts (e.g., 5). After N failures, move the item to DLQ with last error snapshot.
- **Indexer handshake:** Require indexers to ack success by deleting the Outbox entry (via optimistic transaction) and optionally publish a metric. If indexers run out-of-process, expose a gRPC/HTTP endpoint returning success/failure so the kernel can retire entries deterministically.

### Replay convergence

- **Cold replay:** Replayer reads WAL in commit order, validates envelopes via schema registry, reconstitutes receipts/offsets, and re-populates the Outbox.
- **Async cohort sync:** After WAL replay, the replayer replays pending Outbox entries through the same apply pipeline. Indexers emit success metrics; replayer ensures fingerprints match expectations.
- **Consistency checks:** After replay, run parity checks (e.g., count of embeddings vs WAL topics) and emit `replay_parity_failures` metrics. Provide a dry-run mode to compare without applying.
- **Snapshots:** Optionally generate periodic WAL snapshots plus Outbox state so cold start can fast-forward before replaying the delta.

### SSE backpressure policy

- **Lag thresholds:** Track `lag_ms` and `pending_events` per subscriber. If thresholds exceed configured limits, move the subscriber to a throttled rate class or pause topics.
- **Shedding behavior:** For chronic offenders, drop the connection with an explicit `429` SSE event and require explicit `ack` with a catch-up cursor. Expose admin hooks to manually resume.
- **Cursor retention:** Keep cursor records for 7–14 days; after expiration, require full catch-up replay. Emit warnings through Observability when approaching expiry.
- **Integration with scheduler:** When SSE backlog grows, scheduler tightens read budgets globally (e.g., reduce max fanout or boost command weight) until backlog clears.

### Device key & MLS integration

- **Key registry:** Maintain device keys and status (active, revoked, pending) in a secure table tied to PEP. PEP includes current key version in obligations.
- **Rotation:** During rotation, accept both old and new keys for a configurable grace window; receipts include key version to trace auditing. If a key is revoked mid-flight, Minimal Gate rejects future submissions and SSE emits an advisory event.
- **MLS groups:** Kernel doesn’t manage MLS groups but should honor PEP obligations: if PEP signals “re-encrypt for group X,” kernel updates receipts/outbox entries with required metadata so downstream services can act.
- **Failure handling:** On signature failure, return `PEP_DENY` or `REJECTED_KERNEL_GATE` depending on whether policy or cryptographic verification failed; always log to security telemetry.

### Testing strategy without artificial sleeps

- **Crash injection:** Add hooks to simulate WAL fsync errors or forced process restarts by manipulating SQLite pragmas or OS-level file handles (temporary rename/lock). Combine with Ward fixtures that run commit sequences and validate recovery.
- **Concurrency stress:** Use actual concurrent tasks with bounded work items; rely on real scheduler behavior and instrumentation to confirm fairness. For deterministic assertions, use barriers/latches rather than sleeps.
- **Fault harness:** Create a harness that orchestrates commit, crash, replay, and SSE resubscribe sequences automatically to ensure zero data loss and consistent receipts.
- **Security tests:** Use real libsodium primitives with ephemeral keys, verifying signature failure cases and rotation scenarios.

### Designing a kernel to rival Windows and macOS

- **Modular microkernel base:** Keep the K0 philosophy—minimal trusted core with driver aliases. Extend aliasing to hardware drivers, file systems, and networking stacks to let OEMs plug in custom components without touching the kernel core.
- **Robust hardware abstraction:** Develop a HAL that wraps device classes (storage, network, graphics). Provide rich driver SDKs and validation harnesses to attract hardware vendors; emphasize sandboxed drivers to improve stability versus monolithic kernels.
- **Security-first architecture:** Enforce mandatory access control, capability-based permissions, and memory isolation comparable to modern hypervisors. Support remote attestation, secure boot, and hardware-backed key storage by default.
- **Scheduling excellence:** Offer multi-class scheduling (latency-sensitive UI threads, background services, batch jobs) with deterministic QoS. Integrate power-aware scheduling and CPU topology awareness (big.LITTLE, SMT).
- **File systems & storage:** Ship with transactional, journaled file systems supporting snapshots, deduplication, and transparent encryption. Provide user-space file system interfaces (like FUSE) but keep durability contracts in kernel space.
- **Compatibility & virtualization:** Introduce a robust ABI/API layer for applications plus compatibility shims (containers, VM integration) to run legacy workloads. Consider integrated hypervisor capabilities for isolation and cross-OS app support.
- **Developer ergonomics:** Publish stable kernel APIs, comprehensive tooling (debuggers, tracing, crash dump analyzers), and strong documentation. CI for driver certification and automated regression testing is essential to match commercial OS quality.
- **UX & ecosystem:** Although kernel-centric, collaborate closely with UX and app platform teams to ensure fast startup, responsive UI scheduling, consistent power management, and tight integration with services (update system, app store).
- **Observability & telemetry:** Bake in fine-grained metrics, tracing, and crash diagnostics akin to enterprise systems. Provide user consent controls and privacy guarantees from day one.

### Scheduler wiring — enterprise-grade pick

- **Decision:** Shared, lock-free, multi-queue scheduler akin to Windows’ dispatcher: per-band queues implemented as M/WFQ priority heaps pinned per core, with a global coordinator for cross-core load balancing. Permission tokens are lightweight structs containing CPU affinity, time slice, and QoS budget; ports call `scheduler.acquire(band, port, metadata)` and receive a token bound to a CPU core.
- **Why:** Prevents convoying on multi-core machines, keeps NUMA locality, and supports high-frequency timers without starving control-plane tasks. Lets us introduce CPU group-aware balancing and real-time lanes later.
- **Follow-through:** Implement scheduler in Rust for lock-free structures with an FFI shim to Python (short-term) and expose tracing counters for context switches, queue depth per core, and starvation detectors.

### `k0ctl` command surface — hardened ops model

- **Decision:** Authenticated management console mirroring macOS `launchctl`/Windows `sc.exe` model. Use mTLS mutual auth tied to operator smartcards; commands require role-based authorization enforced by K0’s PEP (`OPERATOR_ADMIN`, `SECURITY_ADMIN`, `SRE_OPERATOR`). Support both CLI and gRPC API for automation.
- **Key commands:**
  - `schema register/activate/deprecate/block` (with signed bundle input)
  - `scheduler set-profile --profile=<fastlane|balanced|drain>`
  - `sse cleanup --older-than <duration>`
  - `replay start --from <offset>`
  - `keys rotate --device <id> --new-key <pem>`
- **Why:** Matches enterprise operations and gives auditability, while keeping kernel trusted boundary small.

### Indexer handshake transport — hardened asynchronous driver model

- **Decision:** Out-of-process indexers communicate via mutually authenticated gRPC (HTTP/2) channels with signed JWT tokens issued by the kernel. Kernel writes Outbox entries, notifies indexers via edge-triggered `eventfd` (or Windows IOCP equivalent), and awaits a gRPC `ApplyResult` to delete the entry. If the indexer is co-located, we can optionally use shared-memory ring buffers for performance, but gRPC remains the canonical handshake for audit trails.
- **Why:** Allows multiple indexer implementations, supports remote drivers (vector GPU farms), and provides deterministic state (apply either succeeds and row is deleted or failure is recorded with fingerprint).

### SSE backpressure thresholds — desktop-grade streaming strategy

- **Decision:** Model after Windows’ multimedia scheduler/macOS app nap policies: tiered thresholds per subscriber.
  - **Warning:** lag > 2 s or pending events > 5 000 → send advisory event (`type=lag-warning`, include catch-up cursor, recommended actions).
  - **Throttle:** lag > 5 s or pending > 20 000 → reduce delivery rate by 50 % and move subscriber to background queue.
  - **Shed:** lag > 15 s or pending > 50 000 → disconnect with `429` event, require `sse.ack` with last cursor before resubscribe.
- **Why:** Keeps the kernel responsive, protects hot topics, and mirrors OS-level resource management.

### Key registry integration — enterprise security stance

- **Decision:** Central hardware-backed key vault (e.g., Windows DPAPI/Apple Secure Enclave equivalent). K0 maintains an L1 cache of allowed keys with TTL ≈ 5 minutes, refreshed via signed push notifications from the key service. Revocation uses CRL-style deltas; rotations require dual-signature approval (security + ops) captured in audit logs. Grace window configurable per band (e.g., GREEN 30 min, RED immediate).
- **Why:** Ensures compromised devices are cut off quickly, supports compliance (FIPS/CC), and integrates with hardware roots of trust.

### Observability thresholds — production alert posture

- **Decision:** Define concrete SLO-backed alerting profiles:
  - `scheduler_tightening_events > 3/hr` → page SRE (indicates sustained overload).
  - `sse_lag_ms p95 > 2 000` for 5 min → high-priority alert.
  - `key_rotation_events` with revocations > 0 → security on-call.
  - `replay_parity_failures > 0` → immediate incident, auto-escalate.
- **Why:** Mimics the rigor of commercial OS telemetry; ensures new metrics feed actionable alerts.

### Crash-injection & stress hooks — OS reliability discipline

- **Decision:** Provide test-only kernel build flags (toggled via signed config) that expose:
  - WAL fault injectors (simulate fsync failure, disk-full) triggered through `k0ctl fault wal --mode=<fsync_fail|disk_full>`; disabled in production builds.
  - Scheduler stress harness (`k0ctl scheduler flood`) that spawns synthetic workloads to validate fairness.
  - SSE lag simulator to test backpressure responses.
  - Crash dump integration (write minidumps equivalent) to analyze failure paths; run automatically after each injected crash.
- **Why:** Essential for shipping OS-class reliability—mirrors Windows’ Driver Verifier / macOS sanitisers.

---

## 22) Performance & Correctness Harnesses

* **Golden workloads (`perf/profiles/`)**: ship three canonical mixes — `small` (1–2 KB, 70 % write / 20 % query / 10 % SSE), `balanced` (8–16 KB, 40 % write / 40 % query / 20 % SSE), and `large` (256 KB artifact fan-out) — with Ward-driven runners invoked via `make perf-small`, `perf-balanced`, and `perf-replay`.
* **SLO enforcement**: CI gates validate `submit→receipt P95 ≤ 150 ms`, `replay throughput ≥ 12 k events/s`, and `sse lag p95 < 2 s` on reference hardware. Grafana dashboard JSON and Prometheus alerts (`perf/dashboards/`) codify thresholds; failure blocks release until dashboards return to green. For local previews use the runbook in `docs/development/runbooks/k0-slo-dashboard.md`.
* **Correctness spec linkage**: `contracts/CORRECTNESS.md` enumerates invariants and deny matrix. Any README change touching Sections 5, 6, 8, 9, or 19 must update that spec and the suites under `tests/correctness/`, `tests/snapshots/`, or `tests/security/`.
* **Driver conformance**: `drivers/conformance/` fuzzes `prepare/apply/fingerprint` determinism, crash-restart idempotence, and `replay_range` accuracy for each alias. New drivers MUST pass this harness before alias activation in `alias_map.yaml`.
* **Hot reload audit**: every successful `k0ctl config reload` emits a `config.changed` event with the config version, SHA256, and Ward report ID. Failure emits `config.reload_failed` with invariant details from the correctness checks.
* **Space-aware sync**: per-space replay harness exercises `idx_wal_space_pos` to validate selective restore, emits `merge.applied` events, and verifies SSE cursors (`subscriber_id`, `topic`, `space_id`) stay isolated under load.

These harnesses are part of the release checklist: no build ships without green perf runs, updated dashboards, and passing correctness suites.

---

# Appendix A — Example Idempotency Key

`idem_key = blake3( tenant_id | space_id | actor | topic | schema_uri | schema_version | payload_sha256 )`

Key derivation must be **stable** and **collision‑resistant**; clients may also submit an explicit key for cross‑process retries.

---

# Appendix B — Example Indexer Contract

```json
{
  "driver": "st_vector",
  "op_kind": "upsert",
  "payload": {
    "doc_id": "…",
    "embedding_sha": "…",
    "vector": "…"
  },
  "fingerprint": "blake3(doc_id|embedding_sha)"
}
```

`apply()` must be idempotent: the same fingerprint MUST NOT change the target state.

---

# Appendix C — Threat Model (abridged)

* **Tampering**: reject altered payloads via hash + signature.
* **Replay**: idempotency ledger blocks duplicates; receipts are signed.
* **Denial**: scheduler, admission control, and size caps at gate.
* **Privilege**: SSE ACLs, policy guards for `intelligence.*`/`policy.*`.

---

# Appendix D — Example Config Snippets

`qos/defaults.yaml`:

```yaml
reads:
  max_fanout: 3
  top_k: 8
  per_store_slice_ms: 75
writes:
  max_concurrency: 8
sse:
  heartbeat_ms: 8000
```

`drivers/alias_map.yaml`:

```yaml
aliases:
  st_epi: sqlite
  st_sem: sqlite
  st_ws:  sqlite
  st_fts: fts5
  st_vector: faiss
  st_emb: faiss
  st_kg_dom: sqlite_kg
  st_blob: localfs
```

`config/kernel.yaml`:

```yaml
server:
  host: "0.0.0.0"
  port: 8080
  log_level: info
  timeout_graceful_shutdown: 30
retention:
  default:
    wal_days: 7
    wal_max_events: 10000000
  topics:
    "ui.*":
      wal_days: 2
      wal_max_events: 1000000
    "policy.*":
      wal_days: 30
      wal_max_events: 20000000
    "infra.sanitized.*":
      wal_days: 14
  spaces:
    "shared:household":
      wal_days: 30
    "personal:*":
      wal_days: 14

gate_caps:
  max_envelope_bytes: 64000
  max_body_bytes: 4194304
  sig_verify_timeout_ms: 5

signature_budget:
  per_tenant_per_sec: 500
  burst: 1000

outbox:
  retry_schedule:
    base_ms: 250
    factor: 2.0
    jitter_ratio: 0.2
    max_attempts: 5

hot_reload:
  config_version: "2025.09.27"
  allow_files:
    - config/kernel.yaml
    - qos/defaults.yaml
    - drivers/alias_map.yaml

provisioning:
  default_space_prefix: "personal"
  enforce_space_declaration: true
```

---

# Appendix E — Example OpenAPI Usage

**Submit:**

```http
POST /k0/command.submit
Content-Type: application/json

{
  "tenant_id": "household:abc123",
  "space_id": "personal:user:prince",
  "device_id": "device:pixel8:XYZ",
  "topic": "memory.formation",
  "schema_uri": "mem://m1",
  "schema_version": "1.0.0",
  "actor": "user:prince",
  "band": "GREEN",
  "policy_version": "v1",
  "ts": "2025-09-27T00:00:00Z",
  "sig": "<ed25519>",
  "idem_key": "<blake3>",
  "body": { /* domain payload */ }
}
```

**Response:**

```json
{ "receipt_id":"…", "offsets":{"memory.formation":12345}, "commit_ts":"…" }
```

---

# Appendix F — What lives **outside** K0 (for clarity)

* **Pipelines P01–P20**, retrieval heuristics, attention/hippocampus/workspace, affect systems, global workspace, family intelligence/advisory, device E2EE sync: **all user‑space**, consuming kernel topics via bus/SSE and calling Query Port with **soft hints** only.

---

# Appendix G — Error Codes

| Code | HTTP Status | Description |
| ---- | ----------- | ----------- |
| `REJECTED_KERNEL_GATE` | 400 | Minimal Gate rejection (schema/catalog status, payload hash mismatch, size caps, canonicalization, space/device/MLS violations). |
| `PEP_DENY` | 403 | Policy enforcement failure (band/caps/ABAC) or key revocation. |
| `IDEMPOTENT_DUPLICATE` | 409 | Existing commit for the supplied idem key; receipt replayed. |
| `QOS_BUDGET_EXCEEDED` | 429 | Hard QoS budget depleted (Query/SSE/Command deferrals). |

Codes appear in the `error.code` field of the normative error envelope (§5.8) and are stable across releases.

---

## FAQ

**Q:** Can user‑space validate domain schemas before K0?
**A:** Yes — and it should. K0 still enforces the **Minimal Gate** to keep WAL pristine.

**Q:** Can we swap FAISS for another ANN?
**A:** Yes; change the alias binding and ship a driver implementing SPI/idempotency.

**Q:** Does K0 ever call user‑space synchronously on commit?
**A:** No. Commit completes before user‑space handlers; effects flow via WAL→Bus/SSE and Outbox.

---

## How this README ties to your diagrams

* **K0 Hybrid Microkernel, Ports, Drivers, Alias Map, QoS, Replay, SSE**: matches the central kernel block and driver aliases in your merged architecture.
* **Storage primitives, events spine, outbox, receipts, offsets, DLQ, ACL topics (infra/privacy/intelligence)**: matches the infrastructure and bus diagrams and SSE exposure.
* **Cognitive/hippocampus/attention/workspace staying out of kernel, serving Memory Backbone**: matches the cognitive detail diagrams and boundaries.
* **Family Intelligence as advisory; P04 as sole executor**: matches the intelligence boundary and advisory‑only constraint.

---
