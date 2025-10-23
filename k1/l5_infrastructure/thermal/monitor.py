"""
Device Temperature Monitor

Purpose: Monitor NPU/GPU/CPU temperature sensors for thermal management
Location: k1/l5_infrastructure/thermal/monitor.py
Performance: <5ms temperature read

Primary ADRs:
- ADR-0026: Thermal Management (monitoring integration)
- ADR-0026a: Thermal Zones (sensor monitoring, state detection)

Related ADRs:
- ADR-0024: Performance Budgets (temperature read <5ms)
- ADR-0029: Prometheus Metrics (thermal_temperature_celsius, thermal_state gauges)

Key Responsibilities:

1. Temperature Monitoring:
   - Poll NPU/GPU/CPU temperature sensors (1 Hz)
   - Thermal zones: COOL (<70°C), WARM (70-74°C), HOT (75-84°C), CRITICAL (85-95°C), EMERGENCY (>95°C)
   - Alert on CRITICAL (≥85°C) or EMERGENCY (≥95°C)
   - Multi-sensor aggregation (max temperature rule)

2. Cross-Platform Support:
   - Linux: /sys/class/thermal/thermal_zone*/temp
   - Windows: WMI (Win32_TemperatureProbe)
   - macOS: IOKit (SMC sensors)
   - Graceful degradation on sensor unavailability

3. Metrics Emission:
   - thermal_temperature_celsius gauge (per device: NPU/GPU/CPU)
   - thermal_state gauge (0=COOL, 1=WARM, 2=HOT, 3=CRITICAL, 4=EMERGENCY)
   - thermal_alerts_total counter (HOT/CRITICAL/EMERGENCY)
   - Push to Prometheus every 10s

4. State Detection:
   - Zone classification: <0.2ms (simple threshold comparison)
   - Alert latency: <100ms (detection + notification)
   - State propagation to PlacementPlanner

Performance Metrics:
- Temperature read: <5ms P95 (<3ms typical)
- Polling frequency: 1 Hz
- Alert latency: <100ms
- State detection: <0.2ms (zone classification)
- Multi-sensor aggregation: <1ms

Implementation Notes:
- Use asyncio for 1 Hz polling loop
- Cache sensor paths for fast reads (<1ms lookup)
- Max temperature rule for multi-sensor aggregation
- Graceful degradation: Default to WARM state on sensor failure
- Alert throttling: Max 1 alert per minute per zone (prevent spam)

Example Usage:
    monitor = ThermalMonitor()
    await monitor.start_monitoring()

    # Get current temperature
    temp = await monitor.get_temperature("NPU")  # Returns: float (Celsius)

    # Get thermal state
    state = monitor.get_thermal_state()  # Returns: ThermalZone enum

    # Register callback for state changes
    monitor.on_state_change(lambda zone: print(f"Thermal state: {zone}"))

Research Foundation:
- Thermal sensor polling (Linux hwmon, Windows WMI, macOS SMC)
- Multi-sensor fusion (max/avg/weighted strategies)
- Alert throttling (debouncing, rate limiting)

TODO:
- [ ] Implement cross-platform temperature sensor access (Linux/Windows/macOS)
- [ ] Implement 1 Hz polling loop with asyncio
- [ ] Implement thermal zone classification (<0.2ms)
- [ ] Implement multi-sensor aggregation (max temperature rule)
- [ ] Implement alert system (CRITICAL ≥85°C, EMERGENCY ≥95°C)
- [ ] Add Prometheus metrics (thermal_temperature_celsius, thermal_state, thermal_alerts_total)
- [ ] Add graceful degradation on sensor failure (default WARM state)
- [ ] Add alert throttling (max 1 alert/min per zone)
- [ ] Implement state change callbacks for PlacementPlanner integration
- [ ] Add unit tests for zone classification logic
- [ ] Add integration tests with mock sensor data
"""

# TODO: Implement ThermalMonitor class with 1 Hz polling
