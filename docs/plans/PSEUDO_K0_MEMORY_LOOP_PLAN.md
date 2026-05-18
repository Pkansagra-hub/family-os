# Pseudo-K0 Memory Loop Plan

Status: proposed
Date: 2026-05-18
Scope: `ui/web`, `scripts/boot_web.ps1`, `scripts/pseudo_k0`, `bridge`, K1 kernel bootstrapping, selfmodel projection, Memory Writer, and Concierge recall.

This plan turns the current K1 web shell + pseudo-K0 bridge into a closed family-memory loop:

    1. Web boot can clearly run in sink/offline mode or live pseudo-K0 mode.
    2. Family profile and turn-derived memories are written into a durable K0-like store.
    3. `recall_memory` can retrieve those facts in later turns and later sessions.
    4. The Concierge prompt gets deterministic household grounding so the model does not spend cycles rediscovering family identity.
    5. K1 remains edge-first: it must work with local projections and outbox even when K0 is absent.

Do not solve this by adding another compact ReAct-loop prompt hack. The model bottleneck should be reduced by better boot-time context, reliable memory write/read contracts, prompt budgeting, and live bridge reliability.

## Current State

### Boot Path

- `scripts/boot_web.ps1` sets `PYTHONPATH`, validates `GOOGLE_API_KEY` in production mode, and runs `python -m ui.web`.
- `ui/web/__main__.py` selects `model_mode` and logs `K0_ENDPOINT` if present.
- `ui/web/coordinator.py` builds `KernelConfig`, including `k0_endpoint`, `seed_memories`, `selfmodel_space_id`, `active_member_id`, and family-tool settings.
- `k1/kernel/service.py` starts the kernel:
  - S2.6 builds the selfmodel bundle.
  - S4 selects bridge mode.
  - P3/P4 wire per-session fabric and Concierge.
  - P5 starts Memory Writer.

### Bridge Modes

- `k0_endpoint` set: `LiveBridgeAdapter` wraps `LiveBridgeClient` and talks to `/k0/command.submit`, `/k0/obs.emit`, and `/k0/sse/{topic}`.
- `bridge_enabled=True` and no `k0_endpoint`: `SinkBridgeAdapter` wraps `SinkBridgeClient` and queues commands to `./data/bridge_outbox.db`.
- `bridge_enabled=False`: `OfflineBridgeAdapter` returns no client.

### Pseudo-K0 Surface

- `python -m scripts.pseudo_k0 --port 8090 --db data/pseudo_k0.db` starts the dev K0 server.
- `scripts/pseudo_k0/server.py` exposes:
  - `POST /k0/command.submit`
  - `POST /k0/obs.emit`
  - `GET /k0/sse/{topic}`
  - `GET /healthz`
- `scripts/pseudo_k0/store.py` persists envelopes to a SQLite WAL and implements simple recall using `LIKE` over a projected `content` column.

### Memory Paths

- Family profile seed memories are built in `verticals/family/seeder.py` and passed into `KernelConfig.seed_memories` for in-session prompt state.
- `ui/web/coordinator.py` also has `_seed_k0_long_term_memories(...)`, which seeds profile memories to live K0 only when `K0_ENDPOINT` is set.
- `k1/concierge/tools/implementations.py::execute_recall_memory` calls `ctx.recall_fn` when available.
- `k1/concierge/adapters/recall_memory.py::build_recall_fn` sends typed `recall.request.v1` through the live bridge.
- `k1/memory_writer` extracts turn memories after `k1.session.turn.completed.v1` and submits batches through `BridgeCommandAdapter`.

### Known Gaps

- Web boot does not start pseudo-K0; operators must start it separately and set `K0_ENDPOINT`.
- Offline/sink mode queues writes but cannot satisfy live recall.
- `memory.delta` from Memory Writer and `memory.write.v1` profile seed writes are not fully aligned for pseudo-K0 recall indexing.
- Memory Writer defaults to session batching: `flush_turn_threshold=20`, `flush_idle_seconds=300`, so new user facts are not immediately durable or recallable.
- `space_id` must be exactly consistent across selfmodel, profile seed writes, Memory Writer writes, and recall requests.
- The active prompt can miss household roster names because `space_graph_block` currently renders `relations.projected_others`, while safe roster data lives in the actor's own L3 `family_members` list.
- Live bridge does not yet own local outbox/drain recovery, so live K0 outages do not get the same queue-and-drain behavior as the sink path.
- Prompt/model cost is inflated by large static prompt assembly, repeated prompt dumps, and model-driven memory discovery.

## Guardrails

- Keep K1 edge-first. K0 improves persistence and recall, but K1 must still boot and answer from local projections when K0 is offline.
- Do not run the full kernel suite. Use only the focused `Run:` lines below plus tests for directly touched files.
- Do not run the full fabric suite unsolicited.
- Do not expose or commit API keys. Rotate any key that appears in logs.
- Preserve privacy rules: full household roster can be name/role grounding; private attributes still require consent and visibility intersection.

## Milestone M0 -- Baseline Boot Truth

Purpose: make the current operating modes obvious and reproducible before changing runtime behavior.

### Epic M0.E1 -- Web Boot Observability

#### Issue M0.E1.I1 -- Document the exact pseudo-K0 + web startup sequence

**Files:**

- `docs/runbooks/` or `docs/development/`
- `scripts/pseudo_k0/__main__.py`
- `scripts/boot_web.ps1`

