# Capability Search Algorithm — Design Whiteboard

**Date:** 2026-06-11
**Status:** MEASURED — 100-query tiered benchmark executed
**Benchmark:** `scripts/bench_resolver_search.py`
**Scope:** How `resolve_situation` narrows to the right TOOL (not just the right connector).

---

## ⚠️ METRIC CORRECTION — Tool Accuracy Is Primary

The benchmark initially reported **connector accuracy (66%)**. This is a puddle-jump metric.
It answers "did we get the user to the right aisle?" not "did we put the right product in
their hand?"

**Tool accuracy is 20% (20/100).** That's the real number. If the user says "add eggs to
shopping list" and the resolver returns `create_list` instead of `add_item`, that's a
FAILURE — even though both are `family.shopping`. The user gets the wrong action executed.

**From this point forward:**
- **M0 = Tool Accuracy**: did we return the EXACT correct capability?
- **M1 = Connector Accuracy (diagnostic)**: did we at least get the right connector?
  Useful for diagnosing WHERE failures happen: wrong connector vs wrong tool within connector.

---

## 2026-06-11 Benchmark Results (100 queries, 5 tiers)

### Tiered Accuracy

| Tier | Queries | Tool OK | Tool% | Conn OK | Conn% | Blocked | Avg ms |
|------|---------|---------|-------|---------|-------|---------|--------|
| EASY (perfect hints) | 20 | 7 | **35.0%** | 20 | 100.0% | 0 | 13.3 |
| MEDIUM (natural lang) | 20 | 6 | **30.0%** | 18 | 90.0% | 0 | 13.5 |
| HARD (1 field wrong) | 20 | 2 | **10.0%** | 12 | 60.0% | 0 | 26.4 |
| ULTRAHARD (2+ wrong) | 20 | 0 | **0.0%** | 8 | 40.0% | 0 | 29.4 |
| HARDEST (adversarial) | 20 | 5 | **25.0%** | 8 | 40.0% | 14 | 20.8 |
| **OVERALL** | **100** | **20** | **20.0%** | **66** | **66.0%** | **14** | **20.7** |

MRR: 0.180 overall (0.350 easy, 0.300 medium, 0.100 hard, 0.000 ultrahard, 0.150 hardest).

### Tier Definitions

| Tier | LLM Hallucination Profile | What's Tested |
|------|--------------------------|---------------|
| **EASY** | None — perfect domain/rf/op_hint | Baseline 5-stage pipeline accuracy |
| **MEDIUM** | None — but action text uses indirect phrasing, slang, synonyms | FTS5 robustness to vocabulary drift |
| **HARD** | ONE field wrong (wrong domain, OR wrong resource_family, OR wrong op_hint) | Resolver robustness to single poisoned hint |
| **ULTRAHARD** | TWO+ fields wrong (wrong domain + wrong rf, wrong rf + wrong op, or all three) | Resolver fallback when most hints are wrong |
| **HARDEST** | Adversarial — all hints empty, nonsensical (`domain="xyzzy"`, `rf="plumbus"`, `op="fleeb"`), or multi-intent with hallucinated second intent | FTS5-only resolution with zero valid hints |

---

## Experiment #1: Hypothesis Combo (K2 no-domain + K5 all-tools + K8 return-all + K9 advisory)

**Date:** 2026-06-11
**Knobs:** `domain_mode=no-domain`, `return_mode=all-tools-for-connector`, `fallback_mode=return-all-connectors`, `gate_mode=advisory-only`
**Command:** `python scripts/bench_resolver_search.py --hypothesis`

### Results

| Metric | Baseline | Hypothesis | Δ |
|--------|----------|------------|---|
| ★ Tool Accuracy | 20.0% | 19.0% | **-1.0%** |
| Connector Accuracy | 66.0% | 66.0% | 0.0% |
| Blocked Rate | 14.0% | 1.0% | **-13.0%** ↓ |
| MRR | 0.180 | 0.189 | +0.009 |
| Avg Latency | 20.7ms | 24.6ms | +3.9ms |

### Tier Breakdown (Hypothesis)

