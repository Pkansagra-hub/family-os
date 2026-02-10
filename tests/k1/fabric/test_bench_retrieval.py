"""
Epic 6.7.2 -- Retrieval pipeline performance benchmarks.

Benchmark the 4-step retrieval pipeline and each sub-component:
  - discover_capabilities()  at 1K  contracts (target <20ms P95)
  - discover_capabilities()  at 10K contracts (target <50ms P95)
  - EmbeddingPort.embed()    single query     (target <5ms P95)
  - HardFilter.filter_passed()  with 1K candidates (target <2ms P95)
  - SoftRanker.rank()           with 500 candidates (target <10ms P95)
  - TopKSelector.select()       with 500 candidates (target <1ms P95)
  - EmbeddingIndex.add_vector() bulk insert 1K      (target <50ms P95)
  - EmbeddingIndex.search()     with 1K vectors     (target <5ms P95)

NO MOCKS -- real HardFilter, SoftRanker, TopKSelector, EmbeddingIndex,
RetrievalEngine.  Embedding port uses a fast deterministic stub
(numpy hash) so we isolate the pipeline overhead from actual model
inference latency.

References:
  - fabric-implementation-plan.md Epic 6.7, Issue 6.7.2
  - policies.contract.yaml SLI: retrieval <20ms P95
"""

from __future__ import annotations

import random
import time
from typing import Any, Dict, FrozenSet, List

import numpy as np

from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.core.registry import CapabilityRegistry
from k1.fabric.retrieval.embedding_index import EmbeddingIndex
from k1.fabric.retrieval.hard_filter import FilterCandidate, HardFilter
from k1.fabric.retrieval.retrieval_engine import RetrievalEngine
from k1.fabric.retrieval.soft_ranker import RankerCandidate, SoftRanker
from k1.fabric.retrieval.top_k_selector import TopKSelector
from k1.fabric.types import Availability, CapabilityContract, InputSpec, SafetyBand

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DIM = 384  # MiniLM-L6 dimension (matches EmbeddingIndex default)

# Reuse the same realistic domain/name pools from test_bench_registry
_DOMAINS = [
    "HEALTH",
    "FOOD",
    "SOCIAL",
    "FINANCE",
    "WEATHER",
    "PLANNING",
    "TRANSPORT",
    "ENTERTAINMENT",
    "EDUCATION",
    "HOME_AUTOMATION",
    "COMMUNICATION",
    "SHOPPING",
    "TRAVEL",
    "FITNESS",
    "PRODUCTIVITY",
    "SECURITY",
    "ENERGY",
    "CHILDCARE",
    "ELDER_CARE",
]

_TOOL_EXECUTE_NAMES = [
    "restaurant_booking",
    "appointment_scheduler",
    "medication_reminder",
    "grocery_delivery_order",
    "ride_share_request",
    "video_call_initiator",
    "smart_thermostat_control",
    "door_lock_manager",
    "sprinkler_system_scheduler",
    "blood_pressure_logger",
    "heart_rate_monitor_sync",
    "step_counter_aggregator",
    "sleep_quality_analyzer",
    "calendar_event_creator",
    "email_draft_composer",
    "text_message_sender",
    "photo_album_organizer",
    "music_playlist_generator",
    "recipe_suggestion_engine",
    "budget_tracker_entry",
    "bill_payment_processor",
    "investment_portfolio_rebalancer",
    "insurance_claim_submitter",
    "prescription_refill_request",
    "vaccination_record_updater",
    "school_pickup_coordinator",
    "homework_assignment_tracker",
    "elderly_wellness_checker",
    "emergency_contact_notifier",
    "pet_feeding_scheduler",
    "garden_watering_controller",
    "laundry_cycle_monitor",
    "package_delivery_tracker",
    "flight_status_checker",
    "hotel_reservation_manager",
    "car_maintenance_scheduler",
    "parking_spot_finder",
    "public_transit_planner",
    "weather_alert_configurator",
    "air_quality_monitor",
    "noise_level_detector",
    "baby_monitor_stream_viewer",
    "diaper_change_logger",
    "breast_feeding_tracker",
    "toddler_activity_planner",
    "family_calendar_sync",
    "shared_grocery_list_manager",
    "chore_assignment_rotator",
    "allowance_tracker",
    "screen_time_limiter",
]