**Work:**

- Add a runbook that documents the live dev flow:
  - `python -m scripts.pseudo_k0 --port 8090 --db data/pseudo_k0.db`
  - `$env:K0_ENDPOINT = "http://127.0.0.1:8090"`
  - `$env:GOOGLE_API_KEY = "..."`
  - `./scripts/boot_web.ps1`
- Include the sink/offline flow with no `K0_ENDPOINT`.
- Include health checks:
  - `GET http://127.0.0.1:8090/healthz`
  - web log must show `bridge=LIVE` when endpoint is set.
  - web log must show `bridge=OFFLINE (SinkBridgeClient / outbox mode)` when endpoint is empty.
- Include the expected seed-memory boot events:
  - `seed_memories.built`
  - `space_graph.seeded`
  - `self_projections.seeded`
  - `k0_memories.seeded` when live.

**Acceptance:** a developer can bring up pseudo-K0 + web UI from a fresh shell and know which bridge mode is active from logs alone.

**Run:** documentation-only; no tests required.

#### Issue M0.E1.I2 -- Surface bridge mode and K0 health in web boot summary

**Files:**

- `ui/web/__main__.py`
- `ui/web/coordinator.py`
- `scripts/boot_web.ps1`

**Work:**

- Make the boot output explicitly print one of:
  - `Bridge: LIVE -> <K0_ENDPOINT>`
  - `Bridge: SINK/outbox -> ./data/bridge_outbox.db`
  - `Bridge: DISABLED`
- When `K0_ENDPOINT` is set, perform a lightweight `/healthz` preflight before starting uvicorn or during coordinator phase 2.
- If pseudo-K0 is unreachable, fail fast only when a new explicit strict flag is set; otherwise warn and let kernel boot in sink/offline mode.
- Record this in the phase timeline payload so the browser boot diagnostics can show it.

**Acceptance:** logs and boot timeline identify bridge mode without reading Python code.

**Run:** `pytest tests/scripts/pseudo_k0/test_server.py tests/k1/kernel/adapters/test_live_bridge_adapter.py -v`

#### Issue M0.E1.I3 -- Add secret hygiene guardrails for local logs

**Files:**

- `scripts/boot_web.ps1`
- `ui/web/__main__.py`
- `docs/development/` or `docs/runbooks/`

**Work:**

- Ensure boot scripts never echo `GOOGLE_API_KEY` or other provider keys.
- Add runbook guidance to rotate keys if pasted into logs.
- Add a small logging helper if needed so environment variables are only reported as present/missing, never printed.

**Acceptance:** boot output can prove keys are configured without revealing key values.

**Run:** documentation/config focused; no broad tests.

### Epic M0.E2 -- Current-State Regression Anchors

#### Issue M0.E2.I1 -- Lock bridge-mode selection with focused tests

**Files:**

- `tests/integration/k1/live/m7/test_m7_l1_l6_pseudo_k0_integration.py`
- `tests/k1/kernel/adapters/test_live_bridge_adapter.py`
- `k1/kernel/service.py`

**Work:**

- Keep or expand the existing S4 mode test so it proves:
  - `k0_endpoint` set -> `LiveBridgeAdapter`.
  - `bridge_enabled=True`, empty endpoint -> `SinkBridgeAdapter`.
  - `bridge_enabled=False`, empty endpoint -> `OfflineBridgeAdapter`.
- Assert `LiveBridgeAdapter.get_client()` exposes `recall_request_v1` and `memory_write_v1` when live.

**Acceptance:** a future kernel bootstrap change cannot silently break pseudo-K0 mode.

**Run:** `pytest tests/k1/kernel/adapters/test_live_bridge_adapter.py tests/integration/k1/live/m7/test_m7_l1_l6_pseudo_k0_integration.py::test_m7_l6_s4_bridge_mode_selects_expected_client_classes -v`

#### Issue M0.E2.I2 -- Add a minimal recall smoke probe for live pseudo-K0

**Files:**

- `tests/k1/kernel/adapters/test_live_bridge_adapter.py`
- `scripts/pseudo_k0/store.py`
- `scripts/pseudo_k0/server.py`

**Work:**

- Use existing in-process pseudo-K0 server fixture.
- Seed one `memory.write.v1` semantic memory into `family:smith`.
- Build `recall_fn = build_recall_fn(client, space_id="family:smith")`.
- Assert `recall_fn("peanut", ["semantic"], 5)` returns a pseudo-K0 hit.

**Acceptance:** live write -> recall works without the full web app.

**Run:** `pytest tests/k1/kernel/adapters/test_live_bridge_adapter.py::TestLiveBridgeAdapter::test_recall_request_returns_seeded_hits -v`

## Milestone M1 -- Pseudo-K0 as First-Class Dev K0

Purpose: make pseudo-K0 reliable enough to develop end-to-end memory and connector flows locally.

### Epic M1.E1 -- Pseudo-K0 Wire Fidelity

#### Issue M1.E1.I1 -- Align pseudo-K0 response shapes with active bridge contracts

**Files:**

- `scripts/pseudo_k0/server.py`
- `scripts/pseudo_k0/models.py`
- `bridge/_generated/k1/models/recall_response_v1.py`
- `bridge/_generated/k1/models/memory_write_v1.py`
- `tests/scripts/pseudo_k0/test_server.py`

