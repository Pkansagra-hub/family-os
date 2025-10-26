"""
WARD tests for ThermalMonitor component.

Tests cross-platform sensor monitoring, thermal zone classification,
hysteresis FSM integration, and Prometheus metrics emission.
"""

import asyncio
import time

from ward import fixture, test

# Import thermal components
from k1.l5_infrastructure.thermal.monitor import (ThermalMonitor,
                                                  ThermalStatus, ThermalZone)
from k1.l5_infrastructure.thermal.placement_planner import (Accelerator,
                                                            HysteresisFSM,
                                                            PlacementPlanner)


@fixture
async def thermal_monitor():
    """Real ThermalMonitor instance for testing."""
    monitor = ThermalMonitor()
    yield monitor
    # Cleanup if needed
    try:
        await monitor.stop_monitoring()
    except Exception:
        pass


@fixture(scope="module")
def hysteresis_fsm():
    """Real HysteresisFSM instance for testing."""
    return HysteresisFSM()


@test("ThermalMonitor initializes with correct platform detection")
def _(monitor=thermal_monitor):
    """Test that ThermalMonitor detects platform correctly."""
    import platform
    expected_platform = platform.system().lower()
    assert monitor._platform == expected_platform


@test("ThermalMonitor discovers sensors on initialization")
def _(monitor=thermal_monitor):
    """Test that sensor discovery runs during initialization."""
    # Should have attempted sensor discovery
    assert hasattr(monitor, '_sensor_paths')
    assert isinstance(monitor._sensor_paths, dict)


@test("ThermalZone classification works correctly")
def _(monitor=thermal_monitor):
    """Test thermal zone classification logic."""
    # Test all zone boundaries
    assert monitor._classify_thermal_zone(30) == ThermalZone.COOL
    assert monitor._classify_thermal_zone(59) == ThermalZone.COOL
    assert monitor._classify_thermal_zone(60) == ThermalZone.WARM
    assert monitor._classify_thermal_zone(74) == ThermalZone.WARM
    assert monitor._classify_thermal_zone(75) == ThermalZone.HOT
    assert monitor._classify_thermal_zone(84) == ThermalZone.HOT
    assert monitor._classify_thermal_zone(85) == ThermalZone.CRITICAL
    assert monitor._classify_thermal_zone(94) == ThermalZone.CRITICAL
    assert monitor._classify_thermal_zone(95) == ThermalZone.EMERGENCY
    assert monitor._classify_thermal_zone(100) == ThermalZone.EMERGENCY


@test("HysteresisFSM initializes in COOL state")
def _(fsm=hysteresis_fsm):
    """Test HysteresisFSM starts in COOL state."""
    assert fsm.get_current_zone() == ThermalZone.COOL
    assert fsm.min_state_duration_seconds == 10
    assert fsm.upgrade_cooldown_seconds == 10


@test("HysteresisFSM upgrade thresholds are correct")
def _(fsm=hysteresis_fsm):
    """Test upgrade threshold configuration."""
    expected_upgrades = {
        ThermalZone.COOL: 60,
        ThermalZone.WARM: 75,
        ThermalZone.HOT: 85,
        ThermalZone.CRITICAL: 95,
    }
    assert fsm.upgrade_thresholds == expected_upgrades


@test("HysteresisFSM downgrade thresholds implement 5°C buffer")
def _(fsm=hysteresis_fsm):
    """Test downgrade thresholds provide 5°C hysteresis buffer."""
    expected_downgrades = {
        ThermalZone.WARM: 55,      # 60 - 5
        ThermalZone.HOT: 70,       # 75 - 5
        ThermalZone.CRITICAL: 80,  # 85 - 5
        ThermalZone.EMERGENCY: 90, # 95 - 5
    }
    assert fsm.downgrade_thresholds == expected_downgrades


@test("HysteresisFSM prevents rapid transitions with cooldown")
async def _(fsm=hysteresis_fsm):
    """Test cooldown timers prevent thermal flapping."""
    # Start in COOL
    assert fsm.get_current_zone() == ThermalZone.COOL

    # Immediate upgrade to WARM (should work)
    new_zone = fsm.update_temperature(65)  # Above 60°C
    assert new_zone == ThermalZone.WARM

    # Immediate downgrade back (should be blocked by cooldown)
    new_zone = fsm.update_temperature(50)  # Below 55°C
    assert new_zone is None  # Blocked by cooldown

    # Wait for cooldown and try again
    await asyncio.sleep(11)  # Wait > 10s upgrade cooldown
    new_zone = fsm.update_temperature(50)
    assert new_zone == ThermalZone.COOL


@test("HysteresisFSM emergency jump bypasses all timers")
def _(fsm=hysteresis_fsm):
    """Test emergency jump forces immediate EMERGENCY state."""
    # Start in COOL
    assert fsm.get_current_zone() == ThermalZone.COOL

    # Force emergency jump
    jumped = fsm.force_emergency_jump()
    assert jumped is True
    assert fsm.get_current_zone() == ThermalZone.EMERGENCY

    # Second jump should return False (already in EMERGENCY)
    jumped = fsm.force_emergency_jump()
    assert jumped is False


