"""
Tests for MetaSection - Session Metadata (HOT CORE)
=====================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 2.2 Implement HOT CORE Sections
ISSUE: 2.2.8 (meta)

Comprehensive tests for MetaSection covering:
- ISection protocol compliance
- SessionIdentity operations
- SessionLifecycle operations
- MemoryUsage operations
- VersionInfo operations
- Integrity hashing
- FlatBuffer serialization
- Apply operations (MutationGuard pattern)
- Edge cases and error handling
"""

import hashlib
import time

import pytest

from k1.sessionstate.sections.meta import (
    MemoryUsage,
    MetaSection,
    PressureLevel,
    PrivacyBand,
    SessionIdentity,
    SessionLifecycle,
    VersionInfo,
    create_meta_section,
)

# =============================================================================
# Test Classes for Data Classes
# =============================================================================


class TestSessionIdentity:
    """Tests for SessionIdentity dataclass."""

    def test_init_generates_session_id(self):
        """Session ID is generated if not provided."""
        identity = SessionIdentity()
        assert identity.session_id != ""
        assert len(identity.session_id) == 36  # UUID format

    def test_init_with_session_id(self):
        """Session ID is preserved if provided."""
        identity = SessionIdentity(session_id="test-session-123")
        assert identity.session_id == "test-session-123"

    def test_default_values(self):
        """Default values are correct."""
        identity = SessionIdentity(session_id="test")
        assert identity.user_id == ""
        assert identity.device_id == ""
        assert identity.privacy_band == PrivacyBand.AMBER
        assert identity.is_anonymous is False
        assert identity.is_demo_mode is False

    def test_is_elevated_privacy_green(self):
        """GREEN is not elevated privacy."""
        identity = SessionIdentity(session_id="test", privacy_band=PrivacyBand.GREEN)
        assert identity.is_elevated_privacy() is False

    def test_is_elevated_privacy_amber(self):
        """AMBER is not elevated privacy."""
        identity = SessionIdentity(session_id="test", privacy_band=PrivacyBand.AMBER)
        assert identity.is_elevated_privacy() is False

    def test_is_elevated_privacy_red(self):
        """RED is elevated privacy."""
        identity = SessionIdentity(session_id="test", privacy_band=PrivacyBand.RED)
        assert identity.is_elevated_privacy() is True

    def test_is_elevated_privacy_black(self):
        """BLACK is elevated privacy."""
        identity = SessionIdentity(session_id="test", privacy_band=PrivacyBand.BLACK)
        assert identity.is_elevated_privacy() is True

    def test_to_dict(self):
        """to_dict returns correct dictionary."""
        identity = SessionIdentity(
            session_id="sess-123",
            user_id="user-456",
            device_id="device-789",
            privacy_band=PrivacyBand.RED,
            is_anonymous=True,
            is_demo_mode=True,
        )
        d = identity.to_dict()
        assert d["session_id"] == "sess-123"
        assert d["user_id"] == "user-456"
        assert d["device_id"] == "device-789"
        assert d["privacy_band"] == "RED"
        assert d["is_anonymous"] is True
        assert d["is_demo_mode"] is True