**Work:**

- Keep `recall.request.v1` response shaped exactly like `RecallResponseV1`.
- Decide and document whether `memory.write.v1` returns generic ack or typed `memory.write.response.v1`.
- If typed response model exists, add a compatibility mode where pseudo-K0 can return it.
- Preserve current generic ack for `LiveBridgeClient.submit_command_batch(...)` until the Memory Writer path is migrated.

**Acceptance:** generated typed clients can validate pseudo-K0 responses for recall and, when enabled, memory writes.

**Run:** `pytest tests/scripts/pseudo_k0/test_models.py tests/scripts/pseudo_k0/test_server.py -v`

#### Issue M1.E1.I2 -- Make pseudo-K0 WAL diagnostics useful for dev

**Files:**

- `scripts/pseudo_k0/server.py`
- `scripts/pseudo_k0/store.py`
- `tests/scripts/pseudo_k0/test_server.py`

**Work:**

- Extend `/healthz` or add a read-only diagnostics endpoint that reports:
  - WAL row count.
  - obs row count.
  - rows by topic.
  - rows by `space_id`.
  - last write trace id.
- Keep diagnostics safe for local dev only; do not expose raw private memory bodies unless an explicit debug flag is set.

**Acceptance:** after a web turn, a developer can confirm whether memory writes reached pseudo-K0 without opening SQLite manually.

**Run:** `pytest tests/scripts/pseudo_k0/test_server.py -v`

#### Issue M1.E1.I3 -- Fix recall selector coverage for pseudo-K0

**Files:**

- `scripts/pseudo_k0/store.py`
- `scripts/pseudo_k0/models.py`
- `tests/scripts/pseudo_k0/test_store.py`

**Work:**

- Preserve the current `episodic` and `semantic` selector behavior.
- Map `procedural` requests to `semantic` at the pseudo-K0 boundary or prove the K1 recall adapter already maps it before sending.
- Decide whether `belief`, `session`, `device`, and `graph` should remain empty or map to specific WAL topics.
- Document this clearly in `store.py` and tests.

**Acceptance:** default Concierge calls with `memory_types=["episodic", "semantic", "procedural"]` cannot fail due to unsupported selector type.

**Run:** `pytest tests/scripts/pseudo_k0/test_store.py tests/scripts/pseudo_k0/test_models.py -v`

### Epic M1.E2 -- Connector Host for Local Tool Integration

#### Issue M1.E2.I1 -- Add a registration seam for pseudo-K0 connector handlers

**Files:**

- `scripts/pseudo_k0/__main__.py`
- `scripts/pseudo_k0/connector_host.py`
- `scripts/pseudo_k0/server.py`
- `tests/scripts/pseudo_k0/test_connector_host.py`

**Work:**

- Keep `ConnectorHost` empty by default.
- Add a simple optional handler-registration module path, for example `--connector-module scripts.dev_connectors.family_tools`.
- The module should receive a `ConnectorHost` and call `register_fn(...)` or `register(...)`.
- Do not couple pseudo-K0 directly to `k1.tools.family`; keep it pluggable.

**Acceptance:** a local dev run can register `calendar/create_event` without editing pseudo-K0 server code.

**Run:** `pytest tests/scripts/pseudo_k0/test_connector_host.py tests/scripts/pseudo_k0/test_server.py -v`

#### Issue M1.E2.I2 -- Keep K1-native family tools separate from K0 connectors

**Files:**

- `ui/web/coordinator.py`
- `k1/kernel/service.py`
- `k1/tools/family/**`
- `scripts/pseudo_k0/connector_host.py`

**Work:**

- Document that K1-native family tools are registered in Fabric at S8 and do not require K0.
- Pseudo-K0 connector handlers are for K0-side connector simulation only.
- Add boot diagnostics showing both:
  - K1 family tools registered in Fabric.
  - K0 connector handlers registered in pseudo-K0, if any.

**Acceptance:** developers do not confuse local K1 family-tool routes with pseudo-K0 connector handlers.

**Run:** `pytest tests/scripts/pseudo_k0/test_connector_host.py tests/k1/kernel/adapters/test_live_bridge_adapter.py -v`

## Milestone M2 -- Memory Write/Recall Contract Closure

Purpose: make every memory that is written to pseudo-K0 recallable by the same `recall_memory` path Concierge uses.

### Epic M2.E1 -- Topic and Body Alignment

#### Issue M2.E1.I1 -- Decide canonical K0 write topic for Memory Writer output

**Files:**

- `k1/memory_writer/envelope/envelope_builder.py`
- `k1/memory_writer/envelope/field_mapper.py`
- `scripts/pseudo_k0/store.py`
- `bridge/contracts/**memory*`
- `tests/k1/memory_writer/test_envelope_builder.py`
- `tests/scripts/pseudo_k0/test_store.py`

**Work:**

- Current Memory Writer emits `topic="memory.delta"`.
- Profile seeding emits `topic="memory.write.v1"`.
- Pick one of these strategies:
  - Preferred: Memory Writer emits `memory.write.v1` once contract mapping is ready.
  - Interim: pseudo-K0 treats `memory.delta` as a memory write and indexes it equivalently.
- Whichever strategy is chosen, add tests proving pseudo-K0 recall returns Memory Writer-written atoms.

**Acceptance:** a Memory Writer envelope generated from a turn can be recalled by `recall_memory` through pseudo-K0.