@test("PlacementPlanner initializes with correct accelerator profiles")
def _():
    """Test PlacementPlanner has correct accelerator configurations."""
    planner = PlacementPlanner()

    # Check NPU profile
    npu = planner.accelerator_profiles[Accelerator.NPU]
    assert npu.latency_ms == 30
    assert npu.power_watts == 10
    assert ThermalZone.COOL in npu.supported_thermal_zones
    assert ThermalZone.WARM in npu.supported_thermal_zones
    assert ThermalZone.HOT not in npu.supported_thermal_zones

    # Check Remote profile (works in all zones)
    remote = planner.accelerator_profiles[Accelerator.REMOTE]
    assert remote.latency_ms == 500
    assert ThermalZone.EMERGENCY in remote.supported_thermal_zones


@test("PlacementPlanner 4-tier cascade works correctly")
def _():
    """Test accelerator selection follows 4-tier cascade."""
    planner = PlacementPlanner()

    # COOL zone: NPU → GPU → CPU → Remote
    accelerator = planner._select_accelerator_cascade(ThermalZone.COOL, None)
    assert accelerator == Accelerator.NPU

    # HOT zone: GPU → CPU → Remote (NPU disabled)
    accelerator = planner._select_accelerator_cascade(ThermalZone.HOT, None)
    assert accelerator == Accelerator.GPU

    # CRITICAL zone: CPU → Remote
    accelerator = planner._select_accelerator_cascade(ThermalZone.CRITICAL, None)
    assert accelerator == Accelerator.CPU

    # EMERGENCY zone: Remote only
    accelerator = planner._select_accelerator_cascade(ThermalZone.EMERGENCY, None)
    assert accelerator == Accelerator.REMOTE


@test("PlacementPlanner generates correct reasoning")
def _():
    """Test placement decision reasoning is human-readable."""
    planner = PlacementPlanner()

    # Emergency reasoning
    reasoning = planner._get_placement_reasoning(Accelerator.REMOTE, ThermalZone.EMERGENCY)
    assert "Emergency" in reasoning
    assert "Remote" in reasoning

    # Normal reasoning
    reasoning = planner._get_placement_reasoning(Accelerator.NPU, ThermalZone.COOL)
    assert "Optimal" in reasoning
    assert "NPU" in reasoning
    assert "30ms" in reasoning


@test("ThermalMonitor polling loop updates status")
async def _(monitor=thermal_monitor):
    """Test that polling loop updates thermal status."""
    # Start monitoring
    await monitor.start_monitoring()

    # Wait for a few polling cycles
    await asyncio.sleep(2.5)  # Should get at least 2 readings

    # Check that status was updated
    status = monitor.get_thermal_status()
    assert status is not None
    assert isinstance(status.max_temperature_celsius, float)
    assert isinstance(status.thermal_zone, ThermalZone)

    # Stop monitoring
    await monitor.stop_monitoring()


@test("ThermalMonitor handles sensor failures gracefully")
async def _(monitor=thermal_monitor):
    """Test graceful degradation when sensors fail."""
    # Mock sensor reading to always fail
    original_read = monitor._read_sensor_temperature

    async def failing_read(sensor_id, sensor_path):
        return None

    monitor._read_sensor_temperature = failing_read

    try:
        # Start monitoring
        await monitor.start_monitoring()
        await asyncio.sleep(1.5)  # Wait for polling

        # Should default to WARM state
        status = monitor.get_thermal_status()
        assert status is not None
        assert status.thermal_zone == ThermalZone.WARM
        assert status.max_temperature_celsius == 70.0

    finally:
        monitor._read_sensor_temperature = original_read
        await monitor.stop_monitoring()


@test("Integration: ThermalMonitor + PlacementPlanner work together")
async def _(monitor=thermal_monitor):
    """Test end-to-end thermal monitoring to placement decision."""
    planner = PlacementPlanner(thermal_monitor=monitor)

    # Start monitoring
    await monitor.start_monitoring()
    await asyncio.sleep(1.5)  # Let it poll

    # Get placement decision
    decision = planner.choose_accelerator()

    # Should have valid decision
    assert isinstance(decision.accelerator, Accelerator)
    assert isinstance(decision.thermal_zone, ThermalZone)
    assert decision.confidence == 1.0
    assert len(decision.reasoning) > 0

    await monitor.stop_monitoring()


@test("Performance: Placement decision under 10ms")
def _():
    """Test placement decision meets <10ms performance budget."""
    planner = PlacementPlanner()

    import time
    start = time.perf_counter()

    # Make multiple decisions to get average
    for _ in range(100):
        planner.choose_accelerator()

    elapsed_ms = (time.perf_counter() - start) * 1000 / 100

    assert elapsed_ms < 10, f"Placement decision took {elapsed_ms:.2f}ms, exceeds 10ms budget"


@test("State change callbacks work correctly")
async def _(monitor=thermal_monitor):
    """Test thermal state change notifications."""
    callback_called = []

    def test_callback(zone):
        callback_called.append(zone)

    monitor.on_state_change(test_callback)

    # Simulate state change by directly setting status
    # (In real usage this would happen during polling)
    monitor._current_status = ThermalStatus(
        max_temperature_celsius=80,
        thermal_zone=ThermalZone.HOT,
        sensor_readings=[],
        timestamp_ms=int(time.time() * 1000)
    )

    # Manually trigger callback (normally done in polling loop)
    for callback in monitor._state_callbacks:
        callback(ThermalZone.HOT)

    assert len(callback_called) == 1
    assert callback_called[0] == ThermalZone.HOT        callback(ThermalZone.HOT)

    assert len(callback_called) == 1
    assert callback_called[0] == ThermalZone.HOT
