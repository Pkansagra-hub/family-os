"""
Comprehensive test suite for M10 Ingress Classify module.

Test Categories:
1. Ingress Topic Classification (8 tests)
2. Activity Type Classification (12 tests)
3. Content Type Determination (6 tests)
4. Ingress Source Inference (8 tests)
5. End-to-End Classification (6 tests)
6. Performance Tests (3 tests)
7. Metrics Tests (2 tests)
8. Edge Cases (5 tests)

Total: 50 tests
"""

import json
import time
from unittest.mock import Mock

import pytest

# Direct import to avoid __init__.py conflicts
from k0.modules.context.ingress_classify import (
    classify_activity_type,
    classify_ingress,
    classify_ingress_topic,
    determine_content_type,
    get_metrics,
    infer_ingress_source,
    reset_metrics,
    run,
)


# Module alias for shorter calls
class ic:
    """Module alias for ingress_classify functions."""

    classify_ingress_topic = staticmethod(classify_ingress_topic)
    classify_activity_type = staticmethod(classify_activity_type)
    determine_content_type = staticmethod(determine_content_type)
    infer_ingress_source = staticmethod(infer_ingress_source)
    classify_ingress = staticmethod(classify_ingress)
    run = staticmethod(run)
    get_metrics = staticmethod(get_metrics)
    reset_metrics = staticmethod(reset_metrics)


# =============================================================================
# MOCK CLASSES FOR PHASE 2 SIGNATURE
# =============================================================================


class MockMessage:
    """Mock BusMessage for testing Phase 2 signature."""

    def __init__(self, payload: dict, trace_id: str = "test_trace"):
        self.payload = json.dumps(payload) if isinstance(payload, dict) else payload
        self.trace_id = trace_id
        self.offset = 0


class MockContext:
    """Mock PipelineContext for testing Phase 2 signature."""

    def __init__(self):
        self.logger = Mock()
        self.syscalls = Mock()
        self.config = {}


