# Bridge adapter pattern (MS-4)

## Audience

K1 contributors authoring or modifying any file under
`k1/**/adapters/bridge_*.py`, `k1/**/adapters/*_bridge*.py`,
`k1/**/adapters/null_bridge*.py`, or
`k1/**/adapters/model_gateway_bridge.py`.

## Purpose

The bridge wall (R8 in the bridge architecture plan) forbids K1 modules
from importing bridge internals. The legitimate seam is the
**generated, manifest-bound client** under `bridge._generated.k1.*`
returned by the `BridgeRuntime`. K1 adapters are the glue between that
generated client and the K1 module's own port.

## What an adapter is

An adapter is a thin domain-translation layer that:

1. Owns no transport, signing, envelope-building, or retry logic
   (those live behind the wall in `bridge.core.*`).
2. Translates a domain-shaped Pydantic model into the generated wire
   model and calls the runtime-bound client.
3. Maps wire-level errors into domain-meaningful exceptions.

It MAY:

* Hold privacy/policy guards (E3 black-band egress, etc.) that the
  generated client cannot enforce because they are domain-defined.
* Implement batching, health, and circuit-breaker logic specific to
  the consuming module's lifecycle.
* Convert between K1's domain types and the wire types.

It MUST NOT:

* `import bridge.core.*`, `bridge.kernel.*`, `bridge.sync.*`,
  `bridge.connector.*`, `bridge.codecs.*`, or `bridge.adapters.*`.
  These imports are caught by the
  `bridge_not_imported_from_kernels` CI gate.
* Construct a `BridgeRuntime` or transport directly. That is the
  `bridge_client_construction_via_runtime_only` gate's job.
* Re-implement signing, envelope construction, or the wire-format
  codec. Those live in `bridge.core.signing`,
  `bridge.core.envelope_builder`, and `bridge.core.codecs`.

## SLOC budget (MS-4)

The `tooling/ci/gates/adapter_loc_budget.py` gate enforces:

| Constant | Current value | Rationale |
|----------|--------------|-----------|
| `PER_FILE_SLOC_CAP` | 250 | Just above the largest current adapter (`k1/fabric/adapters/bridge_connection.py`, 227 SLOC). |
| `TOTAL_SLOC_BUDGET` | 1150 | ~6% above the MS-4 audit total (1089 SLOC across 12 production adapter files). |

SLOC is counted by `_count_sloc()` in the gate module: non-blank,
non-comment lines, with module + class docstrings stripped (function
docstrings are kept because they are typically one-liners and are
hard to abuse). Test files (`test_*.py` / `*_test.py`) are excluded.

### When may these constants change?

* **Lowering** (always allowed): if a refactor genuinely reduces
  total SLOC, lower `TOTAL_SLOC_BUDGET` to the new total. This
  prevents a future regression from hiding under the previous
  ceiling.
* **Raising**: requires a one-line justification appended to the
  table above, naming the adapter, the SLOC delta, and the reason
  (new domain feature, new privacy guard, etc.). PRs that bump the
  budget without updating this table must be rejected.

## The 12 adapters (MS-4 baseline audit)

These are the production adapter files protected by the gate. The
SLOC numbers were measured by the gate on 2026-05-XX.

| File | SLOC | Role |
|------|-----:|------|
| `k1/concierge/adapters/null_bridge_write.py` | 21 | Offline no-op write adapter for concierge degraded mode. |
| `k1/fabric/adapters/bridge_connection.py` | 227 | IFL routing, health probes, retries; consumed by `KernelService` lines 1208/1637. |
| `k1/fabric/adapters/model_gateway_bridge.py` | 145 | `model_hub` ↔ `fabric.model_gateway` type translation; consumed by `KernelService` lines 1205/1634. |
| `k1/kernel/adapters/bridge_adapter.py` | 29 | `OfflineBridgeAdapter` + `SinkBridgeAdapter`; consumed by `KernelService` lines 1183/1187. |
| `k1/memory_writer/adapters/bridge_command_adapter.py` | 46 | `IBridgeCommandPort` ↔ `IKernelCommandPort` Protocol shim; constructed at `KernelService` line 1750. |
| `k1/orchestrator/adapters/bridge_client_shim.py` | 33 | Orchestrator-side bridge-client adapter; consumed by `KernelService` line 1260. |
| `k1/orchestrator/adapters/bridge_write_adapter.py` | 135 | Write-path orchestration error semantics. |
| `k1/orchestrator/adapters/mock_bridge_adapter.py` | 82 | In-memory mock for tests + zero-config factory. |
| `k1/planner/adapters/bridge_adapter.py` | 113 | Planner-specific recall response shaping. |
| `k1/selfmodel/adapters/bridge_amendment_sync.py` | 213 | E3-guarded constitution amendment sync (privacy-band guards + SSE inbound). |
| `k1/sessionstate/adapters/bridge_storage.py` | 29 | Stub awaiting MS-2+ contracts. |
| `k1/sessionstate/adapters/bridge_sync.py` | 16 | Stub awaiting MS-2+ contracts. |

The MS-4 audit confirmed **zero forbidden bridge-internal imports**
across all 12 files. The cleanup was completed in MS-3a/3b. This
gate prevents regression.

## Authoring checklist for new adapters

When adding a new adapter file:

1. Place it under `k1/<module>/adapters/` and name it
   `bridge_<role>.py` (or similar; see `_FILE_PATTERNS` in the gate).
2. Import only:
   * Your own module's port + Protocol types.
   * The generated client class from `bridge._generated.k1.clients.<topic>`.
   * Standard library and Pydantic for typing.
3. Receive the runtime-bound client via constructor injection. Do
   NOT construct it.
4. Run `python -m tooling.ci.gates.adapter_loc_budget` locally.
5. Update the table above if you bump either constant.
