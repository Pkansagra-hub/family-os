# K1 Flows — Section 2 (UltraBERT Classification) Current State

**Source-of-truth design doc:** [architecture_diagrams/k1/K1_FLOWS.md](../../architecture_diagrams/k1/K1_FLOWS.md) §2 (lines 434–1402)
**Inventory:** [K1_FLOWS_ENUMERATED.md](K1_FLOWS_ENUMERATED.md) §2
**Architectural override:** [docs/plans_completed_donotrefer/temp_tier_fix_plan.md](../plans_completed_donotrefer/temp_tier_fix_plan.md) — Decision A (UltraBERT keeps all heads except `complexity_tier`); Decisions B/C (Front LLM subsumes hypothesis/uncertainty/question planning)
**Companion:** [K1_FLOWS_SECTION1_CURRENT.md](K1_FLOWS_SECTION1_CURRENT.md)
**Verification basis:** subagent code-scan of `k1/concierge/fsm/`, `k1/sessionstate/sections/`, `wheels/familyos_ultrabert-4.0.2`
**Date:** 2026-04-24

Legend: ✅ wired · ⚠️ partial (works but diverges from doc OR has dead-code paths) · ❌ missing · 🔵 deprecated-by-design (per Decisions A/B/C) · 🔵 stub-only (active default is StubPhase1Pipeline)

---

## Major architectural finding

**P3 of the tier-fix plan is partially executed.** Live code shows tombstones at:

- [k1/concierge/fsm/ultrabert_phase1.py#L259](../../k1/concierge/fsm/ultrabert_phase1.py#L259) — *"`_compute_complexity()` was deleted. Tier is now derived in `dispatch_task` from `plan: bool` + multi-intent + `depends_on` signals."*
- [k1/concierge/fsm/phase1.py#L74](../../k1/concierge/fsm/phase1.py#L74) — `# P3.4a: complexity_tier removed`
- [k1/concierge/fsm/phase1.py#L123](../../k1/concierge/fsm/phase1.py#L123) — `to_metadata()` no longer emits `complexity_tier`
- [k1/concierge/config/concierge.py#L15](../../k1/concierge/config/concierge.py#L15) — `# P3.4c: tool_tier removed`
- Controller `_run_phase1()` tombstones at [controller.py#L1619, L1684, L1788, L1852](../../k1/concierge/fsm/controller.py#L1619)

**Residual P3 cleanup not yet done** — these are the demolition targets:

| File | Lines | What survives |
|---|---|---|
| [k1/sessionstate/sections/control.py](../../k1/sessionstate/sections/control.py) | L364, L770, L801, L830, L841, L849, L854, L1228, L1234 | `set_complexity_tier()`/`get_complexity_tier()` shims + `_fsm_overlay` schema field |
| [k1/concierge/_scan_temp/10_ledger_experience_identity_compression.md#L532](../../k1/concierge/_scan_temp/10_ledger_experience_identity_compression.md#L532) | L532, L535 | `IdentitySnapshot.compute(complexity_tier=)` still accepts param (now defaults to `"LOW"`) |
| [k1/concierge/prompt/mode.py](../../k1/concierge/prompt/mode.py) | various | `FRONT_TIER_ALLOWLISTS` still exported |
| [k1/concierge/_scan_temp/06_tools_react.md#L672](../../k1/concierge/_scan_temp/06_tools_react.md#L672) | L672 | `AUTO` tier reads `control.get_complexity_tier()` |
| [poc/session_state_demo/anniversary_demo/runner.py#L2171](../../poc/session_state_demo/anniversary_demo/runner.py#L2171) | L2171 | Demo consumer |
| [poc/session_state_demo/anniversary_demo/display.py#L327](../../poc/session_state_demo/anniversary_demo/display.py#L327) | L327 | Demo struct |

**Tests already updated for P3.1**: `test_m10_e102`, `test_m10_e103`, `test_m04_e41`, `test_m05` assert `complexity_tier` is **absent** from `Phase1Result` — i.e., the tests are correct against the new design.

---

## Section 2 Status Summary

| F# | Name | Status | One-line note |
|---|---|---|---|
| F11 | UltraBERT Core Forward Pass (22ms) | ⚠️ partial | Real `UltraBERTPhase1Pipeline` exists; default is `StubPhase1Pipeline`; 22ms not enforced (CPU/ONNX backend gives more) |
| F12 | Intent Classification (multi-label) | ⚠️ partial | Wheel returns **single** `intent` string; `intent_scores` dict not exposed → multi-label code is dead |
| F13 | Ingress/Domain Classification | ⚠️ partial | Wheel returns **single** `ingress` string; no `domains[]` array; no threshold logic |
| F14 | Safety Band Classification | ✅ | 4-band (GREEN/AMBER/RED/CRISIS) → `PrivacyBand` enum, written to SS control |
| F15 | Emotion Detection | ✅ | 44 emotion classes; `emotion_scores` dict mapped to AFFECTIVE_NOW (emotion + intensity + valence + arousal) |
| F16 | NER Entity Extraction | ✅ | Two NER heads (family + general) merged; confidence threshold 0.65 in wheel v3.0.4+ |
| F17 | Relations Extraction | ⚠️ partial | Wheel returns `list[str]` (not typed tuples); extracted but **NOT written to SS**, no downstream consumer |
| F18 | Sentiment Analysis | ✅ | 5-level → `valence` mapping; `sentiment_confidence` silently dropped |
| F19 | Crisis Detection & Safety Override | ✅ | Inline `if safety_band == "CRISIS"` short-circuit; no `CrisisDetector` class (doc fiction) |
| F20 | Multi-Intent Scoring | ⚠️ partial | `_filter_intents()` real; downstream complexity bump deleted (P3.4a) → produces data nobody reads |
| F21 | Cross-Domain Detection | ⚠️ effectively missing | Single `domain_context: str` only; no `CrossDomainResolver`; doc was forward-looking, never built |
| F22 | Complexity Classification | 🔵 **deprecated-by-design (Decision A; P3.4a EXECUTED)** | `_compute_complexity()` deleted; tier now implicit in Front tool choice |
| F23 | Hypothesis Generation | 🔵 deprecated-by-design (Decision C) | Front LLM (STANDARD mode) reasons over `Phase1Result` directly |
| F24 | Contract & Signal Gap Detection | 🔵 deprecated-by-design (Decision C) | Front LLM (CLARIFY_ASK) detects gaps + calls `update_clarifications()` |
| F25 | Context Inference | 🔵 deprecated-by-design (Decision C) | Front LLM reads SS sections directly via prompt rendering |
| F26 | Tiny Sanity Arbiter Validation | ❌ **real gap** | No pre-LLM verdict gate; `TRIGGER_CLARIFICATION_DETECTED` defined but never emitted (same gap as F02) |
| F27 | Uncertainty Estimation | 🔵 deprecated-by-design (Decision B/C) | Zero entropy/uncertainty math anywhere in repo — Front LLM is the estimator |
| F28 | Entropy-Min Question Planning | 🔵 deprecated-by-design (Decision C) | CLARIFY_ASK prompt + `clarifications.get_top_blocking()` does the selection |
| F29 | Emotion → AFFECTIVE_NOW | ✅ | `_write_phase1_to_ss` → `affective.update(...)`; under stub, writes neutral values |
| F30 | NER → BELIEFS_ACTIVE | ❌ **real gap** | Entities are routed to **SCOREBOARD** (`scoreboard.add_referent`), not BELIEFS_ACTIVE — doc claims wrong destination |
| F31 | Safety → CONTROL | ✅ | `control.escalate_safety(band, reason)` persists band to SS |
| F32 | Intent/Ingress → CONTROL | ✅ | `control.set_intent(IntentClassification)` + `control.set_primary_domain(domain_context)` |

### Headline counts

| Status | Count | Flows |
|---|---|---|
| ✅ wired | **8** | F14, F15, F16, F18, F19, F29, F31, F32 |
| ⚠️ partial | **5** | F11, F12, F13, F17, F20 |
| ⚠️ effectively missing | **1** | F21 (cross-domain — never built) |
| 🔵 deprecated-by-design | **6** | F22, F23, F24, F25, F27, F28 |
| ❌ real gap | **2** | F26 (sanity arbiter / clarification trigger), F30 (NER routed to wrong SS section) |

---

## F11 — UltraBERT Core Forward Pass (22ms) ⚠️ partial

- Real pipeline: [k1/concierge/fsm/ultrabert_phase1.py#L29](../../k1/concierge/fsm/ultrabert_phase1.py#L29) `UltraBERTPhase1Pipeline.classify()`
- Real adapter: [k1/concierge/fsm/ultrabert_adapter.py#L200](../../k1/concierge/fsm/ultrabert_adapter.py#L200) `K1UltraBERTAdapter.analyze()` — single call returns all heads in one forward pass; sha256 LRU/TTL cache; latency captured but no SLO assertion
- Wheel: `familyos_ultrabert-4.0.2` ([wheels/](../../wheels/)) — multi-head shared encoder (`modernbert_multitask.py` + `heads.py` inside the wheel; no separate source dir in repo)
- **Default is StubPhase1Pipeline.** `UltraBERTPhase1Pipeline` requires explicit M10 E10.1 wiring with GPU
- 22ms claim: not enforced; only valid on GPU/ONNX backend

**Gap:** wire `UltraBERTPhase1Pipeline` as default when adapter healthy.

---

## F12 — Intent Classification (Multi-Label) ⚠️ partial

- Adapter mapping: [ultrabert_adapter.py#L244](../../k1/concierge/fsm/ultrabert_adapter.py#L244) `"intent": result.intent`
- Multi-label filter: [ultrabert_phase1.py#L192–200](../../k1/concierge/fsm/ultrabert_phase1.py#L192) `_filter_intents()`
- **Wheel v4.0.2 returns `result.intent` = single string** (primary argmax); does NOT return `intent_scores` dict
- Result: `_filter_intents(analysis.get("intent_scores", {}))` always sees `{}` → returns single-element list
- Downstream `IntentClassification.all_intents` ([controller.py#L1674](../../k1/concierge/fsm/controller.py#L1674)) is always length 1

**Gap:** either upgrade wheel to expose `intent_scores`, or accept single-label permanently and delete the dead multi-label code.

---

## F13 — Ingress/Domain Classification ⚠️ partial

- [ultrabert_adapter.py#L245](../../k1/concierge/fsm/ultrabert_adapter.py#L245), [ultrabert_phase1.py#L130](../../k1/concierge/fsm/ultrabert_phase1.py#L130)
- Same shape as F12: wheel returns single `ingress` string; `Phase1Result.domain_context: str` is scalar
- No `domains[]` array, no per-class threshold

**Gap:** as F12 — wheel limitation propagates downstream.

---

## F14 — Safety Band Classification ✅ wired

- [ultrabert_adapter.py#L236](../../k1/concierge/fsm/ultrabert_adapter.py#L236), [ultrabert_phase1.py#L132](../../k1/concierge/fsm/ultrabert_phase1.py#L132), [controller.py#L1679](../../k1/concierge/fsm/controller.py#L1679)
- Wheel v2.0.3+ normalizes smart-quote text for CRISIS detection
- `_SAFETY_BAND_MAP` maps to `PrivacyBand` enum
- `safety_confidence` extracted from wheel result but NOT placed on `Phase1Result` (minor gap)

---

## F15 — Emotion Detection ✅ wired

- [ultrabert_phase1.py#L133–142](../../k1/concierge/fsm/ultrabert_phase1.py#L133), [controller.py#L1718–1720](../../k1/concierge/fsm/controller.py#L1718)
- 44 emotion classes; `emotions: list[str]` + `emotion_scores: dict[str, float]`
- `primary_emotion = emotions[0]`; `emotion_confidence = max(emotion_scores.values())`; arousal heuristic via `_infer_arousal()` from HIGH/LOW arousal sets
- All written to `affective_now` (see F29)

---

## F16 — NER Entity Extraction ✅ wired

- [ultrabert_adapter.py#L239–240](../../k1/concierge/fsm/ultrabert_adapter.py#L239), [ultrabert_phase1.py#L148–159](../../k1/concierge/fsm/ultrabert_phase1.py#L148) `_merge_entities()`
- **Two NER heads** in the wheel: `entities` (family NER: KINSHIP, FAMILY_EVENT) + `general_entities` (PERSON, ORG, LOC, DATE)
- Merged + de-duped by span; confidence threshold 0.65 enforced inside the wheel (v3.0.4+)
- Doc described single GlobalPointer head — reality is two

**Note:** Doc-claimed entity types MONEY/TIME may be in `general_entities` only (family NER doesn't carry them).

---

## F17 — Relations Extraction ⚠️ partial

- [ultrabert_adapter.py#L246](../../k1/concierge/fsm/ultrabert_adapter.py#L246), [ultrabert_phase1.py#L155](../../k1/concierge/fsm/ultrabert_phase1.py#L155)
- Wheel returns `result.relations: list[str]` (NOT typed tuples like `(USER, spouse_of, Sarah)`)
- `Phase1Result.relations: list[str]` is populated and exposed in `to_metadata()`
- **`_write_phase1_to_ss()` does NOT write relations to SS** ([controller.py#L1653](../../k1/concierge/fsm/controller.py#L1653) doesn't reference them)
- Documented downstream consumers (CONTEXT_INFERENCE, K0 Knowledge Graph) have zero current wiring

**Gap:** decide if relations are wanted (need richer wheel format + SS section + consumer) or deprecate the field.

---

## F18 — Sentiment Analysis ✅ wired

- [ultrabert_adapter.py#L233–234](../../k1/concierge/fsm/ultrabert_adapter.py#L233), [ultrabert_phase1.py#L138–139](../../k1/concierge/fsm/ultrabert_phase1.py#L138), [ultrabert_adapter.py#L28–35](../../k1/concierge/fsm/ultrabert_adapter.py#L28) `SENTIMENT_TO_VALENCE`
- 5-level scale → valence float (-0.8 .. +0.8)
- Internal doc delta: [k1/concierge/docs/milestone10.md](../../k1/concierge/docs/milestone10.md) lists 0.1/0.3/0.5/0.7/0.9 instead of the actual mapping; K1_FLOWS.md doesn't specify numerics so this is a milestone10 doc bug, not a flow bug
- `sentiment_confidence` extracted but discarded (no `Phase1Result` field for it)

---

## F19 — Crisis Detection & Safety Override ✅ wired

- [phase1.py#L91, L104](../../k1/concierge/fsm/phase1.py#L91), [ultrabert_phase1.py#L129](../../k1/concierge/fsm/ultrabert_phase1.py#L129), [controller.py#L1803](../../k1/concierge/fsm/controller.py#L1803), [controller.py#L2004](../../k1/concierge/fsm/controller.py#L2004) `_deliver_crisis_response()`
- Doc describes a `CrisisDetector` class — **does not exist**. Crisis is a 3-line `if result.safety_band == "CRISIS"` short-circuit
- `crisis_iterations` config ([config/loader.py#L245](../../k1/concierge/config/loader.py#L245)) is for ReAct-loop budget on AMBER/RED, NOT for CRISIS (LLM is bypassed entirely)

---

## F20 — Multi-Intent Scoring ⚠️ partial (orphaned)

- [ultrabert_phase1.py#L193](../../k1/concierge/fsm/ultrabert_phase1.py#L193) `_filter_intents()` is a genuine multi-label threshold filter
- Doc named `MultiIntentArbiter` class — **does not exist**
- **Pre-P3:** multi-intent count fed `_compute_complexity()` to bump tier
- **Post-P3.4a:** `_compute_complexity()` deleted → multi-intent list lives in `Phase1Result.intents` but **no downstream consumer reads `len(intents) > 1`**
- F20 is functionally orphaned — produces data nobody uses (and intent_scores aren't exposed by wheel anyway → list is always length 1, see F12)

---

## F21 — Cross-Domain Detection ⚠️ effectively missing

- `CrossDomainResolver` — **zero matches** in repo
- `Phase1Result` has `domain_context: str` (single domain), no `domains: list[str]`
- Diagram shows `CROSS_DOMAIN_DETECTOR` feeding `COMPLEXITY_CLASSIFIER` — the latter is now deleted, so the former had no remaining consumer either
- This is a documentation fiction — never built

---

## F22 — Complexity Classification 🔵 deprecated-by-design (P3.4a EXECUTED)

- **Live tombstones** (already in code):
  - [ultrabert_phase1.py#L259](../../k1/concierge/fsm/ultrabert_phase1.py#L259) — `_compute_complexity()` deleted
  - [phase1.py#L74](../../k1/concierge/fsm/phase1.py#L74) — `complexity_tier` field removed from `Phase1Result`
  - [phase1.py#L123](../../k1/concierge/fsm/phase1.py#L123) — `to_metadata()` no longer emits it
- New tier model (Decision B): tier is **derived in `dispatch_task`** from `plan: bool` + multi-intent + `depends_on` signals, OR **implicit in Front's tool choice** (`invoke_capability` → LOW; `dispatch_task` → MED; `dispatch_task(plan=True)` → HIGH)
- **Residual cleanup needed** (see "Major architectural finding" table at top): SS shims, IdentitySnapshot param, FRONT_TIER_ALLOWLISTS, `AUTO` tier reads, demo files

---

## F23–F25, F27, F28 — Subsumed by Front LLM 🔵 deprecated-by-design

| Flow | Named class | Exists? | Front LLM covers |
|---|---|---|---|
| F23 Hypothesis Generation | `HypothesisGenerator` | ❌ | STANDARD mode reasoning over `Phase1Result` |
| F24 Contract & Signal Gap | `ContractGapDetector` | ❌ | CLARIFY_ASK + `update_clarifications()` ([implementations.py#L341](../../k1/concierge/tools/implementations.py#L341)) |
| F25 Context Inference | `ContextInferrer` | ❌ | Front prompt rendering injects SS sections directly ([front.py#L742](../../k1/concierge/actors/front.py#L742)) |
| F27 Uncertainty Estimation | `UncertaintyEstimator` | ❌ | CLARIFY_ASK; **zero entropy math anywhere in repo** |
| F28 Entropy-Min Question Planning | `EntropyMinQuestionPlanner` | ❌ | CLARIFY_ASK prompt + `clarifications.get_top_blocking()` ([front.py#L388](../../k1/concierge/actors/front.py#L388)) |

These flows are **not gaps** — they're explicit non-goals per Decision C ("no new components; Front LLM owns the reasoning").

---

## F26 — Tiny Sanity Arbiter Validation ❌ real gap

- `TinySanityArbiter` — **zero matches** in repo
- The intended pre-LLM gate (UltraBERT confidence + cached conflict patterns + entity consistency → verdict `PROCEED|CLARIFY|REJECT`) does not exist
- **`TRIGGER_CLARIFICATION_DETECTED` is defined** at [transition_table.py#L78](../../k1/concierge/fsm/transition_table.py#L78) → routes `DISPATCHING → CLARIFYING_USER`
- **Never emitted by `front.py` or anywhere else** → FSM never advances to `CLARIFYING_USER` programmatically
- Same gap as F02 (Section 1)

**Why this is a real gap (not Decision-C-deprecated):** the sanity verdict is supposed to fire *before* Front LLM runs. Front-LLM-as-arbiter happens *after*. The pre-gate is missing entirely. Practical effect: LLM always runs, even on inputs where a deterministic check could have caught a problem cheaper.

---

## F29 — Emotion → AFFECTIVE_NOW ✅ wired

- [controller.py#L1721–1733](../../k1/concierge/fsm/controller.py#L1721) → `affective.update(emotion, intensity, valence, arousal, confidence, source="ultrabert")`
- `AffectiveNowSection.update()` at [sections/affective_now.py#L548](../../k1/sessionstate/sections/affective_now.py#L548)
- Under StubPhase1Pipeline: writes neutral constants every turn (`emotion="neutral"`, `confidence=0.5`, `valence=0.0`, `arousal=0.0`)

---

## F30 — NER → BELIEFS_ACTIVE ❌ real gap (wrong destination)

- Doc says NER entities → `BELIEFS_ACTIVE`
- **Actual code routes entities to SCOREBOARD**: [controller.py#L1700–1714](../../k1/concierge/fsm/controller.py#L1700) → `scoreboard.add_referent(text, entity_id, entity_type, salience)`
- `BELIEFS_ACTIVE` section is **fully implemented** with `add_fact()` ([sections/beliefs_active.py#L415](../../k1/sessionstate/sections/beliefs_active.py#L415)), `add_entity()` (L623), `set_mentioned_time/location` — but **zero callers in `k1/concierge/`**
- Decide: doc is wrong (entities ARE referents, not beliefs) OR code is wrong (need to add a `beliefs_active.add_entity()` call to `_write_phase1_to_ss`)

**Stub effect:** stub returns `entities=[]` so neither SCOREBOARD nor BELIEFS_ACTIVE is touched — this gap is invisible until the real UltraBERT pipeline is wired (F11).

---

## F31 — Safety → CONTROL ✅ wired

- [controller.py#L1676–1683](../../k1/concierge/fsm/controller.py#L1676) → `control.escalate_safety(band, reason="phase1_classification")`
- `ControlSection.escalate_safety()` at [sections/control.py#L1169](../../k1/sessionstate/sections/control.py#L1169) — sets `_safety.band`, `_safety.escalation_reason`, `_safety.escalated_at_ms`
- Both routing (`arbiter.py#L586`) and persistence (SS) consume the band
- Under stub: always GREEN, written every turn

---

## F32 — Intent/Ingress → CONTROL ✅ wired

- Intent: [controller.py#L1666–1675](../../k1/concierge/fsm/controller.py#L1666) → `control.set_intent(IntentClassification(primary, all_intents, classifier="ultrabert"))`
- Ingress/domain: [controller.py#L1677](../../k1/concierge/fsm/controller.py#L1677) → `control.set_primary_domain(result.domain_context)` — **note**: doc calls the field `control.ingress`; actual is `control._domains.primary_domain` sourced from the wheel's `ingress` head ([ultrabert_phase1.py#L125](../../k1/concierge/fsm/ultrabert_phase1.py#L125))
- Under stub: keyword-classified values (`intent="general"/"booking"`, `domain="general"/"travel"`)

---

## Cross-cutting findings

1. **`StubPhase1Pipeline` is the active default.** Sections F11–F18 (heads) are 🔵 stub-only in production until M10 E10.1 wires `UltraBERTPhase1Pipeline`. Stub still produces SS writes (F29, F31, F32) — just with low-fidelity values.
2. **No `single_writer` class** — single-writer is enforced structurally via `TurnLock` + `_write_phase1_to_ss` being the sole caller path. This is consistent across F29/F31/F32.
3. **`familyos_ultrabert-4.0.2` wheel is the bottleneck for F12/F13/F17.** Wheel returns single intent/ingress strings (no `intent_scores` / `domains[]` dicts) and `relations: list[str]` (not typed tuples). Multi-label code in K1 is correct in structure but receives empty/single-element data at runtime.
4. **P3.4a is partially executed.** `_compute_complexity()` deleted, `Phase1Result.complexity_tier` removed, tests updated. Residual: SS shims (`set/get_complexity_tier`), `IdentitySnapshot` param, `FRONT_TIER_ALLOWLISTS`, `tool_tier` config field, demo consumers.
5. **Two real gaps** (not by-design):
   - **F26/F02 — `TRIGGER_CLARIFICATION_DETECTED` is never emitted** → CLARIFYING_USER state unreachable programmatically. Same gap appears in §1.
   - **F30 — NER routes to SCOREBOARD, not BELIEFS_ACTIVE** → doc/code disagreement; needs design decision before action.
6. **`safety_confidence` and `sentiment_confidence` are silently dropped.** Wheel returns them; `Phase1Result` has no fields; never reach SS.

---

## Recommended next actions (priority order)

| Pri | Action | Touches | Source |
|---|---|---|---|
| P0 | **Finish P3** demolition: delete SS `set/get_complexity_tier` shims + `_fsm_overlay` schema entry; drop `complexity_tier` param from `IdentitySnapshot.compute`; delete `FRONT_TIER_ALLOWLISTS`; clean PoC demos | F22, tooling, IdentitySnapshot | tier-fix plan §P3 |
| P0 | Wire `UltraBERTPhase1Pipeline` as default when adapter healthy | F11–F19, F29 (real values), F30 (gap visibility) | M10 E10.1 |
| P1 | Decide F30: change doc OR add `beliefs_active.add_entity()` call in `_write_phase1_to_ss` | F30 | new |
| P1 | Emit `TRIGGER_CLARIFICATION_DETECTED` from Front when LLM calls `update_clarifications` | F02, F26 | unchanged from §1 |
| P2 | Decide on F12/F13/F17: upgrade wheel to expose `intent_scores`/`domains[]`/typed relations OR delete dead multi-label code paths | F12, F13, F17, F20 | new |
| P2 | Add `safety_confidence` and `sentiment_confidence` fields to `Phase1Result` (currently silently dropped) | F14, F18 | new |
| P3 | Update K1_FLOWS.md §2 to mark F22–F28 as deprecated-by-design and drop the named-class fictions (CrisisDetector, MultiIntentArbiter, CrossDomainResolver, HypothesisGenerator, ContractGapDetector, ContextInferrer, TinySanityArbiter, UncertaintyEstimator, EntropyMinQuestionPlanner) | doc | new |

**Net Section 2 reading:** much healthier than it looks. Of 22 flows: 8 wired, 6 deprecated-by-design (correctly, per Decision A/C), 6 partial (mostly wheel API limitations), and only **2 real implementation gaps** (F26 trigger emission + F30 SS routing).

---

**Section 2 complete. Next:** §3 Tool Execution Flows (F33–F42) — 10 flows, 1–2 subagents.