class TestSessionLifecycle:
    """Tests for SessionLifecycle dataclass."""

    def test_init_sets_timestamps(self):
        """Timestamps are initialized if not provided."""
        lifecycle = SessionLifecycle()
        assert lifecycle.created_at_ms > 0
        assert lifecycle.last_activity_ms > 0
        assert lifecycle.expires_at_ms > lifecycle.created_at_ms

    def test_default_values(self):
        """Default values are correct."""
        lifecycle = SessionLifecycle()
        assert lifecycle.turn_count == 0
        assert lifecycle.last_turn_id == ""
        assert lifecycle.is_active is True
        assert lifecycle.is_expired is False
        assert lifecycle.idle_timeout_ms == 3600000  # 1 hour
        assert lifecycle.max_lifetime_ms == 86400000  # 24 hours

    def test_record_activity(self):
        """record_activity updates timestamps and turn count."""
        lifecycle = SessionLifecycle()
        original_activity = lifecycle.last_activity_ms
        original_count = lifecycle.turn_count

        time.sleep(0.001)  # Small delay
        lifecycle.record_activity("turn-123")

        assert lifecycle.last_activity_ms >= original_activity
        assert lifecycle.turn_count == original_count + 1
        assert lifecycle.last_turn_id == "turn-123"

    def test_check_expiration_not_expired(self):
        """check_expiration returns False for fresh session."""
        lifecycle = SessionLifecycle()
        assert lifecycle.check_expiration() is False
        assert lifecycle.is_expired is False
        assert lifecycle.is_active is True

    def test_check_expiration_idle_timeout(self):
        """check_expiration detects idle timeout."""
        lifecycle = SessionLifecycle(idle_timeout_ms=1)  # 1ms timeout
        time.sleep(0.01)  # Wait for timeout
        assert lifecycle.check_expiration() is True
        assert lifecycle.is_expired is True
        assert lifecycle.is_active is False

    def test_deactivate(self):
        """deactivate sets is_active to False."""
        lifecycle = SessionLifecycle()
        lifecycle.deactivate()
        assert lifecycle.is_active is False

    def test_reactivate(self):
        """reactivate sets is_active to True if not expired."""
        lifecycle = SessionLifecycle()
        lifecycle.deactivate()
        lifecycle.reactivate()
        assert lifecycle.is_active is True

    def test_reactivate_expired_session(self):
        """reactivate does not work for expired session."""
        lifecycle = SessionLifecycle()
        lifecycle.is_expired = True
        lifecycle.is_active = False
        lifecycle.reactivate()
        assert lifecycle.is_active is False  # Should remain inactive

    def test_get_age_ms(self):
        """get_age_ms returns correct age."""
        lifecycle = SessionLifecycle()
        time.sleep(0.01)
        age = lifecycle.get_age_ms()
        assert age >= 10  # At least 10ms

    def test_get_idle_ms(self):
        """get_idle_ms returns correct idle time."""
        lifecycle = SessionLifecycle()
        time.sleep(0.01)
        idle = lifecycle.get_idle_ms()
        assert idle >= 10  # At least 10ms

    def test_get_remaining_lifetime_ms(self):
        """get_remaining_lifetime_ms returns correct value."""
        lifecycle = SessionLifecycle(max_lifetime_ms=1000000)
        remaining = lifecycle.get_remaining_lifetime_ms()
        assert remaining > 0
        assert remaining <= 1000000

    def test_to_dict(self):
        """to_dict returns correct dictionary."""
        lifecycle = SessionLifecycle()
        lifecycle.record_activity("turn-1")
        d = lifecycle.to_dict()
        assert "created_at_ms" in d
        assert "last_activity_ms" in d
        assert d["turn_count"] == 1
        assert d["last_turn_id"] == "turn-1"
        assert d["is_active"] is True


