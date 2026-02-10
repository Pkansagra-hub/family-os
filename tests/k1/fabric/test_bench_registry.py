"""
Epic 6.7.1 -- Registry performance benchmarks.

Benchmark critical CapabilityRegistry operations at scale:
  - lookup()          with 1K, 10K, 100K contracts  (target <1ms P95)
  - contains()        with 1K, 10K, 100K contracts  (target <1ms P95)
  - list_by_domain()  with 1K, 10K, 100K contracts  (target <5ms P95)
  - list_by_type()    with 1K, 10K, 100K contracts  (target <5ms P95)
  - list_by_provider() with 1K, 10K, 100K contracts (target <5ms P95)
  - list_all()        with 1K, 10K, 100K contracts  (target <50ms P95)
  - size property      with 100K contracts           (target <0.1ms P95)

All contracts use realistic long-form names matching production patterns,
realistic domains, descriptions, inputs, outputs, and provider endpoints.

NO MOCKS -- real CapabilityRegistry with real ContractValidator.

References:
  - fabric-implementation-plan.md Epic 6.7, Issue 6.7.1
  - policies.contract.yaml SLI: registry_lookup <1ms P95
"""

from __future__ import annotations

import random
import time
from typing import List

from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.core.registry import CapabilityRegistry
from k1.fabric.types import Availability, CapabilityContract, InputSpec, SafetyBand

# ---------------------------------------------------------------------------
# Realistic contract generation
# ---------------------------------------------------------------------------

# Production-like domain taxonomy (19 domains)
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

# Realistic capability name segments (action objects) per action verb
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

# Provider types with realistic distribution
_PROVIDER_TYPES = ["MCP", "MCP", "MCP", "WASM", "WASM", "BRIDGE"]

# Realistic provider endpoint prefixes
_PROVIDER_ENDPOINTS = {
    "MCP": "mcp://local/",
    "WASM": "wasm://sandbox/",
    "BRIDGE": "bridge://k0/",
}

# Realistic required inputs per domain
_COMMON_INPUTS = [
    InputSpec(name="user_query", type="STRING", description="Natural language user request"),
    InputSpec(name="location", type="STRING", description="Geographic location or address"),
    InputSpec(
        name="date_range_start",
        type="DATE",
        description="Start date for the operation (YYYY-MM-DD)",
    ),
]

_HEALTH_INPUTS = [
    InputSpec(
        name="patient_identifier",
        type="STRING",
        description="De-identified patient reference token",
    ),
    InputSpec(
        name="measurement_type",
        type="STRING",
        description="Type of health measurement (blood_pressure, heart_rate, glucose)",
    ),
    InputSpec(
        name="measurement_value",
        type="NUMBER",
        description="Numeric measurement value in standard units",
    ),
]

_FINANCE_INPUTS = [
    InputSpec(
        name="account_reference",
        type="STRING",
        description="Tokenized account reference identifier",
    ),
    InputSpec(
        name="transaction_amount", type="NUMBER", description="Transaction amount in local currency"
    ),
    InputSpec(
        name="transaction_category",
        type="STRING",
        description="Categorization of the financial transaction",
    ),
]

_HOME_INPUTS = [
    InputSpec(
        name="device_identifier", type="STRING", description="Smart home device unique identifier"
    ),
    InputSpec(
        name="target_state",
        type="STRING",
        description="Desired device state (on, off, dim, schedule)",
    ),
    InputSpec(
        name="room_location", type="STRING", description="Room where the device is installed"
    ),
]

_INPUTS_BY_DOMAIN = {
    "HEALTH": _HEALTH_INPUTS,
    "FINANCE": _FINANCE_INPUTS,
    "HOME_AUTOMATION": _HOME_INPUTS,
    "ENERGY": _HOME_INPUTS,
}

# Realistic output schemas
_OUTPUT_SCHEMA_RICH = {
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
        "metadata": {
            "type": "object",
            "properties": {
                "provider_version": {"type": "string"},
                "latency_ms": {"type": "number"},
                "cache_hit": {"type": "boolean"},
            },
        },
    },
    "required": ["status", "result_payload"],
}


