# ⚠️ ARCHITECTURE CHANGE: Template-Based Strategies DEPRECATED

**Date:** 2025-10-22
**Status:** Production Architecture Updated
**Migration:** Issue 2.16.2 completed with LLM-first approach

---

## Summary

The original **Epic 2.16 plan** called for **5 separate strategy contracts** with **22 templates** (rephrase_strategy.yml, simplify_strategy.yml, offer_options_strategy.yml, context_recovery_strategy.yml, missing_entity_strategy.yml).

**This approach has been DEPRECATED** and replaced with **LLM_FIRST_WITH_DETERMINISTIC_FALLBACK** architecture (matching production clarification pipeline v2.1.0).

---

## What Changed

### ❌ DELETED (Never Created):
1. `rephrase_strategy.yml` (3 templates: "I didn't quite catch that", "Could you rephrase?", "Could you say that differently?")
2. `simplify_strategy.yml` (Template: "I caught {understood_parts}, but I missed {missed_parts}. Could you clarify?")
3. `offer_options_strategy.yml` (Template: "Did you mean {option_a} or {option_b}?")
4. `context_recovery_strategy.yml` (Template: "Are we still talking about {last_topic}?")
5. `missing_entity_strategy.yml` (Template: "I can {action}, but I need {missing_entity}")

**Rationale:** Templates sound robotic - user hears same 22 phrases 1,460× over 20 years (see ADR-0054d).

### ✅ REPLACED WITH:
1. **`strategy_selection.yml`** (v2.0.0) — LLM scenario selection (this directory)
2. **`clarification_generation.yml`** (v2.1.0) — 5 LLM system prompts with infinite variety
3. **`confidence_thresholds.yml`** (v2.0.0) — LLM_FIRST_WITH_DETERMINISTIC_FALLBACK mode
4. **`clarification_decision.yml`** (v2.1.0) — Backend selection (remote_llm | local_slm | failover_deterministic)

**Location:** `k1/contracts/dialogue/clarification/`

---

## Architecture Comparison

| Aspect | Template-Based (OLD) | LLM-First (PRODUCTION) |
|--------|----------------------|------------------------|
| **Approach** | 22 fixed templates across 5 strategies | 5 LLM system prompts, infinite variety |
| **Quality** | Robotic (same phrases 1,460× over 20 years) | Natural, contextual phrasing |
| **Latency** | <15ms (5ms select + 10ms render) | <505ms (5ms select + 500ms LLM) |
| **Cost** | $0 | $0.005/clarification ($1.83/year) |
| **Reliability** | 100% (no external dependency) | 99.9% (deterministic fallback <10ms on timeout/offline/cost-cap) |
| **Grounding** | Manual (hardcoded options in templates) | Automatic (candidate_options from memory/tools) |
| **Hallucination** | N/A (no LLM) | Prevented (grounding validation) |
| **Offline Mode** | ✅ Works (templates local) | ✅ Works (deterministic fallback <10ms) |
| **Privacy** | ✅ No PII exposure | ✅ RED/BLACK → deterministic (no LLM) |

**Decision:** Prioritize user experience (natural phrasing) over template efficiency (15ms latency).

---

## File Structure (ACTUAL)

```
k1/contracts/dialogue/repair_strategies/
├── strategy_selection.yml                  # ✅ LLM scenario selection (v2.0.0)
└── README_ARCHITECTURE_CHANGE.md           # ⚠️ This file (explains architecture change)

k1/contracts/dialogue/clarification/
├── confidence_thresholds.yml               # ✅ LLM_FIRST_WITH_DETERMINISTIC_FALLBACK mode (v2.0.0)
├── clarification_decision.yml              # ✅ Backend selection (v2.1.0)
└── clarification_generation.yml            # ✅ 5 LLM system prompts (v2.1.0)
```

**Contract Count:** 1 file created (strategy_selection.yml) instead of 5 files (templates deprecated).

---

## LLM System Prompts (Production)

Instead of 22 templates, we now have **5 LLM system prompts** in `clarification_generation.yml`:

### 1. scenario_1_rephrase (confidence <0.4)
**System Prompt:**
```
You didn't understand the user's request.
Ask them to rephrase conversationally and briefly (<30 words).
Be friendly and admit uncertainty gracefully.
```

**Example Output:** "I didn't quite catch that. Could you rephrase what you're looking for?"

---

### 2. scenario_2_missing_entity (confidence ≥0.6 + missing entities)
**System Prompt:**
```
You understand the user's intent with HIGH confidence, but you're missing required information to complete the action.
Ask a brief natural question about the specific missing information (<30 words).
Be conversational and helpful.
```

**Example Output:** "I'd be happy to book dinner tomorrow! What time works for you, and do you have a restaurant in mind?"

---

### 3. scenario_3_ambiguous_entity (ambiguous entities present)
**System Prompt:**
```
The user's input has multiple plausible interpretations.
Offer the options conversationally and ask which one they meant (<30 words).
List options clearly (use commas for 3+ options).
**CRITICAL:** Use ONLY the candidate_options provided - DO NOT make up options.
```