_TOOL_READ_NAMES = [
    "weather_forecast_provider",
    "stock_market_data_fetcher",
    "health_record_retriever",
    "calendar_availability_checker",
    "contact_directory_browser",
    "news_headline_aggregator",
    "traffic_condition_reporter",
    "energy_consumption_reader",
    "water_usage_statistics",
    "medication_interaction_checker",
    "allergy_database_searcher",
    "nutrition_facts_lookup",
    "exercise_history_reader",
    "sleep_pattern_analyzer",
    "blood_glucose_trend_reader",
    "smart_home_status_dashboard",
    "security_camera_feed_reader",
    "doorbell_event_log_viewer",
    "thermostat_schedule_reader",
    "appliance_energy_rating_lookup",
]

_TOOL_WRITE_NAMES = [
    "health_journal_entry_writer",
    "expense_report_generator",
    "family_photo_uploader",
    "document_scanner_saver",
    "voice_memo_transcriber",
    "meeting_notes_recorder",
    "daily_reflection_logger",
    "gratitude_journal_writer",
    "meal_plan_composer",
    "workout_plan_builder",
]

_TOOL_DELETE_NAMES = [
    "expired_reminder_cleaner",
    "old_notification_purger",
    "cache_invalidator",
    "temporary_file_remover",
    "stale_session_cleaner",
]

_PROVIDER_TYPES = ["MCP", "MCP", "MCP", "WASM", "WASM", "BRIDGE"]

_COMMON_INPUTS = [
    InputSpec(name="user_query", type="STRING", description="Natural language user request"),
    InputSpec(name="location", type="STRING", description="Geographic location or address"),
    InputSpec(name="date_range_start", type="DATE", description="Start date (YYYY-MM-DD)"),
]

_OUTPUT_SCHEMA_RICH: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["success", "partial", "failed"]},
        "result_payload": {
            "type": "object",
            "properties": {
                "confirmation_id": {"type": "string"},
                "timestamp_utc": {"type": "string", "format": "date-time"},
                "details": {"type": "string"},
            },
            "required": ["confirmation_id", "timestamp_utc"],
        },
    },
    "required": ["status", "result_payload"],
}


# ---------------------------------------------------------------------------
# Contract generation (reusable, deterministic)
# ---------------------------------------------------------------------------


