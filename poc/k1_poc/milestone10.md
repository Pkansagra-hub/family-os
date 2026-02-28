## M10: UltraBERT Integration & Tier Routing -- Implementation Plan

### Codebase State Summary

**What's ready (M1-M9 complete, 508 tests passing):**

| Infrastructure | File | Status |
|---|---|---|
| Phase1Result (11 fields) | fsm/phase1.py L55-112 | `intents`, `entities`, `salience_map`, `primary_emotion`, `emotion_confidence`, `valence`, `arousal`, `intent_classification`, `domain_context`, `safety_band`, `complexity_tier` |
| Phase1Pipeline protocol | fsm/phase1.py L126-153 | `classify(text) -> Phase1Result` |
| StubPhase1Pipeline | fsm/phase1.py L157-267 | Keyword-based: "hotel"/"flight" -> MEDIUM, everything else -> LOW. No UltraBERT. |
| TurnLock | fsm/phase1.py L269-325 | Sequencing gate (boolean flag, synchronous POC) |
| familyos_ultrabert wheel | wheels/familyos_ultrabert-4.0.0-py3-none-any.whl | `Client(backend="auto")`, `client.analyze(text)` returns result object with 12 head attributes. Pip-installed package. K1 creates its own adapter -- zero dependency on k0/runtime/ |
| ControlSection | sessionstate/sections/control.py L287-1328 | Has `IntentClassification`, `DomainContext`, `SafetyContext` dataclasses. Has `_intents`, `_domains`, `_safety` fields. Has `get_domains()`, `get_safety()`, `set_primary_domain()`, `escalate_safety()`. NO `set_intent()` or `get_intents()` method |
| ScoreboardSection | sessionstate/sections/scoreboard.py L182-1050+ | Has `add_referent()`, `set_salience()`, `set_user_intent()`, `get_user_intent()`, `list_referents()`. All methods exist and work |
| AffectiveNowSection | sessionstate/sections/affective_now.py L250-1200+ | Has `update(emotion, intensity, valence, arousal, dominance, confidence, source)` full method + `update_emotion()` shorthand. Both work |
| ConciergeControlExtension | fsm/control_extension.py L32-221 | In-memory wrapper: `_complexity_tier`, `_fsm_state`, `_active_task_ids`. Has `bind_control_section()` + `sync()` for overlay. `set_complexity_tier()` exists |
| Controller._run_phase1() | fsm/controller.py L1611-1652 | Acquires TurnLock, calls classify(), writes to control_ext only, attaches metadata to history, releases TurnLock. NO SS section writes |
| Controller._run_phase1_with_arbiter() | fsm/controller.py L1660-1750+ | Phase1 + Arbiter for LISTENING/CLARIFYING. Same missing SS writes |
| _route_via_orchestrator() | fsm/controller.py L1899-1990 | HIGH tier -> immediate `task.failed`. MEDIUM -> OrchestratorStub or direct Back. LOW -> direct Back |
| Tool dispatcher | tools/dispatcher.py L50-480 | `BUDGET_LIMITS`: LOW=5, MEDIUM=10, HIGH=20, CRISIS=3. `FRONT_TIER_ALLOWLISTS`, `BACK_TIER_ALLOWLISTS` with CRISIS=empty |
| dispatch_task tool | tools/implementations.py L850-945 | LLM provides tier in args. No AUTO/fallback-to-SS logic. `ComplexityTier(tier_raw.upper())` |
| Bootstrap | kernel/bootstrap.py (924 lines) | Creates FSM with `StubPhase1Pipeline()` by default. No UltraBERT wiring |
| Ledger (M9) | ledger/ | Full ledger infrastructure: store, writer, projections, recovery |
| Bus events | events/ (10 files) | 30 canonical event classes, `EVENT_TYPE_REGISTRY` |

**`familyos_ultrabert` Client.analyze() result object attributes (12 heads):**

```python
result = client.analyze(text)

result.sentiment          # str: "very_negative"|"negative"|"neutral"|"positive"|"very_positive"
result.sentiment_confidence  # float
result.emotions           # list[str]: top emotions from 44-class head (e.g. ["joy", "love"])
result.emotion_scores     # dict[str, float]: {emotion: score} for all 44 classes
result.safety             # str: "GREEN"|"AMBER"|"RED"|"CRISIS"
result.safety_confidence  # float
result.entities           # list[dict]: family NER [{text, label, start, end}] (KINSHIP, FAMILY_EVENT)
result.general_entities   # list[dict]: general NER [{text, label, start, end}] (PERSON, ORG, LOC, DATE)
result.temporal           # list[dict]: temporal [{text, label, start, end}] (DATE_REL, TIME_REL)
result.intent             # str: primary intent (8 classes)
result.ingress            # str: routing domain (12 domains)
result.relations          # list[str]: relationship types (parent_of, spouse_of, etc.)
result.embedding          # list[float]: 768-dim vector
result.latency_ms         # float: inference time
```

**K1-owned mapping constants (defined in `fsm/ultrabert_adapter.py`):**

| Mapping | Defined In | Values |
|---|---|---|
| `SENTIMENT_TO_VALENCE` | K1 ultrabert_adapter.py | very_negative=0.1, negative=0.3, neutral=0.5, positive=0.7, very_positive=0.9 |
| `HIGH_AROUSAL_EMOTIONS` | K1 ultrabert_adapter.py | anger, excitement, fear, surprise -> arousal >= 0.7 |
| `LOW_AROUSAL_EMOTIONS` | K1 ultrabert_adapter.py | sadness, calm, boredom, contentment -> arousal <= 0.3 |
| `ENTITY_MIN_CONFIDENCE` | K1 ultrabert_adapter.py | 0.65 (filter garbage NER spans) |

**K1 owns ALL mappings. Zero imports from k0/runtime/. The `familyos_ultrabert` pip package is the only shared dependency.**

