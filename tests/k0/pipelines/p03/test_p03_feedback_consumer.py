"""Tests for P03 Feedback Consumer.

Issue: M3 3.2.6 — P21 to P03 Feedback Consumer
Tests the feedback signal consumption, routing, and metrics.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.feedback.payloads import P03FeedbackPayload
from k0.feedback.topics import FEEDBACK_SIGNAL_P03_V1
from k0.pipelines.p03.feedback_consumer import (
    FeedbackType,
    P03FeedbackConsumer,
    P03FeedbackMetrics,
    P03FeedbackSubscriber,
)


class TestP03FeedbackPayload:
    """Tests for P03FeedbackPayload schema."""

    def test_salience_adjustment_payload(self):
        """Test SALIENCE_ADJUSTMENT payload validation."""
        payload = P03FeedbackPayload(
            feedback_type="SALIENCE_ADJUSTMENT",
            entity_id="PERSON_mom_123",
            salience_delta=0.15,
            was_helpful=True,
            confidence=0.70,
        )
        assert payload.feedback_type == "SALIENCE_ADJUSTMENT"
        assert payload.salience_delta == 0.15
        assert payload.entity_id == "PERSON_mom_123"

    def test_decay_reversal_payload(self):
        """Test DECAY_REVERSAL payload validation."""
        payload = P03FeedbackPayload(
            feedback_type="DECAY_REVERSAL",
            entity_id="EVENT_birthday_2024",
            decay_lambda_delta=-0.005,
            confidence=0.85,
        )
        assert payload.feedback_type == "DECAY_REVERSAL"
        assert payload.decay_lambda_delta == -0.005

    def test_cluster_correction_payload(self):
        """Test CLUSTER_CORRECTION payload validation."""
        payload = P03FeedbackPayload(
            feedback_type="CLUSTER_CORRECTION",
            entity_id="ENTITY_123",
            correct_cluster_id="cluster_a",
            incorrect_cluster_id="cluster_b",
            confidence=0.90,
        )
        assert payload.feedback_type == "CLUSTER_CORRECTION"
        assert payload.correct_cluster_id == "cluster_a"
        assert payload.incorrect_cluster_id == "cluster_b"

    def test_reinforcement_outcome_payload(self):
        """Test REINFORCEMENT_OUTCOME payload validation."""
        payload = P03FeedbackPayload(
            feedback_type="REINFORCEMENT_OUTCOME",
            edge_id="edge_123",
            was_retrieved=True,
            was_helpful=True,
            confidence=0.75,
        )
        assert payload.feedback_type == "REINFORCEMENT_OUTCOME"
        assert payload.was_retrieved is True
        assert payload.was_helpful is True

    def test_novelty_signal_payload(self):
        """Test NOVELTY_SIGNAL payload validation."""
        payload = P03FeedbackPayload(
            feedback_type="NOVELTY_SIGNAL",
            session_context={"query": "what is X?"},
            confidence=0.40,
        )
        assert payload.feedback_type == "NOVELTY_SIGNAL"
        assert payload.session_context == {"query": "what is X?"}

    def test_regret_signal_payload(self):
        """Test REGRET_SIGNAL payload validation."""
        payload = P03FeedbackPayload(
            feedback_type="REGRET_SIGNAL",
            entity_id="ENTITY_pruned_456",
            was_retrieved=True,
            confidence=0.90,
        )
        assert payload.feedback_type == "REGRET_SIGNAL"
        assert payload.was_retrieved is True

    def test_salience_delta_bounds(self):
        """Test salience_delta must be in [-1.0, 1.0]."""
        # Valid bounds
        P03FeedbackPayload(
            feedback_type="SALIENCE_ADJUSTMENT",
            salience_delta=-1.0,
        )
        P03FeedbackPayload(
            feedback_type="SALIENCE_ADJUSTMENT",
            salience_delta=1.0,
        )

        # Out of bounds
        with pytest.raises(ValueError):
            P03FeedbackPayload(
                feedback_type="SALIENCE_ADJUSTMENT",
                salience_delta=1.5,
            )
        with pytest.raises(ValueError):
            P03FeedbackPayload(
                feedback_type="SALIENCE_ADJUSTMENT",
                salience_delta=-1.5,
            )

    def test_confidence_bounds(self):
        """Test confidence must be in [0.0, 1.0]."""
        # Valid bounds
        P03FeedbackPayload(feedback_type="NOVELTY_SIGNAL", confidence=0.0)
        P03FeedbackPayload(feedback_type="NOVELTY_SIGNAL", confidence=1.0)

        # Out of bounds
        with pytest.raises(ValueError):
            P03FeedbackPayload(feedback_type="NOVELTY_SIGNAL", confidence=1.5)
        with pytest.raises(ValueError):
            P03FeedbackPayload(feedback_type="NOVELTY_SIGNAL", confidence=-0.1)

    def test_invalid_feedback_type(self):
        """Test invalid feedback_type is rejected."""
        with pytest.raises(ValueError):
            P03FeedbackPayload(feedback_type="INVALID_TYPE")


class TestP03FeedbackMetrics:
    """Tests for P03FeedbackMetrics."""

    def test_record_received(self):
        """Test recording received signals."""
        metrics = P03FeedbackMetrics()
        metrics.record_received("SALIENCE_ADJUSTMENT")
        metrics.record_received("SALIENCE_ADJUSTMENT")
        metrics.record_received("DECAY_REVERSAL")

        assert metrics.received_total["SALIENCE_ADJUSTMENT"] == 2
        assert metrics.received_total["DECAY_REVERSAL"] == 1

    def test_record_processed(self):
        """Test recording processed signals."""
        metrics = P03FeedbackMetrics()
        metrics.record_processed("CLUSTER_CORRECTION")

        assert metrics.processed_total["CLUSTER_CORRECTION"] == 1

    def test_record_error(self):
        """Test recording errors."""
        metrics = P03FeedbackMetrics()
        metrics.record_error("UNKNOWN")

        assert metrics.errors_total["UNKNOWN"] == 1

    def test_as_dict(self):
        """Test metrics export as dictionary."""
        metrics = P03FeedbackMetrics()
        metrics.record_received("NOVELTY_SIGNAL")
        metrics.record_processed("NOVELTY_SIGNAL")

        result = metrics.as_dict()
        assert "p03_feedback_received_total" in result
        assert "p03_feedback_processed_total" in result
        assert "p03_feedback_errors_total" in result


class TestFeedbackType:
    """Tests for FeedbackType enum."""

    def test_all_feedback_types(self):
        """Test all 6 feedback types are defined."""
        assert FeedbackType.SALIENCE_ADJUSTMENT.value == "SALIENCE_ADJUSTMENT"
        assert FeedbackType.DECAY_REVERSAL.value == "DECAY_REVERSAL"
        assert FeedbackType.CLUSTER_CORRECTION.value == "CLUSTER_CORRECTION"
        assert FeedbackType.REINFORCEMENT_OUTCOME.value == "REINFORCEMENT_OUTCOME"
        assert FeedbackType.NOVELTY_SIGNAL.value == "NOVELTY_SIGNAL"
        assert FeedbackType.REGRET_SIGNAL.value == "REGRET_SIGNAL"

    def test_feedback_type_is_string(self):
        """Test FeedbackType can be compared as string."""
        assert FeedbackType.SALIENCE_ADJUSTMENT == "SALIENCE_ADJUSTMENT"


class TestP03FeedbackConsumer:
    """Tests for P03FeedbackConsumer."""

    @pytest.fixture
    def mock_pool(self):
        """Create a mock database pool."""
        pool = MagicMock()
        conn = AsyncMock()
        conn.execute = AsyncMock()

        # Make pool.acquire() return an async context manager
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=None)
        pool.acquire = MagicMock(return_value=cm)

        return pool, conn

    @pytest.fixture
    def consumer(self, mock_pool):
        """Create a P03FeedbackConsumer with mock pool."""
        pool, _ = mock_pool
        return P03FeedbackConsumer(pool)

    def test_topic_constant(self):
        """Test consumer uses correct topic."""
        assert P03FeedbackConsumer.TOPIC == FEEDBACK_SIGNAL_P03_V1
        assert P03FeedbackConsumer.TOPIC == "feedback.signal.p03.v1"

    def test_default_handlers_registered(self, consumer):
        """Test all 6 handlers are registered by default."""
        assert len(consumer._handlers) == 6
        assert FeedbackType.SALIENCE_ADJUSTMENT in consumer._handlers
        assert FeedbackType.DECAY_REVERSAL in consumer._handlers
        assert FeedbackType.CLUSTER_CORRECTION in consumer._handlers
        assert FeedbackType.REINFORCEMENT_OUTCOME in consumer._handlers
        assert FeedbackType.NOVELTY_SIGNAL in consumer._handlers
        assert FeedbackType.REGRET_SIGNAL in consumer._handlers

    @pytest.mark.asyncio
    async def test_process_salience_adjustment(self, consumer, mock_pool):
        """Test processing SALIENCE_ADJUSTMENT signal."""
        _, conn = mock_pool

        message = {
            "feedback_id": "sig_123",
            "payload": {
                "feedback_type": "SALIENCE_ADJUSTMENT",
                "entity_id": "PERSON_mom",
                "salience_delta": 0.1,
                "confidence": 0.7,
            },
        }

        result = await consumer.process(message)

        assert result is True
        assert consumer.metrics.received_total.get("SALIENCE_ADJUSTMENT") == 1
        assert consumer.metrics.processed_total.get("SALIENCE_ADJUSTMENT") == 1
        # Verify mark_consumed was called
        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_decay_reversal(self, consumer, mock_pool):
        """Test processing DECAY_REVERSAL signal."""
        message = {
            "feedback_id": "sig_456",
            "payload": {
                "feedback_type": "DECAY_REVERSAL",
                "entity_id": "EVENT_123",
                "decay_lambda_delta": -0.01,
            },
        }

        result = await consumer.process(message)

        assert result is True
        assert consumer.metrics.processed_total.get("DECAY_REVERSAL") == 1

    @pytest.mark.asyncio
    async def test_process_cluster_correction(self, consumer, mock_pool):
        """Test processing CLUSTER_CORRECTION signal."""
        message = {
            "feedback_id": "sig_789",
            "payload": {
                "feedback_type": "CLUSTER_CORRECTION",
                "entity_id": "ENT_1",
                "correct_cluster_id": "c1",
                "incorrect_cluster_id": "c2",
            },
        }

        result = await consumer.process(message)

        assert result is True
        assert consumer.metrics.processed_total.get("CLUSTER_CORRECTION") == 1

    @pytest.mark.asyncio
    async def test_process_reinforcement_outcome(self, consumer, mock_pool):
        """Test processing REINFORCEMENT_OUTCOME signal."""
        message = {
            "feedback_id": "sig_abc",
            "payload": {
                "feedback_type": "REINFORCEMENT_OUTCOME",
                "edge_id": "edge_1",
                "was_helpful": True,
            },
        }

        result = await consumer.process(message)

        assert result is True
        assert consumer.metrics.processed_total.get("REINFORCEMENT_OUTCOME") == 1

    @pytest.mark.asyncio
    async def test_process_novelty_signal(self, consumer, mock_pool):
        """Test processing NOVELTY_SIGNAL signal."""
        message = {
            "feedback_id": "sig_def",
            "payload": {
                "feedback_type": "NOVELTY_SIGNAL",
                "session_context": {"query": "hedging detected"},
                "confidence": 0.4,
            },
        }

        result = await consumer.process(message)

        assert result is True
        assert consumer.metrics.processed_total.get("NOVELTY_SIGNAL") == 1

    @pytest.mark.asyncio
    async def test_process_regret_signal(self, consumer, mock_pool):
        """Test processing REGRET_SIGNAL signal."""
        message = {
            "feedback_id": "sig_ghi",
            "payload": {
                "feedback_type": "REGRET_SIGNAL",
                "entity_id": "pruned_entity",
                "was_retrieved": True,
            },
        }

        result = await consumer.process(message)

        assert result is True
        assert consumer.metrics.processed_total.get("REGRET_SIGNAL") == 1

    @pytest.mark.asyncio
    async def test_process_invalid_payload(self, consumer, mock_pool):
        """Test processing with invalid payload returns False."""
        message = {
            "feedback_id": "sig_bad",
            "payload": {
                "feedback_type": "INVALID_TYPE",  # Invalid
            },
        }

        result = await consumer.process(message)

        assert result is False
        assert consumer.metrics.errors_total.get("UNKNOWN", 0) == 1

    @pytest.mark.asyncio
    async def test_process_marks_consumed(self, consumer, mock_pool):
        """Test signal is marked consumed in st_feedback_signals."""
        _, conn = mock_pool

        message = {
            "feedback_id": "sig_mark",
            "payload": {
                "feedback_type": "SALIENCE_ADJUSTMENT",
                "entity_id": "test",
            },
        }

        await consumer.process(message)

        # Verify UPDATE was called with correct signal_id
        call_args = conn.execute.call_args
        assert "UPDATE st_feedback_signals" in call_args[0][0]
        assert call_args[0][2] == "sig_mark"  # signal_id

    @pytest.mark.asyncio
    async def test_register_custom_handler(self, consumer, mock_pool):
        """Test registering a custom handler."""
        custom_handler_called = False

        async def custom_handler(payload, conn):
            nonlocal custom_handler_called
            custom_handler_called = True

        consumer.register_handler(FeedbackType.SALIENCE_ADJUSTMENT, custom_handler)

        message = {
            "feedback_id": "sig_custom",
            "payload": {
                "feedback_type": "SALIENCE_ADJUSTMENT",
            },
        }

        await consumer.process(message)

        assert custom_handler_called is True

    @pytest.mark.asyncio
    async def test_metrics_on_error(self, consumer, mock_pool):
        """Test error metrics are recorded on handler failure."""
        pool, _ = mock_pool

        async def failing_handler(payload, conn):
            raise RuntimeError("Handler failed")

        consumer.register_handler(FeedbackType.NOVELTY_SIGNAL, failing_handler)

        message = {
            "feedback_id": "sig_fail",
            "payload": {
                "feedback_type": "NOVELTY_SIGNAL",
            },
        }

        result = await consumer.process(message)

        assert result is False
        assert consumer.metrics.errors_total.get("NOVELTY_SIGNAL") == 1


class TestP03FeedbackSubscriber:
    """Tests for P03FeedbackSubscriber."""

    @pytest.fixture
    def mock_bus(self):
        """Create a mock bus dispatcher."""
        bus = MagicMock()
        bus.subscribe = MagicMock()
        return bus

    @pytest.fixture
    def mock_consumer(self):
        """Create a mock consumer."""
        pool = MagicMock()
        return P03FeedbackConsumer(pool)

    @pytest.fixture
    def subscriber(self, mock_consumer, mock_bus):
        """Create a P03FeedbackSubscriber."""
        return P03FeedbackSubscriber(mock_consumer, mock_bus)

    def test_initial_state(self, subscriber):
        """Test subscriber starts not running."""
        assert subscriber.running is False

    @pytest.mark.asyncio
    async def test_start_subscribes_to_topic(self, subscriber, mock_bus):
        """Test start() subscribes to the correct topic."""
        await subscriber.start()

        assert subscriber.running is True
        mock_bus.subscribe.assert_called_once()
        call_args = mock_bus.subscribe.call_args
        assert call_args.kwargs["topic"] == FEEDBACK_SIGNAL_P03_V1

    @pytest.mark.asyncio
    async def test_start_idempotent(self, subscriber, mock_bus):
        """Test start() is idempotent."""
        await subscriber.start()
        await subscriber.start()  # Second call

        # Only one subscription
        assert mock_bus.subscribe.call_count == 1

    @pytest.mark.asyncio
    async def test_stop_sets_not_running(self, subscriber, mock_bus):
        """Test stop() sets running to False."""
        await subscriber.start()
        await subscriber.stop()

        assert subscriber.running is False

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, subscriber):
        """Test stop() when not running is no-op."""
        await subscriber.stop()  # Should not raise
        assert subscriber.running is False