class TestMemoryUsage:
    """Tests for MemoryUsage dataclass."""

    def test_default_values(self):
        """Default values are correct."""
        mem = MemoryUsage()
        assert mem.hot_control == 0
        assert mem.hot_budget == 49152
        assert mem.warm_budget == 49152
        assert mem.total_budget == 98304

    def test_hot_total(self):
        """hot_total calculates correctly."""
        mem = MemoryUsage(
            hot_control=1000,
            hot_beliefs_active=2000,
            hot_scoreboard=3000,
            hot_history_active=4000,
            hot_clarifications=500,
            hot_affective_now=600,
            hot_narrative_active=700,
            hot_meta=200,
        )
        assert mem.hot_total == 12000

    def test_warm_total(self):
        """warm_total calculates correctly."""
        mem = MemoryUsage(
            warm_beliefs_history=5000,
            warm_history_recent=6000,
            warm_persona=3000,
            warm_telemetry=2000,
        )
        assert mem.warm_total == 16000

    def test_session_total(self):
        """session_total is sum of hot and warm."""
        mem = MemoryUsage(hot_control=1000, warm_telemetry=2000)
        assert mem.session_total == 3000

    def test_is_over_budget_false(self):
        """is_over_budget is False when under budget."""
        mem = MemoryUsage(hot_control=1000)
        assert mem.is_over_budget is False

    def test_is_over_budget_true_hot(self):
        """is_over_budget is True when HOT over budget."""
        mem = MemoryUsage(hot_control=50000)  # Over 48KB
        assert mem.is_over_budget is True

    def test_is_over_budget_true_warm(self):
        """is_over_budget is True when WARM over budget."""
        mem = MemoryUsage(warm_telemetry=50000)  # Over 48KB
        assert mem.is_over_budget is True

    def test_pressure_level_normal(self):
        """pressure_level is NORMAL when under 60%."""
        mem = MemoryUsage(hot_control=20000)  # ~40% of 48KB
        assert mem.pressure_level == PressureLevel.NORMAL

    def test_pressure_level_elevated(self):
        """pressure_level is ELEVATED at 60-80%."""
        mem = MemoryUsage(hot_control=35000)  # ~71% of 48KB
        assert mem.pressure_level == PressureLevel.ELEVATED

    def test_pressure_level_high(self):
        """pressure_level is HIGH at 80-90%."""
        mem = MemoryUsage(hot_control=42000)  # ~85% of 48KB
        assert mem.pressure_level == PressureLevel.HIGH

    def test_pressure_level_critical(self):
        """pressure_level is CRITICAL at >90%."""
        mem = MemoryUsage(hot_control=45000)  # ~91% of 48KB
        assert mem.pressure_level == PressureLevel.CRITICAL

    def test_get_hot_utilization(self):
        """get_hot_utilization returns correct value."""
        mem = MemoryUsage(hot_control=24576)  # 50% of 48KB
        util = mem.get_hot_utilization()
        assert abs(util - 0.5) < 0.01

    def test_get_warm_utilization(self):
        """get_warm_utilization returns correct value."""
        mem = MemoryUsage(warm_telemetry=24576)  # 50% of 48KB
        util = mem.get_warm_utilization()
        assert abs(util - 0.5) < 0.01

    def test_update_hot_section(self):
        """update_hot_section updates correct attribute."""
        mem = MemoryUsage()
        mem.update_hot_section("control", 1000)
        assert mem.hot_control == 1000

    def test_update_warm_section(self):
        """update_warm_section updates correct attribute."""
        mem = MemoryUsage()
        mem.update_warm_section("telemetry", 2000)
        assert mem.warm_telemetry == 2000

    def test_record_eviction(self):
        """record_eviction updates count and timestamp."""
        mem = MemoryUsage()
        mem.record_eviction()
        assert mem.eviction_count == 1
        assert mem.last_eviction_ms > 0

    def test_get_section_sizes(self):
        """get_section_sizes returns all sections."""
        mem = MemoryUsage(hot_control=100, warm_telemetry=200)
        sizes = mem.get_section_sizes()
        assert sizes["hot_control"] == 100
        assert sizes["warm_telemetry"] == 200
        assert len(sizes) == 12  # 8 HOT + 4 WARM

    def test_to_dict(self):
        """to_dict returns comprehensive dictionary."""
        mem = MemoryUsage(hot_control=1000)
        d = mem.to_dict()
        assert d["hot_control"] == 1000
        assert d["hot_total"] == 1000
        assert "pressure_level" in d
        assert "hot_utilization" in d


class TestVersionInfo:
    """Tests for VersionInfo dataclass."""

    def test_default_values(self):
        """Default values are correct."""
        ver = VersionInfo()
        assert ver.state_version == 1
        assert ver.min_compatible_version == 1
        assert ver.format == "flatbuffers"
        assert ver.features == 0

    def test_is_compatible_same_version(self):
        """is_compatible returns True for same version."""
        ver = VersionInfo(min_compatible_version=1)
        assert ver.is_compatible(1) is True

    def test_is_compatible_higher_version(self):
        """is_compatible returns True for higher version."""
        ver = VersionInfo(min_compatible_version=1)
        assert ver.is_compatible(2) is True

    def test_is_compatible_lower_version(self):
        """is_compatible returns False for lower version."""
        ver = VersionInfo(min_compatible_version=2)
        assert ver.is_compatible(1) is False

    def test_get_schema_string(self):
        """get_schema_string returns correct format."""
        ver = VersionInfo(schema_major=1, schema_minor=2, schema_patch=3)
        assert ver.get_schema_string() == "1.2.3"

    def test_to_dict(self):
        """to_dict returns correct dictionary."""
        ver = VersionInfo()
        d = ver.to_dict()
        assert d["state_version"] == 1
        assert d["format"] == "flatbuffers"
        assert "schema" in d


# =============================================================================
# Test Classes for MetaSection
# =============================================================================


class TestMetaSectionInit:
    """Tests for MetaSection initialization."""

    def test_init_default(self):
        """Default initialization creates valid section."""
        section = MetaSection()
        assert section.session_id != ""
        assert section.user_id == ""
        assert section.is_active is True

    def test_init_with_session_id(self):
        """Session ID is preserved."""
        section = MetaSection(session_id="test-session")
        assert section.session_id == "test-session"

    def test_init_with_user_id(self):
        """User ID is set correctly."""
        section = MetaSection(user_id="user-123")
        assert section.user_id == "user-123"

    def test_init_with_device_id(self):
        """Device ID is set correctly."""
        section = MetaSection(device_id="device-456")
        assert section.device_id == "device-456"

    def test_init_with_privacy_band(self):
        """Privacy band is set correctly."""
        section = MetaSection(privacy_band=PrivacyBand.RED)
        assert section.privacy_band == PrivacyBand.RED

    def test_init_anonymous(self):
        """Anonymous flag is set correctly."""
        section = MetaSection(is_anonymous=True)
        assert section.is_anonymous is True

    def test_init_demo_mode(self):
        """Demo mode flag is set correctly."""
        section = MetaSection(is_demo_mode=True)
        assert section.is_demo_mode is True


