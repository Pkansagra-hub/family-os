"""
GPS Tracker

ADR References:
- ADR-0085a: Location Awareness - GPS Tracking

Purpose:
High-precision GPS tracking (<10m accuracy) with RED privacy band protection.
GPS data is local-only and never synced; degraded to GREEN city-level before sync.

Performance Budget:
- Precision: <10m
- Update latency: <2s P95
- Privacy band: RED (local-only, never synced)
- Degradation: RED → GREEN city-level before sync

Components:
- CoreLocation (iOS) integration
- FusedLocationProvider (Android) integration
- High-precision GPS (<10m accuracy)
- Privacy enforcement (RED band, local-only)
- Degradation logic (RED → GREEN city-level)
- Permission management

Key Responsibilities:
1. Initialize platform-specific location provider (CoreLocation/FusedLocationProvider)
2. Request high-precision GPS updates (<10m)
3. Mark GPS data as RED privacy band (local-only)
4. Degrade to GREEN city-level before any sync (ADR-0085a)
5. Manage location permissions
6. Update latency <2s P95

Integration Points:
- Privacy Enforcement: Degrade RED → GREEN before sync (ADR-0085a)
- SessionState: Update location context (multimodal section)
- EventBus: Publish LocationUpdated events (RED band, local-only)

Contracts to Review:
- contracts/flatbuffers/location_updated_event.fbs
- contracts/privacy/location_privacy_bands.yml
"""

# TODO: Implement CoreLocation integration (iOS)
# TODO: Implement FusedLocationProvider integration (Android)
# TODO: Request high-precision GPS (<10m accuracy)
# TODO: Mark GPS data as RED privacy band
# TODO: Implement degradation logic (RED → GREEN city-level)
# TODO: Manage location permissions
# TODO: Add Prometheus metrics (gps_update_latency_ms) (ADR-0029)
