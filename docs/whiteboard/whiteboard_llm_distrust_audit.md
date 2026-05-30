# Whiteboard — LLM-Distrust Audit Triage

**Question for every item:** Does this belong in a **generic kernel** (domain-agnostic, instantiable for FamilyOS or any other domain)? Does it **make the LLM dumb** by overriding its capability, or does it provide a legitimate boundary the LLM cannot enforce alone?

**Mental model:**

- **Kernel-appropriate boundaries** = things the LLM physically *cannot* know or enforce: budgets (cost/latency SLO), safety/policy denials from external systems, schema validation against the actual tool registry, secret redaction.
- **Domain logic dressed as kernel rules** = keyword tables, intent classifiers, English vetoes, hardcoded fallback strings, "broad question → MUST call X" — these belong in a domain pack, not the kernel, and modern LLMs do this reasoning better than any frozenset.
- **Output mutilation** = always wrong in a kernel. If the model produces bad output, fix the prompt or the model, never silently rewrite the bytes.

Legend:

- **K?** = Belongs in generic kernel? (✅ yes / ⚠️ maybe-as-port / ❌ no)
- **Dumbs LLM?** = Does it override a capability modern LLMs have? (✅ yes / ⚠️ partially / ❌ no)
- **Verdict:** DELETE / REPLACE-WITH-PORT / KEEP / MOVE-TO-DOMAIN-PACK

---

## TIER 1 — HIGH severity (overrides / replaces / blocks LLM)

### Group A — Output scrubbers (mutilate LLM text post-generation)

| # | Item | K? | Dumbs LLM? | Verdict |
|---|------|----|-----------|---------|
| H1 | `_strip_leaked_reasoning` (regex strips "I will", "Based on", "Let me"…) | ❌ | ✅ | **DELETE** |
| H2 | `_strip_leaked_system_blocks` ([HIL Request], suspended notes) | ❌ | ✅ | **DELETE** |
| H3 | `_strip_leaked_back_frame` (<think>, JSON with task_id, tool traces) | ❌ | ✅ | **DELETE** |
| H4 | `_sanitize_result_summary` (keyword scan → canned "I couldn't finish") | ❌ | ✅ | **DELETE** |

**Pros (why they exist):**

- Cover for early model failures (leaked CoT, leaked structured frames, leaked tool names).
- Protect the user from "robot internals" appearing in the chat.

**Cons:**

- All four are **post-hoc surgery on bytes the LLM produced**. Definition-of-dumbing.
- Fragile: any legitimate use of words like "worker", "based on", or JSON in an answer is corrupted.
- A generalist kernel cannot know what "leaked" means for an arbitrary domain — these patterns are FamilyOS-specific superstitions.
- The right fix is **prompt discipline + output schema** (force structured output where it matters, free prose elsewhere). Modern LLMs comply with "respond in plain text, no JSON" without scrubbing.

**Kernel verdict:** A generic kernel must not own a "post-generation regex laundry". If a domain wants this, expose an optional `OutputFilter` port that the domain pack registers — but recommend not using it.

---

### Group B — Keyword classifiers replacing LLM intent parsing

| # | Item | K? | Dumbs LLM? | Verdict |
|---|------|----|-----------|---------|
| H5 | `_approval_decision_from_text` (approve/reject/modify/cancel by substring) | ❌ | ✅ | **DELETE** — let LLM emit a structured decision tool call |
| H6 | `_match_hil_option` (substring picks HIL option from raw answer) | ❌ | ✅ | **DELETE** — let LLM map answer→option via tool args |
| H7 | `InterruptClassifier` (frozenset cancel/chat) | ❌ | ✅ | **DELETE** entirely (already half-replaced) |
| H8 | `_DEFAULT_CANCEL_KEYWORDS` / `_DEFAULT_DEFER_KEYWORDS` | ❌ | ✅ | **DELETE** |
| H9 | `ConversationArbiter.classify` (full deterministic routing, zero LLM) | ❌ | ✅ | **REPLACE** with LLM-driven router OR thin port |
| H10 | `_handle_interrupt` (resolves all 4 branches before LLM) | ❌ | ✅ | **REFACTOR** — call LLM to classify, kernel only enforces the chosen branch |

**Pros:**

- Deterministic, no token cost, sub-millisecond.
- Predictable in tests.

**Cons:**

- This is **the exact same anti-pattern as the temporal-clarification flag we deleted**: non-LLM code makes the call, LLM is bypassed.
- "stop" in "stop making it so formal" triggers full CANCEL of all in-flight tasks. "sure, cancel it" matches both DEFER ("sure") and CANCEL ("cancel") — undefined behavior.
- A generic kernel cannot know which keywords mean cancel in Japanese, French, or domain-specific jargon. **This is domain logic in disguise.**
- Modern LLMs do intent classification *better* than any keyword table — and they handle negation, sarcasm, code-switching, and context.
- Phase-1 LLM intent classification was the stated intent (per the source docstring) but was never wired.

