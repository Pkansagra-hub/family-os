"""
Coarse Location Classifier

ADR References:
- ADR-0085a: Location Awareness - Coarse Location Classifier

Purpose:
Classifies location into 4 coarse categories (HOME, WORK, TRAVELING, UNKNOWN)
using WiFi SSID matching and GPS proximity checks.

Performance Budget:
- Classification latency: <100ms
- Categories: 4 (HOME, WORK, TRAVELING, UNKNOWN)
- WiFi matching: Direct SSID lookup
- GPS proximity: <100m radius
- Privacy band: GREEN (safe to sync)

Components:
- WiFi SSID direct match (known networks)
- GPS proximity check (<100m from home/work)
- Traveling detection (>10km from home/work)
- Haversine distance calculation
- Context-aware response adaptation

Key Responsibilities:
1. Match WiFi SSID to known locations (HOME, WORK)
2. Check GPS proximity to known locations (<100m)
3. Detect traveling state (>10km from home/work)
4. Calculate haversine distance for proximity
5. Emit CoarseLocationChanged events (GREEN band)

Categories:
- HOME: WiFi SSID match OR GPS within 100m of home
- WORK: WiFi SSID match OR GPS within 100m of work
- TRAVELING: >10km from both home and work
- UNKNOWN: None of the above

Integration Points:
- WiFi Triangulator: SSID data (ADR-0085a)
- GPS Tracker: Coordinate data (ADR-0085a)
- SessionState: Update coarse_location context
- EventBus: Publish CoarseLocationChanged events (GREEN band)

Contracts to Review:
- contracts/flatbuffers/coarse_location_changed_event.fbs
- contracts/location/coarse_categories.yml
"""

# TODO: Implement WiFi SSID matching (known networks)
# TODO: Implement GPS proximity check (<100m radius)
# TODO: Implement traveling detection (>10km threshold)
# TODO: Implement haversine distance calculation
# TODO: Emit CoarseLocationChanged events (GREEN band)
# TODO: Update SessionState coarse_location context
# TODO: Add Prometheus metrics (classification_latency_ms) (ADR-0029)