---

### UltraBERT Containerized Serving Architecture

**Problem:** UltraBERT (~149M params, ~500MB GPU memory) must be shared by both K0 kernel container and K1 POC container. Loading the model in each container wastes 2x memory and prevents GPU sharing.

**Solution: K1-Native UltraBERT Adapter (Tightly Coupled)**

K1 owns its own UltraBERT adapter that directly imports the `familyos_ultrabert` pip package. Zero dependency on k0/runtime/. The adapter lives at `fsm/ultrabert_adapter.py` and provides:

```
+-------------------+
| K1 POC            |
|                   |
| fsm/              |
|  ultrabert_       |    pip import     +---------------------+
|  adapter.py  -----+---------------->  | familyos_ultrabert  |
|  (K1-owned)       |                   | (pip package v4.0)  |
|                   |                   | Client.analyze()    |
| ultrabert_        |                   +---------------------+
|  phase1.py        |
|  (pipeline)       |
+-------------------+
```

**K1UltraBERTAdapter responsibilities:**

1. **Singleton client management** -- thread-safe lazy init of `familyos_ultrabert.Client`
2. **LRU/TTL cache** -- 64 entries, 30s TTL (independently owned by K1)
3. **GPU detection** -- `Client(backend="auto")` auto-selects CUDA/CPU
4. **Result dict conversion** -- `analyze(text) -> dict | None` converting result object attributes to dict
5. **Warmup** -- optional first-call on startup to amortize model load latency
6. **Metrics** -- call_count, avg_latency_ms, cache_hits, cache_misses, fallback_count
7. **Mapping constants** -- `SENTIMENT_TO_VALENCE`, `HIGH_AROUSAL_EMOTIONS`, `LOW_AROUSAL_EMOTIONS`, `ENTITY_MIN_CONFIDENCE`

**Protocol for testability:**

```python
class UltraBERTAdapter(Protocol):
    def analyze(self, text: str) -> dict | None: ...
    def is_available(self) -> bool: ...
    def get_metrics(self) -> dict: ...
```

`K1UltraBERTAdapter` is the real implementation (directly uses `familyos_ultrabert.Client`). `StubUltraBERTAdapter` returns None (for tests without GPU). The `UltraBERTPhase1Pipeline` depends on the protocol, not the concrete class.

---

### File Change Matrix

| File | Action | Epic | Changes |
|---|---|---|---|
| `fsm/ultrabert_phase1.py` | **NEW** | E10.1 | `UltraBERTPhase1Pipeline` implementing `Phase1Pipeline` protocol. Calls adapter, maps 12-head output to `Phase1Result`, multi-factor complexity classifier, confidence thresholding, graceful degradation |
| `fsm/ultrabert_adapter.py` | **NEW** | E10.4 | `UltraBERTAdapter` protocol + `K1UltraBERTAdapter` (directly uses `familyos_ultrabert.Client`), `StubUltraBERTAdapter` (for tests), singleton `get_ultrabert_adapter()`, LRU/TTL cache, mapping constants |
| `fsm/phase1.py` | **MODIFY** | E10.1 | Add `temporal_expressions` and `relations` fields to `Phase1Result.__slots__` and `__init__`. Update `to_metadata()` |
| `fsm/controller.py` | **MODIFY** | E10.2, E10.3 | `_run_phase1()`: add 3 SS section writes (control, scoreboard, affective_now) inside TurnLock. `_run_phase1_with_arbiter()`: same writes. Add CRISIS safety-band short-circuit after classify. `_route_via_orchestrator()`: replace HIGH fail-fast with Planner handoff |
| `sessionstate/sections/control.py` | **MODIFY** | E10.2 | Add `set_intent(IntentClassification)`, `get_intents() -> IntentClassification`, `set_complexity_tier(str)`, `get_complexity_tier() -> str` methods |
| `kernel/bootstrap.py` | **MODIFY** | E10.4 | Wire `K1UltraBERTAdapter` + `UltraBERTPhase1Pipeline` into FSM creation. Add config-driven pipeline selection. Add warmup call |
| `tools/implementations.py` | **MODIFY** | E10.3 | `dispatch_task`: add AUTO tier logic -- if LLM sends "AUTO" or omits tier, read from SS control section |
| `bus/builders.py` | **MODIFY** | E10.3 | Add `build_crisis_event()`, `build_phase1_classified()`, `build_task_routed()` builder functions |
| `events/conversation.py` | **MODIFY** | E10.3 | Add `Phase1Classified`, `CrisisDetected`, `TaskRouted` canonical event classes |
| `config/defaults.py` | **MODIFY** | E10.1, E10.4 | Add `phase1.pipeline`, `phase1.complexity_thresholds`, `phase1.intent_confidence_threshold`, `phase1.require_ultrabert`, `ultrabert.mode`, `ultrabert.warmup` config keys |
| `tests/poc/test_m10_e101_ultrabert_pipeline.py` | **NEW** | E10.1 | Tests for UltraBERTPhase1Pipeline: mapping, complexity classifier, thresholding, degradation |
| `tests/poc/test_m10_e102_ss_writes.py` | **NEW** | E10.2 | Tests for 3-section SS writes in _run_phase1(), atomic TurnLock, control/scoreboard/affective_now population |
| `tests/poc/test_m10_e103_tier_routing.py` | **NEW** | E10.3 | Tests for AUTO tier, HIGH-tier Planner handoff, CRISIS short-circuit, routing observability events |
| `tests/poc/test_m10_e104_adapter.py` | **NEW** | E10.4 | Tests for UltraBERTAdapter protocol, K1UltraBERTAdapter, stub mode, warmup, bootstrap wiring |
| `tests/poc/test_m10_e105_extra_heads.py` | **NEW** | E10.5 | Tests for temporal, relation, embedding head integration into Phase1Result and SS |

---

### Dependency Graph