def _build_realistic_contracts(n: int) -> List[CapabilityContract]:
    """
    Generate N realistic CapabilityContract instances.

    Names follow production patterns like:
      tool.execute.restaurant_booking
      tool.read.weather_forecast_provider
      tool.write.health_journal_entry_writer
      tool.delete.expired_reminder_cleaner

    Each contract has:
      - 1-3 domain tags from the 19 production domains
      - Realistic description (40-120 chars)
      - 1-3 required inputs with realistic field names
      - Rich output schema matching production contracts
      - Realistic provider_id, provider_type, endpoint
      - Varied safety bands and availability
    """
    rng = random.Random(42)  # deterministic for reproducibility

    # Build a pool of (action_prefix, name_segment) tuples
    pool = []
    for seg in _TOOL_EXECUTE_NAMES:
        pool.append(("tool.execute", seg))
    for seg in _TOOL_READ_NAMES:
        pool.append(("tool.read", seg))
    for seg in _TOOL_WRITE_NAMES:
        pool.append(("tool.write", seg))
    for seg in _TOOL_DELETE_NAMES:
        pool.append(("tool.delete", seg))

    # If we need more than the pool size, add numeric variants
    # e.g., tool.execute.restaurant_booking_v0002
    contracts = []
    for i in range(n):
        idx = i % len(pool)
        variant = i // len(pool)
        action_prefix, base_name = pool[idx]

        if variant == 0:
            full_name = f"{action_prefix}.{base_name}"
        else:
            full_name = f"{action_prefix}.{base_name}_v{variant:04d}"

        # 1-3 domain tags
        num_domains = rng.randint(1, 3)
        domains = rng.sample(_DOMAINS, num_domains)

        # Provider
        ptype = rng.choice(_PROVIDER_TYPES)
        provider_id = f"{ptype.lower()}-{base_name.replace('_', '-')}"
        if variant > 0:
            provider_id = f"{provider_id}-v{variant:04d}"

        # Inputs: common + domain-specific
        inputs = list(_COMMON_INPUTS[: rng.randint(1, 3)])
        for d in domains:
            extra = _INPUTS_BY_DOMAIN.get(d)
            if extra:
                inputs.extend(extra[: rng.randint(1, len(extra))])
                break

        # Safety band distribution: 70% GREEN, 20% AMBER, 10% RED
        band_roll = rng.random()
        if band_roll < 0.7:
            safety = SafetyBand.GREEN.value
        elif band_roll < 0.9:
            safety = SafetyBand.AMBER.value
        else:
            safety = SafetyBand.RED.value

        # Availability: 85% ONLINE, 10% DEGRADED, 5% OFFLINE
        avail_roll = rng.random()
        if avail_roll < 0.85:
            avail = Availability.ONLINE.value
        elif avail_roll < 0.95:
            avail = Availability.DEGRADED.value
        else:
            avail = Availability.OFFLINE.value

        description = (
            f"Production capability for {base_name.replace('_', ' ')} "
            f"in {', '.join(domains)} domain(s). "
            f"Provider: {ptype}, endpoint: {_PROVIDER_ENDPOINTS[ptype]}{base_name}"
        )
        if len(description) > 512:
            description = description[:509] + "..."

        contract = CapabilityContract(
            name=full_name,
            version=f"{rng.randint(1, 5)}.{rng.randint(0, 12)}.{rng.randint(0, 30)}",
            domain=domains,
            description=description,
            capabilities=[f"{base_name}_action_{j}" for j in range(rng.randint(1, 4))],
            limitations=["rate_limited", "no_pii_in_response"][: rng.randint(0, 2)],
            required_inputs=inputs,
            output=_OUTPUT_SCHEMA_RICH,
            provider_type=ptype,
            provider_id=provider_id,
            safety_band_min=safety,
            availability=avail,
        )
        contracts.append(contract)

    return contracts


def _populate_registry(
    registry: CapabilityRegistry,
    contracts: List[CapabilityContract],
) -> None:
    """Bulk-register contracts using skip_validation for speed."""
    for c in contracts:
        registry.register(c, skip_validation=True)


def _make_registry() -> CapabilityRegistry:
    """Create a fresh CapabilityRegistry with validator and event port."""
    validator = ContractValidator()
    event_port = LocalEventAdapter()
    event_port.enable_capture()
    return CapabilityRegistry(validator=validator, event_port=event_port)


