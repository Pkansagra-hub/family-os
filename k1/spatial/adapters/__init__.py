"""Production and default adapters for k1.spatial."""

from __future__ import annotations

from k1.spatial.adapters.bridge_place_registry_adapter import BridgePlaceRegistryAdapter
from k1.spatial.adapters.browser_device_location_adapter import (
    BrowserDeviceLocationAdapter,
)
from k1.spatial.adapters.device_context_adapter import SpatialDeviceContextAdapter
from k1.spatial.adapters.event_bus_adapter import SpatialEventBusAdapter
from k1.spatial.adapters.local_place_registry_adapter import LocalPlaceRegistryAdapter
from k1.spatial.adapters.nominatim_geocoder_adapter import NominatimGeocoderAdapter
from k1.spatial.adapters.null_device_location_adapter import NullDeviceLocationAdapter
from k1.spatial.adapters.null_geocoder_adapter import NullGeocoderAdapter
from k1.spatial.adapters.null_metrics_adapter import NullSpatialMetricsAdapter
from k1.spatial.adapters.null_presence_adapter import NullPresenceAdapter
from k1.spatial.adapters.selfmodel_policy_adapter import SelfModelSpatialPolicyAdapter
from k1.spatial.adapters.session_state_adapter import SpatialStateAdapter
from k1.spatial.adapters.uuid_id_adapter import UUIDSpatialIdAdapter

__all__ = [
    "BridgePlaceRegistryAdapter",
    "BrowserDeviceLocationAdapter",
    "LocalPlaceRegistryAdapter",
    "NullDeviceLocationAdapter",
    "NullGeocoderAdapter",
    "NullPresenceAdapter",
    "NullSpatialMetricsAdapter",
    "NominatimGeocoderAdapter",
    "SelfModelSpatialPolicyAdapter",
    "SpatialDeviceContextAdapter",
    "SpatialEventBusAdapter",
    "SpatialStateAdapter",
    "UUIDSpatialIdAdapter",
]
