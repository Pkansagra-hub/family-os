# Phase 1 Deprecation Plan

**Status:** Draft — awaiting approval before code removal
**Author:** GitHub Copilot, with end-to-end repo read by Explore subagent
**Date:** 2026-05-13
**Owner of decision:** Repo owner

---

## 1. Motivation

The K1 Concierge pipeline runs a "Phase 1" pre-LLM classifier on every user
input. It produces intent / domain / safety / affect / entity signals from a
keyword fallback or, when enabled, an UltraBERT (ModernBERT multitask) model.

The LLM that follows is fully capable of judging the same signals as part of
its normal reasoning. Maintaining a parallel classifier means:

- Two sources of truth for intent / safety / domain / affect.
- A ~200-keyword regex layer that drifts and produces both false positives
  (over-eager `update_scoreboard` / `update_beliefs` calls on greetings) and
  false negatives.
- A ~500MB UltraBERT model load (~8s warmup, GB of weights, GPU dependency).
- A `TurnLock` gate, an Arbiter input contract, an `intent.arbitrated` event,
  a `Phase1Classified` event, a per-turn metrics block, and ~20 test files of
  surface area.
- Coupling that makes the prompt and tool policy harder to reason about.

The LLM judges the request. We do not need a static chatbot's classifier in
front of it.

## 2. Scope

**In scope:**
- Remove `Phase1Pipeline`, `Phase1Result`, `StubPhase1Pipeline`,
  `KeywordPhase1Pipeline`, `UltraBERTPhase1Pipeline`, `K1UltraBERTAdapter`,
  `UltraBERTAdapter`, the `phase1.TurnLock`, the `Phase1Classified` event,
  the `Phase1MetricsSubscriber`, and the `Phase1Config` block.
- Remove controller hooks `_run_phase1`, `_run_phase1_with_arbiter`,
  `_write_phase1_to_ss`, `_emit_intent_arbitrated_ledger` (Phase-1-derived
  payload only), `_phase1_pipeline`, all `TurnLock("phase1")` acquire/release.
- Remove `phase1_pipeline` field + validator from `ConciergeConfig`.
- Remove `_build_shared_phase1_pipeline` from `KernelService`.
- Remove UltraBERT/ONNX/PyTorch runtime deps from Docker images.
- Delete or rewrite ~20 tests that assert Phase 1 behavior.

**Out of scope (preserved, possibly relocated):**
- `compute_temporal_anchor` and the temporal anchor write — clock-only, no NLU.
- `ControlSection.IntentClassification` dataclass — keep API; just stop writing
  it from a classifier. Front LLM may write it via cognitive tool.
- `ControlSection._turn_lock` (FlatBuffer dataclass) — unrelated to Phase 1.
- CRISIS safety short-circuit — kept, but driven by a thin keyword check at
  `_on_user_input` entry rather than the full Phase 1 pipeline.
- `ConversationArbiter` — kept, but its input contract changes (no Phase1Result).

## 3. Replacement Strategy

| Phase 1 Output | Replacement |
|---|---|
| `safety_band` | Cheap regex check for CRISIS only (existing `_RED_SAFETY_KEYWORDS`) in FSM entry; everything else defaults to GREEN unless Front LLM escalates via cognitive tool. |
| `temporal_anchor` | Standalone FSM step `_write_session_context_to_ss()` calls `compute_temporal_anchor(persona.timezone)` — already clock-only. |
| `intent_classification` | Dropped at FSM entry. Front LLM populates `control.IntentClassification` via cognitive tool when it matters; prompt no longer relies on it. |
| `domain_context` | Dropped. Front LLM derives domain implicitly; Arbiter uses simplified inflight-vs-new heuristics. |
| `emotion / valence / arousal` | Dropped at FSM entry. Front LLM sets affect via `refine_affect()` cognitive tool. `affective_now` block in prompt shows "unknown" until LLM writes. |
| `entities / referents` | Dropped at FSM entry. Front LLM writes via `update_scoreboard()` when relevant. Initial referent count = 0; this is acceptable and accurate. |
| `TurnLock("phase1")` | Removed. No pre-LLM SS writes need sequencing. |
| `Phase1Classified` event | Removed. |
| `IntentArbitrated` event | Kept; payload simplified (no `domain` / `safety_band` from Phase 1). |
| `ArbiterResult.phase1` field | Replaced with lighter `ArbiterInput` struct carrying raw text + inflight context. Arbiter uses internal keyword constants (CANCEL/DEFER) for routing. |