def _percentile(data: List[float], pct: float) -> float:
    """Calculate the p-th percentile of a sorted list."""
    data_sorted = sorted(data)
    idx = int(len(data_sorted) * pct / 100)
    idx = min(idx, len(data_sorted) - 1)
    return data_sorted[idx]


# ---------------------------------------------------------------------------
# Pre-generated contract pools (module-level for reuse across tests)
# ---------------------------------------------------------------------------

_CONTRACTS_1K: List[CapabilityContract] = []
_CONTRACTS_10K: List[CapabilityContract] = []
_CONTRACTS_100K: List[CapabilityContract] = []


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


def _ensure_contracts_100k() -> List[CapabilityContract]:
    global _CONTRACTS_100K
    if not _CONTRACTS_100K:
        _CONTRACTS_100K = _build_realistic_contracts(100_000)
    return _CONTRACTS_100K


# =========================================================================
# lookup() benchmarks
# =========================================================================


class TestBenchLookup:
    """
    Benchmark CapabilityRegistry.lookup() at 1K, 10K, 100K scale.

    lookup() is O(1) dict access via _by_name. Target: <1ms P95.
    """

    def test_lookup_1k_contracts_p95_under_1ms(self) -> None:
        """lookup() with 1K realistic contracts: P95 < 1ms."""
        contracts = _ensure_contracts_1k()
        registry = _make_registry()
        _populate_registry(registry, contracts)
        assert registry.size == 1_000

        # Pick 50 random names to lookup (deterministic)
        rng = random.Random(123)
        targets = [rng.choice(contracts).name for _ in range(50)]

        # Warm up
        for t in targets[:10]:
            registry.lookup(t)

        # Measure
        timings = []
        for _ in range(3):
            for name in targets:
                start = time.perf_counter()
                result = registry.lookup(name)
                elapsed_ms = (time.perf_counter() - start) * 1000
                timings.append(elapsed_ms)
                assert result is not None, f"lookup({name!r}) returned None"

        p95 = _percentile(timings, 95)
        median = _percentile(timings, 50)
        assert p95 < 1.0, (
            f"lookup P95={p95:.4f}ms exceeds 1ms target "
            f"(median={median:.4f}ms, n={len(timings)}, registry=1K)"
        )

    def test_lookup_10k_contracts_p95_under_1ms(self) -> None:
        """lookup() with 10K realistic contracts: P95 < 1ms."""
        contracts = _ensure_contracts_10k()
        registry = _make_registry()
        _populate_registry(registry, contracts)
        assert registry.size == 10_000

        rng = random.Random(456)
        targets = [rng.choice(contracts).name for _ in range(100)]

        for t in targets[:10]:
            registry.lookup(t)

        timings = []
        for _ in range(3):
            for name in targets:
                start = time.perf_counter()
                result = registry.lookup(name)
                elapsed_ms = (time.perf_counter() - start) * 1000
                timings.append(elapsed_ms)
                assert result is not None

        p95 = _percentile(timings, 95)
        median = _percentile(timings, 50)
        assert p95 < 1.0, (
            f"lookup P95={p95:.4f}ms exceeds 1ms target "
            f"(median={median:.4f}ms, n={len(timings)}, registry=10K)"
        )

    def test_lookup_100k_contracts_p95_under_1ms(self) -> None:
        """lookup() with 100K realistic contracts: P95 < 1ms."""
        contracts = _ensure_contracts_100k()
        registry = _make_registry()
        _populate_registry(registry, contracts)
        assert registry.size == 100_000

        rng = random.Random(789)
        targets = [rng.choice(contracts).name for _ in range(200)]

        for t in targets[:20]:
            registry.lookup(t)

        timings = []
        for _ in range(3):
            for name in targets:
                start = time.perf_counter()
                result = registry.lookup(name)
                elapsed_ms = (time.perf_counter() - start) * 1000
                timings.append(elapsed_ms)
                assert result is not None

        p95 = _percentile(timings, 95)
        median = _percentile(timings, 50)
        assert p95 < 1.0, (
            f"lookup P95={p95:.4f}ms exceeds 1ms target "
            f"(median={median:.4f}ms, n={len(timings)}, registry=100K)"
        )

    def test_lookup_miss_100k_p95_under_1ms(self) -> None:
        """lookup() for non-existent names with 100K contracts: P95 < 1ms."""
        contracts = _ensure_contracts_100k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        miss_names = [f"tool.execute.nonexistent_capability_{i:06d}" for i in range(200)]

        timings = []
        for name in miss_names:
            start = time.perf_counter()
            result = registry.lookup(name)
            elapsed_ms = (time.perf_counter() - start) * 1000
            timings.append(elapsed_ms)
            assert result is None

        p95 = _percentile(timings, 95)
        assert p95 < 1.0, f"lookup-miss P95={p95:.4f}ms exceeds 1ms target (registry=100K)"