**Run:** `pytest tests/k1/memory_writer/test_envelope_builder.py tests/scripts/pseudo_k0/test_store.py -v`

#### Issue M2.E1.I2 -- Ensure pseudo-K0 indexes Memory Writer bodies correctly

**Files:**

- `scripts/pseudo_k0/store.py`
- `k1/memory_writer/envelope/field_mapper.py`
- `tests/scripts/pseudo_k0/test_store.py`

**Work:**

- `FieldMapper` writes memory content under `text`, not `content`.
- `SQLiteK0Store._extract_content(...)` already checks `content`, `summary`, `text`, `title`, and `description`; lock this with a test using a real Memory Writer-shaped body.
- `SQLiteK0Store._infer_memory_type(...)` currently checks `memory_type` and `type`, then defaults `memory.write*` to `episodic`.
- Add support for Memory Writer's `activity_type` if that is the desired selector mapping, or explicitly map all `memory.delta` atoms to `episodic` for recall.

**Acceptance:** a body containing only `text` and `activity_type` is projected into WAL `content` and recallable by query.

**Run:** `pytest tests/scripts/pseudo_k0/test_store.py -v`

#### Issue M2.E1.I3 -- Consolidate family profile K0 seeding through one code path

**Files:**

- `ui/web/coordinator.py`
- `verticals/family/seeder.py`
- `tests/verticals/family/test_seeder.py`
- `tests/k1/kernel/adapters/test_live_bridge_adapter.py`

**Work:**

- `_seed_k0_long_term_memories(...)` in `ui/web/coordinator.py` duplicates `SpaceDataSeeder.seed_k0_memories(...)` intent.
- Move the canonical transformation from `FamilyMemoryEntry` to K0 envelope into `verticals/family/seeder.py`.
- Make coordinator call that canonical path through the live bridge client.
- Preserve current behavior: no live K0 means skip K0 seed without failing web boot.

**Acceptance:** one family profile memory seed function controls shape, tags, memory type, actor, band, and `space_id`.

**Run:** `pytest tests/verticals/family/test_seeder.py tests/k1/kernel/adapters/test_live_bridge_adapter.py -v`

### Epic M2.E2 -- Space Identity Invariants

#### Issue M2.E2.I1 -- Enforce one `space_id` from selfmodel to K0 recall

**Files:**

- `ui/web/coordinator.py`
- `k1/kernel/service.py`
- `k1/concierge/adapters/recall_memory.py`
- `k1/memory_writer/envelope/envelope_builder.py`
- `k1/memory_writer/context/context_builder.py`
- `verticals/family/profile.py`

**Work:**

- Use `KernelConfig.selfmodel_space_id` as the default for:
  - `LiveBridgeAdapter.default_space_id`.
  - `build_recall_fn(..., space_id=...)`.
  - family profile K0 seed writes.
  - Memory Writer envelope headers.
- Audit SessionState `meta` and `control` sections to find where Memory Writer gets `control_context["space_id"]`.
- If SessionState does not carry space id, add it at session creation from `KernelConfig.selfmodel_space_id`.
- Add an assertion or diagnostic if Memory Writer is about to submit with empty/default `space_id` while selfmodel uses `family:smith`.

**Acceptance:** all write and recall paths for the Smith web profile use `family:smith`.

**Run:** `pytest tests/k1/kernel/adapters/test_live_bridge_adapter.py tests/k1/memory_writer/test_envelope_builder.py tests/verticals/family/test_seeder.py -v`

#### Issue M2.E2.I2 -- Preserve actor identity across seed, Memory Writer, and recall

**Files:**

- `ui/web/coordinator.py`
- `k1/kernel/service.py`
- `k1/memory_writer/envelope/envelope_builder.py`
- `verticals/family/seeder.py`

**Work:**

- Confirm active member is resolved from device and passed as `KernelConfig.active_member_id`.
- Ensure `LiveBridgeAdapter.default_actor` uses that active member id.
- Ensure family profile seed entries use `FamilyMemoryEntry.actor_id` when present.
- Ensure Memory Writer headers use the real active actor, not an opaque session actor, when the web device maps to a family member.

**Acceptance:** pseudo-K0 WAL rows for Alex's web turn show `actor_id=alex` or the agreed canonical actor id, not `bridge` or empty string.

**Run:** `pytest tests/k1/kernel/adapters/test_live_bridge_adapter.py tests/k1/memory_writer/test_envelope_builder.py -v`

#### Issue M2.E2.I3 -- Add K0 seed idempotency

**Files:**

- `verticals/family/seeder.py`
- `scripts/pseudo_k0/store.py`
- `bridge/core/envelope_builder.py`
- `tests/verticals/family/test_seeder.py`
- `tests/scripts/pseudo_k0/test_store.py`

**Work:**

- Add deterministic idempotency metadata to profile memory seed envelopes.
- Suggested key: `profile:<space_id>:<actor_id>:<hash(content)>`.
- Pseudo-K0 should either ignore duplicates or surface enough metadata for tests to verify duplicates.
- Do not require production K0 idempotency behavior for this local milestone; just make repeated web boot not multiply seeded facts indefinitely in dev.

**Acceptance:** restarting web with the same pseudo-K0 db does not create duplicate Smith profile memory rows.

**Run:** `pytest tests/verticals/family/test_seeder.py tests/scripts/pseudo_k0/test_store.py -v`