## 4. Tool Policy Note

`react/loop.py::_resolve_tool_choice` does **not** reference Phase 1 today.
It hardcodes `tool_choice="required"` for Front iteration 0 when tools exist.
That hardcoding is the actual reason a greeting can still trigger
`update_scoreboard` / `update_beliefs` even with a corrected prompt.

This plan does **not** change `_resolve_tool_choice`. That is a separate
follow-up: once Phase 1 is gone, the system prompt becomes the sole authority
on tool-vs-text choice, and we will switch the default to `"auto"` so the
LLM is free to emit text on a greeting without being forced into a tool.

Tracked as follow-up FU-1 in §8.

## 5. Removal Plan — Staged

Each stage is independently mergeable. Each stage ends green on the full
`tests/k1` suite.

### Stage 0 — Test Baseline
- Snapshot current pass/fail counts for `tests/k1`.
- No code changes.

### Stage 1 — Sever Phase 1 from the FSM hot path
1. In `ConciergeController`:
   - Add `_write_session_context_to_ss()` that writes only the temporal
     anchor (lifted from `_write_phase1_to_ss`).
   - Add `_check_crisis_keywords(text) -> bool` that runs the existing
     `_RED_SAFETY_KEYWORDS` list. On hit, escalate
     `control.safety_band = CRISIS` and short-circuit to crisis delivery.
   - Replace `await self._run_phase1_with_arbiter(...)` in `_on_user_input`
     with: crisis check → session-context write → arbiter (with new input
     contract) → react loop.
   - Replace `_run_phase1` in legacy parallel-new path similarly.
2. In `ConversationArbiter`:
   - Add a new `ArbiterInput` (text + inflight context + optional caller
     hints). Keep `ArbiterResult` shape; replace `phase1: Phase1Result`
     field with `inputs: ArbiterInput` (or remove the field entirely if
     downstream readers don't need it — verify in stage 1 PR).
   - Move cancel/defer keyword tuples into the arbiter.
3. Stop emitting `Phase1Classified`. Keep `IntentArbitrated` (simplified
   payload — drop `domain` and Phase 1 `safety_band` fields, since safety
   is now FSM-owned).
4. Tests:
   - Update `test_m05_arbiter.py`, `test_m05_e52`, `test_m05_e53`,
     `test_m05_e54`, `test_concierge_factory*`, `test_m11_epics_4_5_6.py`,
     `test_c1_port_protocols.py`, `tests/k1/concierge/ports/test_port_protocols.py`,
     `test_dispatch_task_plan_derivation.py`, `test_event_registry_completeness.py`,
     `tests/k1/sessionstate/sections/test_affective_now.py` (drop
     `source == "ultrabert"` assertion).

### Stage 2 — Delete Phase 1 modules
1. Delete:
   - `k1/concierge/fsm/phase1.py`
   - `k1/concierge/fsm/ultrabert_phase1.py`
   - `k1/concierge/fsm/ultrabert_adapter.py`
   - `k1/concierge/adapters/ultrabert_classification.py`
   - `k1/concierge/obs/phase1_metrics.py`
2. Trim re-exports:
   - `k1/concierge/fsm/__init__.py` — remove `Phase1Pipeline`, `Phase1Result`,
     `StubPhase1Pipeline`.
   - `k1/concierge/adapters/__init__.py` — remove `StubPhase1Pipeline`.
   - `k1/concierge/types/__init__.py` — remove `Phase1Result`.
   - `k1/concierge/obs/__init__.py` — remove `Phase1MetricsSubscriber`.
   - `k1/concierge/events/conversation.py` — remove `Phase1Classified`.
   - `k1/concierge/events/registry.py` — remove `Phase1Classified` mapping.
3. Trim config:
   - `k1/concierge/config/concierge.py` — remove `phase1_pipeline` field,
     `_VALID_PHASE1_PIPELINES`, `__post_init__` validator clause.
   - `k1/concierge/config/loader.py` — remove `Phase1Config` class and
     `_build_phase1()`.
4. Trim kernel service:
   - `k1/kernel/service.py` — remove `_build_shared_phase1_pipeline`,
     `self._phase1_pipeline`, cleanup line, and the `classification=` kwarg
     on the session factory call.
5. Trim obs metrics fields `phase1_start_ms`/`phase1_end_ms`/`phase1_ms`.
6. Delete tests:
   - `tests/k1/concierge/ports/test_classification_llm_hardening.py`
   - `tests/k1/concierge/test_e0515_obs_stubs.py::TestPhase1MetricsSubscriber`
   - `tests/k1/concierge/test_event_registry_completeness.py::TestPhase1ClassifiedRoundTrip`
   - `tests/k1/concierge/test_m10_e104_adapter.py::TestStubUltraBERTAdapter`

### Stage 3 — Drop heavy dependencies
1. `Dockerfile` — remove UltraBERT wheel COPY/install lines, `HF_TOKEN` if
   unused elsewhere.
2. `Dockerfile.gpu` — remove PyTorch nightly install, `familyos-ultrabert`
   install, `HF_TOKEN`.
3. `requirements.txt` — remove `onnxruntime` (verify no other consumer).
4. Delete `wheels/familyos_ultrabert-*.whl`.

### Stage 4 — Documentation & cleanup
- Update `CHANGELOG.md` with breaking-change note.
- Remove or archive Phase-1-specific docs under `docs/`.
- Grep for stale references to `phase1`, `UltraBERT`, `Phase1Result`,
  `IntentClassification(classifier="ultrabert"`).

