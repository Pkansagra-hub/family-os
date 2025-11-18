"""
Tests for M01: hippocampus.pattern_separate

Tests cover:
- Unit tests: SimHash/MinHash determinism, similarity, error handling
- Integration tests: Full envelope processing, idempotency, performance
- Performance validation: P95 latency <15ms

Run: pytest tests/k0/modules/hippocampus/test_pattern_separate.py -v
"""

import json
import time
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from k0.modules.hippocampus import pattern_separate

# ========== Test Fixtures ==========


@pytest.fixture
def mock_context():
    """Create mock PipelineContext with logger and trace_id."""
    context = MagicMock()
    context.logger = MagicMock()
    context.trace_id = "test-trace-id-12345"
    return context


@pytest.fixture
def sample_envelope():
    """Create sample envelope matching cognitive.memory.write.committed.v1 schema."""
    return {
        "cognitive_trace_id": "11111111-2222-3333-4444-555555555555",
        "tenant_id": "family-smith",
        "space_id": "personal:dad",
        "topic": "memory.episodic.formation",
        "actor_id": "person_dad",
        "device_id": "device-dad-phone",
        "band": "AMBER",
        "ts": "2025-11-16T18:00:00Z",
        "body": {
            "text": "We had dinner at Olive Garden with Mom and it was great",
            "participants": ["person_dad", "person_mom"],
            "location_name": "Olive Garden, Market St",
            "activity_type": "dinner",
            "event_time": "2025-11-16T18:00:00Z",
        },
    }


@pytest.fixture
def mock_message(sample_envelope):
    """Create mock BusMessage with envelope payload."""
    message = MagicMock()
    message.payload = json.dumps(sample_envelope)
    message.trace_id = "test-trace-id-12345"
    return message


# ========== Unit Tests ==========


@pytest.mark.asyncio
async def test_simhash_deterministic(mock_message, mock_context):
    """SimHash must be deterministic (same input → same hash)."""
    # Run twice with same envelope
    result1 = await pattern_separate.run(mock_message, mock_context, hash_seed=42)
    result2 = await pattern_separate.run(mock_message, mock_context, hash_seed=42)

    assert result1["simhash_hex"] == result2["simhash_hex"]
    assert len(result1["simhash_hex"]) == 16  # 64-bit hex = 16 chars


@pytest.mark.asyncio
async def test_simhash_similarity(mock_context):
    """SimHash should produce similar hashes for similar text."""
    # Create two similar messages
    message1 = MagicMock()
    message1.payload = json.dumps(
        {
            "body": {
                "text": "We had dinner at Olive Garden",
                "participants": ["person_dad", "person_mom"],
            }
        }
    )
    message1.trace_id = "trace1"

    message2 = MagicMock()
    message2.payload = json.dumps(
        {
            "body": {
                "text": "We had dinner at Olive Garden with family",  # Slight variation
                "participants": ["person_dad", "person_mom"],
            }
        }
    )
    message2.trace_id = "trace2"

    result1 = await pattern_separate.run(message1, mock_context, hash_seed=42)
    result2 = await pattern_separate.run(message2, mock_context, hash_seed=42)

    # Compute Hamming distance
    hash1 = int(result1["simhash_hex"], 16)
    hash2 = int(result2["simhash_hex"], 16)
    hamming_distance = bin(hash1 ^ hash2).count("1")

    # Similar text should have low Hamming distance (≤20 bits difference for very similar text)
    assert hamming_distance <= 20, f"Hamming distance {hamming_distance} too high for similar text"


@pytest.mark.asyncio
async def test_minhash_deterministic(mock_message, mock_context):
    """MinHash must be deterministic (same input → same signature)."""
    result1 = await pattern_separate.run(
        mock_message, mock_context, hash_seed=42, minhash_permutations=32
    )
    result2 = await pattern_separate.run(
        mock_message, mock_context, hash_seed=42, minhash_permutations=32
    )

    minhash1 = json.loads(result1["minhash32"])
    minhash2 = json.loads(result2["minhash32"])

    assert minhash1 == minhash2
    assert len(minhash1) == 32  # 32 permutations


