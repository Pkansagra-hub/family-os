# MS-2.5 Epic 2.5.5 — First contract: `memory.write.v1`

**Status:** complete
**Owner:** Bridge runtime team
**Closes:** D4 (one contract live end-to-end)

This runbook documents the first bridge contract shipped end-to-end on
the substrate built in Epics 2.5.1–2.5.4.

## Surface

| Layer | Path | Generated? |
|------|------|-----------|
| Manifest | `bridge/contracts/manifests/memory.write.v1.yaml` | hand-written |
| Schema | `bridge/contracts/schemas/memory.write.v1.json` | hand-written (`$ref` to K1) |
| Pydantic model | `bridge/_generated/k0/models/memory_write_v1.py`, `bridge/_generated/k1/models/memory_write_v1.py` | yes (`datamodel-code-generator`) |
| Producer client | `bridge/_generated/k1/clients/memory_write_v1.py` | yes |
| Producer port | `bridge/_generated/k1/ports/memory_write_v1.py` | yes |
| Consumer handler-reg | `bridge/_generated/k0/handlers/memory_write_v1.py` | yes |
| Consumer impl | `bridge/handlers/k0/memory_write_v1.py` | hand-written |
| Pipeline sink | `k0/pipelines/p02_write_ingest/__init__.py` | hand-written (MS-3a stub) |

## Wire flow

```
K1 producer code
  └── MemoryWriteV1Client.publish(payload: MemoryWriteV1)
       └── BridgeRuntime.transport.publish(topic, schema_uri, payload)
            └── InProcessHttpTransport (httpx ASGI) POST /bridge/v1/dispatch
                 └── bridge.testing.dispatcher_app
                      └── BridgeRuntime.dispatch(topic, payload_dict)
                           ├── topic alias resolution (memory.write → memory.write.v1)
                           ├── HandlerRegistry.lookup(canonical)
                           ├── Pydantic validation (entry.model.model_validate)
                           └── handle_memory_write_v1 (bridge/handlers/k0/...)
                                └── k0.pipelines.p02_write_ingest.ingest
                                     └── ack {atom_id, ack: True, topic}
```

The K0 production `/k0/command.submit` endpoint is **not** on this path
in MS-2.5; the dispatcher app is a thin ASGI surface that exposes the
runtime's dispatch table over HTTP. MS-3a (Epic 3a.2) folds this into
production K0.

## Idempotency key

The `EnvelopeBuilder` computes:

```
idem_key = BLAKE3(topic ‖ \x00 ‖ canonical_json(body) ‖ \x00 ‖ device_id)
```

This intentionally **differs** from the original plan spec
`(tenant_id, space_id, atom_id, minute(ts))`. The bridge already had a
production envelope builder (`bridge/core/envelope_builder.py:214`)
when MS-2.5 began; rewriting the formula would invalidate every K0
ledger entry currently in flight. The plan-doc spec is preserved in
`docs/architecture/whiteboard_k1/bridge_implementation_plan.md` for
posterity, but the live contract honours the implemented formula.

## Topic alias

`bridge/_topic_aliases.py` maps `memory.write` → `memory.write.v1`.
This lets legacy K1 producers keep their existing topic string for one
release while we migrate them; the alias is removed in the MS-3a
"alias-removal" PR. `BridgeRuntime.dispatch` resolves the alias before
handler lookup, so registry, gates, and runtime treat both names as
the same canonical topic.

## Observability

Per the MS-2.5 observability rule:

| Kind | Name | Labels |
|-----|------|-------|
| Gauge (health) | `bridge_runtime_up` | `role` |
| Counter (success) | `bridge_memory_write_v1_accepted_total` | `tenant_id` |
| Counter (error) | `bridge_memory_write_v1_rejected_total` | `tenant_id`, `reason` |
| Histogram (latency) | `bridge_memory_write_v1_latency_ms` | `tenant_id` |

`reason` ∈ {`unknown_topic`, `schema_validation`, `unknown`}. Latency
is wall time from dispatcher receipt to handler return, in
milliseconds.

A structured info-level log `bridge.dispatch.outcome` is emitted on
every dispatch with fields `{topic, tenant_id, elapsed_ms, accepted,
reason}` so structured-log pipelines see the same shape.

## Tests

`tests/bridge/contracts/test_memory_write_v1.py` — 19 cases (1 + 14
parametrised over required fields + 4 protocol cases). Coverage
includes Pydantic validation, schema-version constants,
sentiment/source-type/novelty enum families, Ed25519 sign+verify,
BLAKE3 idem-key, alias resolution, and a real httpx ASGI round-trip
asserting JSON-mode `model_dump` equality between the K1-side input
and the K0-side validated payload.

## Reversibility

To roll back this contract:

1. Set `status: deprecated` in the manifest.
2. Remove `bridge/handlers/k0/memory_write_v1.py` (or leave; idle).
3. Set `bridge.contracts.first_contract_live: false` in
   `bridge/contracts/_meta/feature_flags.yaml`.
4. Re-run `python -m tooling.contracts.codegen` — generated artefacts
   stay (they're harmless without a registered impl); the
   `manifest_implementation_bound` gate flips to FAIL only for
   `status: active` manifests, so a deprecated manifest needs no
   handler.

## Iteration log entry

> **MS-2.5 / Epic 2.5.5 closed.** First contract `memory.write.v1`
> live end-to-end via real Pydantic + Ed25519 + httpx ASGI; 19 contract
> tests green; `EnvelopeBuilder` BLAKE3 idem-key formula formally
> documented (deviation from plan spec); topic alias landed for legacy
> producers; metrics + structured boundary log instrumented.