class TestISectionProtocol:
    """Tests for ISection protocol compliance."""

    def test_name_property(self):
        """name property returns 'meta'."""
        section = MetaSection()
        assert section.name == "meta"

    def test_tier_property(self):
        """tier property returns 'hot'."""
        section = MetaSection()
        assert section.tier == "hot"

    def test_budget_bytes_property(self):
        """budget_bytes property returns 2048."""
        section = MetaSection()
        assert section.budget_bytes == 2048

    def test_can_evict_property(self):
        """can_evict property returns False."""
        section = MetaSection()
        assert section.can_evict is False

    def test_get_size_bytes(self):
        """get_size_bytes returns positive value."""
        section = MetaSection()
        size = section.get_size_bytes()
        assert size > 0
        assert size <= 2048

    def test_clear(self):
        """clear resets section state."""
        section = MetaSection(user_id="user-123")
        section.record_turn("turn-1")
        section.update_section_size("control", 1000)

        session_id = section.session_id
        section.clear()

        # Identity preserved
        assert section.session_id == session_id
        assert section.user_id == "user-123"
        # State reset
        assert section.turn_count == 0
        assert section.get_memory().hot_control == 0

    def test_get_metadata(self):
        """get_metadata returns comprehensive metadata."""
        section = MetaSection(session_id="sess-123", user_id="user-456")
        meta = section.get_metadata()

        assert meta["name"] == "meta"
        assert meta["tier"] == "hot"
        assert meta["budget_bytes"] == 2048
        assert meta["can_evict"] is False
        assert meta["session_id"] == "sess-123"
        assert meta["user_id"] == "user-456"


class TestIdentityAPI:
    """Tests for Identity API."""

    def test_get_identity(self):
        """get_identity returns SessionIdentity."""
        section = MetaSection(session_id="sess-123", user_id="user-456")
        identity = section.get_identity()

        assert isinstance(identity, SessionIdentity)
        assert identity.session_id == "sess-123"
        assert identity.user_id == "user-456"

    def test_set_user_id(self):
        """set_user_id updates user ID."""
        section = MetaSection()
        section.set_user_id("new-user")
        assert section.user_id == "new-user"

    def test_set_device_id(self):
        """set_device_id updates device ID."""
        section = MetaSection()
        section.set_device_id("new-device")
        assert section.device_id == "new-device"

    def test_set_privacy_band(self):
        """set_privacy_band updates privacy band."""
        section = MetaSection()
        section.set_privacy_band(PrivacyBand.BLACK)
        assert section.privacy_band == PrivacyBand.BLACK

    def test_upgrade_from_anonymous(self):
        """upgrade_from_anonymous converts anonymous session."""
        section = MetaSection(is_anonymous=True)
        section.upgrade_from_anonymous("authenticated-user")

        assert section.user_id == "authenticated-user"
        assert section.is_anonymous is False

    def test_upgrade_from_anonymous_no_op_if_not_anonymous(self):
        """upgrade_from_anonymous does nothing if not anonymous."""
        section = MetaSection(user_id="original-user", is_anonymous=False)
        section.upgrade_from_anonymous("new-user")

        # Should not change since not anonymous
        assert section.user_id == "original-user"