## Milestone M3 -- Immediate Memory Closure

Purpose: make new user/family facts usable quickly, not five minutes or twenty turns later.

### Epic M3.E1 -- Web-Friendly Memory Writer Flush Policy

#### Issue M3.E1.I1 -- Add a dev/web Memory Writer flush profile

**Files:**

- `k1/memory_writer/config.py`
- `k1/kernel/service.py`
- `ui/web/coordinator.py`
- `tests/k1/memory_writer/test_factory.py`
- `tests/k1/memory_writer/test_pipeline.py`

**Work:**

- Keep production defaults conservative if needed.
- Add a web/dev override for local family UX:
  - lower `flush_turn_threshold`, or
  - lower `flush_idle_seconds`, or
  - flush immediately when the turn contains explicit durable preference language.
- Make the override visible in boot logs.
- Do not add another model call to the foreground response path unless explicitly chosen; Memory Writer can still be background.

**Acceptance:** a fact like "Riley is in a no green phase" can be written to K0 without waiting for 20 turns or 300 seconds in web dev mode.

**Run:** `pytest tests/k1/memory_writer/test_factory.py tests/k1/memory_writer/test_pipeline.py -v`

#### Issue M3.E1.I2 -- Flush memory-worthy facts at turn completion

**Files:**

- `k1/memory_writer/pipeline/session_batch_dispatcher.py`
- `k1/memory_writer/filter/relevance_filter.py`
- `k1/memory_writer/events.py`
- `tests/k1/memory_writer/test_race_condition_fix.py`
- `tests/k1/memory_writer/test_pipeline.py`

**Work:**

- Add a small classification gate for preference/family-profile corrections.
- If a turn is clearly memory-worthy, flush the current buffer immediately after the response is finalized.
- Keep batching for routine low-value turns.
- Preserve `_processed_ids` bounded dedup behavior.

**Acceptance:** explicit durable preferences leave the buffer in the same turn they are observed.

**Run:** `pytest tests/k1/memory_writer/test_pipeline.py tests/k1/memory_writer/test_race_condition_fix.py -v`

### Epic M3.E2 -- Session-Local Read-Your-Writes

#### Issue M3.E2.I1 -- Make freshly stated preferences available before K0 recall catches up

**Files:**

- `k1/concierge/tools/implementations.py`
- `k1/sessionstate/**`
- `k1/concierge/prompt/builder.py`
- `tests/k1/concierge/tools/**`
- `tests/k1/concierge/prompt/test_builder_with_capsule.py`

**Work:**

- When Front calls `update_beliefs` or `update_session_bundle` for a durable preference, keep the fact in SessionState immediately.
- Ensure prompt builder renders the relevant SessionState sections compactly enough that the next turn can use the fact without K0 recall.
- Do not treat SessionState as K0 truth; this is read-your-writes for the active session.

**Acceptance:** after Alex says Riley hates greens and Jordan is trying vegan, the next turn can answer from SessionState even if pseudo-K0 is not yet flushed.

**Run:** `pytest tests/k1/concierge/tools/test_tool_dispatcher_tier_collapse.py tests/k1/concierge/prompt/test_builder_with_capsule.py -v`

#### Issue M3.E2.I2 -- Hydrate turn-start memory from K0 when live

**Files:**

- `k1/kernel/service.py`
- `k1/concierge/adapters/recall_memory.py`
- `k1/sessionstate/**`
- `tests/k1/kernel/adapters/test_live_bridge_adapter.py`

**Work:**

- At session creation, after live bridge and recall port are available, run one bounded recall query for household context.
- Suggested query: `family preferences dietary routines member constraints household context`.
- Write top hits into a compact SessionState belief/profile section with source metadata `k0_recall_startup`.
- Do not block boot for long; use a small timeout and fail open.

**Acceptance:** a new web session can see K0-seeded family facts before the model chooses to call `recall_memory`.

**Run:** `pytest tests/k1/kernel/adapters/test_live_bridge_adapter.py tests/integration/k1/live/m7/test_m7_l1_l6_pseudo_k0_integration.py::test_m7_l2_recall_request_like_search_returns_pseudo_k0_hits -v`

### Epic M3.E3 -- Memory Loop Observability

#### Issue M3.E3.I1 -- Emit write/recall loop events with trace ids

**Files:**

- `k1/memory_writer/service.py`
- `k1/memory_writer/batch/batch_emitter.py`
- `k1/concierge/tools/implementations.py`
- `scripts/pseudo_k0/server.py`

**Work:**

- Add structured logs for:
  - Memory Writer atoms extracted.
  - envelopes submitted.
  - K0 accepted rows.
  - recall query, selector types, hit count, and target `space_id`.
- Include `trace_id`, `session_id`, `space_id`, and `actor_id` when available.
- Avoid logging raw private memory body unless debug mode is on.

**Acceptance:** a single user turn can be traced from prompt -> tool calls -> Memory Writer -> pseudo-K0 WAL -> later recall.

**Run:** `pytest tests/k1/memory_writer/test_batch_emitter.py tests/scripts/pseudo_k0/test_server.py -v`

#### Issue M3.E3.I2 -- Add a manual loop probe script

**Files:**

- `scripts/`
- `scripts/pseudo_k0/**`
- `docs/runbooks/`

**Work:**