```
E10.4.1 (K1UltraBERTAdapter)
    |
    v
E10.4.3 (warmup) -----> E10.4.2 (bootstrap wiring) [last, needs all pieces]
    |
    v
E10.1.1 (UltraBERTPhase1Pipeline)
    |
    +---> E10.1.3 (confidence thresholding)
    |         |
    |         v
    +---> E10.1.2 (multi-factor complexity classifier)
    |
    +---> E10.1.4 (graceful degradation)
    |
    v
E10.2.1 (SS control writes) --+
    |                          |
E10.2.2 (SS scoreboard writes)-+---> E10.2.4 (TurnLock atomic)
    |                          |
E10.2.3 (SS affective writes) -+
    |
    v
E10.3.1 (Front AUTO tier from SS)
    |
E10.3.3 (CRISIS safety short-circuit)
    |
E10.3.2 (HIGH-tier Planner handoff)
    |
E10.3.4 (routing observability events)
    |
    v
E10.5.1 (temporal head)
E10.5.2 (relation head)
E10.5.3 (embedding head)
    |
    v
E10.4.2 (bootstrap wiring -- final integration)
    |
    v
E10.4.4 (end-to-end integration test)
```

---

### Execution Plan (5 Epics, 19 Issues)

---

#### PHASE 1: Adapter & Pipeline Foundation (E10.4.1 + E10.1)

**Do first because everything depends on having a working UltraBERT adapter and Phase1Pipeline replacement.**

##### Step 1: E10.4.1 -- K1UltraBERTAdapter (direct `familyos_ultrabert` integration)

**File:** `poc/k1_poc/fsm/ultrabert_adapter.py` (NEW, ~200 lines)

```python
from __future__ import annotations
from typing import Protocol
import threading, time, logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# ---- Mapping constants (K1-owned, no k0 imports) ----
SENTIMENT_TO_VALENCE = {
    "very_negative": 0.1, "negative": 0.3, "neutral": 0.5,
    "positive": 0.7, "very_positive": 0.9,
}
HIGH_AROUSAL_EMOTIONS = {"anger", "excitement", "fear", "surprise"}
LOW_AROUSAL_EMOTIONS = {"sadness", "calm", "boredom", "contentment"}
ENTITY_MIN_CONFIDENCE = 0.65


class UltraBERTAdapter(Protocol):
    """Protocol for UltraBERT analysis -- testable abstraction."""
    def analyze(self, text: str) -> dict | None: ...
    def is_available(self) -> bool: ...
    def get_metrics(self) -> dict: ...


class K1UltraBERTAdapter:
    """K1-native adapter. Directly imports familyos_ultrabert.Client.
    No dependency on k0/runtime/. Owns its own cache, GPU detection,
    singleton pattern, and metric tracking."""

    _instance: K1UltraBERTAdapter | None = None
    _lock = threading.Lock()

    def __init__(self, warmup: bool = False):
        self._client = None  # Lazy init
        self._call_count = 0
        self._total_latency_ms = 0.0
        self._cache_hits = 0
        self._cache_misses = 0
        self._fallback_count = 0
        self._available: bool | None = None
        self._init_client()
        if warmup and self._client:
            self.warmup()

    def _init_client(self):
        try:
            from familyos_ultrabert import Client
            self._client = Client(backend="auto")
            self._available = True
        except (ImportError, Exception) as exc:
            logger.warning("familyos_ultrabert unavailable: %s", exc)
            self._client = None
            self._available = False

    def analyze(self, text: str) -> dict | None:
        if not self._client:
            self._fallback_count += 1
            return None
        # TODO: LRU/TTL cache (64 entries, 30s)
        t0 = time.perf_counter()
        result = self._client.analyze(text)
        elapsed = (time.perf_counter() - t0) * 1000
        self._call_count += 1
        self._total_latency_ms += elapsed
        return self._result_to_dict(result)

    @staticmethod
    def _result_to_dict(result) -> dict:
        return {
            "sentiment": result.sentiment,
            "sentiment_confidence": result.sentiment_confidence,
            "emotions": result.emotions,
            "emotion_scores": result.emotion_scores,
            "safety": result.safety,
            "safety_confidence": result.safety_confidence,
            "entities": result.entities,
            "general_entities": result.general_entities,
            "temporal": result.temporal,
            "intent": result.intent,
            "ingress": result.ingress,
            "relations": result.relations,
            "embedding": result.embedding,
            "latency_ms": result.latency_ms,
        }

    def is_available(self) -> bool:
        return bool(self._available)

    def warmup(self) -> None:
        if self._client:
            t0 = time.perf_counter()
            self.analyze("warmup")
            logger.info("UltraBERT warmup: %.1fms", (time.perf_counter() - t0) * 1000)

    def get_metrics(self) -> dict:
        return {
            "call_count": self._call_count,
            "avg_latency_ms": (self._total_latency_ms / self._call_count) if self._call_count else 0,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "fallback_count": self._fallback_count,
        }

    @classmethod
    def get_instance(cls, warmup: bool = False) -> K1UltraBERTAdapter:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(warmup=warmup)
        return cls._instance


class StubUltraBERTAdapter:
    """Returns None for all analyze() calls. Used in tests without GPU."""
    def analyze(self, text: str) -> dict | None:
        return None
    def is_available(self) -> bool:
        return False
    def get_metrics(self) -> dict:
        return {"stub": True}


def get_ultrabert_adapter(warmup: bool = False) -> UltraBERTAdapter:
    """Singleton factory."""
    return K1UltraBERTAdapter.get_instance(warmup=warmup)
```

**Why K1 adapter first:** Every subsequent issue depends on having a working UltraBERT integration. The adapter directly imports `familyos_ultrabert` -- no k0 imports, no bridge abstraction over external code. K1 owns its own singleton, cache, GPU detection, and metrics.