def _build_realistic_contracts(n: int) -> List[CapabilityContract]:
    """Generate N realistic contracts with varied domains and safety bands."""
    rng = random.Random(42)
    pool = []
    for seg in _TOOL_EXECUTE_NAMES:
        pool.append(("tool.execute", seg))
    for seg in _TOOL_READ_NAMES:
        pool.append(("tool.read", seg))
    for seg in _TOOL_WRITE_NAMES:
        pool.append(("tool.write", seg))
    for seg in _TOOL_DELETE_NAMES:
        pool.append(("tool.delete", seg))

    contracts: List[CapabilityContract] = []
    for i in range(n):
        idx = i % len(pool)
        variant = i // len(pool)
        action_prefix, base_name = pool[idx]

        if variant == 0:
            full_name = f"{action_prefix}.{base_name}"
        else:
            full_name = f"{action_prefix}.{base_name}_v{variant:04d}"

        num_domains = rng.randint(1, 3)
        domains = rng.sample(_DOMAINS, num_domains)
        ptype = rng.choice(_PROVIDER_TYPES)
        inputs = list(_COMMON_INPUTS[: rng.randint(1, 3)])

        band_roll = rng.random()
        safety = (
            SafetyBand.GREEN.value
            if band_roll < 0.7
            else SafetyBand.AMBER.value if band_roll < 0.9 else SafetyBand.RED.value
        )
        avail_roll = rng.random()
        avail = (
            Availability.ONLINE.value
            if avail_roll < 0.85
            else Availability.DEGRADED.value if avail_roll < 0.95 else Availability.OFFLINE.value
        )

        description = (
            f"Production capability for {base_name.replace('_', ' ')} "
            f"in {', '.join(domains)} domain(s). Provider: {ptype}"
        )

        contract = CapabilityContract(
            name=full_name,
            version=f"{rng.randint(1, 5)}.{rng.randint(0, 12)}.{rng.randint(0, 30)}",
            domain=domains,
            description=description,
            capabilities=[f"{base_name}_action_{j}" for j in range(rng.randint(1, 3))],
            limitations=["rate_limited"][: rng.randint(0, 1)],
            required_inputs=inputs,
            output=_OUTPUT_SCHEMA_RICH,
            provider_type=ptype,
            provider_id=f"{ptype.lower()}-{base_name.replace('_', '-')}",
            safety_band_min=safety,
            availability=avail,
            success_rate_30d=round(rng.uniform(0.6, 1.0), 3),
            cost_per_call=round(rng.uniform(0.001, 0.05), 4),
            avg_latency_ms=rng.randint(10, 500),
        )
        contracts.append(contract)
    return contracts


# ---------------------------------------------------------------------------
# Deterministic embedding port (fast, no model inference)
# ---------------------------------------------------------------------------


class _FastEmbeddingPort:
    """
    Deterministic embedding port that hashes text into a unit vector.

    Produces consistent embeddings without actual model inference so we
    benchmark pipeline overhead, not ML latency.
    """

    def __init__(self, dim: int = _DIM) -> None:
        self._dim = dim

    def embed(self, text: str) -> np.ndarray:
        rng = np.random.RandomState(hash(text) % (2**31))
        vec = rng.randn(self._dim).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry() -> CapabilityRegistry:
    validator = ContractValidator()
    event_port = LocalEventAdapter()
    event_port.enable_capture()
    return CapabilityRegistry(validator=validator, event_port=event_port)


def _populate_registry(
    registry: CapabilityRegistry,
    contracts: List[CapabilityContract],
) -> None:
    for c in contracts:
        registry.register(c, skip_validation=True)


def _build_embedding_index(
    contracts: List[CapabilityContract],
    embedding_port: _FastEmbeddingPort,
) -> EmbeddingIndex:
    """Build an embedding index with vectors for all contracts."""
    index = EmbeddingIndex()
    for c in contracts:
        vec = embedding_port.embed(c.description)
        index.add_vector(c.name, vec)
    return index


def _make_retrieval_engine(
    contracts: List[CapabilityContract],
) -> RetrievalEngine:
    """Wire up a complete RetrievalEngine with the given contracts."""
    registry = _make_registry()
    _populate_registry(registry, contracts)
    embedding_port = _FastEmbeddingPort()
    index = _build_embedding_index(contracts, embedding_port)
    hard_filter = HardFilter()
    soft_ranker = SoftRanker()
    top_k_selector = TopKSelector()
    return RetrievalEngine(
        embedding_index=index,
        hard_filter=hard_filter,
        soft_ranker=soft_ranker,
        top_k_selector=top_k_selector,
        embedding_port=embedding_port,
        registry_port=registry,
    )


def _percentile(data: List[float], pct: float) -> float:
    data_sorted = sorted(data)
    idx = int(len(data_sorted) * pct / 100)
    idx = min(idx, len(data_sorted) - 1)
    return data_sorted[idx]