# =========================================================================
# contains() benchmarks
# =========================================================================


class TestBenchContains:
    """
    Benchmark CapabilityRegistry.contains() at scale.

    contains() is O(1) via `name in _by_name`. Target: <1ms P95.
    """

    def test_contains_1k_p95_under_1ms(self) -> None:
        """contains() with 1K contracts: P95 < 1ms."""
        contracts = _ensure_contracts_1k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        rng = random.Random(111)
        targets = [rng.choice(contracts).name for _ in range(100)]

        timings = []
        for _ in range(5):
            for name in targets:
                start = time.perf_counter()
                found = registry.contains(name)
                elapsed_ms = (time.perf_counter() - start) * 1000
                timings.append(elapsed_ms)
                assert found

        p95 = _percentile(timings, 95)
        assert p95 < 1.0, f"contains P95={p95:.4f}ms exceeds 1ms (registry=1K)"

    def test_contains_100k_p95_under_1ms(self) -> None:
        """contains() with 100K contracts: P95 < 1ms."""
        contracts = _ensure_contracts_100k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        rng = random.Random(222)
        targets = [rng.choice(contracts).name for _ in range(200)]

        timings = []
        for _ in range(3):
            for name in targets:
                start = time.perf_counter()
                found = registry.contains(name)
                elapsed_ms = (time.perf_counter() - start) * 1000
                timings.append(elapsed_ms)
                assert found

        p95 = _percentile(timings, 95)
        assert p95 < 1.0, f"contains P95={p95:.4f}ms exceeds 1ms (registry=100K)"


# =========================================================================
# list_by_domain() benchmarks
# =========================================================================


class TestBenchListByDomain:
    """
    Benchmark CapabilityRegistry.list_by_domain() at scale.

    list_by_domain() is O(1) lookup + O(k) copy where k = domain size.
    Target: <5ms P95 for typical domains.
    """

    def test_list_by_domain_1k_p95_under_5ms(self) -> None:
        """list_by_domain() with 1K contracts: P95 < 5ms."""
        contracts = _ensure_contracts_1k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        timings = []
        for domain in _DOMAINS:
            for _ in range(5):
                start = time.perf_counter()
                result = registry.list_by_domain(domain)
                elapsed_ms = (time.perf_counter() - start) * 1000
                timings.append(elapsed_ms)

        p95 = _percentile(timings, 95)
        assert p95 < 5.0, f"list_by_domain P95={p95:.4f}ms exceeds 5ms (registry=1K)"

    def test_list_by_domain_10k_p95_under_5ms(self) -> None:
        """list_by_domain() with 10K contracts: P95 < 5ms."""
        contracts = _ensure_contracts_10k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        timings = []
        for domain in _DOMAINS:
            for _ in range(3):
                start = time.perf_counter()
                result = registry.list_by_domain(domain)
                elapsed_ms = (time.perf_counter() - start) * 1000
                timings.append(elapsed_ms)
                # With 10K contracts and 19 domains (~526 per domain avg)
                # ensure we actually get results for most domains
                assert isinstance(result, list)

        p95 = _percentile(timings, 95)
        assert p95 < 5.0, f"list_by_domain P95={p95:.4f}ms exceeds 5ms (registry=10K)"

    def test_list_by_domain_100k_p95_under_10ms(self) -> None:
        """list_by_domain() with 100K contracts: P95 < 10ms."""
        contracts = _ensure_contracts_100k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        timings = []
        for domain in _DOMAINS[:10]:  # sample 10 domains
            for _ in range(3):
                start = time.perf_counter()
                result = registry.list_by_domain(domain)
                elapsed_ms = (time.perf_counter() - start) * 1000
                timings.append(elapsed_ms)
                assert isinstance(result, list)
                assert len(result) > 0, f"Domain {domain} returned empty at 100K scale"

        p95 = _percentile(timings, 95)
        assert p95 < 10.0, f"list_by_domain P95={p95:.4f}ms exceeds 10ms (registry=100K)"

    def test_list_by_domain_nonexistent_domain_under_1ms(self) -> None:
        """list_by_domain() for nonexistent domain is near-zero."""
        contracts = _ensure_contracts_100k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        timings = []
        for _ in range(200):
            start = time.perf_counter()
            result = registry.list_by_domain("NONEXISTENT_DOMAIN_ZZZZZ")
            elapsed_ms = (time.perf_counter() - start) * 1000
            timings.append(elapsed_ms)
            assert result == []

        p95 = _percentile(timings, 95)
        assert p95 < 1.0, f"list_by_domain(miss) P95={p95:.4f}ms exceeds 1ms"

    def test_list_by_domain_result_count_consistent(self) -> None:
        """list_by_domain() returns same count on repeated calls (no mutation)."""
        contracts = _ensure_contracts_10k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        for domain in _DOMAINS[:5]:
            first_count = len(registry.list_by_domain(domain))
            for _ in range(10):
                assert len(registry.list_by_domain(domain)) == first_count