@pytest.mark.asyncio
async def test_minhash_collision_rate(mock_context):
    """Different texts should produce different MinHash signatures."""
    messages = []
    for i in range(10):
        msg = MagicMock()
        msg.payload = json.dumps({"body": {"text": f"Unique text content number {i}"}})
        msg.trace_id = f"trace{i}"
        messages.append(msg)

    signatures = []
    for msg in messages:
        result = await pattern_separate.run(
            msg, mock_context, hash_seed=42, minhash_permutations=32
        )
        signatures.append(json.loads(result["minhash32"]))

    # All signatures should be unique
    unique_signatures = [tuple(sig) for sig in signatures]
    assert (
        len(set(unique_signatures)) == 10
    ), "MinHash signatures should be unique for different texts"


@pytest.mark.asyncio
async def test_empty_text_handling(mock_context):
    """Module should handle empty text gracefully."""
    message = MagicMock()
    message.payload = json.dumps({"body": {}})  # No text field
    message.trace_id = "test-trace"

    result = await pattern_separate.run(message, mock_context, hash_seed=42)

    # Should return default fingerprint
    assert result["simhash_hex"] == "0000000000000000"
    assert json.loads(result["minhash32"]) == [0] * 32


@pytest.mark.asyncio
async def test_unicode_text_handling(mock_context):
    """Module should handle Unicode text correctly."""
    message = MagicMock()
    message.payload = json.dumps(
        {
            "body": {
                "text": "Hello 世界 🌍 Здравствуй мир",  # Mixed scripts + emoji
                "participants": ["person_1"],
            }
        }
    )
    message.trace_id = "test-trace"

    result = await pattern_separate.run(message, mock_context, hash_seed=42)

    # Should not crash and should produce valid fingerprint
    assert len(result["simhash_hex"]) == 16
    assert len(json.loads(result["minhash32"])) == 32