| Tier | Tool OK | Tool% | Δ vs Baseline | Blocked |
|------|---------|-------|---------------|---------|
| EASY | 7 | 35.0% | 0% | 0 |
| MEDIUM | 6 | 30.0% | 0% | 0 |
| HARD | 2 | 10.0% | 0% | 0 |
| ULTRAHARD | 0 | 0.0% | 0% | 0 |
| HARDEST | 4 | 20.0% | -5% | 1 (was 14) |

### Analysis

**What worked:**
- **K8 (return-all-connectors)**: Blocked rate dropped from 14% → 1%. All 13 `missing_capability`
  verdicts in HARDEST tier are now `can_execute` with all 52 tools returned. Back LLM has
  full agency instead of a dead end. This is a pure win — never block, always return options.
- **K5 (all-tools-for-connector)**: Individual tool selections improved within correct
  connectors. `easy-shop-01` ("add eggs") now correctly returns `add_item` instead of
  `create_list`. `easy-shop-04` ("check off bread") now returns `check_off_item` instead
  of `update_item`. The heuristic for connector selection combined with full-tool-list
  expansion works for within-connector accuracy.

**What didn't work:**
- **K2 (no-domain) had ZERO effect on connector accuracy.** The 34 wrong-connector
  failures are identical between baseline and hypothesis. Removing the domain filter
  doesn't help because:
  1. Resource_family and operation_hint are STILL hard filters in graph traversal.
     Wrong rf="reminder" for a calendar query still routes to reminders connector.
  2. FTS5 fallback STILL returns zero results even with domain=''. The BM25 text
     search on capability descriptions doesn't match natural language queries like
     "put paper towels on the grocery run" against "Add an item to a shopping list".
     The vocabulary gap is lexical, not domain-related.
- **K9 (advisory-only) had no measurable effect** — the baseline already had 0 hard
  blocks from gate verdicts (all blocks were `missing_capability`, not gate-related).

**Conclusion:** K2+K5+K8+K9 is NOT sufficient. The graph traversal's resource_family
and operation_hint hard filters are the next bottleneck. We need:
- **K3 (no-rf)**: Skip resource_family filtering — let text matching find the connector
- **K4 (no-op)**: Skip operation_hint filtering
- **K11 (embedding search)**: BM25 can't bridge the vocabulary gap between natural
  language queries and structured capability descriptions. Even MiniLM (22MB) would
  understand that "put paper towels on the grocery run" ≈ "add_item to shopping list".

---

## Experiment #2: Remove All Hard Filters (K2 no-domain + K3 no-rf + K4 no-op + K5 all-tools + K8 return-all + K9 advisory)

**Date:** 2026-06-11
**Knobs:** `domain_mode=no-domain`, `rf_mode=no-rf`, `op_mode=no-op`, `return_mode=all-tools-for-connector`, `fallback_mode=return-all-connectors`, `gate_mode=advisory-only`
**Command:** `python scripts/bench_resolver_search.py --hypothesis` (after K3+K4 implementation)

### Results

| Metric | Baseline | Exp #1 (K2+K5+K8) | Exp #2 (+K3+K4) |
|--------|----------|--------------------|--------------------|
| ★ Tool Accuracy | 20.0% | 19.0% | 19.0% |
| Connector Accuracy | 66.0% | 66.0% | **64.0%** ↓ |
| Blocked Rate | 14.0% | 1.0% | 1.0% |
| MRR | 0.180 | 0.189 | 0.189 |
| Avg Latency | 20.7ms | 24.6ms | 16.1ms |

### Tier Breakdown

| Tier | Baseline Conn | Exp #1 Conn | Exp #2 Conn | Δ |
|------|-------------|------------|------------|---|
| EASY | 100.0% | 100.0% | 100.0% | 0% |
| MEDIUM | 90.0% | 90.0% | **95.0%** | +5% ↑ |
| HARD | 60.0% | 60.0% | 60.0% | 0% |
| ULTRAHARD | 40.0% | 40.0% | **30.0%** | -10% ↓ |
| HARDEST | 40.0% | 40.0% | **35.0%** | -5% ↓ |

### Analysis