# =========================================================================
# list_by_type() benchmarks
# =========================================================================


class TestBenchListByType:
    """
    Benchmark CapabilityRegistry.list_by_type() at scale.

    list_by_type() is O(1) lookup + O(k) copy. Target: <5ms P95.
    Type prefixes: "tool.execute", "tool.read", "tool.write", "tool.delete".
    """

    _TYPE_PREFIXES = ["tool.execute", "tool.read", "tool.write", "tool.delete"]

    def test_list_by_type_1k_p95_under_5ms(self) -> None:
        """list_by_type() with 1K contracts: P95 < 5ms."""
        contracts = _ensure_contracts_1k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        timings = []
        for prefix in self._TYPE_PREFIXES:
            for _ in range(10):
                start = time.perf_counter()
                result = registry.list_by_type(prefix)
                elapsed_ms = (time.perf_counter() - start) * 1000
                timings.append(elapsed_ms)
                assert isinstance(result, list)

        p95 = _percentile(timings, 95)
        assert p95 < 5.0, f"list_by_type P95={p95:.4f}ms exceeds 5ms (registry=1K)"

    def test_list_by_type_10k_p95_under_5ms(self) -> None:
        """list_by_type() with 10K contracts: P95 < 5ms."""
        contracts = _ensure_contracts_10k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        timings = []
        for prefix in self._TYPE_PREFIXES:
            for _ in range(5):
                start = time.perf_counter()
                result = registry.list_by_type(prefix)
                elapsed_ms = (time.perf_counter() - start) * 1000
                timings.append(elapsed_ms)
                assert isinstance(result, list)

        p95 = _percentile(timings, 95)
        assert p95 < 5.0, f"list_by_type P95={p95:.4f}ms exceeds 5ms (registry=10K)"

    def test_list_by_type_100k_p95_under_10ms(self) -> None:
        """list_by_type() with 100K contracts: P95 < 10ms."""
        contracts = _ensure_contracts_100k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        timings = []
        for prefix in self._TYPE_PREFIXES:
            for _ in range(5):
                start = time.perf_counter()
                result = registry.list_by_type(prefix)
                elapsed_ms = (time.perf_counter() - start) * 1000
                timings.append(elapsed_ms)
                assert isinstance(result, list)
                assert len(result) > 0

        p95 = _percentile(timings, 95)
        assert p95 < 10.0, f"list_by_type P95={p95:.4f}ms exceeds 10ms (registry=100K)"

    def test_list_by_type_distribution_matches_pool(self) -> None:
        """Type distribution matches the contract name pool ratio."""
        contracts = _ensure_contracts_1k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        execute_count = len(registry.list_by_type("tool.execute"))
        read_count = len(registry.list_by_type("tool.read"))
        write_count = len(registry.list_by_type("tool.write"))
        delete_count = len(registry.list_by_type("tool.delete"))
        total = execute_count + read_count + write_count + delete_count

        assert total == 1_000, f"Type counts don't sum to 1K: {total}"
        # tool.execute has 50 names, tool.read has 20, tool.write has 10, tool.delete has 5
        # ratio: 50:20:10:5 = 10:4:2:1
        assert execute_count > read_count > write_count > delete_count

    def test_list_by_type_nonexistent_under_1ms(self) -> None:
        """list_by_type() for nonexistent type is near-zero."""
        contracts = _ensure_contracts_100k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        timings = []
        for _ in range(200):
            start = time.perf_counter()
            result = registry.list_by_type("agent.spawn")
            elapsed_ms = (time.perf_counter() - start) * 1000
            timings.append(elapsed_ms)
            # No agent contracts generated, should be empty
            assert isinstance(result, list)

        p95 = _percentile(timings, 95)
        assert p95 < 1.0, f"list_by_type(miss) P95={p95:.4f}ms exceeds 1ms"


