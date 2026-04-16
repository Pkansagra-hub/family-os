"""
Epic 6.7.3 -- Context-build performance benchmarks.

Benchmark ContextBuilder and ContextBudget operations:
  - build() with small context (2-3 sections): P95 < 10ms
  - build() with large context (6+ sections):  P95 < 50ms
  - build_minimal() (no contract requirements): P95 < 1ms
  - count_tokens()     single string:           P95 < 1ms
  - count_tokens_dict() single dict:            P95 < 1ms
  - ContextBudget.apply() within-budget:        P95 < 5ms
  - ContextBudget.apply() over-budget (L1-L3):  P95 < 10ms

NO MOCKS -- real ContextBuilder, ContextBudget, TestSessionStateReaderAdapter,
TestPromptSystemAdapter.  Real token counting (tiktoken or fallback).

References:
  - fabric-implementation-plan.md Epic 6.7, Issue 6.7.3
  - policies.contract.yaml SLI: context_build <50ms P95
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter
from k1.fabric.core.context_budget import (
    ContextBudget,
    ContextBudgetConfig,
    count_tokens,
    count_tokens_dict,
)
from k1.fabric.core.context_builder import ContextBuilder, ContextBuildResult
from k1.fabric.types import Availability, CapabilityContract, InputSpec, SafetyBand

# ---------------------------------------------------------------------------
# Realistic session section data (mirrors production SessionState)
# ---------------------------------------------------------------------------

_SECTION_CONTROL = {
    "current_goal": "schedule_doctor_appointment",
    "active_plan_id": "plan-8475-fa29",
    "turn_number": 3,
    "last_capability_used": "tool.read.calendar_availability_checker",
    "pending_clarifications": [],
    "session_start_utc": "2025-07-15T09:30:00Z",
    "interaction_mode": "conversational",
}

_SECTION_BELIEFS_ACTIVE = {
    "user_prefers_morning_appointments": {"value": True, "confidence": 0.92, "source": "explicit"},
    "user_primary_doctor_name": {
        "value": "Dr. Eleanor Richardson",
        "confidence": 0.85,
        "source": "memory",
    },
    "user_insurance_provider": {
        "value": "BlueCross BlueShield Premium",
        "confidence": 0.78,
        "source": "inferred",
    },
    "user_allergies_documented": {
        "value": ["penicillin", "shellfish"],
        "confidence": 0.95,
        "source": "explicit",
    },
    "user_preferred_clinic_location": {
        "value": "Riverside Medical Center, Suite 204",
        "confidence": 0.70,
        "source": "history",
    },
}

_SECTION_SCOREBOARD = {
    "total_turns": 47,
    "successful_tool_calls": 38,
    "failed_tool_calls": 2,
    "clarification_requests": 7,
    "avg_response_time_ms": 342,
    "capability_usage_histogram": {
        "tool.read.calendar_availability_checker": 12,
        "tool.execute.appointment_scheduler": 8,
        "tool.read.health_record_retriever": 6,
        "tool.execute.medication_reminder": 5,
    },
}

_SECTION_HISTORY_ACTIVE = {
    "turns": [
        {
            "turn_id": 1,
            "user_message": "I need to schedule a checkup with my doctor",
            "assistant_response": "I can help you schedule an appointment with Dr. Richardson. What dates work best for you?",
            "timestamp_utc": "2025-07-15T09:30:15Z",
        },
        {
            "turn_id": 2,
            "user_message": "Any morning slot next Tuesday or Wednesday would work",
            "assistant_response": "Let me check Dr. Richardson's availability for Tuesday and Wednesday mornings.",
            "timestamp_utc": "2025-07-15T09:30:45Z",
        },
        {
            "turn_id": 3,
            "user_message": "Tuesday is preferred if there's a 9am or 10am slot",
            "assistant_response": "Checking for Tuesday morning 9am-10am availability at Riverside Medical Center.",
            "timestamp_utc": "2025-07-15T09:31:10Z",
        },
    ]
}

_SECTION_AFFECTIVE_NOW = {
    "emotion": "calm",
    "intensity": 0.25,
    "valence": 0.6,
    "arousal": 0.3,
    "confidence": 0.88,
    "source": "linguistic_analysis",
    "last_updated_utc": "2025-07-15T09:31:10Z",
}

_SECTION_NARRATIVE_ACTIVE = {
    "active_thread": "healthcare_management",
    "thread_start_utc": "2025-07-15T09:30:00Z",
    "key_entities": ["Dr. Richardson", "Riverside Medical Center", "checkup"],
    "sentiment_trend": "positive",
    "complexity_level": "routine",
}

_SECTION_META = {
    "family_id": "fam-a9c3e821",
    "member_id": "mem-dad-001",
    "member_role": "father",
    "timezone": "America/Chicago",
    "locale": "en-US",
    "privacy_level": "standard",
}

# Optional / warm sections
_SECTION_BELIEFS_HISTORY = {
    "archived_beliefs": [
        {"key": "preferred_pharmacy", "value": "CVS Main Street", "retired_utc": "2025-06-01"},
        {"key": "exercise_routine", "value": "morning_run", "retired_utc": "2025-05-15"},
    ]
}

_SECTION_HISTORY_RECENT = {
    "previous_sessions": [
        {
            "session_id": "sess-prev-001",
            "summary": "Scheduled dentist appointment",
            "date": "2025-07-10",
        },
        {
            "session_id": "sess-prev-002",
            "summary": "Refilled prescription medications",
            "date": "2025-07-08",
        },
    ]
}

_SECTION_PERSONA = {
    "name": "Family Health Assistant",
    "personality_traits": ["empathetic", "thorough", "proactive"],
    "communication_style": "warm_professional",
    "domain_expertise": ["healthcare", "scheduling", "medication_management"],
}

_SECTION_TELEMETRY = {
    "session_duration_seconds": 85,
    "messages_per_minute": 2.1,
    "avg_token_count_per_turn": 127,
    "error_count": 0,
    "retry_count": 1,
}

# All required (HOT) sections
_HOT_SECTIONS = {
    "control": _SECTION_CONTROL,
    "beliefs_active": _SECTION_BELIEFS_ACTIVE,
    "scoreboard": _SECTION_SCOREBOARD,
    "history_active": _SECTION_HISTORY_ACTIVE,
    "affective_now": _SECTION_AFFECTIVE_NOW,
    "narrative_active": _SECTION_NARRATIVE_ACTIVE,
    "meta": _SECTION_META,
}

# Optional (WARM) sections
_WARM_SECTIONS = {
    "beliefs_history": _SECTION_BELIEFS_HISTORY,
    "history_recent": _SECTION_HISTORY_RECENT,
    "persona": _SECTION_PERSONA,
    "telemetry": _SECTION_TELEMETRY,
}

# Combine all
_ALL_SECTIONS = {**_HOT_SECTIONS, **_WARM_SECTIONS}

# Realistic prompt template
_PROMPT_TEMPLATE = (
    "You are a Family Health Assistant helping {member_role} manage healthcare.\n"
    "Current emotional state: {emotion} (intensity: {intensity}).\n"
    "Active goal: {goal}.\n"
    "Available context sections: {section_count}.\n\n"
    "Instructions:\n"
    "1. Always verify appointment details before confirming.\n"
    "2. Check medication interactions when relevant.\n"
    "3. Respect the user's scheduling preferences.\n"
    "4. Confirm insurance coverage when applicable.\n"
    "5. Document all health-related actions in the journal.\n\n"
    "Respond in a warm, professional tone appropriate for healthcare interactions."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state_reader(
    session_id: str,
    sections: Dict[str, Dict[str, Any]],
) -> TestSessionStateReaderAdapter:
    """Pre-load sections into a TestSessionStateReaderAdapter."""
    reader = TestSessionStateReaderAdapter()
    reader.load_many(session_id, sections)
    return reader


def _make_prompt_system() -> TestPromptSystemAdapter:
    """Create a prompt system with a realistic template."""
    ps = TestPromptSystemAdapter()
    ps.add_template(
        name="healthcare_assistant",
        template=_PROMPT_TEMPLATE,
        variables=["member_role", "emotion", "intensity", "goal", "section_count"],
    )
    ps.add_template(
        name="general_assistant",
        template=(
            "You are a helpful family AI assistant.\n"
            "Help with: {task_description}\n"
            "Be concise and accurate."
        ),
        variables=["task_description"],
    )
    return ps


def _make_small_contract() -> CapabilityContract:
    """Contract requiring 2-3 small context sections."""
    return CapabilityContract(
        name="tool.read.calendar_availability_checker",
        version="2.1.0",
        domain=["HEALTH", "PLANNING"],
        description="Check calendar availability for scheduling appointments",
        required_inputs=[
            InputSpec(name="date_range_start", type="DATE", description="Start date"),
            InputSpec(name="date_range_end", type="DATE", description="End date"),
        ],
        output={"type": "object", "properties": {"available_slots": {"type": "array"}}},
        provider_type="MCP",
        provider_id="mcp-calendar-checker",
        required_context=["control", "meta"],
        optional_context=["affective_now"],
        safety_band_min=SafetyBand.GREEN.value,
        availability=Availability.ONLINE.value,
    )


def _make_large_contract() -> CapabilityContract:
    """Contract requiring 6+ context sections (hot + warm)."""
    return CapabilityContract(
        name="tool.execute.appointment_scheduler",
        version="3.0.5",
        domain=["HEALTH", "PLANNING", "COMMUNICATION"],
        description=(
            "Schedule medical appointments with provider, verify insurance, "
            "check medication interactions, and update health journal"
        ),
        required_inputs=[
            InputSpec(name="provider_name", type="STRING", description="Doctor name"),
            InputSpec(name="preferred_date", type="DATE", description="Preferred date"),
            InputSpec(name="preferred_time", type="STRING", description="Preferred time slot"),
        ],
        output={
            "type": "object",
            "properties": {
                "appointment_id": {"type": "string"},
                "confirmed_date": {"type": "string"},
                "confirmed_time": {"type": "string"},
            },
        },
        provider_type="MCP",
        provider_id="mcp-appointment-scheduler",
        required_context=[
            "control",
            "beliefs_active",
            "scoreboard",
            "history_active",
            "affective_now",
            "meta",
        ],
        optional_context=[
            "narrative_active",
            "beliefs_history",
            "history_recent",
            "persona",
            "telemetry",
        ],
        safety_band_min=SafetyBand.GREEN.value,
        availability=Availability.ONLINE.value,
    )


def _percentile(data: List[float], pct: float) -> float:
    data_sorted = sorted(data)
    idx = int(len(data_sorted) * pct / 100)
    idx = min(idx, len(data_sorted) - 1)
    return data_sorted[idx]


# ---------------------------------------------------------------------------
# Realistic text payloads for token counting benchmarks
# ---------------------------------------------------------------------------

_SHORT_TEXT = "Schedule a doctor appointment for next Tuesday morning at 9am."

_MEDIUM_TEXT = (
    "The patient has a history of controlled hypertension managed with lisinopril 20mg "
    "daily. Last blood pressure reading was 128/82 mmHg recorded on July 10, 2025. "
    "The patient reports occasional dizziness in the morning and requests a follow-up "
    "appointment with Dr. Eleanor Richardson at Riverside Medical Center. Insurance "
    "coverage through BlueCross BlueShield Premium plan has been verified and the "
    "copay for specialist visits is $30. Previous appointments at this clinic have "
    "been satisfactory according to the patient's feedback."
)

_LONG_TEXT = _MEDIUM_TEXT * 20  # ~10KB of text

_LARGE_DICT = {
    f"section_{i}": {
        f"key_{j}": f"value_{j}_with_realistic_content_for_benchmarking_{i}" for j in range(50)
    }
    for i in range(10)
}


# =========================================================================
# ContextBuilder.build() -- small context benchmarks
# =========================================================================


class TestBenchContextBuildSmall:
    """
    Benchmark ContextBuilder.build() with small context (2-3 sections).

    Target: P95 < 10ms.
    """

    def test_build_small_context_p95_under_10ms(self) -> None:
        """build() with 2 required + 1 optional section: P95 < 10ms."""
        session_id = "bench-sess-small-001"
        reader = _make_state_reader(session_id, _ALL_SECTIONS)
        prompt_system = _make_prompt_system()
        builder = ContextBuilder(state_reader=reader, prompt_system=prompt_system)
        contract = _make_small_contract()

        # Warm up
        builder.build(
            contract=contract,
            params={"date_range_start": "2025-07-22", "date_range_end": "2025-07-23"},
            session_id=session_id,
            trace_id="bench-trace-warmup",
        )

        timings: List[float] = []
        for trial in range(100):
            t0 = time.perf_counter()
            result = builder.build(
                contract=contract,
                params={
                    "date_range_start": "2025-07-22",
                    "date_range_end": "2025-07-23",
                },
                session_id=session_id,
                trace_id=f"bench-trace-small-{trial:04d}",
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)

        p95 = _percentile(timings, 95)
        median = _percentile(timings, 50)
        assert p95 < 10, f"build(small) P95={p95:.2f}ms exceeds 10ms " f"(median={median:.2f}ms)"

    def test_build_small_returns_context_result(self) -> None:
        """build() returns ContextBuildResult with populated context."""
        session_id = "bench-sess-verify-001"
        reader = _make_state_reader(session_id, _ALL_SECTIONS)
        prompt_system = _make_prompt_system()
        builder = ContextBuilder(state_reader=reader, prompt_system=prompt_system)
        contract = _make_small_contract()

        result = builder.build(
            contract=contract,
            params={"date_range_start": "2025-07-22", "date_range_end": "2025-07-23"},
            session_id=session_id,
            trace_id="bench-trace-verify",
        )
        assert isinstance(result, ContextBuildResult)
        assert result.assembly_ms >= 0
        assert result.budget is not None
        assert result.context is not None

    def test_build_small_no_missing_required(self) -> None:
        """Small context with all sections available: no missing required."""
        session_id = "bench-sess-nomissing-001"
        reader = _make_state_reader(session_id, _ALL_SECTIONS)
        builder = ContextBuilder(state_reader=reader)
        contract = _make_small_contract()

        result = builder.build(
            contract=contract,
            params={"date_range_start": "2025-07-22"},
            session_id=session_id,
        )
        assert result.missing_required == []


# =========================================================================
# ContextBuilder.build() -- large context benchmarks
# =========================================================================


class TestBenchContextBuildLarge:
    """
    Benchmark ContextBuilder.build() with large context (6+ sections).

    Target: P95 < 50ms.
    """

    def test_build_large_context_p95_under_50ms(self) -> None:
        """build() with 6 required + 5 optional sections: P95 < 50ms."""
        session_id = "bench-sess-large-001"
        reader = _make_state_reader(session_id, _ALL_SECTIONS)
        prompt_system = _make_prompt_system()
        builder = ContextBuilder(state_reader=reader, prompt_system=prompt_system)
        contract = _make_large_contract()

        # Warm up
        builder.build(
            contract=contract,
            params={
                "provider_name": "Dr. Eleanor Richardson",
                "preferred_date": "2025-07-22",
                "preferred_time": "09:00",
            },
            session_id=session_id,
            trace_id="bench-trace-large-warmup",
            prompt_template_name="healthcare_assistant",
            prompt_variables={
                "member_role": "father",
                "emotion": "calm",
                "intensity": "0.25",
                "goal": "schedule_doctor_appointment",
                "section_count": "11",
            },
        )

        timings: List[float] = []
        for trial in range(50):
            t0 = time.perf_counter()
            result = builder.build(
                contract=contract,
                params={
                    "provider_name": "Dr. Eleanor Richardson",
                    "preferred_date": "2025-07-22",
                    "preferred_time": "09:00",
                },
                session_id=session_id,
                trace_id=f"bench-trace-large-{trial:04d}",
                prompt_template_name="healthcare_assistant",
                prompt_variables={
                    "member_role": "father",
                    "emotion": "calm",
                    "intensity": "0.25",
                    "goal": "schedule_doctor_appointment",
                    "section_count": "11",
                },
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)

        p95 = _percentile(timings, 95)
        median = _percentile(timings, 50)
        assert p95 < 50, f"build(large) P95={p95:.2f}ms exceeds 50ms " f"(median={median:.2f}ms)"

    def test_build_large_with_prompt_resolution(self) -> None:
        """Large build with prompt template resolves successfully."""
        session_id = "bench-sess-prompt-001"
        reader = _make_state_reader(session_id, _ALL_SECTIONS)
        prompt_system = _make_prompt_system()
        builder = ContextBuilder(state_reader=reader, prompt_system=prompt_system)
        contract = _make_large_contract()

        result = builder.build(
            contract=contract,
            params={
                "provider_name": "Dr. Richardson",
                "preferred_date": "2025-07-22",
                "preferred_time": "09:00",
            },
            session_id=session_id,
            trace_id="bench-trace-prompt",
            prompt_template_name="healthcare_assistant",
            prompt_variables={
                "member_role": "father",
                "emotion": "calm",
                "intensity": "0.25",
                "goal": "schedule_doctor_appointment",
                "section_count": "11",
            },
        )
        assert result.prompt_resolved is True
        assert result.context.prompt is not None

    def test_build_large_no_reader_graceful(self) -> None:
        """build() without state reader degrades gracefully (missing sections)."""
        builder = ContextBuilder(state_reader=None, prompt_system=None)
        contract = _make_large_contract()

        result = builder.build(
            contract=contract,
            params={"provider_name": "Dr. Smith"},
            trace_id="bench-trace-no-reader",
        )
        assert len(result.missing_required) > 0
        assert result.context is not None


# =========================================================================
# ContextBuilder.build_minimal() benchmarks
# =========================================================================


class TestBenchContextBuildMinimal:
    """
    Benchmark ContextBuilder.build_minimal() -- simple tool calls.

    Target: P95 < 1ms.
    """

    def test_build_minimal_p95_under_1ms(self) -> None:
        """build_minimal() with small params: P95 < 1ms."""
        builder = ContextBuilder()

        # Warm up
        builder.build_minimal(params={"query": "warm up"}, trace_id="warmup")

        timings: List[float] = []
        for trial in range(200):
            t0 = time.perf_counter()
            ctx = builder.build_minimal(
                params={"query": f"test query number {trial}", "location": "Chicago IL"},
                trace_id=f"bench-minimal-{trial:04d}",
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)

        p95 = _percentile(timings, 95)
        assert p95 < 1, f"build_minimal() P95={p95:.4f}ms exceeds 1ms"

    def test_build_minimal_returns_execution_context(self) -> None:
        """build_minimal() returns an ExecutionContext with params."""
        builder = ContextBuilder()
        ctx = builder.build_minimal(
            params={"device_id": "thermostat-001", "target_temp": 72},
            trace_id="bench-verify-minimal",
        )
        assert ctx.params["device_id"] == "thermostat-001"
        assert ctx.trace_id == "bench-verify-minimal"


# =========================================================================
# Token counting benchmarks
# =========================================================================


class TestBenchTokenCounting:
    """
    Benchmark count_tokens() and count_tokens_dict().

    Target: P95 < 1ms for typical payloads (short, medium, ~10KB).
    """

    def test_count_tokens_short_text_p95_under_1ms(self) -> None:
        """count_tokens() on short text (~60 chars): P95 < 1ms."""
        # Warm up
        count_tokens(_SHORT_TEXT)

        timings: List[float] = []
        for _ in range(200):
            t0 = time.perf_counter()
            count = count_tokens(_SHORT_TEXT)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)
            assert count > 0

        p95 = _percentile(timings, 95)
        assert p95 < 1, f"count_tokens(short) P95={p95:.4f}ms exceeds 1ms"

    def test_count_tokens_medium_text_p95_under_1ms(self) -> None:
        """count_tokens() on medium text (~500 chars): P95 < 1ms."""
        count_tokens(_MEDIUM_TEXT)

        timings: List[float] = []
        for _ in range(200):
            t0 = time.perf_counter()
            count = count_tokens(_MEDIUM_TEXT)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)
            assert count > 0

        p95 = _percentile(timings, 95)
        assert p95 < 1, f"count_tokens(medium) P95={p95:.4f}ms exceeds 1ms"

    def test_count_tokens_long_text_p95_under_5ms(self) -> None:
        """count_tokens() on ~10KB text: P95 < 5ms."""
        count_tokens(_LONG_TEXT)

        timings: List[float] = []
        for _ in range(100):
            t0 = time.perf_counter()
            count = count_tokens(_LONG_TEXT)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)
            assert count > 0

        p95 = _percentile(timings, 95)
        assert p95 < 5, f"count_tokens(long) P95={p95:.2f}ms exceeds 5ms"

    def test_count_tokens_dict_p95_under_1ms(self) -> None:
        """count_tokens_dict() on moderate dict: P95 < 1ms."""
        small_dict = {
            "query": "schedule doctor appointment",
            "location": "Riverside Medical Center",
            "date": "2025-07-22",
            "time_preference": "morning",
        }
        count_tokens_dict(small_dict)

        timings: List[float] = []
        for _ in range(200):
            t0 = time.perf_counter()
            count = count_tokens_dict(small_dict)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)
            assert count > 0

        p95 = _percentile(timings, 95)
        assert p95 < 1, f"count_tokens_dict(small) P95={p95:.4f}ms exceeds 1ms"

    def test_count_tokens_dict_large_p95_under_5ms(self) -> None:
        """count_tokens_dict() on large dict (500 keys): P95 < 5ms."""
        count_tokens_dict(_LARGE_DICT)

        timings: List[float] = []
        for _ in range(50):
            t0 = time.perf_counter()
            count = count_tokens_dict(_LARGE_DICT)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)
            assert count > 0

        p95 = _percentile(timings, 95)
        assert p95 < 10, f"count_tokens_dict(large) P95={p95:.2f}ms exceeds 10ms"

    def test_count_tokens_empty_returns_zero(self) -> None:
        """count_tokens('') returns 0 and count_tokens_dict({}) returns 0."""
        assert count_tokens("") == 0
        assert count_tokens_dict({}) == 0


# =========================================================================
# ContextBudget.apply() benchmarks
# =========================================================================


class TestBenchContextBudget:
    """
    Benchmark ContextBudget.apply() with within-budget and over-budget
    scenarios.
    """

    def test_budget_apply_within_budget_p95_under_5ms(self) -> None:
        """apply() when total tokens fit within budget: P95 < 5ms."""
        budget = ContextBudget()

        sections = {
            "control": _SECTION_CONTROL,
            "beliefs_active": _SECTION_BELIEFS_ACTIVE,
            "meta": _SECTION_META,
        }
        prompt = "You are a helpful family assistant. Be concise and accurate."
        params = {"query": "schedule appointment", "date": "2025-07-22"}

        # Warm up
        budget.apply(
            session_sections=sections,
            prompt=prompt,
            params=params,
            optional_sections=["persona"],
        )

        timings: List[float] = []
        for trial in range(100):
            t0 = time.perf_counter()
            result = budget.apply(
                session_sections=sections,
                prompt=prompt,
                params=params,
                optional_sections=[],
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)
            assert not result.over_budget

        p95 = _percentile(timings, 95)
        assert p95 < 5, f"apply(within-budget) P95={p95:.2f}ms exceeds 5ms"

    def test_budget_apply_over_budget_compression_p95_under_10ms(self) -> None:
        """apply() with over-budget sections triggers compression: P95 < 10ms."""
        # Use a very low ceiling to force compression
        config = ContextBudgetConfig(ceiling=200, response_headroom=50)
        budget = ContextBudget(config=config)

        sections = dict(_ALL_SECTIONS)
        prompt = _PROMPT_TEMPLATE
        params = {"query": "large request with many parameters", "extra": "data" * 20}

        # Warm up
        budget.apply(
            session_sections=sections,
            prompt=prompt,
            params=params,
            optional_sections=list(_WARM_SECTIONS.keys()),
        )

        timings: List[float] = []
        for trial in range(50):
            t0 = time.perf_counter()
            result = budget.apply(
                session_sections=dict(_ALL_SECTIONS),
                prompt=prompt,
                params=params,
                optional_sections=list(_WARM_SECTIONS.keys()),
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            timings.append(elapsed_ms)
            # Compression should have been applied
            assert result.compression_applied.value != "none" or result.over_budget

        p95 = _percentile(timings, 95)
        assert p95 < 10, f"apply(over-budget) P95={p95:.2f}ms exceeds 10ms"

    def test_budget_effective_budget_calculation(self) -> None:
        """effective_budget = ceiling - response_headroom."""
        config = ContextBudgetConfig(ceiling=128_000, response_headroom=4_000)
        budget = ContextBudget(config=config)
        assert budget.effective_budget == 124_000

    def test_budget_drops_optional_sections_first(self) -> None:
        """Over-budget L1 compression drops optional sections."""
        config = ContextBudgetConfig(ceiling=300, response_headroom=50)
        budget = ContextBudget(config=config)

        sections = dict(_ALL_SECTIONS)
        result = budget.apply(
            session_sections=sections,
            prompt=None,
            params={"query": "test"},
            optional_sections=list(_WARM_SECTIONS.keys()),
        )
        if result.sections_dropped:
            for dropped in result.sections_dropped:
                # Only warm/optional sections should be dropped first
                assert dropped in _WARM_SECTIONS or dropped in _ALL_SECTIONS
