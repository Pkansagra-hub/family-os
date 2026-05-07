# MS-2.5 Epic 2.5.6 — Exit criterion + gate flips

**Status:** complete
**Owner:** Bridge runtime team
**Closes:** D1–D7 (substrate operational + first contract live)

This runbook documents the closing PR of MS-2.5: stub manifests for the
broader contract surface, R10 enforcement on the K1 local bus, all six
CI gates flipped to enforcing, the two transitional feature flags
deleted, and a single exit-criterion test that asserts every D-fact in
one place.

## D1–D7 mapping

| ID | Assertion | File |
|----|-----------|------|
| D1 | Registry validates `memory.write.v1` | `tests/bridge/contracts/test_ms_2_5_exit_criterion.py::test_d1_*` |
| D2 | `codegen --check` zero drift | same module, `test_d2_*` |
| D3 | Generated K1 client + K0 handler import cleanly with metadata | `test_d3_*` |
| D4 | Round-trip via `InProcessHttpTransport` Pydantic-equal | `test_d4_*` |
| D5 | `no_cross_kernel_imports` exits 0 | `test_d5_*` |
| D6 | `bus_yaml_aligned_with_registry` exits 0 | `test_d6_*` |
| D7 | R10: bridge-bound `bus.publish` raises `UnknownContractError` | `test_d7_*` |

All seven run in `<10 s` wall on the round-trip path.

## Stub manifests added

* `bridge/contracts/manifests/k1.k0.sse.v1.yaml` — `status: proposed`.
  Registers the cross-kernel topic prefix referenced by
  `k1/config/bus.yaml` so the `bus_yaml_aligned_with_registry` gate
  is GREEN at exit-criterion. Concrete schema lands in MS-3a once the
  K0 SSE endpoint is finalised.

* `bridge/contracts/schemas/_stub.json` — placeholder body schema for
  `status: proposed` manifests. Replace before flipping `status:
  active`.

Additional family stubs (`feedback.*`, `recall.*`, `curiosity.*`,
`p03.*`, `p07.*`, `family.*`, `ifl.*`) listed in the original plan are
deferred to MS-3a where each will land alongside its concrete schema +
producer wiring; a `proposed` manifest with no consumer wiring is
strictly *registry awareness* and is added on-demand per family rather
than batch-stubbed here.

## R10 enforcement

`bridge/bus_guard.py` exposes:

* `UnknownContractError` — raised when a bridge-bound topic is
  published on the local bus.
* `load_bridge_topics(contracts_root=None) -> frozenset[str]` —
  resolves all cross-kernel topics from the registry.
* `BridgeAwareLocalBus(inner: LocalBus, *, ...)` — proxy that delegates
  every `IBus` method to the inner production `LocalBus` *except*
  `publish`, which validates the topic against the bridge-bound set
  before delegating.

This proxy approach was chosen over modifying `LocalBus` directly so
the existing 1100+ K1 bus regression tests stay untouched. K1 boot
code wraps its production `LocalBus` instance in a
`BridgeAwareLocalBus` to opt in to enforcement; tests can opt out by
holding the inner bus directly.

## Gate flips

`tooling/ci/run_all_gates.py::_GATES` — all six gates now ship with
`fail` mode:

| Gate | MS-2.5 PR#1 | MS-2.5 exit-criterion |
|------|------------|----------------------|
| `no_cross_kernel_imports` | fail | fail |
| `bridge_not_imported_from_kernels` | warn | **fail** |
| `manifest_implementation_bound` | warn | **fail** |
| `schema_checksum_stable` | fail | fail |
| `bus_yaml_aligned_with_registry` | warn | **fail** |
| `single_ibridge_port_definition` | warn | **fail** |

CLI `--warn-only`/`--fail-on-violation` overrides remain available for
emergency manifest landings.

## Feature flags removed

`bridge/contracts/_meta/feature_flags.yaml`:

* `ms_2_5.codegen_enforced` — deleted; the `codegen_no_diff` workflow
  enforces drift unconditionally.
* `ms_2_5.exit_criterion_active` — deleted; the round-trip test runs
  on every push.

A `ms_2_5.closed: true` marker is left so future readers see the
milestone has shipped, and a `ms_3a` namespace is reserved for the
next milestone's reversibility flags.

## Iteration log entry

> **MS-2.5 closed.** D1–D6 verified by
> `tests/bridge/contracts/test_ms_2_5_exit_criterion.py` (7/7 green,
> 4.5 s wall). Substrate operational: registry + meta-schema + manifest
> loader + jinja codegen + 6 enforcing CI gates + runtime skeleton +
> handler dispatch + in-process HTTP transport + Ed25519 signing +
> BLAKE3 idem-key. First contract `memory.write.v1` live end-to-end (19
> contract tests). R10 enforced via `BridgeAwareLocalBus`. Two
> transitional feature flags removed.
>
> **Open carry-overs to MS-3a.** Concrete K0 SSE manifest +
> additional family stubs (`feedback.*`, `recall.*`, `curiosity.*`,
> `p03.*`, `p07.*`, `family.*`, `ifl.*`) land per-family alongside
> concrete schemas. K0 production `/k0/command.submit` absorbs the
> bridge dispatcher endpoint (currently `bridge.testing.dispatcher_app`).
> `MemoryWriter` in K1 migrates from direct K0 calls to the generated
> `MemoryWriteV1Client`. `memory.write` topic alias removed once all
> producers are migrated.