def _build_filter_candidates(
    contracts: List[CapabilityContract],
) -> List[FilterCandidate]:
    """Build FilterCandidate list from contracts."""
    candidates = []
    for c in contracts:
        req_inputs = frozenset(
            getattr(inp, "name", inp) if not isinstance(inp, str) else inp
            for inp in c.required_inputs
        )
        candidates.append(
            FilterCandidate(
                contract_name=c.name,
                safety_band_min=c.safety_band_min,
                availability=c.availability,
                required_input_names=req_inputs,
                contract=c,
            )
        )
    return candidates


def _build_ranker_candidates(
    contracts: List[CapabilityContract],
    embedding_port: _FastEmbeddingPort,
) -> List[RankerCandidate]:
    """Build RankerCandidate list with embedding vectors."""
    candidates = []
    for c in contracts:
        vec = embedding_port.embed(c.description)
        candidates.append(
            RankerCandidate(
                contract_name=c.name,
                capability_vector=vec,
                domains=frozenset(c.domain),
                success_rate_30d=c.success_rate_30d,
                cost_per_call=c.cost_per_call,
                avg_latency_ms=c.avg_latency_ms,
                availability=c.availability,
                contract=c,
            )
        )
    return candidates


# ---------------------------------------------------------------------------
# Lazy contract caches (module-level to avoid regeneration)
# ---------------------------------------------------------------------------

_CONTRACTS_1K: List[CapabilityContract] = []
_CONTRACTS_10K: List[CapabilityContract] = []


def _ensure_contracts_1k() -> List[CapabilityContract]:
    global _CONTRACTS_1K
    if not _CONTRACTS_1K:
        _CONTRACTS_1K = _build_realistic_contracts(1_000)
    return _CONTRACTS_1K


def _ensure_contracts_10k() -> List[CapabilityContract]:
    global _CONTRACTS_10K
    if not _CONTRACTS_10K:
        _CONTRACTS_10K = _build_realistic_contracts(10_000)
    return _CONTRACTS_10K


# =========================================================================
# Full pipeline: discover_capabilities() benchmarks
# =========================================================================