class TestLifecycleAPI:
    """Tests for Lifecycle API."""

    def test_record_turn(self):
        """record_turn increments turn count."""
        section = MetaSection()
        count = section.record_turn("turn-1")
        assert count == 1
        assert section.turn_count == 1

    def test_record_turn_generates_id(self):
        """record_turn generates turn ID if not provided."""
        section = MetaSection()
        count = section.record_turn()
        assert count == 1
        lifecycle = section.get_lifecycle()
        assert lifecycle.last_turn_id != ""

    def test_check_expiration_fresh(self):
        """check_expiration returns False for fresh session."""
        section = MetaSection()
        assert section.check_expiration() is False

    def test_deactivate(self):
        """deactivate sets is_active to False."""
        section = MetaSection()
        section.deactivate()
        assert section.is_active is False

    def test_reactivate(self):
        """reactivate sets is_active to True."""
        section = MetaSection()
        section.deactivate()
        section.reactivate()
        assert section.is_active is True

    def test_set_idle_timeout(self):
        """set_idle_timeout updates timeout."""
        section = MetaSection()
        section.set_idle_timeout(60000)
        lifecycle = section.get_lifecycle()
        assert lifecycle.idle_timeout_ms == 60000

    def test_set_max_lifetime(self):
        """set_max_lifetime updates lifetime and expiration."""
        section = MetaSection()
        section.set_max_lifetime(1000000)
        lifecycle = section.get_lifecycle()
        assert lifecycle.max_lifetime_ms == 1000000

    def test_get_age_ms(self):
        """get_age_ms returns session age."""
        section = MetaSection()
        time.sleep(0.01)
        age = section.get_age_ms()
        assert age >= 10

    def test_get_idle_ms(self):
        """get_idle_ms returns idle time."""
        section = MetaSection()
        time.sleep(0.01)
        idle = section.get_idle_ms()
        assert idle >= 10


class TestMemoryAPI:
    """Tests for Memory API."""

    def test_get_memory(self):
        """get_memory returns MemoryUsage."""
        section = MetaSection()
        mem = section.get_memory()
        assert isinstance(mem, MemoryUsage)

    def test_pressure_level_property(self):
        """pressure_level returns correct level."""
        section = MetaSection()
        assert section.pressure_level == PressureLevel.NORMAL

    def test_hot_utilization_property(self):
        """hot_utilization returns correct value."""
        section = MetaSection()
        assert section.hot_utilization >= 0

    def test_warm_utilization_property(self):
        """warm_utilization returns correct value."""
        section = MetaSection()
        assert section.warm_utilization >= 0

    def test_update_section_size_hot(self):
        """update_section_size updates HOT section."""
        section = MetaSection()
        section.update_section_size("control", 1000)
        mem = section.get_memory()
        assert mem.hot_control == 1000

    def test_update_section_size_warm(self):
        """update_section_size updates WARM section."""
        section = MetaSection()
        section.update_section_size("telemetry", 2000)
        mem = section.get_memory()
        assert mem.warm_telemetry == 2000

    def test_update_section_size_meta(self):
        """update_section_size updates meta section."""
        section = MetaSection()
        section.update_section_size("meta", 500)
        mem = section.get_memory()
        assert mem.hot_meta == 500

    def test_update_all_sizes(self):
        """update_all_sizes updates multiple sections."""
        section = MetaSection()
        section.update_all_sizes(
            {
                "control": 1000,
                "beliefs_active": 2000,
                "telemetry": 3000,
            }
        )
        mem = section.get_memory()
        assert mem.hot_control == 1000
        assert mem.hot_beliefs_active == 2000
        assert mem.warm_telemetry == 3000

    def test_record_eviction(self):
        """record_eviction increments eviction count."""
        section = MetaSection()
        section.record_eviction()
        mem = section.get_memory()
        assert mem.eviction_count == 1
        assert mem.last_eviction_ms > 0

    def test_set_cold_references(self):
        """set_cold_references updates count."""
        section = MetaSection()
        section.set_cold_references(5)
        mem = section.get_memory()
        assert mem.cold_references == 5

    def test_set_remote_references(self):
        """set_remote_references updates count."""
        section = MetaSection()
        section.set_remote_references(3)
        mem = section.get_memory()
        assert mem.remote_references == 3


class TestVersionAPI:
    """Tests for Version API."""

    def test_get_version(self):
        """get_version returns VersionInfo."""
        section = MetaSection()
        ver = section.get_version()
        assert isinstance(ver, VersionInfo)

    def test_get_schema_version(self):
        """get_schema_version returns version string."""
        section = MetaSection()
        schema = section.get_schema_version()
        assert schema == "1.0.0"

    def test_is_compatible_version(self):
        """is_compatible_version checks compatibility."""
        section = MetaSection()
        assert section.is_compatible_version(1) is True
        assert section.is_compatible_version(2) is True

    def test_set_features(self):
        """set_features updates feature flags."""
        section = MetaSection()
        section.set_features(0x0F)
        ver = section.get_version()
        assert ver.features == 0x0F


