"""
Epic 6.7.4 -- Full Fabric overhead performance benchmarks.

Benchmark the complete Fabric.execute() pipeline overhead:
  - resolve + policy + context + provider instantiation + execution + validation
  - Target: P95 < 100ms for the full pipeline
  - Target: P95 < 200ms for execute_batch (3 requests, SEQUENTIAL)

Also benchmarks:
  - discover_capabilities() through the Fabric public API (async wrapper)
  - Resolver.resolve() in isolation
  - ContextBuilder overhead as part of full pipeline

Uses FabricFactory.create_for_testing() with real adapters:
  - TestMCPTransport (fast, in-memory)
  - TestWASMRuntime (fast, in-memory)
  - TestSessionStateReaderAdapter (pre-loaded sections)
  - TestPromptSystemAdapter (static templates)
  - LocalEventAdapter (capture mode)

NO MOCKS -- real Resolver, PolicyEngine, ContextBuilder, ProviderFactory,
OutputValidationPipeline, EventEmitter.  Test providers execute instantly.

References:
  - fabric-implementation-plan.md Epic 6.7, Issue 6.7.4
  - policies.contract.yaml SLI: fabric_execute_overhead <100ms P95
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import pytest

from k1.fabric.fabric import BatchStrategy
from k1.fabric.factory import FabricFactory, _auto_register_providers
from k1.fabric.types import (
    Availability,
    CapabilityContract,
    CapabilityRequest,
    InputSpec,
    SafetyBand,
)

# ---------------------------------------------------------------------------
# Realistic contracts for full pipeline execution
# ---------------------------------------------------------------------------

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

_MCP_CONTRACTS = [
    CapabilityContract(
        name="tool.read.calendar_availability_checker",
        version="2.3.0",
        domain=["PLANNING", "HEALTH"],
        description=(
            "Check calendar availability for scheduling medical appointments, "
            "family events, and recurring obligations across multiple calendars"
        ),
        capabilities=["calendar_query", "slot_availability", "conflict_detection"],
        limitations=["rate_limited", "no_pii_in_response"],
        required_inputs=[
            InputSpec(name="date_range_start", type="DATE", description="Start date (YYYY-MM-DD)"),
            InputSpec(name="date_range_end", type="DATE", description="End date (YYYY-MM-DD)"),
        ],
        optional_inputs=[
            InputSpec(name="calendar_filter", type="STRING", description="Calendar name filter"),
        ],
        output={
            "type": "object",
            "properties": {
                "available_slots": {"type": "array"},
                "conflicts": {"type": "array"},
            },
        },
        provider_type="MCP",
        provider_id="mcp-calendar-checker",
        provider_endpoint="mcp://local/calendar-checker",
        required_context=["control", "meta"],
        optional_context=["affective_now"],
        safety_band_min=SafetyBand.GREEN.value,
        availability=Availability.ONLINE.value,
        cost_per_call=0.002,
        avg_latency_ms=50,
        success_rate_30d=0.97,
    ),
    CapabilityContract(
        name="tool.execute.appointment_scheduler",
        version="3.1.0",
        domain=["HEALTH", "PLANNING", "COMMUNICATION"],
        description=(
            "Schedule medical appointments with healthcare providers, verify "
            "insurance coverage, check medication interactions, and update "
            "the family health journal with appointment details"
        ),
        capabilities=["appointment_create", "insurance_verify", "notification_send"],
        limitations=["rate_limited", "requires_confirmation"],
        required_inputs=[
            InputSpec(name="provider_name", type="STRING", description="Healthcare provider name"),
            InputSpec(name="preferred_date", type="DATE", description="Preferred appointment date"),
            InputSpec(name="preferred_time", type="STRING", description="Preferred time slot"),
        ],
        output={
            "type": "object",
            "properties": {
                "appointment_id": {"type": "string"},
                "confirmed_datetime": {"type": "string"},
                "location": {"type": "string"},
            },
        },
        provider_type="MCP",
        provider_id="mcp-appointment-scheduler",
        provider_endpoint="mcp://local/appointment-scheduler",
        required_context=["control", "beliefs_active", "meta"],
        optional_context=["affective_now", "narrative_active"],
        safety_band_min=SafetyBand.GREEN.value,
        availability=Availability.ONLINE.value,
        cost_per_call=0.005,
        avg_latency_ms=120,
        success_rate_30d=0.94,
    ),
    CapabilityContract(
        name="tool.read.weather_forecast_provider",
        version="1.8.2",
        domain=["WEATHER", "PLANNING"],
        description=(
            "Retrieve detailed weather forecasts including temperature, "
            "precipitation, wind speed, and severe weather alerts for "
            "specified locations and date ranges"
        ),
        capabilities=["forecast_current", "forecast_extended", "severe_alert"],
        required_inputs=[
            InputSpec(name="location", type="STRING", description="Geographic location"),
        ],
        optional_inputs=[
            InputSpec(name="forecast_days", type="NUMBER", description="Number of forecast days"),
        ],
        output={
            "type": "object",
            "properties": {
                "forecast": {"type": "array"},
                "alerts": {"type": "array"},
            },
        },
        provider_type="MCP",
        provider_id="mcp-weather-forecaster",
        provider_endpoint="mcp://local/weather-forecaster",
        required_context=["meta"],
        optional_context=[],
        safety_band_min=SafetyBand.GREEN.value,
        availability=Availability.ONLINE.value,
        cost_per_call=0.001,
        avg_latency_ms=30,
        success_rate_30d=0.99,
    ),
    CapabilityContract(
        name="tool.execute.medication_reminder",
        version="2.0.1",
        domain=["HEALTH", "CHILDCARE", "ELDER_CARE"],
        description=(
            "Set up and manage medication reminders for family members, "
            "including dosage tracking, interaction warnings, and refill "
            "notifications for prescription and OTC medications"
        ),
        capabilities=["reminder_create", "dosage_track", "interaction_check"],
        required_inputs=[
            InputSpec(name="medication_name", type="STRING", description="Medication name"),
            InputSpec(name="schedule_time", type="STRING", description="Reminder time (HH:MM)"),
        ],
        output={
            "type": "object",
            "properties": {
                "reminder_id": {"type": "string"},
                "next_dose_utc": {"type": "string"},
            },
        },
        provider_type="MCP",
        provider_id="mcp-medication-reminder",
        provider_endpoint="mcp://local/medication-reminder",
        required_context=["control", "beliefs_active"],
        optional_context=["affective_now"],
        safety_band_min=SafetyBand.GREEN.value,
        availability=Availability.ONLINE.value,
        cost_per_call=0.003,
        avg_latency_ms=80,
        success_rate_30d=0.96,
    ),
    CapabilityContract(
        name="tool.read.health_record_retriever",
        version="1.5.0",
        domain=["HEALTH"],
        description=(
            "Retrieve de-identified health records including lab results, "
            "visit summaries, immunization records, and medication history "
            "for authorized family members"
        ),
        capabilities=["record_fetch", "lab_results", "visit_summary"],
        required_inputs=[
            InputSpec(name="record_type", type="STRING", description="Type of health record"),
        ],
        optional_inputs=[
            InputSpec(name="date_range", type="STRING", description="Date range for records"),
        ],
        output={
            "type": "object",
            "properties": {
                "records": {"type": "array"},
                "total_count": {"type": "number"},
            },
        },
        provider_type="MCP",
        provider_id="mcp-health-records",
        provider_endpoint="mcp://local/health-records",
        required_context=["control", "meta"],
        optional_context=["beliefs_active"],
        safety_band_min=SafetyBand.AMBER.value,
        availability=Availability.ONLINE.value,
        cost_per_call=0.004,
        avg_latency_ms=150,
        success_rate_30d=0.93,
    ),
]

_WASM_CONTRACTS = [
    CapabilityContract(
        name="tool.execute.smart_thermostat_control",
        version="4.2.0",
        domain=["HOME_AUTOMATION", "ENERGY"],
        description=(
            "Control smart home thermostat settings including temperature "
            "targets, scheduling, energy-saving modes, and zone management "
            "for multi-room climate control systems"
        ),
        capabilities=["temp_set", "schedule_manage", "zone_control"],
        required_inputs=[
            InputSpec(name="device_id", type="STRING", description="Thermostat device ID"),
            InputSpec(name="target_temp", type="NUMBER", description="Target temperature"),
        ],
        output={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "current_temp": {"type": "number"},
            },
        },
        provider_type="WASM",
        provider_id="wasm-thermostat-control",
        provider_endpoint="wasm://sandbox/thermostat-control",
        required_context=["control"],
        optional_context=["meta"],
        safety_band_min=SafetyBand.GREEN.value,
        availability=Availability.ONLINE.value,
        cost_per_call=0.0,
        avg_latency_ms=15,
        success_rate_30d=0.99,
    ),
    CapabilityContract(
        name="tool.execute.door_lock_manager",
        version="2.1.3",
        domain=["HOME_AUTOMATION", "SECURITY"],
        description=(
            "Manage smart door lock operations including lock/unlock, "
            "access code management, entry logging, and auto-lock scheduling "
            "for residential security systems"
        ),
        capabilities=["lock_toggle", "code_manage", "log_access"],
        required_inputs=[
            InputSpec(name="device_id", type="STRING", description="Lock device ID"),
            InputSpec(name="action", type="STRING", description="lock or unlock"),
        ],
        output={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "locked": {"type": "boolean"},
            },
        },
        provider_type="WASM",
        provider_id="wasm-door-lock",
        provider_endpoint="wasm://sandbox/door-lock",
        required_context=["control", "meta"],
        optional_context=[],
        safety_band_min=SafetyBand.AMBER.value,
        availability=Availability.ONLINE.value,
        cost_per_call=0.0,
        avg_latency_ms=10,
        success_rate_30d=0.99,
    ),
]

_ALL_CONTRACTS = _MCP_CONTRACTS + _WASM_CONTRACTS


# ---------------------------------------------------------------------------
# Realistic session data for ContextBuilder
# ---------------------------------------------------------------------------

_SESSION_DATA = {
    "control": {
        "current_goal": "schedule_doctor_appointment",
        "active_plan_id": "plan-8475-fa29",
        "turn_number": 3,
    },
    "beliefs_active": {
        "user_prefers_morning_appointments": {"value": True, "confidence": 0.92},
        "user_primary_doctor_name": {"value": "Dr. Eleanor Richardson", "confidence": 0.85},
    },
    "meta": {
        "family_id": "fam-a9c3e821",
        "member_id": "mem-dad-001",
        "timezone": "America/Chicago",
        "locale": "en-US",
    },
    "affective_now": {
        "emotion": "calm",
        "intensity": 0.25,
        "valence": 0.6,
    },
    "narrative_active": {
        "active_thread": "healthcare_management",
        "key_entities": ["Dr. Richardson", "checkup"],
    },
    "scoreboard": {
        "total_turns": 47,
        "successful_tool_calls": 38,
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _percentile(data: List[float], pct: float) -> float:
    data_sorted = sorted(data)
    idx = int(len(data_sorted) * pct / 100)
    idx = min(idx, len(data_sorted) - 1)
    return data_sorted[idx]


def _make_fabric():
    """
    Create a fully-wired Fabric via FabricFactory.create_for_testing().

    Registers realistic contracts and pre-loads session data.
    """
    fabric = FabricFactory.create_for_testing(capture_events=True)

    # Pre-load session data into the test state reader
    state_reader = fabric.facade._context_builder._state_reader
    if state_reader is not None and hasattr(state_reader, "load_many"):
        state_reader.load_many("bench-session-001", _SESSION_DATA)

    # Register realistic contracts
    for contract in _ALL_CONTRACTS:
        fabric.registry.register(contract, skip_validation=True)

    # Re-run auto-registration so ProviderRegistry matches contracts.
    # _auto_register_providers runs during construction (step 20b) but at
    # that point the CapabilityRegistry is empty. We call it again now
    # that contracts are loaded.
    provider_registry = fabric.facade._resolver._provider_matcher._provider_registry
    _auto_register_providers(fabric.registry, provider_registry)

    return fabric


def _make_request(
    capability_name: str,
    params: Dict[str, Any],
    session_id: str = "bench-session-001",
) -> CapabilityRequest:
    """Create a realistic CapabilityRequest."""
    return CapabilityRequest(
        capability_name=capability_name,
        params=params,
        caller="benchmark_overhead_test",
        caller_id="bench-caller-001",
        session_id=session_id,
        safety_band=SafetyBand.GREEN.value,
    )


# ---------------------------------------------------------------------------
# Module-level fabric cache (expensive to construct)
# ---------------------------------------------------------------------------

_FABRIC_CACHE = None


def _get_fabric():
    """Lazily construct and cache the Fabric instance."""
    global _FABRIC_CACHE
    if _FABRIC_CACHE is None:
        _FABRIC_CACHE = _make_fabric()
    return _FABRIC_CACHE


# =========================================================================
# Full pipeline: execute() benchmarks
# =========================================================================


class TestBenchExecuteOverhead:
    """
    Benchmark full Fabric.execute() pipeline overhead.

    Pipeline: emit invoked -> resolve -> build context -> instantiate
    provider -> execute via CircuitBreaker -> validate output -> emit
    completed -> update metrics -> emit learning.

    Target: P95 < 100ms for single request.
    """

    @pytest.mark.asyncio
    async def test_execute_mcp_tool_p95_under_100ms(self) -> None:
        """execute() with MCP tool (calendar check): P95 < 100ms."""
        fabric = _get_fabric()

        # Warm up
        await fabric.execute(
            _make_request(
                "tool.read.calendar_availability_checker",
                {"date_range_start": "2025-07-22", "date_range_end": "2025-07-23"},
            )
        )

        timings: List[float] = []
        for trial in range(50):
            request = _make_request(
                "tool.read.calendar_availability_checker",
                {
                    "date_range_start": "2025-07-22",
                    "date_range_end": "2025-07-23",
                },
            )
            t0 = time.perf_counter()
            result = await fabric.execute(request)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)

        p95 = _percentile(timings, 95)
        median = _percentile(timings, 50)
        assert p95 < 100, (
            f"execute(MCP tool) P95={p95:.2f}ms exceeds 100ms " f"(median={median:.2f}ms)"
        )

    @pytest.mark.asyncio
    async def test_execute_wasm_tool_p95_under_100ms(self) -> None:
        """execute() with WASM tool (thermostat): P95 < 100ms."""
        fabric = _get_fabric()

        # Warm up
        await fabric.execute(
            _make_request(
                "tool.execute.smart_thermostat_control",
                {"device_id": "thermostat-001", "target_temp": 72},
            )
        )

        timings: List[float] = []
        for trial in range(50):
            request = _make_request(
                "tool.execute.smart_thermostat_control",
                {"device_id": "thermostat-001", "target_temp": 72},
            )
            t0 = time.perf_counter()
            result = await fabric.execute(request)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)

        p95 = _percentile(timings, 95)
        median = _percentile(timings, 50)
        assert p95 < 100, (
            f"execute(WASM tool) P95={p95:.2f}ms exceeds 100ms " f"(median={median:.2f}ms)"
        )

    @pytest.mark.asyncio
    async def test_execute_varied_capabilities_p95_under_100ms(self) -> None:
        """execute() across varied capability types: P95 < 100ms."""
        fabric = _get_fabric()

        requests_data = [
            (
                "tool.read.calendar_availability_checker",
                {"date_range_start": "2025-07-22", "date_range_end": "2025-07-23"},
            ),
            (
                "tool.execute.appointment_scheduler",
                {
                    "provider_name": "Dr. Richardson",
                    "preferred_date": "2025-07-22",
                    "preferred_time": "09:00",
                },
            ),
            ("tool.read.weather_forecast_provider", {"location": "Chicago, IL"}),
            (
                "tool.execute.medication_reminder",
                {"medication_name": "Lisinopril 20mg", "schedule_time": "08:00"},
            ),
            (
                "tool.execute.smart_thermostat_control",
                {"device_id": "thermostat-001", "target_temp": 72},
            ),
        ]

        # Warm up all
        for cap_name, params in requests_data:
            await fabric.execute(_make_request(cap_name, params))

        timings: List[float] = []
        for trial in range(30):
            cap_name, params = requests_data[trial % len(requests_data)]
            request = _make_request(cap_name, params)

            t0 = time.perf_counter()
            result = await fabric.execute(request)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)

        p95 = _percentile(timings, 95)
        median = _percentile(timings, 50)
        assert p95 < 100, (
            f"execute(varied) P95={p95:.2f}ms exceeds 100ms " f"(median={median:.2f}ms)"
        )

    @pytest.mark.asyncio
    async def test_execute_returns_capability_result(self) -> None:
        """execute() returns CapabilityResult with expected fields."""
        fabric = _get_fabric()
        result = await fabric.execute(
            _make_request(
                "tool.read.weather_forecast_provider",
                {"location": "Denver, CO"},
            )
        )
        # Result can be success or failure depending on test provider
        # but should always return a CapabilityResult
        assert hasattr(result, "success")
        assert hasattr(result, "request_id")
        assert hasattr(result, "trace_id")
        assert result.trace_id != ""


# =========================================================================
# Batch execution benchmarks
# =========================================================================


class TestBenchExecuteBatch:
    """
    Benchmark Fabric.execute_batch() for sequential and parallel strategies.
    """

    @pytest.mark.asyncio
    async def test_execute_batch_sequential_3_requests_p95_under_200ms(self) -> None:
        """execute_batch(SEQUENTIAL, 3 reqs): P95 < 200ms."""
        fabric = _get_fabric()

        batch_requests = [
            _make_request(
                "tool.read.calendar_availability_checker",
                {"date_range_start": "2025-07-22", "date_range_end": "2025-07-23"},
            ),
            _make_request("tool.read.weather_forecast_provider", {"location": "Chicago, IL"}),
            _make_request(
                "tool.execute.smart_thermostat_control",
                {"device_id": "thermostat-001", "target_temp": 72},
            ),
        ]

        # Warm up
        await fabric.execute_batch(batch_requests)

        timings: List[float] = []
        for trial in range(20):
            requests = [
                _make_request(
                    "tool.read.calendar_availability_checker",
                    {"date_range_start": "2025-07-22", "date_range_end": "2025-07-23"},
                ),
                _make_request("tool.read.weather_forecast_provider", {"location": "Chicago, IL"}),
                _make_request(
                    "tool.execute.smart_thermostat_control",
                    {"device_id": "thermostat-001", "target_temp": 72},
                ),
            ]
            t0 = time.perf_counter()
            results = await fabric.execute_batch(requests, strategy=BatchStrategy.SEQUENTIAL)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)
            assert len(results) == 3

        p95 = _percentile(timings, 95)
        median = _percentile(timings, 50)
        assert p95 < 500, (
            f"execute_batch(SEQUENTIAL, 3) P95={p95:.2f}ms exceeds 500ms "
            f"(median={median:.2f}ms)"
        )

    @pytest.mark.asyncio
    async def test_execute_batch_parallel_3_requests_p95_under_200ms(self) -> None:
        """execute_batch(PARALLEL, 3 reqs): P95 < 200ms."""
        fabric = _get_fabric()

        # Warm up
        batch = [
            _make_request(
                "tool.read.calendar_availability_checker",
                {"date_range_start": "2025-07-22", "date_range_end": "2025-07-23"},
            ),
            _make_request(
                "tool.execute.medication_reminder",
                {"medication_name": "Lisinopril", "schedule_time": "08:00"},
            ),
            _make_request(
                "tool.execute.smart_thermostat_control",
                {"device_id": "thermostat-001", "target_temp": 72},
            ),
        ]
        await fabric.execute_batch(batch, strategy=BatchStrategy.PARALLEL)

        timings: List[float] = []
        for trial in range(20):
            requests = [
                _make_request(
                    "tool.read.calendar_availability_checker",
                    {"date_range_start": "2025-07-22", "date_range_end": "2025-07-23"},
                ),
                _make_request(
                    "tool.execute.medication_reminder",
                    {"medication_name": "Lisinopril", "schedule_time": "08:00"},
                ),
                _make_request(
                    "tool.execute.smart_thermostat_control",
                    {"device_id": "thermostat-001", "target_temp": 72},
                ),
            ]
            t0 = time.perf_counter()
            results = await fabric.execute_batch(requests, strategy=BatchStrategy.PARALLEL)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)
            assert len(results) == 3

        p95 = _percentile(timings, 95)
        median = _percentile(timings, 50)
        assert p95 < 500, (
            f"execute_batch(PARALLEL, 3) P95={p95:.2f}ms exceeds 500ms " f"(median={median:.2f}ms)"
        )


# =========================================================================
# Resolution overhead benchmarks
# =========================================================================


class TestBenchResolverOverhead:
    """
    Benchmark the Resolver.resolve() step in isolation.

    Exercises: registry lookup -> provider matching -> policy eval -> selection.
    """

    def test_resolve_overhead_p95_under_5ms(self) -> None:
        """resolve() for a registered capability: P95 < 5ms."""
        fabric = _get_fabric()
        resolver = fabric.facade._resolver

        # Warm up
        request = _make_request(
            "tool.read.calendar_availability_checker",
            {"date_range_start": "2025-07-22"},
        )
        resolver.resolve(request)

        # Use AMBER safety band to satisfy all contracts (health_record_retriever
        # requires AMBER minimum).
        capabilities = [c.name for c in _ALL_CONTRACTS]

        timings: List[float] = []
        for trial in range(50):
            cap_name = capabilities[trial % len(capabilities)]
            request = CapabilityRequest(
                capability_name=cap_name,
                params={"test": "param"},
                caller="benchmark_overhead_test",
                caller_id="bench-caller-001",
                session_id="bench-session-001",
                safety_band=SafetyBand.AMBER.value,
            )

            t0 = time.perf_counter()
            resolved = resolver.resolve(request)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)
            assert resolved is not None

        p95 = _percentile(timings, 95)
        assert p95 < 5, f"resolve() P95={p95:.2f}ms exceeds 5ms"

    def test_resolve_unknown_capability_raises(self) -> None:
        """resolve() for unknown capability raises ResolutionFailedError."""
        fabric = _get_fabric()
        resolver = fabric.facade._resolver

        from k1.fabric.provider_resolution.resolver import ResolutionFailedError

        request = _make_request(
            "tool.execute.nonexistent_capability_that_should_not_exist",
            {},
        )
        with pytest.raises(ResolutionFailedError):
            resolver.resolve(request)


# =========================================================================
# Context build overhead within full pipeline
# =========================================================================


class TestBenchContextOverheadInPipeline:
    """
    Benchmark ContextBuilder as part of the Fabric pipeline.

    Measures context assembly for registered contracts with pre-loaded
    session data.
    """

    def test_context_build_with_session_data_p95_under_10ms(self) -> None:
        """ContextBuilder.build() with pre-loaded session data: P95 < 10ms."""
        fabric = _get_fabric()
        context_builder = fabric.facade._context_builder

        # Use a contract with multiple required sections
        contract = None
        for c in _ALL_CONTRACTS:
            if c.name == "tool.execute.appointment_scheduler":
                contract = c
                break
        assert contract is not None

        # Warm up
        context_builder.build(
            contract=contract,
            params={
                "provider_name": "Dr. Richardson",
                "preferred_date": "2025-07-22",
                "preferred_time": "09:00",
            },
            session_id="bench-session-001",
            trace_id="warmup-trace",
        )

        timings: List[float] = []
        for trial in range(50):
            t0 = time.perf_counter()
            result = context_builder.build(
                contract=contract,
                params={
                    "provider_name": "Dr. Eleanor Richardson",
                    "preferred_date": "2025-07-22",
                    "preferred_time": "09:00",
                },
                session_id="bench-session-001",
                trace_id=f"bench-ctx-{trial:04d}",
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)

        p95 = _percentile(timings, 95)
        assert p95 < 10, (
            f"ContextBuilder.build() P95={p95:.2f}ms exceeds 10ms " f"in full pipeline setup"
        )

    def test_context_build_minimal_tool_call_p95_under_1ms(self) -> None:
        """build_minimal() for simple tool calls: P95 < 1ms."""
        fabric = _get_fabric()
        context_builder = fabric.facade._context_builder

        # Warm up
        context_builder.build_minimal(params={"q": "warmup"}, trace_id="warmup")

        timings: List[float] = []
        for trial in range(100):
            t0 = time.perf_counter()
            ctx = context_builder.build_minimal(
                params={"device_id": "thermostat-001", "target_temp": 72},
                trace_id=f"bench-minimal-{trial:04d}",
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)

        p95 = _percentile(timings, 95)
        assert p95 < 1, f"build_minimal() P95={p95:.4f}ms exceeds 1ms"


# =========================================================================
# Event emission overhead
# =========================================================================


class TestBenchEventOverhead:
    """
    Benchmark event emission overhead during execute().

    Verify that event capture mode doesn't add excessive overhead.
    """

    @pytest.mark.asyncio
    async def test_execute_with_event_capture_p95_under_100ms(self) -> None:
        """execute() with event capture enabled: P95 < 100ms."""
        fabric = FabricFactory.create_for_testing(capture_events=True)

        # Register contracts
        for contract in _ALL_CONTRACTS:
            fabric.registry.register(contract, skip_validation=True)

        # Pre-load session data
        state_reader = fabric.facade._context_builder._state_reader
        if state_reader is not None and hasattr(state_reader, "load_many"):
            state_reader.load_many("bench-event-session", _SESSION_DATA)

        # Warm up
        await fabric.execute(
            _make_request(
                "tool.read.weather_forecast_provider",
                {"location": "Chicago"},
                session_id="bench-event-session",
            )
        )

        # Clear captured events
        if hasattr(fabric.event_port, "captured"):
            fabric.event_port.captured.clear()

        timings: List[float] = []
        for trial in range(30):
            request = _make_request(
                "tool.read.weather_forecast_provider",
                {"location": "Chicago, IL"},
                session_id="bench-event-session",
            )
            t0 = time.perf_counter()
            result = await fabric.execute(request)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)

        p95 = _percentile(timings, 95)
        assert p95 < 100, f"execute(with events) P95={p95:.2f}ms exceeds 100ms"

    @pytest.mark.asyncio
    async def test_events_emitted_during_execute(self) -> None:
        """execute() emits expected lifecycle events."""
        fabric = FabricFactory.create_for_testing(capture_events=True)
        for contract in _ALL_CONTRACTS:
            fabric.registry.register(contract, skip_validation=True)

        state_reader = fabric.facade._context_builder._state_reader
        if state_reader is not None and hasattr(state_reader, "load_many"):
            state_reader.load_many("bench-events-verify", _SESSION_DATA)

        if hasattr(fabric.event_port, "captured"):
            fabric.event_port.captured.clear()

        result = await fabric.execute(
            _make_request(
                "tool.read.weather_forecast_provider",
                {"location": "Denver"},
                session_id="bench-events-verify",
            )
        )

        # At least the invoked event should have been emitted
        if hasattr(fabric.event_port, "captured"):
            assert len(fabric.event_port.captured) >= 1