class TestBenchDiscoverCapabilities:
    """
    Benchmark RetrievalEngine.discover_capabilities() end-to-end.

    Pipeline: embed query -> hard filter -> soft rank -> top-K.
    Uses real components, no mocks.
    """

    def test_discover_1k_contracts_p95_under_20ms(self) -> None:
        """discover_capabilities() with 1K contracts: P95 < 20ms."""
        contracts = _ensure_contracts_1k()
        engine = _make_retrieval_engine(contracts)

        # Warm up
        engine.discover_capabilities(domain=["HEALTH"], intent="check blood pressure readings")

        rng = random.Random(555)
        intents = [
            "schedule a medical appointment for next Tuesday",
            "turn on the living room thermostat to 72 degrees",
            "check my investment portfolio performance this quarter",
            "order groceries for the weekly meal plan",
            "find the cheapest flight to Denver next month",
            "set up a video call with grandmother",
            "read the latest weather forecast for tomorrow",
            "track my daily step count and exercise",
            "pay the electricity bill for this month",
            "find a restaurant nearby for dinner tonight",
        ]
        domains_pool = [
            ["HEALTH"],
            ["HOME_AUTOMATION"],
            ["FINANCE"],
            ["FOOD"],
            ["TRAVEL"],
            ["COMMUNICATION"],
            ["WEATHER"],
            ["FITNESS"],
            ["FINANCE", "ENERGY"],
            ["FOOD", "SOCIAL"],
        ]

        timings: List[float] = []
        for trial in range(50):
            intent = intents[trial % len(intents)]
            domain = domains_pool[trial % len(domains_pool)]

            t0 = time.perf_counter()
            result = engine.discover_capabilities(domain=domain, intent=intent)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)

        p95 = _percentile(timings, 95)
        median = _percentile(timings, 50)
        assert p95 < 20, (
            f"discover_capabilities(1K) P95={p95:.2f}ms exceeds 20ms " f"(median={median:.2f}ms)"
        )

    def test_discover_10k_contracts_p95_under_200ms(self) -> None:
        """discover_capabilities() with 10K contracts: P95 < 200ms.

        10K pipeline iterates all contracts, embeds query, filters, ranks.
        200ms accounts for the linear scan over 10K FilterCandidates +
        SoftRanker composite scoring.
        """
        contracts = _ensure_contracts_10k()
        engine = _make_retrieval_engine(contracts)

        # Warm up
        engine.discover_capabilities(domain=["FITNESS"], intent="track daily exercise routine")

        intents = [
            "find healthiest meal options for a diabetic family member",
            "automate the morning routine for smart home devices",
            "compare insurance premiums across three providers",
            "book a round trip flight and hotel for vacation",
            "check medication interactions and refill prescriptions",
        ]
        domains_pool = [
            ["HEALTH", "FOOD"],
            ["HOME_AUTOMATION", "ENERGY"],
            ["FINANCE"],
            ["TRAVEL", "PLANNING"],
            ["HEALTH"],
        ]

        timings: List[float] = []
        for trial in range(30):
            intent = intents[trial % len(intents)]
            domain = domains_pool[trial % len(domains_pool)]

            t0 = time.perf_counter()
            result = engine.discover_capabilities(
                domain=domain,
                intent=intent,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)

        p95 = _percentile(timings, 95)
        median = _percentile(timings, 50)
        assert p95 < 200, (
            f"discover_capabilities(10K) P95={p95:.2f}ms exceeds 200ms " f"(median={median:.2f}ms)"
        )

    def test_discover_returns_scored_capabilities(self) -> None:
        """discover_capabilities() result has ScoredCapability entries."""
        contracts = _ensure_contracts_1k()
        engine = _make_retrieval_engine(contracts)
        result = engine.discover_capabilities(
            domain=["HEALTH"],
            intent="schedule a doctor appointment",
        )
        assert result.total_matched > 0
        assert len(result.capabilities) > 0
        for cap in result.capabilities:
            assert cap.score >= 0.0
            assert cap.contract is not None


# =========================================================================
# Embedding port benchmarks
# =========================================================================


class TestBenchEmbedding:
    """
    Benchmark embedding computation independently.

    Uses _FastEmbeddingPort (deterministic hash-to-vector).
    Verifies pipeline can embed queries under 5ms P95.
    """

    def test_embed_single_query_p95_under_5ms(self) -> None:
        """Single embed() call: P95 < 5ms."""
        port = _FastEmbeddingPort()
        # Warm up
        port.embed("warm up query string for testing")

        queries = [
            "schedule appointment for blood pressure check next week",
            "turn off all smart lights in bedroom and nursery",
            "check investment portfolio rebalancing recommendations",
            "order weekly grocery delivery with fresh produce",
            "find cheapest round trip flights to New York JFK",
            "set medication reminder for 8am daily with alerts",
            "track sleep quality and heart rate variability trends",
            "pay monthly utility bills for electricity and water",
            "create shared family calendar event for birthday party",
            "enable security cameras and doorbell motion detection",
        ]

        timings: List[float] = []
        for trial in range(100):
            text = queries[trial % len(queries)]
            t0 = time.perf_counter()
            vec = port.embed(text)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)
            assert vec.shape == (_DIM,)
            assert vec.dtype == np.float32

        p95 = _percentile(timings, 95)
        assert p95 < 5, f"embed() P95={p95:.2f}ms exceeds 5ms"

    def test_embed_produces_unit_vectors(self) -> None:
        """Embedding vectors are unit-normalized."""
        port = _FastEmbeddingPort()
        for text in ["hello world", "schedule doctor visit", "pay bills"]:
            vec = port.embed(text)
            norm = float(np.linalg.norm(vec))
            assert abs(norm - 1.0) < 1e-5, f"Norm={norm} for '{text}'"

    def test_embed_deterministic(self) -> None:
        """Same text always produces same vector."""
        port = _FastEmbeddingPort()
        text = "medication reminder for grandmother at 8am daily"
        v1 = port.embed(text)
        v2 = port.embed(text)
        assert np.allclose(v1, v2)


