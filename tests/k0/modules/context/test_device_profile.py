"""
Comprehensive test suite for M09 Device Profile module.

Test Categories:
1. Device Kind Classification (10 tests)
2. Platform Detection (8 tests)
3. Client Version Parsing (6 tests)
4. Input Method Mapping (8 tests)
5. End-to-End Profiling (6 tests)
6. Performance Tests (3 tests)
7. Metrics Tests (2 tests)
8. Edge Cases (5 tests)

Total: 48 tests
"""

import asyncio

# Import module under test
import sys
import time

import pytest

sys.path.insert(0, "d:/familyos")

from k0.modules.context import device_profile as dp

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module metrics before each test."""
    dp.reset_metrics()
    yield
    dp.reset_metrics()


@pytest.fixture
def sample_envelope_phone():
    """Sample envelope with phone device."""
    return {
        "device_id": "device-dad-phone",
        "metadata": {
            "user_agent": "FamilyOS/2.3.1 (iOS 17.1; iPhone15,2)",
            "client_version": "2.3.1+20250115.1",
            "input_source": "text_entry",
        },
    }


@pytest.fixture
def sample_envelope_tablet():
    """Sample envelope with tablet device."""
    return {
        "device_id": "device-mom-tablet",
        "metadata": {
            "user_agent": "FamilyOS/2.3.1 (iOS 17.1; iPad13,1)",
            "client_version": "2.3.1",
            "input_source": "photo_capture",
        },
    }


@pytest.fixture
def sample_envelope_watch():
    """Sample envelope with watch device."""
    return {
        "device_id": "device-teen-watch",
        "metadata": {
            "user_agent": "FamilyOS/2.3.1 (watchOS 10.0; Watch6,1)",
            "client_version": "2.3.1",
            "input_source": "voice_memo",
        },
    }


@pytest.fixture
def sample_envelope_web():
    """Sample envelope with web device."""
    return {
        "device_id": "web-dad-desktop",
        "metadata": {
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) FamilyOS/2.3.1",
            "client_version": "2.3.1",
            "input_source": "text_entry",
        },
    }


@pytest.fixture
def sample_envelope_api():
    """Sample envelope with API device."""
    return {
        "device_id": "api-connector-gcal",
        "metadata": {
            "user_agent": "FamilyOS-Connector/1.0.0",
            "client_version": "1.0.0",
            "input_source": "bulk_import",
        },
    }


# =============================================================================
# TEST GROUP 1: Device Kind Classification (10 tests)
# =============================================================================


class TestDeviceKindClassification:
    """Test device kind classification from device_id."""

    def test_classify_phone_explicit(self):
        """Test phone classification with explicit 'phone' in device_id."""
        assert dp.classify_device_kind("device-dad-phone") == "phone"

    def test_classify_phone_iphone(self):
        """Test phone classification with 'iphone' in device_id."""
        assert dp.classify_device_kind("device-teen-iphone") == "phone"

    def test_classify_phone_android(self):
        """Test phone classification with 'android' in device_id."""
        assert dp.classify_device_kind("device-mom-android") == "phone"

    def test_classify_tablet_explicit(self):
        """Test tablet classification with explicit 'tablet' in device_id."""
        assert dp.classify_device_kind("device-dad-tablet") == "tablet"

    def test_classify_tablet_ipad(self):
        """Test tablet classification with 'ipad' in device_id."""
        assert dp.classify_device_kind("device-mom-ipad") == "tablet"

    def test_classify_watch_explicit(self):
        """Test watch classification with explicit 'watch' in device_id."""
        assert dp.classify_device_kind("device-teen-watch") == "watch"

    def test_classify_watch_wearable(self):
        """Test watch classification with 'wearable' in device_id."""
        assert dp.classify_device_kind("device-kid-wearable") == "watch"

    def test_classify_web_explicit(self):
        """Test web classification with 'web-' prefix."""
        assert dp.classify_device_kind("web-dad-desktop") == "web"

    def test_classify_api_explicit(self):
        """Test API classification with 'api-' prefix."""
        assert dp.classify_device_kind("api-connector-gcal") == "api"

    def test_classify_unknown_defaults_to_phone(self):
        """Test unknown device_id defaults to 'phone' (most common)."""
        assert dp.classify_device_kind("unknown-device-xyz") == "phone"
        assert dp.classify_device_kind("") == "phone"


# =============================================================================
# TEST GROUP 2: Platform Detection (8 tests)
# =============================================================================


class TestPlatformDetection:
    """Test platform detection from device_id and user_agent."""

    def test_detect_ios_iphone(self):
        """Test iOS detection from 'iphone' in device_id."""
        assert dp.detect_platform("device-dad-iphone") == "iOS"

    def test_detect_ios_ipad(self):
        """Test iOS detection from 'ipad' in device_id."""
        assert dp.detect_platform("device-mom-ipad") == "iOS"

    def test_detect_ios_watch(self):
        """Test iOS detection from 'watch' in device_id."""
        assert dp.detect_platform("device-teen-watch", "watchOS 10.0") == "iOS"

    def test_detect_android_phone(self):
        """Test Android detection from 'android' in device_id."""
        assert dp.detect_platform("device-dad-android") == "Android"

    def test_detect_web_mozilla(self):
        """Test web detection from 'mozilla' in user_agent."""
        assert dp.detect_platform("web-dad-desktop", "Mozilla/5.0 ...") == "web"

    def test_detect_web_chrome(self):
        """Test web detection from 'chrome' in user_agent."""
        assert dp.detect_platform("web-dad-chrome", "Chrome/120.0") == "web"

    def test_detect_unknown_no_match(self):
        """Test unknown detection when no platform matches."""
        assert dp.detect_platform("custom-device-xyz") == "unknown"

    def test_detect_unknown_empty_inputs(self):
        """Test unknown detection with empty inputs."""
        assert dp.detect_platform("", "") == "unknown"


# =============================================================================
# TEST GROUP 3: Client Version Parsing (6 tests)
# =============================================================================


class TestClientVersionParsing:
    """Test client version parsing into version and build."""

    def test_parse_version_only(self):
        """Test parsing version without build."""
        version, build = dp.parse_client_version("2.3.1")
        assert version == "2.3.1"
        assert build is None

    def test_parse_version_with_plus_build(self):
        """Test parsing version with build (+ separator)."""
        version, build = dp.parse_client_version("2.3.1+20250115.1")
        assert version == "2.3.1"
        assert build == "20250115.1"

    def test_parse_version_with_space_build(self):
        """Test parsing version with build (space separator)."""
        version, build = dp.parse_client_version("2.3.1 20250115.1")
        assert version == "2.3.1"
        assert build == "20250115.1"

    def test_parse_version_with_whitespace(self):
        """Test parsing version with extra whitespace."""
        version, build = dp.parse_client_version("  2.3.1  ")
        assert version == "2.3.1"
        assert build is None

    def test_parse_version_none(self):
        """Test parsing None client version."""
        version, build = dp.parse_client_version(None)
        assert version is None
        assert build is None

    def test_parse_version_empty(self):
        """Test parsing empty client version."""
        version, build = dp.parse_client_version("")
        assert version is None
        assert build is None


# =============================================================================
# TEST GROUP 4: Input Method Mapping (8 tests)
# =============================================================================


class TestInputMethodMapping:
    """Test input method mapping from input_source."""

    def test_map_voice_memo(self):
        """Test voice mapping from 'voice_memo'."""
        assert dp.map_input_method("voice_memo") == "voice"

    def test_map_voice_audio(self):
        """Test voice mapping from 'audio'."""
        assert dp.map_input_method("audio_transcription") == "voice"

    def test_map_photo_capture(self):
        """Test photo mapping from 'photo_capture'."""
        assert dp.map_input_method("photo_capture") == "photo"

    def test_map_photo_image(self):
        """Test photo mapping from 'image'."""
        assert dp.map_input_method("image_upload") == "photo"

    def test_map_scan_ocr(self):
        """Test scan mapping from 'ocr'."""
        assert dp.map_input_method("ocr_document") == "scan"

    def test_map_import_bulk(self):
        """Test import mapping from 'bulk'."""
        assert dp.map_input_method("bulk_import") == "import"

    def test_map_api_connector(self):
        """Test api mapping from 'connector'."""
        assert dp.map_input_method("api_connector") == "api"

    def test_map_text_default(self):
        """Test text default mapping for unknown input."""
        assert dp.map_input_method("unknown_input") == "text"
        assert dp.map_input_method(None) == "text"


# =============================================================================
# TEST GROUP 5: End-to-End Profiling (6 tests)
# =============================================================================


class TestEndToEndProfiling:
    """Test complete device profiling with async run()."""

    @pytest.mark.asyncio
    async def test_run_with_phone_envelope(self, sample_envelope_phone):
        """Test complete profiling with phone envelope."""
        result = await dp.run(sample_envelope_phone)

        assert result["device_id"] == "device-dad-phone"
        assert result["device_kind"] == "phone"
        assert result["device_platform"] == "iOS"
        assert result["client_version"] == "2.3.1"
        assert result["client_build"] == "20250115.1"
        assert result["input_method"] == "text"
        assert "device_profiled_at_utc" in result

    @pytest.mark.asyncio
    async def test_run_with_tablet_envelope(self, sample_envelope_tablet):
        """Test complete profiling with tablet envelope."""
        result = await dp.run(sample_envelope_tablet)

        assert result["device_kind"] == "tablet"
        assert result["device_platform"] == "iOS"
        assert result["input_method"] == "photo"

    @pytest.mark.asyncio
    async def test_run_with_watch_envelope(self, sample_envelope_watch):
        """Test complete profiling with watch envelope."""
        result = await dp.run(sample_envelope_watch)

        assert result["device_kind"] == "watch"
        assert result["device_platform"] == "iOS"
        assert result["input_method"] == "voice"

    @pytest.mark.asyncio
    async def test_run_with_web_envelope(self, sample_envelope_web):
        """Test complete profiling with web envelope."""
        result = await dp.run(sample_envelope_web)

        assert result["device_kind"] == "web"
        assert result["device_platform"] == "web"
        assert result["input_method"] == "text"

    @pytest.mark.asyncio
    async def test_run_with_api_envelope(self, sample_envelope_api):
        """Test complete profiling with API envelope."""
        result = await dp.run(sample_envelope_api)

        assert result["device_kind"] == "api"
        assert result["device_platform"] == "unknown"
        assert result["input_method"] == "import"

    @pytest.mark.asyncio
    async def test_run_idempotency(self, sample_envelope_phone):
        """Test idempotency: same envelope → same result."""
        result1 = await dp.run(sample_envelope_phone)
        result2 = await dp.run(sample_envelope_phone)

        # Timestamps will differ, so exclude them
        for key in [
            "device_id",
            "device_kind",
            "device_platform",
            "client_version",
            "input_method",
        ]:
            assert result1[key] == result2[key]


# =============================================================================
# TEST GROUP 6: Performance Tests (3 tests)
# =============================================================================


class TestPerformance:
    """Test performance against <2ms P95 budget."""

    @pytest.mark.asyncio
    async def test_run_latency_batch(self, sample_envelope_phone):
        """Test async run() latency for batch of 1000 profiles (P95 < 2ms)."""
        latencies = []

        for _ in range(1000):
            start = time.perf_counter()
            await dp.run(sample_envelope_phone)
            end = time.perf_counter()
            latencies.append((end - start) * 1000)  # Convert to milliseconds

        latencies.sort()
        p50 = latencies[int(len(latencies) * 0.50)]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]

        print("\n📊 Latency Results (n=1000):")
        print(f"   P50: {p50:.4f}ms")
        print(f"   P95: {p95:.4f}ms (budget: <2ms)")
        print(f"   P99: {p99:.4f}ms")

        # Performance assertion
        assert p95 < 2.0, f"P95 latency {p95:.4f}ms exceeds 2ms budget"

    @pytest.mark.asyncio
    async def test_throughput_single_thread(self, sample_envelope_phone):
        """Test throughput (target: >500 ops/sec single-threaded)."""
        num_ops = 1000
        start = time.perf_counter()

        for _ in range(num_ops):
            await dp.run(sample_envelope_phone)

        elapsed = time.perf_counter() - start
        throughput = num_ops / elapsed

        print(f"\n🚀 Throughput: {throughput:,.0f} ops/sec")

        # Throughput assertion (expect >500 ops/sec)
        assert throughput > 500, f"Throughput {throughput:.0f} ops/sec below 500 target"

    def test_profile_device_context_latency(self):
        """Test profile_device_context() latency (<1ms for pure string parsing)."""
        latencies = []

        for _ in range(1000):
            start = time.perf_counter()
            dp.profile_device_context(
                device_id="device-dad-phone",
                user_agent="FamilyOS/2.3.1 (iOS 17.1; iPhone15,2)",
                client_version_str="2.3.1+20250115.1",
                input_source="text_entry",
            )
            end = time.perf_counter()
            latencies.append((end - start) * 1000)

        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]

        print(f"\n⚡ profile_device_context() P95: {p95:.4f}ms")

        # Should be < 1ms for pure string parsing
        assert p95 < 1.0, f"P95 latency {p95:.4f}ms exceeds 1ms"


# =============================================================================
# TEST GROUP 7: Metrics Tests (2 tests)
# =============================================================================


class TestMetrics:
    """Test metrics tracking for observability."""

    @pytest.mark.asyncio
    async def test_metrics_tracking(
        self, sample_envelope_phone, sample_envelope_tablet, sample_envelope_watch
    ):
        """Test metrics increment correctly for different device kinds."""
        dp.reset_metrics()

        # Profile 3 phones, 2 tablets, 1 watch
        for _ in range(3):
            await dp.run(sample_envelope_phone)
        for _ in range(2):
            await dp.run(sample_envelope_tablet)
        await dp.run(sample_envelope_watch)

        metrics = dp.get_metrics()

        assert metrics["total_profiles"] == 6
        assert metrics["device_kind_phone"] == 3
        assert metrics["device_kind_tablet"] == 2
        assert metrics["device_kind_watch"] == 1
        assert metrics["platform_ios"] == 6
        assert metrics["input_method_text"] == 3
        assert metrics["input_method_photo"] == 2
        assert metrics["input_method_voice"] == 1

    def test_reset_metrics(self):
        """Test metrics reset works correctly."""
        # Profile some devices
        dp.profile_device_context("device-dad-phone")
        dp.profile_device_context("device-mom-tablet")

        # Reset
        dp.reset_metrics()

        metrics = dp.get_metrics()
        assert metrics["total_profiles"] == 0
        assert metrics["device_kind_phone"] == 0
        assert metrics["device_kind_tablet"] == 0


# =============================================================================
# TEST GROUP 8: Edge Cases (5 tests)
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_run_with_missing_device_id(self):
        """Test handling of missing device_id (should default to 'unknown')."""
        envelope = {"metadata": {}}
        result = await dp.run(envelope)

        assert result["device_id"] == "unknown"
        assert result["device_kind"] == "phone"  # Default fallback

    @pytest.mark.asyncio
    async def test_run_with_missing_metadata(self):
        """Test handling of missing metadata (should use defaults)."""
        envelope = {"device_id": "device-dad-phone"}
        result = await dp.run(envelope)

        assert result["device_id"] == "device-dad-phone"
        assert result["device_kind"] == "phone"
        assert result["device_platform"] == "unknown"  # No user_agent to detect platform
        assert result["client_version"] is None
        assert result["input_method"] == "text"  # Default

    @pytest.mark.asyncio
    async def test_run_with_empty_envelope(self):
        """Test handling of empty envelope (should use all defaults)."""
        envelope = {}
        result = await dp.run(envelope)

        assert result["device_id"] == "unknown"
        assert result["device_kind"] == "phone"
        assert result["input_method"] == "text"

    def test_classify_case_insensitive(self):
        """Test device kind classification is case-insensitive."""
        assert dp.classify_device_kind("DEVICE-DAD-PHONE") == "phone"
        assert dp.classify_device_kind("Device-Mom-Tablet") == "tablet"
        assert dp.classify_device_kind("device-teen-WATCH") == "watch"

    @pytest.mark.asyncio
    async def test_concurrent_profiling(self, sample_envelope_phone, sample_envelope_tablet):
        """Test concurrent profiling (thread-safety check)."""
        tasks = []
        for _ in range(50):
            tasks.append(dp.run(sample_envelope_phone))
            tasks.append(dp.run(sample_envelope_tablet))

        results = await asyncio.gather(*tasks)

        # Verify all 100 results returned
        assert len(results) == 100

        # Verify metrics are correct (50 phones + 50 tablets)
        metrics = dp.get_metrics()
        assert metrics["total_profiles"] == 100
        assert metrics["device_kind_phone"] == 50
        assert metrics["device_kind_tablet"] == 50


# =============================================================================
# RUN ALL TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
    pytest.main([__file__, "-v", "--tb=short", "-s"])
