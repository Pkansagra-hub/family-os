# Bridge Implementation Plan — Skeleton

**Companion to:** [bridge_system_design.md](bridge_system_design.md) · [bridge_architecture_v2.mmd](../../../architecture_diagrams/bridge/bridge_architecture_v2.mmd)
**Status:** SKELETON ONLY — enumerates structure; each milestone/epic/issue to be filled in subsequent passes.
**Purpose:** Sequential, gated implementation plan. Each milestone unlocks the next. Wiring is built end-to-end and grows; nothing is left dangling. Final milestones are dedicated to integration + live-system + adversarial-path testing.

---

## Global rules (apply to every milestone, every epic, every issue)

1. **No-mock policy.** Production code paths are tested against real implementations. Mocks/stubs allowed **only** at:
   - The OS / network boundary (real HTTP loopback, real SQLite tmp file, real filesystem) — never a fake transport in production tests.
   - External 3rd-party services that don't have a local equivalent (only in MS-5+ IFL adapter tests).
   - Time (`freezegun`-style) and randomness (`seed=...`) — explicitly declared per test.
   - Anywhere else, a mock is a code smell that fails review.
2. **Unit tests per epic.** Every epic ships with its own test file(s) under `tests/bridge/<area>/`. Coverage gate: ≥85% line / ≥75% branch on the epic's modules. Unit tests run in <30s for the epic.
3. **Wiring closes forward.** Every epic ends with a wiring-section that connects its new code to the already-wired surface from prior epics. No orphaned modules. The MS-2.5 exit-criterion test (one contract round-tripping K1→K0 through generated code) keeps passing through every subsequent milestone — it is the canary.
4. **Each milestone has an exit-criterion test.** A single named pytest test that, when green, certifies the milestone is shipped. Listed per-milestone below as the final epic.
5. **Adversarial paths in MS-7 / MS-8.** Happy-path coverage lives in each epic's unit tests; failure-mode, partial-failure, byzantine-input, and recovery paths land in MS-7/MS-8 against the booted live system.
6. **Reversibility.** Every epic ships behind a feature flag in `bridge/contracts/_meta/feature_flags.yaml` until its milestone's exit-criterion is green. Flag removal is the final issue of each milestone.
7. **Observability per epic.** Every epic emits at minimum: one health gauge, one error counter, one latency histogram, structured logs at the boundary. Listed in each epic's wiring section.
8. **Documentation per epic.** Every epic updates [bridge_system_design.md](bridge_system_design.md) with what changed and adds an entry to the iteration log. No PR merges without doc delta.
9. **CI gates accumulate.** Each milestone enables its CI gates in `--fail-on-violation` mode at the milestone's exit. They never get disabled.
10. **No skipping milestones.** MS-2.5 → MS-3a → … → MS-8 is sequential. MS-3 sub-milestones (a–e) can parallelize *within* MS-3 only if their epics declare no shared wiring.

---

## Milestone summary (the spine)

| MS | Name | Unlocks | Exit criterion (one test) |
| -- | ---- | ------- | ------------------------- |
| **MS-2.5** | Contract registry + codegen substrate + CI gates | All contract-driven work | `test_one_contract_round_trips_through_generated_code` |
| **MS-3a** | Online command path (real HTTP) | Real K1→K0 writes | `test_memory_write_v1_lands_in_k0_via_real_http` |
| **MS-3b** | Outbox + DEGRADED for commands | Offline tolerance for writes | `test_outbox_drains_on_online_transition_within_50ms_p99` |
| **MS-3c** | Query port (recall) | Real K1→K0 reads | `test_recall_request_returns_real_k0_hits` |
| **MS-3d** | SSE port (chunked streaming + cursor resume) | Real K0→K1 events | `test_curiosity_intent_v1_streams_e2e_under_200ms_p99` |
| **MS-3e** | Obs / feedback port | Closing the feedback loop | `test_feedback_signal_p02_v1_round_trips_to_k0` |
| **MS-4** | Codecs (msgpack/CBOR) + adapter consolidation | Wire-format flexibility, LOC budget | `test_adapter_loc_under_budget_and_codec_negotiation_works` |
| **MS-5** | IFL minimum (ConnectorGateway + MCP Process Manager + Google Calendar read-only adapter) | External device reach via MCP | `test_ifl_google_calendar_events_list_round_trips_via_gateway` |
| **MS-6** | LAN device sync (mDNS + LWW CRDT, intra-person L3) — **post-v1, deferred** | Multi-device-per-person coherence | `test_two_k1_devices_same_wifi_share_session_state_no_k0` |
| **MS-7** | Integration testing — booted live system (multi-tenant K0 + multiple K1s) | Whole-system trust | `test_full_system_boot_and_e2e_user_journey` |
| **MS-8** | Adversarial / failure-mode / chaos testing | Production confidence | `test_chaos_suite_no_data_loss_no_corruption_no_split_brain` |

---

## MS-2.5 — Contract registry + codegen substrate + CI gates

**Unlocks:** every later milestone — without the registry, no contract-driven code exists. After MS-2.5 lands, *every* future K0↔K1 contract must enter via `bridge/contracts/manifests/<topic>.yaml` or it fails to boot.

**Pre-conditions:** none. Codebase facts pinned by 2026-05-05 walk:

- Existing crypto in [bridge/core/signing.py](bridge/core/signing.py) (Ed25519 + HMAC, pynacl, base64url no-padding).
- Existing envelope builder in [bridge/core/envelope_builder.py](bridge/core/envelope_builder.py) (18 fields, canonical JSON, sorted keys).
- Existing K0 contract tooling in [k0/automation/compute_contract_checksums.py](k0/automation/compute_contract_checksums.py) and [k0/automation/contract_compatibility_checker.py](k0/automation/contract_compatibility_checker.py).
- Existing schema chain: [k0/contracts/jsonschema/topics/memory_write.body.json](k0/contracts/jsonschema/topics/memory_write.body.json) `$ref`s [k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json](k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json) (MemoryAtom v2.2, 14 required fields).
- Three live `class IBridgePort` definitions: [k1/kernel/ports/bridge_port.py](k1/kernel/ports/bridge_port.py), [k1/fabric/ports/bridge_port.py](k1/fabric/ports/bridge_port.py), [k1/planner/ports/bridge_port.py](k1/planner/ports/bridge_port.py).
- Two known wall violations: [k1/memory_writer/adapters/bridge_command_adapter.py](k1/memory_writer/adapters/bridge_command_adapter.py) imports `bridge.core.envelope_builder`; [k1/kernel/adapters/bridge_adapter.py](k1/kernel/adapters/bridge_adapter.py) imports `bridge.sync.local_outbox`.
- Production topic today is `"memory.write"` (no `.v1` suffix); MS-2.5 introduces `"memory.write.v1"` with a temporary alias.
- No CI infra exists today — no `.github/workflows/`, no `.pre-commit-config.yaml`, no ruff/mypy/import-linter config.

**Wiring at exit:** `bridge/contracts/` registry populated with one active manifest, `tooling/contracts/` toolchain operational, `tooling/ci/gates/` enforced, `bridge/_generated/{k0,k1}/` vendored, `BridgeRuntime.from_registry()` constructs ports from manifests, `memory.write.v1` round-trips K1→K0 over real httpx loopback into real SQLite WAL.

**PR sequencing within MS-2.5** (matches D6 plan):

| PR | Scope | Gates flipped |
| -- | ----- | ------------- |
| PR#1 | Three `IBridgePort` renames + import-site updates + 12 test renames | `single_ibridge_port_definition` → `--warn-only` then `--fail-on-violation` at end of PR |
| PR#2 | Manifest substrate (meta-schema, `_meta/` dir, codegen scripts, CI gate scripts as `--warn-only`) | none flipped (orchestrator runs all gates as WARN) |
| PR#3 | First contract migrated (`memory.write.v1`) + generated code vendored + exit-criterion test | All MS-2.5 gates flipped to `--fail-on-violation` |

### Epic 2.5.1 — Repo scaffolding + meta-schema (D1, D3 partial)

**Goal:** produce the static substrate files that everything else depends on. No runtime code yet.

**Files to create:**

- `bridge/contracts/manifests/.gitkeep`
- `bridge/contracts/schemas/.gitkeep`
- `bridge/contracts/_meta/manifest.schema.json` — full JSON Schema 2020-12 doc per D1, with `additionalProperties: false`, `topic` regex `^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+\.v[0-9]+$`, `direction` enum `[k0_to_k1, k1_to_k0, k0_to_k0, k1_to_k1, device_to_k0, k0_to_device]`, `delivery.transport` enum `[http, sse, in_process, e2ee_lan, https]`, `delivery.endpoint_class` enum `[cloud_k0, home_k0, peer_k1, device_local]`, `delivery.partition_mode` enum `[k0_primary, k1_mesh_fallback, k1_mesh_only]`, `semantics.description` `minLength: 40` (R6 mitigation), `allOf` blocks for: (1) `sync` required when direction in `{k0_to_k0, k1_to_k1}`, (2) `tool_class` required when `sync.layer == l2_family_tool_state`, (3) `signing` required for `device_*` directions.
- `bridge/contracts/_meta/ca_bundle.schema.json` — JSON Schema for the bundle file (D3 validator).
- `bridge/contracts/_meta/ca_bundle.json` — placeholder bundle: one entry `{ca_id: "familyos_root_v1", ed25519_public_key: "PLACEHOLDER_REPLACE_BEFORE_MS5", status: "active", valid_until: "2099-01-01T00:00:00Z"}`. Real key replaces placeholder via D3 ceremony pre-MS-5.
- `bridge/contracts/_meta/feature_flags.yaml` — initial flags: `ms_2_5.codegen_enforced: false`, `ms_2_5.exit_criterion_active: false`. Used by `BridgeRuntime` to gate behavior until milestones close.
- `bridge/contracts/_meta/README.md` — explains the file set; points reviewers at D1/D3.

**Unit tests:** `tests/bridge/contracts/test_meta_schema.py`

- `test_meta_schema_is_valid_jsonschema_2020_12` — load with `jsonschema.Draft202012Validator(check_schema=True)`.
- `test_meta_schema_rejects_unknown_top_level_field` — fixture manifest with `extra_field: 1` fails.
- `test_meta_schema_topic_regex_enforced` — `"MemoryWrite.v1"` (capital), `"memory.write"` (no `.v`), `"memory..v1"` all fail; `"memory.write.v1"` passes.
- `test_meta_schema_semantics_description_min_length_40` — 39 chars fails (R6); 40 chars passes.
- `test_meta_schema_allof_sync_required_for_k0_to_k0` — direction `k0_to_k0` without `sync:` block fails.
- `test_meta_schema_allof_tool_class_required_when_l2` — `sync.layer: l2_family_tool_state` without `sync.tool_class` fails.
- `test_meta_schema_allof_signing_required_for_device_directions` — `direction: device_to_k0` without `signing:` block fails.
- `test_ca_bundle_schema_validates_placeholder` — placeholder bundle passes its own schema.

**No-mock compliance:** uses real `jsonschema` library; no mocks.

**Wiring at end of epic:** static files only; no runtime imports anything yet.

**Observability:** N/A (pre-runtime).

**Documentation update:** add "MS-2.5 Epic 2.5.1 shipped" entry to [bridge_system_design.md](bridge_system_design.md) iteration log.

### Epic 2.5.2 — Codegen toolchain (`tooling/contracts/`) (D2)

**Goal:** turn manifests into typed Python: payload models, port protocols, client stubs, handler-registry wiring.

**Files to create:**

- `tooling/__init__.py`
- `tooling/contracts/__init__.py`
- `tooling/contracts/manifest_loader.py` — `load_manifests(root: Path) -> list[Manifest]` parses every `*.yaml` under `manifests/`; validates each against `_meta/manifest.schema.json`; returns typed `Manifest` dataclass; raises `ManifestValidationError` with file path + JSON-pointer on failure.
- `tooling/contracts/checksums.py` — lifted from [k0/automation/compute_contract_checksums.py](k0/automation/compute_contract_checksums.py); same logic, new home. Computes `sha256` of every `manifests/*.yaml` and `schemas/*.json`; writes back to `manifest.checksums.{schema_sha256, manifest_sha256}`. CLI: `python -m tooling.contracts.checksums [--update]`.
- `tooling/contracts/compatibility.py` — lifted from [k0/automation/contract_compatibility_checker.py](k0/automation/contract_compatibility_checker.py); SemVer + breaking-change classifier (BREAKING / COMPATIBLE / PATCH per ADR-0013).
- `tooling/contracts/templates/port_protocol.py.jinja` — emits one `Protocol` class per `(consumer_role, topic)` pair with one method per topic; methods typed against generated payload models.
- `tooling/contracts/templates/client_stub.py.jinja` — emits thin `publish/request` dispatch into hand-written `bridge/core/transport/`.
- `tooling/contracts/templates/handler_registry.py.jinja` — emits `register_handlers(runtime, *, impl)` with compile-time check that every Protocol method is implemented.
- `tooling/contracts/templates/package_index.py.jinja` — emits `bridge/_generated/{k0,k1}/__init__.py` re-exports.
- `tooling/contracts/codegen.py` — orchestrator: loads manifests, runs `datamodel-codegen` per payload schema, runs Jinja2 templates, writes to `bridge/_generated/{role}/`. CLI: `python -m tooling.contracts.codegen [--check]`. `--check` writes to tmp dir and `diff`s against vendored output; non-zero exit on drift.
- `tooling/contracts/_artifact_header.py` — produces `# AUTOGENERATED — DO NOT EDIT — regenerate with: python -m tooling.contracts.codegen\n# manifest_bundle_sha: <sha>\n# source manifest: <path>\n` header injected at top of every generated file.
- `requirements.txt` additions: `datamodel-code-generator==0.25.*`, `jinja2==3.1.*`, `jsonschema==4.21.*` (pin minor versions for deterministic output).

**`datamodel-code-generator` invocation flags** (committed in `tooling/contracts/codegen.py` as a constant; `--disable-timestamp` is critical to keep no-diff CI gate from false-positiving):

```bash
datamodel-codegen \
  --input <schema.json> --input-file-type jsonschema \
  --output <out.py> \
  --target-python-version 3.13 \
  --output-model-type pydantic_v2.BaseModel \
  --use-schema-description --use-field-description \
  --use-default --strict-nullable --disable-timestamp
```

**Unit tests:** `tests/tooling/contracts/test_codegen.py`

- `test_load_manifests_validates_each_against_meta_schema` — fixture set with one bad manifest; loader raises `ManifestValidationError`.
- `test_codegen_emits_autogenerated_header` — every output file starts with the canonical header.
- `test_codegen_is_deterministic` — run codegen twice into separate tmp dirs; assert identical `sha256` per file.
- `test_codegen_check_mode_detects_drift` — modify a vendored file by 1 byte; `codegen.py --check` exits non-zero with the offending path printed.
- `test_codegen_handles_payload_$ref_chains` — fixture schema `$ref`s another schema; generated Pydantic model resolves the reference.
- `test_codegen_emits_disjoint_k0_k1_trees` — assert no K0 file imports a K1 generated symbol and vice versa (the wall holds inside `_generated/`).
- `test_checksums_round_trip` — compute → write → reload → assert equality.
- `test_compatibility_classifies_breaking_change` — fixture v1 vs v2 schemas with required-field-removal → classified BREAKING.

**No-mock compliance:** real `datamodel-codegen` subprocess; real Jinja2; real tmp dirs; real `jsonschema`.

**Wiring at end of epic:** `tooling/contracts/codegen.py` reads `bridge/contracts/manifests/`; writes `bridge/_generated/{k0,k1}/` (currently empty since no manifest exists yet — Epic 2.5.5 creates the first one).

**Observability:** codegen prints structured summary to stderr: `{"manifests_processed": N, "files_emitted": M, "drift_files": [...], "manifest_bundle_sha": "..."}`.

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log entry "Epic 2.5.2 shipped: codegen toolchain operational".

### Epic 2.5.3 — IBridgePort renames (D6 PR#1) + `BridgeRuntime` skeleton

**Goal:** kill the three `IBridgePort` collisions; stand up `BridgeRuntime.from_registry()` to be the only legitimate entry point.

**D6 PR#1 — pure rename mapping (atomic, single commit per file pair to keep `git mv` history clean):**

| Current location | Current behavior | New name | Test files renamed |
| ---------------- | ---------------- | -------- | ------------------ |
| [k1/kernel/ports/bridge_port.py](k1/kernel/ports/bridge_port.py) | Lifecycle wrapper (`connect/disconnect/is_connected/get_client`) | `IBridgeRuntime` | `tests/k1/kernel/ports/test_bridge_port.py` and 3 dependents |
| [k1/fabric/ports/bridge_port.py](k1/fabric/ports/bridge_port.py) | Fabric K0 access (`send_command/query/route_ifl/is_available/get_health`) | `IFabricK0Port` | `tests/k1/fabric/ports/test_bridge_port.py` and 5 dependents |
| [k1/planner/ports/bridge_port.py](k1/planner/ports/bridge_port.py) | Planner recall + persist (`recall/persist_plan`) | `IPlannerWritePort` | `tests/k1/planner/ports/test_bridge_port.py` and 4 dependents |

**Import sites to update** (verified via 2026-05-05 walk):

- `k1/kernel/ports/__init__.py`, `k1/kernel/service.py`, `k1/kernel/adapters/bridge_adapter.py`
- `k1/fabric/ports/__init__.py`, `k1/fabric/providers/bridge_provider.py` (4 sites), `k1/fabric/adapters/bridge_connection.py`, `k1/planner/adapters/bridge_adapter.py`
- `k1/planner/ports/__init__.py`, `k1/planner/__init__.py:72`, `k1/planner/factory.py`, `k1/planner/stages/commit_service.py`, `k1/planner/services/tool_call_router.py`

**Files to create (post-rename):**

- `bridge/runtime.py` — `class BridgeRuntime` (frozen dataclass) with `command/query/sse/obs/gateway` slots typed against generated `Protocol`s. `@classmethod from_registry(cls, *, contracts_path: Path, role: Role, transport: Transport | None = None) -> BridgeRuntime` — parses every manifest, instantiates ports from generated modules, verifies impl-binding, returns the wired runtime. `start()` opens transport, starts health checker, starts outbox drain (when MS-3b lands). `stop()` reverses.
- `bridge/runtime_errors.py` — `class UnboundContractError(RuntimeError)`, `class ManifestValidationError(ValueError)`, `class OfflineError(RuntimeError)`.
- `bridge/core/transport/__init__.py` — exports `get_transport(runtime, *, transport: str)`.
- `bridge/core/transport/in_process_http.py` — `class InProcessHttpTransport` wraps `httpx.AsyncClient(transport=httpx.ASGITransport(app=k0_app))`. Real httpx, real ASGI roundtrip, no mocks. Used by every test that does K1→K0 in the same process.
- `bridge/core/transport/http.py` — production `class HttpTransport` over real `httpx.AsyncClient` against a real URL.
- `bridge/_generated/__init__.py`, `bridge/_generated/k0/__init__.py`, `bridge/_generated/k1/__init__.py` (initially empty re-export shims; populated by codegen).

**Unit tests:** `tests/bridge/runtime/test_from_registry.py`

- `test_from_registry_parses_all_manifests` — fixture dir with 3 manifests; assert all 3 loaded, types correct.
- `test_from_registry_role_k1_registers_publish_for_k1_to_k0` — direction `k1_to_k0` produces a publish-side port on K1 role.
- `test_from_registry_role_k0_registers_consume_for_k1_to_k0` — same manifest, K0 role, registers consume-side.
- `test_from_registry_raises_unbound_contract_when_handler_missing` — manifest active but no generated handler → `UnboundContractError` with topic name in message.
- `test_from_registry_validates_manifest_against_meta_schema_at_boot` — invalid manifest in fixture dir → boot fails loudly before any I/O.
- `test_in_process_http_transport_round_trips` — tiny FastAPI app + `InProcessHttpTransport`; assert real httpx round-trip.

**Plus rename tests:** `tests/bridge/runtime/test_ibridge_port_rename_complete.py` — `grep -rE "^class IBridgePort\b" k0 k1` returns zero hits (this is the test that the gate later enforces).

**No-mock compliance:** real httpx via `ASGITransport`; real FastAPI; real Pydantic.

**Wiring at end of epic:** `BridgeRuntime` exists and can boot against a fixture manifest dir even though no production manifest is in `bridge/contracts/manifests/` yet. The three renamed K1 ports compile and tests pass.

**Observability:** `BridgeRuntime` exposes:

- `bridge.runtime.contracts_loaded{role}` (gauge) — count of active manifests at boot
- `bridge.runtime.manifest_bundle_sha` (info metric)
- `bridge.runtime.boot_time_ms` (histogram)
- structured log on every `from_registry` call: `{"event": "runtime_boot", "role": "...", "contracts": [...], "bundle_sha": "..."}`

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log entry "Epic 2.5.3 shipped: D6 PR#1 complete (renames atomic), BridgeRuntime skeleton operational".

### Epic 2.5.4 — CI gates (D5 + D6) — six gates + orchestrator + workflows

**Goal:** every wall, every drift, every cross-kernel reach is automatically detected at PR time. Day-one expected results table from D5 honored.

**Files to create:**

- `tooling/ci/__init__.py`
- `tooling/ci/gates/__init__.py`
- `tooling/ci/gates/no_cross_kernel_imports.py` — `ast.parse` every `*.py` under `k0/` and `k1/`; visit `Import` and `ImportFrom`; fail if `k0/**` imports `k1.*` or vice versa. Allowlist via `# noqa: cross-kernel — reason` annotation. **Day one:** GREEN (verified zero hits).
- `tooling/ci/gates/bridge_not_imported_from_kernels.py` — `ast.parse` `k0/**/*.py` + `k1/**/*.py`; fail on imports of `bridge.core.*`, `bridge.kernel.*`, `bridge.sync.*`, `bridge.connector.*`. Allowed: `bridge.client`, `bridge.contracts`, `bridge.testing`, `bridge._generated.<own_role>.*`, `bridge.ports`. **Day-one allowlist file** `tooling/ci/known_violations/bridge_imports.txt`:

  ```text
  k1/memory_writer/adapters/bridge_command_adapter.py:25  # MS-3a remediation
  k1/kernel/adapters/bridge_adapter.py:59                 # MS-3b remediation
  ```