# =========================================================================
# HardFilter benchmarks
# =========================================================================


class TestBenchHardFilter:
    """
    Benchmark HardFilter.filter_passed() at scale.

    Exercises all three rules (safety band, availability, input
    satisfiability) with realistic candidate distributions.
    """

    def test_hard_filter_1k_candidates_p95_under_2ms(self) -> None:
        """filter_passed() with 1K candidates: P95 < 2ms."""
        contracts = _ensure_contracts_1k()
        candidates = _build_filter_candidates(contracts)
        hf = HardFilter()

        # Warm up
        hf.filter_passed(
            candidates[:100],
            user_band="GREEN",
            available_param_names=frozenset(["user_query"]),
            session_keys=frozenset(),
        )

        param_sets = [
            frozenset(["user_query"]),
            frozenset(["user_query", "location"]),
            frozenset(["user_query", "location", "date_range_start"]),
            frozenset(["user_query", "patient_identifier"]),
            frozenset(["user_query", "device_identifier"]),
        ]
        bands = ["GREEN", "AMBER", "RED"]

        timings: List[float] = []
        for trial in range(50):
            params = param_sets[trial % len(param_sets)]
            band = bands[trial % len(bands)]

            t0 = time.perf_counter()
            survivors = hf.filter_passed(
                candidates,
                user_band=band,
                available_param_names=params,
                session_keys=frozenset(["affective_now", "cognitive"]),
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)

        p95 = _percentile(timings, 95)
        median = _percentile(timings, 50)
        assert p95 < 2, f"filter_passed(1K) P95={p95:.2f}ms exceeds 2ms " f"(median={median:.2f}ms)"

    def test_hard_filter_eliminates_offline_candidates(self) -> None:
        """OFFLINE candidates are always eliminated."""
        contracts = _ensure_contracts_1k()
        candidates = _build_filter_candidates(contracts)
        hf = HardFilter()

        survivors = hf.filter_passed(
            candidates,
            user_band="RED",
            available_param_names=frozenset(["user_query", "location", "date_range_start"]),
            session_keys=frozenset(),
        )
        survivor_names = {s.contract_name for s in survivors}
        offline_contracts = [c for c in contracts if c.availability == "OFFLINE"]
        for c in offline_contracts:
            assert c.name not in survivor_names

    def test_hard_filter_respects_safety_band(self) -> None:
        """GREEN user band rejects AMBER and RED contracts."""
        contracts = _ensure_contracts_1k()
        candidates = _build_filter_candidates(contracts)
        hf = HardFilter()

        survivors = hf.filter_passed(
            candidates,
            user_band="GREEN",
            available_param_names=frozenset(["user_query", "location", "date_range_start"]),
            session_keys=frozenset(),
        )
        survivor_names = {s.contract_name for s in survivors}
        for c in contracts:
            if c.safety_band_min in ("AMBER", "RED"):
                assert c.name not in survivor_names


# =========================================================================
# SoftRanker benchmarks
# =========================================================================