**No k0 dependency:** The `familyos_ultrabert` pip package is the shared dependency. K0 has its own adapter wrapping the same package. K1 has this adapter. They are independent.

**Test:** `test_m10_e104_adapter.py`

- StubUltraBERTAdapter returns None, is_available() = False
- K1UltraBERTAdapter with monkeypatched `familyos_ultrabert.Client` -> verify dict conversion
- Metrics tracking: call_count, avg_latency_ms, fallback_count
- Singleton pattern: get_ultrabert_adapter() returns same instance
- Warmup: logs timing, increments call_count

##### Step 2: E10.4.3 -- UltraBERT warmup

**File:** `poc/k1_poc/fsm/ultrabert_adapter.py` (already included in K1UltraBERTAdapter above)

- `warmup()` method calls `self.analyze("warmup")` to trigger first-pass latency
- Logs warmup latency at INFO level
- Called from bootstrap.py after adapter creation
- If adapter unavailable, warmup is a no-op with WARNING log

**Test:** Warmup call logged, latency tracked in metrics

##### Step 3: E10.1.1 -- UltraBERTPhase1Pipeline

**File:** `poc/k1_poc/fsm/ultrabert_phase1.py` (NEW, ~200 lines)

```python
class UltraBERTPhase1Pipeline:
    """Real Phase1Pipeline using UltraBERT via adapter."""

    def __init__(self, adapter: UltraBERTAdapter, fallback: StubPhase1Pipeline | None = None):
        self._adapter = adapter
        self._fallback = fallback or StubPhase1Pipeline()

    def classify(self, text: str) -> Phase1Result:
        analysis = self._adapter.analyze(text)
        if analysis is None:
            # Fallback to stub
            return self._fallback.classify(text)
        return self._map_to_phase1_result(analysis)

    def _map_to_phase1_result(self, analysis: dict) -> Phase1Result:
        # Mapping from adapter dict -> Phase1Result fields:
        # analysis["intent"] -> intent_classification
        # analysis["ingress"] -> domain_context
        # analysis["safety"] -> safety_band
        # analysis["sentiment"] -> SENTIMENT_TO_VALENCE -> valence
        # analysis["emotions"][0] -> primary_emotion
        # analysis["emotion_scores"] -> emotion_confidence (max score)
        # analysis["entities"] + analysis["general_entities"] -> entities[]
        # analysis["temporal"] -> temporal_expressions (NEW field)
        # analysis["relations"] -> relations (NEW field)
        # Complexity tier computed by _compute_complexity()
```

**Mapping table (analysis dict key -> Phase1Result field):**

| analysis key | Phase1Result field | Transformation |
|---|---|---|
| `intent` | `intent_classification` | Direct string assignment |
| `intent` + multi-label scores | `intents` | All intents above confidence threshold |
| `ingress` | `domain_context` | Direct string assignment |
| `safety` | `safety_band` | Direct: "GREEN"/"AMBER"/"RED"/"CRISIS" |
| `sentiment` | `valence` | `SENTIMENT_TO_VALENCE[sentiment]` (0.1-0.9) |
| `emotions[0]` | `primary_emotion` | First emotion from sorted list |
| `max(emotion_scores.values())` | `emotion_confidence` | Highest score across 44 classes |
| `emotion_scores` -> arousal inference | `arousal` | Heuristic: high-energy emotions (anger, excitement) -> high arousal |
| `entities` + `general_entities` | `entities` | Merged list of `{text, label, start, end}` dicts |
| `entities`/`general_entities` -> salience | `salience_map` | `{entity_id: 0.8}` for each entity |
| `temporal` | `temporal_expressions` (NEW) | List of temporal spans |
| `relations` | `relations` (NEW) | List of relationship types |
| computed | `complexity_tier` | Multi-factor classifier (step 5) |

**Test:** `test_m10_e101_ultrabert_pipeline.py`

- classify() with mock adapter returning known dict -> verify all 11+2 fields mapped correctly
- classify() with None adapter -> verify fallback to StubPhase1Pipeline
- Sentiment-to-valence mapping edge cases
- Entity merging (family + general NER)

##### Step 4: E10.1.3 -- Confidence thresholding

**File:** `poc/k1_poc/fsm/ultrabert_phase1.py` (extend)

- `INTENT_CONFIDENCE_THRESHOLD = 0.3` (configurable via `get_config().phase1.intent_confidence_threshold`)
- In `_map_to_phase1_result()`: filter multi-label intents by threshold
- Primary intent = argmax (always included regardless of threshold)
- Same threshold applied to domain scores (multi-label ingress)
- Prevents phantom intents from inflating complexity

**Test cases:**

- "hi" -> single intent above threshold -> LOW
- "Book hotel and find restaurant near doctor" -> 3 intents above threshold -> HIGH
- Scores [0.8, 0.3, 0.1, 0.05] with threshold 0.3 -> 2 intents (not 4)

##### Step 5: E10.1.2 -- Multi-factor complexity classifier

**File:** `poc/k1_poc/fsm/ultrabert_phase1.py` (extend)

```python
def _compute_complexity(self, all_intents: list[str], active_domains: list[str],
                        primary_intent: str, entities: list[dict],
                        safety_band: str) -> str:
    """Multi-factor complexity scoring from architecture diagram."""
    score = 0

    # Factor 1: Multi-Intent Score
    if len(all_intents) > 1:
        score += 1

    # Factor 2: Cross-Domain Score
    if len(active_domains) > 1:
        score += 1

    # Factor 3: Intent-Type Score (temporal ambiguity)
    temporal_intents = {"set_reminder", "seek_advice", "reflect"}
    has_temporal = any(e.get("label") in ("DATE_REL", "TIME_REL") for e in entities)
    if primary_intent in temporal_intents and has_temporal:
        score += 1

    # Factor 4: Safety escalation override
    if safety_band in ("RED", "CRISIS"):
        return "LOW"  # Minimize tool exposure

    # Score mapping (configurable thresholds)
    thresholds = get_config().phase1.complexity_thresholds
    # Default: {medium: 1, high: 3}
    if score >= thresholds.get("high", 3):
        return "HIGH"
    elif score >= thresholds.get("medium", 1):
        return "MEDIUM"
    return "LOW"
```