class TestIntegrityAPI:
    """Tests for Integrity API."""

    def test_compute_integrity(self):
        """compute_integrity returns SHA256 hash."""
        section = MetaSection()
        data = b"test data"
        hash_value = section.compute_integrity(data)
        expected = hashlib.sha256(data).hexdigest()
        assert hash_value == expected

    def test_set_get_integrity(self):
        """set_integrity and get_integrity work correctly."""
        section = MetaSection()
        section.set_integrity("test-hash")
        assert section.get_integrity() == "test-hash"

    def test_verify_integrity_no_hash(self):
        """verify_integrity returns True when no hash set."""
        section = MetaSection()
        assert section.verify_integrity(b"any data") is True

    def test_verify_integrity_matching(self):
        """verify_integrity returns True for matching hash."""
        section = MetaSection()
        data = b"test data"
        section.set_integrity(section.compute_integrity(data))
        assert section.verify_integrity(data) is True

    def test_verify_integrity_mismatch(self):
        """verify_integrity returns False for mismatched hash."""
        section = MetaSection()
        section.set_integrity("wrong-hash")
        assert section.verify_integrity(b"test data") is False

    def test_update_integrity_from_serialized(self):
        """update_integrity_from_serialized computes and stores hash."""
        section = MetaSection()
        hash_value = section.update_integrity_from_serialized()

        assert len(hash_value) == 64  # SHA256 hex digest
        assert section.get_integrity() == hash_value


class TestFlatBufferSerialization:
    """Tests for FlatBuffer serialization."""

    def test_to_flatbuffer_returns_bytes(self):
        """to_flatbuffer returns bytes."""
        section = MetaSection()
        data = section.to_flatbuffer()
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_to_flatbuffer_caching(self):
        """to_flatbuffer caches result."""
        section = MetaSection()
        data1 = section.to_flatbuffer()
        data2 = section.to_flatbuffer()
        assert data1 is data2  # Same object (cached)

    def test_to_flatbuffer_cache_invalidated(self):
        """Mutation invalidates cache."""
        section = MetaSection()
        data1 = section.to_flatbuffer()
        section.record_turn("turn-1")
        data2 = section.to_flatbuffer()
        assert data1 is not data2

    def test_from_flatbuffer_restores_identity(self):
        """from_flatbuffer restores identity."""
        section = MetaSection(
            session_id="sess-123",
            user_id="user-456",
            device_id="device-789",
            privacy_band=PrivacyBand.RED,
            is_anonymous=True,
            is_demo_mode=True,
        )
        data = section.to_flatbuffer()

        restored = MetaSection()
        restored.from_flatbuffer(data)

        assert restored.session_id == "sess-123"
        assert restored.user_id == "user-456"
        assert restored.device_id == "device-789"
        assert restored.privacy_band == PrivacyBand.RED
        assert restored.is_anonymous is True
        assert restored.is_demo_mode is True

    def test_from_flatbuffer_restores_lifecycle(self):
        """from_flatbuffer restores lifecycle."""
        section = MetaSection()
        section.record_turn("turn-1")
        section.record_turn("turn-2")
        data = section.to_flatbuffer()

        restored = MetaSection()
        restored.from_flatbuffer(data)

        assert restored.turn_count == 2
        lifecycle = restored.get_lifecycle()
        assert lifecycle.last_turn_id == "turn-2"

    def test_from_flatbuffer_restores_memory(self):
        """from_flatbuffer restores memory usage."""
        section = MetaSection()
        section.update_section_size("control", 1000)
        section.update_section_size("telemetry", 2000)
        section.record_eviction()
        data = section.to_flatbuffer()

        restored = MetaSection()
        restored.from_flatbuffer(data)

        mem = restored.get_memory()
        assert mem.hot_control == 1000
        assert mem.warm_telemetry == 2000
        assert mem.eviction_count == 1

    def test_from_flatbuffer_restores_version(self):
        """from_flatbuffer restores version info."""
        section = MetaSection()
        section.set_features(0xFF)
        data = section.to_flatbuffer()

        restored = MetaSection()
        restored.from_flatbuffer(data)

        ver = restored.get_version()
        assert ver.features == 0xFF

    def test_round_trip_preserves_data(self):
        """Full round-trip preserves all data."""
        section = MetaSection(
            session_id="sess-abc",
            user_id="user-xyz",
            device_id="device-123",
            privacy_band=PrivacyBand.BLACK,
        )
        section.record_turn("turn-1")
        section.update_section_size("control", 5000)
        section.update_section_size("history_recent", 10000)
        section.set_cold_references(10)
        section.set_features(0x1F)

        data = section.to_flatbuffer()

        restored = MetaSection()
        restored.from_flatbuffer(data)

        # Compare all key fields
        assert restored.session_id == section.session_id
        assert restored.user_id == section.user_id
        assert restored.device_id == section.device_id
        assert restored.privacy_band == section.privacy_band
        assert restored.turn_count == section.turn_count

        mem_original = section.get_memory()
        mem_restored = restored.get_memory()
        assert mem_restored.hot_control == mem_original.hot_control
        assert mem_restored.warm_history_recent == mem_original.warm_history_recent