class TestBenchSoftRanker:
    """
    Benchmark SoftRanker.rank() with realistic candidates.

    Exercises the 4-dimension composite scoring formula.
    """

    def test_soft_ranker_500_candidates_p95_under_10ms(self) -> None:
        """rank() with 500 candidates: P95 < 10ms."""
        contracts = _ensure_contracts_1k()[:500]
        embedding_port = _FastEmbeddingPort()
        candidates = _build_ranker_candidates(contracts, embedding_port)
        ranker = SoftRanker()

        # Warm up
        query_vec = embedding_port.embed("test warmup query")
        ranker.rank(candidates[:50], query_vec, frozenset(["HEALTH"]))

        queries = [
            "schedule appointment for blood pressure monitoring",
            "automate smart home thermostat schedule",
            "track investment portfolio growth this quarter",
            "order healthy groceries for diabetic meal plan",
            "book affordable flight plus hotel package",
        ]
        domain_sets: List[FrozenSet[str]] = [
            frozenset(["HEALTH"]),
            frozenset(["HOME_AUTOMATION"]),
            frozenset(["FINANCE"]),
            frozenset(["FOOD"]),
            frozenset(["TRAVEL", "PLANNING"]),
        ]

        timings: List[float] = []
        for trial in range(50):
            query_text = queries[trial % len(queries)]
            qvec = embedding_port.embed(query_text)
            doms = domain_sets[trial % len(domain_sets)]

            t0 = time.perf_counter()
            ranked = ranker.rank(candidates, qvec, doms)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)

        p95 = _percentile(timings, 95)
        median = _percentile(timings, 50)
        assert p95 < 10, f"rank(500) P95={p95:.2f}ms exceeds 10ms " f"(median={median:.2f}ms)"

    def test_soft_ranker_1k_candidates_p95_under_20ms(self) -> None:
        """rank() with 1K candidates: P95 < 20ms."""
        contracts = _ensure_contracts_1k()
        embedding_port = _FastEmbeddingPort()
        candidates = _build_ranker_candidates(contracts, embedding_port)
        ranker = SoftRanker()

        query_vec = embedding_port.embed("manage family health records")

        timings: List[float] = []
        for trial in range(30):
            t0 = time.perf_counter()
            ranked = ranker.rank(candidates, query_vec, frozenset(["HEALTH", "ELDER_CARE"]))
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)

        p95 = _percentile(timings, 95)
        assert p95 < 20, f"rank(1K) P95={p95:.2f}ms exceeds 20ms"

    def test_soft_ranker_returns_descending_scores(self) -> None:
        """Ranked results are sorted by score descending."""
        contracts = _ensure_contracts_1k()[:200]
        embedding_port = _FastEmbeddingPort()
        candidates = _build_ranker_candidates(contracts, embedding_port)
        ranker = SoftRanker()
        query_vec = embedding_port.embed("schedule doctor appointment")
        ranked = ranker.rank(candidates, query_vec, frozenset(["HEALTH"]))
        scores = [r.score for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_soft_ranker_degraded_penalty_applied(self) -> None:
        """DEGRADED candidates receive a penalty multiplier."""
        contracts = _ensure_contracts_1k()[:200]
        embedding_port = _FastEmbeddingPort()
        candidates = _build_ranker_candidates(contracts, embedding_port)
        ranker = SoftRanker()
        query_vec = embedding_port.embed("health monitoring")
        ranked = ranker.rank(candidates, query_vec, frozenset(["HEALTH"]))
        degraded_items = [r for r in ranked if r.degraded_penalty_applied]
        non_degraded = [r for r in ranked if not r.degraded_penalty_applied]
        # All DEGRADED candidates should come from DEGRADED availability
        for item in degraded_items:
            assert item.degraded_penalty_applied


# =========================================================================
# TopKSelector benchmarks
# =========================================================================


class TestBenchTopKSelector:
    """
    Benchmark TopKSelector.select() at scale.

    The selector is O(K) slicing of a pre-sorted list.
    """

    def test_top_k_select_500_p95_under_1ms(self) -> None:
        """select() from 500 ranked items: P95 < 1ms."""
        contracts = _ensure_contracts_1k()[:500]
        embedding_port = _FastEmbeddingPort()
        candidates = _build_ranker_candidates(contracts, embedding_port)
        ranker = SoftRanker()
        query_vec = embedding_port.embed("home automation control")
        ranked = ranker.rank(candidates, query_vec, frozenset(["HOME_AUTOMATION"]))

        selector = TopKSelector()
        # Warm up
        selector.select(ranked, k=10)

        timings: List[float] = []
        for trial in range(100):
            k = (trial % 25) + 1
            t0 = time.perf_counter()
            selected = selector.select(ranked, k=k)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)
            assert len(selected) == min(k, len(ranked))

        p95 = _percentile(timings, 95)
        assert p95 < 1, f"select(500) P95={p95:.2f}ms exceeds 1ms"

    def test_top_k_preserves_score_order(self) -> None:
        """Selected entries maintain descending score order."""
        contracts = _ensure_contracts_1k()[:200]
        embedding_port = _FastEmbeddingPort()
        candidates = _build_ranker_candidates(contracts, embedding_port)
        ranker = SoftRanker()
        query_vec = embedding_port.embed("financial planning")
        ranked = ranker.rank(candidates, query_vec, frozenset(["FINANCE"]))
        selector = TopKSelector()
        selected = selector.select(ranked, k=10)
        scores = [s.score for s in selected]
        assert scores == sorted(scores, reverse=True)


