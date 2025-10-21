"""Utilities for composing deployment bundle manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Sequence

import yaml

from . import _renderer
from .components.secrets import SecretSyncResult
from .validation import validate_bundle_manifest


@dataclass(slots=True)
class BundleComponent:
    """Association between a component name and its rendered artifact."""

    name: str
    artifact: _renderer.RenderedArtifact

    def as_record(self) -> Dict[str, Any]:
        """Return a serialisable mapping for manifest emission."""

        record = {
            "component": self.name,
        }
        record.update(self.artifact.as_output())
        return record


@dataclass(slots=True)
class BundleWriteResult:
    """Result of writing bundle manifest artifacts."""

    manifest: Dict[str, Any]
    json_artifact: _renderer.RenderedArtifact
    yaml_artifact: _renderer.RenderedArtifact

    @property
    def files(self) -> List[str]:
        return [str(self.json_artifact.path), str(self.yaml_artifact.path)]


def write_bundle_manifest(
    *,
    stack_name: str,
    components: Sequence[BundleComponent],
    secrets: SecretSyncResult,
    extra: Mapping[str, Any] | None = None,
) -> BundleWriteResult:
    """Persist JSON and YAML bundle manifests alongside compose artifacts."""

    manifest: Dict[str, Any] = {
        "stack": stack_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "components": [component.as_record() for component in components],
        "secrets": {
            "missing": list(secrets.missing),
            "metadata": secrets.metadata,
        },
    }

    if extra:
        manifest["extra"] = dict(extra)

    validate_bundle_manifest(manifest)

    json_artifact = _renderer.write_raw_artifact(
        target_name=f"{stack_name}-bundle.json",
        data=json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"),
        subdir=stack_name,
    )

    yaml_artifact = _renderer.write_raw_artifact(
        target_name=f"{stack_name}-bundle.yaml",
        data=yaml.safe_dump(manifest, sort_keys=False).encode("utf-8"),
        subdir=stack_name,
    )

    return BundleWriteResult(
        manifest=manifest,
        json_artifact=json_artifact,
        yaml_artifact=yaml_artifact,
    )
