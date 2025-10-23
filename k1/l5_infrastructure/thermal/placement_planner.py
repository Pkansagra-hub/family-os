"""
Thermal-Aware Model Placement Planner

Purpose: Choose optimal accelerator (NPU/GPU/CPU/Remote) based on device thermal state
Location: k1/l5_infrastructure/thermal/placement_planner.py
Performance: <10ms placement decision

Primary ADRs:
- ADR-0026: Thermal Management (hysteresis matrix, 4-tier placement)
- ADR-0026a: Thermal Zones (5 zones: COOL/WARM/HOT/CRITICAL/EMERGENCY)
- ADR-0026b: Hysteresis FSM (state transitions, dead zone, persistence)
- ADR-0026c: Hysteresis Matrix (asymmetric thresholds, cooldown periods)
- ADR-0026d: Throttling (HOT/CRITICAL/EMERGENCY state degradation)
- ADR-0027: Model Placement Cascade (NPU→GPU→CPU→Remote)

Related ADRs:
- ADR-0024: Performance Budgets (placement <10ms)
- ADR-0029: Prometheus Metrics (device temperature, placement decisions)
- ADR-0009: Circuit Breaker (failure detection integration)

Key Responsibilities:

1. 4-Tier Placement Strategy:
   - NPU (30ms, 10W): Optimal for on-device inference
   - GPU (50ms, 12W): Fallback for NPU overload/thermal
   - CPU (120ms, 15W): Fallback for GPU overload/thermal
   - Remote (500ms, 5W): Cloud inference (last resort)

2. Thermal Zone Management:
   - COOL (<70°C): All accelerators available
   - WARM (70-74°C): All accelerators available
   - HOT (75-84°C): NPU disabled, GPU/CPU/Remote available
   - CRITICAL (85-95°C): NPU/GPU disabled, CPU/Remote available
   - EMERGENCY (>95°C): All local disabled, Remote only

3. Hysteresis FSM:
   - 5°C buffer prevents oscillation (upgrade +5°C, downgrade -2°C, 7°C band)
   - Cooldown periods: 10s upgrade, 30-60s downgrade (3:1 to 6:1 ratio)
   - Dead zone: Temperatures within zone maintain current state
   - State persistence: Minimum 10s duration (exception: EMERGENCY)
   - Emergency jump: CRITICAL → Remote (immediate, <50ms)

4. Placement Decision Logic:
   - Monitor device temperature (1 Hz polling)
   - Choose accelerator based on thermal zone + availability
   - State-aware policies: COOL/WARM (all), HOT (GPU/CPU/Remote), CRITICAL (CPU/Remote), EMERGENCY (Remote)
   - Automatic failover: Running models migrate on thermal state change
   - Failover: KV cache transfer <30ms, model loading <50ms, <100ms total

5. Throttling Strategies:
   - HOT: Increase batch interval 20% (100ms → 120ms), defer background tasks
   - CRITICAL: Skip persona/grounding/vision, simplified responses
   - EMERGENCY: Reject new turns, notify user "Device cooling down", Remote only

Performance Metrics:
- Placement decision: <10ms P95 (<5ms typical)
- Thermal polling: 1 Hz
- Temperature read: <5ms P95
- Failover latency: <100ms (detection 20ms + transfer 30ms + loading 50ms)
- Emergency jump: <50ms (CRITICAL → Remote)
- State persistence: ≥10s (prevent rapid switching)

Implementation Notes:
- Hysteresis FSM prevents thermal oscillation (5°C buffer)
- Asymmetric thresholds: Faster heat response, slower cool response
- Cooldown timers enforce minimum state duration
- Emergency path bypasses normal cascade (safety priority)
- KV cache migration preserves conversation context during failover

Example Usage:
    planner = PlacementPlanner(thermal_monitor)

    # Get optimal accelerator for current thermal state
    accelerator = planner.choose_accelerator(model_config)
    # Returns: "NPU" | "GPU" | "CPU" | "Remote"

    # Handle thermal state change (automatic migration)
    if planner.should_migrate(current_accelerator):
        new_accelerator = planner.choose_accelerator(model_config)
        # Trigger KV cache transfer + model reload

Research Foundation:
- Thermal hysteresis control (HVAC systems, Schmitt trigger)
- Dynamic voltage and frequency scaling (DVFS, Intel SpeedStep, ARM big.LITTLE)
- Mobile device thermal throttling (iPhone A-series, Android Snapdragon)
- Embedded system thermal management (automotive, aerospace)

TODO:
- [ ] Implement ThermalZone enum (COOL/WARM/HOT/CRITICAL/EMERGENCY)
- [ ] Implement Hysteresis FSM with 5°C buffer and cooldown timers
- [ ] Implement 4-tier placement logic (NPU→GPU→CPU→Remote)
- [ ] Implement automatic failover on thermal state change
- [ ] Implement throttling strategies (HOT/CRITICAL/EMERGENCY)
- [ ] Implement emergency jump path (CRITICAL → Remote, <50ms)
- [ ] Add Prometheus metrics (placement_decisions, thermal_failovers, emergency_jumps)
- [ ] Add state persistence enforcement (minimum 10s duration)
- [ ] Integrate with ThermalMonitor for 1 Hz temperature polling
- [ ] Implement KV cache migration during failover (<30ms)
- [ ] Add unit tests for hysteresis FSM transitions
- [ ] Add integration tests for 4-tier cascade with thermal simulation
"""

# TODO: Implement PlacementPlanner class with hysteresis FSM