def make_test_call(envelope: dict, **config) -> tuple:
    """Helper to create message, context, and config for test calls."""
    message = MockMessage(payload=envelope, trace_id="test_trace")
    context = MockContext()
    return message, context, config


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module metrics before each test."""
    ic.reset_metrics()
    yield
    ic.reset_metrics()


@pytest.fixture
def sample_envelope_write():
    """Sample envelope for write channel."""
    return {
        "topic": "cognitive.memory.write.v1",
        "body": {"text": "Had breakfast at 8am with family"},
        "metadata": {"user_agent": "FamilyOS/2.3.1 (iOS 17.1; iPhone15,2)"},
        "device_id": "device-dad-phone",
    }


@pytest.fixture
def sample_envelope_photo():
    """Sample envelope for photo channel."""
    return {
        "topic": "cognitive.memory.photo.v1",
        "body": {"text": "Dinner receipt", "has_photo": True},
        "metadata": {"user_agent": "FamilyOS/2.3.1 (iOS 17.1; iPhone15,2)"},
        "device_id": "device-mom-phone",
    }


@pytest.fixture
def sample_envelope_voice():
    """Sample envelope for voice channel."""
    return {
        "topic": "cognitive.memory.voice.v1",
        "body": {"text": "Voice memo transcription: Team meeting at 3pm"},
        "metadata": {"user_agent": "FamilyOS/2.3.1 (iOS 17.1; iPhone15,2)"},
        "device_id": "device-dad-phone",
    }


@pytest.fixture
def sample_envelope_import():
    """Sample envelope for import channel."""
    return {
        "topic": "cognitive.memory.import.v1",
        "body": {"text": "Bulk import from Google Calendar", "is_structured": True},
        "metadata": {"source": "connector-gcal", "is_structured": True},
        "device_id": "api-connector-gcal",
    }


# =============================================================================
# TEST GROUP 1: Ingress Topic Classification (8 tests)
# =============================================================================


class TestIngressTopicClassification:
    """Test ingress topic classification from event topics."""

    def test_classify_write_explicit(self):
        """Test write classification with explicit topic."""
        assert ic.classify_ingress_topic("cognitive.memory.write") == "write"

    def test_classify_write_versioned(self):
        """Test write classification with versioned topic."""
        assert ic.classify_ingress_topic("cognitive.memory.write.v1") == "write"

    def test_classify_write_committed(self):
        """Test write classification with committed event."""
        assert ic.classify_ingress_topic("cognitive.memory.write.committed.v1") == "write"

    def test_classify_photo(self):
        """Test photo classification."""
        assert ic.classify_ingress_topic("cognitive.memory.photo.v1") == "photo"

    def test_classify_voice(self):
        """Test voice classification."""
        assert ic.classify_ingress_topic("cognitive.memory.voice.v1") == "voice"

    def test_classify_import(self):
        """Test import classification."""
        assert ic.classify_ingress_topic("cognitive.memory.import.v1") == "import"

    def test_classify_unknown_defaults_write(self):
        """Test unknown topic defaults to write."""
        assert ic.classify_ingress_topic("unknown.topic.v1") == "write"

    def test_classify_empty_defaults_write(self):
        """Test empty topic defaults to write."""
        assert ic.classify_ingress_topic("") == "write"


# =============================================================================
# TEST GROUP 2: Activity Type Classification (12 tests)
# =============================================================================


class TestActivityTypeClassification:
    """Test activity type classification from text keywords."""

    def test_classify_meal_breakfast(self):
        """Test meal classification for breakfast."""
        assert ic.classify_activity_type("Had breakfast at 8am") == "meal"

    def test_classify_meal_lunch(self):
        """Test meal classification for lunch."""
        assert ic.classify_activity_type("Lunch meeting at restaurant") == "meal"

    def test_classify_meal_dinner(self):
        """Test meal classification for dinner."""
        assert ic.classify_activity_type("Ate dinner with family") == "meal"

    def test_classify_milestone_birthday(self):
        """Test milestone classification for birthday."""
        assert ic.classify_activity_type("Celebrated birthday party today") == "milestone"

    def test_classify_milestone_graduation(self):
        """Test milestone classification for graduation."""
        assert ic.classify_activity_type("Graduation ceremony this morning") == "milestone"

    def test_classify_work_meeting(self):
        """Test work classification for meeting."""
        assert ic.classify_activity_type("Client meeting at 3pm") == "work"

    def test_classify_social_party(self):
        """Test social classification for party."""
        assert ic.classify_activity_type("Family reunion party") == "social"

    def test_classify_conversation_chat(self):
        """Test conversation classification for chat."""
        assert ic.classify_activity_type("Talked with friend on phone") == "conversation"

    def test_classify_routine_shower(self):
        """Test routine classification for shower."""
        assert ic.classify_activity_type("Morning shower routine") == "routine"

    def test_classify_unknown_no_keywords(self):
        """Test unknown classification when no keywords match."""
        assert ic.classify_activity_type("Random note without keywords") == "unknown"

    def test_classify_priority_meal_over_social(self):
        """Test meal has higher priority than social."""
        # "dinner party" should be "meal" (not "social")
        assert ic.classify_activity_type("Dinner party with friends") == "meal"

    def test_classify_empty_text(self):
        """Test classification with empty text."""
        assert ic.classify_activity_type("") == "unknown"


# =============================================================================
# TEST GROUP 3: Content Type Determination (6 tests)
# =============================================================================


class TestContentTypeDetermination:
    """Test content type determination (episodic/semantic/procedural)."""

    def test_determine_episodic_default(self):
        """Test episodic is default content type."""
        assert ic.determine_content_type({}) == "episodic"

    def test_determine_episodic_normal_event(self):
        """Test episodic for normal time-bound event."""
        body = {"text": "Had breakfast at 8am"}
        assert ic.determine_content_type(body) == "episodic"

    def test_determine_semantic_explicit_marker(self):
        """Test semantic with explicit is_fact marker."""
        body = {"text": "Paris is the capital of France", "is_fact": True}
        assert ic.determine_content_type(body) == "semantic"

    def test_determine_semantic_knowledge_marker(self):
        """Test semantic with knowledge_base marker."""
        body = {"text": "Definition of episodic memory", "is_knowledge_base_entry": True}
        assert ic.determine_content_type(body) == "semantic"

    def test_determine_procedural_recipe_marker(self):
        """Test procedural with recipe marker."""
        body = {"text": "How to make pasta", "is_recipe": True}
        assert ic.determine_content_type(body) == "procedural"

    def test_determine_procedural_how_to_marker(self):
        """Test procedural with how_to marker."""
        body = {"text": "Steps to fix the sink", "is_how_to": True}
        assert ic.determine_content_type(body) == "procedural"


# =============================================================================
# TEST GROUP 4: Ingress Source Inference (8 tests)
# =============================================================================


class TestIngressSourceInference:
    """Test ingress source inference from metadata and device_id."""

    def test_infer_mobile_app_iphone(self):
        """Test mobile_app inference from iPhone user-agent."""
        metadata = {"user_agent": "FamilyOS/2.3.1 (iOS 17.1; iPhone15,2)"}
        assert ic.infer_ingress_source(metadata) == "mobile_app"

    def test_infer_mobile_app_android(self):
        """Test mobile_app inference from Android user-agent."""
        metadata = {"user_agent": "FamilyOS/2.3.1 (Android 14; Pixel 8)"}
        assert ic.infer_ingress_source(metadata) == "mobile_app"

    def test_infer_web_app_mozilla(self):
        """Test web_app inference from Mozilla user-agent."""
        metadata = {"user_agent": "Mozilla/5.0 (Macintosh) FamilyOS/2.3.1"}
        assert ic.infer_ingress_source(metadata) == "web_app"

    def test_infer_web_app_chrome(self):
        """Test web_app inference from Chrome user-agent."""
        metadata = {"user_agent": "Chrome/120.0 FamilyOS/2.3.1"}
        assert ic.infer_ingress_source(metadata) == "web_app"

    def test_infer_api_source_hint(self):
        """Test api inference from source hint."""
        metadata = {"source": "api-scheduled"}
        assert ic.infer_ingress_source(metadata) == "api"

    def test_infer_connector_source_hint(self):
        """Test connector inference from source hint."""
        metadata = {"source": "connector-gcal"}
        assert ic.infer_ingress_source(metadata) == "connector"

    def test_infer_connector_device_id(self):
        """Test connector inference from device_id."""
        metadata = {}
        device_id = "api-connector-fitbit"
        assert ic.infer_ingress_source(metadata, device_id) == "connector"

    def test_infer_mobile_app_default(self):
        """Test mobile_app as default when no patterns match."""
        metadata = {"user_agent": "CustomClient/1.0"}
        assert ic.infer_ingress_source(metadata) == "mobile_app"


# =============================================================================
# TEST GROUP 5: End-to-End Classification (6 tests)
# =============================================================================


class TestEndToEndClassification:
    """Test complete ingress classification with async run()."""

    @pytest.mark.asyncio
    async def test_run_with_write_envelope(self, sample_envelope_write):
        """Test complete classification with write envelope."""
        message, context, config = make_test_call(sample_envelope_write)
        result = await ic.run(message, context, **config)

        assert result["ingress_topic"] == "write"
        assert result["activity_type"] == "meal"  # "breakfast" keyword
        assert result["content_type"] == "episodic"
        assert result["ingress_source"] == "mobile_app"
        assert result["is_user_initiated"] is True
        assert result["is_structured"] is False
        assert "ingress_classified_at_utc" in result

    @pytest.mark.asyncio
    async def test_run_with_photo_envelope(self, sample_envelope_photo):
        """Test complete classification with photo envelope."""
        message, context, config = make_test_call(sample_envelope_photo)
        result = await ic.run(message, context, **config)

        assert result["ingress_topic"] == "photo"
        assert result["activity_type"] == "meal"  # "dinner" keyword
        assert result["ingress_source"] == "mobile_app"

    @pytest.mark.asyncio
    async def test_run_with_voice_envelope(self, sample_envelope_voice):
        """Test complete classification with voice envelope."""
        message, context, config = make_test_call(sample_envelope_voice)
        result = await ic.run(message, context, **config)

        assert result["ingress_topic"] == "voice"
        assert result["activity_type"] == "work"  # "meeting" keyword
        assert result["is_user_initiated"] is True

    @pytest.mark.asyncio
    async def test_run_with_import_envelope(self, sample_envelope_import):
        """Test complete classification with import envelope."""
        message, context, config = make_test_call(sample_envelope_import)
        result = await ic.run(message, context, **config)

        assert result["ingress_topic"] == "import"
        assert result["ingress_source"] == "connector"
        assert result["is_user_initiated"] is False  # Import is not user-initiated
        assert result["is_structured"] is True

    @pytest.mark.asyncio
    async def test_run_idempotency(self, sample_envelope_write):
        """Test idempotency: same envelope → same result."""
        message, context, config = make_test_call(sample_envelope_write)
        result1 = await ic.run(message, context, **config)
        message2, context2, config2 = make_test_call(sample_envelope_write)
        result2 = await ic.run(message2, context2, **config2)

        # Timestamps will differ, so exclude them
        for key in ["ingress_topic", "activity_type", "content_type", "ingress_source"]:
            assert result1[key] == result2[key]

    @pytest.mark.asyncio
    async def test_run_with_minimal_envelope(self):
        """Test classification with minimal envelope (all defaults)."""
        envelope = {"topic": "unknown.topic", "body": {}, "metadata": {}}
        message, context, config = make_test_call(envelope)
        result = await ic.run(message, context, **config)

        assert result["ingress_topic"] == "write"  # Default
        assert result["activity_type"] == "unknown"  # No keywords
        assert result["content_type"] == "episodic"  # Default
        assert result["ingress_source"] == "mobile_app"  # Default


# =============================================================================
# TEST GROUP 6: Performance Tests (3 tests)
# =============================================================================


class TestPerformance:
    """Test performance against <3ms P95 budget."""

    @pytest.mark.asyncio
    async def test_run_latency_batch(self, sample_envelope_write):
        """Test async run() latency for batch of 1000 classifications (P95 < 3ms)."""
        latencies = []

        for _ in range(1000):
            message, context, config = make_test_call(sample_envelope_write)
            start = time.perf_counter()
            await ic.run(message, context, **config)
            end = time.perf_counter()
            latencies.append((end - start) * 1000)  # Convert to milliseconds

        latencies.sort()
        p50 = latencies[int(len(latencies) * 0.50)]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]

        print("\n📊 Latency Results (n=1000):")
        print(f"   P50: {p50:.4f}ms")
        print(f"   P95: {p95:.4f}ms (budget: <3ms)")
        print(f"   P99: {p99:.4f}ms")

        # Performance assertion
        assert p95 < 3.0, f"P95 latency {p95:.4f}ms exceeds 3ms budget"

    @pytest.mark.asyncio
    async def test_throughput_single_thread(self, sample_envelope_write):
        """Test throughput (target: >300 ops/sec single-threaded)."""
        num_ops = 1000
        start = time.perf_counter()

        for _ in range(num_ops):
            message, context, config = make_test_call(sample_envelope_write)
            await ic.run(message, context, **config)

        elapsed = time.perf_counter() - start
        throughput = num_ops / elapsed

        print(f"\n🚀 Throughput: {throughput:,.0f} ops/sec")

        # Throughput assertion (expect >300 ops/sec)
        assert throughput > 300, f"Throughput {throughput:.0f} ops/sec below 300 target"

    def test_classify_ingress_latency(self):
        """Test classify_ingress() latency (<2ms for keyword matching)."""
        latencies = []

        for _ in range(1000):
            start = time.perf_counter()
            ic.classify_ingress(
                topic="cognitive.memory.write.v1",
                body={"text": "Had breakfast at 8am with family"},
                metadata={"user_agent": "FamilyOS/2.3.1 (iOS 17.1; iPhone15,2)"},
                device_id="device-dad-phone",
            )
            end = time.perf_counter()
            latencies.append((end - start) * 1000)

        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]

        print(f"\n⚡ classify_ingress() P95: {p95:.4f}ms")

        # Should be < 2ms for keyword matching
        assert p95 < 2.0, f"P95 latency {p95:.4f}ms exceeds 2ms"


# =============================================================================
# TEST GROUP 7: Metrics Tests (2 tests)
# =============================================================================


class TestMetrics:
    """Test metrics tracking for observability."""

    @pytest.mark.asyncio
    async def test_metrics_tracking(
        self, sample_envelope_write, sample_envelope_photo, sample_envelope_voice
    ):
        """Test metrics increment correctly for different channels and activities."""
        ic.reset_metrics()

        # Classify 3 writes, 2 photos, 1 voice
        for _ in range(3):
            message, context, config = make_test_call(sample_envelope_write)
            await ic.run(message, context, **config)
        for _ in range(2):
            message, context, config = make_test_call(sample_envelope_photo)
            await ic.run(message, context, **config)
        message, context, config = make_test_call(sample_envelope_voice)
        await ic.run(message, context, **config)

        metrics = ic.get_metrics()

        assert metrics["total_classifications"] == 6
        assert metrics["ingress_write"] == 3
        assert metrics["ingress_photo"] == 2
        assert metrics["ingress_voice"] == 1
        assert metrics["activity_meal"] == 5  # 3 writes + 2 photos (all meal keywords)
        assert metrics["activity_work"] == 1  # 1 voice (meeting keyword)
        assert metrics["content_episodic"] == 6  # All default to episodic
        assert metrics["source_mobile_app"] == 6  # All from mobile

    def test_reset_metrics(self):
        """Test metrics reset works correctly."""
        # Classify some events
        ic.classify_ingress("cognitive.memory.write.v1", {"text": "Test"}, {})
        ic.classify_ingress("cognitive.memory.photo.v1", {"text": "Test"}, {})

        # Reset
        ic.reset_metrics()

        metrics = ic.get_metrics()
        assert metrics["total_classifications"] == 0
        assert metrics["ingress_write"] == 0
        assert metrics["ingress_photo"] == 0


# =============================================================================
# TEST GROUP 8: Edge Cases (5 tests)
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_run_with_missing_topic(self):
        """Test handling of missing topic (should default to write)."""
        envelope = {"body": {"text": "Test"}, "metadata": {}}
        message, context, config = make_test_call(envelope)
        result = await ic.run(message, context, **config)

        assert result["ingress_topic"] == "write"

    @pytest.mark.asyncio
    async def test_run_with_empty_body(self):
        """Test handling of empty body (should use defaults)."""
        envelope = {"topic": "cognitive.memory.write.v1", "body": {}, "metadata": {}}
        message, context, config = make_test_call(envelope)
        result = await ic.run(message, context, **config)

        assert result["activity_type"] == "unknown"  # No text to classify
        assert result["content_type"] == "episodic"  # Default

    @pytest.mark.asyncio
    async def test_run_with_complex_text(self):
        """Test classification with complex multi-activity text."""
        envelope = {
            "topic": "cognitive.memory.write.v1",
            "body": {
                "text": "Had breakfast meeting with client at restaurant to discuss project deadline"
            },
            "metadata": {},
        }
        message, context, config = make_test_call(envelope)
        result = await ic.run(message, context, **config)

        # Should classify as "meal" (highest priority keyword: breakfast)
        assert result["activity_type"] == "meal"

    def test_classify_case_insensitive(self):
        """Test activity classification is case-insensitive."""
        assert ic.classify_activity_type("HAD BREAKFAST") == "meal"
        assert ic.classify_activity_type("Birthday Party") == "milestone"
        assert ic.classify_activity_type("CLIENT MEETING") == "work"

    @pytest.mark.asyncio
    async def test_concurrent_classification(self, sample_envelope_write, sample_envelope_photo):
        """Test concurrent classification (thread-safety check)."""
        import asyncio

        tasks = []
        for _ in range(50):
            message_w, context_w, config_w = make_test_call(sample_envelope_write)
            tasks.append(ic.run(message_w, context_w, **config_w))
            message_p, context_p, config_p = make_test_call(sample_envelope_photo)
            tasks.append(ic.run(message_p, context_p, **config_p))

        results = await asyncio.gather(*tasks)

        # Verify all 100 results returned
        assert len(results) == 100

        # Verify metrics are correct (50 writes + 50 photos)
        metrics = ic.get_metrics()
        assert metrics["total_classifications"] == 100
        assert metrics["ingress_write"] == 50
        assert metrics["ingress_photo"] == 50


# =============================================================================
# RUN ALL TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