**Test cases:**

- Single intent, single domain -> score 0 -> LOW
- Multi-intent (2+), single domain -> score 1 -> MEDIUM
- Multi-intent + multi-domain -> score 2 -> MEDIUM
- Multi-intent + multi-domain + temporal ambiguity -> score 3 -> HIGH
- Any RED/CRISIS safety -> forced LOW regardless of score

##### Step 6: E10.1.4 -- Graceful degradation

**File:** `poc/k1_poc/fsm/ultrabert_phase1.py` (extend)

- If `adapter.analyze()` returns None or raises: fall back to `StubPhase1Pipeline.classify()`
- Set `Phase1Result.to_metadata()` with `{"degraded": true, "reason": "ultrabert_unavailable"}`
- Emit bus event `k1.phase1.degraded.v1` (RELAXED delivery, observability only)
- Log at WARNING level
- Config flag: `phase1.require_ultrabert: false` (default). When true AND unavailable -> raise error

**Test cases:**

- Adapter returns None -> fallback to stub, metadata has `degraded: true`
- Adapter raises exception -> same fallback
- `require_ultrabert: true` + unavailable -> error raised

---

#### PHASE 2: SessionState Three-Section Feed (E10.2)

**Do second because Front reads SS sections for prompt construction. Without these writes, Phase1 outputs are invisible to the LLM.**

##### Step 7: E10.2.1 -- Write Phase 1 to SS control section

**File:** `poc/k1_poc/fsm/controller.py` (modify `_run_phase1()`)
**File:** `poc/k1_poc/sessionstate/sections/control.py` (add methods)

**New methods on ControlSection:**

```python
def set_intent(self, intent: IntentClassification) -> None:
    """Set classified intent from Phase 1."""
    self._intents = intent
    self._touch()

def get_intents(self) -> IntentClassification:
    """Get current intent classification."""
    return self._intents

def set_complexity_tier(self, tier: str) -> None:
    """Set complexity tier in FSM overlay."""
    self._fsm_overlay["complexity_tier"] = tier
    self._touch()

def get_complexity_tier(self) -> str:
    """Get complexity tier from FSM overlay."""
    return self._fsm_overlay.get("complexity_tier", "")
```

**Changes in `_run_phase1()` (controller.py):**

```python
# After classify() and before TurnLock release:
if self._ss:
    control = self._ss.get_section("control")
    if control:
        control.set_intent(IntentClassification(
            primary=result.intent_classification,
            all_intents=result.intents,
        ))
        control.set_primary_domain(result.domain_context)
        control.escalate_safety(
            band=_band_to_enum(result.safety_band),
            reason="phase1_classification",
        )
        control.set_complexity_tier(result.complexity_tier)
```

**Test:** `test_m10_e102_ss_writes.py`

- After _run_phase1(), verify control.get_intents().primary == result.intent_classification
- Verify control.get_domains().primary_domain == result.domain_context
- Verify control.get_safety().band matches result.safety_band
- Verify control.get_complexity_tier() == result.complexity_tier

##### Step 8: E10.2.2 -- Write Phase 1 to SS scoreboard section

**File:** `poc/k1_poc/fsm/controller.py` (modify `_run_phase1()`)

**Changes in `_run_phase1()` (controller.py):**

```python
# After control writes, still inside TurnLock:
if self._ss:
    scoreboard = self._ss.get_section("scoreboard")
    if scoreboard:
        scoreboard.set_user_intent(result.intent_classification, result.emotion_confidence)
        for entity in result.entities:
            entity_id = entity.get("entity_id", str(uuid.uuid4()))
            scoreboard.add_referent(
                text=entity.get("text", ""),
                entity_id=entity_id,
                entity_type=entity.get("label", ""),
                salience=entity.get("confidence", 0.8),
            )
```

**Existing API verified:** `ScoreboardSection.set_user_intent(intent, confidence)` exists at L988. `add_referent(text, entity_id, entity_type, salience)` exists at L581. Both methods work, no new methods needed.

**Test:**

- After _run_phase1(), verify scoreboard.get_user_intent() == (intent, confidence)
- Verify scoreboard.list_referents() contains entities from Phase1Result
- Verify salience entries created for each entity

##### Step 9: E10.2.3 -- Write Phase 1 to SS affective_now section

**File:** `poc/k1_poc/fsm/controller.py` (modify `_run_phase1()`)

**Changes in `_run_phase1()` (controller.py):**

```python
# After scoreboard writes, still inside TurnLock:
if self._ss:
    affective = self._ss.get_section("affective_now")
    if affective:
        affective.update(
            emotion=result.primary_emotion,
            intensity=result.emotion_confidence,
            valence=result.valence,
            arousal=result.arousal,
            confidence=result.emotion_confidence,
            source="ultrabert",
        )
```

**Existing API verified:** `AffectiveNowSection.update(emotion, intensity, valence, arousal, dominance, confidence, source)` exists at L529. Full method with all needed params. No new methods needed.

**Test:**

- After _run_phase1(), verify affective._current_emotion == result.primary_emotion
- Verify affective._dimensions.valence == result.valence
- Verify affective._source == "ultrabert"

##### Step 10: E10.2.4 -- TurnLock atomic write

**File:** `poc/k1_poc/fsm/controller.py` (modify `_run_phase1()`)

All 3 section writes (steps 7-9) happen inside the existing TurnLock acquire/release block. The current code already acquires TurnLock at L1631 and releases at L1647. We insert the 3 SS writes between classify() and release. Order:

```
TurnLock.acquire("phase1")
  result = classify(text)
  control_ext.set_complexity_tier(result.complexity_tier)  # existing
  # NEW: SS control writes (step 7)
  # NEW: SS scoreboard writes (step 8)
  # NEW: SS affective_now writes (step 9)
  # existing: history metadata attachment
TurnLock.release()
```

If any individual write fails, log error but continue (partial write > no write). Add timing log: `"Phase 1 complete: classify=%dms, ss_writes=%dms, total=%dms"`.

**Test:**

- Verify all 3 sections written inside single TurnLock (mock TurnLock to track)
- Verify partial failure (scoreboard raises) doesn't block affective write
- Verify timing logged

**Same pattern applied to `_run_phase1_with_arbiter()`** -- extract SS writes into a helper method `_write_phase1_to_ss(result: Phase1Result)` called from both paths.

---

#### PHASE 3: Tier Routing & Safety (E10.3)

**Do third because this requires SS writes (Phase 2) to be in place for Front to read tier from SS.**

##### Step 11: E10.3.1 -- Front dispatch_task reads tier from SS control

**File:** `poc/k1_poc/tools/implementations.py` (modify `execute_dispatch_task`)

**Current behavior:** LLM provides tier in tool call args. `tier_raw = args.get("tier", "LOW")`.

**New behavior:**

```python
tier_raw = args.get("tier", "AUTO")
if tier_raw == "AUTO" and ctx.session_state:
    control = ctx.session_state.get_section("control")
    if control and hasattr(control, "get_complexity_tier"):
        ss_tier = control.get_complexity_tier()
        if ss_tier:
            tier_raw = ss_tier
        else:
            tier_raw = "LOW"  # SS has no tier (Phase 1 didn't run)
            logger.warning("dispatch_task: no complexity_tier in SS, defaulting to LOW")
    else:
        tier_raw = "LOW"
```

LLM can still override by providing explicit tier ("LOW"/"MEDIUM"/"HIGH"). Only "AUTO" or omitted tier triggers SS read.

**Test:** `test_m10_e103_tier_routing.py`

- tier="AUTO" + SS has "MEDIUM" -> dispatch with MEDIUM
- tier="LOW" (explicit) + SS has "HIGH" -> dispatch with LOW (LLM override)
- tier="AUTO" + SS empty -> default LOW with warning
- tier omitted -> AUTO behavior

##### Step 12: E10.3.3 -- CRISIS safety-band short-circuit

**File:** `poc/k1_poc/fsm/controller.py` (modify `_run_phase1()`)

After classify() and AFTER SS writes (the SS writes ensure control section has safety_band even if crisis response is returned):

```python
# CRISIS short-circuit
if result.safety_band == "CRISIS":
    self._turn_lock.release()
    # Emit crisis event (RELAXED delivery)
    crisis_env = build_crisis_event(
        payload={"session_id": self._session_id, "safety_band": "CRISIS"},
        parent_id=envelope.envelope_id,
    )
    self._bus.publish(crisis_env)
    logger.critical("Phase 1 CRISIS detected, skipping LLM dispatch")
    # Return canned safety response (no LLM call)
    self._deliver_crisis_response(envelope)
    return

# RED annotation
if result.safety_band == "RED":
    # Annotate envelope for HITL interception
    envelope_payload = _parse_payload(envelope)
    envelope_payload["requires_safety_review"] = True

# AMBER annotation
if result.safety_band == "AMBER":
    envelope_payload = _parse_payload(envelope)
    envelope_payload["safety_note"] = "elevated"
```

**New helper:** `_deliver_crisis_response(envelope)` -- emits a canned safety-protocol response (crisis helpline text) without invoking Front LLM.

**Test:**

- safety_band="CRISIS" -> no Front delivery, crisis event emitted, canned response
- safety_band="RED" -> requires_safety_review=True in envelope
- safety_band="AMBER" -> safety_note="elevated" in envelope
- safety_band="GREEN" -> normal flow (no annotations)

##### Step 13: E10.3.2 -- HIGH-tier Orchestrator -> Planner handoff

**File:** `poc/k1_poc/fsm/controller.py` (modify `_route_via_orchestrator()`)

Replace fail-fast block (L1911-1929):

```python
# BEFORE (current):
if record.tier == ComplexityTier.HIGH:
    logger.warning("HIGH tier not implemented, failing task_id=%s", ...)
    env = build_task_failed(payload={"reason": "HIGH tier not implemented"}, ...)
    self._bus.publish(env)
    return

# AFTER:
if record.tier == ComplexityTier.HIGH:
    logger.info("HIGH tier -> Planner handoff for task_id=%s", dispatch.task_id)
    # PassthroughPlannerStub: wraps single intent as 1-step plan
    # Makes HIGH functionally equivalent to MEDIUM (single plan step)
    # but with correct routing path for future real Planner
    plan_step = {"intent": dispatch.intents[0].to_dict() if dispatch.intents else {},
                 "step_id": f"step-{dispatch.task_id}"}
    committed_plan = {"task_id": dispatch.task_id, "steps": [plan_step]}
    # Route through same MEDIUM path (Orchestrator -> Back)
    # Fall through to existing MEDIUM routing logic below
    record = RoutingRecord(tier=ComplexityTier.MEDIUM, ...)
```

**Why PassthroughPlannerStub:** Real Planner (4-stage pipeline: sketch -> expand -> verify -> commit) is a later milestone. PassthroughPlannerStub makes HIGH tier execute (instead of failing) while maintaining the correct routing path. Back gets 20-iteration budget (HIGH BUDGET_LIMITS) and full tool set.

**Test:**

- HIGH tier task -> no longer emits task.failed
- HIGH tier task -> routes to Back with MEDIUM path (PassthroughPlannerStub)
- HIGH tier task -> gets HIGH budget (20 iterations) from BUDGET_LIMITS

##### Step 14: E10.3.4 -- Tier routing observability events

