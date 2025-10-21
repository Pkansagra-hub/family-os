"""Pulumi preview smoke harness for deployment stacks."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence, cast

import yaml

from . import _renderer
from .stacks import datacenter_ha, edge_cluster, local_single_node
from .validation import load_and_validate_bundle_manifest

_pulumi_import_error: ImportError | None = None
try:  # pragma: no cover - exercised in runtime environments with Pulumi installed
    from pulumi import automation as _pulumi_automation  # type: ignore
except ImportError as exc:  # pragma: no cover - captured for friendly error message
    _pulumi_automation = None
    _pulumi_import_error = exc

logger = logging.getLogger(__name__)

SUPPORTED_STACKS = {
    "local-single-node": local_single_node.pulumi_program_from_config,
    "edge-cluster": edge_cluster.pulumi_program_from_config,
    "datacenter-ha": datacenter_ha.pulumi_program_from_config,
}

ARTIFACT_ROOT = Path("artifacts") / "pulumi"


@dataclass(frozen=True)
class PreviewSummary:
    """Outcome of a Pulumi preview run."""

    stack: str
    manifest_yaml: Path
    manifest_json: Path
    change_summary: Mapping[str, int]


def _require_automation(module: Any | None) -> Any:
    if module is not None:
        return module
    if _pulumi_automation is None:
        raise RuntimeError(
            "Pulumi Automation API is not available. Ensure the 'pulumi' package is "
            "installed in the current environment."
        ) from _pulumi_import_error
    return cast(Any, _pulumi_automation)


def _resolve_program(stack: str):
    factory = SUPPORTED_STACKS.get(stack)
    if factory is None:
        raise ValueError(f"Unsupported stack: {stack}")
    return factory()


def _encode_config_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _normalise_config_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if "config" in payload or "secrets" in payload:
        return payload
    return {"config": payload}


def _flatten_config(
    payload: Mapping[str, Any], automation_module: Any
) -> MutableMapping[str, Any]:
    payload = _normalise_config_payload(payload)
    config_values: MutableMapping[str, Any] = {}

    config_section = payload.get("config", {})
    if config_section is not None:
        if not isinstance(config_section, Mapping):
            raise ValueError("'config' section must be a mapping")
        for namespace, entries in cast(Mapping[str, Any], config_section).items():
            if not isinstance(entries, Mapping):
                raise ValueError("Config namespace entries must be mappings")
            for key, value in cast(Mapping[str, Any], entries).items():
                full_key = f"{namespace}:{key}"
                config_values[str(full_key)] = automation_module.ConfigValue(
                    value=_encode_config_value(value), secret=False
                )

    secrets_section = payload.get("secrets", [])
    if secrets_section is not None:
        if not isinstance(secrets_section, Sequence):
            raise ValueError("'secrets' section must be a sequence of mappings")
        for item in cast(Sequence[Any], secrets_section):
            if not isinstance(item, Mapping):
                raise ValueError("Secret entries must be mappings")
            secret_mapping = cast(Mapping[str, Any], item)
            key = secret_mapping.get("key")
            if key is None:
                raise ValueError("Secret entries require a 'key' field")
            if not isinstance(key, str):
                raise ValueError("Secret entry keys must be strings")

            value = secret_mapping.get("value")
            if value is None:
                raise ValueError(f"Secret '{key}' is missing a value")
            config_values[str(key)] = automation_module.ConfigValue(
                value=_encode_config_value(value), secret=True
            )

    return config_values


def _has_changes(change_summary: Mapping[str, int] | None) -> bool:
    if not change_summary:
        return False
    return any(count for count in change_summary.values())


def _log_preview_output(line: str) -> None:
    text = line.rstrip()
    if text:
        logger.info(text)


def run_preview(
    stack: str,
    *,
    config: Mapping[str, Any] | None = None,
    artifacts_root: Path | None = None,
    expect_no_changes: bool = False,
    automation_module: Any | None = None,
) -> PreviewSummary:
    automation = _require_automation(automation_module)
    program = _resolve_program(stack)

    root = artifacts_root or ARTIFACT_ROOT / stack
    state_dir = root / "state"
    workspace_dir = root / "workspace"
    bundles_dir = root / "bundles"

    for path in (state_dir, workspace_dir, bundles_dir):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

    _renderer.set_generated_directory_override(bundles_dir)

    project_name = f"k0-deployment-{stack}"
    stack_name = f"preview-{stack}"

    backend_url = f"file://{state_dir.resolve()}"
    project_settings = automation.ProjectSettings(
        name=project_name,
        runtime="python",
        backend=automation.ProjectBackend(url=backend_url),
    )
    stack_settings = {
        stack_name: automation.StackSettings(secrets_provider="passphrase")
    }
    env_vars = {
        "PULUMI_CONFIG_PASSPHRASE": os.environ.get(
            "PULUMI_CONFIG_PASSPHRASE", "memory-kernel-smoke"
        ),
        "PULUMI_SKIP_UPDATE_CHECK": "true",
    }

    workspace_options = automation.LocalWorkspaceOptions(
        work_dir=str(workspace_dir),
        project_settings=project_settings,
        stack_settings=stack_settings,
        env_vars=env_vars,
    )

    stack_handle = automation.create_or_select_stack(
        stack_name=stack_name,
        project_name=project_name,
        program=program,
        opts=workspace_options,
    )

    try:
        if config:
            flattened = _flatten_config(config, automation)
            if flattened:
                stack_handle.set_all_config(flattened)

        preview_result = stack_handle.preview(on_output=_log_preview_output)

        change_summary = cast(
            Mapping[str, int], getattr(preview_result, "change_summary", {})
        )
        if expect_no_changes and _has_changes(change_summary):
            raise RuntimeError(
                f"Pulumi preview for stack '{stack}' produced unexpected changes: {change_summary}"
            )

        manifest_dir = bundles_dir / stack
        manifest_yaml = manifest_dir / f"{stack}-bundle.yaml"
        manifest_json = manifest_dir / f"{stack}-bundle.json"

        if not manifest_yaml.exists() or not manifest_json.exists():
            raise FileNotFoundError(
                f"Expected bundle manifests not found under {manifest_dir}"
            )

        load_and_validate_bundle_manifest(manifest_yaml)
        load_and_validate_bundle_manifest(manifest_json)

        summary = PreviewSummary(
            stack=stack,
            manifest_yaml=manifest_yaml,
            manifest_json=manifest_json,
            change_summary=change_summary or {},
        )
    finally:
        with suppress(Exception):  # pragma: no cover - best effort cleanup
            stack_handle.workspace.remove_stack(stack_name)
        _renderer.set_generated_directory_override(None)

    return summary


def _load_config_file(path: Path) -> Mapping[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise ValueError("Configuration file must contain a mapping at the root")
    return cast(Mapping[str, Any], data)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Pulumi preview smoke harness for FamilyOS deployment stacks.",
    )
    parser.add_argument(
        "--stack",
        required=True,
        choices=sorted(SUPPORTED_STACKS.keys()),
        help="Stack identifier to execute (e.g. local-single-node)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional YAML/JSON file supplying Pulumi configuration values.",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=None,
        help="Directory for smoke artifacts (defaults to artifacts/pulumi/<stack>).",
    )
    parser.add_argument(
        "--expect-no-changes",
        action="store_true",
        help="Fail if the preview reports resource changes.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress Pulumi preview output (errors still surface).",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - CLI glue
    args = _parse_args(argv)
    if args.quiet:
        logging.basicConfig(level=logging.WARNING)
    else:
        logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    config_payload: Mapping[str, Any] | None = None
    if args.config is not None:
        config_payload = _load_config_file(args.config)

    summary = run_preview(
        args.stack,
        config=config_payload,
        artifacts_root=args.artifacts_dir,
        expect_no_changes=args.expect_no_changes,
    )

    logger.info("Preview change summary: %s", dict(summary.change_summary))
    logger.info("Bundle manifest (YAML): %s", summary.manifest_yaml)
    logger.info("Bundle manifest (JSON): %s", summary.manifest_json)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
