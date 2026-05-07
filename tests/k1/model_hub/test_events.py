"""M1 Foundation -- Test Event Schemas [F04].

Tests all event topic constants and payload dataclasses defined in
k1.model_hub.events.

NO MOCKS.  Pure data structure tests.
"""

from __future__ import annotations

import dataclasses

import pytest

from k1.model_hub.events import (
    TOPIC_BUDGET_ALERT,
    TOPIC_CACHE_HIT,
    TOPIC_CAPABILITY_AVAILABLE,
    TOPIC_CIRCUIT_STATE,
    TOPIC_FALLBACK_TRIGGERED,
    TOPIC_PROVIDER_FAILURE,
    TOPIC_PROVIDER_HEALTH,
    TOPIC_PROVIDER_REGISTERED,
    TOPIC_REQUEST_RECEIVED,
    TOPIC_REQUEST_ROUTED,
    TOPIC_RESPONSE_COMPLETE,
    BudgetAlertPayload,
    CacheHitPayload,
    CapabilityAvailablePayload,
    CircuitStatePayload,
    FallbackTriggeredPayload,
    ProviderFailurePayload,
    ProviderHealthPayload,
    ProviderRegisteredPayload,
    RequestReceivedPayload,
    RequestRoutedPayload,
    ResponseCompletePayload,
)
from k1.model_hub.types import CapabilityType, CircuitState, HealthStatus

# =========================================================================
# Topic Constants
# =========================================================================


class TestTopicConstants:
    def test_all_topics_follow_pattern(self) -> None:
        topics = [
            TOPIC_REQUEST_RECEIVED,
            TOPIC_REQUEST_ROUTED,
            TOPIC_RESPONSE_COMPLETE,
            TOPIC_CACHE_HIT,
            TOPIC_PROVIDER_FAILURE,
            TOPIC_FALLBACK_TRIGGERED,
            TOPIC_CIRCUIT_STATE,
            TOPIC_BUDGET_ALERT,
            TOPIC_PROVIDER_HEALTH,
            TOPIC_PROVIDER_REGISTERED,
            TOPIC_CAPABILITY_AVAILABLE,
        ]
        assert len(topics) == 11
        for t in topics:
            assert t.startswith("k1.model_hub.")
            assert t.endswith(".v1")

    def test_topic_values(self) -> None:
        assert TOPIC_REQUEST_RECEIVED == "k1.model_hub.request.received.v1"
        assert TOPIC_REQUEST_ROUTED == "k1.model_hub.request.routed.v1"
        assert TOPIC_RESPONSE_COMPLETE == "k1.model_hub.response.complete.v1"
        assert TOPIC_CACHE_HIT == "k1.model_hub.cache.hit.v1"
        assert TOPIC_PROVIDER_FAILURE == "k1.model_hub.provider.failure.v1"
        assert TOPIC_FALLBACK_TRIGGERED == "k1.model_hub.fallback.triggered.v1"
        assert TOPIC_CIRCUIT_STATE == "k1.model_hub.circuit.state.v1"
        assert TOPIC_BUDGET_ALERT == "k1.model_hub.budget.alert.v1"
        assert TOPIC_PROVIDER_HEALTH == "k1.model_hub.provider.health.v1"
        assert TOPIC_PROVIDER_REGISTERED == "k1.model_hub.provider.registered.v1"
        assert TOPIC_CAPABILITY_AVAILABLE == "k1.model_hub.capability.available.v1"


# =========================================================================
# Payload Dataclasses
# =========================================================================


class TestRequestReceivedPayload:
    def test_construction(self) -> None:
        p = RequestReceivedPayload(
            request_id="r1",
            consumer_id="planner",
            capability=CapabilityType.CHAT,
        )
        assert p.request_id == "r1"
        assert p.budget_remaining_pct == 100.0
        assert p.trace_id == ""

    def test_frozen(self) -> None:
        p = RequestReceivedPayload(request_id="r1", consumer_id="c", capability=CapabilityType.CHAT)
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.request_id = "x"  # type: ignore[misc]


class TestRequestRoutedPayload:
    def test_construction(self) -> None:
        p = RequestRoutedPayload(
            request_id="r1",
            provider_id="openai",
            model_id="gpt-4o",
            capability=CapabilityType.CHAT,
        )
        assert p.provider_id == "openai"


class TestResponseCompletePayload:
    def test_construction(self) -> None:
        p = ResponseCompletePayload(request_id="r1")
        assert p.tokens_used == 0
        assert p.latency_ms == 0
        assert p.cost_usd == 0.0
        assert p.cache_hit is False


class TestCacheHitPayload:
    def test_construction(self) -> None:
        p = CacheHitPayload(
            request_id="r1",
            cache_key="k1",
            capability=CapabilityType.CHAT,
        )
        assert p.age_ms == 0


class TestProviderFailurePayload:
    def test_construction(self) -> None:
        p = ProviderFailurePayload(request_id="r1", provider_id="openai")
        assert p.will_fallback is False
        assert p.error_type == ""


class TestFallbackTriggeredPayload:
    def test_construction(self) -> None:
        p = FallbackTriggeredPayload(
            request_id="r1", from_provider="openai", to_provider="anthropic"
        )
        assert p.reason == ""


class TestCircuitStatePayload:
    def test_construction(self) -> None:
        p = CircuitStatePayload(
            provider_id="openai",
            old_state=CircuitState.CLOSED,
            new_state=CircuitState.OPEN,
        )
        assert p.failure_count == 0

    def test_frozen(self) -> None:
        p = CircuitStatePayload(
            provider_id="openai",
            old_state=CircuitState.CLOSED,
            new_state=CircuitState.OPEN,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.failure_count = 5  # type: ignore[misc]


class TestBudgetAlertPayload:
    def test_construction(self) -> None:
        p = BudgetAlertPayload()
        assert p.tenant_id == "default"
        assert p.level == "WARNING"

    def test_invalid_level_rejected(self) -> None:
        with pytest.raises(ValueError, match="level must be WARNING|EXCEEDED"):
            BudgetAlertPayload(level="INFO")

    def test_exceeded_level(self) -> None:
        p = BudgetAlertPayload(level="EXCEEDED", pct=100.0)
        assert p.level == "EXCEEDED"


class TestProviderHealthPayload:
    def test_construction(self) -> None:
        p = ProviderHealthPayload(provider_id="openai", status=HealthStatus.HEALTHY)
        assert p.latency_p50 == 0
        assert p.error_rate == 0.0


class TestProviderRegisteredPayload:
    def test_construction(self) -> None:
        p = ProviderRegisteredPayload(provider_id="openai")
        assert p.capabilities == []
        assert p.model_count == 0


class TestCapabilityAvailablePayload:
    def test_construction(self) -> None:
        p = CapabilityAvailablePayload(capability=CapabilityType.CHAT)
        assert p.provider_ids == []
        assert p.model_count == 0