**File:** `poc/k1_poc/events/conversation.py` (add event classes)
**File:** `poc/k1_poc/bus/builders.py` (add builder functions)

**New canonical events:**

```python
class Phase1Classified(CanonicalEvent):
    """Emitted after every Phase 1 classification."""
    event_type = "k1.phase1.classified.v1"
    # payload: turn_number, complexity_tier, intent_primary, domain_primary,
    #          safety_band, emotion_primary, classification_latency_ms, is_degraded

class TaskRouted(CanonicalEvent):
    """Emitted after task routing decision."""
    event_type = "k1.task.routed.v1"
    # payload: task_id, assigned_tier, routing_path, budget_limit
```

**Emit points:**

- `Phase1Classified`: end of `_run_phase1()` and `_run_phase1_with_arbiter()`, after all SS writes
- `TaskRouted`: end of `_route_via_orchestrator()`, after routing decision

**Test:**

- Verify `Phase1Classified` emitted with correct payload after classification
- Verify `TaskRouted` emitted after routing with correct tier and path

---

#### PHASE 4: Extra Heads & Bootstrap Wiring (E10.5 + E10.4.2-4)

**Do last because these extend the foundation built in Phases 1-3.**

##### Step 15: Phase1Result field extensions (E10.5 prerequisite)

**File:** `poc/k1_poc/fsm/phase1.py` (modify Phase1Result)

Add to `__slots__`:

```python
"temporal_expressions",  # list[dict] from UltraBERT temporal head
"relations",             # list[str] from UltraBERT relation head
```

Add to `__init__`:

```python
temporal_expressions: list[dict[str, Any]] | None = None,
relations: list[str] | None = None,
```

Update `to_metadata()`:

```python
"temporal_expressions": self.temporal_expressions,
"relations": self.relations,
```

##### Step 16: E10.5.1 -- Temporal head integration

**File:** `poc/k1_poc/fsm/ultrabert_phase1.py` (extend `_map_to_phase1_result`)
**File:** `poc/k1_poc/fsm/controller.py` (extend SS writes)

In `_map_to_phase1_result()`: extract `analysis["temporal"]` -> `Phase1Result.temporal_expressions`

In `_write_phase1_to_ss()`: write temporal expressions to scoreboard metadata:

```python
# Write temporal spans as scoreboard metadata for TIME_RESOLUTION engine
if result.temporal_expressions and scoreboard:
    for temporal in result.temporal_expressions:
        scoreboard.add_referent(
            text=temporal.get("text", ""),
            entity_id=f"temporal-{temporal.get('start', 0)}",
            entity_type=temporal.get("label", "TEMPORAL"),
            salience=0.7,
        )
```

**Test:** `test_m10_e105_extra_heads.py`

- "next Saturday" -> temporal_expressions contains DATE_REL span
- Temporal referents added to scoreboard

##### Step 17: E10.5.2 -- Relation head integration

**File:** `poc/k1_poc/fsm/ultrabert_phase1.py` (extend `_map_to_phase1_result`)

In `_map_to_phase1_result()`: extract `analysis["relations"]` -> `Phase1Result.relations`

Relations are stored in Phase1Result metadata (accessible via `to_metadata()`). Not written to SS in M10 (family graph module is a later milestone). The scoreboard referent entries from NER already capture the entity mentions; relations add the relationship type metadata.

**Test:**

- "Mom called about grandma" -> relations contains "parent_of" or similar
- Relations appear in to_metadata() output

##### Step 18: E10.5.3 -- Embedding integration

**File:** `poc/k1_poc/fsm/ultrabert_phase1.py` (extend `_map_to_phase1_result`)

In `_map_to_phase1_result()`: extract `analysis["embedding"]` -> store in Phase1Result metadata dict (NOT a dedicated field -- 768 floats too large for Phase1Result struct).

```python
# In to_metadata(), add conditionally:
if hasattr(self, '_embedding') and self._embedding is not None:
    metadata["embedding_dim"] = len(self._embedding)
    # Actual embedding stored separately (not in metadata dict -- too large)
```

The embedding is cached in the UltraBERTPhase1Pipeline instance for the current turn. Tools like `recall_memory` can access it via `pipeline.last_embedding` property. Full embedding storage in SS is deferred to a later milestone (requires dedicated embedding cache section).

**Test:**

- Verify embedding extracted from analysis dict
- Verify embedding accessible via pipeline.last_embedding
- Verify embedding NOT serialized into to_metadata() (size concern)

##### Step 19: E10.4.2 -- Wire into bootstrap.py

**File:** `poc/k1_poc/kernel/bootstrap.py` (modify)

After FSM creation in `start_kernel()`:

```python
# Phase 1 pipeline selection (config-driven)
pipeline_mode = get_config().phase1.pipeline  # "ultrabert" | "stub"
if pipeline_mode == "ultrabert":
    adapter = K1UltraBERTAdapter(warmup=True)
    if adapter.is_available():
        pipeline = UltraBERTPhase1Pipeline(adapter=adapter)
        logger.info("Phase 1 pipeline: UltraBERT (K1 adapter, direct import)")
    else:
        pipeline = StubPhase1Pipeline()
        logger.warning("Phase 1 pipeline: STUB (familyos_ultrabert unavailable)")
else:
    pipeline = StubPhase1Pipeline()
    logger.info("Phase 1 pipeline: STUB (config: phase1.pipeline=%s)", pipeline_mode)

fsm._phase1_pipeline = pipeline
```

Add to `KernelConfig`:

```python
phase1_pipeline: str = "stub"  # "ultrabert" | "stub" -- default stub for tests
```

**Test:** `test_m10_e104_adapter.py`

- Config `phase1.pipeline: "ultrabert"` + available -> UltraBERTPhase1Pipeline used
- Config `phase1.pipeline: "ultrabert"` + unavailable -> StubPhase1Pipeline fallback
- Config `phase1.pipeline: "stub"` -> StubPhase1Pipeline regardless

