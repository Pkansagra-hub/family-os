# K0 Kernel Contracts

The files in this directory are the canonical machine-readable contracts for the K0 kernel. They mirror the normative specification captured in `k0/README.md` and are the single source of truth for partner integrations, automated validation, and code generation.

## Layout

| Path | Purpose |
| ---- | ------- |
| `openapi.k0.yaml` | HTTP port contract (command/query/SSE ack/observability) referencing shared JSON Schemas. |
| `asyncapi.events.yaml` | Topic catalogue describing publish semantics for kernel event streams. |
| `jsonschema/*.json` | Individual JSON Schema documents shared across OpenAPI/AsyncAPI, including envelopes, errors, receipts, cursors, and policy responses. |
| `sql/` | Canonical SQLite DDL (`storage.sql`) and baseline migration artifacts under `sql/migrations/`. |
| `../CORRECTNESS.md` | Contractual invariants validated by Ward suites. |

## Canonical Schemas

* **Envelope** (`jsonschema/envelope.schema.json`) — Required fields for command submissions, including tenancy/device identifiers and canonical topic patterns.
* **Receipt** (`jsonschema/receipt.schema.json`) — Durable receipt payload signed over the canonical field order.
* **Error** (`jsonschema/error.schema.json`) — Stable error envelope with enumerated reasons.
* **Query Recall** (`jsonschema/query.recall.*.json`) — Request/response structures for the recall port, including `space_id` scoping and budget telemetry.
* **SSE Offsets** (`jsonschema/offset.cursor.schema.json`, `jsonschema/sse.ack.request.json`) — Cursor materialization and acknowledgement payloads scoped per `{subscriber_id, topic, space_id, tenant_id}`.
* **PEP Contract** (`jsonschema/pep.schema.json`) — Input context and policy outputs (decision, obligations) used during syscall preflight.
* **Snapshot Events** (`jsonschema/infra.snapshot.event.json`) — Payload emitted on `infra.snapshot.*` topics when snapshots begin/commit.

## Canonical Signing Order

Receipts **must** be signed over the canonical JSON array:

```
[receipt_id, idem_key, wal_pos, commit_ts, payload_sha256, mls_group_id, key_version, obligations]
```

The same ordering is enforced wherever the receipt schema is referenced. Clients computing or verifying signatures must serialize using UTF-8, sorted keys, and no insignificant whitespace.

## Storage Contract & Schema Evolution

The storage contract is captured in `sql/storage.sql` and mirrored by the baseline migration `sql/migrations/0001_baseline.sql`. Both files reproduce the WAL, receipts, offsets, outbox, DLQ, schema registry, and provisioning tables documented in `k0/README.md` §6.1.

When evolving the storage schema:

1. Update `sql/storage.sql` with the desired DDL changes.
2. Create a new migration under `sql/migrations/` (e.g., `0002_add_foo.sql`) that applies the same diff.
3. Regenerate or adjust manifests/migration modules via the automation flow in `.github/instructions/migration-automation.instructions.md`.
4. Update `k0/README.md` (and any dependent docs) to reflect the new tables/indexes.
5. Extend Ward storage suites to validate the new invariants and ensure replay/snapshot coverage remains intact.

> **Note:** `sql/storage.sql` is the canonical snapshot for fresh deployments; migrations provide deterministic upgrades for existing nodes. Treat both as authoritative and keep them in lock-step.

## Versioning & Change Control

* All schemas follow semantic versioning via the surrounding API surface (`openapi.k0.yaml`, `asyncapi.events.yaml`).
* The `VERSION` file tracks canonical checksums for all contract artifacts, enforcing release stability and preventing unauthorized drift.
* Changes to shared JSON Schemas require simultaneous updates to `k0/README.md` **and** Ward contract suites **and** VERSION checksums.
* Each schema exports a stable `$id` so downstream tooling can resolve references even when files move.

**Contract Update Workflow:**
1. Modify contract artifacts (schemas, OpenAPI, AsyncAPI, SQL)
2. Run `python -m k0.automation.compute_contract_checksums --update`
3. Update approvals in VERSION file if breaking changes
4. Regenerate API documentation
5. Validate all automation passes
6. Commit contract changes + VERSION update together

See `docs/development/contracts-playbook.md` §7-9 for complete versioning workflow and approval process.

## Validation Workflow

1. OpenAPI/AsyncAPI documents reference these JSON Schemas via `$ref` to ensure a single source of truth.
2. Ward suites load each schema to validate sample payloads and to exercise the contract invariants.
3. CI will lint schemas (`jsonschema`/`ajv`) and compare README snippets to the canonical artifacts (planned in Milestone 3).

## Extending the Contracts

When introducing a new field or schema:

1. Update the appropriate JSON Schema in `jsonschema/` (or add a new one).
2. Reference it from `openapi.k0.yaml` and/or `asyncapi.events.yaml` as needed.
3. Amend narrative documentation in `k0/README.md` and add/extend Ward tests.
4. If storage tables change, follow the evolution workflow above (update `sql/`, produce migrations, refresh README) and run the migration automation per `.github/instructions/migration-automation.instructions.md`.

By keeping these artifacts in sync, we maintain contract-first development while allowing tooling to generate clients, validate payloads, and enforce invariants automatically.
