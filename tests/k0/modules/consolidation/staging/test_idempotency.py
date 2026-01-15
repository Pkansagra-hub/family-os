"""
Unit tests for IdempotencyKeyGenerator — Issue 5.1.5

Tests the deterministic idempotency key generation for R6 staged writes,
R7 truth writes, and R8 event emissions.

Spec Reference:
    - Dossier §12.2.3 (Idempotency Key Design)
    - M5_EXECUTION.md Issue 5.1.5
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.staging.idempotency import (
    IdempotencyKeyGenerator,
    ParsedKey,
    extract_cycle_ulid,
    keys_same_cycle,
    parse_idempotency_key,
    validate_idempotency_key,
)

# =============================================================================
# Test Fixtures
# =============================================================================

# Valid 26-character ULID for testing (Crockford base32: 0-9, A-Z excluding I, L, O, U)
TEST_ULID = "01HXYZ123456789ABCDEFGHJKM"  # Exactly 26 chars


@pytest.fixture
def generator() -> IdempotencyKeyGenerator:
    """Provide a generator with test ULID."""
    return IdempotencyKeyGenerator(cycle_ulid=TEST_ULID)


# =============================================================================
# Test: IdempotencyKeyGenerator Initialization
# =============================================================================


class TestGeneratorInit:
    """Tests for generator initialization."""

    def test_init_with_valid_ulid(self):
        """Initialize with valid ULID."""
        gen = IdempotencyKeyGenerator(cycle_ulid=TEST_ULID)
        assert gen.cycle_ulid == TEST_ULID

    def test_init_requires_ulid(self):
        """Empty ULID raises ValueError."""
        with pytest.raises(ValueError, match="cycle_ulid is required"):
            IdempotencyKeyGenerator(cycle_ulid="")

    def test_init_validates_ulid_length(self):
        """Invalid ULID length raises ValueError."""
        with pytest.raises(ValueError, match="Invalid ULID length"):
            IdempotencyKeyGenerator(cycle_ulid="SHORT")


# =============================================================================
# Test: for_event_update (R6)
# =============================================================================


class TestForEventUpdate:
    """Tests for R6 event update keys."""

    def test_basic_event_update_key(self, generator: IdempotencyKeyGenerator):
        """Generate basic event update key."""
        key = generator.for_event_update("evt_001")

        assert key == f"p03:staging:{TEST_ULID}:evt_001"

    def test_event_update_key_format(self, generator: IdempotencyKeyGenerator):
        """Key format matches dossier spec."""
        key = generator.for_event_update("01HABC789")

        # Format: p03:staging:{cycle_ulid}:{event_id}
        assert key.startswith("p03:staging:")
        assert TEST_ULID in key
        assert key.endswith(":01HABC789")

    def test_event_update_requires_event_id(self, generator: IdempotencyKeyGenerator):
        """Empty event_id raises ValueError."""
        with pytest.raises(ValueError, match="event_id is required"):
            generator.for_event_update("")

    def test_event_update_deterministic(self, generator: IdempotencyKeyGenerator):
        """Same input produces same key."""
        key1 = generator.for_event_update("evt_001")
        key2 = generator.for_event_update("evt_001")

        assert key1 == key2

    def test_event_update_unique_per_event(self, generator: IdempotencyKeyGenerator):
        """Different events produce different keys."""
        key1 = generator.for_event_update("evt_001")
        key2 = generator.for_event_update("evt_002")

        assert key1 != key2


# =============================================================================
# Test: for_truth_write (R7)
# =============================================================================


class TestForTruthWrite:
    """Tests for R7 truth write keys."""

    def test_basic_truth_write_key(self, generator: IdempotencyKeyGenerator):
        """Generate basic truth write key."""
        key = generator.for_truth_write("st_epi", "epi-001")

        assert key == f"p03:write:{TEST_ULID}:st_epi:epi-001"

    def test_truth_write_key_format(self, generator: IdempotencyKeyGenerator):
        """Key format matches dossier spec."""
        key = generator.for_truth_write("st_sem", "sem-123")

        # Format: p03:write:{cycle_ulid}:{table}:{record_id}
        assert key.startswith("p03:write:")
        assert TEST_ULID in key
        assert ":st_sem:" in key
        assert key.endswith(":sem-123")

    def test_truth_write_requires_table(self, generator: IdempotencyKeyGenerator):
        """Empty table raises ValueError."""
        with pytest.raises(ValueError, match="table is required"):
            generator.for_truth_write("", "rec-001")

    def test_truth_write_requires_record_id(self, generator: IdempotencyKeyGenerator):
        """Empty record_id raises ValueError."""
        with pytest.raises(ValueError, match="record_id is required"):
            generator.for_truth_write("st_epi", "")

    @pytest.mark.parametrize(
        "table",
        [
            "st_epi",
            "st_sem",
            "st_procedural",
            "st_social",
            "st_prospective",
            "st_kg_dom",
            "st_kg_edges",
            "st_vec",
            "st_learning_queue",
        ],
    )
    def test_truth_write_all_layers(
        self,
        generator: IdempotencyKeyGenerator,
        table: str,
    ):
        """All truth layers produce valid keys."""
        key = generator.for_truth_write(table, "rec-001")

        assert f":{table}:" in key


# =============================================================================
# Test: for_event_emit (R8)
# =============================================================================


class TestForEventEmit:
    """Tests for R8 event emission keys."""

    def test_basic_event_emit_key(self, generator: IdempotencyKeyGenerator):
        """Generate basic event emit key."""
        key = generator.for_event_emit("p03.pattern.detected.v1", 42)

        assert key == f"p03:emit:{TEST_ULID}:p03.pattern.detected.v1:42"

    def test_event_emit_key_format(self, generator: IdempotencyKeyGenerator):
        """Key format matches dossier spec."""
        key = generator.for_event_emit("topic.name", 0)

        # Format: p03:emit:{cycle_ulid}:{topic}:{offset}
        assert key.startswith("p03:emit:")
        assert TEST_ULID in key
        assert ":topic.name:" in key

    def test_event_emit_requires_topic(self, generator: IdempotencyKeyGenerator):
        """Empty topic raises ValueError."""
        with pytest.raises(ValueError, match="topic is required"):
            generator.for_event_emit("", 0)

    def test_event_emit_requires_nonnegative_offset(self, generator: IdempotencyKeyGenerator):
        """Negative offset raises ValueError."""
        with pytest.raises(ValueError, match="offset must be non-negative"):
            generator.for_event_emit("topic", -1)

    def test_event_emit_zero_offset(self, generator: IdempotencyKeyGenerator):
        """Zero offset is valid."""
        key = generator.for_event_emit("topic", 0)

        assert key.endswith(":0")


# =============================================================================
# Test: for_batch_phase
# =============================================================================


class TestForBatchPhase:
    """Tests for batch phase keys."""

    def test_basic_batch_phase_key(self, generator: IdempotencyKeyGenerator):
        """Generate basic batch phase key."""
        key = generator.for_batch_phase("R1", ["evt_001", "evt_002"])

        assert key.startswith(f"p03:R1:{TEST_ULID}:")
        # Hash is 12 hex chars
        hash_part = key.split(":")[-1]
        assert len(hash_part) == 12
        assert all(c in "0123456789abcdef" for c in hash_part)

    def test_batch_phase_requires_phase(self, generator: IdempotencyKeyGenerator):
        """Empty phase raises ValueError."""
        with pytest.raises(ValueError, match="phase is required"):
            generator.for_batch_phase("", ["evt_001"])

    def test_batch_phase_requires_event_ids(self, generator: IdempotencyKeyGenerator):
        """Empty event_ids raises ValueError."""
        with pytest.raises(ValueError, match="event_ids is required"):
            generator.for_batch_phase("R1", [])

    def test_batch_phase_deterministic(self, generator: IdempotencyKeyGenerator):
        """Same events produce same key."""
        key1 = generator.for_batch_phase("R2", ["evt_001", "evt_002"])
        key2 = generator.for_batch_phase("R2", ["evt_001", "evt_002"])

        assert key1 == key2

    def test_batch_phase_order_independent(self, generator: IdempotencyKeyGenerator):
        """Different order produces same key (sorted internally)."""
        key1 = generator.for_batch_phase("R3", ["evt_001", "evt_002", "evt_003"])
        key2 = generator.for_batch_phase("R3", ["evt_003", "evt_001", "evt_002"])

        assert key1 == key2

    def test_batch_phase_different_events_different_key(self, generator: IdempotencyKeyGenerator):
        """Different events produce different keys."""
        key1 = generator.for_batch_phase("R1", ["evt_001", "evt_002"])
        key2 = generator.for_batch_phase("R1", ["evt_001", "evt_003"])

        assert key1 != key2


# =============================================================================
# Test: compute_batch_hash
# =============================================================================


class TestComputeBatchHash:
    """Tests for batch hash computation."""

    def test_hash_length(self):
        """Hash is 12 characters."""
        hash_val = IdempotencyKeyGenerator.compute_batch_hash(["evt_001"])

        assert len(hash_val) == 12

    def test_hash_is_hex(self):
        """Hash is valid hex string."""
        hash_val = IdempotencyKeyGenerator.compute_batch_hash(["evt_001", "evt_002"])

        assert all(c in "0123456789abcdef" for c in hash_val)

    def test_hash_deterministic(self):
        """Same input produces same hash."""
        hash1 = IdempotencyKeyGenerator.compute_batch_hash(["a", "b", "c"])
        hash2 = IdempotencyKeyGenerator.compute_batch_hash(["a", "b", "c"])

        assert hash1 == hash2

    def test_hash_order_independent(self):
        """Different order produces same hash."""
        hash1 = IdempotencyKeyGenerator.compute_batch_hash(["a", "b", "c"])
        hash2 = IdempotencyKeyGenerator.compute_batch_hash(["c", "a", "b"])

        assert hash1 == hash2

    def test_hash_different_content(self):
        """Different content produces different hash."""
        hash1 = IdempotencyKeyGenerator.compute_batch_hash(["a", "b"])
        hash2 = IdempotencyKeyGenerator.compute_batch_hash(["a", "c"])

        assert hash1 != hash2


# =============================================================================
# Test: for_outbox_event
# =============================================================================


class TestForOutboxEvent:
    """Tests for outbox event keys."""

    def test_basic_outbox_event_key(self, generator: IdempotencyKeyGenerator):
        """Generate basic outbox event key."""
        key = generator.for_outbox_event("topic.name", "evt_001")

        assert key == f"p03:emit:{TEST_ULID}:topic.name:evt_001"

    def test_outbox_event_with_sequence(self, generator: IdempotencyKeyGenerator):
        """Generate outbox event key with sequence."""
        key = generator.for_outbox_event("topic.name", "evt_001", sequence=2)

        assert key == f"p03:emit:{TEST_ULID}:topic.name:evt_001:2"

    def test_outbox_event_zero_sequence_omitted(self, generator: IdempotencyKeyGenerator):
        """Zero sequence is omitted from key."""
        key = generator.for_outbox_event("topic.name", "evt_001", sequence=0)

        assert key == f"p03:emit:{TEST_ULID}:topic.name:evt_001"
        # Key should NOT end with a sequence number when sequence=0
        assert not key.endswith(":0")


# =============================================================================
# Test: parse_idempotency_key
# =============================================================================


class TestParsedKeyDataclass:
    """Tests for ParsedKey dataclass."""

    def test_parsed_key_fields(self):
        """ParsedKey has all required fields."""
        parsed = ParsedKey(
            pipeline="p03",
            key_type="staging",
            cycle_ulid=TEST_ULID,
            entity_id="evt_001",
            extra=None,
        )

        assert parsed.pipeline == "p03"
        assert parsed.key_type == "staging"
        assert parsed.cycle_ulid == TEST_ULID
        assert parsed.entity_id == "evt_001"
        assert parsed.extra is None

    def test_parsed_key_with_extra(self):
        """ParsedKey stores extra field."""
        parsed = ParsedKey(
            pipeline="p03",
            key_type="write",
            cycle_ulid=TEST_ULID,
            entity_id="rec-001",
            extra="st_epi",
        )

        assert parsed.extra == "st_epi"


# =============================================================================
# Test: parse_idempotency_key
# =============================================================================


class TestParseIdempotencyKey:
    """Tests for key parsing."""

    def test_parse_staging_key(self):
        """Parse staging key."""
        key = f"p03:staging:{TEST_ULID}:evt_001"

        parsed = parse_idempotency_key(key)

        assert parsed is not None
        assert parsed.pipeline == "p03"
        assert parsed.key_type == "staging"
        assert parsed.cycle_ulid == TEST_ULID
        assert parsed.entity_id == "evt_001"

    def test_parse_write_key(self):
        """Parse write key."""
        key = f"p03:write:{TEST_ULID}:st_epi:epi-001"

        parsed = parse_idempotency_key(key)

        assert parsed is not None
        assert parsed.key_type == "write"
        assert parsed.extra == "st_epi"  # table name
        assert parsed.entity_id == "epi-001"  # record_id

    def test_parse_emit_key(self):
        """Parse emit key."""
        key = f"p03:emit:{TEST_ULID}:topic.name:42"

        parsed = parse_idempotency_key(key)

        assert parsed is not None
        assert parsed.key_type == "emit"
        assert parsed.extra == "topic.name"  # topic
        assert parsed.entity_id == "42"  # offset

    def test_parse_invalid_key(self):
        """Invalid key returns None."""
        assert parse_idempotency_key("invalid") is None
        assert parse_idempotency_key("") is None
        assert parse_idempotency_key("not:p03:key") is None


# =============================================================================
# Test: validate_idempotency_key
# =============================================================================


class TestValidateIdempotencyKey:
    """Tests for key validation."""

    def test_validate_valid_staging_key(self, generator: IdempotencyKeyGenerator):
        """Valid staging key passes."""
        key = generator.for_event_update("evt_001")

        is_valid, error = validate_idempotency_key(key)

        assert is_valid
        assert error == ""

    def test_validate_empty_key(self):
        """Empty key fails."""
        is_valid, error = validate_idempotency_key("")

        assert not is_valid
        assert "empty" in error.lower()

    def test_validate_wrong_prefix(self):
        """Wrong prefix fails."""
        is_valid, error = validate_idempotency_key("wrong:staging:ulid:id")

        assert not is_valid
        assert "p03:" in error

    def test_validate_too_long(self):
        """Key exceeding max length fails."""
        key = "p03:staging:" + "x" * 200

        is_valid, error = validate_idempotency_key(key)

        assert not is_valid
        assert "max length" in error.lower()


# =============================================================================
# Test: extract_cycle_ulid
# =============================================================================


class TestExtractCycleUlid:
    """Tests for ULID extraction."""

    def test_extract_from_staging_key(self, generator: IdempotencyKeyGenerator):
        """Extract ULID from staging key."""
        key = generator.for_event_update("evt_001")

        ulid = extract_cycle_ulid(key)

        assert ulid == TEST_ULID

    def test_extract_from_write_key(self, generator: IdempotencyKeyGenerator):
        """Extract ULID from write key."""
        key = generator.for_truth_write("st_epi", "rec-001")

        ulid = extract_cycle_ulid(key)

        assert ulid == TEST_ULID

    def test_extract_from_invalid_key(self):
        """Invalid key returns None."""
        ulid = extract_cycle_ulid("invalid")

        assert ulid is None


# =============================================================================
# Test: keys_same_cycle
# =============================================================================


class TestKeysSameCycle:
    """Tests for cycle comparison."""

    def test_same_cycle_keys(self, generator: IdempotencyKeyGenerator):
        """Keys from same generator are same cycle."""
        key1 = generator.for_event_update("evt_001")
        key2 = generator.for_truth_write("st_epi", "rec-001")

        assert keys_same_cycle(key1, key2)

    def test_different_cycle_keys(self):
        """Keys from different generators are different cycles."""
        gen1 = IdempotencyKeyGenerator("01AAAAAAAAAAAAAAAAAAAAAAAA")
        gen2 = IdempotencyKeyGenerator("01BBBBBBBBBBBBBBBBBBBBBBBB")

        key1 = gen1.for_event_update("evt_001")
        key2 = gen2.for_event_update("evt_001")

        assert not keys_same_cycle(key1, key2)

    def test_invalid_key_comparison(self):
        """Invalid key comparison returns False."""
        assert not keys_same_cycle("invalid", "invalid")


# =============================================================================
# Test: Key Length
# =============================================================================


class TestKeyLength:
    """Tests for key length constraints."""

    def test_event_update_key_reasonable_length(self, generator: IdempotencyKeyGenerator):
        """Event update key is reasonable length."""
        key = generator.for_event_update("evt_" + "x" * 50)

        assert len(key) < 200

    def test_truth_write_key_reasonable_length(self, generator: IdempotencyKeyGenerator):
        """Truth write key is reasonable length."""
        key = generator.for_truth_write("st_epi", "rec_" + "x" * 50)

        assert len(key) < 200

    def test_batch_phase_key_fixed_length(self, generator: IdempotencyKeyGenerator):
        """Batch phase key has fixed hash length regardless of input."""
        key1 = generator.for_batch_phase("R1", ["e1"])
        key2 = generator.for_batch_phase("R1", ["e" + str(i) for i in range(100)])

        # Hash portion is always 12 chars
        assert key1.split(":")[-1] != key2.split(":")[-1]
        assert len(key1.split(":")[-1]) == 12
        assert len(key2.split(":")[-1]) == 12