- Add a small script that:
  - checks pseudo-K0 `/healthz`.
  - writes one memory under a supplied `space_id`.
  - recalls it by query.
  - prints pass/fail with row count and hit count.
- This should not require the web UI or Gemini.

**Acceptance:** developers can validate K0 memory write/read in under five seconds.

**Run:** `pytest tests/scripts/pseudo_k0/test_server.py tests/scripts/pseudo_k0/test_store.py -v`

## Milestone M4 -- Family Roster and Selfmodel Grounding

Purpose: the model should know who is in the family before asking K0 or guessing.

### Epic M4.E1 -- Safe Household Roster in Active Prompt

#### Issue M4.E1.I1 -- Render safe roster in `space_graph_block`

**Files:**

- `k1/selfmodel/service/capsule_builder.py`
- `k1/concierge/prompt/builder.py`
- `verticals/family/seeder.py`
- `tests/k1/selfmodel/service/test_capsule_family_roster.py`
- `tests/k1/concierge/prompt/test_builder_with_capsule.py`

**Work:**

- `SpaceDataSeeder.seed_self_projections(...)` already places other members into actor L3 `family_members`.
- `GroundingCapsuleBuilder._render_family(...)` renders that safe roster, but `_build_active_member_block(...)` promotes only `self_block` and `space_graph_block`.
- Move or duplicate the safe roster into `_render_space_graph(...)`, or explicitly include `family_block` in the active member block when it contains roster-only safe data.
- Keep private projected attributes under the existing visibility/consent path.

**Acceptance:** Alex's active prompt `[space]` lists Riley, Jordan, and Nana Liz by safe display name/role/alias, while private details still require visibility and consent.

**Run:** `pytest tests/k1/selfmodel/service/test_capsule_family_roster.py tests/k1/concierge/prompt/test_builder_with_capsule.py -v`

#### Issue M4.E1.I2 -- Preserve privacy split between roster and attributes

**Files:**

- `k1/selfmodel/service/situation_composer.py`
- `k1/selfmodel/service/capsule_builder.py`
- `tests/k1/selfmodel/service/test_situation_composer.py`
- `tests/k1/selfmodel/service/test_capsule_family_roster.py`

**Work:**

- Safe roster: member id, display name, role/relation, aliases.
- Protected attributes: preferences, schedule, age, routines, sensitive facts.
- Keep protected attributes behind `consent_posture.family ∩ visibility_rules`.
- Add tests proving a member can be named in roster while sensitive attributes remain absent.

**Acceptance:** prompt grounding can resolve "Jordan" without leaking Jordan's private notes.

**Run:** `pytest tests/k1/selfmodel/service/test_situation_composer.py tests/k1/selfmodel/service/test_capsule_family_roster.py -v`

### Epic M4.E2 -- Family Graph Coverage

#### Issue M4.E2.I1 -- Add non-parent relationship edges where product needs them

**Files:**

- `verticals/family/seeder.py`
- `verticals/family/profile.py`
- `k1/selfmodel/contracts/space_graph.py`
- `tests/verticals/family/test_seeder.py`
- `tests/k1/selfmodel/service/test_space_graph_service.py`

**Work:**

- Current seed graph builds `parent_of` edges from parents to children.
- Add explicit relationship edge policy for:
  - co-guardians / partners where applicable.
  - grandparent/caregiver relation to child where applicable.
  - sibling relation if profile supports multiple children later.
- Do not use graph edges to leak attributes; they only help relation projection and prompt context.

**Acceptance:** family graph represents enough structure for household reasoning without requiring K0 memory recall for obvious relationships.

**Run:** `pytest tests/verticals/family/test_seeder.py tests/k1/selfmodel/service/test_space_graph_service.py -v`

#### Issue M4.E2.I2 -- Add family visibility policy tests for guardian, caregiver, child, visitor

**Files:**

- `k1/selfmodel/contracts/bootstrap_constitution.v1.yaml`
- `k1/selfmodel/service/situation_composer.py`
- `tests/k1/selfmodel/service/test_situation_composer.py`

**Work:**

- Verify bootstrap visibility rules for role vocabulary:
  - `self`
  - `guardian`
  - `caregiver`
  - `member`
  - `child`
  - `visitor`
- Add tests for expected visible keys per viewer/target role pair.
- Keep default-deny for missing role paths.

**Acceptance:** role vocabulary changes cannot silently empty `[space]` again.

**Run:** `pytest tests/k1/selfmodel/service/test_situation_composer.py tests/k1/selfmodel/service/test_composer_helpers.py -v`

## Milestone M5 -- Live Bridge Reliability and Outbox Recovery

Purpose: live pseudo-K0 mode should retain the edge-first queue-and-drain behavior, not lose writes during K0 outages.

### Epic M5.E1 -- LiveBridgeAdapter Local Outbox

#### Issue M5.E1.I1 -- Give `LiveBridgeClient` an outbox and DrainWorker

**Files:**

- `k1/kernel/adapters/live_bridge_adapter.py`
- `bridge/sync/local_outbox.py`
- `bridge/sync/drain_worker.py`
- `tests/integration/k1/live/m7/test_m7_l1_l6_pseudo_k0_integration.py`

**Work:**

- Add optional local outbox ownership to `LiveBridgeAdapter` or `LiveBridgeClient`.
- On transport failure for queueable topics, enqueue instead of only logging.
- Start `DrainWorker` when health flips back online.
- Use existing `DrainWorker` startup pass and safety-net sweep.
- Keep sink mode unchanged.