## 6. Risk & Rollback

- **CRISIS detection regression risk** — mitigated by keeping the
  `_RED_SAFETY_KEYWORDS` list at FSM entry. Add a regression test asserting
  CRISIS short-circuit on at least three sample inputs.
- **Arbiter regression risk** — `ArbiterResult.phase1` reshape is the most
  invasive change. Mitigation: keep `ArbiterResult.from_dict` backward
  compatible for one release by accepting and ignoring the old field.
- **Affect prompt content regression** — `affective_now` block will show
  "unknown" until Front LLM calls `refine_affect()`. Acceptable; the prompt
  must continue to render without crashing when the section is empty
  (already verified in `_render_affective_now_*`).
- **Tests broken in CI** — staged; each stage ends green.
- **Rollback** — Stage 1 is reversible by reverting the controller diff.
  Stages 2–3 are not reversible without un-deleting files; we will land
  Stage 1 alone first and bake for one cycle before Stage 2.

## 7. Acceptance Criteria

- `_phase1_pipeline` and all `phase1` imports gone from `k1/`.
- `tests/k1` green; no test references UltraBERT / Phase1Result.
- Live browser turn with input `"Hello Good morning"` emits a single text
  response with **zero** tool calls (combined with FU-1).
- `boot_web.ps1` start time reduced (no UltraBERT warmup).
- Docker image size reduced (no PyTorch / UltraBERT weights in GPU image).

## 8. Follow-Ups (out of this plan)

- **FU-1:** Change `_resolve_tool_choice` default for Front iteration 0 from
  `"required"` to `"auto"`. Required to actually eliminate forced tool calls
  on greetings.
- **FU-2:** ModelHub preferred-model routing fix (currently ignores
  `ConciergeConfig.front_model_preferred`).
- **FU-3:** Dispatcher per-tool reset leak.
- **FU-4:** Provider manifest update for Gemini 3.

## 9. Subagent Inventory Reference

Detailed call-site / consumer / test inventory used to write this plan is
captured in the session-resource report from the Explore subagent run on
2026-05-13. Sections A–H of that report map to Sections 2–6 of this plan.