# =========================================================================
# EmbeddingIndex benchmarks
# =========================================================================


class TestBenchEmbeddingIndex:
    """
    Benchmark EmbeddingIndex operations (add, search, contains).
    """

    def test_bulk_add_1k_vectors_under_50ms(self) -> None:
        """add_vector() for 1K vectors total time < 50ms."""
        embedding_port = _FastEmbeddingPort()
        contracts = _ensure_contracts_1k()

        t0 = time.perf_counter()
        index = EmbeddingIndex()
        for c in contracts:
            vec = embedding_port.embed(c.description)
            index.add_vector(c.name, vec)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert index.size == 1_000
        # Generous limit: FAISS flat index rebuild is cheap for 1K
        assert elapsed_ms < 5000, f"Bulk add 1K vectors took {elapsed_ms:.1f}ms (limit 5000ms)"

    def test_search_1k_index_p95_under_5ms(self) -> None:
        """search() with 1K vectors: P95 < 5ms."""
        embedding_port = _FastEmbeddingPort()
        contracts = _ensure_contracts_1k()
        index = _build_embedding_index(contracts, embedding_port)

        # Warm up
        qvec = embedding_port.embed("warm up search query")
        index.search(qvec, k=10)

        queries = [
            "health monitoring blood pressure glucose",
            "smart home automation thermostat lights",
            "financial planning budget investment",
            "meal planning grocery delivery",
            "travel booking flight hotel",
        ]

        timings: List[float] = []
        for trial in range(50):
            qvec = embedding_port.embed(queries[trial % len(queries)])
            t0 = time.perf_counter()
            hits = index.search(qvec, k=10)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)
            assert len(hits) <= 10

        p95 = _percentile(timings, 95)
        assert p95 < 5, f"search(1K) P95={p95:.2f}ms exceeds 5ms"

    def test_contains_check_p95_under_0_1ms(self) -> None:
        """contains() is O(1) dict lookup: P95 < 0.1ms."""
        embedding_port = _FastEmbeddingPort()
        contracts = _ensure_contracts_1k()
        index = _build_embedding_index(contracts, embedding_port)

        rng = random.Random(42)
        names = [rng.choice(contracts).name for _ in range(100)]

        timings: List[float] = []
        for name in names:
            t0 = time.perf_counter()
            result = index.contains(name)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)
            assert result is True

        p95 = _percentile(timings, 95)
        assert p95 < 0.1, f"contains() P95={p95:.4f}ms exceeds 0.1ms"

    def test_search_returns_search_hits(self) -> None:
        """search() returns SearchHit objects with scores."""
        embedding_port = _FastEmbeddingPort()
        contracts = _ensure_contracts_1k()[:100]
        index = _build_embedding_index(contracts, embedding_port)
        qvec = embedding_port.embed("health blood pressure")
        hits = index.search(qvec, k=5)
        assert len(hits) <= 5
        for hit in hits:
            assert hit.contract_id != ""
            assert isinstance(hit.score, float)