**Acceptance:** the existing xfail `test_m7_l5_live_bridge_queues_and_drains_after_pseudo_k0_restart` can be made passing.

**Run:** `pytest tests/integration/k1/live/m7/test_m7_l1_l6_pseudo_k0_integration.py::test_m7_l5_live_bridge_queues_and_drains_after_pseudo_k0_restart -v`

#### Issue M5.E1.I2 -- Reuse bridge degraded-matrix semantics for queueable vs online-required topics

**Files:**

- `bridge/core/degraded.py`
- `bridge/core/online_first.py`
- `k1/kernel/adapters/live_bridge_adapter.py`
- `tests/bridge/integration/test_outbox_drain_on_recovery.py`

**Work:**

- `memory.write.v1` and Memory Writer output must be queueable.
- Truly online-required contracts must fail clearly when K0 is offline.
- LiveBridgeAdapter should not invent a separate degraded policy if bridge core already has one.

**Acceptance:** live bridge behavior matches bridge-core chaos tests.

**Run:** `pytest tests/bridge/integration/test_outbox_drain_on_recovery.py tests/integration/k1/live/m7/test_m7_l1_l6_pseudo_k0_integration.py::test_m7_l5_live_bridge_queues_and_drains_after_pseudo_k0_restart -v`

### Epic M5.E2 -- Real K0 Readiness Boundaries

#### Issue M5.E2.I1 -- Thread signing configuration through KernelConfig

**Files:**

- `k1/concierge/config/kernel.py`
- `k1/kernel/adapters/live_bridge_adapter.py`
- `bridge/core/signing.py`
- `tests/k1/kernel/adapters/test_live_bridge_adapter.py`

**Work:**

- Current live bridge uses dev zero-key HMAC signing.
- Add `KernelConfig` fields for signing key id and secret source.
- Keep pseudo-K0 dev mode able to ignore signatures.
- Fail fast or warn clearly when a real K0 endpoint is configured with dev signing.

**Acceptance:** production-like K0 can reject dev signatures, and K1 has a real config path to supply valid signing material.

**Run:** `pytest tests/k1/kernel/adapters/test_live_bridge_adapter.py tests/bridge/core/test_online_first.py -v`

#### Issue M5.E2.I2 -- Distinguish pseudo-K0 from real K0 at boot

**Files:**

- `scripts/pseudo_k0/server.py`
- `ui/web/coordinator.py`
- `k1/kernel/service.py`

**Work:**

- Add `/healthz` response metadata such as `kind=pseudo_k0`, `version`, `contract_level`.
- Web boot can log `K0 kind=pseudo_k0` vs `K0 kind=real`.
- Real K0 should not be assumed to support dev-only endpoints.

**Acceptance:** operators can tell whether they are connected to pseudo-K0 or real K0 from logs.

**Run:** `pytest tests/scripts/pseudo_k0/test_server.py tests/k1/kernel/adapters/test_live_bridge_adapter.py -v`

## Milestone M6 -- Model Bottleneck Reduction

Purpose: reduce model confusion and latency by giving it the right context deterministically and avoiding wasted calls.

### Epic M6.E1 -- Deterministic Context Before Model Work

#### Issue M6.E1.I1 -- Hydrate household facts outside the ReAct loop

**Files:**

- `k1/kernel/service.py`
- `k1/concierge/prompt/builder.py`
- `k1/concierge/actors/front.py`
- `k1/concierge/adapters/recall_memory.py`

**Work:**

- Do not rely on the model to discover basic household roster and stable preferences each turn.
- Use selfmodel safe roster and startup K0 recall hydration to pre-fill prompt/SessionState.
- Keep `recall_memory` for dynamic historical lookup, not as the only path for known family identity.

**Acceptance:** a dinner prompt sees household roster and known stable preferences before the first tool call.

**Run:** `pytest tests/k1/concierge/prompt/test_builder_with_capsule.py tests/k1/selfmodel/service/test_capsule_family_roster.py -v`

#### Issue M6.E1.I2 -- Add a compact memory digest block for high-signal family facts

**Files:**

- `k1/concierge/prompt/builder.py`
- `k1/sessionstate/**`
- `k1/concierge/adapters/recall_memory.py`

**Work:**

- Create a bounded digest for stable recalled/profile facts:
  - dietary constraints.
  - strong preferences/dislikes.
  - routines relevant to current request.
  - current active commitments.
- Keep it separate from raw recall hits.
- Include provenance labels: `profile_seed`, `session_fact`, `k0_recall`.

**Acceptance:** the model can answer "does it cover everyone?" without a broad recall loop when the digest already has the facts.

**Run:** `pytest tests/k1/concierge/prompt/test_builder_with_capsule.py -v`

### Epic M6.E2 -- Prompt and Runtime Cost

#### Issue M6.E2.I1 -- Cache static prompt sections per session

**Files:**

- `k1/concierge/prompt/builder.py`
- `k1/concierge/actors/front.py`

**Work:**

- Identify static sections that do not change per turn:
  - identity text.
  - native intelligence rules.
  - anti-patterns.
  - dispatch rules.
- Cache rendered static sections per session or process.
- Re-render only dynamic sections: time, affect, SessionState, capsule, scenario data.