##### Step 20: E10.4.4 -- End-to-end integration test

**File:** `tests/poc/test_m10_e104_adapter.py` (extend)

Full-chain test (requires UltraBERT installed, `@pytest.mark.skipif` otherwise):

1. Create FSM with UltraBERTPhase1Pipeline wired
2. Send user.input: "Mom called about grandma's birthday party next Saturday"
3. Verify Phase1Result: intents, entities (KINSHIP: Mom, grandma), temporal (DATE_REL), emotion, domain, safety, complexity >= MEDIUM
4. Verify SS sections: control.get_intents().primary, scoreboard referents for Mom/grandma, affective_now.current_emotion
5. Verify Front dispatch uses correct tier from SS

**This test is the M10 acceptance gate.**

---

### Key Design Decisions

| Decision | Rationale |
|---|---|
| K1-native adapter with direct `familyos_ultrabert` import | Zero dependency on k0/runtime/. K1 owns its own singleton, cache, GPU detection, and mappings. Simplest integration path. Testable with StubUltraBERTAdapter |
| Protocol abstraction (`UltraBERTAdapter`) for testability | Pipeline depends on protocol, not concrete class. StubUltraBERTAdapter for tests, K1UltraBERTAdapter for real inference. Clean swap |
| Helper method `_write_phase1_to_ss(result)` | Shared between `_run_phase1()` and `_run_phase1_with_arbiter()`. Single place to modify SS writes. DRY |
| PassthroughPlannerStub for HIGH tier | HIGH tier must not fail-fast. Real Planner is a later milestone. Passthrough makes HIGH execute via MEDIUM path with HIGH budget |
| CRISIS short-circuit AFTER SS writes | SS must have safety_band even in CRISIS (for observability). Short-circuit prevents LLM invocation but preserves classification data |
| Safety RED/CRISIS forces LOW tier | Minimize tool exposure. The complexity classifier returns LOW for RED/CRISIS regardless of intent/domain scores |
| `Phase1Result.temporal_expressions` and `relations` as new fields | Spec requires 12-head integration. These 2 fields cover the 5 remaining heads not in original Phase1Result (temporal, relation, embedding via metadata) |
| Embedding NOT in Phase1Result fields | 768 floats too large for the dataclass. Stored as pipeline instance state. Accessible via `last_embedding` property |
| Config-driven pipeline selection | Tests run with `phase1.pipeline: "stub"` (no GPU). Production runs with `"ultrabert"`. CI can test both paths |

---

### Test Inventory (Estimated ~85-95 tests)

| Test File | Epic | Est. Tests | Coverage |
|---|---|---|---|
| `test_m10_e101_ultrabert_pipeline.py` | E10.1 | ~25 | Pipeline mapping, complexity classifier, thresholding, degradation |
| `test_m10_e102_ss_writes.py` | E10.2 | ~20 | Control/scoreboard/affective writes, TurnLock atomicity, partial failure |
| `test_m10_e103_tier_routing.py` | E10.3 | ~20 | AUTO tier, HIGH handoff, CRISIS short-circuit, RED/AMBER annotation, observability events |
| `test_m10_e104_adapter.py` | E10.4 | ~15 | Adapter protocol, K1UltraBERTAdapter/stub modes, warmup, bootstrap wiring, e2e integration |
| `test_m10_e105_extra_heads.py` | E10.5 | ~10 | Temporal/relation/embedding integration, Phase1Result extensions |

**All tests use `StubUltraBERTAdapter` by default (no GPU required).** Integration tests with real UltraBERT are `@pytest.mark.skipif(not is_ultrabert_available())`.

---

### Risk Matrix

| Risk | Impact | Mitigation |
|---|---|---|
| UltraBERT not installed in CI | Tests skip real classification | StubUltraBERTAdapter + monkeypatched analysis dicts cover all logic paths |
| K0 adapter import fails in K1 | Bridge creation fails | NOT APPLICABLE -- K1 adapter imports `familyos_ultrabert` directly, no k0 dependency. If pip package missing, `try/except ImportError` falls back to StubUltraBERTAdapter |
| ControlSection.set_intent() breaks FlatBuffer serialization | SS corruption | Add set_intent to FlatBuffer serialization path, test round-trip |
| _run_phase1() performance regression (3 extra SS writes) | Turn latency increase | Target: < 5ms for 3 SS writes (in-memory sections, no I/O). Log timing |
| HIGH tier PassthroughPlannerStub masks real Planner need | Technical debt | Documented as explicit stub. Real Planner is M10+ milestone. Tests verify HIGH routes correctly |
| CRISIS short-circuit skips LLM | User gets canned response | Correct behavior for safety. Canned response includes crisis helpline info |

---

### Config Additions

```yaml
phase1:
  pipeline: "stub"  # "ultrabert" | "stub"
  require_ultrabert: false  # When true + unavailable -> error
  intent_confidence_threshold: 0.3
  complexity_thresholds:
    medium: 1
    high: 3

ultrabert:
  warmup: true
```

---

### Execution Summary

| Phase | Epics | Steps | Key Deliverable |
|---|---|---|---|
| Phase 1 | E10.4.1, E10.1 | Steps 1-6 | Working UltraBERTPhase1Pipeline with K1 adapter, complexity classifier, degradation |
| Phase 2 | E10.2 | Steps 7-10 | Phase 1 outputs written to 3 SS sections inside TurnLock |
| Phase 3 | E10.3 | Steps 11-14 | AUTO tier from SS, CRISIS short-circuit, HIGH Planner handoff, observability |
| Phase 4 | E10.5, E10.4 | Steps 15-20 | Extra heads, bootstrap wiring, end-to-end integration test |

**Total: 5 epics, 19 issues, 4 phases, ~85-95 tests, 2 new files, 8 modified files**
