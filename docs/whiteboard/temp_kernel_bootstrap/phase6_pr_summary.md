# Phase 6 — Bus Production Hardening

Branch: `bus-hardening` → `POC_Migration`

This PR delivers the entire Phase 6 hardening described in
[09_wiring_plan.md](../09_wiring_plan.md) §Phase 6.  All 15 issues
(`P6.0`–`P6.14`) landed across three commits on `bus-hardening`.

## Tier-by-tier summary

### Tier 2 (P6.1–P6.4) — fail-safe fixes
- **P6.1** Async handler errors now surface via `Future.add_done_callback`
  in `k1/bus/async_bridge.py`.
- **P6.2** `RustBusAdapter.publish()` runs the configured `MiddlewareChain`
  and `TimingChain` (previously bypassed).
- **P6.3** `RustBusAdapter.drain()` now clears the captured queue,
  matching `LocalBus.drain()` semantics.
- **P6.4** `k1/bus/impl/__init__.py` re-exports the missing public symbols.

### Tier 3 (P6.5) — async dispatch
- New per-subscription bounded `LocalMailbox` + daemon worker, opt-in
  via `BusFactory.create_local(async_dispatch=True)`.
- New `IBus.flush(timeout_ms)` Protocol method; `LocalBus.flush()` blocks
  until every async subscription has drained and no worker is mid-handler.
- `BusStats` extended with `mailbox_full_drops`, `mailbox_high_water_mark`,
  `async_handler_retries`, `async_handler_dlq`.

### Tier 4 (P6.6 + P6.7) — retry + DLQ
- `retry_resolver: (topic) -> RetryPolicy | None` consulted by the async
  worker on handler exceptions.  Exponential / fixed backoff with jitter,
  capped at 10s.
- `dlq_callback(envelope, exc, attempts)` invoked after retry exhaustion.

### Tier 5 (P6.8 + P6.9) — topic renames
- `turn.complete.v1` → `k1.session.turn.complete.v1` (producer + contract).
- `SessionBusAdapter` flattens `sessionstate.*` events to
  `k1.sessionstate.*` (was double-nested `k1.session.sessionstate.*`).

### Tier 6 (P6.10–P6.13) — opt-in extensions
- **P6.10** k1.model_hub STRICT timing rule (already in `bus.yaml`,
  verified by audit).
- **P6.11** `TopicRegistry.register(topic, validator=...)` stores an
  optional payload validator.  `TopicValidationMiddleware` runs it in
  one of two modes: `"permissive"` (warn + count) or `"strict"`
  (drop + count).  No new mandatory dependencies.
- **P6.12** New `IdempotencyMiddleware` (LRU+TTL, stdlib only) that
  drops duplicate `(topic, request_id)` envelopes.  Opt-in via
  middleware list.
- **P6.13** New `BusOutbox` (SQLite WAL) for durable topics.
  `LocalBus(outbox=..., durable_topics={...})` persists envelopes
  before dispatch; `subscribe(..., consumer_id=...)` enables
  at-least-once delivery and `bus.replay_durable_topics()` redelivers
  un-acked envelopes after a process restart.

### Tier 7 (P6.14) — verification
- New `tests/k1/bus/test_phase6_e2e.py` (7 tests) exercises async
  retry/DLQ, topic renames, schema validation, idempotency, and
  durability replay end-to-end.

## Test results

| Suite                                  | Pass | New |
|----------------------------------------|------|-----|
| `tests/k1/bus`                         | 1108 | +39 |
| `tests/k1/memory_writer`               | 773  |   – |
| `tests/k1/sessionstate` (excl. flakes) | green |   – |
| `tests/k1/concierge`   (excl. flakes)  | green |   – |
| `tests/k1/model_hub`   (alone)         | 1052 |   – |

The remaining failures in the consumer sweep (`test_factory.py`
event-loop, orchestrator perf SLOs, `test_no_deep_imports_in_production`,
`test_runner_cli`) are pre-existing on `POC_Migration` and reproduce
without this branch's changes.

## API impact

- **Additive only.**  `IBus.flush()` is a new Protocol method; legacy
  bus implementations keep working under duck typing.
- `BusFactory.create_local()` gains keyword-only params: `async_dispatch`,
  `subscription_mailbox_capacity`, `retry_resolver`, `dlq_callback`,
  `outbox`, `durable_topics`.
- `LocalBus.subscribe(..., consumer_id=...)` gained an optional kwarg.
- `TopicRegistry.register(topic, validator=...)` gained an optional kwarg.
- No existing call site needs modification.

## Migration notes

- Subscribers of `turn.complete.v1` must update to
  `k1.session.turn.complete.v1` (single point of contact: the
  contract YAML and `TurnDispatcher.TOPIC` constant).
- Subscribers of `k1.session.sessionstate.*` must update wildcards to
  `k1.sessionstate.*` (`SessionBusAdapter` no longer prefixes that
  family with `k1.session.`).

## Commits

| SHA       | Scope                                  |
|-----------|----------------------------------------|
| `44006c8` | P6.1–P6.4 (Tier 2)                     |
| `47c7f10` | P6.5–P6.9 (async, retry/DLQ, renames)  |
| (this PR) | P6.11–P6.14 (schema, idempotency, durability, E2E) |