@pytest.mark.asyncio
async def test_output_schema_valid(mock_message, mock_context):
    """Output must match expected schema."""
    result = await pattern_separate.run(mock_message, mock_context, hash_seed=42)

    # Required fields
    assert "simhash_hex" in result
    assert "minhash32" in result
    assert "fingerprint_computed_at_utc" in result

    # Field types
    assert isinstance(result["simhash_hex"], str)
    assert isinstance(result["minhash32"], str)  # JSON string
    assert isinstance(result["fingerprint_computed_at_utc"], str)

    # Field formats
    assert len(result["simhash_hex"]) == 16  # 64-bit hex
    minhash = json.loads(result["minhash32"])
    assert isinstance(minhash, list)
    assert len(minhash) == 32  # Default permutations

    # Timestamp format (ISO 8601)
    datetime.fromisoformat(result["fingerprint_computed_at_utc"].replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_malformed_envelope_error(mock_context):
    """Module should raise ValueError for malformed envelope."""
    message = MagicMock()
    message.payload = "not valid json"
    message.trace_id = "test-trace"

    with pytest.raises(ValueError, match="Invalid envelope payload"):
        await pattern_separate.run(message, mock_context)

    # Logger should have recorded error
    mock_context.logger.error.assert_called_once()


# ========== Integration Tests ==========


@pytest.mark.asyncio
async def test_process_full_envelope(sample_envelope, mock_context):
    """End-to-end test with full envelope."""
    message = MagicMock()
    message.payload = json.dumps(sample_envelope)
    message.trace_id = "test-trace-full"

    result = await pattern_separate.run(
        message, mock_context, hash_seed=42, minhash_permutations=32
    )

    # Verify fingerprinting used all components
    # Text: "we had dinner at olive garden with mom and it was great"
    # Participants: ["person_dad", "person_mom"]
    # Location: "olive garden, market st"
    # Activity: "dinner"
    # Time: "2025-11-16T18" (hour bucket)

    assert result["simhash_hex"] != "0000000000000000"  # Non-default
    minhash = json.loads(result["minhash32"])
    assert all(h != 0 for h in minhash)  # All permutations computed

    # Logger should log completion
    mock_context.logger.info.assert_called_once()


@pytest.mark.asyncio
async def test_idempotency(mock_message, mock_context):
    """Processing same envelope twice should produce identical fingerprints (timestamps may differ)."""
    result1 = await pattern_separate.run(mock_message, mock_context, hash_seed=42)
    result2 = await pattern_separate.run(mock_message, mock_context, hash_seed=42)
    result3 = await pattern_separate.run(mock_message, mock_context, hash_seed=42)

    # Fingerprints must be identical
    assert result1["simhash_hex"] == result2["simhash_hex"] == result3["simhash_hex"]
    assert result1["minhash32"] == result2["minhash32"] == result3["minhash32"]
    # Note: fingerprint_computed_at_utc will differ (real-time timestamp)


@pytest.mark.asyncio
async def test_trace_context_propagated(mock_message, mock_context):
    """Trace ID should be included in logs."""
    await pattern_separate.run(mock_message, mock_context, hash_seed=42)

    # Verify logger was called with trace_id
    log_calls = mock_context.logger.info.call_args_list
    assert len(log_calls) > 0
    log_extra = log_calls[0].kwargs.get("extra", {})
    assert log_extra.get("trace_id") == "test-trace-id-12345"


# ========== Performance Tests ==========


@pytest.mark.asyncio
@pytest.mark.slow
async def test_performance_under_15ms(sample_envelope, mock_context):
    """P95 latency must be under 15ms (contract requirement)."""
    message = MagicMock()
    message.payload = json.dumps(sample_envelope)
    message.trace_id = "perf-test"

    latencies = []
    iterations = 100

    for _ in range(iterations):
        start = time.perf_counter()
        await pattern_separate.run(message, mock_context, hash_seed=42, minhash_permutations=32)
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(elapsed_ms)

    # Calculate P95
    latencies.sort()
    p95 = latencies[94]  # 95th percentile
    p99 = latencies[98]  # 99th percentile
    median = latencies[49]

    print(f"\nPerformance metrics ({iterations} iterations):")
    print(f"  Median: {median:.2f}ms")
    print(f"  P95:    {p95:.2f}ms")
    print(f"  P99:    {p99:.2f}ms")

    # Contract requirement: P95 ≤ 15ms
    assert p95 < 15, f"P95 latency {p95:.2f}ms exceeds 15ms budget"
    assert p99 < 25, f"P99 latency {p99:.2f}ms exceeds 25ms budget"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_performance_large_text(mock_context):
    """Performance with large text (1000 words)."""
    large_text = " ".join([f"word{i}" for i in range(1000)])
    message = MagicMock()
    message.payload = json.dumps({"body": {"text": large_text}})
    message.trace_id = "perf-large"

    start = time.perf_counter()
    result = await pattern_separate.run(
        message, mock_context, hash_seed=42, minhash_permutations=32
    )
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert result["simhash_hex"] != "0000000000000000"
    # Should still be under 50ms even for large text
    assert elapsed_ms < 50, f"Large text latency {elapsed_ms:.2f}ms exceeds 50ms"


# ========== Helper Function Tests ==========


def test_generate_shingles():
    """Test shingle generation with various inputs."""
    # Normal case
    shingles = pattern_separate._generate_shingles("hello world foo bar", k=2)
    assert shingles == {"hello world", "world foo", "foo bar"}

    # Short text (< k)
    shingles = pattern_separate._generate_shingles("hello", k=3)
    assert shingles == {"hello"}

    # Empty text
    shingles = pattern_separate._generate_shingles("", k=3)
    assert shingles == set()

    # k=1 (unigrams)
    shingles = pattern_separate._generate_shingles("a b c", k=1)
    assert shingles == {"a", "b", "c"}


def test_extract_text_for_fingerprinting():
    """Test text extraction from envelope."""
    envelope = {
        "body": {
            "text": "Hello World",
            "participants": ["person_b", "person_a"],  # Should be sorted
            "location_name": "Office",
            "activity_type": "meeting",
            "event_time": "2025-11-16T18:30:00Z",
        }
    }

    text = pattern_separate._extract_text_for_fingerprinting(envelope)

    # Should contain all components
    assert "hello world" in text  # Text (lowercased)
    assert "person_a" in text  # Participants (sorted)
    assert "person_b" in text
    assert "office" in text  # Location
    assert "meeting" in text  # Activity
    assert "2025-11-16T18" in text  # Hour bucket


def test_extract_text_partial_envelope():
    """Test text extraction with missing fields."""
    envelope = {
        "body": {
            "text": "Only text here",
            # No participants, location, activity, event_time
        }
    }

    text = pattern_separate._extract_text_for_fingerprinting(envelope)

    assert "only text here" in text
    assert text.strip() == "only text here"