**What improved:**
- **MEDIUM connector accuracy: 90% → 95%.** `med-cross-01` ("make sure I don't forget
  to buy milk") correctly resolved to `family.reminders` instead of `family.shopping`.
  K3+K4 removed the resource_family/operation filters that were routing this query
  through the wrong graph path.

**What got WORSE:**
- **ULTRAHARD connector accuracy: 40% → 30%.** With ALL filters removed, the typed
  capability lookup returns ALL 52 capabilities unfiltered. `_select_best_capability()`
  faces the entire catalog and picks based on fragile heuristics (first-word match,
  operation starts_with). More noise = more wrong picks.
- **HARDEST connector: 40% → 35%.** Same problem — 13 queries that previously
  hard-blocked (`missing_capability`) now soft-block with wrong connector picks.

**Critical insight — Filters can't be REMOVED, they must be REPLACED:**

The graph traversal filters (domain, resource_family, operation_family) were wrong
65% of the time, but they at least **narrowed the search space** from 52 caps to
2–5 caps. Removing them without adding a better ranking engine turns the resolver
into a random picker.

The correct sequence is:
1. **FTS5 or embedding search** on action text → ranked capability list
2. **Group by connector** → connector ranking with confidence scores
3. **Return top connector's tools** for Back to pick from
4. `_select_best_capability` only runs within the top connector's 4–11 tools

Without step 1 (better search), steps 2–4 are useless. **K11 (embedding search) is
the prerequisite for removing filters.** We can't skip it.

### Next Steps

**K11 must come before any further filter removal experiments.** The options:
- **MiniLM (22MB)**: `pip install sentence-transformers`, embed action text + all 52
  capability descriptions once at boot, cosine similarity at query time. Expected to
  handle "scratch that board meeting" → delete_event, "put paper towels on the
  grocery run" → add_item.
- **FTS5 + trigram + richer index (K6+K7)**: Zero-dependency alternative. Add
  action_names, connector labels, concept aliases to FTS5 index. Use trigram
  tokenization for typo tolerance. Won't handle synonyms but may handle typos
  and short queries.

---

## Key Findings

### Finding #1: The Cliff Is Real — Accuracy Collapses with Hint Degradation

```
Tool accuracy:  35% → 30% → 10% → 0% → 25%
Conn accuracy: 100% → 90% → 60% → 40% → 40%
```

The resolver is **tightly coupled to LLM hint quality**. When the LLM hallucinates,
the resolver follows the hallucination into the wrong connector AND the wrong tool.
The sharpest drop is between MEDIUM (30%) and HARD (10%) — just ONE wrong field
cuts tool accuracy by 67%.

### Finding #2: Even Perfect Hints → Only 35% Tool Accuracy

With the LLM giving PERFECT domain/resource_family/operation_hint, the resolver
picks the wrong tool **65% of the time**. The 5-stage pipeline does NOT reliably
map intent→capability even under ideal conditions.

**Root cause:** Stage 4 (Capability Binder) uses `_select_best_capability()` with
fragile heuristics:
1. action_text first-word hint (e.g., "add" → prefers `add_item`)
2. operation starts_with match
3. operation contains match
4. non-generic preference
5. `caps[0]` fallback

These heuristics can't distinguish `add_item` from `create_list` when the LLM sets
`operation_hint="create"`. The user says "add eggs" but `create_list` wins because
"create" matches its operation family. The action_text hint ("add") should override
but it's only a first-word check, not a semantic match.

### Finding #3: Domain-Scoped FTS5 Is THE Root Cause of the Cliff

Stage 2 (Type Resolution) performs **domain-scoped FTS5**. When the LLM hallucinates
`domain="healthcare"`, FTS5 searches for capabilities in the healthcare domain — which
has ZERO capabilities. Even the FTS5 fallback path STILL filters by domain:

```
resolver step4: graph MISS domain='healthcare' rf=event op=fleeb effect=read
  → trying FTS5 query='schedule dentist for Friday'
resolver step4: FTS5 MISS domain='healthcare' action='schedule dentist for Friday'
  → no matches
```

The FTS5 query text is correct ("schedule dentist for Friday") but it's scoped to
a dead domain. Same for empty-domain queries — `domain=''` means `WHERE domain=''`
which matches nothing because 100% of capabilities have `domain="family"`.

**Fix:** Domain-agnostic FTS5. When graph traversal fails, search ALL domains.
Domain hint becomes a BM25 boost multiplier, never a WHERE filter.

### Finding #4: `missing_capability` Blocks Are FTS5 Text-Scarcity Failures

The 14 hard-blocks in HARDEST are all `missing_capability`. Two-word queries
("calendar this week", "my tasks") don't have enough text overlap with capability
descriptions for BM25 to score. The index has rich descriptions like "List calendar
events within a time window..." but 2-word queries can't hit them.

**Fix:** Index connector labels, action_names, and concept aliases alongside
descriptions. For very short queries (≤3 words), use prefix matching. As a last
resort, return ALL connectors (6 connectors → trivial for Back to scan).

### Finding #5: Single-Capability Return → No Ranking → MRR = Precision

`allowed_capability_names` has exactly 1 entry (the primary binding). There's no
ranked list for Back to choose from. The resolver makes a binary decision and Back
gets whatever it picked. MRR is effectively precision because rank is always 1 or nothing.

**Fix:** Return ALL tools for the matched connector. Back reads descriptions and
picks the right one. MRR becomes meaningful because there IS a ranked list.

### Finding #6: Latency Is Not the Problem

Average 20.7ms per resolve. Even worst-case (ultrahard, 29.4ms) is well under budget.
**All investment should go to accuracy, not speed.**

---

## Control Knobs Matrix — What We Can Dial

Every row is an independent variable. No heuristics. Each knob has a current
position (the baseline we measured at 20% tool accuracy) and alternative
positions. We test each position, measure M0 (tool accuracy) and M3 (blocked
rate), and converge on the optimal combination.

### K1: Search Method

**What it controls:** How the resolver maps intent → capability candidates.

| Position | Description | Predicted M0 | Predicted M3 |
|----------|-------------|-------------|-------------|
| **graph-only** (current) | Concept→resource→connector→capability graph traversal. Fails hard when any hint is wrong. | 20% (baseline) | 14% |
| graph→FTS5 fallback | Graph first. On miss, FTS5 text search (domain-scoped — current bug). | 20% (same) | 14% |
| FTS5-only | Skip graph entirely. FTS5 BM25 on indexed tool text. Domain-agnostic. | ? | ? |
| FTS5→graph refine | FTS5 finds connector. Graph traversal within that connector only to verify resource_family/operation compatibility. | ? | ? |

**Test:** Run benchmark with `SEARCH_METHOD` env var. Compare M0 per tier.

### K2: Domain Handling

**What it controls:** How the domain hint from the LLM is used in search.

| Position | Description | Predicted M0 | Predicted M3 |
|----------|-------------|-------------|-------------|
| **hard-filter** (current) | `WHERE domain = X`. Wrong domain → zero results → block or wrong connector. | 20% (baseline) | 14% |
| boost-2x | Domain match multiplies BM25 score by 2.0. Mismatch gets raw BM25 score — still findable. | ? | ? |
| boost-1.5x | Domain match multiplies by 1.5. Weaker signal, more weight on text match. | ? | ? |
| no-domain | Domain hint ignored entirely. Pure text search. Tests: is domain hint useful at all? | ? | ? |
| domain-as-tiebreaker | Domain only used to break ties when BM25 scores are within 10% of each other. | ? | ? |

**Test:** Run benchmark with `DOMAIN_MODE` env var. Key question: does domain hint
help (higher M0 with boost) or hurt (higher M0 with no-domain)?

### K3: Resource Family Handling

**What it controls:** How `resource_family` hint is used.

| Position | Description | Predicted M0 | Predicted M3 |
|----------|-------------|-------------|-------------|
| **hard-filter** (current) | `WHERE resource_family = Y`. Wrong rf → graph miss, FTS5 fallback still domain-scoped. | 20% (baseline) | 14% |
| boost-2x | Rf match boosts BM25 score. Mismatch still searchable. | ? | ? |
| no-rf | Rf hint ignored entirely. | ? | ? |

**Test:** Run benchmark with `RF_MODE` env var. Is resource_family a useful signal
or a liability?

### K4: Operation Hint Handling

**What it controls:** How `operation_hint` (read/create/update/delete) is used.

| Position | Description | Predicted M0 | Predicted M3 |
|----------|-------------|-------------|-------------|
| **hard-filter** (current) | `WHERE operation_family = Z`. Wrong op → wrong capability within right connector. | 20% (baseline) | 14% |
| boost-1.5x | Op match boosts. "read" won't block "create" tools, just rank them lower. | ? | ? |
| no-op | Op hint ignored. Back picks tool based on action text + tool descriptions. | ? | ? |

**Test:** Run benchmark with `OP_MODE` env var. Does op_hint actually help tool
selection, or is it noise that the LLM hallucinates?

### K5: Return Mode

**What it controls:** What the resolver returns to Back.

| Position | Description | Predicted M0 | Predicted M3 |
|----------|-------------|-------------|-------------|
| **single-capability** (current) | `_select_best_capability()` picks ONE winner. Back gets binary choice. | 20% (baseline) | 14% |
| all-tools-for-connector | Return ALL tools for the matched connector (4–11 tools). Back reads descriptions, picks one. | ? | ? |
| top-3-connectors | Return top-3 connectors (BM25-ranked), each with ALL their tools. Back sees 12–33 tools total. | ? | ? |
| top-1-with-fallback | Return best connector's tools. If Back can't pick, it can request alternatives (search_confidence < 0.5). | ? | ? |

**Test:** This is the BIG knob. Run benchmark with `RETURN_MODE` env var. H3 says
all-tools-for-connector + Back picking gives ≥99% tool accuracy. Measure it.

### K6: FTS5 Index Content

**What it controls:** What text is indexed for BM25 search.

| Position | Description | Predicted M0 | Predicted M3 |
|----------|-------------|-------------|-------------|
| **descriptions-only** (current) | Only `capability.description` text in FTS5 index. | 20% (baseline) | 14% |
| +action_names | Add `action_name` field ("add_item", "list_events"). | ? | ? |
| +connector_meta | Add `connector_id`, `connector_label`, `connector_description`. | ? | ? |
| +concept_aliases | Add ontology concept aliases ("groceries", "buy", "shopping list"). | ? | ? |
| +all | All of the above. Rich index — more hits, more noise. | ? | ? |

**Test:** Rebuild GPS index with `INDEX_CONTENT` env var. Re-run benchmark.
Does richer index help (more text = more hits) or hurt (more noise = lower precision)?

### K7: FTS5 Query Construction

**What it controls:** What query string we send to FTS5.

| Position | Description | Predicted M0 | Predicted M3 |
|----------|-------------|-------------|-------------|
| **action-text-only** (current) | Query = user's action text as-is. | 20% (baseline) | 14% |
| action+op_terms | Append operation hint as OR-terms. "add eggs" becomes "add eggs OR create OR add". | ? | ? |
| prefix-matching | For queries ≤3 words, use `prefix*` matching. "cal" matches "calendar". | ? | ? |
| weighted-fields | BM25 with field weights: action_name^3, concept_aliases^2, description^1. | ? | ? |

**Test:** Run benchmark with `QUERY_MODE` env var.

### K8: Fallback / Safety Net

**What it controls:** What happens when all search paths fail (zero results).

| Position | Description | Predicted M0 | Predicted M3 |
|----------|-------------|-------------|-------------|
| **hard-block** (current) | `missing_capability` verdict. Back gets nothing. | 20% (baseline) | 14% |
| return-all-connectors | Return ALL 6 connectors with ALL their tools (52 tools total). Back has full agency. | ? | ? |
| return-all-readonly | Return all READ tools across all connectors. Safe fallback — can't mutate, can only read. | ? | ? |
| hil-escalate | Trigger HIL: "I couldn't figure out what you want. Can you rephrase?" | ? | ? |

**Test:** Run benchmark with `FALLBACK_MODE` env var. Key question: is returning
all 52 tools better than blocking? (Back has an 8-tool-call budget.)

### K9: Constitution & Gate Injection

**What it controls:** How prerequisites, companions, and safety gates are presented.

| Position | Description | Predicted M0 | Predicted M3 |
|----------|-------------|-------------|-------------|
| **blocking-gates** (current) | 13-step verdict cascade can return `can_execute_with_gate`, `needs_hil`, `missing_required_params`. | 20% (baseline) | 14% |
| advisory-only | All gates are `required: false`. Verdict is ALWAYS `can_execute`. Prereqs are suggestions. | ? | 0% |
| no-constitution | No prerequisites, no companions, no gates. Just tools. Back has full freedom. | ? | 0% |

**Test:** Run benchmark with `GATE_MODE` env var. Does removing gates improve
tool accuracy? Or do gates help Back make better decisions?

### K10: Multi-Intent Strategy

**What it controls:** How multiple intents in one frame are resolved.

| Position | Description | Predicted M0 | Predicted M3 |
|----------|-------------|-------------|-------------|
| **independent** (current) | Each intent resolved separately. Results merged. | 20% (baseline) | 14% |
| primary-only | Resolve only the first intent. Ignore hallucinated second intents. | ? | ? |
| union-connectors | Resolve all intents, return union of all matched connectors' tools. | ? | ? |

**Test:** The 4 multi-intent queries in HARDEST tier. Measure which strategy
best handles hallucinated second intents.

### K11: Retrieval Backend — Lexical → Semantic Spectrum

**What it controls:** The underlying search engine. FTS5 is BM25 (lexical, exact
word matching). Embedding models add semantic understanding — "pencil in" ≈ "schedule",
"scratch that" ≈ "cancel", "grab some stuff" ≈ "add to shopping list". The models
below all run locally with no API calls — they're tiny.

| Position | Model | Size | Description | Predicted M0 | Predicted M3 |
|----------|-------|------|-------------|-------------|-------------|
| **FTS5 BM25** (current) | SQLite FTS5 | 0 MB | Pure lexical. Exact word matching. Fails on synonyms, typos, paraphrasing. | 20% (baseline) | 14% |
| FTS5 + trigram | SQLite FTS5 + `tokenize=trigram` | 0 MB | Character-level 3-gram indexing. Handles typos ("calander"→"calendar") natively. Still lexical for synonyms. | ? | ? |
| all-MiniLM-L6-v2 | sentence-transformers | **22 MB** | Smallest production-grade embedding model. 384-dim vectors. Cosine similarity on action text vs tool descriptions. | ? | ? |
| gte-small | Alibaba GTE | **60 MB** | 384-dim. Better than MiniLM on retrieval benchmarks. MTEB score 61.3 vs MiniLM's 56.5. | ? | ? |
| all-mpnet-base-v2 | sentence-transformers | **420 MB** | 768-dim. Best quality among small models. MTEB 63.3. Overkill for 52 tools? | ? | ? |
| SPLADE-v3 | naver/splade-v3 | **~80 MB** | Sparse neural retrieval. Learns term expansions. "pencil in" expands to "schedule, create, appointment, calendar". Hybrid lexical+semantic in one index. | ? | ? |
| Hybrid BM25 + MiniLM | FTS5 + MiniLM | 22 MB | BM25 for exact matches, MiniLM for semantic rerank. Reciprocal rank fusion (RRF) of both result lists. | ? | ? |
| Hybrid BM25 + SPLADE | FTS5 + SPLADE | ~80 MB | BM25 for recall, SPLADE for neural rerank. Both are sparse — can merge into one index. | ? | ? |

**Why this matters more than any other knob:**

FTS5 BM25 cannot handle "scratch that board meeting" → `delete_event`. "Scratch" is
not in any capability description, action_name, or concept alias. It's a synonym
that only semantic search understands. The MEDIUM tier's 10% accuracy drop (100%→90%
connector, 35%→30% tool) is almost entirely vocabulary mismatch that an embedding
model would catch.

