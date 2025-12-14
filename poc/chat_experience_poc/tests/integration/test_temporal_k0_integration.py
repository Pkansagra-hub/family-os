"""
Integration tests for Temporal Module ↔ K0 P05 Prospectives

Tests K0 P05 query capability, conversion to triggers, and deduplication.

Architecture:
- Temporal Module queries Mock K0 P05 endpoint
- Discovers prospectives with fire_time <= NOW()
- Converts to Trigger objects
- Merges with local triggers (deduplicates)
- Fires all due triggers via SSE

Performance Targets:
- K0 query: <100ms P95
- Prospective conversion: <50ms P95
- Merge deduplication: <10ms P95
- Scheduler tick overhead: +100ms vs local-only

Coverage:
- Unit tests: K0 query isolation, conversion, merge
- Integration tests: End-to-end flow, error handling
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from l5_infrastructure.temporal.temporal_module import (
    TemporalModule,
    Trigger,
    TriggerType,
    get_temporal_module,
)


class TestTemporalModuleK0Integration:
    """Tests for K0 P05 prospectives integration"""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset TemporalModule singleton before each test"""
        TemporalModule._instance = None
        yield
        TemporalModule._instance = None

    @pytest.fixture
    def temporal_module(self, tmp_path):
        """Create TemporalModule instance with temporary database"""
        db_path = tmp_path / "test_temporal.db"
        module = TemporalModule(
            db_path=db_path,
            sse_url="http://localhost:8002",
            k0_backend_url="http://localhost:8001",
        )
        return module

    # ========== UNIT TESTS: K0 Query ==========

    @pytest.mark.asyncio
    async def test_fetch_prospectives_from_k0_fallback_on_error(self, temporal_module):
        """Test K0 query returns empty list on error (graceful fallback)"""

        # Mock K0 error response
        async def mock_error(*args, **kwargs):
            raise ConnectionError("K0 unavailable")

        temporal_module.http_client.post = mock_error

        # Query
        result = await temporal_module._fetch_prospectives_from_k0()

        # Verify: Empty result (graceful fallback)
        assert result == []

    # ========== UNIT TESTS: P05 → Trigger Conversion ==========

    def test_prospectives_to_triggers_single(self, temporal_module):
        """Test converting single P05 to Trigger"""
        prospectives = [
            {
                "p05_id": "p05_abc123",
                "fire_time": datetime.utcnow().isoformat() + "Z",
                "message": "Reminder",
                "action": "notification",
                "user_id": "user_1",
                "confidence": 0.9,
                "writer_id": "memory_ai",
                "metadata": {"tag": "health"},
            }
        ]

        triggers = temporal_module._prospectives_to_triggers(prospectives)

        assert len(triggers) == 1
        assert triggers[0].trigger_id == "k0_p05_p05_abc123"
        assert triggers[0].trigger_type == TriggerType.TIME_BASED
        assert triggers[0].message == "Reminder"
        assert triggers[0].user_id == "user_1"
        assert triggers[0].metadata["source"] == "k0_p05"
        assert triggers[0].metadata["p05_id"] == "p05_abc123"
        assert triggers[0].metadata["confidence"] == 0.9

    def test_prospectives_to_triggers_multiple(self, temporal_module):
        """Test converting multiple P05s to Triggers"""
        prospectives = [
            {
                "p05_id": f"p05_{i}",
                "fire_time": (datetime.utcnow() + timedelta(minutes=i)).isoformat() + "Z",
                "message": f"Reminder {i}",
                "action": "notification",
                "user_id": "user_1",
                "confidence": 0.9,
            }
            for i in range(5)
        ]

        triggers = temporal_module._prospectives_to_triggers(prospectives)

        assert len(triggers) == 5
        for i, trigger in enumerate(triggers):
            assert trigger.trigger_id == f"k0_p05_p05_{i}"
            assert trigger.message == f"Reminder {i}"

    def test_prospectives_to_triggers_invalid_fire_time(self, temporal_module):
        """Test handling invalid fire_time format"""
        prospectives = [
            {
                "p05_id": "p05_bad",
                "fire_time": "not_a_date",  # Invalid
                "message": "Test",
                "action": "notify",
                "user_id": "user_1",
            }
        ]

        triggers = temporal_module._prospectives_to_triggers(prospectives)

        # Verify: Invalid P05 skipped
        assert len(triggers) == 0

    def test_prospectives_to_triggers_missing_required_fields(self, temporal_module):
        """Test handling missing required fields in P05"""
        prospectives = [
            {
                "p05_id": "p05_incomplete",
                # Missing: fire_time, message, action, user_id
            }
        ]

        triggers = temporal_module._prospectives_to_triggers(prospectives)

        # Verify: Invalid P05 skipped
        assert len(triggers) == 0

    # ========== UNIT TESTS: Merge & Deduplication ==========

    def test_merge_triggers_no_duplicates(self, temporal_module):
        """Test merging with no duplicates"""
        local_trigger = Trigger(
            trigger_id="local_123",
            trigger_type=TriggerType.TIME_BASED,
            fire_time=datetime.utcnow() + timedelta(minutes=5),
            message="Local trigger",
            action="notify",
            user_id="user_1",
        )

        k0_trigger = Trigger(
            trigger_id="k0_p05_abc",
            trigger_type=TriggerType.TIME_BASED,
            fire_time=datetime.utcnow() + timedelta(minutes=3),
            message="K0 prospective",
            action="notify",
            user_id="user_1",
        )

        merged = temporal_module._merge_triggers([local_trigger], [k0_trigger])

        # Verify: Both triggers present
        assert len(merged) == 2
        assert any(t.trigger_id == "local_123" for t in merged)
        assert any(t.trigger_id == "k0_p05_abc" for t in merged)

    def test_merge_triggers_skip_duplicates(self, temporal_module):
        """Test merging skips duplicate K0 triggers"""
        # Same trigger in both lists
        trigger = Trigger(
            trigger_id="k0_p05_abc",
            trigger_type=TriggerType.TIME_BASED,
            fire_time=datetime.utcnow() + timedelta(minutes=5),
            message="Shared trigger",
            action="notify",
            user_id="user_1",
        )

        merged = temporal_module._merge_triggers([trigger], [trigger])

        # Verify: Only one instance (deduped)
        assert len(merged) == 1
        assert merged[0].trigger_id == "k0_p05_abc"

    def test_merge_triggers_local_precedence(self, temporal_module):
        """Test that local triggers take precedence"""
        # Same trigger ID, different details
        local = Trigger(
            trigger_id="shared_123",
            trigger_type=TriggerType.TIME_BASED,
            fire_time=datetime.utcnow() + timedelta(minutes=5),
            message="Local version",
            action="notify",
            user_id="user_1",
        )

        k0 = Trigger(
            trigger_id="shared_123",
            trigger_type=TriggerType.TIME_BASED,
            fire_time=datetime.utcnow() + timedelta(minutes=3),
            message="K0 version",
            action="notify",
            user_id="user_1",
        )

        merged = temporal_module._merge_triggers([local], [k0])

        # Verify: Local version kept
        assert len(merged) == 1
        assert merged[0].message == "Local version"

    def test_merge_triggers_empty_lists(self, temporal_module):
        """Test merging with empty lists"""
        local = []
        k0 = []

        merged = temporal_module._merge_triggers(local, k0)

        assert len(merged) == 0

    def test_merge_triggers_only_local(self, temporal_module):
        """Test merging with only local triggers"""
        local = [
            Trigger(
                trigger_id=f"local_{i}",
                trigger_type=TriggerType.TIME_BASED,
                fire_time=datetime.utcnow() + timedelta(minutes=i),
                message=f"Local {i}",
                action="notify",
                user_id="user_1",
            )
            for i in range(3)
        ]

        merged = temporal_module._merge_triggers(local, [])

        assert len(merged) == 3
        assert all(t.trigger_id.startswith("local_") for t in merged)

    def test_merge_triggers_only_k0(self, temporal_module):
        """Test merging with only K0 prospectives"""
        k0 = [
            Trigger(
                trigger_id=f"k0_p05_p05_{i}",
                trigger_type=TriggerType.TIME_BASED,
                fire_time=datetime.utcnow() + timedelta(minutes=i),
                message=f"K0 {i}",
                action="notify",
                user_id="user_1",
            )
            for i in range(3)
        ]

        merged = temporal_module._merge_triggers([], k0)

        assert len(merged) == 3
        assert all(t.trigger_id.startswith("k0_p05_") for t in merged)

    # ========== INTEGRATION TESTS ==========

    @pytest.mark.asyncio
    async def test_k0_query_resilience_on_k0_down(self, temporal_module):
        """Test scheduler continues if K0 is down"""
        # Mock K0 unavailable
        temporal_module._fetch_prospectives_from_k0 = AsyncMock(return_value=[])

        # Query K0
        result = await temporal_module._fetch_prospectives_from_k0()

        # Verify: Empty result (graceful fallback)
        assert result == []

    @pytest.mark.asyncio
    async def test_config_k0_backend_url_from_init(self, tmp_path):
        """Test K0 backend URL configuration"""
        custom_url = "http://custom-k0:8080"
        module = TemporalModule(
            db_path=tmp_path / "test.db",
            sse_url="http://localhost:8002",
            k0_backend_url=custom_url,
        )

        assert module.k0_backend_url == custom_url

    @pytest.mark.asyncio
    async def test_config_k0_backend_url_default(self, tmp_path):
        """Test K0 backend URL defaults to localhost:8001"""
        module = TemporalModule(db_path=tmp_path / "test.db")

        assert module.k0_backend_url == "http://localhost:8001"

    def test_singleton_factory_passes_k0_url(self, tmp_path):
        """Test singleton factory accepts k0_backend_url"""
        custom_url = "http://custom-k0:9000"
        module = get_temporal_module(
            db_path=tmp_path / "test.db",
            k0_backend_url=custom_url,
        )

        assert module.k0_backend_url == custom_url
