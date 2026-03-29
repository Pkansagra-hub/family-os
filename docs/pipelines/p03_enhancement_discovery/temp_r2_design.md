



Created 3 todos

First let me verify what signals R0 actually loads into P03EventState — no point designing with signals we can't access at R2 time.

Audit P03EventState and R0 signal loading

Read [](file:///d%3A/familyos/k0/pipelines/p03/event_state.py#1-1), lines 1 to 300

Searched for regex `SELECT.*FROM.*st_hipp_events` (`**/k0/pipelines/p03/phases/r0_batch_selector.py`), 1 result

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r0_batch_selector.py#1100-1100), lines 1100 to 1500

Searched for regex `P03EventState\(` (`**/k0/pipelines/p03/phases/r0_batch_selector.py`), 1 result

Searched for regex `R0_SELECT_COLUMNS_SQL|_build_state_payload` (`**/k0/pipelines/p03/phases/r0_batch_selector.py`), 4 results

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r0_batch_selector.py#400-400), lines 400 to 900

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r0_batch_selector.py#1-1), lines 1 to 400

Read [](file:///d%3A/familyos/k0/pipelines/p03/phases/r0_batch_selector.py#885-885), lines 885 to 950

Read [](file:///d%3A/familyos/k0/pipelines/p03/event_state.py#260-260), lines 260 to 300

Read [](file:///d%3A/familyos/k0/contracts/schemas/st_hipp_events_v2.columns.yaml#1-1), lines 1 to 250

Read [](file:///d%3A/familyos/k0/contracts/schemas/st_hipp_events_v2.columns.yaml#250-250), lines 250 to 700

Read [](file:///d%3A/familyos/k0/contracts/schemas/st_hipp_events_v2.columns.yaml#700-700), lines 700 to 1100

Read [](file:///d%3A/familyos/k0/contracts/schemas/st_hipp_events_v2.columns.yaml#1100-1100), lines 1100 to 1500

Searched for regex `surprise_level|identity_relevance|source_reliability|memory_tier|temporal_anchor_json|spatial_familiarity|salience_reasons_json|dominant_emotions_json|has_partner_present|has_parent_present` (`**/k0/contracts/schemas/st_hipp_events_v2.columns.yaml`), 8 results

Searched for regex `0074|M5A|Group 16|surprise|identity_relev|source_reli|memory_tier|temporal_anchor` (`**/k0/contracts/schemas/st_hipp_events_v2.columns.yaml`), no results

Read [](file:///c%3A/Users/princ/AppData/Roaming/Code/User/workspaceStorage/af8eada89b8e0ceb331a1a230f56c42f/GitHub.copilot-chat/chat-session-resources/f09d48b3-430d-4e84-b189-4415f74a6601/tooluse_1Gjz6JcKoZGJOW7qSIIbVG__vscode-1772817459113/content.txt#1-1), lines 1 to 400

Starting: *Design neuromorphic episode formation* (2/3)

Excellent finding. Almost every signal we need is already loaded. Let me confirm the 3 actionable gaps:

Starting: *Present design for discussion* (3/3)

---

## Signal Surface Status: Almost Perfect

**64 of 67 signals we need are ALREADY loaded by R0 into P03EventState.** Only 3 actionable gaps:

| Gap Signal | R2 Value | Priority |
|---|---|---|
| `spatial_familiarity` | Novel places create stronger episode boundaries (von Restorff) | MEDIUM |
| `has_partner_present` / `has_parent_present` | Quick social binding flags | LOW (reconstructable from `participant_relationships_json`) |
| `salience_reasons_json` | Shared salience reason = narrative binding | LOW (we have `salience_score` + `entity_salience_json`) |

**None of these are blockers.** We can design with 64 signals NOW.

---

## Neuromorphic Episode Formation — Complete Design

### The Core Insight: How the Hippocampus Actually Forms Episodes

The hippocampus doesn't "cluster vectors." It runs a **continuous prediction machine** (Zacks & Swallow, 2007; Davachi & DuBrow, 2015) that does three things simultaneously:

1. **Maintains a situation model** — a multimodal representation of "what's happening right now" spanning WHO is here, WHERE we are, WHAT we're doing, HOW we feel, and WHY this matters
2. **Detects prediction errors** — when any channel of the situation model violates expectations, a boundary fires
3. **Binds within boundaries** — events between consecutive boundaries are bound into a single episodic trace via hippocampal CA1 conjunction coding

Our system should mirror this with three interacting subsystems:

```
                    ┌─────────────────────────────────────┐
                    │   SUBSYSTEM 1: CONTEXT ASSEMBLY     │
                    │   (Entorhinal Cortex analog)        │
                    │                                     │
                    │   64 raw signals → 8 context        │
                    │   channels per event                 │
                    └────────────────┬────────────────────┘
                                     │
                    ┌────────────────▼────────────────────┐
                    │   SUBSYSTEM 2: BOUNDARY DETECTION   │
                    │   (Dentate Gyrus / pattern sep.)    │
                    │                                     │
                    │   Prediction error accumulation     │
                    │   across channels → split points    │
                    └────────────────┬────────────────────┘
                                     │
                    ┌────────────────▼────────────────────┐
                    │   SUBSYSTEM 3: EPISODIC BINDING     │
                    │   (CA1 conjunction coding)          │
                    │                                     │
                    │   6D multi-dimensional distance     │
                    │   → HDBSCAN → coherent clusters     │
                    └────────────────┬────────────────────┘
                                     │
                    ┌────────────────▼────────────────────┐
                    │   SUBSYSTEM 4: EPISODE ENCODING     │
                    │   (Consolidation to neocortex)      │
                    │                                     │
                    │   Salience-weighted centroid         │
                    │   + multi-dimensional metadata      │
                    └─────────────────────────────────────┘
```

---

### SUBSYSTEM 1: Context Assembly (Entorhinal Cortex)

For each event, organize 64 loaded signals into **8 context channels** that mirror the two entorhinal pathways:

**MEC pathway (WHERE/WHEN):**

| Channel | Signals | Brain Analog |
|---------|---------|--------------|
| **Temporal** | `conversation_anchor_ms` (gold), `temporal_source` (confidence), `temporal_links_json` (associations), `temporal_orientation`, `temporal_anchor_json`, `time_of_day_bucket`, `circadian_slot`, `is_weekend`, `extraction_sequence` | Time cells (CA1), grid cells (MEC) |
| **Spatial** | `place_id` (place cell primary), `geohash_6` (grid cell metric), `location_name`, `location_type`, `location_hierarchy_json`, `spatial_context_json` (transition) | Place cells (CA1/CA3), grid cells (MEC) |

**LEC pathway (WHAT/WHO/HOW/WHY):**

| Channel | Signals | Brain Analog |
|---------|---------|--------------|
| **Semantic** | `embedding_768`, `activity_type_ultrabert` (12-type), `intent_ultrabert` (8-type), `activity_type` (legacy 7-type fallback), `content_text` | Perirhinal cortex → LEC |
| **Social** | `participants_json`, `participant_relationships_json` (typed), `social_context`, `social_intimacy`, `num_participants`, `is_solo_event` | Social brain network (mPFC, TPJ) |
| **Affective** | `affect_valence`, `affect_arousal`, `affect_dominance` (full VAD), `emotions_json`, `surprise_level`, `salience_score`, `salience_band`, `entity_salience_json` | Amygdala → hippocampal modulation |
| **Narrative** | `narrative_thread_id`, `narrative_arc_position`, `narrative_is_goal_event`, `goal_context`, `intent_type`, `temporal_orientation` | Default mode network (vmPFC) |
| **Cognitive** | `elaboration_depth`, `novelty`, `identity_domains_json`, `identity_relevance`, `memory_tier`, `source_type` | Prefrontal cortex (encoding depth) |
| **Reliability** | `source_reliability`, `temporal_source` (provenance), `activity_type_confidence`, `intent_confidence`, `k1_signal_version` | Meta-cognitive monitoring |

---

### SUBSYSTEM 2: Boundary Detection (Enhanced EpisodeSplitter)

**Replace** the current 4-signal priority cascade with a **prediction error accumulator** — the core mechanism of Event Segmentation Theory.

**The principle**: The brain predicts that the NEXT moment will be similar to the CURRENT moment across all situation model channels. When accumulated prediction error exceeds a threshold, a new episode begins.

For each consecutive event pair `(e_i, e_{i+1})`, compute change per channel:

```
Channel deltas:
┌──────────────────────────────────────────────────────────────────────────────┐
│ Δ_narrative  = narrative_change(e_i, e_{i+1})                               │
│   IF both have narrative_thread_id:                                          │
│     different thread → 1.0 (strongest boundary signal)                      │
│     same thread → 0.0                                                        │
│   ELIF goal_context differs → 0.7                                            │
│   ELIF intent_type differs → 0.5                                             │
│   ELSE → 0.0 (no signal = no change assumed)                                │
│                                                                              │
│ Δ_social     = social_change(e_i, e_{i+1})                                  │
│   IF both have participants_json:                                            │
│     1.0 - jaccard(participants_i, participants_j)                           │
│   ELIF social_context differs → 0.8                                          │
│   ELIF is_solo changes → 0.6                                                 │
│   ELSE → 0.0                                                                 │
│                                                                              │
│ Δ_spatial    = spatial_change(e_i, e_{i+1})                                  │
│   IF both have place_id:                                                     │
│     different → 1.0 (place cell remapping)                                   │
│     same → 0.0                                                               │
│   ELIF both have geohash_6:                                                  │
│     prefix_distance / 6.0  (grid cell metric fallback)                      │
│   ELIF location_name differs → 0.7                                           │
│   ELSE → 0.0                                                                 │
│   BOOST: if spatial_context_json.transition_from_place exists → min(Δ, 0.8) │
│     (explicit transition = definite boundary but places are related)         │
│                                                                              │
│ Δ_activity   = activity_change(e_i, e_{i+1})                                │
│   IF both have activity_type_ultrabert:                                      │
│     different → 0.8 (12-type goal boundary)                                  │
│     same → 0.0                                                               │
│   ELIF activity_type differs → 0.6 (7-type fallback)                        │
│   ELSE → 0.0                                                                 │
│                                                                              │
│ Δ_temporal   = temporal_change(e_i, e_{i+1})                                │
│   log(1 + |ts_diff| / τ) / log(1 + max_gap / τ)                            │
│   where τ = 30 min = 1,800,000 ms, max_gap = 4h = 14,400,000 ms           │
│   Range: [0.0, 1.0], logarithmic (Howard & Kahana 2002)                    │
│                                                                              │
│ Δ_affective  = affective_shift(e_i, e_{i+1})                               │
│   sqrt(((v_i-v_j)/2)^2 + (a_i-a_j)^2 + (d_i-d_j)^2) / sqrt(3)           │
│   Full VAD distance, normalized [0,1]                                        │
│                                                                              │
│ Δ_cognitive  = cognitive_shift(e_i, e_{i+1})                                │
│   novelty_spike: if e_{i+1}.novelty ∈ {NOVEL,SURPRISING}                   │
│     AND e_i.novelty ∈ {ROUTINE,EXPECTED} → 0.8                              │
│   identity_shift: if dominant identity_domain changes → 0.5                  │
│   ELSE → 0.0                                                                 │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Prediction Error Score** — weighted sum with confidence gating:

```
PredictionError(i, i+1) =
    w_nar * Δ_narrative  * present(narrative)     [w = 0.25]
  + w_soc * Δ_social     * present(social)        [w = 0.15]
  + w_spa * Δ_spatial    * present(spatial)        [w = 0.12]
  + w_act * Δ_activity   * present(activity)       [w = 0.13]
  + w_tmp * Δ_temporal   * 1.0 (always present)   [w = 0.15]
  + w_aff * Δ_affective  * present(affective)     [w = 0.10]
  + w_cog * Δ_cognitive  * present(cognitive)      [w = 0.10]
                                                   ─────────
                                         max sum =  1.00

where present(channel) =
  1.0 if signal exists on BOTH events
  0.5 if signal exists on ONE event
  0.0 if missing on BOTH (channel excluded, weight redistributed)
```

**Boundary Decision Logic** — three tiers:

```
TIER 1 — HARD BOUNDARIES (mandatory, override everything):
  • time_gap > max_episode_hours (4h default)        → ALWAYS SPLIT
  • memory_tier == "landmark"                         → ALWAYS SPLIT before this event
  • surprise_level > 0.85                             → ALWAYS SPLIT (flashbulb memory)

TIER 2 — PREDICTION ERROR BOUNDARY:
  • PredictionError >= θ_boundary (default 0.30)      → SPLIT HERE

  UNLESS narrative veto applies:
  • IF same narrative_thread_id on both events
    AND PredictionError < θ_narrative_veto (default 0.55)
                                                      → DO NOT SPLIT
    (coherent story thread = active situation model, harder to break)

TIER 3 — SOFT BOUNDARIES (recorded but not split):
  • PredictionError >= 0.15 but < θ_boundary          → MARK as "weak boundary"
  • Used for: episode sub-structure, retrieval hints,
    HDBSCAN noise rescue guidance
```

**Why this is neuroscience-correct:**
- The brain's Event Segmentation Theory says boundaries occur at **prediction errors**, not fixed thresholds on single features
- The **narrative veto** mirrors how sustained attention to a story suppresses boundary detection (Zacks, 2007: "when an ongoing event model is working well, it resists updating")
- **Landmark anchoring** mirrors flashbulb memory formation (Brown & Kulik, 1977): extraordinary events ALWAYS start new episodes
- **Logarithmic temporal** mirrors hippocampal time cells (Howard & Kahana 2002): recent events are sharply separated, distant events compressed
- **Multi-channel accumulation** mirrors the entorhinal cortex's multi-modal input: no single channel defines boundaries alone

---

### SUBSYSTEM 3: Episodic Binding (Enhanced CompositeDistance + HDBSCAN)

Within each split segment, HDBSCAN clusters events using **6-dimensional distance** that mirrors hippocampal CA1 conjunction coding.

**The 6D Distance Function:**

```
d(i,j) = w_sem * d_semantic(i,j)        [0.25]
        + w_tmp * d_temporal(i,j)        [0.15]
        + w_spa * d_spatial(i,j)         [0.12]
        + w_soc * d_social(i,j)          [0.15]
        + w_aff * d_affective(i,j)       [0.10]
        + w_nar * d_narrative(i,j)       [0.23]
                                         ──────
                                          1.00
```

**Dimension 1 — Semantic Distance [w=0.25]** *(perirhinal cortex → LEC → CA1)*

```
d_sem = cosine_distance(embedding_768_i, embedding_768_j)
Range: [0, 2], typical [0.05, 0.40] for UltraBERT

Activity type micro-adjustment:
  IF activity_type_ultrabert matches → d_sem *= 0.85 (15% tighter)
  IF activity_type_ultrabert differs → d_sem *= 1.10 (10% looser)
```

**Dimension 2 — Temporal Distance [w=0.15]** *(time cells, MEC)*

```
# Base: logarithmic compression (Howard & Kahana 2002)
d_tmp_raw = log(1 + |ts_i - ts_j| / τ) / log(1 + max_gap / τ)
  τ = 1,800,000 ms (30 min)
  max_gap = 14,400,000 ms (4h)

# Confidence weighting from temporal_source (GAP-002)
conf_map = {conversation_anchor: 1.0, event_time: 0.8, envelope_ts: 0.5, now: 0.3}
confidence = min(conf(source_i), conf(source_j))
d_tmp = confidence * d_tmp_raw + (1 - confidence) * 0.5
  → uncertain timestamps push toward neutral (0.5), not assumed close or far

# Temporal link binding (GAP-002 — temporal context reinstatement)
shared_links = shared_resolved_epochs(temporal_links_i, temporal_links_j)
IF shared_links > 0:
  d_tmp *= max(0.3, 1.0 - 0.25 * shared_links)
  → events referencing same time points are temporally bound
  → neuroscience: recalling one event reinstates temporal context of associated events
    (Howard & Kahana 2002 Temporal Context Model)

# Hard cutoff preserved
IF |ts_i - ts_j| > max_gap_ms → d_tmp = ∞
```

**Dimension 3 — Spatial Distance [w=0.12]** *(place cells + grid cells, CA1/MEC)*

```
# TIER 1: Place cell identity (GAP-002 — STRONGEST spatial signal)
IF both have place_id:
  same place_id   → d_spa = 0.0  (same place cell pattern = same place)
  different       → d_spa = 1.0
  transition_from → d_spa = 0.75 (related places, explicit transition)

  WHY place_id > geohash: "Grandma's house" is ONE place whether you're
  in the kitchen or garden. Place cells fire for semantic places, not
  GPS coordinates. This is O'Keefe's Nobel Prize finding (2014).

# TIER 2: Grid cell metric (fallback)
ELIF both have geohash_6:
  d_spa = geohash_prefix_distance(geo_i, geo_j) / 6.0

# TIER 3: Location name (fallback)
ELIF both have location_name:
  same → 0.0, different → 0.8

# TIER 4: Location hierarchy (GAP-002 — multi-resolution comparison)
ELIF both have location_hierarchy_json:
  shared_levels = count matching hierarchy levels
  d_spa = 1.0 - (shared_levels / max(len_i, len_j))

# Unknown
ELSE → 0.5 (neutral)
```

**Dimension 4 — Social Distance [w=0.15]** *(social brain network: mPFC, TPJ)*

```
# TIER 1: Typed relationship distance (MW v2 — weighted Jaccard)
IF both have participant_relationships_json:
  Extract {person → relationship_type} maps

  relationship_weight = {
    partner: 1.0, parent: 0.9, child: 0.9, sibling: 0.85,
    grandparent: 0.8, friend: 0.6, colleague: 0.4, acquaintance: 0.2
  }

  shared_persons = intersection of person sets
  union_persons = union of person sets

  IF union_persons is empty → 0.5
  ELSE:
    weighted_overlap = Σ(weight[type] for shared persons)
    max_possible = Σ(max weight for each union person)
    d_soc = 1.0 - (weighted_overlap / max_possible)

  WHY typed: "dinner with partner" and "dinner with colleague" have
  identical participant COUNT but maximally different social context.
  Dunbar's social brain layers: intimate (5) → close (15) → friends (50)
  → acquaintances (150). Relationship type encodes which Dunbar layer.

# TIER 2: Flat participant Jaccard (fallback)
ELIF both have participants_json with entries:
  d_soc = 1.0 - jaccard(set_i, set_j)

# TIER 3: Social context category (fallback)
ELIF both have social_context:
  same → 0.0, different → 0.8

# TIER 4: Solo detection
ELIF both is_solo_event → 0.0

# Unknown
ELSE → 0.5

# Intimacy modulation (social_intimacy)
IF both HIGH intimacy AND d_soc < 0.5:
  d_soc *= 0.7  (intimate interactions bind tighter)
```

**Dimension 5 — Affective Distance [w=0.10]** *(amygdala → hippocampal modulation)*

```
# Full 3D VAD distance (Russell & Mehrabian 1977)
d_aff = sqrt(
  ((v_i - v_j) / 2)^2     # valence [-1,1] → normalized range contribution
  + (a_i - a_j)^2          # arousal [0,1]
  + (dom_i - dom_j)^2      # dominance [0,1] — GAP-002 addition (3rd VAD axis)
) / sqrt(3)                # normalize to [0, 1]

# Novelty/surprise separation (prediction error signal)
IF one SURPRISING + other ROUTINE → d_aff = max(d_aff, 0.7)
IF surprise_level diff > 0.5     → d_aff = max(d_aff, 0.6)

# Shared dominant emotion binding
IF dominant_emotions overlap (both have "joy" or both have "anxiety"):
  d_aff *= 0.75  (shared emotion = emotional coherence)

# Shared entity salience binding
IF entity_salience_json overlaps on high-salience entities:
  d_aff *= 0.80  (shared emotionally salient entity = affective connection)
```

**Dimension 6 — Narrative Distance [w=0.23]** *(default mode network, vmPFC)*

```
# TIER 1: Thread identity (STRONGEST binding signal in all of episodic memory)
IF both have narrative_thread_id:
  same thread → 0.0  (same story = same episode, PERIOD)
  different   → 1.0  (different story = different episode)

  WHY strongest: Rubin (2006) Basic Systems Model — narrative is the PRIMARY
  organizing system for autobiographical memory. When you recall "the time
  we planned the birthday party," narrative thread IS the episode identity.
  Two events 3 hours apart on the same thread are ONE episode.
  Two events 5 minutes apart on different threads are DIFFERENT episodes.

# TIER 2: Goal context (goal boundary in EST)
ELIF both have goal_context:
  same → 0.2, different → 0.8

# TIER 3: Temporal orientation (cognitive mode shift)
ELIF both have temporal_orientation:
  same → 0.3, different → 0.75

  WHY: Remembering past and planning future engage distinct hippocampal
  circuits (Schacter et al., 2012). Switching between "recalling yesterday"
  and "planning tomorrow" is a fundamental cognitive boundary.

# TIER 4: Intent type
ELIF both have intent_type:
  same → 0.2, different → 0.6

# Unknown
ELSE → 0.5

# NARRATIVE SHORT-CIRCUIT (MANDATORY OVERRIDE)
IF narrative_thread_id matches AND total d(i,j) > 0.4:
  d(i,j) = min(d(i,j), 0.20)
  → Same thread ALWAYS clusters together. This is the single most
    important rule in the entire system. Nothing overrides narrative
    thread identity except the 4h hard temporal cutoff.
```

**Global Modifiers Applied After 6D Sum:**

```
# Source reliability gating
reliability = min(source_reliability_i, source_reliability_j)
IF reliability < 0.8:
  d(i,j) = reliability * d(i,j) + (1 - reliability) * 0.5
  → Low-reliability events: all distances pushed toward neutral (0.5)
  → Prevents unreliable signals from creating false clusters OR false separations

# Memory tier anchoring
IF either event has memory_tier == "landmark":
  IF same landmark context (narrative_thread_id or place_id match):
    d(i,j) *= 0.5  (landmark anchors nearby related events)
  ELSE:
    d(i,j) *= 1.3  (landmark repels unrelated events)

# Extraction sequence binding
IF extraction_sequence difference == 0 (same K1 turn extraction):
  d(i,j) *= 0.7  (same cognitive moment = implicit binding)

# Hard temporal cutoff (preserved, final override)
IF |ts_i - ts_j| > max_gap_ms → d(i,j) = ∞
```

---

### SUBSYSTEM 4: Episode Encoding (Enhanced CentroidCalculator)

**Encoding Strength Weight** — determines how much each event contributes to the episode's centroid representation:

```
encoding_weight(e_i) =
    0.25 * salience_score                              # P02 M06 importance
  + 0.20 * elaboration_map[elaboration_depth]          # User's own attention investment
  + 0.15 * identity_relevance                          # Self-reference effect (Rogers 1977)
  + 0.15 * arousal_boost(affect_arousal, affect_valence)   # Emotional modulation (McGaugh 2004)
  + 0.10 * memory_tier_map[memory_tier]                # Direct encoding strength classification
  + 0.10 * recency_decay(ts_i, episode_duration)       # Exponential, half-life = duration/3
  + 0.05 * hdbscan_probability^0.5                     # Cluster core > fringe

Lookup tables:
  elaboration_map: MENTION→0.2, DISCUSSED→0.5, ELABORATED→0.8, DEEPLY_PROCESSED→1.0
  memory_tier_map: routine→0.2, notable→0.5, significant→0.8, landmark→1.0
  arousal_boost:   affect_arousal * (1 + |affect_valence|)  range [0, 2]
  recency_decay:   exp(-1.5 * (ts_max - ts_i) / episode_duration)  range [0.22, 1.0]

Final: normalize so Σ weights = 1.0, floor each at 0.02 (no zero weights)
```

**WHY this weighting is neuroscience-correct:**
- **Salience**: MW v2 M06 already computes multi-factor importance — trust the upstream pipeline
- **Elaboration depth**: Craik & Lockhart (1972) Levels of Processing — deeper processing = stronger memory trace. When a user writes 500 words about one event in a 5-event episode, that event IS the episode
- **Identity relevance**: Rogers, Kuiper & Kirker (1977) Self-Reference Effect — self-relevant information is remembered ~2x better. The centroid should be pulled toward what matters to the user's identity
- **Arousal boost**: McGaugh (2004) — amygdala modulates hippocampal encoding strength. High arousal + strong valence = strongest possible encoding
- **Memory tier**: Direct MW classification of encoding strength — "landmark" events are flashbulb memories that anchor episodes
- **Recency**: Exponential decay is more natural than linear (the "end" of an episode is more vivid than the "beginning" in immediate recall, but with soft decay, not cliff)
- **HDBSCAN probability**: Core cluster members define the episode more than fringe members

---

### ENHANCED NOISE RESCUE — Context-Aware Multi-Signal Rescue

Replace hardcoded 0.3/0.2 thresholds with **multi-channel rescue scoring**:

```
For each noise event, compute rescue affinity to nearest cluster:

rescue_score =
    0.28 * narrative_match   # same narrative_thread_id as cluster majority
  + 0.18 * social_match      # same social_context as cluster majority
  + 0.14 * spatial_match     # same place_id as cluster majority
  + 0.14 * semantic_proximity # cosine to cluster centroid < 0.3
  + 0.12 * temporal_proximity # within 15min of cluster boundary
  + 0.08 * activity_match    # same activity_type_ultrabert as cluster majority
  + 0.06 * entity_overlap    # shared high-salience entities with cluster

IF rescue_score >= 0.35 → RESCUE into cluster
IF rescue_score >= 0.25 AND memory_tier ∈ {notable, significant, landmark}
   → RESCUE (important events get lower threshold)
```

**WHY**: Prevents rescuing a work email into a family dinner cluster just because the embeddings are similar (both discuss "scheduling"). The narrative thread and social context signals prevent cross-context contamination.

---

### ENHANCED QUALITY ASSESSMENT — EpisodicCoherenceScore

Replace fake silhouette (always ~0.98) with **multi-dimensional coherence per episode**:

```
Per-episode quality:
  narrative_coherence  = fraction sharing dominant narrative_thread_id    [w=0.25]
  social_coherence     = fraction sharing dominant social_context         [w=0.20]
  spatial_coherence    = fraction sharing dominant place_id or geohash[:4] [w=0.15]
  true_silhouette      = sklearn silhouette on precomputed 6D distance    [w=0.15]
  temporal_compactness = 1.0 - (duration / max_gap_hours)                [w=0.10]
  affective_coherence  = 1.0 - stddev(affect_valence) / 2.0             [w=0.10]
  identity_coherence   = fraction sharing dominant identity_domain       [w=0.05]

Batch quality = mean(episode qualities)
```

This replaces the broken closed-loop sensor (Section 24.4 in discovery doc) with signals that are ALL available NOW.

---

### Summary: Old → New

| Component | Current (2D, broken) | Proposed (Neuromorphic) |
|-----------|---------------------|------------------------|
| **Boundary detection** | 4-signal priority cascade (2 were dead, now 4 live) | 7-channel prediction error accumulator with narrative veto + landmark anchoring |
| **Clustering distance** | `0.7*cosine + 0.3*linear_time` | 6D: semantic + log-temporal + spatial (place_id) + social (typed) + affective (VAD) + narrative (thread_id) |
| **Temporal model** | Linear normalization | Logarithmic compression + temporal_source confidence + temporal_link binding |
| **Spatial model** | geohash prefix (grid cell only) | place_id primary (place cell) → geohash fallback (grid cell) → hierarchy → name |
| **Social model** | None (post-hoc decoration) | Typed relationship Jaccard + social_context + intimacy modulation |
| **Affective model** | None | Full 3D VAD + novelty/surprise + emotion overlap + entity salience |
| **Narrative model** | None | Thread identity (strongest signal) + goal context + temporal orientation + short-circuit override |
| **Centroid weighting** | `importance_score` only | 7-factor: salience + elaboration + identity_relevance + arousal + memory_tier + recency + HDBSCAN probability |
| **Noise rescue** | Hardcoded 0.3/0.2 | 7-signal context-aware rescue scoring |
| **Quality metric** | Fake silhouette (~0.98 always) | 7-dimension episodic coherence score |
| **Signals used** | 2 of 64 (3%) | 45+ of 64 (70%+) |

---

### The Three Neuroscience Guarantees

1. **Narrative thread identity is sacred.** Same `narrative_thread_id` = same episode, period. This is the single most important rule. Rubin (2006) showed narrative is the primary organizer of autobiographical memory. Two events on the same conversation thread cluster together even if 3 hours apart and at different locations. Only the 4h hard cutoff overrides this.

2. **Place cells, not grid cells.** `place_id` is the primary spatial signal, `geohash_6` is the metric fallback. O'Keefe's Nobel Prize finding: the hippocampus encodes *places* (semantic locations), not *coordinates*. "Home" is one place whether you're in the kitchen or garden.

3. **Experienced time, not ingestion time.** `conversation_anchor_ms` with `temporal_source` confidence weighting means episodes form around when the user EXPERIENCED events, not when they typed them. Uncertain timestamps get neutral distance (0.5), not assumed-close (0.0). This prevents the systematic misclustering that occurred before GAP-002.

---

That's the complete design. What's your read — does this match how you want episodes to form? Any channels you'd weight differently, or boundary logic you'd adjust before we encode this into the discovery document?