**Kernel verdict:** Keep an `IntentClassifierPort` interface, ship a **default LLM-backed implementation**, allow domains to plug in faster classifiers if they want. No keyword tables in the kernel.

---

### Group C — Kernel state machines that command the LLM

| # | Item | K? | Dumbs LLM? | Verdict |
|---|------|----|-----------|---------|
| H11 | `force_text` last-iter (strips ALL tools) | ⚠️ | ✅ | **REPLACE** with prompt hint, not hard removal |
| H12 | `force_submit` last-iter coercion message | ⚠️ | ⚠️ | **KEEP MILD** — natural-language "this is your last turn" is fine; don't hard-inject "MUST" |
| H13 | `_back_progress_nudge` (prescribes next tool from history) | ❌ | ✅ | **DELETE** |
| H14 | `context_read_gap_requires_dispatch` (synthesizes `dispatch_task` if LLM didn't) | ❌ | ✅ | **DELETE** — if LLM says "I don't know", honor it |
| H15 | `_SAFETY_REASONS` hard abort + canned "I can't help with that here." | ⚠️ | ⚠️ | **SPLIT** — keep the abort (kernel-enforced policy is legitimate), DELETE the canned text and let LLM phrase the denial |
| H16 | `ask_human_recovery_from_tool_data` auto-suspend | ✅ | ❌ | **KEEP** — tool contract field is structured signal, not LLM bypass |
| H17 | Dispatcher `submit_result(complete)` no-work guard | ⚠️ | ⚠️ | **SOFTEN** — return as feedback, let LLM decide; don't hard-reject |

**Pros:**

- Without `force_text`/`force_submit`, infinite loops are possible.
- Without `_SAFETY_REASONS`, denied tool calls would replay forever.
- Spin guards prevent token-burn loops.

**Cons:**

- `_back_progress_nudge` is the most egregious: a Python state machine writes "Now call X" to the LLM as a user-role message — pure puppetry. Modern LLMs given good tool descriptions choose the next tool correctly far more often than this state machine.
- `context_read_gap_requires_dispatch` literally **fabricates a tool call the LLM did not make**. This is the kernel lying about LLM intent in the trace.
- Canned "I can't help with that here." is FamilyOS voice baked into kernel — a generic kernel can't ship this string.

**Kernel verdict:**

- **Budgets and termination conditions** (iteration cap, time cap, cost cap) are legitimate kernel concerns — keep them as **soft signals in prompt** ("you have 1 iteration left") not **hard tool removal**.
- **Tool selection nudges** belong nowhere — delete.
- **Policy denials** are kernel-legitimate (the kernel knows what's blocked); the **response text** belongs to the LLM, not the kernel.

---

### Group D — Hardcoded fallback strings

| # | Item | K? | Dumbs LLM? | Verdict |
|---|------|----|-----------|---------|
| H18 | LLM timeout → `front_degenerate_fallback` string | ❌ | ✅ | **DELETE** — retry or surface error structurally |
| H19 | LLM ERROR finish → same string | ❌ | ✅ | **DELETE** |
| H20 | Validation failure → same string | ❌ | ✅ | **DELETE** — feed validation error back to LLM as tool result |
| H21 | Budget exhausted → `front_budget_fallback` | ⚠️ | ⚠️ | **KEEP** as last-resort safety net only — never as primary path |

**Pros:**

- Guarantees a string reaches the user even when everything fails.
- Test determinism.

**Cons:**

- Hides real failures from observability — every timeout returns the same string, masking patterns.
- The strings ("Let me think about that for a moment.", "Let me get back to you on that.") are **FamilyOS voice**. A generic kernel can't pick prose.
- Validation failure SHOULD trigger an LLM repair iteration (already a known pattern: feed the schema error back as a tool error message). Hardcoded string is lazy.

**Kernel verdict:** Kernel returns structured `error` events; **the domain renderer** turns them into prose. Optionally a last-resort emergency string for truly catastrophic states — but with telemetry that screams when it fires.

---

### Group E — Prompt-injected procedural vetoes

| # | Item | K? | Dumbs LLM? | Verdict |
|---|------|----|-----------|---------|
| H22 | `ANTI-PATTERNS (NEVER DO THESE)` block in BACK prompt | ⚠️ | ⚠️ | **SHRINK** — soft hints, not "NEVER" commandments |
| H23 | STEP 5 `PRACTICAL RULE` (verb-in-dispatch ⇒ approval=True) | ❌ | ✅ | **DELETE** — let LLM judge approval per-capability |
| H24 | `should_guess` + CLARIFY_DEPTH_BLOCKS[2] ("Do NOT ask again") | ❌ | ⚠️ | **SOFTEN** — surface "you've asked twice" as context, not commandment |
| H25 | `blocking_gaps > 0: You MUST ask` | ❌ | ✅ | **DELETE** — let LLM see the gaps and decide |
| H26 | `PROACTIVE_INTELLIGENCE` "you MUST call recall_memory() … non-negotiable" | ❌ | ✅ | **DELETE** — let LLM decide when it has enough |
| H27 | `REACT_RHYTHM FIRST-ITERATION DECISION` table | ❌ | ✅ | **DELETE** — that's a rule engine in prose |
| H28 | `GREETINGS (CRITICAL)` keyword list + "Do NOT offer help" | ❌ | ✅ | **DELETE** or move to domain pack persona |

**Pros:**

- "Procedural rules in prompt" feel more flexible than code, easier to tune.
- Compensates for older/smaller models that needed explicit guidance.

**Cons:**

- This is **the exact pattern of the TEMPORAL RESOLUTION POLICY block we deleted last session**. Same disease, different organ.
- A generalist kernel cannot ship "GREETINGS" persona rules — that's a domain pack.
- "MUST", "NEVER", "non-negotiable" are **certainty injections** that override the model's judgment on edge cases.
- Modern models (Claude 4, GPT-5 class) follow soft hints excellently and outperform rigid rules. The rigid rules force them to behave like rule engines, which is exactly when they get "dumb".

**Kernel verdict:** Kernel prompt = **role + tool schemas + termination signals**. Persona, manners, domain norms = **domain pack instructions**, supplied via a `PersonaProvider` port. The kernel itself ships no "MUST" / "NEVER" rules.

---

### Group F — Hard caps at API boundary (non-LLM math constrains LLM call)

| # | Item | K? | Dumbs LLM? | Verdict |
|---|------|----|-----------|---------|
| H29 | `apply_affect_hard_constraints` (caps `max_tokens`, `max_tool_calls`) | ⚠️ | ⚠️ | **SPLIT** — keep `max_tokens` (cost), DELETE affect-driven `max_tool_calls` |
| H30 | `tool_budget_override=2` for "crisis" affect | ❌ | ✅ | **DELETE** — affect classifier deciding tool budget is wrong layer |
| H31 | `EMOTIONAL_SUPPRESS_VALENCE` (valence < −0.5 → no WEAVE call) | ❌ | ✅ | **DELETE** — let LLM decide if WEAVE is appropriate |

**Pros:**

- Cost protection (token caps).
- Latency SLO during emotional crises (smaller responses → faster).
- "Don't be chatty when user is in crisis" is empathetic.

**Cons:**

- Affect band is computed by **another non-LLM heuristic** (keyword scans of dominance/valence). So heuristic → heuristic → hard cap. Compounding errors.
- A grieving user asking the system to actually do something complex gets capped at 2 tool calls regardless. Kernel deciding "you can only call 2 tools because the user seems sad" is **the kernel being smarter than it is**.
- "Don't be chatty in crisis" is a **persona decision**, not a kernel decision — and the LLM does empathetic brevity natively if asked.

**Kernel verdict:**

- **Cost/latency budgets** = kernel-legitimate, expressed as one knob (`max_tokens`, `max_iterations`) per request, set from SLO config not affect.
- **Affect-driven behavior modulation** = domain concern. Move affect modifiers into prompt context (LLM reads the affect band and adapts naturally), not into API params.

---

### Group G — Tool-schema filtering (LLM never sees options)

| # | Item | K? | Dumbs LLM? | Verdict |
|---|------|----|-----------|---------|
| H32 | `TOOL_ALLOWLIST` per-mode (`HITL_RELAY=[]`, etc.) | ⚠️ | ⚠️ | **REVIEW** — some modes truly are tool-free; others are over-restrictive |
| H33 | `get_tool_allowlist` confidence gate | ❌ | ✅ | **DELETE** — show LLM all relevant tools, let it choose |
| H34 | `_filter_back_tools` by tier | ❌ | ⚠️ | **DELETE** — tier-based gating is heuristic; better to show all + let LLM pick |
| H35 | `FORBIDDEN_SECTIONS` / `POLICY_EXCLUDED_OPERATIONS` | ✅ | ❌ | **KEEP** — data-integrity boundary the LLM cannot enforce |
| H36 | `evaluate_quality_gates` (14 numeric thresholds → eligibility) | ⚠️ | ⚠️ | **MOVE** to domain pack — quality SLOs are domain-defined |

**Pros:**

- Mode-based tool filtering reduces token cost and confusion.
- Quality gates protect production from regressed plans.
- Forbidden sections protect immutable data.

**Cons:**

- "User is in crisis" → "LLM cannot call `refine_affect`" is exactly the wrong direction. The LLM should call MORE refining tools when uncertainty is high, not fewer.
- Tier-bucket filtering means a "simple" task that escalates mid-flight has no tools to escalate with.
- 14 hardcoded thresholds are **definitely** domain config, not kernel constants.

**Kernel verdict:** Two legitimate kernel concerns: **policy denials** (the kernel knows what's forbidden) and **schema validity** (LLM can't call a tool that doesn't exist). Everything else (modes, tiers, quality gates) is **domain configuration** loaded into the kernel from a domain pack.

---

## TIER 2 — MEDIUM (bias / pre-empt LLM context)

| # | Item | K? | Dumbs LLM? | Verdict |
|---|------|----|-----------|---------|
| M1 | `_RELATED_DOMAINS` static dict | ❌ | ✅ | **DELETE** — embedding similarity or LLM judgment |
| M2 | `is_short_input` <3 words penalty | ❌ | ✅ | **DELETE** — semantically empty heuristic |
| M3 | `recall_memory ≥3` spin guard (prohibit further calls) | ⚠️ | ⚠️ | **SOFTEN** — surface count, don't prohibit |
| M4 | Back capability spin guard ≥2 | ⚠️ | ⚠️ | **SOFTEN** — same |
| M5 | `_is_pseudo` pattern detection → forced submit | ❌ | ✅ | **DELETE** — feed error back, let LLM correct |
| M6 | Scenario nudge text table (degenerate retry) | ❌ | ✅ | **DELETE** — generic retry message is fine |
| M7 | `classify_intents` `$ref` → CHAINED override | ⚠️ | ⚠️ | **KEEP** — `$ref` is a structural fact, but document it |
| M8 | `ALWAYS_SEQUENTIAL` static tool list | ⚠️ | ❌ | **MOVE** to tool metadata (each tool declares parallel-safe) |
| M9 | `ProactiveScheduler` affect+HITL suppression | ❌ | ⚠️ | **MOVE** to domain pack — proactivity policy is domain-defined |
| M10 | `ValidationDetector` regex polarity | ❌ | ✅ | **DELETE** — LLM does sentiment vastly better |
| M11 | `CorrectionDetector` regex patterns | ❌ | ✅ | **DELETE** — same |
| M12 | `ReformulationDetector` Jaccard | ❌ | ✅ | **DELETE** — semantic similarity needs embeddings or LLM |
| M13 | `AnticipatoryResponder` frequency-count hints | ❌ | ⚠️ | **DELETE** or move to domain pack |
| M14 | `NarrativeWeaver` frequency-rank "Continue thread" | ❌ | ⚠️ | **DELETE** or move to domain pack |
| M15 | `_infer_dominance` imperative-verb keyword scan | ❌ | ✅ | **DELETE** — LLM infers tone naturally from utterance |
| M16 | `CannedResponse` frozen string (circuit-breaker open) | ⚠️ | ⚠️ | **KEEP** as emergency-only, configurable |

**Pros (general):**

- Heuristic context (predicted intent, thread suggestion, polarity) can speed up the LLM.
- Spin guards are cheap insurance.

**Cons (general):**

- Almost every "heuristic context hint" is now **slower and worse than a small LLM call** at this layer.
- Regex-based feedback detectors are the same anti-pattern as the temporal-clarification flag: a non-LLM module forms a confident-feeling signal that biases the LLM, often in the wrong direction.

**Kernel verdict:** Tier 2 is mostly **misplaced heuristic stubs** that were placeholders for proper LLM-driven implementations. Default behavior: delete. Where a fast pre-LLM signal is genuinely useful, expose it as an optional port a domain pack can wire up.

---

## TIER 3 — LOW (cosmetic / infrastructure)

| # | Item | K? | Dumbs LLM? | Verdict |
|---|------|----|-----------|---------|
| L1 | `_SENSITIVE_KEY_PATTERN` redaction | ✅ | ❌ | **KEEP** — security hygiene, can't trust LLM to redact its own logs |
| L2 | `ProactiveAgent` template fill | ⚠️ | ⚠️ | **KEEP** as stub, mark for LLM upgrade |
| L3 | Episodic compressor default extractive | ⚠️ | ⚠️ | **KEEP** dual strategy, change default to LLM if available |
| L4 | `validator._attempt_fix` silent strip (Front path) | ❌ | ⚠️ | **FIX** — feed back to LLM like Back path |
| L5 | `_select_trigger_type` pre-assigns trigger category | ⚠️ | ⚠️ | **KEEP** — category is structural metadata, content still LLM-owned |
| L6 | `max_iterations_delta=-1` for crisis | ❌ | ⚠️ | **DELETE** — same family as Group F |

---

## Kernel Generalization Principles (derived from above)

A generic, domain-instantiable kernel SHOULD own:

1. **Tool registry + schema validation** (LLM can't invent tools).
2. **Policy enforcement** when policy comes from external systems (RBAC, allowlists, capability denials) — but **never the user-facing prose** for those denials.
3. **Budgets**: iteration cap, time cap, token cap, cost cap. Expressed as **soft signals in prompt** and **hard termination at cap** — never as mid-stream tool removal.
4. **Structured output validation** (schema, tool args) with **feedback loop** to LLM, never silent strip.
5. **Persistence + replay + tracing** of LLM I/O verbatim.
6. **Secret redaction** in observability surfaces.
7. **Tool execution sandbox** with timeouts, retries, idempotency keys.

A generic kernel MUST NOT own:

1. **Keyword tables** for intent / approval / cancel / sentiment / correction — these are language-specific and domain-flavored.
2. **Persona, voice, manners** — domain pack only.
3. **English vetoes** in system prompts ("NEVER", "MUST", "non-negotiable"). Use schemas and tool descriptions; let the LLM reason.
4. **Output regex scrubbers** — fix the prompt or the model, never the bytes.
5. **Hardcoded fallback strings** for user-facing prose — return structured errors; let domain render.
6. **Affect-driven API caps** — affect is a context feature, not a budget knob.
7. **Heuristic feedback detectors** (validation, correction, reformulation by regex) — these belong in an optional, swappable analysis stage with an LLM default.
8. **State-machine commands that puppet the LLM** ("now call X") — give it context, let it decide.

---

## Does this make modern LLMs dumb?

**Yes, in most Tier 1 and Tier 2 cases.** The patterns were written when models were weaker; they have outlived their justification. The current generation of LLMs (Claude 4-class, GPT-5-class, Gemini 2.5-class):

- Classifies intent better than any frozenset.
- Reasons about negation, sarcasm, and code-switching natively.
- Follows soft hints ("you have 1 iteration left, prefer to finalize") better than hard injected user-role coercion.
- Produces calibrated uncertainty (`needs_human_review` tool call) when given that affordance, without external counters.
- Respects "do not leak structured frames" in system prompt without post-hoc regex laundering.

The temporal-clarification cleanup proved the thesis: removing the procedural override made the system **more correct, not less**, because the LLM had the resolved windows in EXECUTION GROUNDING and only needed to be trusted to use them.

---

## Recommended order of deletion (high-impact, low-blast-radius first)

**Phase 1 — output scrubbers + canned fallback strings** (no behavioral coupling, immediate trust win)

- H1, H2, H3, H4, H18, H19, H20

**Phase 2 — prompt vetoes** (already touched this codepath last session)

- H22, H23, H25, H26, H27, H28
- H24 (soften, don't delete the depth tracking)

**Phase 3 — HIL keyword parsers → structured tool calls**

- H5, H6 (requires teaching Front to emit a structured decision)

**Phase 4 — interrupt arbiter rewrite**

- H7, H8, H9, H10 (biggest blast radius; design first)

**Phase 5 — kernel commanding LLM**

- H13, H14 (delete)
- H11, H12 (soften)
- H15 (split: keep abort, drop prose)
- H17 (soften to feedback)

**Phase 6 — affect-driven API caps**

- H29 (split), H30, H31

**Phase 7 — tool-schema filtering review**

- H33, H34 (delete), H36 (move to domain config), H32 (case-by-case)

**Phase 8 — Tier 2 heuristic detectors**

- Bulk delete M1, M2, M5, M6, M10, M11, M12, M13, M14, M15
- Soften M3, M4
- Move M8, M9 to per-tool metadata / domain pack

---

## Addendum — Hard Config Knobs / Kernel Overengineering

**Why this belongs in the same whiteboard:** hard config knobs are another form of LLM distrust and kernel distrust. A knob that encodes a magic behavior threshold, a FamilyOS-specific default, a duplicate budget, or a fake feature flag is the kernel saying "I already know the shape of this domain". That makes the kernel less general, makes behavior harder to reason about, and often constrains the LLM before it ever gets a chance to reason.

**Question for every config knob:** Is this a real deployment boundary, or is it a frozen opinion pretending to be tunable?

### Config TIER 0 — Active correctness bugs

| # | Item | Problem | Verdict |
|---|------|---------|---------|
| CB1 | `LlmConfig.default_max_tokens`: Python `4096` vs YAML `65536` | Silent 93% token budget cut if YAML load fails | **FIX** |
| CB2 | `delta_batch_window_ms`: `100` / `500` / `500` across concierge/kernel/loader | Three authorities for one batch window | **MERGE** |
| CB3 | `enable_ledger_recovery`: `True` in `ConciergeConfig`, `False` in `KernelConfig`, fallback forces `False` | Declared default is unreachable | **DELETE duplicate** |
| CB4 | `sessionstate/events.py` hardcodes `96KB`; tiers config says `104KB` | Wrong utilization math in emitted events | **FIX** |
| CB5 | `ProtocolsConfig.hil_timeouts`: annotated `dict[str, int]`, YAML uses float seconds | Type drift after migration | **FIX** |
| CB6 | `memory_writer/filter/rules.py` default `threshold=5` shadows config | Config knob is decorative | **WIRE or DELETE** |
| CB7 | `tier_budget` appears in YAML, `TaskConfig`, and `BackActorConfig` with different values | No single answer to "how much budget does a tier get?" | **MERGE** |

**Pros (why these exist):**

- They were probably added incrementally to preserve old tests during migrations.
- Duplicates make local modules easy to instantiate in isolation.
- YAML defaults give operators something visible to edit.

**Cons:**

- These are not philosophical issues; they are active correctness bugs.
- Duplicate defaults create false confidence. The code path only reads one source, while the other source rots.
- A generic kernel cannot have three independent opinions about the same budget, timeout, or batch window.

**Kernel verdict:** there must be one authority per operational concept. If a value is needed by many modules, pass a typed config object or port; do not redeclare the same primitive field everywhere.

---

### Config TIER 1 — Big-pile duplication / config god-objects

| # | Item | Problem | Verdict |
|---|------|---------|---------|
| CD1 | `section_update_*` cluster | 10 fields copied across `ConciergeConfig`, `KernelConfig`, and `SectionUpdateConfig` for a disabled-by-default feature | **Collapse to one `SectionUpdateConfig`** |
| CD2 | HIL timeouts | 5 timeout knobs repeated in `k1/hil/config.py`, `k1/planner/config.py`, `k1/concierge/config/kernel.py`, and request dataclasses | **HIL owns them** |
| CD3 | Retrieval `top_k` | `DEFAULT_K=10`, `MAX_K=25`, `TopKSelectorConfig`, `RetrievalEngineConfig`, and planner call sites repeat the same values | **One owner** |
| CD4 | Restore SLA `50ms` | `StorageConfig`, `ColdTierConfig`, and `ReconstructionConfig` repeat the same SLA | **Merge** |
| CD5 | `suspension_timeouts` and `hil_timeouts` | Same keys, same values, same units after migration | **Delete one** |
| CD6 | `cancel_keywords` | Duplicated in `ArbiterConfig` and `FsmConfig`; also belongs on the LLM-distrust delete list | **Delete** |
| CD7 | Temporal/spatial/grounding TTLs | `60_000` / `120_000` freshness knobs drift across three modules | **Shared freshness config** |
| CD8 | Circuit breaker configs | Memory writer, orchestrator, model hub, and degradation all invent their own breaker fields | **Shared `CircuitBreakerConfig`** |
| CD9 | `BusConfig` / `KernelConfig` naming collisions | Same class names in `kernel.py` and `loader.py`, different fields | **Unify public API** |
| CD10 | `KernelConfig` | ~60 fields, includes domain strings, feature flags, HIL timeouts, bus settings, test-mode knobs | **Decompose** |
| CD11 | `SessionStateSectionsConfig` | ~50 flat fields, budgets already drift vs tier budgets | **Delete class** |

**Pros:**

- Flat configs are easy to grep.
- Duplicated local defaults make unit tests less setup-heavy.
- God-objects are convenient during early bootstrapping.

**Cons:**

- The kernel is no longer generic if its config object contains FamilyOS defaults, selfmodel ontology strings, UI strings, and feature rollout flags.
- The same number repeated three times is not configurability. It is entropy.
- God-object config makes every subsystem depend on every other subsystem's knobs, which destroys module boundaries.
- The current shape hides errors: if one duplicate value is wrong, tests may still pass because the code path reads another copy.

**Kernel verdict:** config should mirror real ownership boundaries. If a module owns behavior, it owns one typed config. If a domain owns policy, it lives in a domain pack. The kernel should not be a warehouse of every historical rollout knob.

---

### Config TIER 2 — Magic constants pretending to be tables

| # | Item | Problem | Verdict |
|---|------|---------|---------|
| CM1 | `ToolsConfig.budget_limits` | 7 entries, all `400` | **Replace with one constant** |
| CM2 | `LlmConfig.model_selection_table` | 11 routes, all `gemini-2.5-flash` | **Delete table until real routing exists** |
| CM3 | `LlmConfig.model_hint_overrides` | `fast`, `smart`, `thinking`, `flash` all map to the same model | **Simplify** |
| CM4 | `ThrashConfig` | 6 thresholds encoding a 2x/4x scale | **One sensitivity knob or constants** |
| CM5 | `ExperienceConfig` cadences | `20`, `25`, `30` turn cadences that always covary | **Inline or one cadence base** |

**Pros:**

- Tables look future-proof.
- Operators can see the intended shape of future routing.

**Cons:**

- A table with one unique value is not a table. It is ceremony.
- Fake routing tables make the system look more flexible than it is.
- Future-proofing in config turns into present-day maintenance cost.

**Kernel verdict:** do not ship shape for futures that do not exist. Use one value now; add a table when there is a real second value.

---

### Config TIER 3 — Domain values inside generic kernel config

| # | Item | Problem | Verdict |
|---|------|---------|---------|
| KD1 | `selfmodel_space_id = "family:default"` | FamilyOS ontology string inside generic kernel config | **Move to domain pack** |
| KD2 | `selfmodel_situation_kind = "caregiver_context_briefing"` | FamilyOS scenario label in kernel | **Move to domain pack** |
| KD3 | `enable_family_tools`, `family_tools_db_path`, `family_tool_service_paths` | FamilyOS tool wiring in kernel config | **Move to `FamilyToolsConfig`** |
| KD4 | `OrchestratorConfig.canned_response_text` | User-facing FamilyOS prose in generic orchestrator config | **Move to UI strings/domain renderer** |
| KD5 | `memory_writer.model_hint = "gemini-2.5-flash"` | Provider-specific model name in generic memory writer | **Resolve through model hub** |
| KD6 | `active_member_id` | Runtime session state stored as boot config | **Move to session context** |

**Pros:**

- Fast path to make FamilyOS boot without more plumbing.
- Fewer manifests during early development.

**Cons:**

- This directly violates the "generic kernel can instantiate any domain" goal.
- Domain defaults become invisible because they look like kernel defaults.
- Model/provider names in generic modules make the kernel non-portable.

**Kernel verdict:** the kernel can define ports and schema. The domain pack supplies ontology, persona, tool bundles, UI strings, model policy, and member/session identity.

---

### Config TIER 4 — Feature flags for always-on / always-off code

| # | Item | Default | Verdict |
|---|------|---------|---------|
| CF1 | `hil_enable_audit_topic` | `True` | **Delete; audit is fundamental** |
| CF2 | `hil_enable_llm_synthesis` | `True` | **Delete; synthesis is fundamental** |
| CF3 | `bridge_offline_ok` | `True` | **Delete if there is no real online-required mode** |
| CF4 | `system_bus_enabled` | `True` | **Delete; observability bus should be unconditional** |
| CF5 | `WeavePolicyConfig.enabled` | `True` | **Delete; fallback mode is not meaningful** |
| CF6 | `enable_activity_profiles_strict` | `False` | **Move to test fixtures** |
| CF7 | `enable_llm_relay_rewrite` | `False`, no readers | **Delete** |
| CF8 | `enable_front_fast_path` | `True` | **Inline fast path** |
| CF9 | `enable_self_model` | `False` to preserve tests | **Delete when feature is real, or mark experimental outside prod config** |
| CF10 | `extraction_mode = "session_batch"` | Legacy `per_turn` only for tests | **Delete production branch** |

**Pros:**

- Flags feel safe during migrations.
- They let tests keep old behavior while new behavior lands.

**Cons:**

- Once the migration ends, flags become archaeological layers.
- Always-true flags are not configuration; always-false flags are unfinished code.
- Feature flags in generic config are especially poisonous because every domain now inherits old rollout scaffolding.

**Kernel verdict:** short-lived rollout flags belong in migration branches or test fixtures. Long-lived flags must represent real deployment modes with real users.

---

### Config TIER 5 — Dead knobs and uninjected magic

| # | Item | Problem | Verdict |
|---|------|---------|---------|
| CN1 | Orchestrator MCP/admin/log knobs (`mcp_config_path`, `admin_port`, `trace_propagation`, `structured_log_level`, etc.) | No readers outside validation/config | **Delete until implemented** |
| CN2 | `sessionstate/eviction.py` module constants | Comments point to config; runtime reads config, constants are ghosts | **Delete constants** |
| CN3 | `ReconstructionConfig` | Shadowed by module constants/tests | **Choose config or constants, not both** |
| CN4 | `soft_ranker.py` weights | Ranking policy is hardcoded and uninjected | **Move to ranker config or document as fixed algorithm** |
| CN5 | `hard_filter.py DEFAULT_SATISFIABILITY_THRESHOLD = 0.5` | Arbitrary threshold drops capabilities | **Move to config/port** |
| CN6 | `embedding_index.py DEFAULT_DIMENSION = 384`, IVF constants | Model dimension and FAISS tuning are hardcoded | **Resolve from model/index config** |
| CN7 | Spatial confidence literals (`0.72`, `0.65`, `0.45`, etc.) | Mini prior table hidden in code | **Name or configure priors** |
| CN8 | Selfmodel confidence/TTL constants | Trust and identity policy hardcoded | **Move to domain/trust config** |
| CN9 | `local_events.py queue.Queue(maxsize=10000)` | Inline buffer cap | **Name or configure** |

**Pros:**

- Some constants are legitimate algorithm parameters.
- Keeping them in code prevents endless tuning without data.

**Cons:**

- Dead knobs are worse than constants: they imply control that does not exist.
- Uninjected magic in hot paths makes deployment behavior impossible to tune without code edits.
- Trust scores, identity TTLs, and spatial confidence priors are policy, not generic kernel facts.

**Kernel verdict:** algorithmic constants can stay constants if they are part of the algorithm and documented. Policy constants must move to domain/trust config. Dead knobs should be deleted immediately.

---

### Config TIER 6 — Heuristic thresholds for heuristics that should not exist

| # | Item | Problem | Verdict |
|---|------|---------|---------|
| CH1 | `default_affect_confidence = 1.0` | Missing affect becomes max confidence | **Delete / use absence** |
| CH2 | `ep_skip_confidence_threshold = 0.8` | Combines with CH1 so EmotionalProcessor skips by default | **Delete** |
| CH3 | `default_fsm_state = "DISPATCHING"` | Masks session initialization bugs | **Delete; fail loudly** |

**Pros:**

- Smooths over missing data.
- Avoids crashes during early integration.

**Cons:**

- These are exactly the knobs that make the system feel haunted: absent data becomes confident state.
- They create downstream behavior that looks intentional but came from a fallback.

**Kernel verdict:** missing required state should be explicit. Unknown means unknown, not max-confidence default.

---

## Config Generalization Principles

A generic kernel SHOULD own config for:

1. **Real resource limits**: max iterations, timeouts, total cost, queue sizes, bounded buffers.
2. **Actual external endpoints**: tool registry URL, model hub provider config, storage adapter config.
3. **Security controls**: redaction, sandboxing, policy enforcement, audit transport.
4. **Algorithm parameters only when the algorithm is genuinely kernel-owned** and the parameter is documented.
5. **One typed config object per owning module**, passed explicitly.

A generic kernel MUST NOT own config for:

1. **Domain ontology**: `family:default`, caregiver situation labels, member IDs.
2. **Persona or prose**: canned responses, greeting style, denial text.
3. **Provider-specific model defaults inside generic modules**: generic modules ask for capabilities; model hub chooses providers.
4. **Fake routing tables with one unique value**.
5. **Migration flags that are always true/false after rollout**.
6. **Duplicate primitive knobs** copied across layers.
7. **Fallbacks that convert missing state into confident state**.

**Rule of thumb:** if a knob will not be changed by a real deployment owner, delete it or inline it. If it will be changed by a domain owner, move it out of the generic kernel. If it will be changed by the kernel runtime owner, keep exactly one copy.

---

## Combined Cleanup Order

**Config Phase C0 — correctness bugs first**

- Fix CB1-CB7 before broad deletion, because these can skew tests and runtime behavior.

**Config Phase C1 — collapse duplicate authorities**

- CD1, CD2, CD4, CD5, CD7, CD8, CD9.

**Config Phase C2 — delete fake tables and dead flags**

- CM1-CM5, CF1-CF8, CN1-CN3.

**Config Phase C3 — domain extraction**

- KD1-KD6 into a FamilyOS/domain pack boundary.

**Config Phase C4 — god-object breakup**

- CD10, CD11 after duplicates are removed so the blast radius is smaller.

**Config Phase C5 — policy constants and heuristic thresholds**

- CN4-CN9 and CH1-CH3.

**Combined principle:** delete LLM-distrust rules and config bloat in the same direction: fewer fake decisions in the kernel, more explicit ports, more verbatim LLM I/O, and one authority per real operational boundary.

---

## Open questions for you before any deletion

1. **Persona ownership**: should the kernel ship a `PersonaProvider` port and FamilyOS register its persona there, OR should the kernel have zero persona awareness and the domain wrap it?
2. **Intent classification port**: LLM-default with optional fast classifier override, or just "always LLM"?
3. **Affect modifiers**: is affect a *context feature* (rendered into prompt for LLM to adapt) or a *budget feature* (caps the call)? Recommend the former.
4. **Quality gates**: live in a domain config file (YAML) instead of `vocabulary.py`/`quality_gates.py` constants?
5. **Phase order**: agree with the 8-phase order above, or prioritize differently?
6. **Config ownership**: should `k1/concierge/config/loader.py` become the single typed config authority, or should each subsystem own its own config and the loader only compose them?
7. **Domain pack boundary**: should FamilyOS-specific values (`family:default`, caregiver situation kind, family tools DB path, UI strings) move into one explicit `familyos` domain pack now?
8. **Feature flags**: should always-on/always-off flags be deleted immediately, or first marked with expiry comments and removed in a second pass?
9. **Constants vs config**: for algorithmic values like ranker weights and FAISS params, do we prefer fixed documented constants until data exists, or typed config with domain overrides?
10. **Cleanup interleave**: do config correctness fixes happen before LLM-distrust deletions, or do we continue with the already-planned LLM-distrust Phase 1 first?