**Tradeoffs:**
- **FTS5**: Zero dependencies, zero RAM, zero startup time. But 20% accuracy.
- **MiniLM (22MB)**: `pip install sentence-transformers`, 22MB download, 50ms inference
  per query. Expected to handle synonyms + typos. Adds ~2s to kernel boot (model load).
- **SPLADE (~80MB)**: Best of both worlds — sparse (no vector DB needed, just inverted
  index) but neural (learns synonyms). Can slot into existing FTS5-style index.
- **Hybrid**: BM25 catches exact keyword matches ("calendar" in "what's my calendar").
  Embedding catches synonyms ("pencil in" → create_event). RRF merges both.

**Test:** Run benchmark with `RETRIEVAL_BACKEND` env var. Compare M0 per tier for
each backend. Key prediction: even the smallest embedding model (MiniLM, 22MB)
should push MEDIUM tier from 30% → ≥80% tool accuracy because it handles the
synonym/paraphrase problem that kills BM25.

---

## Knob Interaction Matrix — Which Combinations Matter

Some knobs are independent; some interact. These interactions must be tested:

| Knob Pair | Interaction | Why |
|-----------|------------|-----|
| K1(FTS5-only) × K11(embedding) | **Critical** | If we use embeddings, K1 is no longer FTS5. These knobs are mutually exclusive at the search layer. Embedding search IS the K1 position. |
| K1(FTS5-only) × K2(no-domain) | **Strong** | If we go FTS5-only, domain becomes irrelevant. No-domain is the only logical setting. |
| K1(FTS5-only) × K5(all-tools) | **Strong** | FTS5 finds the right connector, Back picks the right tool. This is the hypothesis combo. |
| K11(embedding) × K5(all-tools) | **Critical** | Embedding search finds the right connector semantically. Back still needs all tools to pick from. The K1×K5 combo generalizes to embeddings. |
| K11(hybrid) × K6(+all) | **Moderate** | Hybrid search benefits from richer index more than pure BM25 — embeddings can leverage connector labels and concept aliases. |
| K2(boost) × K6(+all) | **Moderate** | Richer index means more hits. Boost keeps the right domain's hits on top. |
| K5(all-tools) × K9(advisory-only) | **Strong** | All tools + advisory gates = Back has full agency. Blocking gates contradict "Back picks." |
| K8(return-all) × K5(top-3-connectors) | **Moderate** | If fallback returns everything, top-3 is a softer version of the same idea. |

