"""Pulumi stack skeleton for local single-node deployments."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from ..bundle import BundleComponent, write_bundle_manifest
from ..components.secrets import SecretMaterial, SecretSyncResult, sync_secrets
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

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LocalSingleNodeSettings:
    """Composition of components required for the local stack."""

    storage: StorageLayerConfig
    telemetry: TelemetryConfig
    secrets: list[SecretMaterial]


def orchestrate(settings: LocalSingleNodeSettings) -> None:
    """Entrypoint for the Pulumi program.

    Implementations will stitch together storage, telemetry, and secrets to
    produce the curated Docker Compose bundle referenced in ADR-003.
    """

    stack_name = "local-single-node"

    storage_result: StorageComponentResult = register_storage_components(
        stack_name=stack_name, config=settings.storage
    )

    telemetry_result: TelemetryComponentResult = provision_telemetry(
        stack_name=stack_name, config=settings.telemetry
    )

    secret_result: SecretSyncResult = sync_secrets(
        stack_name=stack_name, secrets=settings.secrets
    )
    secret_artifacts = write_secret_artifacts(stack_name, secret_result)

    components: List[BundleComponent] = []
    components.extend(
        BundleComponent(name="storage", artifact=artifact)
        for artifact in storage_result.artifacts
    )
    components.extend(
        BundleComponent(name="telemetry", artifact=artifact)
        for artifact in telemetry_result.artifacts
    )
    components.extend(
        BundleComponent(name="secrets", artifact=artifact)
        for artifact in secret_artifacts
    )

    secret_outputs: Dict[str, Any] = {
        "metadata": secret_result.metadata,
        "missing": secret_result.missing,
        "artifacts": [artifact.as_output() for artifact in secret_artifacts],
    }

    bundle_result = write_bundle_manifest(
        stack_name=stack_name,
        components=components,
        secrets=secret_result,
        extra={
            "outputs": {
                "storage": storage_result.outputs,
                "telemetry": telemetry_result.outputs,
                "secrets": secret_outputs,
            }
        },
    )

    logger.info(
        "Generated bundle manifest files: %s",
        ", ".join(bundle_result.files),
    )

    # Export Pulumi stack outputs if running inside Pulumi
    try:
        pulumi_mod = __import__("pulumi")
    except ImportError:
        return

    stack_outputs: Dict[str, Any] = {
        "storage": storage_result.outputs,
        "telemetry": telemetry_result.outputs,
        "secrets": secret_outputs,
        "bundle": {
            "manifest": bundle_result.manifest,
            "artifacts": {
                "json": bundle_result.json_artifact.as_output(),
                "yaml": bundle_result.yaml_artifact.as_output(),
            },
        },
    }

    for key, value in stack_outputs.items():
        pulumi_mod.export(f"{stack_name}_{key}", value)


def pulumi_program_from_config() -> Callable[[], None]:
    """Return a Pulumi program that derives settings from Pulumi config."""

    def _program() -> None:
        storage_config = StorageLayerConfig.from_pulumi()
        telemetry_config = TelemetryConfig.from_pulumi()
        secret_materials = SecretMaterial.from_pulumi_config()

        settings = LocalSingleNodeSettings(
            storage=storage_config,
            telemetry=telemetry_config,
            secrets=secret_materials,
        )

        orchestrate(settings)

    return _program
