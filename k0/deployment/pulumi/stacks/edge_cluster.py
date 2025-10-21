"""Pulumi stack implementation for edge cluster deployments."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Sequence

from .. import _renderer
from ..bundle import BundleComponent, write_bundle_manifest
from ..components.secrets import SecretMaterial, sync_secrets
from ..components.storage import (
    StorageComponentResult,
    StorageLayerConfig,
    register_storage_components,
)
from ..components.telemetry import (
    TelemetryComponentResult,
    TelemetryConfig,
    provision_telemetry,
)
from ..secrets_artifacts import write_secret_artifacts
from .config_loader import load_configs, resolve_int
from .topology import (
    ClusterTopology,
    NodeTier,
    PersistentVolumeSpec,
    generate_zone_names,
)

logger = logging.getLogger(__name__)


def _default_secret_materials() -> List[SecretMaterial]:
    return []


@dataclass(slots=True)
class EdgeClusterSettings:
    """Edge cluster configuration envelope."""

    node_count: int
    storage: StorageLayerConfig
    telemetry: TelemetryConfig
    secrets: list[SecretMaterial] = field(default_factory=_default_secret_materials)
    placement_zones: Sequence[str] | None = None
    control_plane_cpu: int = 4
    control_plane_memory_gib: int = 16
    control_plane_storage_gib: int = 128
    worker_cpu: int = 2
    worker_memory_gib: int = 8
    worker_storage_gib: int = 64


STACK_NAME = "edge-cluster"
CLUSTER_CONFIG_NAMESPACE = "k0-edge"


def _ensure_node_counts(node_count: int) -> tuple[int, int]:
    if node_count < 1:
        raise ValueError("Edge cluster requires at least one node")
    control_plane = min(3, node_count)
    worker_nodes = max(node_count - control_plane, 0)
    return control_plane, worker_nodes


def _build_topology(settings: EdgeClusterSettings) -> ClusterTopology:
    control_count, worker_count = _ensure_node_counts(settings.node_count)
    zones = list(
        settings.placement_zones
        or generate_zone_names("edge-zone", max(settings.node_count, 1))
    )
    if not zones:
        zones = ["edge-zone-01"]

    control_zones = zones[:control_count] or [zones[0]]
    worker_zone_offset = control_count % len(zones) if zones else 0
    worker_zones = zones[worker_zone_offset:] or zones

    control_tier = NodeTier(
        name="control-plane",
        role="control",
        count=control_count,
        cpu_cores=settings.control_plane_cpu,
        memory_gib=settings.control_plane_memory_gib,
        storage_gib=settings.control_plane_storage_gib,
        description="Coordinates scheduler, API ingress, and secret synchronisation for the edge cluster.",
        placement_zones=control_zones,
        persistent_volumes=[
            PersistentVolumeSpec(
                name="control-kernel-data",
                size_gib=settings.control_plane_storage_gib,
                mount_path="/var/lib/familyos",
            )
        ],
    )

    tiers: List[NodeTier] = [control_tier]
    if worker_count:
        tiers.append(
            NodeTier(
                name="edge-workers",
                role="worker",
                count=worker_count,
                cpu_cores=settings.worker_cpu,
                memory_gib=settings.worker_memory_gib,
                storage_gib=settings.worker_storage_gib,
                description="Runs compute workloads and local device coordination services for the edge footprint.",
                placement_zones=worker_zones,
                persistent_volumes=[
                    PersistentVolumeSpec(
                        name="worker-artifacts",
                        size_gib=settings.worker_storage_gib,
                        mount_path="/var/lib/familyos",
                    )
                ],
            )
        )

    return ClusterTopology(stack=STACK_NAME, tiers=tiers)


def _render_overlay(
    topology: ClusterTopology,
    storage_result: StorageComponentResult,
    telemetry_result: TelemetryComponentResult,
) -> _renderer.RenderedArtifact:
    control_tier = topology.tiers[0]
    worker_tier = topology.tiers[1] if len(topology.tiers) > 1 else None
    control_zones = control_tier.placement_zones or ["edge-zone-01"]
    worker_zones = worker_tier.placement_zones if worker_tier else []

    context: Dict[str, Any] = {
        "stack": STACK_NAME,
        "control_plane_replicas": control_tier.count,
        "worker_replicas": worker_tier.count if worker_tier else 0,
        "control_zones": control_zones,
        "worker_zones": worker_zones,
        "storage_fragments": storage_result.outputs.get("compose_fragments", []),
        "telemetry_fragments": telemetry_result.outputs.get("compose_fragments", []),
        "persistent_volumes": [
            volume.to_dict() for volume in control_tier.persistent_volumes
        ],
        "worker_volumes": [
            volume.to_dict()
            for volume in (worker_tier.persistent_volumes if worker_tier else [])
        ],
    }

    return _renderer.write_template(
        "edge-cluster-overlay.yml.j2",
        target_name=f"{STACK_NAME}-overlay.yml",
        context=context,
        subdir=STACK_NAME,
    )


def orchestrate(settings: EdgeClusterSettings) -> None:
    """Pulumi program for the edge cluster deployment target."""

    topology = _build_topology(settings)

    storage_result = register_storage_components(
        stack_name=STACK_NAME, config=settings.storage
    )
    telemetry_result = provision_telemetry(
        stack_name=STACK_NAME, config=settings.telemetry
    )
    secret_result = sync_secrets(stack_name=STACK_NAME, secrets=settings.secrets)

    overlay_artifact = _render_overlay(topology, storage_result, telemetry_result)
    secret_artifacts = write_secret_artifacts(STACK_NAME, secret_result)

    topology.services.update(
        {
            "storage": {
                "compose_fragments": storage_result.outputs.get(
                    "compose_fragments", []
                ),
                "enable_postgres": storage_result.outputs.get("enable_postgres", False),
            },
            "telemetry": telemetry_result.outputs.get("ports", {}),
        }
    )

    components: List[BundleComponent] = []
    for artifact in storage_result.artifacts:
        components.append(BundleComponent(name="storage", artifact=artifact))
    for artifact in telemetry_result.artifacts:
        components.append(BundleComponent(name="telemetry", artifact=artifact))
    components.append(
        BundleComponent(name="cluster-overlay", artifact=overlay_artifact)
    )
    for artifact in secret_artifacts:
        components.append(BundleComponent(name="secrets", artifact=artifact))

    extra_outputs: Dict[str, Any] = {
        "storage": storage_result.outputs,
        "telemetry": telemetry_result.outputs,
        "cluster": {
            "topology": topology.to_dict(),
            "scaling": topology.scaling_metadata(),
            "artifacts": {
                "overlay": {
                    "compose_fragments": [str(overlay_artifact.path)],
                    "compose_artifacts": [overlay_artifact.as_output()],
                },
                "secrets": [artifact.as_output() for artifact in secret_artifacts],
            },
        },
    }

    bundle_result = write_bundle_manifest(
        stack_name=STACK_NAME,
        components=components,
        secrets=secret_result,
        extra={"outputs": extra_outputs},
    )

    try:
        pulumi_mod = __import__("pulumi")
    except ImportError:
        logger.debug(
            "Pulumi module not available; skipping stack exports for %s", STACK_NAME
        )
        return

    stack_exports: Dict[str, Any] = {
        "storage": storage_result.outputs,
        "telemetry": telemetry_result.outputs,
        "cluster": extra_outputs["cluster"],
        "secrets": {
            "metadata": secret_result.metadata,
            "missing": secret_result.missing,
            "artifacts": [artifact.as_output() for artifact in secret_artifacts],
        },
        "bundle": {
            "manifest": bundle_result.manifest,
            "artifacts": {
                "json": bundle_result.json_artifact.as_output(),
                "yaml": bundle_result.yaml_artifact.as_output(),
            },
        },
    }

    for key, value in stack_exports.items():
        pulumi_mod.export(f"{STACK_NAME}_{key}", value)


def _settings_from_pulumi() -> EdgeClusterSettings:
    storage = StorageLayerConfig.from_pulumi(
        namespace="k0-storage", fallback_namespace="k0"
    )
    telemetry = TelemetryConfig.from_pulumi(
        namespace="k0-telemetry", fallback_namespace="k0"
    )
    secrets = SecretMaterial.from_pulumi_config()

    configs = load_configs(CLUSTER_CONFIG_NAMESPACE, "k0")
    node_count = resolve_int(configs, ("node_count", "nodeCount"), 3)
    control_cpu = resolve_int(configs, ("control_plane_cpu", "controlPlaneCpu"), 4)
    control_mem = resolve_int(
        configs, ("control_plane_memory_gib", "controlPlaneMemoryGiB"), 16
    )
    control_storage = resolve_int(
        configs, ("control_plane_storage_gib", "controlPlaneStorageGiB"), 128
    )
    worker_cpu = resolve_int(configs, ("worker_cpu", "workerCpu"), 2)
    worker_mem = resolve_int(configs, ("worker_memory_gib", "workerMemoryGiB"), 8)
    worker_storage = resolve_int(
        configs, ("worker_storage_gib", "workerStorageGiB"), 64
    )

    return EdgeClusterSettings(
        node_count=node_count,
        storage=storage,
        telemetry=telemetry,
        secrets=secrets,
        control_plane_cpu=control_cpu,
        control_plane_memory_gib=control_mem,
        control_plane_storage_gib=control_storage,
        worker_cpu=worker_cpu,
        worker_memory_gib=worker_mem,
        worker_storage_gib=worker_storage,
    )


def pulumi_program_from_config() -> Callable[[], None]:
    """Return a Pulumi program that loads configuration from Pulumi config objects."""

    def _program() -> None:
        settings = _settings_from_pulumi()
        orchestrate(settings)

    return _program

    def _program() -> None:
        settings = _settings_from_pulumi()
        orchestrate(settings)

    return _program