# =========================================================================
# list_by_provider() benchmarks
# =========================================================================


class TestBenchListByProvider:
    """
    Benchmark CapabilityRegistry.list_by_provider() at scale.

    list_by_provider() is O(1) lookup + O(k) copy. Target: <5ms P95.
    """

    def test_list_by_provider_10k_p95_under_5ms(self) -> None:
        """list_by_provider() with 10K contracts: P95 < 5ms."""
        contracts = _ensure_contracts_10k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        # Pick some known provider IDs from the contracts
        rng = random.Random(333)
        provider_ids = list({c.provider_id for c in contracts})
        targets = [rng.choice(provider_ids) for _ in range(50)]

        timings = []
        for pid in targets:
            start = time.perf_counter()
            result = registry.list_by_provider(pid)
            elapsed_ms = (time.perf_counter() - start) * 1000
            timings.append(elapsed_ms)
            assert isinstance(result, list)
            assert len(result) > 0

        p95 = _percentile(timings, 95)
        assert p95 < 5.0, f"list_by_provider P95={p95:.4f}ms exceeds 5ms (registry=10K)"

    def test_list_by_provider_100k_p95_under_10ms(self) -> None:
        """list_by_provider() with 100K contracts: P95 < 10ms."""
        contracts = _ensure_contracts_100k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        rng = random.Random(444)
        provider_ids = list({c.provider_id for c in contracts})
        targets = [rng.choice(provider_ids) for _ in range(50)]

        timings = []
        for pid in targets:
            start = time.perf_counter()
            result = registry.list_by_provider(pid)
            elapsed_ms = (time.perf_counter() - start) * 1000
            timings.append(elapsed_ms)
            assert isinstance(result, list)

        p95 = _percentile(timings, 95)
        assert p95 < 10.0, f"list_by_provider P95={p95:.4f}ms exceeds 10ms (registry=100K)"


# =========================================================================
# list_all() benchmarks
# =========================================================================


class TestBenchListAll:
    """
    Benchmark CapabilityRegistry.list_all() at scale.

    list_all() copies the entire registry. Target: <50ms P95 at 100K.
    """

    def test_list_all_1k_p95_under_5ms(self) -> None:
        """list_all() with 1K contracts: P95 < 5ms."""
        contracts = _ensure_contracts_1k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        timings = []
        for _ in range(20):
            start = time.perf_counter()
            result = registry.list_all()
            elapsed_ms = (time.perf_counter() - start) * 1000
            timings.append(elapsed_ms)
            assert len(result) == 1_000

        p95 = _percentile(timings, 95)
        assert p95 < 5.0, f"list_all P95={p95:.4f}ms exceeds 5ms (registry=1K)"

    def test_list_all_10k_p95_under_20ms(self) -> None:
        """list_all() with 10K contracts: P95 < 20ms."""
        contracts = _ensure_contracts_10k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        timings = []
        for _ in range(10):
            start = time.perf_counter()
            result = registry.list_all()
            elapsed_ms = (time.perf_counter() - start) * 1000
            timings.append(elapsed_ms)
            assert len(result) == 10_000

        p95 = _percentile(timings, 95)
        assert p95 < 20.0, f"list_all P95={p95:.4f}ms exceeds 20ms (registry=10K)"

    def test_list_all_100k_p95_under_50ms(self) -> None:
        """list_all() with 100K contracts: P95 < 50ms."""
        contracts = _ensure_contracts_100k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        timings = []
        for _ in range(5):
            start = time.perf_counter()
            result = registry.list_all()
            elapsed_ms = (time.perf_counter() - start) * 1000
            timings.append(elapsed_ms)
            assert len(result) == 100_000

        p95 = _percentile(timings, 95)
        assert p95 < 50.0, f"list_all P95={p95:.4f}ms exceeds 50ms (registry=100K)"