**Updated test matrix:** 11 knobs × average 3 positions = 33 one-at-a-time runs.
5 critical interaction pairs × 4 combos = 20 interaction runs.
**Total:** ~53 benchmark runs. At 100 queries/run = 5300 resolution calls.
At 20ms avg latency = ~106 seconds of wall-clock time for ALL experiments combined.

---

## What We Control

| Variable | Control | Notes |
|----------|---------|-------|
| `capability_name` | Full | `tool.execute.shopping.add_item` — unique, semantic |
| `action_name` | Full | `add_item`, `create_list` — semantic verbs |
| `description` (capability) | Full | "Add an item to a shopping list..." |
| `connector_id` | Full | `family.shopping`, `family.calendar` |
| FTS5 index content | Full | What text we index per capability |
| FTS5 query construction | **Full** | Currently domain-scoped; MUST become domain-agnostic |
| Domain filter behavior | **Full** | Currently hard WHERE; MUST become boost-only |
| Ontology edges | Full | Concept aliases → resource families → connectors |
| Constitution text | Full | Prerequisite reads, companion roles, HIL gates |

## What We Do NOT Control

| Constant | Value | Impact |
|----------|-------|--------|
| Back LLM model | Gemini 2.5 Flash | Reasoning quality, token budget |
| LLM tool call budget | 8 per task | Every re-resolve costs budget |
| SQLite GPS | WAL mode, FTS5 | No external vector DB |
| Tools today | 52 (6 connectors × 4–11) | Small search space |
| Tools at scale | 100K+ | Must degrade by connector |
| User vocabulary | Uncontrolled | "cranberry winfus", "2 loafs", typos |
| **LLM hallucination rate** | **Uncontrolled** | **Wrong domain/rf/op_hint is NORMAL** |