**Acceptance:** prompt build time and allocations drop without changing prompt semantics.

**Run:** `pytest tests/k1/concierge/prompt/test_builder_with_capsule.py -v`

#### Issue M6.E2.I2 -- Make prompt dumps debug-gated and bounded

**Files:**

- `k1/concierge/actors/front.py`
- `data/prompt_dumps/` handling code
- `ui/web/coordinator.py`

**Work:**

- Keep prompt dumps available for diagnosis.
- Gate dumps behind an explicit env var or debug mode.
- Keep `front_prompt_latest.json` if useful, but prevent unbounded per-turn file growth unless debug is enabled.

**Acceptance:** normal family web usage does not synchronously write large prompt dumps every turn.

**Run:** `pytest tests/k1/concierge/prompt/test_builder_with_capsule.py -v`

#### Issue M6.E2.I3 -- Replace model-driven synthesis retry with typed loop policy only if needed

**Files:**

- `k1/concierge/react/loop.py`
- `tests/k1/concierge/react/test_front_operational_routing_guard.py`

**Work:**

- Do not reintroduce the rejected compact Front continuation patch.
- If model degenerate responses persist after memory/context fixes, add a narrow typed policy:
  - detect empty text/no tools from provider.
  - retry once with the same effective prompt and explicit text-only capability.
  - record a typed loop event.
  - keep behavior provider-aware and testable.
- Avoid modifying the system prompt content as the primary fix.

**Acceptance:** recovery from empty model responses is explicit, observable, and not a hidden prompt rewrite.

**Run:** `pytest tests/k1/concierge/react/test_front_operational_routing_guard.py -v`

## Milestone M7 -- End-to-End Family Memory Acceptance

Purpose: prove the full user-facing dinner/preference flow closes the loop.

### Epic M7.E1 -- Automated E2E Without Browser

#### Issue M7.E1.I1 -- Add pseudo-K0 + KernelService + Concierge memory-loop integration test

**Files:**

- `tests/integration/k1/live/m7/`
- `tests/integration/k1/live/m7/helpers.py`
- `verticals/family/smith.py`
- `ui/web/coordinator.py` if needed for helper reuse

**Work:**

- Start in-process pseudo-K0.
- Start KernelService with:
  - `k0_endpoint=pseudo_k0.endpoint`
  - `selfmodel_space_id="family:smith"`
  - `active_member_id="alex"`
  - family seed memories.
- Seed Smith profile into selfmodel and K0.
- Simulate turns:
  1. "planning to make dinner for family any suggestions?"
  2. "does it take care of everyone preferences?"
  3. "Riley is in a no green phase and Jordan is going vegan"
- Assert:
  - prompt has safe roster for Riley, Jordan, Nana Liz.
  - K0 WAL receives profile seed rows.
  - K0 WAL receives Memory Writer rows or session-local facts are visible immediately.
  - later recall returns Riley/Jordan preference facts.

**Acceptance:** the dinner flow works as a kernel integration without opening the browser.

**Run:** `pytest tests/integration/k1/live/m7/test_m7_l1_l6_pseudo_k0_integration.py -v`

### Epic M7.E2 -- Manual Web Acceptance

#### Issue M7.E2.I1 -- Add a manual acceptance script for the web UI flow

**Files:**

- `docs/runbooks/`
- `scripts/`
- `ui/web/**`

**Work:**

- Document manual steps:
  - start pseudo-K0.
  - set `K0_ENDPOINT`.
  - boot web.
  - ask the dinner flow.
  - inspect `/healthz` or diagnostics for WAL row counts.
  - restart web and ask a recall question.
- Include expected log markers.
- Include failure triage:
  - no `bridge=LIVE` -> endpoint not set.
  - no K0 seed rows -> coordinator seed failed.
  - recall returns zero -> `space_id` mismatch or indexing problem.
  - prompt lacks Jordan/Nana -> roster projection issue.

**Acceptance:** a developer can manually prove end-to-end memory closure in the browser and know where to look when it fails.

**Run:** manual; pair with targeted tests from M7.E1.

## Recommended Implementation Order

1. M0.E1.I1 -- runbook first, so everyone boots the same system.
2. M0.E2.I1 -- lock S4 bridge-mode selection.
3. M2.E2.I1 -- enforce `space_id` consistency before deeper memory debugging.
4. M2.E1.I1 + M2.E1.I2 -- make Memory Writer output recallable by pseudo-K0.
5. M4.E1.I1 -- put safe full household roster into the active prompt.
6. M3.E1.I1 -- make memory flush usable for web dev.
7. M5.E1.I1 -- make live bridge survive pseudo-K0 restarts.
8. M7.E1.I1 -- add the full kernel-level dinner memory-loop acceptance test.
9. M6 issues -- optimize prompt/model cost after the data loop is correct.

## Definition of Done

- `scripts/boot_web.ps1` + pseudo-K0 can start a live dev system with clear boot logs.
- `recall_memory` returns K0 hits for Smith profile facts under `family:smith`.
- A new preference stated in a turn becomes available in the current session and later through K0 recall.
- Active prompt includes safe household roster names/roles for the family.
- K1 boots and answers in sink/offline mode when pseudo-K0 is absent.
- Live bridge queues memory writes during pseudo-K0 outage and drains them after recovery.
- Focused tests cover every changed subsystem; no full kernel or full fabric suite is required.