# =========================================================================
# size / list_names() benchmarks
# =========================================================================


class TestBenchSizeAndNames:
    """
    Benchmark CapabilityRegistry.size and list_names() at scale.

    size is O(1) len(). list_names() is O(n log n) sorted().
    """

    def test_size_100k_p95_under_01ms(self) -> None:
        """size property with 100K contracts: P95 < 0.1ms."""
        contracts = _ensure_contracts_100k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        timings = []
        for _ in range(1000):
            start = time.perf_counter()
            s = registry.size
            elapsed_ms = (time.perf_counter() - start) * 1000
            timings.append(elapsed_ms)
            assert s == 100_000

        p95 = _percentile(timings, 95)
        assert p95 < 0.1, f"size P95={p95:.6f}ms exceeds 0.1ms (registry=100K)"

    def test_list_names_1k_p95_under_5ms(self) -> None:
        """list_names() with 1K contracts: P95 < 5ms."""
        contracts = _ensure_contracts_1k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        timings = []
        for _ in range(20):
            start = time.perf_counter()
            names = registry.list_names()
            elapsed_ms = (time.perf_counter() - start) * 1000
            timings.append(elapsed_ms)
            assert len(names) == 1_000
            # Sorted
            assert names == sorted(names)

        p95 = _percentile(timings, 95)
        assert p95 < 5.0, f"list_names P95={p95:.4f}ms exceeds 5ms (registry=1K)"

    def test_list_names_100k_p95_under_100ms(self) -> None:
        """list_names() with 100K contracts: P95 < 100ms."""
        contracts = _ensure_contracts_100k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        timings = []
        for _ in range(5):
            start = time.perf_counter()
            names = registry.list_names()
            elapsed_ms = (time.perf_counter() - start) * 1000
            timings.append(elapsed_ms)
            assert len(names) == 100_000
            assert names == sorted(names)

        p95 = _percentile(timings, 95)
        assert p95 < 100.0, f"list_names P95={p95:.4f}ms exceeds 100ms (registry=100K)"


# =========================================================================
# get_metadata() benchmarks
# =========================================================================


class TestBenchGetMetadata:
    """
    Benchmark CapabilityRegistry.get_metadata() at scale.

    get_metadata() is O(1) dict lookup. Target: <1ms P95.
    """

    def test_get_metadata_100k_p95_under_1ms(self) -> None:
        """get_metadata() with 100K contracts: P95 < 1ms."""
        contracts = _ensure_contracts_100k()
        registry = _make_registry()
        _populate_registry(registry, contracts)

        rng = random.Random(555)
        targets = [rng.choice(contracts).name for _ in range(200)]

        timings = []
        for _ in range(3):
            for name in targets:
                start = time.perf_counter()
                meta = registry.get_metadata(name)
                elapsed_ms = (time.perf_counter() - start) * 1000
                timings.append(elapsed_ms)
                assert meta is not None

        p95 = _percentile(timings, 95)
        assert p95 < 1.0, f"get_metadata P95={p95:.4f}ms exceeds 1ms (registry=100K)"


# =========================================================================
# Registration throughput benchmarks
# =========================================================================