---

## Updated Hypotheses

### H1: Domain-Agnostic FTS5 + Connector-Level Return → ≥95% Tool Accuracy

**Baseline (measured):** 20% tool accuracy (domain-scoped FTS5 + single-capability return).
**Prediction:** Domain-agnostic FTS5 + returning all tools for the matched connector
raises tool accuracy to ≥95%. The combo eliminates both root causes: wrong-connector
(from domain filtering) and wrong-tool-within-connector (from `_select_best_capability`).
**Test:** Re-run 100-query benchmark after implementing both changes.

### H2: Domain Hints as Boost (Not Filter) Eliminates the Cliff

**Baseline (measured):** 35% → 10% → 0% drop across HARD/ULTRAHARD tiers.
**Prediction:** Domain-agnostic FTS5 flattens the curve. HARD rises from 10% to ≥30%,
ULTRAHARD rises from 0% to ≥25%. The cliff becomes a gentle slope.
**Test:** Compare per-tier accuracy before/after domain hint change.

### H3: Back LLM Picks the Correct Tool from 4–11 Options with ≥99% Accuracy

**Baseline (measured):** Back has zero agency — resolver picks one tool, Back uses it.
**Prediction:** When Back receives the full tool list for the correct connector, it
picks the right tool ≥99% of the time. This isolates Back's semantic matching from
the resolver's search quality.
**Test:** Separate benchmark — give Back a fake resolution with the correct connector's
full tool list. Measure Back's tool pick accuracy across 50+ queries.