class TestApplyOperations:
    """Tests for apply() method (MutationGuard pattern)."""

    def test_apply_set_user_id(self):
        """apply set_user_id works."""
        section = MetaSection()
        section.apply("set_user_id", {"user_id": "new-user"})
        assert section.user_id == "new-user"

    def test_apply_set_device_id(self):
        """apply set_device_id works."""
        section = MetaSection()
        section.apply("set_device_id", {"device_id": "new-device"})
        assert section.device_id == "new-device"

    def test_apply_set_privacy_band_int(self):
        """apply set_privacy_band with int works."""
        section = MetaSection()
        section.apply("set_privacy_band", {"band": 2})  # RED
        assert section.privacy_band == PrivacyBand.RED

    def test_apply_set_privacy_band_str(self):
        """apply set_privacy_band with string works."""
        section = MetaSection()
        section.apply("set_privacy_band", {"band": "black"})
        assert section.privacy_band == PrivacyBand.BLACK

    def test_apply_record_turn(self):
        """apply record_turn works."""
        section = MetaSection()
        section.apply("record_turn", {"turn_id": "turn-123"})
        assert section.turn_count == 1

    def test_apply_update_section_size(self):
        """apply update_section_size works."""
        section = MetaSection()
        section.apply("update_section_size", {"section": "control", "size_bytes": 1000})
        mem = section.get_memory()
        assert mem.hot_control == 1000

    def test_apply_update_all_sizes(self):
        """apply update_all_sizes works."""
        section = MetaSection()
        section.apply("update_all_sizes", {"sizes": {"control": 1000, "telemetry": 2000}})
        mem = section.get_memory()
        assert mem.hot_control == 1000
        assert mem.warm_telemetry == 2000

    def test_apply_record_eviction(self):
        """apply record_eviction works."""
        section = MetaSection()
        section.apply("record_eviction", {})
        mem = section.get_memory()
        assert mem.eviction_count == 1

    def test_apply_deactivate(self):
        """apply deactivate works."""
        section = MetaSection()
        section.apply("deactivate", {})
        assert section.is_active is False

    def test_apply_reactivate(self):
        """apply reactivate works."""
        section = MetaSection()
        section.apply("deactivate", {})
        section.apply("reactivate", {})
        assert section.is_active is True

    def test_apply_upgrade_from_anonymous(self):
        """apply upgrade_from_anonymous works."""
        section = MetaSection(is_anonymous=True)
        section.apply("upgrade_from_anonymous", {"user_id": "authenticated"})
        assert section.is_anonymous is False
        assert section.user_id == "authenticated"

    def test_apply_set_idle_timeout(self):
        """apply set_idle_timeout works."""
        section = MetaSection()
        section.apply("set_idle_timeout", {"timeout_ms": 120000})
        lifecycle = section.get_lifecycle()
        assert lifecycle.idle_timeout_ms == 120000

    def test_apply_set_max_lifetime(self):
        """apply set_max_lifetime works."""
        section = MetaSection()
        section.apply("set_max_lifetime", {"lifetime_ms": 3600000})
        lifecycle = section.get_lifecycle()
        assert lifecycle.max_lifetime_ms == 3600000

    def test_apply_set_cold_references(self):
        """apply set_cold_references works."""
        section = MetaSection()
        section.apply("set_cold_references", {"count": 5})
        mem = section.get_memory()
        assert mem.cold_references == 5

    def test_apply_set_remote_references(self):
        """apply set_remote_references works."""
        section = MetaSection()
        section.apply("set_remote_references", {"count": 3})
        mem = section.get_memory()
        assert mem.remote_references == 3

    def test_apply_set_features(self):
        """apply set_features works."""
        section = MetaSection()
        section.apply("set_features", {"features": 0xFF})
        ver = section.get_version()
        assert ver.features == 0xFF

    def test_apply_clear(self):
        """apply clear works."""
        section = MetaSection()
        section.record_turn("turn-1")
        section.apply("clear", {})
        assert section.turn_count == 0

    def test_apply_unknown_operation(self):
        """apply raises ValueError for unknown operation."""
        section = MetaSection()
        with pytest.raises(ValueError, match="Unknown operation"):
            section.apply("unknown_op", {})


