# Thermal Sensor Requirements

## Overview

The K1 thermal monitoring system requires real hardware thermal sensor access. Mock or simulated data is not permitted per development guidelines.

## Platform Requirements

### Windows

- **WMI Access**: Requires WMI service running and proper permissions
- **Performance Counters**: Access to `\\Thermal Zone Information(*)` counters
- **OpenHardwareMonitor**: Optional third-party tool for additional sensors
- **Vendor APIs**: Intel Power Gadget, NVIDIA NVML for GPU thermal data

### Linux

- **sysfs thermal zones**: `/sys/class/thermal/thermal_zone*/temp`
- **hwmon**: Hardware monitoring interfaces
- **Vendor drivers**: AMD Ryzen Master, NVIDIA NVML

### macOS

- **IOKit SMC**: System Management Controller access (requires special entitlements)
- **powermetrics**: Command-line thermal monitoring (requires sudo)
- **SMC tools**: Third-party SMC access utilities

## Development Environment Limitations

In development environments without hardware thermal sensors:

- Thermal drivers return empty sensor lists
- Thermal monitor defaults to WARM state (70°C)
- No mock data is generated
- System logs warnings about missing sensors

## Real Hardware Requirements

For production deployment, ensure:

1. Hardware has ACPI thermal zones (most modern systems)
2. WMI service is running (Windows)
3. Proper permissions for sensor access
4. Vendor-specific drivers installed (optional but recommended)

## Testing

Thermal system can be tested in environments without sensors:

- System gracefully degrades to WARM state
- No mock data is provided
- Proper logging of sensor discovery failures
- ADR-0026 thermal hysteresis logic remains functional