### H4: BM25 on Rich Tool Text Beats Graph Traversal for Connector Matching

**Baseline (measured):** Graph traversal (concept→resource→connector→capability) works
only when all hints are correct. FTS5 fallback is domain-scoped and fails.
**Prediction:** Pure BM25 on {capability_name, action_name, description, connector_label,
concept_aliases} with domain as boost beats graph traversal at connector matching.
BM25 handles typos, synonyms, and missing fields natively.
**Test:** Compare connector accuracy of graph-only vs BM25-only vs hybrid on the 100-query set.

---

## Resolver Contract — Proposed (Post-Redesign)

```python
{
  "verdict": "can_execute",          # ALWAYS — never blocks
  "connector_id": "family.shopping",
  "connector_label": "Shopping",
  "connector_description": "Family shopping lists with categorized items...",
  "tools": [
    # ALL tools for this connector (4–11 tools)
    {
      "capability_name": "tool.execute.shopping.add_item",
      "action_name": "add_item",
      "description": "Add an item to a shopping list; child requests require parent approval",
      "invocation_mode": "execute",
      "effect": "write",
      "required_inputs": ["list_id", "name"],
      "optional_inputs": ["quantity", "unit", "category", "requested_by", "notes", "priority"]
    },
    # ... every other shopping tool
  ],
  "constitution": {
    "prerequisite_reads": [
      {"capability_name": "tool.read.shopping.list_items",
       "reason": "Check for duplicate items before adding",
       "required": False}              # ADVISORY ONLY
    ],
    "companion_resources": [...],
    "advisory_gates": []
  },
  "search_confidence": 0.87,          # How confident is the connector match?
  "alternative_connectors": [          # Top-3 for Back to consider
    {"connector_id": "family.tasks", "confidence": 0.42},
    {"connector_id": "family.reminders", "confidence": 0.31},
  ]
}
```

