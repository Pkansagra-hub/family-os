"""Pulumi stack for managed datacenter high-availability deployments."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Sequence

from .. import _renderer
from ..bundle import BundleComponent, write_bundle_manifest
from ..components.secrets import SecretMaterial, sync_secrets
from ..components.storage import StorageLayerConfig, register_storage_components
from ..components.telemetry import TelemetryConfig, provision_telemetry
from ..secrets_artifacts import write_secret_artifacts
from .config_loader import load_configs, resolve_bool, resolve_int
from .topology import (
    ClusterTopology,
    NodeTier,
    PersistentVolumeSpec,
    generate_zone_names,
)

logger = logging.getLogger(__name__)

DEFAULT_PEER_COUNT = 3
STACK_NAME = "datacenter-ha"
CLUSTER_CONFIG_NAMESPACE = "k0-datacenter"


def _default_secret_list() -> List[SecretMaterial]:
    return []


@dataclass(slots=True)
class DatacenterHASettings:
    """High-availability deployment settings for managed data centers."""

    peer_count: int = DEFAULT_PEER_COUNT
    storage: StorageLayerConfig | None = None
    telemetry: TelemetryConfig | None = None
    secrets: list[SecretMaterial] = field(default_factory=_default_secret_list)
    enable_postgres: bool = True
    enable_blob_store_replication: bool = True
    placement_zones: Sequence[str] | None = None
    regions: Sequence[str] | None = None
    control_plane_cpu: int = 6
    control_plane_memory_gib: int = 24
    control_plane_storage_gib: int = 256
    peer_cpu: int = 8
    peer_memory_gib: int = 32
    peer_storage_gib: int = 512
    postgres_storage_gib: int = 256


def _build_topology(settings: DatacenterHASettings) -> ClusterTopology:
    peer_count = max(settings.peer_count, DEFAULT_PEER_COUNT)
    zones = list(
        settings.placement_zones or generate_zone_names("dc-zone", peer_count + 2)
    )
    regions = list(settings.regions or ["primary-region", "secondary-region"])

    control_tier = NodeTier(
        name="control-plane",
        role="control",
        count=3,
        cpu_cores=settings.control_plane_cpu,
        memory_gib=settings.control_plane_memory_gib,
        storage_gib=settings.control_plane_storage_gib,
        description="Runs admission control, scheduler, and management APIs.",
        placement_zones=zones[:3] or ["dc-zone-01"],
        persistent_volumes=[
            PersistentVolumeSpec(
                name="control-state",
                size_gib=settings.control_plane_storage_gib,
                mount_path="/var/lib/familyos",
            )
        ],
    )

    peer_tier = NodeTier(
        name="data-plane",
        role="peer",
        count=peer_count,
        cpu_cores=settings.peer_cpu,
        memory_gib=settings.peer_memory_gib,
        storage_gib=settings.peer_storage_gib,
        description="Executes core kernel workloads and replicates persisted state across regions.",
        placement_zones=zones[:peer_count] or zones,
        persistent_volumes=[
            PersistentVolumeSpec(
                name="peer-ledger",
                size_gib=settings.peer_storage_gib,
                mount_path="/var/lib/familyos",
            )
        ],
    )

    telemetry_tier = NodeTier(
        name="observability",
        role="telemetry",
        count=2,
        cpu_cores=4,
        memory_gib=16,
        storage_gib=128,
        description="Hosts Prometheus, Grafana, and alerting stack with failover across regions.",
        placement_zones=[f"{regions[0]}-telemetry", f"{regions[-1]}-telemetry"],
        persistent_volumes=[
            PersistentVolumeSpec(
                name="telemetry-data",
                size_gib=128,
                mount_path="/var/lib/telemetry",
            )
        ],
    )

    return ClusterTopology(
        stack=STACK_NAME, tiers=[control_tier, peer_tier, telemetry_tier]
    )


def _render_overlay(
    topology: ClusterTopology,
    storage_outputs: Dict[str, Any],
    telemetry_outputs: Dict[str, Any],
) -> _renderer.RenderedArtifact:
    context: Dict[str, Any] = {
        "stack": STACK_NAME,
        "peer_count": topology.tiers[1].count,
        "regions": topology.tiers[2].placement_zones,
        "storage_fragments": storage_outputs.get("compose_fragments", []),
        "telemetry_fragments": telemetry_outputs.get("compose_fragments", []),
    }

    return _renderer.write_template(
        "datacenter-ha-overlay.yml.j2",
        target_name=f"{STACK_NAME}-overlay.yml",
        context=context,
        subdir=STACK_NAME,
    )


def _render_postgres_overlay(
    settings: DatacenterHASettings,
) -> _renderer.RenderedArtifact | None:
    if not settings.enable_postgres:
        return None
    context: Dict[str, Any] = {
        "stack": STACK_NAME,
        "replicas": 3,
        "storage_gib": settings.postgres_storage_gib,
    }
    return _renderer.write_template(
        "datacenter-ha-postgres.yml.j2",
        target_name=f"{STACK_NAME}-postgres.yml",
        context=context,
        subdir=STACK_NAME,
    )


def _render_blob_overlay(
    storage: StorageLayerConfig, settings: DatacenterHASettings
) -> _renderer.RenderedArtifact | None:
    if not settings.enable_blob_store_replication:
        return None
    context: Dict[str, Any] = {
        "stack": STACK_NAME,
        "provider": storage.blob_provider,
        "snapshot_bucket": storage.snapshot_bucket,
    }
    return _renderer.write_template(
        "datacenter-ha-blob-replication.yml.j2",
        target_name=f"{STACK_NAME}-blob.yml",
        context=context,
        subdir=STACK_NAME,
    )


def orchestrate(settings: DatacenterHASettings) -> None:
    """Pulumi program entrypoint for the datacenter high-availability stack."""

    storage_cfg = settings.storage or StorageLayerConfig(
        enable_postgres=settings.enable_postgres
    )
    telemetry_cfg = settings.telemetry or TelemetryConfig()

    topology = _build_topology(settings)

    storage_result = register_storage_components(
        stack_name=STACK_NAME, config=storage_cfg
    )
    telemetry_result = provision_telemetry(stack_name=STACK_NAME, config=telemetry_cfg)
    secret_result = sync_secrets(stack_name=STACK_NAME, secrets=settings.secrets)

    overlay = _render_overlay(
        topology, storage_result.outputs, telemetry_result.outputs
    )
    postgres_overlay = _render_postgres_overlay(settings)
    blob_overlay = _render_blob_overlay(storage_cfg, settings)
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
            "postgresql": {
                "enabled": settings.enable_postgres,
                "replicas": 3 if settings.enable_postgres else 0,
            },
            "blob_replication": {
                "enabled": settings.enable_blob_store_replication,
                "provider": storage_cfg.blob_provider,
            },
        }
    )

    components: List[BundleComponent] = []
    for artifact in storage_result.artifacts:
        components.append(BundleComponent(name="storage", artifact=artifact))
    for artifact in telemetry_result.artifacts:
        components.append(BundleComponent(name="telemetry", artifact=artifact))
    components.append(BundleComponent(name="ha-overlay", artifact=overlay))
    if postgres_overlay is not None:
        components.append(
            BundleComponent(name="postgres-ha", artifact=postgres_overlay)
        )
    if blob_overlay is not None:
        components.append(
            BundleComponent(name="blob-replication", artifact=blob_overlay)
        )
    for artifact in secret_artifacts:
        components.append(BundleComponent(name="secrets", artifact=artifact))

    overlay_outputs: Dict[str, Any] = {
        "base": overlay.as_output(),
        "postgres": (
            postgres_overlay.as_output() if postgres_overlay is not None else None
        ),
        "blob_replication": (
            blob_overlay.as_output() if blob_overlay is not None else None
        ),
        "secrets": [artifact.as_output() for artifact in secret_artifacts],
    }

    extra_outputs: Dict[str, Any] = {
        "storage": storage_result.outputs,
        "telemetry": telemetry_result.outputs,
        "cluster": {
            "topology": topology.to_dict(),
            "scaling": topology.scaling_metadata(),
            "artifacts": overlay_outputs,
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


def _settings_from_pulumi() -> DatacenterHASettings:
    storage_cfg = StorageLayerConfig.from_pulumi(
        namespace="k0-storage", fallback_namespace="k0"
    )
    telemetry_cfg = TelemetryConfig.from_pulumi(
        namespace="k0-telemetry", fallback_namespace="k0"
    )
    secrets = SecretMaterial.from_pulumi_config()

    configs = load_configs(CLUSTER_CONFIG_NAMESPACE, "k0")
    peer_count = resolve_int(configs, ("peer_count", "peerCount"), DEFAULT_PEER_COUNT)
    enable_postgres = resolve_bool(configs, ("enable_postgres", "enablePostgres"), True)
    enable_blob = resolve_bool(
        configs, ("enable_blob_store_replication", "enableBlobStoreReplication"), True
    )
    control_cpu = resolve_int(configs, ("control_plane_cpu", "controlPlaneCpu"), 6)
    control_memory = resolve_int(
        configs, ("control_plane_memory_gib", "controlPlaneMemoryGiB"), 24
    )
    control_storage = resolve_int(
        configs, ("control_plane_storage_gib", "controlPlaneStorageGiB"), 256
    )
    peer_cpu = resolve_int(configs, ("peer_cpu", "peerCpu"), 8)
    peer_memory = resolve_int(configs, ("peer_memory_gib", "peerMemoryGiB"), 32)
    peer_storage = resolve_int(configs, ("peer_storage_gib", "peerStorageGiB"), 512)
    postgres_storage = resolve_int(
        configs, ("postgres_storage_gib", "postgresStorageGiB"), 256
    )

    return DatacenterHASettings(
        peer_count=peer_count,
        storage=storage_cfg,
        telemetry=telemetry_cfg,
        secrets=secrets,
        enable_postgres=enable_postgres,
        enable_blob_store_replication=enable_blob,
        control_plane_cpu=control_cpu,
        control_plane_memory_gib=control_memory,
        control_plane_storage_gib=control_storage,
        peer_cpu=peer_cpu,
        peer_memory_gib=peer_memory,
        peer_storage_gib=peer_storage,
        postgres_storage_gib=postgres_storage,
    )


def pulumi_program_from_config() -> Callable[[], None]:
    """Return a Pulumi program that loads datacenter settings from config."""

    def _program() -> None:
        settings = _settings_from_pulumi()
        orchestrate(settings)

    return _program
