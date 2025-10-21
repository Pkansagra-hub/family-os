"""Shared helpers for modelling cluster topologies in Pulumi stacks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Sequence


def _empty_str_list() -> List[str]:
    return []


def _empty_volume_list() -> List["PersistentVolumeSpec"]:
    return []


def _empty_services() -> Dict[str, Any]:
    return {}


@dataclass(slots=True)
class PersistentVolumeSpec:
    """Description of a persistent volume required by a node tier."""

    name: str
    size_gib: int
    mount_path: str
    storage_class: str = "local-path"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "size_gib": self.size_gib,
            "mount_path": self.mount_path,
            "storage_class": self.storage_class,
        }


@dataclass(slots=True)
class NodeTier:
    """Grouping of nodes that share sizing and placement characteristics."""

    name: str
    role: str
    count: int
    cpu_cores: int
    memory_gib: int
    storage_gib: int
    description: str
    placement_zones: List[str] = field(default_factory=_empty_str_list)
    persistent_volumes: List[PersistentVolumeSpec] = field(
        default_factory=_empty_volume_list
    )

    def iter_nodes(self) -> Iterator[Dict[str, Any]]:
        zones = self.placement_zones or ["unspecified"]
        for index in range(self.count):
            zone = zones[index % len(zones)]
            yield {
                "name": f"{self.role}-{index + 1}",
                "role": self.role,
                "cpu_cores": self.cpu_cores,
                "memory_gib": self.memory_gib,
                "storage_gib": self.storage_gib,
                "placement_zone": zone,
            }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "count": self.count,
            "cpu_cores": self.cpu_cores,
            "memory_gib": self.memory_gib,
            "storage_gib": self.storage_gib,
            "description": self.description,
            "placement_zones": list(self.placement_zones),
            "nodes": list(self.iter_nodes()),
            "persistent_volumes": [
                volume.to_dict() for volume in self.persistent_volumes
            ],
        }


@dataclass(slots=True)
class ClusterTopology:
    """Top-level topology description exported by deployment stacks."""

    stack: str
    tiers: List[NodeTier]
    services: Dict[str, Any] = field(default_factory=_empty_services)

    def total_nodes(self) -> int:
        return sum(tier.count for tier in self.tiers)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stack": self.stack,
            "total_nodes": self.total_nodes(),
            "tiers": [tier.to_dict() for tier in self.tiers],
            "services": self.services,
        }

    def scaling_metadata(self) -> Dict[str, Any]:
        return {
            "total_nodes": self.total_nodes(),
            "tier_summaries": [
                {
                    "name": tier.name,
                    "count": tier.count,
                    "cpu_cores_per_node": tier.cpu_cores,
                    "memory_gib_per_node": tier.memory_gib,
                    "storage_gib_per_node": tier.storage_gib,
                    "placement_zones": list(tier.placement_zones),
                    "persistent_volumes": [
                        volume.to_dict() for volume in tier.persistent_volumes
                    ],
                }
                for tier in self.tiers
            ],
            "services": self.services,
        }


def generate_zone_names(prefix: str, count: int) -> List[str]:
    """Return a deterministic set of placement zone identifiers."""

    zones: List[str] = []
    for index in range(count):
        zones.append(f"{prefix}-{index + 1:02d}")
    return zones


def expand_nodes(count: int, zones: Sequence[str]) -> Iterable[str]:
    """Return a zone assigned identifier for each node index."""

    zone_cycle = list(zones) or ["unspecified"]
    for index in range(count):
        yield zone_cycle[index % len(zone_cycle)]
        yield zone_cycle[index % len(zone_cycle)]
        yield zone_cycle[index % len(zone_cycle)]