Key changes from current contract:
1. **`tools` = ALL tools** — not one. Back picks.
2. **`verdict` = always `can_execute`** — never blocks. Gates are advisory.
3. **`search_confidence`** — Back can ask for alternatives if low.
4. **`alternative_connectors`** — top-3 with scores. Back has agency.

---

## Implementation Plan

### Phase 1: Fix Domain-Scoped FTS5 (~2 files)

- `k1/fabric/resolver/capability_type_resolver.py`: When graph traversal fails,
  call domain-agnostic FTS5. Domain becomes a BM25 boost multiplier.
- `k1/fabric/stores/global_projection_store.py`: Add `search_capabilities_text(query)`
  that FTS5-searches ALL domains with BM25 ranking, then groups by connector.

### Phase 2: Connector-Level Return (~3 files)

- `k1/fabric/resolver/capability_binder.py`: Return ALL capabilities for matched
  connector instead of selecting ONE primary.
- `k1/fabric/resolver/situated_resolver.py`: `_allowed_next_actions()` includes
  ALL tools for the connector.
- `k1/concierge/prompt/back_prompt.py`: Tool reference section handles "here are
  all tools for connector X — you pick."

### Phase 3: Delete `_select_best_capability` (~1 file)

- `k1/fabric/resolver/capability_binder.py`: Remove `_select_best_capability()`.
  The binder no longer picks winners.

### Phase 4: Re-Benchmark After Each Phase

- Run `scripts/bench_resolver_search.py` after each phase.
- Track tool accuracy per tier.
- Stop when tool accuracy ≥95% overall.

---

## Appendix: Benchmark Script

**`scripts/bench_resolver_search.py`** — 100 queries across 5 tiers (20 per tier).

Run:
```powershell
$env:LLM_PROVIDER="vertex"
$env:GOOGLE_CLOUD_PROJECT="project-33d51855-d616-4fcd-a69"
$env:GOOGLE_CLOUD_LOCATION="global"
python scripts/bench_resolver_search.py
```

Reports: per-query status, tier breakdown, connector breakdown, verdict distribution,
connector failures list, MRR, blocked rate, avg latency.