class TestFactoryFunction:
    """Tests for factory function."""

    def test_create_meta_section_default(self):
        """create_meta_section with defaults works."""
        section = create_meta_section()
        assert section.session_id != ""
        assert section.is_active is True

    def test_create_meta_section_with_params(self):
        """create_meta_section with parameters works."""
        section = create_meta_section(
            session_id="sess-123",
            user_id="user-456",
            device_id="device-789",
            privacy_band=PrivacyBand.RED,
            is_anonymous=True,
            is_demo_mode=True,
        )
        assert section.session_id == "sess-123"
        assert section.user_id == "user-456"
        assert section.device_id == "device-789"
        assert section.privacy_band == PrivacyBand.RED
        assert section.is_anonymous is True
        assert section.is_demo_mode is True


class TestUtilityMethods:
    """Tests for utility methods."""

    def test_to_dict(self):
        """to_dict returns comprehensive dictionary."""
        section = MetaSection(session_id="sess-123", user_id="user-456")
        section.record_turn("turn-1")

        d = section.to_dict()

        assert "identity" in d
        assert "lifecycle" in d
        assert "memory" in d
        assert "version" in d
        assert d["identity"]["session_id"] == "sess-123"
        assert d["lifecycle"]["turn_count"] == 1

    def test_repr(self):
        """__repr__ returns readable string."""
        section = MetaSection(session_id="sess-123", user_id="user-456")
        repr_str = repr(section)

        assert "MetaSection" in repr_str
        assert "sess-123" in repr_str
        assert "user-456" in repr_str


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_strings(self):
        """Empty strings are handled correctly."""
        section = MetaSection(user_id="", device_id="")
        assert section.user_id == ""
        assert section.device_id == ""

    def test_large_section_sizes(self):
        """Large section sizes are handled correctly."""
        section = MetaSection()
        section.update_section_size("control", 100000)
        mem = section.get_memory()
        assert mem.hot_control == 100000
        assert mem.is_over_budget is True

    def test_many_turns(self):
        """Many turns are tracked correctly."""
        section = MetaSection()
        for i in range(100):
            section.record_turn(f"turn-{i}")
        assert section.turn_count == 100

    def test_multiple_evictions(self):
        """Multiple evictions are tracked correctly."""
        section = MetaSection()
        for _ in range(10):
            section.record_eviction()
        mem = section.get_memory()
        assert mem.eviction_count == 10

    def test_unicode_strings(self):
        """Unicode strings are handled correctly."""
        section = MetaSection(user_id="用户-123", device_id="设备-456")
        data = section.to_flatbuffer()

        restored = MetaSection()
        restored.from_flatbuffer(data)

        assert restored.user_id == "用户-123"
        assert restored.device_id == "设备-456"

    def test_timestamp_updates(self):
        """Timestamps are updated correctly."""
        section = MetaSection()
        original_updated = section._last_updated_ms

        time.sleep(0.001)
        section.record_turn("turn-1")

        assert section._last_updated_ms > original_updated

    def test_cache_invalidation_on_mutations(self):
        """Cache is invalidated on all mutations."""
        section = MetaSection()
        section.to_flatbuffer()  # Populate cache
        assert section._cache_valid is True

        section.set_user_id("new-user")
        assert section._cache_valid is False

    def test_size_within_budget(self):
        """Serialized size is within budget."""
        section = MetaSection(
            session_id="sess-123456789",
            user_id="user-123456789",
            device_id="device-123456789",
        )
        section.record_turn("turn-1")
        section.update_section_size("control", 8000)

        data = section.to_flatbuffer()
        assert len(data) <= 2048  # 2KB budget


class TestTimestamps:
    """Tests for timestamp-related functionality."""

    def test_created_at_ms_set_on_init(self):
        """created_at_ms is set on initialization."""
        before = int(time.time() * 1000)
        section = MetaSection()
        after = int(time.time() * 1000)

        assert before <= section.created_at_ms <= after

    def test_last_activity_ms_updated_on_turn(self):
        """last_activity_ms is updated on turn."""
        section = MetaSection()
        original = section.last_activity_ms

        time.sleep(0.001)
        section.record_turn("turn-1")

        assert section.last_activity_ms > original

    def test_lifecycle_expires_at_ms_calculated(self):
        """expires_at_ms is calculated from max_lifetime_ms."""
        section = MetaSection()
        lifecycle = section.get_lifecycle()

        expected_expiry = lifecycle.created_at_ms + lifecycle.max_lifetime_ms
        assert lifecycle.expires_at_ms == expected_expiry