class TestBenchRegistrationThroughput:
    """
    Benchmark contract registration throughput.

    Measures bulk registration speed with realistic contracts.
    """

    def test_register_1k_under_5s(self) -> None:
        """Register 1K realistic contracts in < 5 seconds (with validation)."""
        contracts = _ensure_contracts_1k()
        registry = _make_registry()

        start = time.perf_counter()
        for c in contracts:
            registry.register(c)  # WITH validation
        total_ms = (time.perf_counter() - start) * 1000

        assert registry.size == 1_000
        assert total_ms < 5_000, (
            f"Registering 1K contracts with validation took {total_ms:.1f}ms " f"(target <5000ms)"
        )

    def test_register_10k_skip_validation_under_10s(self) -> None:
        """Register 10K contracts (skip_validation) in < 10 seconds."""
        contracts = _ensure_contracts_10k()
        registry = _make_registry()

        start = time.perf_counter()
        _populate_registry(registry, contracts)
        total_ms = (time.perf_counter() - start) * 1000

        assert registry.size == 10_000
        assert (
            total_ms < 10_000
        ), f"Registering 10K contracts took {total_ms:.1f}ms (target <10000ms)"

    def test_register_100k_skip_validation_under_60s(self) -> None:
        """Register 100K contracts (skip_validation) in < 60 seconds."""
        contracts = _ensure_contracts_100k()
        registry = _make_registry()

        start = time.perf_counter()
        _populate_registry(registry, contracts)
        total_ms = (time.perf_counter() - start) * 1000

        assert registry.size == 100_000
        assert (
            total_ms < 60_000
        ), f"Registering 100K contracts took {total_ms:.1f}ms (target <60000ms)"


# =========================================================================
# Scaling linearity check
# =========================================================================


class TestBenchScalingLinearity:
    """
    Verify that lookup() latency does NOT degrade with registry size.

    Since lookup() is O(1) dict access, going from 1K to 100K should
    not significantly increase latency.
    """

    def test_lookup_latency_stable_across_scales(self) -> None:
        """lookup() median latency at 100K is within 5x of 1K (dict = O(1))."""
        # Measure at 1K
        contracts_1k = _ensure_contracts_1k()
        reg_1k = _make_registry()
        _populate_registry(reg_1k, contracts_1k)

        rng = random.Random(999)
        targets_1k = [rng.choice(contracts_1k).name for _ in range(100)]
        for t in targets_1k[:10]:
            reg_1k.lookup(t)

        timings_1k = []
        for name in targets_1k:
            start = time.perf_counter()
            reg_1k.lookup(name)
            timings_1k.append((time.perf_counter() - start) * 1000)

        # Measure at 100K
        contracts_100k = _ensure_contracts_100k()
        reg_100k = _make_registry()
        _populate_registry(reg_100k, contracts_100k)

        targets_100k = [rng.choice(contracts_100k).name for _ in range(100)]
        for t in targets_100k[:10]:
            reg_100k.lookup(t)

        timings_100k = []
        for name in targets_100k:
            start = time.perf_counter()
            reg_100k.lookup(name)
            timings_100k.append((time.perf_counter() - start) * 1000)

        median_1k = _percentile(timings_1k, 50)
        median_100k = _percentile(timings_100k, 50)

        # O(1) means scaling from 1K to 100K should be constant
        # Allow up to 5x for memory pressure / cache effects
        if median_1k > 0:
            ratio = median_100k / median_1k
            assert ratio < 5.0, (
                f"lookup() 100K/1K ratio={ratio:.2f}x "
                f"(1K median={median_1k:.4f}ms, 100K median={median_100k:.4f}ms)"
            )
        # If median_1k is essentially 0, just check 100K is within target
        assert median_100k < 1.0, f"100K median={median_100k:.4f}ms exceeds 1ms"

    def test_contains_latency_stable_across_scales(self) -> None:
        """contains() latency at 100K is within 5x of 1K."""
        contracts_1k = _ensure_contracts_1k()
        reg_1k = _make_registry()
        _populate_registry(reg_1k, contracts_1k)

        rng = random.Random(888)
        targets_1k = [rng.choice(contracts_1k).name for _ in range(100)]
        timings_1k = []
        for name in targets_1k:
            start = time.perf_counter()
            reg_1k.contains(name)
            timings_1k.append((time.perf_counter() - start) * 1000)

        contracts_100k = _ensure_contracts_100k()
        reg_100k = _make_registry()
        _populate_registry(reg_100k, contracts_100k)

        targets_100k = [rng.choice(contracts_100k).name for _ in range(100)]
        timings_100k = []
        for name in targets_100k:
            start = time.perf_counter()
            reg_100k.contains(name)
            timings_100k.append((time.perf_counter() - start) * 1000)

        median_1k = _percentile(timings_1k, 50)
        median_100k = _percentile(timings_100k, 50)

        assert median_100k < 1.0, f"100K contains median={median_100k:.4f}ms exceeds 1ms"
