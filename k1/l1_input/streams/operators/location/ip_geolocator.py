"""
IP Geolocation

ADR References:
- ADR-0085a: Location Awareness - IP Geolocation

Purpose:
City-level location precision using MaxMind GeoLite2 database (local lookup).
GREEN privacy band (safe to sync), fallback for all devices.

Performance Budget:
- Precision: ~5km (city-level)
- Lookup latency: <100ms P95
- Privacy band: GREEN (safe to sync)
- Database: MaxMind GeoLite2 (local)

Components:
- MaxMind GeoLite2 database (local lookup)
- City-level precision (~5km radius)
- GREEN privacy band (safe to sync)
- Fallback location provider
- <100ms P95 lookup latency

Key Responsibilities:
1. Initialize MaxMind GeoLite2 database (local)
2. Lookup IP address → city/region/country
3. Return city-level coordinates (~5km precision)
4. Mark IP location as GREEN privacy band (safe to sync)
5. Serve as fallback when GPS/WiFi unavailable
6. Update latency <100ms P95

Integration Points:
- MaxMind GeoLite2: Local database lookup
- SessionState: Update location context (multimodal section)
- EventBus: Publish LocationUpdated events (GREEN band)

Contracts to Review:
- contracts/flatbuffers/location_updated_event.fbs
- contracts/privacy/location_privacy_bands.yml
"""

# TODO: Initialize MaxMind GeoLite2 database
# TODO: Implement IP lookup (IP → city/region/country)
# TODO: Return city-level coordinates (~5km precision)
# TODO: Mark IP location as GREEN privacy band
# TODO: Emit LocationUpdated events to EventBus
# TODO: Add Prometheus metrics (ip_geolocation_latency_ms) (ADR-0029)