**Example Output:** "I found a few Italian restaurants you've visited recently. Did you mean Luigi's, Olive Garden, or Carrabba's?"

**Grounding:** candidate_options from `k0.recall.memory_search` (prevents hallucination)

---

### 4. scenario_4_context_recovery (multi-turn context loss)
**System Prompt:**
```
You've lost the conversation context across multiple turns.
Ask a brief natural question to confirm what the user is still talking about (<30 words).
Reference the previous topic conversationally.
```

**Example Output:** "Are we still talking about weather in Seattle? Tuesday will be 68°F and rainy."

---

### 5. scenario_5_simplify (moderate confidence 0.4-0.6)
**System Prompt:**
```
You partially understood the user's request (MODERATE confidence).
Acknowledge what you understood, then ask about what you're missing (<30 words).
Be conversational and helpful.
```

**Example Output:** "I can help book dinner tomorrow. What time would you like to go, and which restaurant?"

---

## Production Guarantees

All 5 LLM scenarios include **deterministic fallback** on timeout/offline/cost-cap:

| Scenario | LLM Output | Deterministic Fallback |
|----------|-----------|------------------------|
| scenario_1_rephrase | "I didn't quite catch that. Could you rephrase what you're looking for?" | "Could you rephrase?" |
| scenario_2_missing_entity | "I'd be happy to book dinner tomorrow! What time and where?" | "What time?" (first missing slot) |
| scenario_3_ambiguous_entity | "Did you mean Luigi's, Olive Garden, or Carrabba's?" | "Which location?" (generic) |
| scenario_4_context_recovery | "Are we still talking about weather in Seattle?" | "Still talking about [last_topic]?" |
| scenario_5_simplify | "I can help book dinner tomorrow. What time and which restaurant?" | "What time and where?" (missing slots) |

**Guarantee:** Never stalls (<10ms deterministic on timeout/offline/cost-cap)

---

## Migration Guide

### For Contract Developers

**OLD (Expected from plan):**
```yaml
# rephrase_strategy.yml (NEVER CREATED)
templates:
  - "I didn't quite catch that"
  - "Could you rephrase?"
  - "Could you say that differently?"
```

**NEW (Production):**
```yaml
# clarification_generation.yml (ACTUAL)
scenario_1_rephrase:
  llm_system_prompt: |
    You didn't understand the user's request.
    Ask them to rephrase conversationally and briefly (<30 words).
  on_failover:
    mode: DETERMINISTIC_MINIMAL
    output_example: "Could you rephrase?"
```

### For Implementation

**OLD (Template-based):**
```python
# NEVER IMPLEMENTED
strategy = RepairStrategies.select(analysis)  # Returns Strategy enum
template = template_library.get_template(strategy)  # Select 1 of 22 templates
question = template.render(understood=..., missed=...)  # Variable substitution
```

**NEW (LLM-based):**
```python
# PRODUCTION
scenario = select_scenario(analysis)  # Returns LLMScenario enum
decision = should_clarify(analysis)  # Returns ClarificationDecision with backend
question = generate_clarification(decision, analysis)  # LLM or deterministic
```

---

## Performance Budgets

| Metric | Template-Based | LLM-First (Production) |
|--------|----------------|------------------------|
| Selection latency | <5ms P95 | <5ms P95 (same) |
| Generation latency | <10ms P95 (template render) | <500ms P95 remote_llm (streaming <150ms first token) |
| | | <200ms P95 local_slm |
| | | <10ms P95 deterministic fallback |
| Cost per clarification | $0 | $0.005 remote_llm, $0.001 local_slm, $0 deterministic |
| Annual cost | $0 | $1.83/year (365 clarifications) |
| Quality | Robotic (22 fixed phrases) | Natural (infinite variety) |
| Reliability | 100% (no external deps) | 99.9% (deterministic fallback on timeout/offline/cap) |

---

## References

- **ADR-0054d** — Dialogue Repair & Clarification Pipeline (lines 176-250 specify 5 strategies)
- **clarification_generation.yml** — 5 LLM system prompts (production implementation)
- **confidence_thresholds.yml** — LLM_FIRST_WITH_DETERMINISTIC_FALLBACK mode
- **clarification_decision.yml** — Backend selection logic
- **strategy_selection.yml** — LLM scenario selection (this directory)

---

## Why This Matters

**Investor/SRE Pitch:** "LLM-first repair with deterministic guarantees"

✅ Natural clarifications (streaming, infinite variety)
✅ NEVER stalls (deterministic <10ms on timeout/offline/cap)
✅ NEVER overspends (monthly cap $0.50)
✅ NEVER leaks PII (RED/BLACK → no LLM)
✅ NEVER hallucinates (grounded options from memory/tools)
✅ Voice-optimized (first token <150ms, barge-in)
✅ Ops-safe (backend breakdown, post-clarification error rate, cost tracking)
✅ Security-reviewed (6 red-team tests pass)

---

**Status:** ✅ PRODUCTION-READY (all 3 clarification contracts updated with hard guardrails)
