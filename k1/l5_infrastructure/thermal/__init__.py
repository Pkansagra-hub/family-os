"""
Layer 5 - Thermal Management Module

This module provides thermal-aware model placement and device temperature monitoring
for K1's 4-tier inference cascade (NPU→GPU→CPU→Remote).

Components:
- placement_planner: Thermal-aware model placement with hysteresis FSM
- monitor: Device temperature monitoring (NPU/GPU/CPU sensors)

Thermal Zones (ADR-0026a):
- COOL (<70°C): All accelerators available
- WARM (70-74°C): All accelerators available
- HOT (75-84°C): NPU disabled, GPU/CPU/Remote available
- CRITICAL (85-95°C): NPU/GPU disabled, CPU/Remote available
- EMERGENCY (>95°C): All local disabled, Remote only

Hysteresis (ADR-0026b, ADR-0026c):
- Asymmetric thresholds: +5°C upgrade, -2°C downgrade (7°C band)
- Cooldown periods: 10s upgrade, 30-60s downgrade (3:1 to 6:1 ratio)
- Dead zone: Temperatures within zone maintain current state
- Emergency jump: CRITICAL → Remote (immediate, skip GPU/CPU)

4-Tier Placement Cascade (ADR-0027):
- NPU (30ms, 10W): Optimal on-device inference
- GPU (50ms, 12W): Fallback for NPU overload
- CPU (120ms, 15W): Fallback for GPU overload
- Remote (500ms, 5W): Cloud inference (last resort)

Performance (ADR-0024):
- Placement decision: <10ms P95
- Temperature read: <5ms P95
- Thermal polling: 1 Hz
- Failover latency: <100ms total

Primary ADRs:
- ADR-0026: Thermal Management (hysteresis matrix, 4-tier placement)
- ADR-0027: Model Placement Cascade (NPU→GPU→CPU→Remote)
- ADR-0024: Performance Budgets (placement <10ms, monitoring <5ms)

Research Foundation:
- Thermal hysteresis control (HVAC systems, embedded computing)
- Dynamic voltage and frequency scaling (DVFS)
- Mobile device thermal throttling (iPhone, Android)
"""

# __all__ = [
#     "PlacementPlanner",
#     "ThermalMonitor",
# ]