- `tooling/ci/gates/manifest_implementation_bound.py` — boots `BridgeRuntime.from_registry(contracts_path='bridge/contracts/')` for each role; for every contract with `status: active`, asserts a generated handler/client exists. Skipped with WARN (not FAIL) when `bridge/_generated/` is empty (so PR#1 doesn't break before PR#3).
- `tooling/ci/gates/schema_checksum_stable.py` — calls `tooling.contracts.checksums:recompute()`; fails if any `manifest.checksums.{schema_sha256, manifest_sha256}` disagrees with the file. Auto-fix: `--update` flag.
- `tooling/ci/gates/bus_yaml_aligned_with_registry.py` — parse [k1/config/bus.yaml](k1/config/bus.yaml); for every `timing_rules` prefix matching cross-kernel pattern (`k0.*`, `memory.*`, `feedback.*`, `recall.*`, `curiosity.*`, `p0[1-9].*`, `family.*`, `ifl.*`), assert ≥1 registry manifest exists with topic starting with that prefix. **Day one:** will fail loudly until each prefix gets at least a `status: proposed` manifest. That failure surfaces every cross-kernel topic currently leaking past the wall (by design).
- `tooling/ci/gates/single_ibridge_port_definition.py` — `grep -rE "^class IBridgePort\b" k0 k1`; fail on any hit (under `bridge/ports/` is *also* disallowed — those are renamed too). Day one in PR#1: `--warn-only`. End of PR#1: `--fail-on-violation`.
- `tooling/ci/run_all_gates.py` — orchestrator (full content from D5 sketch); subprocesses each gate; collects exit codes; prints `::error::N gate(s) failed` summary; exits 1 on any failure.
- `.github/workflows/bridge_ci.yml` — triggers on PR + push; runs `python -m tooling.ci.run_all_gates`.
- `.github/workflows/codegen_no_diff.yml` — runs `python -m tooling.contracts.codegen --check` then `git diff --exit-code bridge/_generated/`.

**Unit tests:** `tests/tooling/ci/gates/test_each_gate.py`

For each gate, two tests minimum:

- `test_<gate>_passes_on_clean_fixture` — `tests/tooling/ci/fixtures/clean/` exits 0.
- `test_<gate>_fails_on_violating_fixture_with_path_in_stderr` — `tests/tooling/ci/fixtures/violating/<gate>/` exits 1 and offending file/line appears in `capsys.readouterr().err`.

Plus orchestrator:

- `test_run_all_gates_aggregates_failures` — fixture with 2 failing gates; orchestrator exits 1 and lists both names.
- `test_run_all_gates_exits_zero_when_all_green` — clean fixture set; exits 0.

**No-mock compliance:** real subprocess invocations; real `ast.parse`; real fixture files on disk.

**Wiring at end of epic:** GitHub Actions workflows exist; running `python -m tooling.ci.run_all_gates` locally mirrors CI exactly. Day-one state per D5 table:

| Gate | Day-one (PR#1 close) | After PR#3 (MS-2.5 close) |
| ---- | -------------------- | -------------------------- |
| `no_cross_kernel_imports` | GREEN | GREEN |
| `bridge_not_imported_from_kernels` | GREEN (2 violations allowlisted) | GREEN (allowlist still active; cleared in MS-3a/3b) |
| `manifest_implementation_bound` | WARN (empty `_generated/`) | GREEN (memory.write.v1 bound) |
| `schema_checksum_stable` | GREEN | GREEN |
| `bus_yaml_aligned_with_registry` | RED (fail-loud, intentional) | GREEN (every cross-kernel prefix has ≥1 `status: proposed` stub manifest) |
| `single_ibridge_port_definition` | GREEN (post-rename, `--fail-on-violation`) | GREEN |

**Observability:** every gate prints its name + duration + outcome to stderr; orchestrator emits a JSON summary line for CI log scraping.

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log entry; commit `docs/runbooks/bridge_ci_gates.md` describing each gate's purpose, the offending-file format, and how to add a new gate.

### Epic 2.5.5 — First contract migrated: `memory.write.v1` (D4)

**Goal:** prove the substrate end-to-end with the one production contract that already exists. Cut over from un-suffixed `"memory.write"` topic to versioned `"memory.write.v1"` with a 2-PR transition (add alias, remove alias).

**Files to create:**

- `bridge/contracts/manifests/memory.write.v1.yaml` — full manifest:

  ```yaml
  topic: memory.write.v1
  direction: k1_to_k0
  owner_team: k0
  status: active
  producer:
    kernel: k1
    pipeline: memory_writer.batch
    emitter: BatchEmitter
  consumer:
    kernel: k0
    pipeline: P02_write_ingest
    state: command_submit_endpoint
  schema: schemas/memory.write.v1.json
  delivery:
    transport: http
    ordering: best_effort
    ack_required: true
    online_required: false
    endpoint_class: cloud_k0
    partition_mode: k0_primary
    max_queue_age: 24h
    drain_rate_per_sec: null
    codec: json
    retry: exponential_backoff
    max_redelivery: 10
  semantics:
    idempotent: true
    duplicate_strategy: dedupe_by_envelope_id
    retention: 7d
    description: >
      MemoryAtom v2.2 write to K0 P02 ingest. Body is a MemoryAtom record with
      14 required fields (see memory_atom.v2.schema.json). Idem key = BLAKE3
      of (tenant_id, space_id, atom_id, ts_truncated_to_minute). Replays within
      24h are idempotent no-ops. Timezone: UTC. Units: ms epoch.
  sla:
    latency_p99_ms: 500
    availability: degrades_to_local_outbox
  versioning:
    strategy: additive_only_within_v1
    breaking_change_requires: new_topic_v2_with_dual_publish_window_30d
  checksums: {}   # filled by tooling/contracts/checksums.py in CI
  ```

- `bridge/contracts/schemas/memory.write.v1.json` — thin wrapper that `$ref`s existing [k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json](k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json). Keeps source of truth single.
- Run codegen → vendor:
  - `bridge/_generated/k1/models/memory_write_v1.py` — Pydantic v2 `MemoryWriteV1` model (auto-generated, AUTOGENERATED header, manifest-bundle SHA).
  - `bridge/_generated/k1/ports/command_v1.py` — `IKernelCommandPort` Protocol with `submit_memory_write_v1(payload: MemoryWriteV1) -> None`.
  - `bridge/_generated/k1/clients/memory_write_v1.py` — `MemoryWriteV1Client` with `__transport__ = "http"` and `__topic__ = "memory.write.v1"`.
  - `bridge/_generated/k0/models/memory_write_v1.py` — same Pydantic model.
  - `bridge/_generated/k0/handlers/memory_write_v1.py` — `register_handlers(runtime, *, impl)` wiring.
- `bridge/_generated/k0/handlers/memory_write_v1_impl.py` — hand-written impl that wraps existing K0 P02 ingest entry point (`k0/pipelines/p02_write_ingest/__init__.py:ingest`). Lives outside `_generated/` so codegen's `--check` doesn't complain.
- `bridge/_topic_aliases.py` — `TOPIC_ALIASES = {"memory.write": "memory.write.v1"}`. Loaded at runtime; bus dispatcher and bridge transport accept either name. Removed in MS-3a (alias-removal PR).

**Unit tests:** `tests/bridge/contracts/test_memory_write_v1.py`

- `test_memory_write_v1_payload_validation_accepts_valid` — fixture v2.2 MemoryAtom passes Pydantic validation.
- `test_memory_write_v1_payload_validation_rejects_missing_required` — strip each of 14 required fields; assert each fails with the field name in the error.
- `test_memory_write_v1_envelope_signs_and_verifies` — real `Ed25519Signing` from [bridge/core/signing.py](bridge/core/signing.py); sign envelope; verify with same key; assert success and round-trip.
- `test_memory_write_v1_envelope_idem_key_is_blake3_of_canonical_fields` — assert `idem_key` matches `blake3(tenant_id || space_id || atom_id || minute(ts)).hexdigest()[:32]`.
- `test_memory_write_v1_alias_resolves_at_runtime` — submit with topic `"memory.write"`; assert it routes to `memory.write.v1` handler.
- `test_memory_write_v1_round_trip_via_in_process_http` — boot K0 FastAPI app + `InProcessHttpTransport`; client submits; assert handler receives equal Pydantic object (Pydantic equality, not dict).

**No-mock compliance:** real signing keys (test fixtures, never reused), real Pydantic, real FastAPI ASGI transport, real schema `$ref` resolution.

**Wiring at end of epic:** end-to-end path is live in-process: `MemoryWriteV1Client.submit_memory_write_v1(payload)` → `EnvelopeBuilder` → `Ed25519Signing` → `InProcessHttpTransport` → K0 FastAPI route → `register_handlers` impl → existing K0 P02 ingest → SQLite WAL row. The MW production code does not yet use the generated client (that's Epic 3a.2).

**Observability:**

- `bridge.command.memory_write_v1.{accepted_total, rejected_total, latency_ms_histogram}` (counters + histogram, labeled by `tenant_id`)
- `k0.handler.memory_write_v1.{p02_ingest_success, p02_ingest_failure}` (counters)
- structured audit log on every accept/reject with `cognitive_trace_id`, `idem_key`, `envelope_sha256`

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log entry; pin the manifest as the canonical example for future contracts.

### Epic 2.5.6 — MS-2.5 EXIT CRITERION + gate flips + flag removal

**Goal:** prove the substrate works end-to-end with one named test; flip every MS-2.5 gate to `--fail-on-violation`; remove MS-2.5 feature flags.

**Files to create:**

- `tests/bridge/contracts/test_ms_2_5_exit_criterion.py` — full content from whiteboard (per D2.5 substrate exit-criterion section). The test exercises:
  1. Registry loads and validates the `memory.write.v1` manifest against the meta-schema.
  2. Codegen `--check` reports zero drift between manifests and vendored `_generated/`.
  3. Generated K1 client and K0 handler import cleanly; client `__transport__ == "http"`.
  4. Round-trip via `InProcessHttpTransport`: K1 client publishes → K0 handler receives → equal Pydantic object.
  5. CI gate `no_cross_kernel_imports` returns no violations.
  6. CI gate `bus_yaml_aligned_with_registry` returns no violations (every cross-kernel prefix in [k1/config/bus.yaml](k1/config/bus.yaml) has ≥1 registry manifest).
  7. K1 bus dispatcher (R10) refuses `bus.publish("memory.write.v1", payload)` that bypasses the registry — raises `UnknownContractError`.

- Update `bridge/contracts/_meta/feature_flags.yaml`: delete `ms_2_5.codegen_enforced` and `ms_2_5.exit_criterion_active` (no longer needed; behavior is now permanent).

**PR#3 final commits:**

1. Flip `single_ibridge_port_definition` from `--warn-only` to `--fail-on-violation` (already done at PR#1 close, but verify state).
2. Flip `bridge_not_imported_from_kernels` from `--warn-only` to `--fail-on-violation` (allowlist still active; the 2 known violations remain, scheduled for MS-3a / MS-3b).
3. Flip `manifest_implementation_bound` from WARN to `--fail-on-violation` now that `_generated/` is non-empty.
4. Flip `bus_yaml_aligned_with_registry` from WARN to `--fail-on-violation` after every cross-kernel prefix has its `status: proposed` stub manifest committed.
5. Stub manifests created for every prefix found in the WARN day: `memory.*`, `feedback.*`, `recall.*`, `curiosity.*`, `p03.*`, `p07.*`, `family.*`, `ifl.*`. Each is a one-shot `status: proposed` placeholder unblocking the gate; they get fleshed out in their respective milestones.
6. Update [bridge_system_design.md](bridge_system_design.md) iteration log: "MS-2.5 closed; D1–D6 verified; substrate operational; first contract live; 6 gates enforced".
7. Commit `docs/runbooks/bridge_runtime_boot.md` documenting the boot path, expected log lines, and `/healthz` shape.

**Unit tests:** the exit-criterion test IS the test. Plus regression coverage that previously-passing tests still pass.

**No-mock compliance:** the exit test uses real httpx ASGI transport, real Pydantic, real SQLite (in-memory), real codegen invocation, real CI gate scripts.

**Wiring at end of milestone:** every K1→K0 contract from now on must enter via `bridge/contracts/manifests/`. The substrate is the only legal road. CI enforces it.

**Observability:** `/healthz` from MS-2.5 onward includes:

- `bridge.runtime.boot_state` (`booting | ready | shutting_down`)
- `bridge.runtime.contracts_loaded`
- `bridge.runtime.manifest_bundle_sha`
- `bridge.runtime.gates_passed_at_boot` (booleans for each enforced gate)

**Exit test:** `test_one_contract_round_trips_through_generated_code` — when this test is green and all 6 gates are `--fail-on-violation`, MS-2.5 is shipped and MS-3a unblocks.

---

## MS-3a — Online command path (real HTTP, real K0 receiver, first wall-violation cleared)

**Unlocks:** every K1→K0 write contract. Before MS-3a, the only "real" path is in-process via `InProcessHttpTransport` (Epic 2.5.5). After MS-3a, K1 sends commands to a K0 process running in a separate OS process over a real network socket.

**Pre-conditions:** MS-2.5 green; `memory.write.v1` manifest active; generated K1 client + K0 handler in tree.

**Wiring at exit:** `bridge.client.HttpBridgeClient` backed by real `httpx.AsyncClient` against real `k0_app` running on `uvicorn` on an ephemeral port; production [k1/memory_writer/adapters/bridge_command_adapter.py](k1/memory_writer/adapters/bridge_command_adapter.py) uses the generated `IKernelCommandPort` exclusively (no `bridge.core.envelope_builder` import); first known wall violation cleared from the allowlist; K0 verifies signatures via real `ProvisioningLedger.DeviceKey`.

### Epic 3a.1 — Real `HttpBridgeClient` (D-resolved item 1)

**Goal:** the bridge client exists as a frozen-dataclass namespace bag of generated ports. Direct construction is forbidden by lint; all instantiation goes through `BridgeRuntime.from_registry()`.

**Files to create / modify:**

- `bridge/client/__init__.py` — exports `HttpBridgeClient`.
- `bridge/client/http_bridge_client.py`:

  ```python
  @dataclass(frozen=True)
  class HttpBridgeClient:
      command: IKernelCommandPort
      query:   IKernelQueryPort
      sse:     IKernelSSEPort
      obs:     IKernelObsPort
      gateway: IConnectorGatewayPort  # NotImplemented in v1
  ```

  All fields are generated `Protocol`s. Construction validated by `BridgeRuntime`; direct callers depend on the port they need, never on the client.

- `bridge/client/_construction_guard.py` — module-import-time check: if `__name__ != "bridge.runtime"` and caller stack does not include `BridgeRuntime.from_registry`, raise `ConstructionForbiddenError`. Belt-and-braces with the lint rule.
- `tooling/ci/gates/bridge_client_construction_via_runtime_only.py` — new CI gate. `ast.parse`s every `*.py` under `k0/`, `k1/`, `bridge/` (excluding `bridge/runtime.py`); fails on direct `HttpBridgeClient(...)` calls.
- Delete `bridge/client/sink_bridge_client.py` (the stub) — the no-op fallback is now the outbox path in MS-3b, not a separate client.
- Update `bridge/runtime.py:BridgeRuntime.from_registry()` to instantiate `HttpBridgeClient` from the generated port set and store it on the runtime. Existing port slots on the runtime point at the same instances (the client is a view, not a separate object graph).

**Unit tests:** `tests/bridge/client/test_http_bridge_client.py`

- `test_http_bridge_client_is_frozen_dataclass` — `dataclasses.fields()` returns 5 fields; mutation raises `FrozenInstanceError`.
- `test_http_bridge_client_construction_outside_runtime_raises` — `HttpBridgeClient(command=..., query=..., ...)` from test code raises `ConstructionForbiddenError`.
- `test_http_bridge_client_via_runtime_works` — `BridgeRuntime.from_registry(...).client` returns a populated instance.
- `test_bridge_client_construction_via_runtime_only_gate` — fixture violation file fails the gate; clean file passes.
- `test_http_bridge_client_round_trip_real_loopback` — boot real K0 FastAPI app on ephemeral uvicorn port; runtime constructs `HttpTransport` against `http://127.0.0.1:<port>`; client.command publishes; assert K0 received it.

**No-mock compliance:** real `uvicorn.Server` on ephemeral port; real `httpx.AsyncClient`; real Pydantic; no fakes.

**Wiring at end of epic:** runtime's port slots and `HttpBridgeClient` slots reference the same generated port instances. Production code dependency-injects the port it needs (`def __init__(self, command: IKernelCommandPort): ...`), never the client.

**Observability:**

- `bridge.client.command.{success_total, failure_total, latency_ms_histogram}`
- `bridge.client.http.{request_total, error_total, status_code_count}`
- structured log on construction: `{"event": "client_constructed", "runtime_role": "...", "transport": "http", "target": "..."}`

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log entry; commit `docs/runbooks/bridge_client_construction.md` documenting the runtime-only construction rule.

### Epic 3a.2 — Remediate first known wall violation (memory_writer)

**Goal:** [k1/memory_writer/adapters/bridge_command_adapter.py](k1/memory_writer/adapters/bridge_command_adapter.py) currently imports `bridge.core.envelope_builder` directly (line 25). After this epic, MW depends only on the generated `IKernelCommandPort`. The 1st of 2 known violations is cleared.

**Files to modify:**

- `k1/memory_writer/adapters/bridge_command_adapter.py` — rewrite to:

  ```python
  from bridge._generated.k1.ports.command_v1 import IKernelCommandPort
  from bridge._generated.k1.models.memory_write_v1 import MemoryWriteV1

  class BridgeCommandAdapter:
      def __init__(self, command: IKernelCommandPort):
          self._command = command

      async def submit(self, atom: MemoryAtom) -> None:
          payload = MemoryWriteV1.from_atom(atom)
          await self._command.submit_memory_write_v1(payload)
  ```

  All envelope construction (the part that was reaching into `bridge.core.envelope_builder`) now lives inside the generated client. MW is back behind the wall.

- `k1/memory_writer/factory.py` — wires `BridgeCommandAdapter(command=runtime.command)` instead of constructing envelope builders directly.
- `tooling/ci/known_violations/bridge_imports.txt` — remove the `memory_writer` entry. File still has the kernel-adapter entry (cleared in MS-3b).
- Delete `k1/memory_writer/_envelope_helpers.py` if it exists (anywhere MW reaches into bridge internals).

**Unit tests:** `tests/k1/memory_writer/test_bridge_command_adapter.py`

- `test_mw_adapter_uses_only_generated_port` — `inspect.getmodule(adapter._command)` is in `bridge._generated.k1.*`.
- `test_mw_adapter_no_bridge_internal_imports` — `ast.parse` `bridge_command_adapter.py`; assert no `bridge.core.*` / `bridge.sync.*` import nodes.
- `test_mw_adapter_round_trip_real_http` — boot real K0 + real K1 MW; submit a real `MemoryAtom`; assert SQLite WAL row in K0.
- `test_mw_adapter_handles_partial_failure` — K0 returns 503; assert MW receives an exception (outbox queueing is MS-3b — for now MW just fails fast).

**No-mock compliance:** real K0 FastAPI on uvicorn; real httpx; real SQLite; real `MemoryAtom` fixtures.

**Wiring at end of epic:** MW → generated port → bridge runtime → real httpx → K0 FastAPI → handler → P02 → SQLite. The MW box is now thin glue (~30 LOC).

**Observability:**

- `k1.memory_writer.adapter.{submit_total, submit_failure_total, submit_latency_ms}`
- log on every `bridge.core.*` import attempt (none expected; alarms if it returns).

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log entry; mark VIOL_MW as RESOLVED in the wall-violations section.

### Epic 3a.3 — Real K0 receiver (`/k0/command.submit` + MinimalGate + IdempotencyLedger)

**Goal:** K0 can boot as a real FastAPI process, accept signed envelopes over HTTP, verify signatures via real `ProvisioningLedger.DeviceKey`, dedupe via `IdempotencyLedger`, and dispatch to P02 ingest.

**Files to create / modify:**

- `k0/runtime/app.py` (or whatever the K0 ASGI entry point is) — register the `/k0/command.submit` route that delegates to the generated handler registry. K0 boots its own `BridgeRuntime(role=K0)` from the same `bridge/contracts/` directory.
- `k0/gate/minimal_gate.py` — verify envelope signature against `ProvisioningLedger.DeviceKey` (already exists per code-walk; ensure it's wired at the route).
- `k0/idem/idempotency_ledger.py` — already exists; ensure it's checked before P02 dispatch and updated after success.
- `k0/scripts/run_dev_server.py` — `python -m k0.scripts.run_dev_server --port <ephemeral>` launches uvicorn for local dev and tests.
- `k0/contracts/jsonschema/topics/memory_write.body.json` — already exists; ensure it's still the `$ref` target of the bridge manifest schema (Epic 2.5.5 set this up).

**Unit tests:** `tests/k0/runtime/test_command_submit_endpoint.py`

- `test_command_submit_accepts_well_signed_envelope` — real Ed25519 keypair; register pubkey in real `ProvisioningLedger`; POST signed envelope; assert 200 + SQLite row.
- `test_command_submit_rejects_bad_signature` — flip a byte in the signature; assert 401 + audit log entry; assert NO SQLite row.
- `test_command_submit_rejects_unknown_kid` — sig from a key not in `ProvisioningLedger`; assert 401.
- `test_command_submit_idempotency` — submit same envelope twice (same `idem_key`); assert 200 both times, exactly 1 SQLite row.
- `test_command_submit_rejects_unknown_topic` — POST envelope with `topic: "nonexistent.v1"`; assert 404 + clear error.
- `test_command_submit_rejects_envelope_with_invalid_body_schema` — payload missing required MemoryAtom v2.2 field; assert 422 + field name in response.
- `test_command_submit_rejects_revoked_key` — set `key_state: REVOKED` in ProvisioningLedger; assert 401.

**No-mock compliance:** real `httpx.AsyncClient` against real uvicorn server; real `nacl.signing.SigningKey`; real PostgreSQL via testcontainers (or sqlite shim if PostgreSQL not yet wired in dev); real `IdempotencyLedger`.

**Wiring at end of epic:** K0 process boots, listens on a port, accepts signed `memory.write.v1` envelopes, verifies + dedupes + dispatches to P02. End-to-end production-equivalent path is live.

**Observability:**

- `k0.command.submit.{accepted_total, rejected_total, latency_ms}` (labeled by `topic`, `tenant_id`, `rejection_reason`)
- `k0.gate.signature_verify.{success_total, failure_total}` (labeled by `failure_kind`: bad_sig | unknown_kid | revoked)
- `k0.idem.{hit_total, miss_total}`
- audit log row per accepted command and per rejection with full envelope SHA + reason

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log entry; commit `docs/runbooks/k0_command_submit.md` covering the boot procedure, key-provisioning prerequisites, and rejection-code → fix mapping.

### Epic 3a.4 — Alias removal + MS-3a EXIT CRITERION

**Goal:** remove the `memory.write` → `memory.write.v1` alias (D4 cut-over PR#2); ship the named exit test.

**Files to modify:**

- Delete `bridge/_topic_aliases.py` (or empty the dict).
- Update [k1/config/bus.yaml](k1/config/bus.yaml) to use `memory.write.v1` everywhere it referenced `memory.write`.
- Update any K1 production code still publishing under the un-suffixed name.
- Update `bridge/contracts/_meta/feature_flags.yaml`: remove MS-3a flags.

**Files to create:**

- `tests/bridge/integration/test_memory_write_v1_real_http.py`:

  ```python
  @pytest.mark.integration
  async def test_memory_write_v1_lands_in_k0_via_real_http(tmp_path, free_port):
      # Boot real K0 process on ephemeral port (subprocess, not in-process)
      k0_proc = await spawn_k0_server(port=free_port, db_path=tmp_path / "k0.db")
      try:
          # Boot real K1 MW with runtime targeting the K0 process
          k1_runtime = BridgeRuntime.from_registry(
              contracts_path=Path("bridge/contracts"),
              role=Role.K1,
              transport=HttpTransport(base_url=f"http://127.0.0.1:{free_port}"),
          )
          mw = MemoryWriter(command_adapter=BridgeCommandAdapter(k1_runtime.command))
          atom = MemoryAtomFactory.build(content="test memory")
          await mw.write(atom)

          # Assert SQLite row in real K0 process's DB
          rows = await k0_query(tmp_path / "k0.db", f"SELECT * FROM wal WHERE atom_id = ?", atom.id)
          assert len(rows) == 1
          assert rows[0].content == "test memory"
      finally:
          await k0_proc.stop()
  ```

- `tests/integration/conftest.py` — `spawn_k0_server` fixture (real uvicorn subprocess), `free_port` fixture, `k0_query` helper.

**Unit tests:** the exit test IS the test. Plus regression: every prior MS-2.5 + MS-3a unit test still green.

**No-mock compliance:** real OS subprocess, real uvicorn, real httpx, real PostgreSQL or SQLite file, real signing.

**Wiring at end of milestone:** K1 production MW writes to a real K0 process over the wire end-to-end. This is the first time anything in the system actually talks across processes through the bridge.

**Observability:** `/healthz` on K0 returns `{"bridge": {"k0_reachable": true, "contracts": [...], "uptime_s": ...}, "db": {"writable": true}}`.

**Exit test:** `test_memory_write_v1_lands_in_k0_via_real_http` — green ⇒ MS-3a shipped, MS-3b unblocks.

---

## MS-3b — Outbox + DEGRADED for commands (offline tolerance)

**Unlocks:** offline-tolerant writes; cellular-network reality (R5/R11). Before MS-3b, K1 fails when K0 is unreachable. After MS-3b, queueable contracts queue to local outbox and replay when K0 returns; `online_required` contracts surface clear errors.

**Pre-conditions:** MS-3a green; real `HttpBridgeClient` over real httpx is live.

**Wiring at exit:** `K0HealthChecker` polling and emitting transition events; auto-derived DEGRADED matrix per-`(port, topic)` from manifest fields; enriched `LocalOutbox` with `dead_letter` table, per-contract TTL, drain pacing; event-driven drain with 60s safety net; second known wall violation cleared.

### Epic 3b.1 — `K0HealthChecker` + 3-state ONLINE/DEGRADED/OFFLINE machine

**Goal:** the runtime knows whether K0 is reachable and emits an event when state changes. Drain workers and DEGRADED matrix subscribe.

**Files to create / modify:**

- [bridge/core/health.py](bridge/core/health.py) — already exists (per walk); rewrite as 3-state machine:

  ```python
  class K0HealthState(Enum):
      ONLINE = "online"          # last 3 probes succeeded
      DEGRADED = "degraded"      # some recent failures; transitional
      OFFLINE = "offline"        # last 3 probes failed
  ```

  - 30s default poll interval (override per env var `BRIDGE_HEALTH_POLL_INTERVAL_S`); jittered ±10% to avoid thundering herd.
  - Probe = HEAD `/healthz` with 5s timeout.
  - Transition rules:
    - `OFFLINE → ONLINE` requires 1 success (fast recovery for cellular handoff).
    - `ONLINE → OFFLINE` requires 3 consecutive failures (avoid flap).
    - `DEGRADED` is the in-between state during partial failures (>0 but <3 consecutive failures).
  - Emits `ONLINE_TRANSITION` event on `OFFLINE → ONLINE` only (the event the drain worker subscribes to).
  - Owned by `BridgeRuntime`; `from_registry()` starts the poll task on `start()`, cancels on `stop()`.

- `bridge/core/events.py` — `class HealthTransition` event dataclass; minimal in-process pub/sub (`asyncio.Queue` per subscriber); used by drain worker (3b.3) and DEGRADED matrix (3b.2).

**Unit tests:** `tests/bridge/core/test_health_checker.py`

- `test_health_starts_offline_until_first_probe` — boot, no probes yet → `OFFLINE`.
- `test_health_transitions_to_online_after_one_success` — probe succeeds once; state flips.
- `test_health_requires_three_failures_to_go_offline` — 1 fail → DEGRADED, 2 fail → DEGRADED, 3 fail → OFFLINE.
- `test_health_emits_online_transition_event_only_on_offline_to_online` — record events; assert exactly one event per `OFFLINE → ONLINE` flip; zero events for `DEGRADED → ONLINE`.
- `test_health_poll_interval_jittered` — capture 100 probe timestamps; assert jitter within ±10%.
- `test_health_handles_5s_timeout` — backend that never responds; assert poll completes in ~5s, not hung.
- `test_health_real_http_loopback` — real FastAPI app that toggles 200 ↔ 503 every N seconds; observe state machine over 5s.

**No-mock compliance:** real httpx; real FastAPI test app on ephemeral port; real `asyncio.sleep` (with `freezegun` for jitter assertions only).

**Wiring at end of epic:** runtime owns checker; checker emits events; downstream subscribers (added in 3b.3 and 3b.2) consume them.

**Observability:**

- `bridge.health.state{role,target}` (gauge with enum value)
- `bridge.health.probes_total{outcome}` (counter)
- `bridge.health.transition_total{from,to}` (counter)
- `bridge.health.probe_latency_ms` (histogram)
- audit log on every transition

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log entry.

### Epic 3b.2 — Auto-derived DEGRADED matrix (D-resolved item 3)

**Goal:** no hand-coded `if degraded:` branches outside `bridge/core/degraded.py`. Per-`(port, topic)` behavior derived from `delivery.online_required` + `delivery.max_queue_age` at runtime construction time. CI gate enforces.

**Files to create:**

- `bridge/core/degraded.py` — `class DegradedModeManager`:
  - `__init__(self, manifests: list[Manifest])` — at construction, builds `_matrix: dict[(port, topic), Behavior]` where `Behavior` ∈ `{queue_to_outbox, raise_offline_error, mark_stream_closed, drop_with_metric_after_ttl, n_a_subscriber_side}`.
  - `behavior_for(port: str, topic: str) -> Behavior` — O(1) lookup.
  - `degraded_topics() -> set[str]` — live set of topics currently in DEGRADED behavior given current health state.
  - Subscribes to `K0HealthChecker` transition events to update its "currently active behavior" view for `/healthz`.
- `tooling/ci/gates/degraded_mode_derived_only.py` — `ast.parse` every `*.py` outside `bridge/core/degraded.py`; fails on any `if degraded` / `if state == OFFLINE` / `if state == DEGRADED` pattern. `# noqa: degraded-mode — reason` allowlist for genuine cases.

**Unit tests:** `tests/bridge/core/test_degraded.py`

- `test_matrix_derived_from_online_required_true` → behavior is `raise_offline_error`.
- `test_matrix_derived_from_online_required_false_with_max_queue_age` → behavior is `queue_to_outbox`.
- `test_matrix_derived_from_obs_path_with_ttl` → behavior is `drop_with_metric_after_ttl`.
- `test_matrix_for_sse_subscriber` → behavior is `mark_stream_closed`.
- `test_matrix_table_matches_d_resolved_item_3` — assert the full table from D-resolved item 3 (Command memory.write.v1 → queue, committed.plan.v1 → raise, recall.request.v1 → raise, SSE → close, Obs → queue with TTL, Gateway → raise).
- `test_degraded_topics_updates_on_health_transition` — boot with health OFFLINE; assert `degraded_topics()` returns the queueable + raise-error sets; flip to ONLINE; assert empty set.
- `test_gate_degraded_mode_derived_only_passes_clean` — clean fixture passes.
- `test_gate_degraded_mode_derived_only_fails_on_violation` — fixture with hand-coded `if degraded:` outside `degraded.py` fails.

**No-mock compliance:** real manifest loader, real `ast.parse`, real fixtures.

**Wiring at end of epic:** runtime instantiates `DegradedModeManager` from manifests at boot; transport / outbox / port decorators consult it on every dispatch.

**Observability:**

- `bridge.degraded_topics_count` (gauge)
- `bridge.degraded.behavior_total{port,topic,behavior}` (counter — every dispatch decision)
- `/healthz` exposes `{"degraded_topics": [...], "behaviors": {...}}`

**Documentation update:** commit `docs/runbooks/degraded_mode.md` listing every behavior, the manifest fields that drive it, and the operator response for each.

### Epic 3b.3 — `LocalOutbox` enriched: `dead_letter` + TTL + drain pacing (D-resolved item 2)

**Goal:** rewrite [bridge/sync/local_outbox.py](bridge/sync/local_outbox.py) into the durable, TTL-bounded, dead-letter-routing, pace-able outbox per D-resolved item 2.

**Files to create / modify:**

- [bridge/sync/local_outbox.py](bridge/sync/local_outbox.py) — schema (SQLite WAL):

  ```sql
  CREATE TABLE outbox (
      envelope_id      TEXT PRIMARY KEY,
      topic            TEXT NOT NULL,
      payload          BLOB NOT NULL,
      enqueued_at      TIMESTAMP NOT NULL,
      max_queue_age_s  INTEGER NOT NULL,
      attempts         INTEGER DEFAULT 0,
      last_error       TEXT
  );
  CREATE INDEX idx_outbox_topic_enqueued ON outbox(topic, enqueued_at);

  CREATE TABLE dead_letter (
      envelope_id      TEXT PRIMARY KEY,
      topic            TEXT NOT NULL,
      payload          BLOB NOT NULL,
      enqueued_at      TIMESTAMP NOT NULL,
      moved_at         TIMESTAMP NOT NULL,
      reason           TEXT NOT NULL,
      response_code    INTEGER,
      response_body    TEXT
  );
  ```

  API:
  - `enqueue(envelope) -> None` — appends to `outbox`; takes `max_queue_age` from manifest.
  - `claim_batch(topic: str | None, max_size: int = 100) -> list[Envelope]` — head-of-line scan; respects per-topic ordering.
  - `mark_drained(envelope_ids: list[str]) -> None` — deletes on success.
  - `move_to_dead_letter(envelope_id, reason, response_code, response_body) -> None` — for 4xx (contract violations).
  - `prune_expired() -> int` — deletes rows where `enqueued_at + max_queue_age_s < now`; returns count for metric.
  - Concurrency: writers use `INSERT`; drain reader uses `BEGIN IMMEDIATE`; SQLite WAL mode handles the rest.

- `bridge/sync/drain_worker.py` — `class DrainWorker`:
  - Three triggers (per D-resolved item 2): event-driven on `ONLINE_TRANSITION` (~50ms p99), 60s safety-net periodic sweep, one immediate pass on `start()`.
  - Bounded batches: max 100 envelopes / 5s wall-clock per batch; yields to asyncio loop between batches.
  - Per-contract pacing: respects `delivery.drain_rate_per_sec` if set.
  - Failure routing: 5xx → leave in outbox (will retry), 4xx → `move_to_dead_letter`.
  - Emits per-batch metrics.
- `bridge/sync/__init__.py` — exports both.

**Unit tests:** `tests/bridge/sync/test_local_outbox.py` and `test_drain_worker.py`

- `test_outbox_enqueue_dequeue_round_trip` — real SQLite tmp file.
- `test_outbox_dead_letter_routing_on_4xx` — drain hits a 4xx-returning loopback; envelope in `dead_letter` table; metric incremented.
- `test_outbox_5xx_keeps_envelope_for_retry` — same flow, 5xx; envelope stays in outbox.
- `test_outbox_ttl_prune_expires_old_envelopes` — fast-forward time via injected clock; assert pruned envelopes counted, deleted.
- `test_outbox_concurrent_enqueue_during_drain` — 1000 concurrent enqueues + drain in flight; assert no row loss, no duplicate drain.
- `test_drain_event_driven_within_50ms_p99` — emit `ONLINE_TRANSITION`; measure time-to-first-batch over 100 trials; assert p99 ≤50ms.
- `test_drain_safety_net_60s_sweep` — break the event path (subscribe disabled); assert 60s sweep still drains.
- `test_drain_startup_pass` — pre-load 50 envelopes into outbox, start worker, assert immediate drain attempt.
- `test_drain_bounded_batch_size_and_wall_clock` — 1000 envelopes; assert each batch ≤100 and ≤5s.
- `test_drain_per_contract_pacing` — set `drain_rate_per_sec=10`; assert observed rate ≤10/s ±10%.

**No-mock compliance:** real SQLite tmp file (in-process via `aiosqlite`); real loopback FastAPI for failure-injection; real `asyncio.Event` for transition signal; injected logical clock for TTL fast-forward (allowed under "Time" exception).

**Wiring at end of epic:** runtime owns one `LocalOutbox` and one `DrainWorker`; `OnlineFirst[Port]` decorator (3b.4) injects them into command paths.

**Observability:**

- `bridge.outbox.depth{topic}` (gauge)
- `bridge.outbox.enqueued_total{topic}` (counter)
- `bridge.outbox.drained_total{topic}` (counter)
- `bridge.outbox.dead_letter_total{topic, reason}` (counter)
- `bridge.outbox.pruned_total{topic}` (counter — TTL expirations)
- `bridge.outbox.drain_latency_ms` (histogram, labeled by `trigger ∈ event|safety_net|startup`)
- `bridge.outbox.drain_batch_size` (histogram)

**Documentation update:** runbook `docs/runbooks/bridge_outbox.md` covering: where the SQLite file lives, how to inspect dead-letter, TTL operator override, dead-letter replay procedure.

### Epic 3b.4 — `OnlineFirst[Port]` decorator (D9)

**Goal:** wrap any `IKernelCommandPort` so it dispatches to HTTP when online and queues / raises when offline, per the auto-derived matrix. No business code touches the matrix or the outbox.

**Files to create:**

- `bridge/core/online_first.py`:

  ```python
  class OnlineFirstCommandPort:
      def __init__(
          self,
          *,
          inner: IKernelCommandPort,
          outbox: LocalOutbox,
          health: K0HealthChecker,
          degraded: DegradedModeManager,
      ): ...

      async def submit_<topic>(self, payload):
          state = self.health.state
          behavior = self.degraded.behavior_for("command", topic)
          if state == ONLINE:
              try:
                  return await self.inner.submit_<topic>(payload)
              except TransientError:
                  if behavior == queue_to_outbox:
                      await self.outbox.enqueue(envelope_for(payload, topic))
                      return
                  raise
          # state in {DEGRADED, OFFLINE}
          if behavior == queue_to_outbox:
              await self.outbox.enqueue(envelope_for(payload, topic))
              return
          if behavior == raise_offline_error:
              raise OfflineError(topic=topic, current_state=state)
  ```

  Methods generated dynamically by reading the wrapped port's `Protocol` methods.

- `bridge/runtime.py:from_registry()` — wrap every `IKernelCommandPort` impl via `OnlineFirstCommandPort` before stuffing into `HttpBridgeClient`.

**Unit tests:** `tests/bridge/core/test_online_first.py`

- `test_online_first_dispatches_to_inner_when_online` — health ONLINE; assert inner called, outbox not touched.
- `test_online_first_queues_when_offline_and_queueable` — health OFFLINE + `online_required: false`; assert outbox enqueued.
- `test_online_first_raises_when_offline_and_required` — health OFFLINE + `online_required: true`; assert `OfflineError`.
- `test_online_first_queues_on_5xx_during_online` — inner raises `TransientError`; queueable contract; assert enqueued.
- `test_online_first_propagates_4xx` — inner raises `ValidationError`; assert raised, NOT enqueued (4xx is not queueable; will hit dead_letter via drain instead if it reaches the wire).
- `test_online_first_e2e_with_real_outbox_and_health` — real httpx loopback that toggles; queue 50 envelopes during outage; observe drain on recovery.

**No-mock compliance:** real outbox SQLite file, real health checker, real loopback.

**Wiring at end of epic:** every command-port flow is offline-aware. No K1 caller code changes.

**Observability:**

- `bridge.online_first.dispatch_total{topic, decision}` where decision ∈ `inline | queued | raised`
- `bridge.online_first.transient_caught_total{topic}` (5xx caught and queued)
- log on every `raised` decision with topic + reason

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log entry.

### Epic 3b.5 — Remediate second known wall violation (kernel adapter)

**Goal:** [k1/kernel/adapters/bridge_adapter.py](k1/kernel/adapters/bridge_adapter.py) currently imports `bridge.sync.local_outbox` (line 59). After this epic, the kernel adapter is back behind the wall — outbox is owned by `BridgeRuntime`, not the adapter.

**Files to modify:**

- `k1/kernel/adapters/bridge_adapter.py` — drop `bridge.sync.local_outbox` import. The adapter receives a wired `IKernelCommandPort` (already `OnlineFirstCommandPort`-decorated by the runtime); outbox queueing happens transparently inside the decorator.
- `k1/kernel/factory.py` — wire `BridgeAdapter(command=runtime.command, query=runtime.query, sse=runtime.sse, obs=runtime.obs)`.
- `tooling/ci/known_violations/bridge_imports.txt` — remove kernel-adapter entry. **File now empty.** Delete the file entirely; gate enforces zero violations.

**Unit tests:** `tests/k1/kernel/test_bridge_adapter.py`

- `test_kernel_adapter_no_bridge_internal_imports` — `ast.parse`; assert no `bridge.core.*` / `bridge.sync.*` imports.
- `test_kernel_adapter_offline_writes_queued_via_decorator` — health OFFLINE; submit; assert outbox depth +1; adapter never touched outbox directly.
- `test_kernel_adapter_online_writes_pass_through` — health ONLINE; submit; assert SQLite WAL row in K0; outbox depth 0.

**No-mock compliance:** real outbox file, real health, real K0 loopback.

**Wiring at end of epic:** the wall holds. Both known violations cleared. The allowlist file no longer exists.

**Observability:** unchanged (the adapter is now thin glue; its metrics are the runtime's metrics).

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log entry; mark VIOL_KERNEL as RESOLVED.

### Epic 3b.6 — MS-3b EXIT CRITERION + chaos harness

**Goal:** prove offline tolerance with a real failure-injection test; remove MS-3b feature flags.

**Files to create:**

- `tests/bridge/integration/test_outbox_drain_on_recovery.py`:

  ```python
  @pytest.mark.integration
  async def test_outbox_drains_on_online_transition_within_50ms_p99(tmp_path, free_port):
      k0_proc = await spawn_k0_server(port=free_port, db_path=tmp_path / "k0.db")
      k1_runtime = BridgeRuntime.from_registry(
          contracts_path=Path("bridge/contracts"),
          role=Role.K1,
          transport=HttpTransport(base_url=f"http://127.0.0.1:{free_port}"),
      )
      await k1_runtime.start()

      # Phase 1: K0 down for 60s
      await k0_proc.stop()
      await asyncio.sleep(0.5)  # let health detect OFFLINE
      assert k1_runtime.health.state == K0HealthState.OFFLINE

      # Submit 200 queueable envelopes + 5 online_required envelopes
      mw = MemoryWriter(command=k1_runtime.command)
      for atom in MemoryAtomFactory.build_batch(200):
          await mw.write(atom)  # queues to outbox
      with pytest.raises(OfflineError):
          await k1_runtime.command.submit_committed_plan_v1(committed_plan_fixture())

      assert k1_runtime.outbox.depth() == 200

      # Phase 2: K0 recovers
      k0_proc = await spawn_k0_server(port=free_port, db_path=tmp_path / "k0.db")
      transition_t = time.monotonic()

      # Phase 3: assert drain completes within bounds
      await wait_until(lambda: k1_runtime.outbox.depth() == 0, timeout_s=30)
      drain_first_batch_latency_ms = (k1_runtime.metrics.first_batch_after_transition_ms())
      assert drain_first_batch_latency_ms < 50  # p99 budget

      # Assert no data loss
      rows = await k0_query(tmp_path / "k0.db", "SELECT COUNT(*) FROM wal")
      assert rows[0][0] == 200

      # Assert no duplicate writes (idempotency)
      atom_ids = await k0_query(tmp_path / "k0.db", "SELECT atom_id FROM wal")
      assert len(set(atom_ids)) == 200
  ```

- `tests/integration/conftest.py` additions: `wait_until` helper, `K0Process` fixture with `start/stop/restart`.
- Update `bridge/contracts/_meta/feature_flags.yaml`: remove MS-3b flags.
- Update [bridge_system_design.md](bridge_system_design.md) iteration log: "MS-3b closed; offline tolerance live; outbox + DEGRADED matrix + OnlineFirst decorator + drain worker operational; both wall violations cleared".

**Unit tests:** the exit test IS the test. Plus 100-trial p99 measurement subtest.

**No-mock compliance:** real subprocess kill/restart; real outbox; real httpx loopback.

**Wiring at end of milestone:** K1 commands survive K0 restarts with no data loss, no duplicates, with sub-50ms recovery latency.

**Exit test:** `test_outbox_drains_on_online_transition_within_50ms_p99` — green ⇒ MS-3b shipped, MS-3c unblocks.

---

## MS-3c — Query port (real recall against real K0)

**Unlocks:** real K1→K0 reads. After MS-3c, [k1/concierge](k1/concierge) and [k1/planner](k1/planner) call `recall("...")` and get real K0 hits, not `RecallBundle.empty()`.

**Pre-conditions:** MS-3b green; outbox + health + DEGRADED operational.

**Wiring at exit:** `recall.request.v1` + `recall.response.v1` manifests active; generated `IKernelQueryPort` replaces hand-written; K0 P01 returns real hits over real httpx; Concierge depends on the generated port directly (no adapter layer).

### Epic 3c.1 — `recall.request.v1` + `recall.response.v1` manifests + schemas + codegen

**Goal:** capture the request/response pair as two paired manifests. Query is request/response, not fire-and-forget; the codegen pattern needs to handle that explicitly.

**Files to create:**

- `bridge/contracts/manifests/recall.request.v1.yaml` — `direction: k1_to_k0`, `delivery.online_required: true`, `delivery.transport: http`, paired with response below.
- `bridge/contracts/manifests/recall.response.v1.yaml` — `direction: k0_to_k1`, `delivery.transport: http` (response on the same HTTP request, NOT SSE), `paired_with: recall.request.v1`.
- `bridge/contracts/schemas/recall.request.v1.json` — body: `{selectors: [...], space_id, tenant_id, max_latency_ms, fail_fast, max_results, vector_query?, fts_query?, time_range?}`.
- `bridge/contracts/schemas/recall.response.v1.json` — body: `{hits: [{atom_id, content, score, source}], total, latency_ms, truncated: bool}`.
- Manifest meta-schema update: add optional `paired_with: <topic>` field to support request/response coupling. Add `allOf` rule: when `paired_with` set, partner manifest must exist.
- Codegen template update: when manifest has `paired_with`, emit a `request` method on the producer side that returns the paired response Pydantic model (instead of `None`).
- Run codegen → vendor `bridge/_generated/{k0,k1}/{models,ports,clients,handlers}/recall_request_v1.py` + `recall_response_v1.py`.

**Unit tests:** `tests/bridge/contracts/test_recall_request_v1.py`

- `test_recall_request_payload_validation` — well-formed and malformed selectors.
- `test_recall_response_payload_validation` — empty response, full response, oversized hits.
- `test_paired_with_meta_schema_rule` — manifest with `paired_with: nonexistent.v1` fails validation.
- `test_codegen_emits_request_method_returning_response_model` — generated client method signature has correct return type annotation.
- `test_recall_request_response_round_trip_in_process` — fixture K0 handler returns 5 hits; client receives them.

**No-mock compliance:** real codegen, real Pydantic, real ASGI loopback.

**Wiring at end of epic:** generated `IKernelQueryPort` exists with `recall_request_v1(payload) -> RecallResponseV1` method.

**Observability:** `bridge.query.recall_request_v1.{success_total, failure_total, latency_ms, hits_returned_count}` (counters + histograms).

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; document `paired_with` pattern in `docs/runbooks/contract_authoring.md`.

### Epic 3c.2 — Real `KernelQueryPort` over real K0 P01 + Concierge integration

**Goal:** end-to-end real recall path; Concierge (the actual production caller) uses the generated port directly.

**Files to create / modify:**

- `k0/runtime/app.py` — register `/k0/query.recall` route delegating to generated handler.
- `bridge/_generated/k0/handlers/recall_request_v1_impl.py` — wraps existing K0 P01 entry point ([k0/pipelines/p01_recall](k0/pipelines/p01_recall) module). Calls P01 with the request payload, packages results into `RecallResponseV1`, returns.
- `k1/concierge/services/recall_service.py` — replace any existing hand-written adapter with direct dependency on `IKernelQueryPort` from generated module:

  ```python
  class RecallService:
      def __init__(self, query: IKernelQueryPort):
          self._query = query

      async def recall(self, prompt: str, **opts) -> RecallBundle:
          payload = build_recall_request(prompt, **opts)
          response = await self._query.recall_request_v1(payload)
          return RecallBundle.from_response(response)
  ```

- `k1/concierge/factory.py` — wires `RecallService(query=runtime.query)`.
- `k1/planner/stages/recall_stage.py` — same dependency change (planner's recall path).

**Unit tests:** `tests/k0/pipelines/p01/test_recall_handler.py` and `tests/k1/concierge/test_recall_service.py`

- `test_p01_recall_handler_returns_real_hits` — write 10 fixture memories to real K0 SQLite; call handler; assert 10 hits in correct order.
- `test_p01_recall_handler_respects_max_results` — write 100; request `max_results: 5`; assert ≤5 returned + `truncated: true`.
- `test_p01_recall_handler_respects_fail_fast` — slow query path; `fail_fast: true` + small `max_latency_ms`; assert returns within budget with partial results.
- `test_concierge_recall_real_e2e` — real K0 + real K1 Concierge; recall returns real hits.
- `test_concierge_recall_offline_raises_offline_error` — health OFFLINE + `online_required: true`; assert `OfflineError` (no fallback queueing for queries — they're synchronous).

**No-mock compliance:** real K0 process, real PostgreSQL via testcontainers (or sqlite for dev), real httpx, real Pydantic.

**Wiring at end of epic:** Concierge → generated port → real httpx → K0 P01 → real DB. Recall returns real data end-to-end.

**Observability:**

- `k0.handler.recall_request_v1.{calls_total, hits_returned, latency_ms, truncated_total}`
- `k1.concierge.recall.{requests_total, latency_ms, hits_received}`
- `k0.p01.{candidates_scanned, vector_search_latency_ms, fts_search_latency_ms}`

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log entry.

### Epic 3c.3 — MS-3c EXIT CRITERION

**Goal:** named test proves real recall round-trip.

**Files to create:**

- `tests/bridge/integration/test_recall_request_real_http.py`:

  ```python
  @pytest.mark.integration
  async def test_recall_request_returns_real_k0_hits(tmp_path, free_port):
      k0_proc = await spawn_k0_server(port=free_port, db_path=tmp_path / "k0.db")
      try:
          k1_runtime = BridgeRuntime.from_registry(
              contracts_path=Path("bridge/contracts"),
              role=Role.K1,
              transport=HttpTransport(base_url=f"http://127.0.0.1:{free_port}"),
          )

          # Seed K0 with real memories via memory.write.v1
          mw = MemoryWriter(command=k1_runtime.command)
          for fact in [
              "yesterday I bought eggs and milk",
              "tomorrow I have a dentist appointment",
              "the kid has math homework due Friday",
          ]:
              await mw.write(MemoryAtomFactory.build(content=fact))
          await wait_until(lambda: k0_seen_atoms(tmp_path / "k0.db") == 3, timeout_s=5)

          # Recall via the real port
          concierge_recall = RecallService(query=k1_runtime.query)
          bundle = await concierge_recall.recall("yesterday's groceries")

          assert len(bundle.hits) >= 1
          assert any("eggs" in h.content for h in bundle.hits)
          assert bundle != RecallBundle.empty()  # the smoking-gun assertion
      finally:
          await k0_proc.stop()
  ```

- Update `bridge/contracts/_meta/feature_flags.yaml`: remove MS-3c flags.
- Update [bridge_system_design.md](bridge_system_design.md) iteration log: "MS-3c closed; recall returns real K0 hits".

**No-mock compliance:** real K0 subprocess, real DB, real recall pipeline.

**Wiring at end of milestone:** the system has both arms wired — writes (MS-3a/b) and reads (MS-3c). Concierge can answer "what did I do yesterday?" from real persisted data.

**Exit test:** `test_recall_request_returns_real_k0_hits` — green ⇒ MS-3c shipped, MS-3d unblocks.

---

## MS-3d — SSE port (real chunked streaming + cursor resume + backpressure)

**Unlocks:** every K0→K1 event topic; the proactive / curiosity / advisory / consolidation flows. Before MS-3d, K1 doesn't actually receive events from K0 (the existing `response.json()["events"]` shortcut breaks under any real load — R3, R11). After MS-3d, K1 gets a live chunked stream that survives cellular handoff via cursor resume.

**Pre-conditions:** MS-3c green; real K0 process running; manifests + codegen toolchain handle SSE direction.

**Wiring at exit:** real `httpx-sse` client; cursor resume protocol on the wire (D13); backpressure handler with explicit policy (D14); five SSE manifests (`curiosity.intent.v1`, `k0.learning.advisory.v1`, `k0.proactive.signal.v1`, `p03.gap.detected.v1`, `p03.complete.v1`) live; K1 `GAP_SSE_LISTENER` receives a real P06-emitted event end-to-end within 200ms p99.

### Epic 3d.1 — Five K0→K1 SSE manifests + schemas + codegen

**Goal:** capture the canonical SSE topics. Codegen needs to handle SSE direction differently from HTTP request/response.

**Files to create:**

- `bridge/contracts/manifests/curiosity.intent.v1.yaml` — `direction: k0_to_k1`, `delivery.transport: sse`, `delivery.ordering: best_effort`, `delivery.ack_required: true`, `delivery.online_required: false`, `delivery.codec: json`, `semantics.duplicate_strategy: dedupe_by_envelope_id`, `sla.latency_p99_ms: 500`, `sla.availability: degrades_to_local_queue` (subscriber side has 24h replay window via cursor).
- `bridge/contracts/manifests/k0.learning.advisory.v1.yaml`
- `bridge/contracts/manifests/k0.proactive.signal.v1.yaml`
- `bridge/contracts/manifests/p03.gap.detected.v1.yaml`
- `bridge/contracts/manifests/p03.complete.v1.yaml`
- Corresponding `bridge/contracts/schemas/<topic>.v1.json` — payload shapes lifted from existing K0 emitters.
- Codegen template update for SSE direction: `IKernelSSEPort` Protocol gets `subscribe_<topic>(handler) -> AsyncContextManager[Subscription]`; client stub wraps handler in retry/cursor logic.
- Run codegen → vendor SSE ports + handlers.

**Unit tests:** `tests/bridge/contracts/test_sse_manifests.py`

- `test_each_sse_manifest_validates_against_meta_schema`
- `test_sse_payload_schemas_validate_real_event_fixtures` — load 10 real events from K0 emitter test fixtures; assert they validate.
- `test_codegen_emits_subscribe_methods_for_sse_topics` — generated `IKernelSSEPort` has `subscribe_curiosity_intent_v1`, etc.
- `test_sse_topics_appear_in_bus_yaml_alignment` — gate `bus_yaml_aligned_with_registry` returns no violations for these prefixes.

**No-mock compliance:** real codegen, real Pydantic, real schema fixtures.

**Wiring at end of epic:** generated `IKernelSSEPort` exists; not yet wired to a transport (3d.2).

**Observability:**

- `bridge.sse.<topic>.{events_received_total, decode_failure_total, lag_ms_histogram}`

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log.

### Epic 3d.2 — Real chunked SSE client (D12, D13, D14)

**Goal:** replace the `response.json()["events"]` shortcut with a real chunked stream that survives cellular handoff via cursor resume and applies backpressure when the consumer is slow.

**Files to create:**

- `requirements.txt` addition: `httpx-sse==0.4.*` (D12 decision pinned).
- `bridge/core/transport/sse_client.py`:
  - `class SSEClient`:
    - Wraps `httpx_sse.aconnect_sse(client, "GET", url, headers={"Last-Event-ID": cursor})`.
    - **Cursor resume (D13):** sends `Last-Event-ID: <envelope_id>` header with the last successfully-handled event's id. K0 SSE endpoint must accept this header and resume from that cursor (server-side replay buffer with ≥24h window per manifest `delivery.retention`).
    - **Backpressure (D14):** internal `asyncio.Queue(maxsize=1000)` between SSE wire reader and consumer handler. Policy on overflow: **block the wire reader** (let TCP backpressure propagate to K0); after `BLOCK_TIMEOUT_S=30` of full queue, **close the stream** and reconnect with current cursor. Drop policy explicitly rejected — events must not be silently dropped (audit + replay constraint).
    - **Reconnect with exponential backoff** capped at 30s; jittered; emits `bridge.sse.reconnect_total{topic, reason}`.
    - On reconnect, resends `Last-Event-ID` so no event is lost.
  - `class SSESubscription` (async context manager): exposes `async for event in subscription: ...`.
  - `class CursorStore`: persists last-handled `envelope_id` per topic to `~/.familyos/sse_cursors.sqlite` so cursor survives K1 process restart.
- `bridge/core/transport/__init__.py` — register SSE transport selector.

**Unit tests:** `tests/bridge/core/transport/test_sse_client.py`

- `test_sse_client_receives_chunked_events` — real K0 FastAPI emitting `EventSourceResponse`; client receives 100 events in order.
- `test_sse_client_sends_last_event_id_header_on_reconnect` — kill connection mid-stream; client reconnects; assert `Last-Event-ID` header set to last handled id.
- `test_sse_client_resumes_from_cursor` — K0 server with replay buffer; client disconnects after handling event 50/100; reconnects with cursor; receives events 51..100 (no duplicates, no gaps).
- `test_sse_client_persists_cursor_across_restart` — handle 50 events, kill K1 process; restart; assert cursor loaded from disk; resume from event 51.
- `test_sse_client_backpressure_blocks_wire_reader_when_handler_slow` — handler sleeps 100ms per event; emit at 100/s; assert internal queue stays bounded; observe wire-reader pause via metric.
- `test_sse_client_closes_stream_after_30s_full_queue` — handler hangs forever; assert stream closed after 30s, reconnect attempted.
- `test_sse_client_no_event_loss_under_handoff_simulation` — kill TCP socket every 2s for 30s while emitter sends 1000 events; assert all 1000 handled (some duplicates allowed but tracked via dedupe).
- `test_sse_client_dedupe_by_envelope_id_on_replay` — server replays 5 already-handled events on reconnect; client `dedupe_by_envelope_id` semantics drop them.

**No-mock compliance:** real `httpx-sse`, real `EventSourceResponse` from `sse-starlette`, real ephemeral uvicorn, real socket close (via OS kill or `aiohttp.web.Server.shutdown`).

**Wiring at end of epic:** any K1 caller can `async with runtime.sse.subscribe_<topic>(handler) as sub: ...` and get a real, resilient stream.

**Observability:**

- `bridge.sse.<topic>.{events_handled_total, events_dedupe_dropped_total, handler_latency_ms}`
- `bridge.sse.stream.{state{topic,value}, reconnects_total{topic, reason}, cursor_lag_events{topic}, wire_buffer_depth{topic}, wire_reader_blocked_total{topic}}`
- audit log on every reconnect with cursor

**Documentation update:** runbook `docs/runbooks/sse_client.md` covering cursor format, reconnect behavior, backpressure policy, troubleshooting "events not arriving".

### Epic 3d.3 — Real K0 SSE endpoint with replay buffer

**Goal:** K0 `/k0/sse.subscribe` is a real chunked endpoint that respects `Last-Event-ID` for replay.

**Files to create / modify:**

- `requirements.txt` addition: `sse-starlette==2.0.*`.
- `k0/sse/endpoint.py`:
  - FastAPI route `/k0/sse.subscribe?topic=<topic>` — returns `EventSourceResponse`.
  - On connect, reads `Last-Event-ID` header; queries [k0/sse/replay_buffer.py](k0/sse/replay_buffer.py) for events strictly after that id.
  - Streams replay events first, then live events.
  - Per-subscriber per-topic backpressure: if consumer can't keep up (TCP send buffer full), K0 detects via `BrokenPipeError` and closes stream cleanly.
- `k0/sse/replay_buffer.py`:
  - SQLite-backed circular buffer per topic (rotated by `delivery.retention` from manifest).
  - `append(envelope) -> envelope_id`
  - `replay_after(topic, last_event_id) -> AsyncIterator[Envelope]`
- Wire P05/P06/P03 emitters to `replay_buffer.append(envelope)` first, then fanout to live subscribers via in-process pub/sub.

**Unit tests:** `tests/k0/sse/test_endpoint.py` and `test_replay_buffer.py`

- `test_endpoint_streams_chunked_response` — assert `Transfer-Encoding: chunked` header.
- `test_endpoint_replays_from_last_event_id` — append 100 events, subscribe with `Last-Event-ID: 50`; assert 51..100 received.
- `test_endpoint_handles_unknown_last_event_id` — cursor not in buffer (e.g. 24h+ old); assert 410 Gone or full snapshot per policy decision.
- `test_endpoint_closes_on_slow_consumer` — consumer that doesn't ack; assert clean close after timeout, no resource leak.
- `test_replay_buffer_rotation` — append > retention size; assert old events evicted; `bridge.sse.replay_buffer.eviction_total` incremented.
- `test_replay_buffer_concurrent_append_and_replay` — 1000 concurrent appends + 5 concurrent replays; no row loss, no torn reads.

**No-mock compliance:** real uvicorn, real SQLite, real httpx-sse client, real FastAPI.

**Wiring at end of epic:** P06 emits `curiosity.intent.v1` → replay buffer + fanout → SSE endpoint → wire → K1 `SSEClient` → handler.

**Observability:**

- `k0.sse.subscribers_count{topic}` (gauge)
- `k0.sse.events_emitted_total{topic}` (counter)
- `k0.sse.slow_consumer_disconnect_total{topic}` (counter)
- `k0.sse.replay_buffer.{depth{topic}, eviction_total{topic}, replay_request_total{topic, hit|miss}}`

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; runbook `docs/runbooks/k0_sse_endpoint.md`.

### Epic 3d.4 — End-to-end proactive flow + MS-3d EXIT CRITERION

**Goal:** trigger real P06 → real `curiosity.intent.v1` → real K1 `GAP_SSE_LISTENER` end-to-end with p99 latency assertion.

**Files to modify:**

- `k1/concierge/services/proactive_listener.py` (or wherever GAP_SSE_LISTENER lives) — replace any hand-written SSE handling with `runtime.sse.subscribe_curiosity_intent_v1(handler)`.

**Files to create:**

- `tests/bridge/integration/test_curiosity_intent_v1_streams_e2e.py`:

  ```python
  @pytest.mark.integration
  async def test_curiosity_intent_v1_streams_e2e_under_200ms_p99(tmp_path, free_port):
      k0_proc = await spawn_k0_server(port=free_port, db_path=tmp_path / "k0.db")
      try:
          k1_runtime = BridgeRuntime.from_registry(
              contracts_path=Path("bridge/contracts"),
              role=Role.K1,
              transport=HttpTransport(base_url=f"http://127.0.0.1:{free_port}"),
          )
          await k1_runtime.start()

          received: list[CuriosityIntentV1] = []
          received_ts: list[float] = []
          async with k1_runtime.sse.subscribe_curiosity_intent_v1(
              lambda evt: (received.append(evt), received_ts.append(time.monotonic_ns()))
          ):
              # Trigger 100 P06 emissions via the K0 admin/test endpoint
              emit_ts: list[float] = []
              for i in range(100):
                  t = time.monotonic_ns()
                  await k0_admin_emit_curiosity_intent(free_port, gap_id=f"g{i}")
                  emit_ts.append(t)

              await wait_until(lambda: len(received) == 100, timeout_s=10)

          latencies_ms = [(rt - et) / 1e6 for rt, et in zip(received_ts, emit_ts)]
          p99 = sorted(latencies_ms)[98]
          assert p99 < 200, f"p99 latency {p99}ms exceeds 200ms budget"

          # Cellular-handoff sub-test: kill TCP mid-stream, assert resume
          async with k1_runtime.sse.subscribe_curiosity_intent_v1(handler) as sub:
              await k0_admin_emit_curiosity_intent(free_port, gap_id="g_pre")
              await wait_until(lambda: any(h.gap_id == "g_pre" for h in received))
              await k0_proc.kill_active_tcp_connections()  # force socket close
              await k0_admin_emit_curiosity_intent(free_port, gap_id="g_post")
              await wait_until(lambda: any(h.gap_id == "g_post" for h in received), timeout_s=5)
      finally:
          await k0_proc.stop()
  ```

- Update `bridge/contracts/_meta/feature_flags.yaml`: remove MS-3d flags.
- Update [bridge_system_design.md](bridge_system_design.md) iteration log: "MS-3d closed; real chunked SSE with cursor resume; proactive flow live end-to-end".

**Unit tests:** the exit test IS the test.

**No-mock compliance:** real K0, real P06 emission path, real SSE wire, real cellular-simulation via TCP kill.

**Wiring at end of milestone:** all proactive flows are real. The asymmetry between MW-write-arm (live since MS-3a) and Concierge-read-arm (live since MS-3c) is now joined by the K0→K1 streaming-event arm. K1 truly receives K0 events.

**Exit test:** `test_curiosity_intent_v1_streams_e2e_under_200ms_p99` — green ⇒ MS-3d shipped, MS-3e unblocks.

---

## MS-3e — Obs / feedback port (closing the feedback loop)

**Unlocks:** the K0 learning loop. Before MS-3e, K1 has no way to tell K0 "that recall hit was wrong / that proactive question was bad / the user corrected me". After MS-3e, K1 emits `feedback.envelope.v1`, K0 P21 ingests, BusDispatcher fans out to P02/P08 — the system can learn from its mistakes.

**Pre-conditions:** MS-3d green; all four prior ports (command, query, SSE, obs-stub) live.

**Wiring at exit:** `feedback.envelope.v1` + `observability.payload.v1` + `feedback.signal.p02.v1` manifests active; real `FeedbackEmitter` with three detectors (Correction, Validation, Reformulation); real K0 P21 writes `st_feedback_signals`; K0 BusDispatcher emits `feedback.signal.<pipeline>.v1` to P02 / P08.

### Epic 3e.1 — Manifests + codegen for obs / feedback path

**Goal:** capture the obs path explicitly. Obs is fire-and-forget K1→K0, queueable with TTL (24h per D-resolved item 3).

**Files to create:**

- `bridge/contracts/manifests/feedback.envelope.v1.yaml` — `direction: k1_to_k0`, `delivery.transport: http`, `delivery.online_required: false`, `delivery.max_queue_age: 24h`, `delivery.codec: json`, `semantics.idempotent: true`, `semantics.duplicate_strategy: dedupe_by_envelope_id`.
- `bridge/contracts/manifests/observability.payload.v1.yaml` — same shape, different topic, lower priority pacing (`delivery.drain_rate_per_sec: 100` to avoid storm on recovery).
- `bridge/contracts/manifests/feedback.signal.p02.v1.yaml` — `direction: k0_to_k0` (intra-K0 bus dispatch), `sync.layer: l1_family_memory` is wrong here — this is intra-K0, not cross-K0; meta-schema needs a `direction: intra_k0` value or this manifest stays in K0's own bus and doesn't enter the bridge registry. **Decision pinned by this epic:** intra-K0 bus topics do NOT enter the bridge registry; only the K1→K0 wire portion does. The signal that K0 fans out to P02 is internal.
- `bridge/contracts/schemas/feedback.envelope.v1.json` — body: `{kind: correction|validation|reformulation, target_atom_id, target_signal_id?, score: float, evidence: {...}, originating_user_msg_id}`.
- `bridge/contracts/schemas/observability.payload.v1.json` — body: `{kind: metrics|logs, payload: {...}}`.
- Run codegen → vendor obs port + handlers.

**Unit tests:** `tests/bridge/contracts/test_obs_manifests.py`

- `test_feedback_envelope_payload_validation` — accept valid; reject missing target.
- `test_feedback_envelope_idempotent_replay` — submit twice; assert second is no-op.
- `test_observability_payload_validation`
- `test_obs_port_codegen` — generated `IKernelObsPort` has `emit_feedback_envelope_v1`, `emit_observability_payload_v1`.

**No-mock compliance:** real codegen, real Pydantic.

**Wiring at end of epic:** generated `IKernelObsPort` exists; not yet wired to detectors.

**Observability:** `bridge.obs.{emitted_total{kind}, dropped_expired_total{kind}}`.

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; pin "intra-K0 bus topics stay out of the registry" as a design rule.

### Epic 3e.2 — `FeedbackEmitter` + three real detectors (no mocks)

**Goal:** detect feedback signals from real conversation transcripts. Three detectors must work against real K1 conversation data, not synthetic fixtures.

**Files to create:**

- `k1/concierge/feedback/detectors/__init__.py`
- `k1/concierge/feedback/detectors/correction.py` — detects user-correction patterns ("no, I meant...", "actually,...", "that's wrong"). Real NLP via existing concierge tokenizer / classifier.
- `k1/concierge/feedback/detectors/validation.py` — detects user-validation ("yes, exactly", "right", "perfect").
- `k1/concierge/feedback/detectors/reformulation.py` — detects re-asks of similar question (signals previous answer insufficient).
- `k1/concierge/feedback/feedback_emitter.py`:

  ```python
  class FeedbackEmitter:
      def __init__(self, *, obs: IKernelObsPort, detectors: list[Detector]):
          self._obs = obs
          self._detectors = detectors

      async def on_user_message(self, ctx: ConversationContext, user_msg: Message):
          for det in self._detectors:
              signals = det.detect(ctx, user_msg)
              for sig in signals:
                  await self._obs.emit_feedback_envelope_v1(
                      FeedbackEnvelopeV1(
                          kind=sig.kind,
                          target_atom_id=sig.target_atom_id,
                          score=sig.score,
                          evidence=sig.evidence,
                          originating_user_msg_id=user_msg.id,
                      )
                  )
  ```

- `k1/concierge/factory.py` — wires `FeedbackEmitter(obs=runtime.obs, detectors=[Correction(), Validation(), Reformulation()])`; subscribes it to the conversation event stream.

**Unit tests:** `tests/k1/concierge/feedback/test_detectors.py`

- For each detector, ≥10 real conversation fixtures from existing K1 test corpus; assert detect / no-detect decisions.
- `test_correction_detects_no_i_meant` — fixture transcript with correction phrase + previous bot answer; assert signal emitted with target = previous atom id.
- `test_validation_detects_yes_exactly`
- `test_reformulation_detects_repeated_question_with_paraphrase` — similarity threshold tuning fixture.
- `test_feedback_emitter_e2e_in_process` — fake conversation transcript → detectors → emitter → in-process obs port → assert real httpx call to K0.
- `test_feedback_emitter_dedupes_repeat_signals_within_window` — same correction fired twice in 5s → only one emit (idempotent dedupe at emitter level).

**No-mock compliance:** real conversation fixtures (`tests/fixtures/conversations/*.json`), real detector code, real httpx loopback for the emit path.

**Wiring at end of epic:** Concierge runs detectors on every user message; feedback flows into the obs port automatically.

**Observability:**

- `k1.feedback.detector.{detected_total{detector,kind}, false_positive_estimate{detector}}` (the false-positive estimate is later validated against K0 audit)
- `k1.feedback.emitter.{emitted_total{kind}, deduped_total{kind}}`

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; document detector tuning thresholds in `docs/runbooks/feedback_detectors.md`.

### Epic 3e.3 — Real K0 P21 + `st_feedback_signals` + bus dispatch to P02 / P08

**Goal:** K0 receives `feedback.envelope.v1`, persists to `st_feedback_signals`, and emits `feedback.signal.<pipeline>.v1` on the K0 bus so P02 (write-ingest) and P08 (embedding) can adjust.

**Files to create / modify:**

- `k0/runtime/app.py` — register `/k0/obs.emit` route (handles both `feedback.envelope.v1` and `observability.payload.v1`).
- `bridge/_generated/k0/handlers/feedback_envelope_v1_impl.py` — wraps K0 P21 entry point.
- [k0/pipelines/p21_feedback](k0/pipelines/p21_feedback) — verify exists or create:
  - `process(envelope) -> SignalRow` — validates, derives `signal_kind`, writes to `st_feedback_signals`.
  - On commit, publishes `feedback.signal.<originating_pipeline>.v1` on the K0 bus (`p02` for memory-correction signals, `p08` for embedding-relevance signals).
- `k0/storage/migrations/<timestamp>_st_feedback_signals.sql` — schema:

  ```sql
  CREATE TABLE st_feedback_signals (
      signal_id        UUID PRIMARY KEY,
      tenant_id        UUID NOT NULL,
      kind             TEXT NOT NULL,
      target_atom_id   UUID,
      target_signal_id UUID,
      score            REAL NOT NULL,
      evidence         JSONB NOT NULL,
      originating_user_msg_id TEXT,
      created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
      processed_at     TIMESTAMP,
      INDEX (tenant_id, kind, created_at)
  );
  ```

- `k0/bus/dispatcher.py` — verify it can route the new internal signals to P02 / P08 subscribers.

**Unit tests:** `tests/k0/pipelines/p21/test_feedback_pipeline.py`

- `test_p21_persists_envelope_to_st_feedback_signals` — emit envelope; assert real PostgreSQL row.
- `test_p21_dispatches_correction_to_p02` — emit kind=correction; assert P02 subscriber receives `feedback.signal.p02.v1`.
- `test_p21_dispatches_relevance_to_p08` — same for embedding kind.
- `test_p21_dedupe_by_envelope_id` — emit same envelope_id twice; assert exactly 1 row.
- `test_p21_audit_log_on_invalid_payload` — malformed envelope; assert rejection + audit row.
- `test_obs_offline_queues_with_24h_ttl` — health OFFLINE; emit; assert outbox depth +1; fast-forward 25h; assert pruned with metric.

**No-mock compliance:** real K0 process, real PostgreSQL, real bus dispatcher, real httpx loopback.

**Wiring at end of epic:** K1 detector → emitter → obs port → outbox-aware HTTP → K0 P21 → SQL write + bus dispatch → P02/P08.

**Observability:**

- `k0.p21.{ingested_total{kind}, dispatched_total{kind, target_pipeline}, rejected_total{reason}, latency_ms}`
- `k0.bus.feedback_signal_dispatched_total{topic}`
- `k0.st_feedback_signals.depth` (rows over time)

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; commit `docs/runbooks/k0_feedback_pipeline.md`.

### Epic 3e.4 — MS-3e EXIT CRITERION

**Goal:** named test proves end-to-end feedback loop closes.

**Files to create:**

- `tests/bridge/integration/test_feedback_loop_real_e2e.py`:

  ```python
  @pytest.mark.integration
  async def test_feedback_signal_p02_v1_round_trips_to_k0(tmp_path, free_port):
      k0_proc = await spawn_k0_server(port=free_port, db_path=tmp_path / "k0.db")
      try:
          k1_runtime = BridgeRuntime.from_registry(
              contracts_path=Path("bridge/contracts"),
              role=Role.K1,
              transport=HttpTransport(base_url=f"http://127.0.0.1:{free_port}"),
          )
          await k1_runtime.start()

          # Seed K0 with a memory
          mw = MemoryWriter(command=k1_runtime.command)
          atom = MemoryAtomFactory.build(content="user said they like espresso")
          await mw.write(atom)
          await wait_until(lambda: k0_seen_atoms(tmp_path / "k0.db") == 1)

          # K1 detector fires a Correction targeting that atom
          emitter = FeedbackEmitter(obs=k1_runtime.obs, detectors=[Correction()])
          ctx = ConversationContext(prior_bot_atom_id=atom.id)
          await emitter.on_user_message(ctx, Message(text="no, actually I drink tea"))

          # Assert K0 PostgreSQL row in st_feedback_signals
          await wait_until(lambda: count_rows(tmp_path / "k0.db", "st_feedback_signals") == 1)
          row = get_row(tmp_path / "k0.db", "st_feedback_signals")
          assert row.kind == "correction"
          assert row.target_atom_id == atom.id

          # Assert P02 subscriber on K0 received feedback.signal.p02.v1
          assert await k0_bus_received(free_port, "feedback.signal.p02.v1", target_atom_id=atom.id, timeout_s=5)
      finally:
          await k0_proc.stop()
  ```

- Update `bridge/contracts/_meta/feature_flags.yaml`: remove MS-3e flags.
- Update [bridge_system_design.md](bridge_system_design.md) iteration log: "MS-3e closed; full feedback loop closes K1 detector → K0 P21 → P02/P08 bus".

**Unit tests:** the exit test IS the test.

**No-mock compliance:** real K0, real PostgreSQL, real bus, real detectors, real httpx.

**Wiring at end of milestone:** the system is now closed-loop. Writes (3a/b) → reads (3c) → events (3d) → feedback (3e). Every K0↔K1 interaction in the v1 product surface is a real wire over a real port with real durability and offline tolerance.

**Exit test:** `test_feedback_signal_p02_v1_round_trips_to_k0` — green ⇒ MS-3e shipped, MS-4 unblocks.

---

## MS-4 — Codecs + adapter consolidation

**Unlocks:** wire-format flexibility (msgpack/CBOR for size-sensitive topics like SSE replay payloads); enforces the K1 adapter LOC budget that R8 (adapter sprawl) was created to prevent regressing.

**Pre-conditions:** MS-3e green (all 5 ports — command, query, SSE, obs, gateway-stub — generated and live; full closed-loop in production).

**Wiring at exit:**

- `bridge/core/codecs/{json,msgpack,cbor}.py` implementations live; codec selected per `manifest.delivery.codec` at dispatch time.
- All 7 K1 adapters that were "thick wrappers" before MS-3 are now <100 LOC each, summing to <100 LOC total. The MW-side `BridgeCommandAdapter` (one of the two known wall violations from MS-2.5) is deleted; MW depends on `IKernelCommandPort` directly.
- New CI gate `adapter_loc_budget` enforced (`tooling/ci/gates/adapter_loc_budget.py`).
- `Content-Type` / `Accept` HTTP header negotiation honored end-to-end so a client can request `application/msgpack` and the K0 endpoint encodes accordingly when the manifest permits it.

### Epic 4.1 — Codec library + per-manifest selection

**Goal:** real msgpack and CBOR encoders/decoders behind a uniform `Codec` Protocol; the codec a contract uses is derived once at runtime construction from `manifest.delivery.codec` (no hand-coded `if codec == ...` branches in business code; same R10 discipline that `OnlineFirst[Port]` follows).

**Decisions pinned by this epic:**

- **msgpack library:** `msgpack==1.0.*` (pure-C, fastest Python option, stable API, 16M+ downloads/month). `ormsgpack` rejected — newer, narrower test surface, marginal speedup not worth supply-chain bet.
- **CBOR library:** `cbor2==5.6.*` (RFC 8949 compliant, has CBOR-tags support we'll need for binary blob payloads in MS-5+).
- **JSON library:** stays stdlib `json` — no need for `orjson` until profiling shows it. The bridge envelope is already canonicalised in `envelope_builder.py`; we don't want two JSON renderers in the path.
- **Codec negotiation:** server-side advertises `Accept-Patch` and respects request `Accept` header; if request asks for a codec the manifest doesn't allow (`manifest.delivery.codecs_allowed: [json, msgpack]`), reply 406 Not Acceptable with structured error.
- **Wire-format constraint:** the envelope outer-frame stays JSON (signing depends on canonical JSON of the envelope). Only the `body` field switches codec. This keeps signing logic untouched and aligns with how K0's existing P03 pipelines treat the body as opaque bytes.

**Manifest schema delta** (lands as part of this epic; meta-schema additive change, no new gate needed):

```yaml
delivery:
  codec: json                                 # default; existing manifests stay valid
  codecs_allowed: [json]                      # allowed list for negotiation; default = [codec]
  codec_negotiation: client_choice_in_allowed # enum: fixed | client_choice_in_allowed
```

**Files to create / modify:**

- `requirements.txt`: add `msgpack==1.0.*`, `cbor2==5.6.*`.
- `bridge/core/codecs/__init__.py`: exports `Codec` Protocol, `JSONCodec`, `MsgpackCodec`, `CBORCodec`, `CodecRegistry`.
- `bridge/core/codecs/json_codec.py`:

  ```python
  class JSONCodec:
      content_type: ClassVar[str] = "application/json"
      def encode(self, body: dict) -> bytes: ...
      def decode(self, raw: bytes) -> dict: ...
  ```

- `bridge/core/codecs/msgpack_codec.py` — same shape; `content_type = "application/msgpack"`; uses `msgpack.packb(body, use_bin_type=True)` and `msgpack.unpackb(raw, raw=False)`.
- `bridge/core/codecs/cbor_codec.py` — same shape; `content_type = "application/cbor"`; uses `cbor2.dumps`/`cbor2.loads`.
- `bridge/core/codecs/registry.py`:

  ```python
  class CodecRegistry:
      def __init__(self) -> None:
          self._by_name: dict[str, Codec] = {"json": JSONCodec(), "msgpack": MsgpackCodec(), "cbor": CBORCodec()}
      def for_manifest(self, manifest: ManifestRecord) -> Codec: ...
      def for_negotiation(self, manifest: ManifestRecord, accept_header: str | None) -> Codec: ...
  ```

- `bridge/core/transport/http_transport.py`: at request build time, ask `codec = registry.for_manifest(manifest)`; encode body via `codec.encode(...)`; set `Content-Type: codec.content_type`; on response, dispatch decode by response `Content-Type`.
- `bridge/_generated/k0/handlers/_dispatch.py` (codegen-emitted): generated handler reads request `Content-Type`; instantiates the right decoder; on output, honors request `Accept` if codec is in manifest's allowed list, else falls back to manifest default.
- `tooling/contracts/codegen.py`: emit `codec_allowed` const into generated handler module so the dispatch table doesn't have to re-read the manifest at runtime.
- Update one existing manifest (`bridge/contracts/manifests/curiosity.intent.v1.yaml` — high-volume SSE replay topic) to `codec: msgpack`, `codecs_allowed: [json, msgpack]` so we exercise the negotiation path in tests against a real production manifest, not just synthetic fixtures.

**Unit tests:** `tests/bridge/core/codecs/test_codecs.py`, `tests/bridge/core/codecs/test_registry.py`, `tests/bridge/core/transport/test_codec_negotiation.py`

- `test_json_codec_round_trip_on_every_active_manifest_body` — load every active manifest's example payload (in `bridge/contracts/schemas/<topic>.v1.example.json`), encode + decode, assert structural equality.
- `test_msgpack_codec_round_trip_preserves_ints_floats_strings_bytes_and_nested_dicts`.
- `test_cbor_codec_round_trip_preserves_same_types_plus_tagged_datetimes`.
- `test_msgpack_smaller_than_json_for_typical_envelope_body` — assert ≥30% size reduction on a representative `curiosity.intent.v1` payload (sanity check, not perf gate).
- `test_codec_registry_resolves_manifest_default` — manifest with `codec: msgpack`; assert registry returns `MsgpackCodec`.
- `test_codec_registry_negotiation_honors_client_accept_when_allowed` — manifest `codec: json, codecs_allowed: [json, msgpack]`; client `Accept: application/msgpack`; registry returns msgpack.
- `test_codec_registry_negotiation_falls_back_to_default_when_accept_not_allowed` — manifest `codec: json, codecs_allowed: [json]`; client `Accept: application/cbor`; registry returns json (or 406 — chosen behaviour per the manifest's `codec_negotiation: fixed` flag).
- `test_codec_negotiation_returns_406_when_strict_and_unsupported` — `codec_negotiation: fixed`, mismatched `Accept`; assert 406 with `{"error":"unsupported_media_type","supported":["application/json"]}`.
- `test_http_transport_sets_correct_content_type_header_per_codec` — real `httpx.MockTransport` ASGI loopback; assert `Content-Type` header byte-for-byte.
- `test_generated_k0_handler_decodes_msgpack_request_body` — real K0 FastAPI app + real httpx; POST msgpack-encoded `curiosity.intent.v1` body; assert handler receives correct dict.
- `test_envelope_outer_frame_stays_json_when_body_is_msgpack` — assert signing works (outer envelope JSON canonicalised; body is `{"_codec": "msgpack", "_bytes_b64": "..."}` or equivalent wrapping).

**No-mock compliance:** real msgpack lib, real cbor2 lib, real FastAPI + httpx loopback. Only fakes are time/randomness if any test uses them.

**Wiring at end of epic:** any manifest can declare a non-JSON codec; clients negotiate via standard HTTP `Accept`; codegen wires the decoder; everything else (signing, idempotency, outbox, SSE) keeps working unchanged because codec is a localised concern at the codec/transport boundary.

**Observability:**

- `bridge.codec.encode_latency_ms_histogram{codec, topic}` — per-codec encode latency.
- `bridge.codec.decode_latency_ms_histogram{codec, topic}`.
- `bridge.codec.encoded_bytes_histogram{codec, topic}` — for the size-comparison story.
- `bridge.codec.negotiation_total{requested, served}` — counter.
- `bridge.codec.unsupported_media_type_total{topic}` — 406 emissions.

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; `docs/runbooks/codec_selection.md` covering when to pick msgpack vs CBOR vs JSON (rule of thumb: JSON unless body is ≥1KB AND topic is high-frequency).

### Epic 4.2 — Adapter consolidation: collapse 7 K1 adapters

**Goal:** every K1 module that today has its own `bridge_*_adapter.py` (memory_writer, kernel, planner, fabric, concierge, sessionstate, learning) becomes a thin shim — ≤15 LOC each — that delegates to the generated client. The wall violations identified in MS-2.5 (`MW.bridge_command_adapter` importing `bridge.core.envelope_builder`; `kernel.bridge_adapter` importing `bridge.sync.local_outbox`) are deleted along with the imports.

**Pre-conditions inside MS-4:** Epic 4.1 may land in parallel; this epic does not depend on codecs.

**Decisions pinned by this epic:**

- **Generated clients are the K1 default.** The hand-written adapter file persists only as a one-import re-export shim while downstream callers migrate. After this epic, the shim is allowed to be 0 LOC (a `from bridge._generated.k1.clients.<topic>_v1 import *` style re-export, validated by import-linter rule).
- **MW-side write path:** `k1/memory_writer/services/writer.py` calls `runtime.command.send_memory_write_v1(...)` directly via `IKernelCommandPort` (DI-injected at K1 boot in `k1/runtime.py`). The `MW.BridgeCommandAdapter` class is deleted; its 200-line content is replaced by the 1-line generated-client call.
- **Wall violations resolved permanently.** The `no_cross_kernel_imports` gate (already enforced since MS-2.5) catches any regression. We additionally remove the now-unused `bridge.sync.local_outbox` symbol from any K1 import surface — outbox lives behind `IKernelCommandPort` (via `OnlineFirstCommandPort` from MS-3b epic 3b.4) and is never reached directly.
- **LOC budget enforcement:** new gate `adapter_loc_budget` runs `wc -l` on every file matching `k1/**/adapters/bridge_*.py`. Budget = 100 LOC total across all 7 files. Exceeded → CI fails with the per-file breakdown in the error message.

**Files to modify (one epic-1-PR per K1 module to keep diffs reviewable):**

| K1 module | Today | Target |
| --------- | ----- | ------ |
| `k1/memory_writer/adapters/bridge_command_adapter.py` | ~200 LOC, builds envelopes, calls outbox, signs | **deleted**; MW.writer calls `runtime.command.send_memory_write_v1(...)` |
| `k1/kernel/adapters/bridge_adapter.py` | ~150 LOC, has `bridge.sync.local_outbox` import | ≤15 LOC re-export shim → generated kernel client |
| `k1/planner/adapters/bridge_adapter.py` | ~120 LOC | ≤15 LOC shim |
| `k1/fabric/adapters/bridge_adapter.py` | ~100 LOC | ≤15 LOC shim |
| `k1/concierge/adapters/bridge_adapter.py` | ~140 LOC | ≤15 LOC shim |
| `k1/sessionstate/adapters/bridge_adapter.py` | ~80 LOC | ≤15 LOC shim |
| `k1/learning/adapters/bridge_adapter.py` | ~60 LOC | ≤15 LOC shim |
| **Total LOC** | **~850** | **<100** |

**Files to create:**

- `tooling/ci/gates/adapter_loc_budget.py`:

  ```python
  ADAPTER_GLOB = "k1/**/adapters/bridge_*.py"
  TOTAL_BUDGET = 100   # SLOC, comments stripped, blank lines stripped
  PER_FILE_HARD_CAP = 25
  def main() -> int: ...   # walk glob, count SLOC via tokenize, fail with breakdown
  ```

- `.github/workflows/bridge_ci.yml` — add `adapter_loc_budget` to the gate matrix; flip to `--fail-on-violation` at MS-4 exit (epic 4.3).

- Add an `import-linter` contract `bridge_internals_not_imported_by_k1` (the import-linter project we already use for MS-2.5 gates):

  ```ini
  [importlinter:contract:bridge_internals_not_imported_by_k1]
  name = K1 must only import bridge via generated clients and Protocol ports
  type = forbidden
  source_modules = k1
  forbidden_modules =
      bridge.core.envelope_builder
      bridge.core.signing
      bridge.sync.local_outbox
      bridge.core.transport
      bridge.connector.mcp_process_manager
  allow_indirect_imports = false
  ```

  This is the structural lockdown that prevents R8 (adapter sprawl) from regrowing — even if a developer adds a 200-LOC adapter to k1, they can't reach into bridge internals to do anything useful with it.

**Unit tests:** `tests/k1/<module>/adapters/test_bridge_adapter_thin_shim.py` per module, plus `tests/tooling/ci/test_adapter_loc_budget_gate.py`

- `test_mw_send_memory_write_v1_uses_generated_client_directly` — assert MW writer calls `runtime.command.send_memory_write_v1(...)` (no `BridgeCommandAdapter` reference).
- For each remaining 6 modules: `test_<module>_bridge_adapter_is_thin_reexport` — assert file SLOC ≤15 via importing the gate's counter; assert all symbols re-exported from `bridge._generated.k1.clients`.
- `test_no_module_in_k1_imports_envelope_builder_or_local_outbox` — programmatic check via `importlib.util.find_spec` and AST walk; redundant with import-linter contract but explicit per-test failure message is more actionable.
- `test_adapter_loc_budget_gate_passes_under_threshold` — synthetic temp tree with 7 files of 14 LOC each; total = 98; gate passes.
- `test_adapter_loc_budget_gate_fails_over_threshold_with_breakdown` — synthetic tree summing to 105; gate fails; assert error message contains per-file table.
- `test_adapter_loc_budget_gate_per_file_cap` — single file = 30 LOC (over per-file cap of 25); fails even when total <100.
- `test_full_k1_test_suite_passes_after_consolidation` — meta-test that re-runs every `tests/k1/**/test_*` file; baseline comparison: zero new failures vs pre-consolidation snapshot.
- `test_import_linter_bridge_internals_contract_passes` — runs `lint-imports` against the new contract; clean.

**No-mock compliance:** real K1 modules, real generated clients, real K0 ASGI loopback for the round-trip assertions. Adapters are deleted before the tests run, so any test still importing them is a real failure to fix.

**Wiring at end of epic:**

- K1 → bridge dependency surface = (a) Protocol ports in `bridge/ports/`, (b) generated clients in `bridge/_generated/k1/clients/`. Nothing else.
- The MS-2.5 canary test (`test_one_contract_round_trips_through_generated_code`) still passes — adapter consolidation does not change wire behaviour.
- The 7 K1 adapter files have either been deleted or shrunk to the re-export shim.

**Observability:**

- No new runtime metrics (the generated clients already emit per-topic dispatch metrics from MS-3a/b/c/d/e).
- Build-time: `adapter_loc_budget` gate emits `bridge.ci.adapter_loc_total` to the CI metrics sink (so we can chart "adapter LOC over time" and prove R8 doesn't regress).

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; new section in `docs/development/bridge_adapter_pattern.md` documenting the thin-shim convention and the LOC budget rationale; update the wall-violation tracker in `bridge_system_design.md` (R8 row → "resolved at MS-4").

### Epic 4.3 — MS-4 EXIT CRITERION

**Goal:** named test proves both halves of MS-4 work: codec negotiation end-to-end AND adapter LOC budget enforced.

**Files to create:**

- `tests/bridge/integration/test_ms4_exit.py`:

  ```python
  @pytest.mark.integration
  async def test_adapter_loc_under_budget_and_codec_negotiation_works(tmp_path, free_port):
      # Part 1: adapter LOC budget
      gate_result = subprocess.run(
          [sys.executable, "-m", "tooling.ci.gates.adapter_loc_budget"],
          capture_output=True, text=True, check=False,
      )
      assert gate_result.returncode == 0, gate_result.stderr

      # Part 2: codec negotiation end-to-end
      k0_proc = await spawn_k0_server(port=free_port, db_path=tmp_path / "k0.db")
      try:
          runtime = await BridgeRuntime.from_registry(role="k1", k0_url=f"http://127.0.0.1:{free_port}")

          # request msgpack via Accept header
          envelope = build_envelope_curiosity_intent_v1(...)
          response = await runtime._http.post(
              "/k0/sse.intent.publish",
              content=msgpack.packb({"envelope": envelope.dict(), "body": {...}}, use_bin_type=True),
              headers={"Content-Type": "application/msgpack", "Accept": "application/msgpack"},
          )
          assert response.status_code == 202
          assert response.headers["Content-Type"] == "application/msgpack"
          decoded = msgpack.unpackb(response.content, raw=False)
          assert decoded["status"] == "accepted"

          # negotiation falls back when client asks for unsupported codec on a json-only manifest
          mw_envelope = build_envelope_memory_write_v1(...)
          response = await runtime._http.post(
              "/k0/memory.write",
              json={"envelope": mw_envelope.dict(), "body": {...}},
              headers={"Accept": "application/cbor"},  # not in memory.write.v1 codecs_allowed
          )
          assert response.status_code == 406
          assert response.json()["error"] == "unsupported_media_type"
      finally:
          await k0_proc.terminate()
  ```

- Update `bridge/contracts/_meta/feature_flags.yaml`: remove MS-4 flags (`codec_negotiation_enabled`, `adapter_consolidation_enforced`).
- Update [bridge_system_design.md](bridge_system_design.md) iteration log: "MS-4 closed; msgpack/CBOR negotiable per-manifest; adapter LOC budget enforced at <100 total; R8 resolved".

**Unit tests:** the exit test IS the test.

**No-mock compliance:** real K0, real msgpack, real httpx, real adapter LOC count.

**Wiring at end of milestone:** wire-format flexibility unlocked for high-volume topics (set the stage for MS-5 IFL adapters that may ship binary payloads); adapter sprawl risk structurally mitigated; K1 → bridge dependency cleaned to (Protocol ports + generated clients) only.

**Exit test:** `test_adapter_loc_under_budget_and_codec_negotiation_works` — green ⇒ MS-4 shipped, MS-5 unblocks.

---

## MS-5 — IFL minimum (ConnectorGateway + MCP Process Manager + Google Calendar read-only adapter)

**Unlocks:** the first external-device reach for FamilyOS — read-only Google Calendar across all family members, exercised through the full v1 IFL surface (manifest + signing + credential vault + MCP process supervision + K0 ingestion). After MS-5, "does the family have a free Saturday?" is answerable from a single K1 query.

**Pre-conditions:** MS-4 green (codecs + clean adapter surface).

**Wiring at exit:**

- `IConnectorGatewayPort` impl in `bridge/connector/gateway.py` constructed from registry at boot.
- 3-stage gateway pipeline (TokenVerifier → AdapterVerifier → RequestRouter) — **no RateLimiter / CircuitBreaker** (D18 deferred to v1.1; reserved manifest fields validated but ignored).
- MCP Process Manager (`bridge/connector/mcp_process_manager.py`) supervising one MCP child process per active adapter manifest with OS-native sandboxing per platform (D16).
- One real adapter live: `connectors/google_calendar/` MCP server, OAuth 2.0 device-flow consent, read-only `calendar.events.list` tool, credentials in OS keychain (D17).
- CA bundle ceremony (D19) executed; `familyos_root_v1` real Ed25519 public key replaces the `PLACEHOLDER_REPLACE_BEFORE_MS5` in `bridge/contracts/_meta/ca_bundle.json`.
- K0 IFL storage tables (`st_ifl_adapter_registry`, `st_ifl_credentials`, `st_ifl_manifests`, `st_ifl_events`) populated on first invocation.

**Strategic shifts vs the original MS-5 skeleton:**

- **WASM removed** (D16). No `WASMSandboxDispatcher`, no Wasmtime/Wasmer/Wazero pin, no MQTT WASM adapter epic. v1 IFL Runtime = MCP Process Manager only. Re-add criteria for WASM documented as triggers for the post-v2 ADR `0091-wasm-untrusted-adapter-runtime`.
- **Rate-limiter / circuit-breaker removed** (D18). v1 ships with OS-level resource caps (cgroup CPU/memory/fd limits in MCP sandbox config) + adapter-SDK retry/timeout. v1.1 drops in `aiolimiter==1.1.*` + `purgatory==3.0.*` without API churn (manifest fields reserved + observability hooks already shipping).
- **Hue deferred** (D15). Google Calendar wins first-adapter slot for universality, OAuth maturity, and cross-person planning value.

**PR sequencing within MS-5:**

| PR | Scope |
| -- | ----- |
| PR#1 | Gateway port + manifest schema additions (`mcp:` block, `delivery.transport: mcp_stdio`) + 3-stage pipeline (no rate-limiter/breaker) |
| PR#2 | MCP Process Manager + per-OS sandbox profiles + crash budget supervision |
| PR#3 | OS keychain + sqlcipher fallback credential vault (`bridge/connector/credential_vault.py`) |
| PR#4 | D19 ceremony executed; signed PR replacing CA bundle placeholder |
| PR#5 | Google Calendar MCP server + IFL manifest + K0 IFL storage tables + exit test |

### Epic 5.1 — `IConnectorGatewayPort` impl + IFL manifest schema additions

**Goal:** the gateway port is constructed from the manifest registry the same way the other 5 ports are; manifest schema knows about `direction: device_to_k0` / `device_from_k0`, the `mcp:` block, and signature-required adapters.

**Decisions pinned by this epic:**

- **Gateway is a port, not a service.** `IConnectorGatewayPort` lives in `bridge/ports/`; impl in `bridge/connector/gateway.py`; injected into K1 fabric at runtime via `BridgeRuntime.from_registry()` exactly like the other ports.
- **One gateway instance for all adapters.** Internally it routes by `manifest.adapter_id`. Per-adapter state (process handle, last-call time) lives in `MCPProcessManager`, not in the port.
- **Signed manifests are mandatory for IFL.** `signing.ca_id: familyos_root_v1` + `signing.signature: <base64url-ed25519>` required for any manifest with `direction` starting `device_*`. Validated at boot via `BridgeBootError` (D10 code `E_BRIDGE_BOOT_CA_BUNDLE_MISSING` if the signing CA isn't in the bundle).

**Files to create / modify:**

- `bridge/ports/connector_gateway.py` (already exists from earlier walk per [bridge/ports/](../../../bridge/ports) — verify Protocol shape):

  ```python
  class IConnectorGatewayPort(Protocol):
      async def invoke(self, *, adapter_id: str, tool: str, args: dict, caller: ConnectorCaller) -> ConnectorResult: ...
      async def list_tools(self, *, adapter_id: str) -> list[ToolDescriptor]: ...
      async def health(self, *, adapter_id: str) -> AdapterHealth: ...
  ```

- `bridge/connector/gateway.py`:

  ```python
  class ConnectorGateway:
      def __init__(self, *,
                   manifest_registry: ManifestRegistry,
                   credential_vault: CredentialVault,
                   process_manager: MCPProcessManager,
                   audit_log: AuditLog) -> None: ...
      async def invoke(self, ...) -> ConnectorResult:
          # 3-stage pipeline (token → adapter → router)
          await self._token_verifier.verify(caller, manifest)
          await self._adapter_verifier.verify(manifest)
          return await self._router.dispatch(manifest, tool, args, caller)
  ```

- `bridge/connector/contracts.py`: dataclasses `ConnectorCaller`, `ConnectorResult`, `ToolDescriptor`, `AdapterHealth`, `OfflineAdapterError`, `AdapterQuarantinedError`, `InvalidAdapterSignatureError`.
- `bridge/contracts/_meta/manifest.schema.json` — additive deltas (not breaking; existing manifests stay valid):

  ```json
  {
    "properties": {
      "direction": {
        "enum": ["k0_to_k1", "k1_to_k0", "k0_to_k0", "k1_to_k1",
                 "device_to_k0", "device_from_k0"]
      },
      "delivery": {
        "properties": {
          "transport": {
            "enum": ["http", "sse", "in_process", "e2ee_lan", "https", "mcp_stdio"]
          }
        }
      },
      "mcp": {
        "type": "object",
        "additionalProperties": false,
        "required": ["server_command", "sandbox", "health"],
        "properties": {
          "server_command": { "type": "array", "items": { "type": "string" }, "minItems": 1 },
          "sandbox": {
            "type": "object",
            "required": ["memory_max", "cpu_quota_percent", "network"],
            "properties": {
              "memory_max":         { "type": "string", "pattern": "^[0-9]+[KMG]$" },
              "cpu_quota_percent":  { "type": "integer", "minimum": 1, "maximum": 100 },
              "network":            { "enum": ["none", "outbound_only", "full"] },
              "filesystem_read":    { "type": "array", "items": { "type": "string" } },
              "filesystem_write":   { "type": "array", "items": { "type": "string" } }
            }
          },
          "health": {
            "type": "object",
            "required": ["ping_interval_s", "max_missed_pings"],
            "properties": {
              "ping_interval_s":   { "type": "integer", "minimum": 1, "maximum": 60 },
              "max_missed_pings":  { "type": "integer", "minimum": 1, "maximum": 10 }
            }
          }
        }
      },
      "rate_limit":      { "$ref": "#/definitions/rate_limit_reserved_v1_1" },
      "circuit_breaker": { "$ref": "#/definitions/circuit_breaker_reserved_v1_1" }
    },
    "allOf": [
      {
        "if": { "properties": { "delivery": { "properties": { "transport": { "const": "mcp_stdio" } } } } },
        "then": { "required": ["mcp", "signing"] }
      },
      {
        "if": { "properties": { "direction": { "pattern": "^device_" } } },
        "then": { "required": ["signing"] }
      }
    ]
  }
  ```

  `rate_limit_reserved_v1_1` and `circuit_breaker_reserved_v1_1` are validated by shape but a runtime warning logs "field reserved for v1.1; ignored at runtime" if present in v1 (D18).

- `tooling/contracts/codegen.py`: when transport is `mcp_stdio`, codegen emits a thin generated wrapper that translates the manifest's tool list into typed Python methods on the gateway.
- `bridge/runtime.py`: when constructing the gateway, instantiates `MCPProcessManager` (epic 5.2), `CredentialVault` (epic 5.3); attaches both to `ConnectorGateway`.

**Unit tests:** `tests/bridge/connector/test_gateway_port.py`, `tests/bridge/contracts/_meta/test_ifl_manifest_validation.py`

- `test_ifl_manifest_with_mcp_block_validates_against_meta_schema` — fixture manifest with full `mcp:` block; meta-schema accepts.
- `test_ifl_manifest_missing_signing_when_device_direction_fails` — assert validation error names `signing` as missing required.
- `test_ifl_manifest_with_mcp_stdio_transport_requires_mcp_block` — drop `mcp:` block from fixture; assert validation error.
- `test_ifl_manifest_v1_1_reserved_fields_validated_but_warned` — manifest with `rate_limit:` block; assert validation passes; assert warning logged at `BridgeRuntime.from_registry()` boot.
- `test_connector_gateway_routes_invoke_through_three_stages_in_order` — instrument each stage; assert call order: token → adapter → router.
- `test_connector_gateway_raises_invalid_signature_when_manifest_unsigned` — manifest without `signing.signature`; assert raise at boot, not at invoke.
- `test_connector_gateway_raises_offline_when_adapter_quarantined` — quarantine the adapter via crash-budget exhaustion (mocked process manager); assert `AdapterQuarantinedError` from `invoke`.
- `test_runtime_constructs_gateway_from_registry` — boot `BridgeRuntime.from_registry()` against fixture manifest; assert `runtime.gateway` is non-None and has the right adapter id registered.

**No-mock compliance:** real meta-schema validation, real codegen, real `BridgeRuntime` boot. The 3 stages have real implementations (token verifier checks vault, adapter verifier checks CA bundle, router calls a real subprocess MCP echo server installed for tests).

**Wiring at end of epic:** `runtime.gateway.invoke(adapter_id="...", tool="...", args=...)` is callable end-to-end against an in-tree `tests/fixtures/mcp_servers/echo/` MCP server. No real Google Calendar yet.

**Observability:**

- `bridge.gateway.invoke_total{adapter_id, tool, outcome}` (counter; outcomes = success | denied | offline | quarantined | error)
- `bridge.gateway.invoke_latency_ms_histogram{adapter_id, tool}` — wall-clock from invoke() entry to result.
- `bridge.gateway.<stage>.{passed_total, blocked_total, latency_ms_histogram}` for each of the 3 stages.
- `bridge.gateway.signature_verification_failures_total{adapter_id}`.

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; runbook `docs/runbooks/connector_gateway.md` (boot sequence, manifest validation errors, signature failures, troubleshooting).

### Epic 5.2 — MCP Process Manager + per-OS sandboxing

**Goal:** spawn / supervise / restart / kill MCP child processes; route gateway invokes to the right child over stdio (preferred) or local loopback HTTP; enforce OS-level sandboxing per the manifest's `mcp.sandbox:` block; honor crash budget.

**Decisions pinned by this epic:**

- **stdio transport is default; loopback HTTP is fallback.** stdio is the MCP standard, has per-message framing built in, and avoids opening any port. Loopback HTTP only when the adapter SDK can't speak stdio (e.g. an existing webhook receiver wrapped as MCP).
- **Per-OS sandboxing impls land all three at MS-5 ship.** Even though dev machines may only exercise one platform, CI runs on Linux + macOS + Windows runners and validates the per-OS profile parses + executes against the test echo MCP server.
- **Crash budget = 3 crashes in 60 seconds** → adapter marked `status: quarantined`; the gateway raises `AdapterQuarantinedError` for any further invokes; `/healthz` surfaces the quarantine. Manual `python -m bridge.connector.unquarantine <adapter_id>` after operator review.
- **Process startup timeout = 10s.** If MCP server doesn't respond to initial `mcp/initialize` within 10s, kill + count as crash.
- **Health pings via MCP's standard `mcp/ping`** at the cadence in `manifest.mcp.health.ping_interval_s`.

**Files to create:**

- `bridge/connector/mcp_process_manager.py`:

  ```python
  class MCPProcessManager:
      def __init__(self, *,
                   sandbox_strategy: SandboxStrategy,    # selected per-platform at construction
                   crash_budget: CrashBudget,
                   audit_log: AuditLog) -> None: ...
      async def start(self, manifest: ManifestRecord) -> MCPChild: ...
      async def stop(self, adapter_id: str, *, reason: str) -> None: ...
      async def restart(self, adapter_id: str) -> None: ...
      async def invoke(self, adapter_id: str, request: MCPRequest) -> MCPResponse: ...
      async def health(self, adapter_id: str) -> AdapterHealth: ...
      async def shutdown_all(self) -> None: ...     # called on bridge runtime shutdown
  ```

- `bridge/connector/mcp_child.py`:

  ```python
  class MCPChild:
      pid: int
      adapter_id: str
      transport: MCPTransport     # MCPStdioTransport | MCPLoopbackHttpTransport
      started_at: datetime
      last_ping_ok_at: datetime
      missed_pings: int
      state: Literal["starting", "ready", "draining", "stopped", "crashed", "quarantined"]
  ```

- `bridge/connector/sandbox/__init__.py`: exports `SandboxStrategy` Protocol + factory `sandbox_strategy_for_platform()`.
- `bridge/connector/sandbox/linux.py`:

  ```python
  class SystemdRunSandbox:
      def build_command(self, manifest: ManifestRecord) -> list[str]:
          mem = manifest.mcp.sandbox.memory_max
          cpu = manifest.mcp.sandbox.cpu_quota_percent
          private_net = "yes" if manifest.mcp.sandbox.network == "none" else "no"
          return [
              "systemd-run", "--scope", "--user", "--quiet",
              f"--property=MemoryMax={mem}",
              f"--property=CPUQuota={cpu}%",
              "--property=NoNewPrivileges=yes",
              "--property=ProtectSystem=strict",
              f"--property=PrivateNetwork={private_net}",
              "--", *manifest.mcp.server_command,
          ]
  ```

- `bridge/connector/sandbox/macos.py`: emits `sandbox-exec -f <profile.sb> -- <server_command>`. Profile templates in `bridge/connector/sandbox_profiles/` (`mcp_outbound_only.sb`, `mcp_no_network.sb`, `mcp_full_network.sb`); per-adapter profile is generated by substituting `(allow file-read* (subpath "..."))` lines from `manifest.mcp.sandbox.filesystem_read`.
- `bridge/connector/sandbox/windows.py`: spawns the child inside a Job Object via `pywin32` (`win32job`) with explicit memory/CPU caps + AppContainer SID via `kernel32.CreateProcessAsUser`. The Job Object handle is held by the manager; on manager exit, the Job Object cleans up all child processes automatically (kernel-level guarantee).
- `bridge/connector/sandbox_profiles/mcp_outbound_only.sb`, `mcp_no_network.sb`, `mcp_full_network.sb` — macOS sandbox profile templates.
- `bridge/connector/transport/mcp_stdio.py`: implements MCP JSON-RPC framing over child's stdin/stdout per the [Model Context Protocol spec](https://modelcontextprotocol.io/specification/draft).
- `bridge/connector/transport/mcp_loopback_http.py`: ephemeral port allocator (`socket.bind(('127.0.0.1', 0))`) for loopback HTTP transport; never binds non-loopback.
- `bridge/connector/crash_budget.py`:

  ```python
  class CrashBudget:
      def __init__(self, *, max_crashes: int = 3, window_s: int = 60) -> None: ...
      def record_crash(self, adapter_id: str) -> CrashBudgetResult:  # OK | QUARANTINE
          ...
  ```

- `tests/fixtures/mcp_servers/echo/server.py` — minimal MCP server implementing `mcp/initialize`, `mcp/ping`, and one tool `echo(text: str) -> {"echoed": str}`. Used by every MCP-related test as the trusted adapter.

**Unit tests:** `tests/bridge/connector/test_mcp_process_manager.py`, `tests/bridge/connector/sandbox/test_<platform>_sandbox.py`, `tests/bridge/connector/test_crash_budget.py`

- `test_process_manager_starts_real_echo_mcp_server_and_invokes_echo_tool` — real subprocess spawn; real stdio JSON-RPC; assert tool result.
- `test_process_manager_kills_child_on_shutdown` — start child; call `shutdown_all()`; assert PID is gone within 5s.
- `test_process_manager_handles_initialize_timeout` — fixture MCP server that hangs in initialize; assert kill after 10s + `crashed` state.
- `test_process_manager_health_ping_detects_dead_child` — kill child externally (SIGKILL); assert manager observes 3 missed pings within configured window; transitions to `crashed`; restarts.
- `test_process_manager_quarantines_after_crash_budget_exhausted` — fixture MCP server that exits immediately; trigger 3 crashes within 60s; assert state = `quarantined`; subsequent invoke raises `AdapterQuarantinedError`; assert `bridge.gateway.adapter_quarantined_total{adapter_id}` incremented.
- `test_process_manager_unquarantine_resets_crash_count` — quarantine; call `unquarantine()`; assert state = `stopped`; next start succeeds.
- `test_linux_sandbox_command_constructed_from_manifest` (skip on non-linux): snapshot the constructed `systemd-run` command; assert flags match manifest.
- `test_linux_sandbox_enforces_memory_max` (skip on non-linux): real cgroup; spawn echo MCP that allocates 600MB; assert OOM kill when manifest sets `memory_max: 256M`.
- `test_macos_sandbox_profile_generated_from_manifest` (skip on non-darwin): assert generated `.sb` file contains `(allow file-read* (subpath "/Users/.../allowed_path"))` lines from manifest.
- `test_windows_appcontainer_capability_sids_set` (skip on non-windows): inspect Job Object via `win32job.QueryInformationJobObject`; assert capabilities match manifest.
- `test_loopback_http_transport_never_binds_non_loopback` — assert `socket.getsockname()[0] == "127.0.0.1"`; attempt connect from `0.0.0.0` fails.
- `test_crash_budget_window_is_rolling` — record crash at t=0, t=30, t=58 → 3 within 60s, quarantine; vs t=0, t=30, t=70 → only 2 within trailing 60s, no quarantine.

**No-mock compliance:** real subprocess spawn for all stdio tests; real socket bind for transport tests; real Linux cgroups / macOS sandbox-exec / Windows Job Object on the matching CI runner. Per-OS tests skip gracefully on other platforms (matrix covers all three).

**Wiring at end of epic:** `runtime.gateway.invoke(adapter_id="echo", tool="echo", args={"text": "hi"})` returns `{"echoed": "hi"}` end-to-end through the manager + sandbox + stdio transport against the in-tree echo MCP server, on all three platforms. Crash + quarantine + unquarantine path verified.

**Observability:**

- `bridge.connector.process.{starts_total{adapter_id}, restarts_total{adapter_id}, crashes_total{adapter_id}}`
- `bridge.connector.process.state{adapter_id, state}` (gauge)
- `bridge.connector.process.uptime_seconds{adapter_id}`
- `bridge.connector.process.memory_rss_bytes{adapter_id}`
- `bridge.connector.process.health_ping.{ok_total, missed_total, latency_ms{adapter_id}}`
- `bridge.connector.adapter_quarantined_total{adapter_id, reason}`
- Audit log on every start / stop / crash / quarantine transition.

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; runbook `docs/runbooks/mcp_process_manager.md` (per-OS sandbox config, crash budget tuning, quarantine recovery, debugging an MCP child).

### Epic 5.3 — Credential vault (OS keychain primary + sqlcipher fallback)

**Goal:** durable, encrypted, per-adapter credential storage that the OAuth flow + ongoing token refresh both read from. Vault auto-selects backend at boot per D17.

**Decisions pinned by this epic:**

- **Single-process vault.** Owned by `BridgeRuntime`; passed to MCP Process Manager; MCP children **do not** have direct access — they receive the credential payload at startup via stdio JSON-RPC `mcp/initialize` extension or fetch on demand via a privileged stdio request. This keeps secrets out of `/proc/<pid>/environ` and out of process command-line args.
- **Naming convention** (D17): service = `familyos.adapter.<adapter_id>`; key = `<credential_type>` (e.g. `oauth.refresh_token`, `oauth.access_token`).
- **No remote vault in v1.** v1 → v2 home-K0 vault migration tool stub created (`bridge/connector/vault_migrate.py` with `--from keyring --to home_k0` interface) but the home-K0 backend isn't implemented yet — out of scope.

**Files to create:**

- `requirements.txt`: `keyring==24.*`, `pysqlcipher3==1.2.*` (the latter optional/conditional install for headless environments via `pip install familyos[headless]`).
- `bridge/connector/credential_vault.py`:

  ```python
  class CredentialVault(Protocol):
      async def store(self, *, adapter_id: str, key: str, secret: str | bytes,
                      metadata: dict | None = None) -> None: ...
      async def retrieve(self, *, adapter_id: str, key: str) -> str | bytes: ...
      async def delete(self, *, adapter_id: str, key: str) -> None: ...
      async def rotate(self, *, adapter_id: str, key: str, new_secret: str | bytes) -> None: ...
      async def list_keys(self, *, adapter_id: str) -> list[str]: ...
      async def health_check(self) -> VaultHealth: ...

  class VaultMiss(Exception): ...
  class VaultBackendUnavailable(Exception): ...
  ```

- `bridge/connector/vault/keyring_vault.py`: backend = `keyring` package; service-name pattern from D17.
- `bridge/connector/vault/sqlcipher_vault.py`: SQLite + sqlcipher; key derived from passphrase per D17 logic (env var → operator prompt → fail).
- `bridge/connector/vault/audit_log.py`: append-only file at `~/.familyos/vault_audit.log`; rotated daily; structured JSONL.
- `bridge/connector/vault/factory.py`:

  ```python
  def select_vault() -> CredentialVault:
      forced = os.environ.get("FAMILYOS_VAULT_BACKEND")
      if forced == "sqlcipher":
          return SqlcipherVault.open(...)
      if forced == "keyring":
          return KeyringVault.open()
      try:
          return KeyringVault.open()
      except keyring.errors.NoKeyringError:
          log.warning("OS keyring unavailable — falling back to sqlcipher vault")
          return SqlcipherVault.open(...)
  ```

- `bridge/connector/vault_migrate.py` — stubbed CLI with `--dry-run` + `--from` + `--to`; v1 supports only `--from keyring --to sqlcipher` and reverse (the v1 local backends); home-K0 target raises `NotImplementedError("v2 milestone")`.

**Unit tests:** `tests/bridge/connector/vault/test_keyring_vault.py`, `test_sqlcipher_vault.py`, `test_factory.py`, `test_audit_log.py`, `test_vault_migrate.py`

- `test_keyring_vault_round_trip` (skip on CI runner without keyring backend; runs locally on dev macOS/Win/Linux+SecretService): store + retrieve + delete a real secret in the OS keychain under a `familyos.adapter.test_*` namespace; cleanup in fixture.
- `test_sqlcipher_vault_round_trip_with_real_passphrase` — temp DB, real `pysqlcipher3`, real encryption; assert raw file is encrypted (no plaintext via `grep`).
- `test_sqlcipher_vault_wrong_passphrase_fails_with_clear_error` — open with passphrase A; reopen with passphrase B; assert `VaultBackendUnavailable("invalid_passphrase")`.
- `test_factory_falls_back_to_sqlcipher_when_keyring_unavailable` — patch `keyring.get_keyring` to raise `NoKeyringError`; assert factory returns `SqlcipherVault`.
- `test_factory_honors_env_override` — `FAMILYOS_VAULT_BACKEND=sqlcipher`; assert sqlcipher chosen even when keyring is available.
- `test_audit_log_records_every_retrieve` — issue 5 retrieves; assert log file has 5 JSONL lines with adapter_id, key, caller_pid, timestamp.
- `test_audit_log_does_not_record_secret_value` — retrieve a 200-char secret; grep audit log; assert secret bytes not present.
- `test_audit_log_rotates_daily` — freeze clock; write log on day 1; advance clock 1 day; write log; assert two files present.
- `test_vault_migrate_dry_run_lists_keys_without_writing` — populate keyring with 3 keys; `vault_migrate --dry-run --from keyring --to sqlcipher`; assert no sqlcipher file created.
- `test_vault_migrate_keyring_to_sqlcipher_round_trip` — populate keyring; migrate; assert sqlcipher contains identical secrets; assert original keyring unchanged unless `--delete-source` flag set.
- `test_vault_migrate_to_home_k0_raises_not_implemented_in_v1` — assert `--to home_k0` raises with helpful message pointing to v2 milestone.

**No-mock compliance:** real `keyring` package (skip per-platform tests where backend unavailable on CI); real `pysqlcipher3`; real disk; real audit log file.

**Wiring at end of epic:** `bridge/runtime.py` calls `select_vault()` at boot, holds the instance, passes to `ConnectorGateway` and `MCPProcessManager`. The `connectors/google_calendar/` MCP server (epic 5.5) will read OAuth refresh tokens from the vault on startup.

**Observability:**

- `bridge.vault.{store_total{adapter_id}, retrieve_total{adapter_id}, delete_total{adapter_id}, rotate_total{adapter_id}, miss_total{adapter_id}}`
- `bridge.vault.backend{name}` (gauge, value = 1 for the active backend)
- `bridge.vault.audit_log_writes_total`
- `bridge.vault.health_check_failures_total{backend}`

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; runbook `docs/runbooks/credential_vault.md` covering: backend selection, sqlcipher passphrase setup for headless deploys, audit log rotation, v1 → v2 migration plan.

### Epic 5.4 — D19 ceremony executed; replace CA bundle placeholder

**Goal:** real `familyos_root_v1` Ed25519 keypair generated via the D3 + D19 ceremony; public key replaces `PLACEHOLDER_REPLACE_BEFORE_MS5` in `bridge/contracts/_meta/ca_bundle.json`; private-key Shamir shares physically distributed to the 5 share-holders per D19 governance.

**Pre-conditions:** governance runbook (`docs/runbooks/familyos_root_governance.md`) shipped at MS-2.5 PR#2 already; D7 CODEOWNERS in place so the bundle-update PR requires HoS + bridge-infra lead sign-off.

**Decisions pinned by this epic:**

- **Air-gapped Tails USB session.** Per D3: clean Tails boot, `ssss` package installed offline from verified ISO, Ed25519 keypair generated via `python -c "from nacl.signing import SigningKey; ..."`, private key split via `ssss-split -t 3 -n 5 -s 256` into 5 shares, paper-printed (no network printer), seed shred + power-off without network reconnect.
- **Public key extraction:** the ceremony also writes the base64url-encoded public key to a USB stick (not the same one with the seed); operator carries USB to the PR machine, copies into `ca_bundle.json`, opens PR.
- **Ceremony witnesses:** at least 3 share-holders physically present (the 3 of 5 needed to reconstitute) plus 1 outside auditor (not a share-holder). Audit logs ceremony date, attendees, output public key SHA-256.
- **No CI gate change.** Boot-time validation already verifies the public key parses as a valid Ed25519 32-byte key (D10 code `E_BRIDGE_BOOT_CA_BUNDLE_MISSING` if missing or malformed). After the placeholder is replaced, every existing unit test that exercises signing against `familyos_root_v1` starts working without modification.

**Files to modify:**

- `bridge/contracts/_meta/ca_bundle.json`: replace `"ed25519_public_key": "PLACEHOLDER_REPLACE_BEFORE_MS5"` with the real base64url public key (44 chars).
- `bridge/contracts/_meta/ca_bundle.audit.json` (new): append-only record of CA bundle changes:

  ```json
  {
    "events": [
      {
        "ca_id": "familyos_root_v1",
        "event": "issued",
        "ceremony_date": "2026-MM-DDTHH:MM:SSZ",
        "ceremony_location": "redacted",
        "witnesses_present": 4,
        "share_holders_present": 3,
        "auditor_present": true,
        "public_key_sha256": "<hex>",
        "ledger_entry_id": "<uuid from physical ledger>"
      }
    ]
  }
  ```

  This audit file is **not** the source of truth (the physical ledger held by HoS is); it's a machine-readable mirror to enable CI cross-checks (e.g. assert public_key in `ca_bundle.json` matches the SHA-256 in the latest audit event).

- `tooling/ci/gates/ca_bundle_audit_consistency.py` (new gate): assert every `ed25519_public_key` in `ca_bundle.json` has a matching `event: issued` entry in `ca_bundle.audit.json` whose SHA matches. Catches the "someone updated the bundle without the audit trail" failure mode.

**Unit tests:** `tests/bridge/contracts/_meta/test_ca_bundle_real_key.py`, `tests/tooling/ci/test_ca_bundle_audit_consistency.py`

- `test_ca_bundle_familyos_root_v1_is_valid_ed25519_public_key` — load bundle; assert key parses as `nacl.signing.VerifyKey`; assert length = 32 bytes after base64url decode.
- `test_ca_bundle_familyos_root_v1_is_not_placeholder` — assert key != literal `"PLACEHOLDER_REPLACE_BEFORE_MS5"`.
- `test_signed_fixture_ifl_manifest_verifies_against_real_key` — load `tests/fixtures/ifl_manifests/test_adapter_signed.yaml` (signed at ceremony with the real private key, signature pre-committed to the fixture); assert verification passes.
- `test_signed_fixture_ifl_manifest_fails_with_tampered_payload` — flip one byte in the manifest body; assert verification fails.
- `test_audit_consistency_gate_passes_when_bundle_and_audit_match`.
- `test_audit_consistency_gate_fails_when_bundle_updated_without_audit_event`.

**No-mock compliance:** real Ed25519 verification via `pynacl`. The test fixtures are signed by the real ceremony private key one time during the ceremony; thereafter only the public key + signed fixtures live in the repo.

**Wiring at end of epic:** every IFL manifest (epic 5.5) signed with `familyos_root_v1` verifies against the real bundle on every boot. The pre-MS-5 `BridgeBootError` for `E_BRIDGE_BOOT_CA_BUNDLE_MISSING` (which fired on every dev environment because of the placeholder) stops firing.

**Observability:**

- `bridge.boot.ca_bundle_loaded{ca_id}` (gauge)
- `bridge.signing.verify_total{ca_id, outcome}` (counter)

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log: "MS-5 PR#4 — CA bundle ceremony executed; `familyos_root_v1` real key in bundle"; `docs/runbooks/familyos_root_governance.md` ceremony log section appended with the date + ledger entry id (no PII).

### Epic 5.5 — Google Calendar (read-only) MCP adapter + K0 IFL ingestion

**Goal:** the v1 reference adapter. Real OAuth 2.0 device flow per Google's documented protocol; refresh token persisted in the credential vault (epic 5.3); MCP server in-tree at `connectors/google_calendar/`; one tool `list_events(calendar_id, time_min, time_max)`; results ingested to K0 P-IFL pipeline as `MemoryAtom` with `kind: calendar_event`.

**Decisions pinned by this epic:**

- **Read-only scope:** `https://www.googleapis.com/auth/calendar.readonly`. Write scopes explicitly excluded from manifest; MCP tool surface excludes any mutating tool.
- **Device flow** (`urn:ietf:wg:oauth:2.0:device-flow:device_code`): user runs `python -m connectors.google_calendar.consent --calendar-account=father@gmail.com`; CLI prints user_code + verification URL; user opens on phone, types code; CLI polls Google `/token` endpoint until consent granted; refresh token stored in vault as `familyos.adapter.google_calendar_<account_id>` / `oauth.refresh_token`.
- **Per-account adapter instances.** The manifest is parameterized: `adapter_id_pattern: google_calendar_<account_id>`. One MCP child process per Google account (so Father's Calendar and Mother's Calendar run in two child processes, each with its own credential context). The MCP Process Manager handles this fan-out via the manifest's `multi_instance: true` flag (additive schema field, lands here).
- **K0 P-IFL ingestion:** results from `list_events` are ingested as `MemoryAtom` per [k0/contracts/jsonschema/topics/memory_write.body.json](k0/contracts/jsonschema/topics/memory_write.body.json) chained to `MemoryAtom v2.2` (subtype `calendar_event`). De-dupe key = `(account_id, event_id, etag)`. K0 IFL storage tables (`st_ifl_adapter_registry`, `st_ifl_credentials_metadata` — note: only metadata, not secrets; secrets stay in the K1 vault per D17, `st_ifl_manifests`, `st_ifl_events`) created by migration.
- **Recorded HTTP fixtures for CI.** `tests/fixtures/google_calendar/recorded_responses/*.json` captured once via real account, replayed in CI via VCR-style fixture (`pytest-recording`). Eliminates Google API rate-limit risk in CI; preserves "no mocks for our code" — Google's API surface is a 3rd-party network boundary, which the MS-5 carve-out in the no-mock rule explicitly permits.

**Files to create:**

- `bridge/contracts/manifests/ifl.google_calendar.events.list.v1.yaml`:

  ```yaml
  topic: ifl.google_calendar.events.list.v1
  status: active
  direction: device_to_k0
  delivery:
    transport: mcp_stdio
    codec: json
    timeout_ms: 5000
    max_queue_age: 5m
  mcp:
    server_command: ["python", "-m", "connectors.google_calendar.server"]
    multi_instance: true
    sandbox:
      memory_max: 256M
      cpu_quota_percent: 25
      network: outbound_only
      filesystem_read: ["~/.familyos/credentials/google_calendar/"]
      filesystem_write: []
    health:
      ping_interval_s: 10
      max_missed_pings: 3
  signing:
    ca_id: familyos_root_v1
    signature: <base64url-ed25519 signature of canonical manifest minus this field>
  semantics:
    description: >
      Read-only Google Calendar events list. Returns events between time_min and
      time_max for one calendar_id. Idempotent; no side effects on Google side.
      Timezone in result is UTC; caller must convert for display. Duplicate calls
      with same args within 60s are deduped at the gateway level.
    idempotent: true
    duplicate_strategy: dedupe_by_args_within_60s
  versioning:
    strategy: additive_only_within_v1
    breaking_change_requires: new_topic_v2_with_dual_publish_window_30d
  rate_limit:                       # reserved for v1.1
    requests_per_minute: 60
    burst: 10
  circuit_breaker:                  # reserved for v1.1
    failure_threshold: 5
    timeout_s: 60
    half_open_probes: 1
  ```

- `bridge/contracts/schemas/ifl.google_calendar.events.list.v1.request.json` — `{calendar_id, time_min, time_max, page_token?, max_results?}`.
- `bridge/contracts/schemas/ifl.google_calendar.events.list.v1.response.json` — `{events: [...], next_page_token?}` mirroring Google's payload shape verbatim (we don't transform here; transformation happens in the K0 P-IFL ingestion).
- `connectors/google_calendar/__init__.py`
- `connectors/google_calendar/server.py` — MCP server entry point. Uses `mcp` Python SDK (add to requirements): `mcp==1.0.*`. Implements `mcp/initialize`, `mcp/ping`, and one tool `list_events`. On startup, pulls OAuth refresh token from vault via stdio JSON-RPC privileged request to the parent (vault is in K1 process, not in the child).
- `connectors/google_calendar/oauth.py` — device flow + refresh-token exchange via `google-auth==2.*`, `google-auth-oauthlib==1.*`, `google-api-python-client==2.*`.
- `connectors/google_calendar/consent.py` — CLI tool `python -m connectors.google_calendar.consent --account=<email>` that runs the device flow interactively and writes the refresh token to the vault.
- `connectors/google_calendar/manifest.signature` (or inline in YAML) — the ed25519 signature over the canonical manifest minus the signature field. Generated at the D19 ceremony or by a permitted maintainer holding the private key recombined under ceremony.
- `k0/migrations/<timestamp>_st_ifl_tables.sql`:

  ```sql
  CREATE TABLE st_ifl_adapter_registry (
      adapter_id            TEXT PRIMARY KEY,
      manifest_topic        TEXT NOT NULL,
      manifest_signature    TEXT NOT NULL,
      ca_id                 TEXT NOT NULL,
      registered_at         TIMESTAMP NOT NULL,
      status                TEXT NOT NULL DEFAULT 'active',  -- active | quarantined | revoked
      multi_instance_account_id TEXT
  );
  CREATE TABLE st_ifl_credentials_metadata (
      adapter_id            TEXT NOT NULL,
      key                   TEXT NOT NULL,
      created_at            TIMESTAMP NOT NULL,
      last_rotated_at       TIMESTAMP,
      vault_backend         TEXT NOT NULL,
      PRIMARY KEY (adapter_id, key)
  );
  CREATE TABLE st_ifl_manifests (
      topic                 TEXT NOT NULL,
      version               INTEGER NOT NULL,
      manifest_yaml         TEXT NOT NULL,
      signature             TEXT NOT NULL,
      registered_at         TIMESTAMP NOT NULL,
      PRIMARY KEY (topic, version)
  );
  CREATE TABLE st_ifl_events (
      event_id              TEXT PRIMARY KEY,
      adapter_id            TEXT NOT NULL,
      tool                  TEXT NOT NULL,
      args_hash             TEXT NOT NULL,
      response_etag         TEXT,
      ingested_at           TIMESTAMP NOT NULL,
      memory_atom_id        TEXT,
      INDEX (adapter_id, tool, ingested_at)
  );
  ```

- `k0/pipelines/p_ifl/google_calendar_normalizer.py` — converts Google's event payload to `MemoryAtom v2.2` with `kind: calendar_event`; populates 14 required fields per the schema chain.
- `k0/pipelines/p_ifl/ingest.py` — entry point that the K0 IFL receiver calls; orchestrates dedupe + normalize + persist.
- `requirements.txt`: `mcp==1.0.*`, `google-auth==2.*`, `google-auth-oauthlib==1.*`, `google-api-python-client==2.*`, `pytest-recording==0.13.*` (test-only).

**Unit tests:** `tests/connectors/google_calendar/test_server.py`, `test_oauth.py`, `test_consent_flow.py`; `tests/bridge/integration/test_google_calendar_e2e.py`; `tests/k0/pipelines/p_ifl/test_google_calendar_normalizer.py`

- `test_mcp_server_responds_to_initialize` — spawn `connectors.google_calendar.server` as subprocess; assert handshake completes.
- `test_mcp_server_lists_one_tool_named_list_events` — MCP `tools/list` returns single `list_events` descriptor with correct schema.
- `test_oauth_device_flow_persists_refresh_token_to_vault` (uses `pytest-recording`): replay recorded device-flow + token-exchange responses; assert vault contains `oauth.refresh_token` for `familyos.adapter.google_calendar_test`.
- `test_oauth_refresh_token_exchange` (uses recorded fixture): given a refresh token, exchange for access token; assert success.
- `test_list_events_calls_google_api_with_correct_query_params` (recorded): assert outbound URL has `timeMin`, `timeMax`, `singleEvents=true`, `orderBy=startTime`.
- `test_list_events_normalizes_to_memory_atom_v2_2` — feed recorded Google payload to `google_calendar_normalizer.py`; assert all 14 required `MemoryAtom v2.2` fields populated; assert `kind: calendar_event`; assert `etag` carried through.
- `test_dedupe_by_etag_in_st_ifl_events` — ingest same event twice with same etag; assert one row in `st_ifl_events`; second call no-ops at the dedupe layer.
- `test_full_pipeline_k1_invoke_to_k0_memory_atom` — boot K0, K1 runtime, gateway, MCP child; invoke `runtime.gateway.invoke(adapter_id="google_calendar_test", tool="list_events", args=...)`; assert returns recorded events; assert K0 has `MemoryAtom` rows for them; assert audit log entries.
- `test_multi_instance_two_accounts_run_in_separate_mcp_children` — start two MCP children for `google_calendar_father` + `google_calendar_mother`; assert two PIDs; invoke each; assert isolation (each retrieves only its own credentials from vault).
- `test_offline_invoke_raises_offline_adapter_error` — drop network namespace via Linux `unshare -n`; invoke; assert `OfflineAdapterError`; vault read still succeeds (vault is local).

**No-mock compliance:** real `mcp` SDK, real Google OAuth library, real subprocess, real K0 pipeline, real PostgreSQL/SQLite, real vault backend. Network calls to Google replayed via `pytest-recording` per the MS-5 carve-out for 3rd-party services.

**Wiring at end of epic:** Google Calendar end-to-end works against any consented family member's calendar. K1 fabric → bridge gateway → MCP child → Google → response → K0 P-IFL ingest → `st_ifl_events` + `MemoryAtom`.

**Observability:**

- `ifl.google_calendar.invoke_total{account_id, tool, outcome}`
- `ifl.google_calendar.invoke_latency_ms_histogram{account_id, tool}`
- `ifl.google_calendar.events_ingested_total{account_id}`
- `ifl.google_calendar.events_deduped_total{account_id}`
- `ifl.google_calendar.oauth_refresh_total{account_id, outcome}`
- `ifl.google_calendar.api_quota_warnings_total{account_id}` (Google returns rate-limit warnings even before erroring; surface them so v1.1 rate-limiter has data)

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; runbook `docs/runbooks/google_calendar_adapter.md` (consent flow, troubleshooting "events not showing up", revoking access, multi-account management).

### Epic 5.6 — MS-5 EXIT CRITERION

**Goal:** named test proves the v1 IFL surface is real end-to-end with the headline use case ("does the family have a free Saturday?").

**Files to create:**

- `tests/bridge/integration/test_ms5_exit.py`:

  ```python
  @pytest.mark.integration
  @pytest.mark.recording
  async def test_ifl_google_calendar_events_list_round_trips_via_gateway(
      tmp_path, free_port, recorded_google_calendar_session,
  ):
      # Boot K0 with IFL pipeline + IFL storage migrations applied
      k0_proc = await spawn_k0_server(
          port=free_port, db_path=tmp_path / "k0.db",
          enable_pipelines=["p_ifl"], apply_migrations=True,
      )
      try:
          # Pre-stage two consented family accounts in the test vault
          vault = SqlcipherVault.open(tmp_path / "vault.db", passphrase="test")
          await vault.store(adapter_id="google_calendar_father", key="oauth.refresh_token",
                            secret=recorded_google_calendar_session["father_refresh_token"])
          await vault.store(adapter_id="google_calendar_mother", key="oauth.refresh_token",
                            secret=recorded_google_calendar_session["mother_refresh_token"])

          # Boot K1 runtime with gateway constructed from registry
          runtime = await BridgeRuntime.from_registry(
              role="k1", k0_url=f"http://127.0.0.1:{free_port}",
              vault_override=vault,
              vault_backend_env="sqlcipher",
          )
          assert runtime.gateway is not None

          # Invoke list_events for both family members
          father_events = await runtime.gateway.invoke(
              adapter_id="google_calendar_father", tool="list_events",
              args={"calendar_id": "primary",
                    "time_min": "2026-05-09T00:00:00Z",
                    "time_max": "2026-05-09T23:59:59Z"},
              caller=ConnectorCaller(person_id="father", session_id="..."),
          )
          mother_events = await runtime.gateway.invoke(
              adapter_id="google_calendar_mother", tool="list_events",
              args={"calendar_id": "primary",
                    "time_min": "2026-05-09T00:00:00Z",
                    "time_max": "2026-05-09T23:59:59Z"},
              caller=ConnectorCaller(person_id="mother", session_id="..."),
          )

          # Assert recorded fixture events came through
          assert len(father_events.payload["events"]) == 2
          assert len(mother_events.payload["events"]) == 1

          # Assert K0 ingested them as MemoryAtoms
          atoms = await k0_query(f"http://127.0.0.1:{free_port}",
                                 "SELECT * FROM memory_atoms WHERE kind='calendar_event'")
          assert len(atoms) == 3   # 2 father + 1 mother

          # Assert the dedupe table has the right etag rows
          ifl_events = await k0_query(f"http://127.0.0.1:{free_port}",
                                      "SELECT * FROM st_ifl_events ORDER BY ingested_at")
          assert len(ifl_events) == 3

          # Assert MCP children running with correct sandbox: 2 PIDs, network outbound_only
          children = runtime.gateway._process_manager._children
          assert len(children) == 2
          for child in children.values():
              assert child.state == "ready"
              assert child.transport.kind == "stdio"

          # Assert audit log captured each invoke with correct caller
          audit_lines = (tmp_path / "audit.log").read_text().splitlines()
          assert any("google_calendar_father" in l and "list_events" in l for l in audit_lines)
          assert any("google_calendar_mother" in l and "list_events" in l for l in audit_lines)
      finally:
          await runtime.shutdown()
          await k0_proc.terminate()
  ```

- Update `bridge/contracts/_meta/feature_flags.yaml`: remove MS-5 flags (`ifl_gateway_enabled`, `mcp_process_manager_enabled`, `google_calendar_adapter_enabled`).
- Update [bridge_system_design.md](bridge_system_design.md) iteration log: "MS-5 closed; IFL minimum live; Google Calendar read-only adapter end-to-end via MCP Process Manager + OS sandbox + OS keychain vault; CA bundle ceremony executed".

**Unit tests:** the exit test IS the test.

**No-mock compliance:** real K0 + real K1 runtime + real MCP process + real vault + real Google API replayed via recorded fixtures (carve-out per global rule 1).

**Wiring at end of milestone:** FamilyOS can read external state. The "free Saturday?" query is answerable. Every component the IFL contract registry promised — gateway, MCP runtime, sandboxing, vault, signed manifests — is real, tested, and producing observability.

**Exit test:** `test_ifl_google_calendar_events_list_round_trips_via_gateway` — green ⇒ MS-5 shipped, MS-6 unblocks.

---

## MS-6 — LAN device sync (mDNS + LWW CRDT, intra-person L3) — POST-V1, DEFERRED

**Status reminder:** per [bridge_system_design.md](bridge_system_design.md) §"Three sync layers", L3 (intra-person device coherence — Father's iPhone ↔ Father's Laptop on the same WiFi) is **deferred post-v1**. The v1 ground truth is single-device-per-person; multi-device coherence round-trips through person-K0. This milestone is included in the plan because (a) the existing LAN-mesh code in [ADR-0050c-lan](../../decisions-K1/06-layer5-infrastructure/0050-multi-device-family-sync-strategy/0050c-lan-first-sync-implementation.md) is already complete and just needs rescoping, (b) the "second device per person" UX is the canonical v1.5 unlock, (c) the L3 surface must be designed alongside L1/L2 to share the same CRDT engine, E2EE primitives, and identity model.

**Sequencing call:** if scope pressure forces a cut, MS-6 is the most defensible deferral — the v1 product works without it. Recommend treating MS-6 as the v1.1 / v1.5 milestone; MS-7 (integration testing) and MS-8 (chaos testing) ship before MS-6 in calendar order if necessary.

**Unlocks:** Father starts a session on his phone, picks up on his laptop seamlessly without round-tripping K0; UX continuity within one person.

**Pre-conditions:** MS-5 green (IFL up). MS-6 does not have a hard dependency on MS-5 internals, but the gateway-side `IConnectorGatewayPort` and MCP Process Manager establish the pattern for adding new bridge subsystems behind ports — MS-6 follows the same pattern for `ISyncPort`.

**Wiring at exit:**

- mDNS service `_familyos-{person_id}._tcp.local` advertised on every K1 device (publishing) and discovered by every other K1 device of the same person.
- TCP port 9000 (existing port from ADR-0050c) hosts the LWW CRDT delta protocol.
- E2EE handshake (X25519 ECDH + AES256-GCM session keys) on every fresh peer pairing; per-person device certificates (Ed25519) signed by the person's K0 identity key during pairing.
- ADR-0050a SessionState coherence guarantees met: read-your-writes ≤5ms within a peer; bounded-staleness ≤250ms across peers on the same WiFi.

### Epic 6.1 — `ISyncPort` + L3 manifests + scope rebound

**Goal:** the bridge sync surface is a port the same way the other 6 ports are; L3 manifests live in the registry; existing `bridge.sync.local_outbox` (the MS-2.5 wall violation we deleted in MS-4) is unrelated to L3 and stays out of K1 surfaces.

**Decisions pinned by this epic:**

- **L3 unit = `device_id` within one `person_id`.** Original ADR-0050 had cross-person L3; this milestone rescopes it to intra-person only (per [bridge_system_design.md](bridge_system_design.md) §"L3 SessionState sync — defer"). Cross-person sync is L1/L2 (out of MS-6 scope; lives in a separate "Family Fabric" milestone outside this plan).
- **Topics in registry as `direction: k1_to_k1`, `sync.layer: l3_intra_person_devices`.** Meta-schema additive: extend the `sync.layer` enum with `l3_intra_person_devices`; require `sync.layer` when `direction == k1_to_k1` (already required when direction in {k0_to_k0, k1_to_k1} per MS-2.5 meta-schema).
- **`status: deferred` on every L3 manifest at MS-5 ship; flipped to `status: active` at MS-6 ship.** Until MS-6 ships, K1 boot ignores `status: deferred` manifests so they don't generate clients or block boot.

**Files to create:**

- `bridge/ports/sync_port.py`:

  ```python
  class ISyncPort(Protocol):
      async def publish_delta(self, *, topic: str, delta: Delta, scope: SyncScope) -> SyncResult: ...
      async def subscribe(self, *, topic: str, on_delta: Callable[[Delta], Awaitable[None]]) -> SyncSubscription: ...
      async def peers(self, *, scope: SyncScope) -> list[PeerDescriptor]: ...
      async def health(self) -> SyncHealth: ...
  ```

- `bridge/contracts/manifests/k0bridge.p07.delta.v1.yaml` (`status: deferred` until MS-6):

  ```yaml
  topic: k0bridge.p07.delta.v1
  status: deferred
  direction: k1_to_k1
  sync:
    layer: l3_intra_person_devices
    conflict_strategy: lww_with_alphabetical_device_id_tiebreaker
    causal_chain: vector_clock
  delivery:
    transport: e2ee_lan
    codec: msgpack
    timeout_ms: 200
  signing:
    ca_id: person_k0_identity      # signed by person-K0 device cert during handshake
  semantics:
    description: >
      Intra-person device-to-device CRDT delta for the per-person SessionState.
      LWW with vector clocks; alphabetical device_id tiebreaker. Idempotent;
      duplicate deltas (same vclock + payload hash) deduped at receiver.
    idempotent: true
    duplicate_strategy: dedupe_by_vclock_and_payload_hash
  ```

- `bridge/contracts/manifests/device.handshake.v1.yaml` (`status: deferred` until MS-6) — `direction: k1_to_k1`, `sync.layer: l3_intra_person_devices`, carries the X25519 public key + device certificate exchange.
- `bridge/contracts/_meta/manifest.schema.json`: extend `sync.layer` enum:

  ```json
  "layer": { "enum": ["l1_family_memory", "l2_family_tool_state", "l3_intra_person_devices"] }
  ```

- `bridge/sync/__init__.py`: re-export `ISyncPort` + concrete `LANSyncEngine`.

**Unit tests:** `tests/bridge/contracts/test_l3_manifests.py`, `tests/bridge/ports/test_sync_port_protocol.py`

- `test_l3_manifest_validates_with_l3_intra_person_devices_layer` — fixture manifest; meta-schema accepts.
- `test_l3_manifest_requires_sync_block_when_direction_k1_to_k1` — drop `sync` block; assert validation error.
- `test_status_deferred_manifests_skipped_at_boot` — boot runtime against fixture registry containing a `status: deferred` manifest; assert no generated client emitted; assert no boot warning.
- `test_isync_port_protocol_shape` — assert `ISyncPort` has the 4 expected methods with the right signatures.

**No-mock compliance:** real meta-schema, real codegen, real boot.

**Wiring at end of epic:** `runtime.sync` slot exists but raises `NotImplementedError("L3 sync not enabled until MS-6")` unless feature flag flipped. No behavioural change for v1 production.

**Observability:** none new yet; the engine ships in epics 6.2–6.4.

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; cross-link [ADR-0050a](../../decisions-K1/06-layer5-infrastructure/0050-multi-device-family-sync-strategy/0050a-sessionstate-coherence-guarantees.md) for the coherence SLAs MS-6 must meet.

### Epic 6.2 — mDNS scanner + DeviceRegistry

**Goal:** every K1 device on the same LAN discovers every other K1 device of the same person within 5 seconds; the discovery surface feeds a `DeviceRegistry` that the sync engine queries for active peers.

**Decisions pinned by this epic:**

- **Service name format** (from ADR-0050c, kept verbatim): `_familyos-{person_id}._tcp.local`. Per-person scoping means devices for different persons on the same WiFi can't see each other's mDNS announcements (privacy + clean separation; one device may participate in multiple persons' service names if it's a shared device, e.g. living-room tablet — out of v1 scope).
- **TXT records** carry: `device_id`, `device_kind` (phone | laptop | tablet | desktop), `protocol_version`, `cert_fingerprint`. Cert fingerprint is the public-key SHA-256 used for E2EE pairing (epic 6.4); receivers verify against pre-paired devices.
- **Library:** `zeroconf==0.131.*` (mature, asyncio-native via `aioconfigure`, real cross-platform mDNS, used by HomeAssistant — battle-tested).
- **Re-announce cadence:** every 30s (zeroconf default) + on network change events (SIGUSR-style detection via OS-specific hook).
- **Scope:** intra-WiFi only. mDNS doesn't cross subnets; this is by design — cross-network device sync needs the v2 home-K0 + WAN sync, out of scope.

**Files to create:**

- `requirements.txt`: `zeroconf==0.131.*`.
- `bridge/sync/mdns_scanner.py`:

  ```python
  class MDNSScanner:
      def __init__(self, *, person_id: str, device_id: str, device_kind: str,
                   port: int = 9000, on_peer_added: Callable, on_peer_removed: Callable) -> None: ...
      async def start(self) -> None: ...        # advertises self + listens for peers
      async def stop(self) -> None: ...
      async def force_refresh(self) -> None: ...   # called on network change events
  ```

- `bridge/sync/device_registry.py`:

  ```python
  class DeviceRegistry:
      def add_peer(self, peer: PeerDescriptor) -> None: ...
      def remove_peer(self, device_id: str) -> None: ...
      def list_peers(self, *, person_id: str | None = None) -> list[PeerDescriptor]: ...
      def get_peer(self, device_id: str) -> PeerDescriptor | None: ...
  ```

- `bridge/sync/peer_descriptor.py`:

  ```python
  @dataclass(frozen=True)
  class PeerDescriptor:
      device_id: str
      person_id: str
      device_kind: Literal["phone", "laptop", "tablet", "desktop"]
      ip: str
      port: int
      cert_fingerprint: str
      first_seen_at: datetime
      last_seen_at: datetime
  ```

- `bridge/sync/network_change_listener.py`: per-OS hook for "WiFi network changed" — Linux via `pyroute2` netlink monitor, macOS via `SCDynamicStore` callback, Windows via `WinINet` event. On change, calls `MDNSScanner.force_refresh()`.

**Unit tests:** `tests/bridge/sync/test_mdns_scanner.py`, `test_device_registry.py`, `test_network_change_listener.py`

- `test_two_processes_on_loopback_discover_each_other_within_5s` — spawn two `MDNSScanner` instances bound to loopback with same person_id; assert both `on_peer_added` callbacks fire within 5s.
- `test_different_person_ids_do_not_discover_each_other` — spawn two scanners with different person_ids; wait 10s; assert neither callback fires.
- `test_peer_removed_on_scanner_stop` — start two; stop one; assert remaining scanner gets `on_peer_removed` within 30s (mDNS TTL).
- `test_txt_records_carry_device_metadata` — assert the announced TXT record has `device_id`, `device_kind`, `cert_fingerprint`.
- `test_force_refresh_re_announces_immediately` — call `force_refresh`; observe new announcement on the wire within 1s (vs default 30s cadence).
- `test_device_registry_dedupes_same_device_id` — add same peer twice; assert single entry; `last_seen_at` updated.
- `test_device_registry_returns_only_same_person_peers_when_filtered` — populate with 3 person-A peers + 2 person-B peers; query for person-A; assert 3 returned.
- `test_network_change_listener_calls_force_refresh_on_simulated_event` (per-OS, skip on others): trigger synthetic network change; assert callback within 2s.

**No-mock compliance:** real `zeroconf` library on real loopback. Per-OS network-change tests run on the matching CI runner.

**Wiring at end of epic:** `MDNSScanner` populates `DeviceRegistry`; sync engine (epic 6.3) queries `DeviceRegistry.list_peers(person_id=...)` to know who to push deltas to.

**Observability:**

- `bridge.sync.mdns.{peers_seen_total, peers_lost_total, announcements_total, force_refreshes_total}`
- `bridge.sync.device_registry.size{person_id}` (gauge)
- `bridge.sync.network_change_total{event}` (counter)

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; runbook `docs/runbooks/lan_device_discovery.md` (firewall settings, mDNS troubleshooting, multi-WiFi behaviour).

### Epic 6.3 — LWW CRDT + vector clocks (lifted from ADR-0050b, rescoped to device_id)

**Goal:** the conflict-resolution engine that lets two K1 devices accept independent writes to the same SessionState section and converge deterministically when they reconnect. Math + wire format lifted intact from [ADR-0050b](../../decisions-K1/06-layer5-infrastructure/0050-multi-device-family-sync-strategy/0050b-crdt-device-to-device-merge.md); only the unit changes from `device_id` (which 0050b already had) confirms scope.

**Decisions pinned by this epic:**

- **Conflict strategy = LWW with alphabetical device_id tiebreaker.** Wall-clock timestamp from the writing device wins; ties broken by lexicographic comparison of `device_id`. Both devices have the same `person_id` so the tiebreaker is on stable globally-unique device ids.
- **Causal chain = vector clocks.** Each SessionState section has an associated `VectorClock(device_id -> counter)`. Increments on every local write; merged on every received delta. Vector clock divergence is the test for "have these two devices been independently writing while disconnected".
- **CRDT scope = SessionState sections only.** Per ADR-0017, SessionState has 6 sections; each is independently CRDT-merged. Other K1 state (memory atoms, etc.) round-trips K0 — NOT replicated peer-to-peer.
- **Wire format = msgpack.** Aligns with MS-4 codec choice; per ADR-0050b table the FlatBuffers shape was the original choice but msgpack is sufficient at L3 message volumes (<100 deltas/sec/peer typical) and avoids the FlatBuffers schema build step.

**Files to create:**

- `bridge/sync/crdt/__init__.py`
- `bridge/sync/crdt/vector_clock.py`:

  ```python
  @dataclass
  class VectorClock:
      counters: dict[str, int]              # device_id -> counter
      def increment(self, device_id: str) -> None: ...
      def merge(self, other: "VectorClock") -> None: ...
      def compare(self, other: "VectorClock") -> Literal["before", "after", "concurrent", "equal"]: ...
      def to_msgpack(self) -> bytes: ...
      @classmethod
      def from_msgpack(cls, raw: bytes) -> "VectorClock": ...
  ```

- `bridge/sync/crdt/lww_register.py`: per-key LWW register with timestamp + device_id tiebreaker.
- `bridge/sync/crdt/session_state_crdt.py`: composes `LWWRegister` per SessionState section (the 6 from ADR-0017).
- `bridge/sync/crdt/delta.py`:

  ```python
  @dataclass(frozen=True)
  class Delta:
      delta_id: str                         # ULID
      origin_device_id: str
      origin_person_id: str
      vclock: VectorClock
      section: str                          # which SessionState section
      operations: list[CRDTOp]              # set | delete | merge ops
      payload_hash: str                     # for receiver-side dedupe
      created_at: datetime                  # wall-clock from origin
  ```

- `bridge/sync/crdt/merge_engine.py`:

  ```python
  class CRDTMergeEngine:
      def apply_local_write(self, section: str, key: str, value: Any) -> Delta: ...
      def receive_remote_delta(self, delta: Delta) -> MergeResult: ...
      def snapshot(self, section: str) -> dict[str, Any]: ...
  ```

**Unit tests:** `tests/bridge/sync/crdt/test_vector_clock.py`, `test_lww_register.py`, `test_session_state_crdt.py`, `test_merge_engine.py`

- `test_vector_clock_compare_identifies_before_after_concurrent_equal` — fixture cases for each.
- `test_vector_clock_merge_takes_max_per_device` — VC1 = {A:3, B:2}, VC2 = {A:2, B:5}; merge → {A:3, B:5}.
- `test_vector_clock_round_trip_msgpack` — encode + decode preserves counters.
- `test_lww_register_later_timestamp_wins` — write at t=1, then write at t=2; assert t=2 value.
- `test_lww_register_alphabetical_device_id_breaks_tie` — same timestamp, device "alpha" + device "beta"; assert "beta" wins (lexicographically greater).
- `test_concurrent_writes_to_same_key_resolve_deterministically` — devices A and B both write at clock=10 (concurrent vclock); assert both nodes resolve to same final value after exchange.
- `test_three_way_partition_heal_converges` — 3 devices, all partitioned, each writes; pair-wise reconnect in arbitrary order; assert all 3 converge to same state.
- `test_dedupe_by_payload_hash_on_repeat_delta` — apply same delta twice; second is no-op; `MergeResult.duplicate=True`.
- `test_session_state_six_sections_independently_merged` — write to section 1 + section 4; assert merge applies independently; sections 2/3/5/6 untouched.
- `test_merge_engine_emits_delta_on_local_write` — apply local write; assert delta emitted with vclock incremented on local device only.

**No-mock compliance:** pure Python, deterministic; real msgpack codec from MS-4.

**Wiring at end of epic:** sync port has the conflict-resolution math; doesn't yet talk over wire (epic 6.4).

**Observability:**

- `bridge.sync.crdt.{local_writes_total, remote_deltas_received_total, conflicts_resolved_total{strategy}, duplicates_dropped_total}`
- `bridge.sync.crdt.vclock_divergence_max{section}` (gauge — max counter delta across known peers; high values indicate long-lived partition)

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; cross-link ADR-0050b for the formal CRDT proof; runbook `docs/runbooks/crdt_conflicts.md`.

### Epic 6.4 — E2EE (X25519 ECDH + AES256-GCM) + DeviceCertificate pairing

**Goal:** every byte that crosses the LAN is encrypted with a per-pair session key derived via X25519 ECDH; devices authenticate via Ed25519 device certificates signed by the person's K0 identity key during a one-time pairing flow (6-digit code, like Signal-style safety numbers).

**Decisions pinned by this epic:**

- **Crypto choices** (per [bridge_system_design.md](bridge_system_design.md) §"Reusable verbatim"): Ed25519 for device identity + cert signing, X25519 for ECDH, AES256-GCM for symmetric encryption, ChaCha20-Poly1305 reserved for cipher-suite negotiation in v1.5+. Library: `pynacl` (already in tree from MS-2.5 envelope signing).
- **Pairing flow:** new device installs FamilyOS, generates Ed25519 keypair locally, computes 6-digit code from public-key fingerprint (BIP39-style words optional for accessibility); user types code on a previously-paired device of the same person; that device signs the new device's certificate with its K0-identity-signed cert chain; new device receives the signed cert via short-lived QR or out-of-band channel.
- **No K0 round-trip required for pairing.** Pairing happens entirely on the LAN once at least one device of the person has been bootstrapped with the K0 identity (initial bootstrap does require K0).
- **Session key cadence:** new ECDH session key per (peer-pair, mDNS-rediscovery-event); session keys rotate every 24h or on rediscovery, whichever comes first.
- **No PFS in v1.** AES-GCM + ECDH gives forward secrecy at the session level only; long-term device keys can decrypt past sessions if compromised. Acceptable for L3 (intra-person devices); revisit if cross-person L1/L2 ever uses this code path.

**Files to create:**

- `bridge/security/__init__.py`
- `bridge/security/e2ee_engine.py`:

  ```python
  class E2EEEngine:
      def __init__(self, *, my_device_key: SigningKey, my_x25519_key: PrivateKey,
                   cert_manager: CertManager) -> None: ...
      def begin_session(self, peer: PeerDescriptor) -> SessionKey: ...
      def encrypt(self, session: SessionKey, plaintext: bytes) -> bytes: ...
      def decrypt(self, session: SessionKey, ciphertext: bytes) -> bytes: ...
      def rotate_session(self, peer: PeerDescriptor) -> SessionKey: ...
  ```

- `bridge/security/cert_manager.py`:

  ```python
  class CertManager:
      def __init__(self, *, my_k0_identity_pub: bytes, my_device_cert: DeviceCertificate) -> None: ...
      def verify_peer_cert(self, peer_cert: DeviceCertificate) -> bool: ...
      def sign_new_device_cert(self, new_device_pub: bytes, *, person_id: str) -> DeviceCertificate: ...

  @dataclass(frozen=True)
  class DeviceCertificate:
      device_id: str
      person_id: str
      device_pub_ed25519: bytes
      device_pub_x25519: bytes
      issued_by_device_id: str
      signature: bytes              # Ed25519 by issuing device
      not_before: datetime
      not_after: datetime
  ```

- `bridge/security/pairing_flow.py`: 6-digit code generation + validation; QR encode/decode helpers.
- `bridge/sync/lan_sync_engine.py`:

  ```python
  class LANSyncEngine(ISyncPort):
      def __init__(self, *, registry: DeviceRegistry, e2ee: E2EEEngine,
                   crdt: CRDTMergeEngine, port: int = 9000) -> None: ...
      async def start(self) -> None: ...    # binds TCP server on port + opens client connections to peers
      async def stop(self) -> None: ...
      async def publish_delta(self, *, topic: str, delta: Delta, scope: SyncScope) -> SyncResult: ...
      async def subscribe(self, *, topic: str, on_delta) -> SyncSubscription: ...
  ```

**Unit tests:** `tests/bridge/security/test_e2ee_engine.py`, `test_cert_manager.py`, `test_pairing_flow.py`; `tests/bridge/sync/test_lan_sync_engine.py`

- `test_x25519_ecdh_two_processes_derive_same_session_key` — real keypair generation; assert derived session keys equal.
- `test_aes256gcm_encrypt_decrypt_round_trip`.
- `test_decrypt_fails_with_modified_ciphertext` — flip one byte; assert `nacl.exceptions.CryptoError`.
- `test_session_key_rotates_after_24h` — freeze clock; advance 25h; observe new session key.
- `test_session_key_rotates_on_rediscovery_event` — simulate mDNS rediscovery; assert new key.
- `test_cert_manager_verifies_peer_cert_signed_by_known_k0_identity` — fixture cert chain; assert verify returns True.
- `test_cert_manager_rejects_cert_signed_by_unknown_identity` — fixture from another family's K0 root; assert False.
- `test_cert_manager_rejects_expired_cert`.
- `test_cert_manager_signs_new_device_cert_with_correct_chain` — pair a new device; assert resulting cert verifies under issuer's chain.
- `test_pairing_6_digit_code_generation_deterministic_from_fingerprint` — same pubkey → same code.
- `test_pairing_6_digit_code_collision_rate_acceptable` — generate 100k codes; assert collision rate matches expected probability for 6-digit space.
- `test_lan_sync_engine_two_processes_on_loopback_exchange_delta_e2ee` — spawn two engines; pair certs; engine A publishes a delta; assert engine B receives it; assert wire bytes (captured via packet sniff on loopback) are not the plaintext.
- `test_lan_sync_engine_rejects_delta_from_unpaired_peer` — third engine joins without pairing; assert engine A rejects delta + audit-log entry.
- `test_lan_sync_engine_no_plaintext_on_wire` — capture loopback traffic via `tcpdump`/`socket.recv`; assert plaintext payload bytes (e.g. SessionState section name) not present in any captured packet.

**No-mock compliance:** real `pynacl` keys, real TCP loopback, real packet capture for the no-plaintext assertion.

**Wiring at end of epic:** L3 sync is end-to-end live: mDNS discovery (epic 6.2) → cert verification → ECDH session → AES-GCM encrypted CRDT delta exchange → CRDT merge → SessionState convergence.

**Observability:**

- `bridge.security.e2ee.{sessions_started_total{peer_pair}, sessions_rotated_total, encrypt_total, decrypt_total, decrypt_failures_total{reason}}`
- `bridge.security.cert.{verifies_total{outcome}, signs_total, expirations_total}`
- `bridge.security.pairing.{attempts_total{outcome}, codes_generated_total}`
- `bridge.sync.lan.{deltas_sent_total{topic, peer}, deltas_received_total{topic, peer}, peers_paired{person_id}}`

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; runbook `docs/runbooks/device_pairing.md` (user-facing pairing flow, troubleshooting "device won't pair", revoking a lost device, key recovery scenarios).

### Epic 6.5 — MS-6 EXIT CRITERION

**Goal:** named test proves two K1 devices on the same WiFi share SessionState within ADR-0050a coherence bounds (RYW ≤5ms within a peer; bounded-staleness ≤250ms across peers) without K0 in the path.

**Files to create:**

- `tests/bridge/integration/test_ms6_exit.py`:

  ```python
  @pytest.mark.integration
  async def test_two_k1_devices_same_wifi_share_session_state_no_k0(tmp_path):
      # No K0 process spawned — this is the L3 invariant.

      # Pre-stage two device certs signed by a fixture K0 identity (the K0 box stays off).
      person_id = "father"
      k0_identity = SigningKey.generate()
      device_a_id, device_b_id = "device_a", "device_b"
      cert_a, cert_b = build_paired_cert_pair(person_id, k0_identity, device_a_id, device_b_id)

      # Boot two BridgeRuntime processes (subprocess.Popen for true OS-level isolation).
      device_a = await spawn_k1_runtime(
          person_id=person_id, device_id=device_a_id, cert=cert_a,
          enable_l3_sync=True, port=9001, mdns_loopback=True,
      )
      device_b = await spawn_k1_runtime(
          person_id=person_id, device_id=device_b_id, cert=cert_b,
          enable_l3_sync=True, port=9002, mdns_loopback=True,
      )
      try:
          # Wait for mDNS discovery
          await wait_until(lambda: device_b.peers_count() == 1, timeout_s=10)

          # RYW bound: A writes, A reads, must be visible immediately
          t0 = time.perf_counter()
          await device_a.session_state.set("father.session.summary", "summary_v1")
          local_read = await device_a.session_state.get("father.session.summary")
          local_dt_ms = (time.perf_counter() - t0) * 1000
          assert local_read == "summary_v1"
          assert local_dt_ms <= 5.0, f"RYW within-device exceeded 5ms: {local_dt_ms}"

          # Bounded-staleness bound: A writes; B reads via CRDT propagation, must converge ≤250ms
          await device_a.session_state.set("father.session.next_action", "open_calendar")
          t1 = time.perf_counter()
          await wait_until(
              lambda: asyncio.run(device_b.session_state.get("father.session.next_action")) == "open_calendar",
              timeout_s=0.5,
          )
          cross_dt_ms = (time.perf_counter() - t1) * 1000
          assert cross_dt_ms <= 250.0, f"Cross-device staleness exceeded 250ms: {cross_dt_ms}"

          # Concurrent-write convergence: both write to same key concurrently; converge to LWW winner
          await asyncio.gather(
              device_a.session_state.set("father.session.draft", "draft_a", ts=now_ms()),
              device_b.session_state.set("father.session.draft", "draft_b", ts=now_ms() + 1),
          )
          await wait_until(
              lambda: (asyncio.run(device_a.session_state.get("father.session.draft"))
                       == asyncio.run(device_b.session_state.get("father.session.draft"))),
              timeout_s=1.0,
          )
          # Tiebreaker: device_b > device_a alphabetically when timestamps tie; here device_b wrote later → wins
          assert (await device_a.session_state.get("father.session.draft")) == "draft_b"

          # No K0 in path: assert neither device made any HTTP call to a K0 URL
          assert device_a.metrics.k0_http_requests_total == 0
          assert device_b.metrics.k0_http_requests_total == 0

          # E2EE check: assert wire bytes never contained plaintext "draft_b"
          wire_capture = device_a.lan_engine.captured_wire_bytes()
          assert b"draft_b" not in wire_capture
      finally:
          await device_a.shutdown()
          await device_b.shutdown()

  ```

- Update `bridge/contracts/_meta/feature_flags.yaml`: remove MS-6 flags; flip every `status: deferred` L3 manifest to `status: active`.
- Update [bridge_system_design.md](bridge_system_design.md) iteration log: "MS-6 closed; intra-person L3 device sync live; mDNS + LWW CRDT + E2EE; ADR-0050a coherence bounds met (RYW ≤5ms, BS ≤250ms); no K0 in L3 path; status flipped to v1.1 / v1.5 unlock".

**Unit tests:** the exit test IS the test.

**No-mock compliance:** real subprocess K1 runtimes, real mDNS, real TCP, real CRDT, real pynacl crypto, real wire-bytes inspection. K0 is provably absent (zero HTTP requests metric).

**Wiring at end of milestone:** Father's iPhone ↔ Father's Laptop on same WiFi share SessionState within human-imperceptible latency, no cloud round-trip. The architecture is now triple-arm: L1/L2 cross-person via K0 (separate Family Fabric milestone), L3 intra-person via LAN, IFL external via gateway+MCP.

**Exit test:** `test_two_k1_devices_same_wifi_share_session_state_no_k0` — green ⇒ MS-6 shipped, MS-7 unblocks.

---

## MS-7 — Integration testing — booted live system

**Unlocks:** whole-system trust before production. Until MS-7 is green, every milestone exit test has only proven its own slice; MS-7 is the first time the entire wired stack — multi-tenant K0 + multiple K1 processes + IFL adapters + (if MS-6 shipped) LAN sync — is exercised together against the canonical user journeys. After MS-7 closes, the only remaining gate to shipping is MS-8 (adversarial / chaos).

**Pre-conditions:** MS-5 green is the hard floor (full IFL surface live). MS-6 green is desirable but not required — if MS-6 deferred per the post-v1 framing, MS-7 simply skips journey 2 (multi-device same person) and runs the other 4 journeys; the harness is built MS-6-aware so the same code path works either way.

**Wiring at exit:**

- `tests/integration/harness/live_system.py` boots a real multi-tenant K0 (FastAPI + uvicorn + real PostgreSQL via `testcontainers-python` for prod-like + SQLite fallback for fast local) and N real K1 subprocesses on ephemeral ports + ephemeral DBs per-test.
- All 5 user journeys (onboarding, multi-device, family calendar, proactive, IFL) round-trip end-to-end against the harness with real wire bytes, real envelopes, real signing, real outbox, real SSE, real Google Calendar via recorded fixtures.
- Performance baselines captured per topic — p50/p95/p99 latency + throughput — published to `docs/test_results/ms7_baselines/` for MS-8 chaos to compare against.
- Harness teardown asserts zero leaked TCP connections, zero orphaned subprocesses, zero open file handles to ephemeral DBs.

**Strategic stance:** MS-7 is a **testing-only milestone** — no new production code lands. It is also the first milestone that may run for hours in CI rather than minutes; nightly chaos schedule (MS-8) builds on the same harness. Investment here pays back across MS-8 + every future regression catch.

**PR sequencing within MS-7:**

| PR | Scope |
| -- | ----- |
| PR#1 | Harness skeleton + lifecycle primitives + self-test |
| PR#2 | Multi-tenant K0 partition isolation tests |
| PR#3 | Journey 1 (onboarding) + Journey 5 (IFL) — the most independent ones |
| PR#4 | Journey 3 (family calendar / L2) + Journey 4 (proactive) |
| PR#5 | Journey 2 (multi-device, MS-6-conditional) + Performance baselines + Exit test |

### Epic 7.1 — Live-system test harness

**Goal:** one well-engineered Python module that other MS-7 / MS-8 tests `import` to spin up an entire FamilyOS deployment in <15 seconds, exercise it, and tear it down cleanly. The harness is the primary investment of MS-7; everything downstream rides on it.

**Decisions pinned by this epic:**

- **Subprocess isolation, not in-process pytest fixtures.** Every K0 + K1 runs in a real `subprocess.Popen`. This catches process-boundary bugs (signal handling, stdout/stderr buffering, file-descriptor inheritance, port binding races) that in-process FastAPI TestClient cannot. The cost is ~1.5s extra per K1 boot; acceptable.
- **Two PostgreSQL backends** — `testcontainers-python` (Docker-backed real PG) for nightly + CI; `pgx-lite` SQLite shim for `pytest -m integration -k local` developer-loop. Tests parameterize via `@pytest.mark.parametrize("k0_db_backend", ["postgres", "sqlite"])` only on the partition-isolation epic (7.2); journeys default to whatever the runner has (Docker available → PG; otherwise SQLite). Schema drift between the two backends is caught by a separate gate (`schema_parity_postgres_sqlite` — already shipping since K0's M-something — referenced not added here).
- **Ephemeral ports.** No hard-coded port numbers. Harness uses `socket.bind(('127.0.0.1', 0))` to grab a free port, releases, hands the integer to the spawned process via env var. Eliminates "port 8080 in use" flake.
- **Ephemeral DBs.** Per-test temp directory; PG: per-test schema in a shared container with `DROP SCHEMA ... CASCADE` teardown; SQLite: per-test file deleted in `finally`.
- **Process lifecycle** owned by the harness. `LiveSystem.__aenter__` boots; `__aexit__` issues SIGTERM with 10s grace, then SIGKILL. PIDs tracked in a class-level set; teardown asserts the set drains to empty + no orphans (cross-checked via `psutil.process_iter()` filter on harness-spawned PIDs).
- **Leak detection** is mandatory at teardown. Three checks: (a) every PID started is dead; (b) every TCP port allocated is closed (`netstat`-style probe); (c) every temp directory created is removed.

**Files to create:**

- `tests/integration/harness/__init__.py`
- `tests/integration/harness/live_system.py`:

  ```python
  class LiveSystem:
      """
      Booted-live-system harness. Use as async context manager.

          async with LiveSystem(num_k1=2, family_layout=...) as sys:
              await sys.k1[0].publish_memory_write_v1(...)
              atoms = await sys.k0.query("SELECT * FROM memory_atoms")
      """
      def __init__(self, *,
                   num_k1: int = 1,
                   family_layout: FamilyLayout | None = None,
                   k0_db_backend: Literal["postgres", "sqlite"] = "auto",
                   enable_l3_sync: bool = False,
                   ifl_adapters: list[str] = (),
                   recorded_sessions: dict[str, RecordedSession] | None = None) -> None: ...
      async def __aenter__(self) -> "LiveSystem": ...
      async def __aexit__(self, *exc) -> None: ...
      @property
      def k0(self) -> "K0Handle": ...
      @property
      def k1(self) -> list["K1Handle"]: ...
      async def time_skew_until_drain(self, *, max_wait_s: float = 10) -> None: ...
      def assert_no_leaks(self) -> None: ...    # called automatically in __aexit__; exposed for explicit assertions
  ```

- `tests/integration/harness/k0_handle.py`:

  ```python
  class K0Handle:
      pid: int
      port: int
      db_url: str
      base_url: str                              # f"http://127.0.0.1:{port}"
      async def query(self, sql: str, *args) -> list[dict]: ...    # via real psycopg/sqlite
      async def healthz(self) -> dict: ...
      async def metrics(self) -> dict[str, float]: ...
      async def signal(self, sig: signal.Signals) -> None: ...     # for chaos in MS-8
  ```

- `tests/integration/harness/k1_handle.py`:

  ```python
  class K1Handle:
      pid: int
      person_id: str
      device_id: str
      device_kind: str
      api_port: int                              # K1 internal API for test-only inspection
      vault: SqlcipherVault                      # test vault, not OS keychain (CI runners may lack one)
      async def publish_memory_write_v1(self, *, body: dict) -> EnvelopeId: ...
      async def query_session_state(self, key: str) -> Any: ...
      async def trigger_curiosity_agent(self, *, prompt: str) -> CuriosityResult: ...
      async def invoke_ifl(self, *, adapter_id: str, tool: str, args: dict) -> ConnectorResult: ...
      async def health(self) -> dict: ...
      async def signal(self, sig: signal.Signals) -> None: ...
  ```

- `tests/integration/harness/family_layout.py`:

  ```python
  @dataclass(frozen=True)
  class FamilyLayout:
      family_id: str
      persons: list[PersonSpec]                  # PersonSpec(person_id, role: parent|kid, devices: list[DeviceSpec])

  def default_father_mother_kid_layout() -> FamilyLayout: ...
  def single_father_layout() -> FamilyLayout: ...
  ```

- `tests/integration/harness/db_backend.py`:

  ```python
  class K0DbBackend(Protocol):
      async def provision(self, schema_name: str) -> str: ...    # returns DB URL
      async def teardown(self, schema_name: str) -> None: ...

  class PostgresContainerBackend(K0DbBackend):    # uses testcontainers; container shared per session, schema per test
      ...
  class SqliteFileBackend(K0DbBackend):
      ...
  def auto_select_backend() -> K0DbBackend: ...   # checks Docker daemon availability
  ```

- `tests/integration/harness/port_allocator.py`:

  ```python
  def allocate_free_port() -> int:
      with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
          s.bind(("127.0.0.1", 0))
          return s.getsockname()[1]
  ```

- `tests/integration/harness/leak_detector.py`:

  ```python
  class LeakDetector:
      def __init__(self) -> None:
          self._pids: set[int] = set()
          self._ports: set[int] = set()
          self._tempdirs: set[Path] = set()
      def track_pid(self, pid: int) -> None: ...
      def track_port(self, port: int) -> None: ...
      def track_tempdir(self, path: Path) -> None: ...
      def assert_clean(self) -> None: ...     # called by LiveSystem.__aexit__; raises with detailed report
  ```

- `tests/integration/harness/process_supervisor.py`:

  ```python
  class ProcessSupervisor:
      """SIGTERM with 10s grace then SIGKILL; tracks all spawned PIDs."""
      async def spawn(self, *args: str, env: dict[str, str], cwd: Path) -> ProcessHandle: ...
      async def shutdown_all(self) -> None: ...
  ```

- `tests/integration/harness/conftest.py`: pytest plugin exposing `live_system` fixture parameterized by markers.
- `tests/integration/harness/recorded_sessions.py`: thin loader for the MS-5 `pytest-recording` fixtures so journeys 4+5 can replay external API calls deterministically.
- `tests/integration/harness/README.md`: usage examples; gotchas (Docker daemon required for PG backend; macOS may need port range fix; Windows test selection).
- `requirements-dev.txt`: add `testcontainers==3.7.*`, `psutil==5.9.*` (psutil already may be present — verify).

**Unit tests:** `tests/integration/harness/test_harness_self.py`

- `test_harness_boots_minimal_k0_only_and_tears_down_clean` — boot K0 with no K1, no DB writes; teardown; assert leak detector clean.
- `test_harness_boots_k0_plus_one_k1_and_round_trips_memory_write` — boot full single-K1 layout; K1 publishes 1 memory write; query K0; assert atom present; teardown clean.
- `test_harness_boots_k0_plus_three_k1_for_father_mother_kid_layout` — assert 3 K1 PIDs distinct, 3 ephemeral ports distinct, 3 ephemeral DBs distinct.
- `test_harness_repeats_boot_teardown_10_times_without_leak` — loop 10×; assert each iteration's leak detector clean; assert PID count returns to baseline; assert no growing temp-dir list.
- `test_harness_postgres_backend_per_test_schema_isolation` — boot 2 LiveSystem instances concurrently against same PG container; write to system A; query system B; assert isolation (different schemas, different data).
- `test_harness_sqlite_backend_per_test_file_isolation` — same concurrency check on SQLite backend.
- `test_harness_auto_selects_postgres_when_docker_available_else_sqlite` — patch `docker.from_env`; assert backend choice.
- `test_harness_sigterm_then_sigkill_grace_period` — boot K0; harness teardown; assert SIGTERM sent first; if K0 unresponsive (instrumented to ignore SIGTERM), SIGKILL after 10s; PID dead within 11s.
- `test_harness_assert_no_leaks_raises_with_report_on_orphan_pid` — leak a PID by skipping teardown of one process; call `assert_no_leaks()`; assert raises with PID + cmdline in message.
- `test_harness_assert_no_leaks_raises_on_unclosed_port` — bind a port via raw socket and don't close; assert leak detector flags it.
- `test_harness_assert_no_leaks_raises_on_unremoved_tempdir` — create + track + skip cleanup; assert leak detector flags it.
- `test_harness_handles_k0_crash_during_test_gracefully` — SIGKILL K0 mid-test; harness teardown still cleans K1 children; final state = no leaks (K0 PID confirmed dead by external signal, not orphaned).
- `test_harness_recorded_sessions_loaded_when_provided` — boot with `recorded_sessions={"google_calendar": ...}`; assert MS-5 fixtures usable inside the test body.

**No-mock compliance:** real subprocess, real PG container (or real SQLite), real TCP, real psutil PID inspection, real signal delivery, real temp directories. Time is wall-clock (test timeouts use `timeout_s` parameters, not freezegun).

**Wiring at end of epic:** any subsequent MS-7 / MS-8 test that needs a booted system writes:

```python
async def test_something(live_system_3p_layout):
    async with LiveSystem(family_layout=default_father_mother_kid_layout(),
                          enable_l3_sync=False) as sys:
        ...
```

and gets a real fully-wired deployment in ~10s with guaranteed cleanup.

**Observability:**

- Harness emits structured logs to `tests/integration/harness/_runs/<test_id>.log`: every `process.start{pid, cmdline}`, `process.stop{pid, signal, exit_code, duration_ms}`, `port.allocated{port}`, `port.released{port}`, `tempdir.created{path}`, `tempdir.removed{path}`.
- CI artifact upload includes the run log on test failure for post-mortem.
- `tests/integration/harness/_runs/summary.jsonl` aggregated across the test session: total PIDs spawned, total ports allocated, leak count (must be zero).

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log entry "MS-7 PR#1 — live-system harness shipped"; `tests/integration/harness/README.md` covers usage, gotchas, debug recipes (how to inspect a stuck K0 mid-test via `kill -SIGUSR1 <pid>` for stack dump).

### Epic 7.2 — Multi-tenant K0 partition isolation tests

**Goal:** prove the K0 partition model from Q15e is correct under a real multi-tenant boot. The K0 partition model is the load-bearing privacy guarantee for the entire product — a single bug here means Father can read Mother's private notes. MS-3/4/5 unit tests cover partition logic in isolation; MS-7 epic 7.2 is the first time the wired multi-tenant system is observed with real concurrent writers + readers.

**Decisions pinned by this epic:**

- **Topology under test:** 1 family, 3 persons (Father, Mother, Kid), each with 1 device. K0 runs as a single process serving all 3 person partitions (the v1 deployment shape — separate per-person K0 processes is a v2 evolution).
- **Scopes exercised** (per [bridge_system_design.md](bridge_system_design.md) §"Q15e partition model"): `private`, `family`, `parents_only`, `kids_only`, `child_visible: true|false`. Every cross-product (writer × scope × reader) must be tested.
- **Real PG required.** SQLite parity is verified by a separate gate; for partition-isolation guarantees we exercise the actual production backend. CI marker `@pytest.mark.requires_docker` skips on runners without Docker.
- **Concurrency dimension:** for the family scope, 3 simultaneous concurrent writers (one from each partition, same logical "family event") must converge — no lost writes, no duplicate atoms via cross-partition replication race.

**Files to create:**

- `tests/integration/test_partition_isolation.py`:

  - 12 test functions covering the writer × scope × reader matrix below. Each test boots a 3-K1 LiveSystem, performs the writes, then asserts read visibility from each partition.

| # | Writer | Scope | Reader | Expected |
| - | ------ | ----- | ------ | -------- |
| 1 | Father | `private` | Father | visible |
| 2 | Father | `private` | Mother | NOT visible |
| 3 | Father | `private` | Kid | NOT visible |
| 4 | Mother | `parents_only` | Father | visible |
| 5 | Mother | `parents_only` | Mother | visible |
| 6 | Mother | `parents_only` | Kid | NOT visible |
| 7 | Father | `family`, `child_visible: true` | All 3 | all visible |
| 8 | Father | `family`, `child_visible: false` | Father, Mother | visible |
| 9 | Father | `family`, `child_visible: false` | Kid | NOT visible |
| 10 | Kid | `kids_only` | Kid | visible |
| 11 | Kid | `kids_only` | Father / Mother | NOT visible (kid privacy per ADR-Q15) |
| 12 | All 3 simultaneously | `family` | All 3 | exactly 3 atoms visible from each, no duplicates |

- `tests/integration/test_partition_metric_emission.py`: assert `k0.partition.access_total{partition_id, scope, outcome}` increments correctly on each access pattern.
- `tests/integration/test_partition_audit_log.py`: assert every cross-partition denial emits a `partition_access_denied` audit event with reason code.

**Unit tests:** the 14 tests above (12 isolation + 1 metric + 1 audit) ARE the epic's tests. Each runs against the LiveSystem harness from epic 7.1 with real K0 + real PG.

- `test_father_writes_private_only_father_reads`
- `test_father_writes_private_mother_cannot_read`
- `test_father_writes_private_kid_cannot_read`
- `test_mother_writes_parents_only_father_can_read`
- `test_mother_writes_parents_only_mother_reads_own`
- `test_mother_writes_parents_only_kid_cannot_read`
- `test_father_writes_family_child_visible_true_all_three_read`
- `test_father_writes_family_child_visible_false_father_reads`
- `test_father_writes_family_child_visible_false_mother_reads`
- `test_father_writes_family_child_visible_false_kid_cannot_read`
- `test_kid_writes_kids_only_kid_reads_own`
- `test_kid_writes_kids_only_parents_cannot_read`
- `test_three_concurrent_family_writes_converge_no_duplicates`
- `test_partition_access_metric_increments_per_outcome`
- `test_partition_denial_emits_audit_event_with_reason`

**No-mock compliance:** real K0 subprocess, real PG via testcontainers, real psycopg async client. Concurrency test uses real `asyncio.gather()` of 3 K1 publish calls; convergence assertion via real K0 query, not in-memory dedupe inspection.

**Wiring at end of epic:** Q15e partition model has end-to-end coverage. Any future PR that touches `k0/storage/partition_router.py` or scope evaluation in `k0/policy/scope_evaluator.py` must keep these 14 tests green.

**Observability:**

- The 14 tests emit per-test partition access metrics that get aggregated into `tests/integration/_results/partition_isolation_baseline.json` for chaos comparison in MS-8.
- Test failures upload K0's audit log + scope evaluator trace as CI artifact.

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; `docs/runbooks/partition_isolation.md` referencing the matrix as the canonical authority for "what does each scope do".

### Epic 7.3 — End-to-end user journeys (happy paths)

**Goal:** five canonical journeys, each exercised end-to-end against a booted LiveSystem with real wire / real DB / real signing / real IFL recorded fixtures. These are the journeys product-owners + go-to-market reference when they say "FamilyOS does X" — if a journey test is red, that promise is broken.

**Decisions pinned by this epic:**

- **Each journey gets its own test file** at `tests/integration/journeys/test_journey_<n>_<name>.py`. Concrete, narrative, named after the user-facing scenario. Code style favors readability over DRY — repeated setup is fine; the journey test IS the system documentation.
- **Tracing:** every journey injects a single `trace_id` at journey start; assertions at the end include "trace_id appears in K0 spans, K1 spans, IFL gateway spans" to validate observability is actually wired (not just emitted but joinable).
- **Recorded fixtures for IFL** per MS-5 carve-out. Journey 5 uses recorded Google Calendar responses + fixture refresh tokens; no real OAuth in CI.
- **Skip behaviour for MS-6-conditional journey:** journey 2 (multi-device same person, requires LAN sync) is decorated `@pytest.mark.skipif(not L3_SYNC_AVAILABLE, reason="MS-6 deferred")`. CI runs in two modes — "v1 minimum" (4 journeys) and "v1.5 with L3" (all 5). v1 ship gate = the 4-journey mode is green.

**Files to create:**

- `tests/integration/journeys/__init__.py`
- `tests/integration/journeys/conftest.py`: provides `trace_id` fixture (ULID per test) and `journey_assertions` helper (`assert_trace_present_in_k0_logs(trace_id)`, `assert_audit_log_contains(...)` etc).
- `tests/integration/journeys/test_journey_1_onboarding.py`:

  ```python
  async def test_journey_1_family_onboarding_first_memory_write_first_recall(trace_id):
      """
      Father opens FamilyOS app for the first time:
      1. Family create ceremony (Ed25519 family root key, Shamir share to backup)
      2. First person K0 provisioned (Father's private partition)
      3. First K1 device enrolled (Father's iPhone, paired against family root key)
      4. First memory write: "I picked up groceries today"
      5. First recall: "what did I do today?" → returns the grocery memory
      """
      async with LiveSystem(family_layout=single_father_layout()) as sys:
          family_id = await sys.bootstrap_family(family_root_passphrase="test-passphrase")
          father_partition = await sys.k0.provision_person_partition(
              family_id=family_id, person_id="father", role="parent")
          assert father_partition.shamir_threshold == (3, 5)

          await sys.k1[0].enroll(family_id=family_id, person_id="father",
                                  device_id="father_iphone", trace_id=trace_id)
          envelope_id = await sys.k1[0].publish_memory_write_v1(
              body={"text": "I picked up groceries today", "scope": "private"},
              trace_id=trace_id,
          )
          await sys.time_skew_until_drain()

          atoms = await sys.k0.query(
              "SELECT * FROM memory_atoms WHERE partition_id=$1", father_partition.id)
          assert len(atoms) == 1
          assert "groceries" in atoms[0]["text"]

          recall = await sys.k1[0].recall(query="what did I do today?", trace_id=trace_id)
          assert any("groceries" in r.text for r in recall.results)

          # Tracing assertion: trace_id appears in both K0 and K1 logs
          await assert_trace_present_in_k0_logs(sys.k0, trace_id)
          await assert_trace_present_in_k1_logs(sys.k1[0], trace_id)
  ```

- `tests/integration/journeys/test_journey_2_multi_device.py` (skipif L3 unavailable):

  ```python
  @pytest.mark.skipif(not L3_SYNC_AVAILABLE, reason="MS-6 deferred")
  async def test_journey_2_father_iphone_writes_father_laptop_recalls(trace_id):
      """Father starts a session on iPhone, picks it up on laptop on same WiFi."""
      async with LiveSystem(
          family_layout=FamilyLayout(family_id="fam_1",
                                      persons=[PersonSpec("father", "parent",
                                                          [DeviceSpec("father_iphone", "phone"),
                                                           DeviceSpec("father_laptop", "laptop")])]),
          enable_l3_sync=True,
      ) as sys:
          iphone, laptop = sys.k1[0], sys.k1[1]
          await wait_until(lambda: laptop.peers_count() == 1, timeout_s=10)

          await iphone.session_state.set("draft.message", "Hey Mom, can you pick up Riya?")
          await wait_until(
              lambda: asyncio.run(laptop.session_state.get("draft.message"))
                       == "Hey Mom, can you pick up Riya?",
              timeout_s=0.5,
          )
          # Validate L3 path didn't round-trip K0
          assert sys.k0.metrics_snapshot()["http_requests_total"] == \
                 sys.k0.metrics_baseline()["http_requests_total"]
  ```

- `tests/integration/journeys/test_journey_3_family_calendar.py`:

  ```python
  async def test_journey_3_mother_adds_event_propagates_to_father_and_kid_via_l2(trace_id):
      """
      Mother adds family dinner Saturday 7pm.
      Family-scope L2 propagates to Father's K1 + Kid's K1.
      Both other K1s observe the event within bounded staleness.
      """
      async with LiveSystem(family_layout=default_father_mother_kid_layout()) as sys:
          father, mother, kid = sys.k1[0], sys.k1[1], sys.k1[2]

          await mother.publish_calendar_event_v1(
              body={"title": "Family dinner", "starts_at": "2026-05-09T19:00:00Z",
                    "scope": "family", "child_visible": True},
              trace_id=trace_id,
          )
          await sys.time_skew_until_drain()

          # Father + Kid both observe via SSE replay or pull
          father_events = await father.query_calendar(time_range="2026-05-09")
          kid_events = await kid.query_calendar(time_range="2026-05-09")
          assert any("Family dinner" in e.title for e in father_events)
          assert any("Family dinner" in e.title for e in kid_events)
  ```

- `tests/integration/journeys/test_journey_4_proactive.py`:

  ```python
  async def test_journey_4_curiosity_gap_detection_spawns_agent_writes_memory(trace_id):
      """
      System detects a calendar gap (Father's free Saturday afternoon).
      Emits curiosity.intent.v1; K1 spawns curiosity agent; agent generates
      "would you like a recommendation for Saturday afternoon?" suggestion;
      result memory.write to Father's partition.
      """
      async with LiveSystem(family_layout=default_father_mother_kid_layout()) as sys:
          father = sys.k1[0]

          # Pre-stage: pre-existing calendar shows no events Saturday afternoon
          await father.publish_calendar_event_v1(body={
              "title": "Lunch with Sam", "starts_at": "2026-05-09T12:00:00Z",
              "duration_min": 60, "scope": "private"})
          await sys.time_skew_until_drain()

          # Trigger gap detector (real production code path; not faked)
          intent = await sys.k0.curiosity.scan_for_gaps(
              person_id="father", time_horizon="2026-05-09")
          assert intent.topic == "curiosity.intent.v1"
          assert intent.body["gap_window"]["starts_at"] == "2026-05-09T13:00:00Z"

          # K1 receives intent via SSE, spawns agent, writes result
          result = await wait_until(
              lambda: father.memory_atoms_filtered(kind="curiosity_suggestion"),
              timeout_s=15,
          )
          assert any("Saturday afternoon" in a.text for a in result)
  ```

- `tests/integration/journeys/test_journey_5_ifl.py`:

  ```python
  @pytest.mark.recording
  async def test_journey_5_google_calendar_ifl_call_via_fabric_bridge(
      trace_id, recorded_google_calendar_session,
  ):
      """K1 fabric → bridge → ConnectorGateway → MCP child → Google → K0 ingest."""
      async with LiveSystem(
          family_layout=single_father_layout(),
          ifl_adapters=["google_calendar"],
          recorded_sessions={"google_calendar": recorded_google_calendar_session},
      ) as sys:
          father = sys.k1[0]
          await father.vault.store(
              adapter_id="google_calendar_father", key="oauth.refresh_token",
              secret=recorded_google_calendar_session["father_refresh_token"])

          events = await father.invoke_ifl(
              adapter_id="google_calendar_father", tool="list_events",
              args={"calendar_id": "primary",
                    "time_min": "2026-05-09T00:00:00Z",
                    "time_max": "2026-05-09T23:59:59Z"},
              trace_id=trace_id,
          )
          assert len(events.payload["events"]) == 2
          atoms = await sys.k0.query(
              "SELECT * FROM memory_atoms WHERE kind='calendar_event'")
          assert len(atoms) == 2
  ```

**Unit tests:** the 5 journey tests above ARE the epic's tests.

**No-mock compliance:** real subprocess for K0 + every K1; real PG / SQLite; real wire envelopes; real signing; real outbox; real SSE; real Google API replayed via `pytest-recording`. The only abstractions are convenience methods on K1Handle / K0Handle that internally call the same production code paths.

**Wiring at end of epic:** five product-narrative journeys are gates; if any journey breaks in CI, the responsible PR is blocked. Journeys are runnable locally via `pytest tests/integration/journeys/ -m "not skipif_l3"`.

**Observability:**

- Each journey publishes its outcome to `tests/integration/_results/journeys/<journey>_<run_id>.json` with: trace_id, end-to-end latency, count of K0 spans, count of K1 spans, count of bridge spans, count of IFL spans.
- A summary report `journey_observability_summary.md` is regenerated each test session and committed to `docs/test_results/` on green CI runs.

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; `docs/runbooks/journey_failures.md` covers "what to look at first when journey N is red" — concrete debugging recipes per journey (e.g. journey 5 red → check `vault_audit.log` first, then MCP child stdout, then recorded fixture freshness).

### Epic 7.4 — Performance baselines

**Goal:** capture per-topic latency + throughput baselines under nominal load, store as committed artifacts, surface regressions in CI.

**Decisions pinned by this epic:**

- **Nominal load definition:** for each topic, 100 envelopes/sec sustained for 60 seconds against a 1-K0 + 1-K1 booted system. This is sized to the v1 family-of-4 workload (peak rates observed in dogfood telemetry × 2 safety factor); not a stress test (that's MS-8).
- **Per-topic SLAs come from the manifest.** Each manifest's `delivery.timeout_ms` is the upper bound; actual SLA is "p99 ≤ 50% of timeout_ms" (per [bridge_system_design.md](bridge_system_design.md) §"SLA conventions"). Baseline tests assert this.
- **Baseline format:** JSON committed to `docs/test_results/ms7_baselines/<topic>.json`:

  ```json
  {
    "topic": "memory.write.v1",
    "captured_at": "2026-MM-DDTHH:MM:SSZ",
    "harness_commit_sha": "...",
    "k0_commit_sha": "...",
    "load_profile": {"rps": 100, "duration_s": 60, "concurrency": 8},
    "results": {
      "p50_ms": 4.2, "p95_ms": 12.5, "p99_ms": 22.1,
      "throughput_rps": 99.8,
      "errors_total": 0
    },
    "manifest_timeout_ms": 100,
    "sla_target_ms": 50,
    "sla_pass": true
  }
  ```

- **Regression gate:** new gate `performance_regression` (non-blocking warning at MS-7 ship; flips to blocking at MS-8 close). Compares current run's p99 against committed baseline; >25% regression = fail.
- **Tooling:** hand-rolled async load generator (`tests/integration/perf/load_generator.py`); rejected `locust` because it adds a UI server we don't need + a process boundary that complicates the harness. ~150 LOC of asyncio is sufficient.

**Files to create:**

- `tests/integration/perf/__init__.py`
- `tests/integration/perf/load_generator.py`:

  ```python
  class LoadGenerator:
      def __init__(self, *, target: Callable[[int], Awaitable[None]],
                   rps: int, duration_s: int, concurrency: int = 8) -> None: ...
      async def run(self) -> LoadResult: ...

  @dataclass
  class LoadResult:
      total_requests: int
      total_errors: int
      latencies_ms: list[float]
      def percentile(self, p: float) -> float: ...
      def throughput_rps(self) -> float: ...
  ```

- `tests/integration/perf/baseline_recorder.py`:

  ```python
  def record_baseline(topic: str, result: LoadResult, *,
                      manifest: ManifestRecord, output_dir: Path) -> None: ...
  def compare_against_committed_baseline(topic: str, result: LoadResult,
                                          baselines_dir: Path) -> RegressionReport: ...
  ```

- `tests/integration/perf/test_baselines.py` — one test per high-volume topic:

  - `test_baseline_memory_write_v1_under_100rps` — 100 RPS for 60s; assert p99 ≤ 50ms (manifest timeout = 100ms).
  - `test_baseline_curiosity_intent_v1_under_50rps` — 50 RPS, 60s; assert p99 ≤ manifest_timeout/2.
  - `test_baseline_session_state_get_under_500rps` — 500 RPS (session state is high-volume); assert p99 ≤ 10ms.
  - `test_baseline_sse_replay_subscribe_steady_state` — 1 subscriber, 100 events/sec emitted to topic; assert delivery p95 ≤ 100ms.
  - `test_baseline_ifl_google_calendar_invoke_recorded` — 10 RPS over recorded fixture; assert p99 ≤ 200ms (recorded I/O is fast; this captures gateway+MCP overhead).
- `tooling/ci/gates/performance_regression.py`:

  ```python
  REGRESSION_THRESHOLD_PCT = 25
  def main() -> int:
      for topic_baseline_file in baselines_dir.glob("*.json"):
          ...   # load, compare, exit non-zero on regression > threshold
  ```

- `.github/workflows/bridge_ci.yml`: add nightly job `perf_baselines` that runs the perf tests against the harness; uploads results to `docs/test_results/ms7_baselines/_history/<date>/`.
- `docs/test_results/ms7_baselines/README.md`: explains the format, how to regenerate baselines (`python -m tests.integration.perf.regenerate_baselines`), how to interpret regressions.

**Unit tests:** `tests/integration/perf/test_load_generator.py`, `test_baseline_recorder.py`

- `test_load_generator_hits_target_rps_within_5pct` — synthetic target sleeps 1ms; assert observed RPS within 95-105 of target.
- `test_load_generator_records_per_request_latency` — assert `latencies_ms` length == `total_requests`.
- `test_load_generator_counts_errors_separately_from_latencies` — target raises 10% of the time; assert `total_errors` ≈ 10%.
- `test_baseline_recorder_writes_committed_format` — fixture LoadResult; assert JSON output matches schema.
- `test_compare_against_baseline_flags_regression_over_threshold` — synthetic baseline p99=20ms; current p99=30ms (50% regression); assert RegressionReport.has_regression == True.
- `test_compare_against_baseline_no_regression_within_threshold` — current p99=22ms (10% regression); assert no flag.
- `test_performance_regression_gate_passes_when_no_regressions` — synthetic clean run; gate exits 0.
- `test_performance_regression_gate_fails_with_breakdown_on_regression` — inject regression in one topic; assert gate exits non-zero with topic name + delta in message.

**No-mock compliance:** real LiveSystem from epic 7.1; real load generator hitting real K0; real DB writes; real metrics extraction.

**Wiring at end of epic:** every high-volume topic has a committed baseline; nightly CI catches >25% regressions; baselines update via opt-in PR (not auto-overwrite — preserves git history of perf evolution).

**Observability:**

- `docs/test_results/ms7_baselines/<topic>.json` per topic.
- `docs/test_results/ms7_baselines/_history/<date>/<topic>.json` nightly snapshots.
- `docs/test_results/ms7_baselines/_history/index.md` — auto-regenerated trend chart (markdown table of last 30 days p99 per topic).

**Documentation update:** [bridge_system_design.md](bridge_system_design.md) iteration log; `docs/runbooks/perf_baseline_regeneration.md` covering the process for legitimately updating baselines after a known-good improvement.

### Epic 7.5 — MS-7 EXIT CRITERION

**Goal:** one named test orchestrates all 5 user journeys against a single booted LiveSystem in sequence, sharing harness state where appropriate, asserting end-to-end happy-path correctness.

**Files to create:**

- `tests/integration/test_ms7_exit.py`:

  ```python
  @pytest.mark.integration
  @pytest.mark.recording
  async def test_full_system_boot_and_e2e_user_journey(
      tmp_path, recorded_google_calendar_session,
  ):
      """
      MS-7 exit criterion. One booted LiveSystem; all 5 journeys executed against
      it in sequence; per-journey trace_ids preserved; final state-of-world
      assertions covering all 5 outcomes.
      """
      trace_j1 = ulid()
      trace_j2 = ulid()      # may be skipped per L3 availability
      trace_j3 = ulid()
      trace_j4 = ulid()
      trace_j5 = ulid()

      family_layout = FamilyLayout(
          family_id="fam_e2e",
          persons=[
              PersonSpec("father", "parent",
                         [DeviceSpec("father_iphone", "phone"), DeviceSpec("father_laptop", "laptop")]
                         if L3_SYNC_AVAILABLE
                         else [DeviceSpec("father_iphone", "phone")]),
              PersonSpec("mother", "parent",  [DeviceSpec("mother_iphone", "phone")]),
              PersonSpec("kid",    "kid",     [DeviceSpec("kid_tablet", "tablet")]),
          ],
      )

      async with LiveSystem(
          family_layout=family_layout,
          enable_l3_sync=L3_SYNC_AVAILABLE,
          ifl_adapters=["google_calendar"],
          recorded_sessions={"google_calendar": recorded_google_calendar_session},
      ) as sys:
          # Journey 1 — onboarding (uses Father's iPhone)
          father_iphone, *father_other_devices = [k for k in sys.k1 if k.person_id == "father"]
          await sys.bootstrap_family(family_root_passphrase="test")
          await father_iphone.first_run_onboarding(trace_id=trace_j1)
          await father_iphone.publish_memory_write_v1(
              body={"text": "I picked up groceries today", "scope": "private"},
              trace_id=trace_j1)
          await sys.time_skew_until_drain()
          father_atoms = await sys.k0.query(
              "SELECT * FROM memory_atoms WHERE partition_id=$1 AND text LIKE '%groceries%'",
              father_iphone.partition_id)
          assert len(father_atoms) == 1, "Journey 1 — onboarding failed"

          # Journey 2 — multi-device same person (skip if L3 deferred)
          if L3_SYNC_AVAILABLE:
              father_laptop = father_other_devices[0]
              await wait_until(lambda: father_laptop.peers_count() == 1, timeout_s=10)
              await father_iphone.session_state.set("draft.note", "buy milk", trace_id=trace_j2)
              await wait_until(
                  lambda: asyncio.run(father_laptop.session_state.get("draft.note")) == "buy milk",
                  timeout_s=0.5)
              k0_calls_before = sys.k0.metrics_snapshot()["http_requests_total"]

          # Journey 3 — family calendar (Mother adds; Father + Kid see)
          mother = next(k for k in sys.k1 if k.person_id == "mother")
          kid = next(k for k in sys.k1 if k.person_id == "kid")
          await mother.publish_calendar_event_v1(
              body={"title": "Family dinner", "starts_at": "2026-05-09T19:00:00Z",
                    "scope": "family", "child_visible": True},
              trace_id=trace_j3)
          await sys.time_skew_until_drain()
          father_cal = await father_iphone.query_calendar(time_range="2026-05-09")
          kid_cal = await kid.query_calendar(time_range="2026-05-09")
          assert any("Family dinner" in e.title for e in father_cal), "Journey 3 — Father calendar prop failed"
          assert any("Family dinner" in e.title for e in kid_cal), "Journey 3 — Kid calendar prop failed"

          # Journey 4 — proactive curiosity
          await father_iphone.publish_calendar_event_v1(
              body={"title": "Lunch with Sam", "starts_at": "2026-05-09T12:00:00Z",
                    "duration_min": 60, "scope": "private"})
          await sys.time_skew_until_drain()
          intent = await sys.k0.curiosity.scan_for_gaps(
              person_id="father", time_horizon="2026-05-09", trace_id=trace_j4)
          assert intent.topic == "curiosity.intent.v1"
          suggestion_atoms = await wait_until(
              lambda: father_iphone.memory_atoms_filtered(kind="curiosity_suggestion"),
              timeout_s=15)
          assert len(suggestion_atoms) >= 1, "Journey 4 — proactive failed"

          # Journey 5 — IFL Google Calendar
          await father_iphone.vault.store(
              adapter_id="google_calendar_father", key="oauth.refresh_token",
              secret=recorded_google_calendar_session["father_refresh_token"])
          ifl_result = await father_iphone.invoke_ifl(
              adapter_id="google_calendar_father", tool="list_events",
              args={"calendar_id": "primary",
                    "time_min": "2026-05-09T00:00:00Z",
                    "time_max": "2026-05-09T23:59:59Z"},
              trace_id=trace_j5)
          assert len(ifl_result.payload["events"]) == 2
          ifl_atoms = await sys.k0.query(
              "SELECT * FROM memory_atoms WHERE kind='calendar_event'")
          assert len(ifl_atoms) == 2, "Journey 5 — IFL ingest failed"

          # Cross-journey assertions
          # All 5 trace_ids present in K0 logs (validates observability wiring)
          for tid in [trace_j1, trace_j3, trace_j4, trace_j5] + ([trace_j2] if L3_SYNC_AVAILABLE else []):
              await assert_trace_present_in_k0_logs(sys.k0, tid)

          # No partition leaks: Mother's partition has zero of Father's private atoms
          mother_visible = await sys.k0.query(
              "SELECT * FROM memory_atoms WHERE partition_id=$1 AND text LIKE '%groceries%'",
              mother.partition_id)
          assert len(mother_visible) == 0, "Privacy leak: Mother saw Father's private atom"

          # Audit log captured every cross-partition denial + IFL invocation
          audit_log = await sys.k0.read_audit_log()
          assert any("ifl.google_calendar" in e.event_type for e in audit_log)

          # No leaks: harness teardown will run via __aexit__ and assert clean
  ```

- Update `bridge/contracts/_meta/feature_flags.yaml`: remove MS-7 flags.
- Update [bridge_system_design.md](bridge_system_design.md) iteration log: "MS-7 closed; live-system harness shipped; partition isolation matrix proven; 5 user journeys green; perf baselines committed".

**Unit tests:** the exit test IS the test.

**No-mock compliance:** real K0, real K1×3 (or ×4 with L3), real PG (or SQLite), real wire, real signing, real outbox, real SSE, real curiosity pipeline, real MCP child for Google Calendar with recorded HTTP fixtures.

**Wiring at end of milestone:** the entire system has been observed working end-to-end. Performance baselines exist. Partition model proven. The remaining failure modes are adversarial / chaos / Byzantine — the domain of MS-8.

**Exit test:** `test_full_system_boot_and_e2e_user_journey` — green ⇒ MS-7 shipped, MS-8 unblocks.

---

## MS-8 — Adversarial / failure-mode / chaos testing

**Unlocks:** production confidence.
**Pre-conditions:** MS-7 green.
**Wiring at exit:** every failure mode exercised; system survives or fails safely with clear observability.

### Epic 8.1 — Network failure modes

- [ ] Issue: K0 unreachable mid-write — outbox queues, drains on recovery, no data loss
- [ ] Issue: cellular handoff mid-SSE — cursor resume continues, no event loss
- [ ] Issue: DNS failure — endpoint resolver falls back per `delivery.endpoint_class` order
- [ ] Issue: partial network (K1 reaches K0 but K0 reaches DB slowly) — backpressure, no cascade failure
- [ ] **Tests:** real `tc netem` or toxiproxy; real httpx
- [ ] **Wiring:** validates R5, R11
- [ ] **Observability:** every failure produces a metric + log + audit entry

### Epic 8.2 — Crash / restart recovery

- [ ] Issue: kill K0 mid-write — outbox preserves unconfirmed envelopes; on restart, no double-write (idempotency)
- [ ] Issue: kill K1 mid-SSE — on restart, cursor resumes from disk
- [ ] Issue: kill drain worker — safety-net 60s sweep recovers; no lost queued envelopes
- [ ] Issue: corrupt SQLite WAL — recovery succeeds or fails loudly (no silent corruption)
- [ ] **Tests:** SIGKILL real processes, restart, assert state
- [ ] **Wiring:** validates R7
- [ ] **Observability:** recovery telemetry

### Epic 8.3 — Byzantine input / adversarial payloads

- [ ] Issue: oversized payload — rejected at envelope builder, no OOM
- [ ] Issue: malformed JSON — rejected at codec, structured error
- [ ] Issue: invalid signature — rejected at gate, audit-logged
- [ ] Issue: unknown topic — registry refuses, R10 forbidden-zone enforced
- [ ] Issue: replay attack (same idem_key) — second write idempotent no-op
- [ ] Issue: clock skew (timestamp far future / past) — bounded acceptance window enforced
- [ ] **Tests:** real wire payloads, real gates, no mocks
- [ ] **Wiring:** validates security core
- [ ] **Observability:** every rejection categorized + counted

### Epic 8.4 — Split-brain + concurrency (R12)

- [ ] Issue: simulate v2 home K0 + cloud K0 both reachable — single-writer + epoch fencing prevents split-brain
- [ ] Issue: concurrent writes to same record from two persons — LWW + person_id tiebreaker, loser audit-logged not dropped
- [ ] Issue: vector-clock divergence + heal — eventual convergence proven
- [ ] **Tests:** boot 2 K0 processes, simulate dual-reach, assert no divergence
- [ ] **Wiring:** validates R12
- [ ] **Observability:** epoch transitions, conflict resolution outcomes

### Epic 8.5 — Outbox edge cases

- [ ] Issue: outbox at TTL boundary — expired envelopes pruned with metric
- [ ] Issue: dead-letter table fills — alerting fires before disk full
- [ ] Issue: drain rate limit hit — pacing honored, no thundering herd on recovery
- [ ] **Tests:** load real outbox to limits; assert behaviour
- [ ] **Wiring:** validates R5
- [ ] **Observability:** outbox health gauges

### Epic 8.6 — Family identity edge cases

- [ ] Issue: family root key compromised — revocation propagates, signed deltas from revoked key rejected
- [ ] Issue: invitee enrollment replay — second enroll attempt rejected
- [ ] Issue: parent leaves family (D22) — retention policy honored, future writes blocked
- [ ] Issue: kid promoted to parent — role change propagates atomically
- [ ] **Tests:** real ceremony harness
- [ ] **Wiring:** validates Q15b
- [ ] **Observability:** identity transitions audit-logged

### Epic 8.7 — IFL adapter failure modes (MS-5 surface)

- [ ] Issue: external API 5xx storm — circuit breaker opens, recovers
- [ ] Issue: rate-limit hit — backpressure surfaces to caller
- [ ] Issue: revoked adapter — pipeline blocks, audit-logged
- [ ] Issue: WASM adapter OOM / runaway — sandbox kills, no host impact
- [ ] **Tests:** real adapters against fault-injecting test backend
- [ ] **Wiring:** validates ConnectorGateway pipeline
- [ ] **Observability:** breaker state, kill counts

### Epic 8.8 — Sync conflict + tombstone semantics (D27)

- [ ] Issue: late write after delete — tombstone TTL honored
- [ ] Issue: delete propagation across L2 — all family member K0s converge to deleted state
- [ ] Issue: scope downgrade (family → private) — already-replicated copies handled per policy
- [ ] **Tests:** multi-K0 booted system
- [ ] **Wiring:** validates Q15h
- [ ] **Observability:** sync conflict counters

### Epic 8.9 — MS-8 EXIT CRITERION + production readiness

- [ ] Issue: chaos suite runs nightly in CI for 7 days without failure
- [ ] Issue: every failure mode has a runbook entry under `docs/runbooks/`
- [ ] Issue: `/healthz` exposes everything from D32 (DEGRADED topics, outbox depth, peer count, identity status)
- [ ] Issue: production readiness review checklist signed off
- [ ] **Exit test:** `test_chaos_suite_no_data_loss_no_corruption_no_split_brain` — runs full chaos suite end-to-end against booted system; asserts zero data loss, zero corruption, zero split-brain incidents

---

## What this plan does NOT cover (explicit out-of-scope)

- v2 home K0 deployment (post-MS-8; separate plan)
- v3 K1↔K1 P2P device mesh (post-MS-8)
- 3rd-party marketplace + external CAs (post-MS-8)
- ADR-0090 family-fabric-sync ADR PRs (parallel work; tracked in D28)
- Q15 sub-question closures D20–D27 (parallel; gating MS-3+ for sync features only)

---

## Cross-cutting back-ports from `bridge/ARCHITECTURE.md` (added 2026-05-08)

`bridge/ARCHITECTURE.md` carries operational detail that this plan and [bridge_system_design.md](bridge_system_design.md) under-specified at draft time. The items below are now binding inputs to the named milestones — not optional polish. Each cites the architecture-document section that is the canonical source.

### Cross-cutting (applies to every MS-3x epic)

- **Four deployment modes are first-class** (ARCHITECTURE.md §1.2). Every transport-touching epic must verify all four modes still wire correctly: **Dev Monolith** (`InProcessHttpTransport`, shipped MS-2.5), **Device + Cloud** (real `HttpTransport` over WAN — MS-3a), **Full Local** (LAN target — MS-3a config-only), **Offline** (`OnlineFirst[Port]` + outbox — MS-3b). Only `TransportConfig.base_url` and the transport-adapter selection differ. Any epic that introduces per-mode special cases is a smell.
- **K0 endpoint table is fixed** (ARCHITECTURE.md §2): `POST /k0/command.submit`, `POST /k0/query.recall`, `GET /k0/sse.subscribe`, `POST /k0/obs.emit`, plus `/healthz`, `/readyz`, `/metrics`. K0 listens on **port 8080** (D-2.16). Bridge `TransportConfig` default of 8000 is a known bug to fix in MS-3a Epic 3a.1.
- **K0 does not sign responses** (D-2.20): commands return `CommandResponse(receipt_id, commit_ts, offsets, idem_key, obligations)`, obs returns `204 No Content`, queries return plain JSON. Bridge `SignatureVerifier` for K0 responses **must not be built**.
- **BLAKE3 idem-key formula is canonical**: `BLAKE3(topic ‖ \x00 ‖ canonical_json(body) ‖ \x00 ‖ device_id)`. Code in `bridge/core/envelope_builder.py:_compute_idem_key` is the source of truth. Do not introduce alternate formulas (e.g. `(tenant_id, space_id, atom_id, minute(ts))`).

### MS-3a additions (online command path)

- **`CommandResponse` envelope shape** is `(receipt_id, commit_ts, offsets, idem_key, obligations)` (ARCHITECTURE.md §2.1 + D-2.20). Generated K1 client must surface all five fields; `obligations` (post-write actions K0 demands of K1) is opaque structured JSON forwarded to the caller.
- **Health endpoint is `/healthz`** (D-2.15), not `/health` and not `/k0/health`. Bridge `K0HealthChecker` (MS-3b) must target this path. K0 `/healthz` shape per ARCHITECTURE.md §11 and existing `k0/kernel/app.py`.

### MS-3b additions (offline / DEGRADED)

- **Priority-tier enforcement is mandatory** (ARCHITECTURE.md §4): `OnlineFirst[Port]` decorator must consult a per-contract priority tag and apply the policy table:

  | Tier | Behavior when K0 unreachable | Where used |
  |------|------------------------------|------------|
  | `CRITICAL` | Always operational locally — no K0 dependency | IFL local-device commands (MS-5) |
  | `HIGH` | Read-write against local cache; sync on reconnect | SessionState LOCAL COLD (MS-3b co-scope) |
  | `NORMAL` | Queue in `LocalOutbox`, drain on reconnect | `memory.write.v1`, `session.snapshot.v1`, most commands |
  | `LOW` | Drop silently; emit drop counter | Telemetry, non-essential obs |

  Add `delivery.priority_tier: critical|high|normal|low` to the contract manifest schema (Epic 3b.2 already defines auto-derived DEGRADED matrix — extend it to read this field). Default = `normal`.

### MS-3c additions (query port)

- **Recall bundle types** (ARCHITECTURE.md §2.2 + §3.2): `RecallSelector` enumerates `episodic | semantic | session | device | belief | graph`. The query manifest schema must register exactly these six variants.
- Cache decision (D-2.3): query cache is **LRU + TTL, default 60 s, disabled by default**. Tunable per-contract via `delivery.cache_ttl_s` manifest field.

### MS-3d additions (SSE port)

- **Backpressure protocol fields are wire-mandatory** (ARCHITECTURE.md §3.3 + D-2.5): every `SSETraceEvent` carries `(level: ok|throttle|shed, lag_ms: int, pending_events: int)`. K1 client must drop oldest when `level=shed`, slow consumption when `level=throttle`, and emit `bridge.sse.shed_total` on every drop.
- **Cursor persistence** (D-2.6): SQLite-backed `(subscriber_id, topic, last_offset)` table colocated with `LocalOutbox`. Resume on reconnect.
- **Six K0→K1 SSE topics** (ARCHITECTURE.md §7): `memory.formed.v1`, `learning.advisory.v1`, `proactive.signal.v1`, `curiosity.intent.v1`, `sync.complete.v1`, `vector.stored.v1`. `p03.gap.detected.v1` and `p03.complete.v1` are the seventh/eighth, lifted from the legacy plan list.

### MS-3e additions (obs / feedback port)

- **`FeedbackEnvelope` schema is fully specified** (ARCHITECTURE.md §3.4) and supersedes the bare `feedback.signal.p02.v1` / `feedback.signal.p08.v1` topic stubs in earlier plan drafts:

  ```text
  feedback_id   : str (uuid)
  pipeline_id   : P02 | P06 | P08
  tenant_id     : str
  space_id      : str
  signal_class  : CORRECTION | VALIDATION | IMPLICIT | EXPLICIT | OUTCOME
  signal_subtype: str
  correlation:
    session_id, event_ids[], wal_positions[], recall_id, target_entity_id
  provenance:
    source_message_id, recall_context_hash, feedback_timestamp (ns)
  payload:
    P02FeedbackPayload | P08FeedbackPayload    # discriminated union
  ```

  Feedback ships **only** via Obs port `kind=feedback` (D-2.8, D-2.22). The legacy `learning.feedback` command topic does not exist in K0 `outbox_routing.yaml` and must not be added.
- **Obs batching** (D-2.7): default flush 5 s, max batch 50; three payload kinds (`metrics`, `logs`, `feedback`). Manifest `delivery.batch_window_ms` and `delivery.batch_max_size` per contract override the defaults.

### MS-5 additions (Connector Gateway / IFL)

- **Capability-token pipeline** is `TokenVerifier → AdapterVerifier → RateLimiter → CircuitBreaker → RequestRouter` (ARCHITECTURE.md §2.5). Every IFL request walks all five stages or is rejected.
- **Credential storage matrix** (D-2.17, ARCHITECTURE.md §10): macOS/iOS Keychain → Secure Enclave; Android Keystore → TEE/StrongBox; Linux libsecret → TPM 2.0; Windows DPAPI → TPM 2.0; fallback AES-256-GCM SQLite + PBKDF2 from hardware ID. Env vars are forbidden for end-user OAuth tokens.
- **Device onboarding** (D-2.19, ARCHITECTURE.md §10): one-time JWT pairing token, 256-bit secret, 15-min expiry, single-use. Admin → K0 console → "Add Device" → QR / deep link → device generates Ed25519 + X25519 keypairs locally → `POST /k0/admin/device.provision`. No 6-digit codes (1 M brute-force space is unacceptable).
- **Device registry lives in Bridge SQLite, not K0** (D-2.21). K0 has no `st_device_registry` or `st_device_credentials` tables. The `POST /k0/driver.handshake` endpoint is for K0 outbox pipeline workers, **not** IoT device registration.

### MS-6 additions (LAN device sync)

- **E2EE cipher locked now, implementation deferred** (D-2.18): X25519 (Curve25519 ECDH) + AES-256-GCM. The `x25519_public_key` field must be present in the device-provisioning schema **from MS-5**, not added at MS-6, to avoid a forced migration.

### Diagram corrections (immediate, before MS-3a)

ARCHITECTURE.md §9 lists nine known inaccuracies in `bridge/architecture_diagrams/*.mmd`. Treat that table as a checklist; correct the MMDs at the start of MS-3a so visual artifacts don't lag the code reality. Notable items:

- Remove `CMD_LEARNING` node (`learning.feedback` topic does not exist).
- Change `BAND_ENFORCER` text from `GREEN/AMBER/RED/BLACK` to `GREEN/AMBER/RED` (D-2.2; BLACK does not exist on the wire).
- Remove K0 from `FAMILY_DEVICES` subgraph (K0 needs PostgreSQL + pgvector; cannot run on phones).
- Remove `SignatureVerifier` and `HMAC-SHA256` request labels; replace with `Ed25519SHA512` envelope signing only.
- Mark `FB_CODEC` (FlatBufferCodec) and `GRPC_ADAPTER` as `(future)` — JSON-over-HTTP only through MS-4.

---

## Iteration log

| Date | Author | Change |
| ---- | ------ | ------ |
| 2026-05-05 | Pair (Prince + Copilot) | Initial skeleton: 11 milestones (MS-2.5 → MS-8), epic+issue enumeration, no-mock + per-epic-test + per-epic-wiring + per-milestone-exit-test global rules. Each milestone unlocks the next. MS-7/MS-8 dedicated to live-system + adversarial-path testing. Skeleton ready for per-milestone fill-in passes. |
| 2026-05-08 | Pair (Prince + Copilot) | MS-2.5 closed (Epics 2.5.4–2.5.6 shipped: 6 CI gates @ `--fail-on-violation`, `memory.write.v1` end-to-end via `InProcessHttpTransport`, `BridgeAwareLocalBus` R10 mitigation, exit-criterion test green). Back-ported 9 cross-cutting items from `bridge/ARCHITECTURE.md` into MS-3a/3b/3c/3d/3e/5/6: `CommandResponse` shape, priority tiers, recall bundle types, SSE backpressure protocol, FeedbackEnvelope schema, capability-token pipeline, credential storage matrix, JWT device onboarding, X25519+AES-GCM cipher lock. Diagram corrections (§9) added as MS-3a precursor. |
| 2026-05-09 | Pair (Prince + Copilot) | **MS-3a CLOSED** (Epics 3a.1–3a.4 shipped). Code-reality deltas vs plan-as-written: `bridge/client.py` is a flat module not a package (so `HttpBridgeClient` was added inline next to `SinkBridgeClient`); `TransportConfig` already defaulted to port 8080 (the "known bug" was pre-fixed); the producer-side `IKernelCommandPort` umbrella does not yet exist as a generated type — only `IMemoryWriteV1Port` does — so `HttpBridgeClient` exposes per-contract publishers as attributes (`client.memory_write_v1.publish(MemoryWriteV1)`) and reserves `query`/`sse`/`obs`/`gateway` slots for MS-3b/c. Critical gap closed: `HttpTransport.publish(*, topic, schema_uri, payload)` now exists and matches the ASGI shape of `InProcessHttpTransport.publish` so generated clients are transport-agnostic. Construction guard: a private sentinel token plus a new CI gate `bridge_client_construction_via_runtime_only` (mode `fail`) — total 7 gates green. K0 receiver was already substantially complete in `k0/ports/command.py` (router prefix `/k0`, `CommandResponse` shape, `MinimalGate`, `IdempotencyLedger`, Ed25519 verify) — Epic 3a.3 was satisfied by existing coverage in `tests/integration/test_command_port.py`. Wall violation cleared: `k1/memory_writer/adapters/bridge_command_adapter.py` no longer imports `bridge.core.envelope_builder.CommandEnvelope` (allowlist line removed). Topic alias shim deleted: `bridge/_topic_aliases.py` removed; `BridgeRuntime.dispatch()` no longer translates `memory.write` → `memory.write.v1`; the corresponding test in `tests/bridge/contracts/test_memory_write_v1.py` was rewritten to assert the canonical-only behaviour. Test surface added: `tests/bridge/client/test_http_bridge_client.py` (8 tests), `tests/bridge/client/test_http_transport_publish.py` (3 tests), `tests/tooling/ci/gates/test_bridge_client_construction_gate.py` (4 tests). 1102 bridge-tree tests pass; the single `test_signing.py::test_verify_rejects_tampered_signature` failure is a pre-existing flake unrelated to MS-3a (passes on isolated re-run). |
