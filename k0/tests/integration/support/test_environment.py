from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from ward import test  # type: ignore[attr-defined]

from tests.integration.support import environment as integration_environment


@test("harness_artifacts fixture generates validated bundles")
def _(
    artifacts: Any = integration_environment.harness_artifacts,  # type: ignore[misc]
) -> None:
    context = cast(integration_environment.HarnessArtifacts, artifacts)
    bundle_dir = context.artifacts_root / "bundles" / context.stack
    manifest_yaml = bundle_dir / f"{context.stack}-bundle.yaml"
    manifest_json = bundle_dir / f"{context.stack}-bundle.json"

    assert manifest_yaml.is_file(), f"missing manifest: {manifest_yaml}"
    assert manifest_json.is_file(), f"missing manifest: {manifest_json}"

    telemetry_files = list(context.telemetry_snapshots())
    assert telemetry_files, "expected telemetry snapshots to be generated"
    for snapshot in telemetry_files:
        assert snapshot.is_file(), f"expected telemetry snapshot: {snapshot}"
        contents = snapshot.read_text(encoding="utf-8")
        assert "k0_kernel_k0_signature_verified_total" in contents


@test("timeline_snapshot fixture surfaces smoke preview metadata")
def _(
    snapshot: Any = integration_environment.timeline_snapshot,  # type: ignore[misc]
    artifacts: Any = integration_environment.harness_artifacts,  # type: ignore[misc]
) -> None:
    context = cast(integration_environment.HarnessArtifacts, artifacts)
    payload = cast(dict[str, Any], snapshot)
    expected_timeline = (
        Path("artifacts")
        / "deployment"
        / (f"deployment-timeline-{context.stack}-integration.json")
    )

    assert payload, "expected timeline snapshot payload"
    assert payload.get("stack") == context.stack
    assert payload.get("status") == "success"
    assert (
        expected_timeline.is_file()
    ), f"missing timeline artifact: {expected_timeline}"
