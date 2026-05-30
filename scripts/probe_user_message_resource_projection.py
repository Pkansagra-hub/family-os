"""Probe user phrase -> connected resource projection for a Bridge inventory item."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poc.back_tool_contract.resource_projection import (
    make_resolve_resources_request,
    resolve_resources,
    validate_resource_universe,
)
from poc.back_tool_contract.resource_registry import ConnectedResourceRegistry

DEFAULT_MESSAGE = "turn off the garage ceiling light"
GARAGE_LIGHT_INVENTORY_RESOURCE = {
    "resource_id": "resource.home.com.google.home.garage_ceiling_bulb",
    "display_label": "Garage ceiling light",
    "room_ref": "room:garage",
    "connector_id": "com.google.home",
    "supported_operation_refs": ["lighting.turn_off"],
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "user_message_resource_projection",
    )
    return parser.parse_args()


def run_probe(*, message: str, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    registry_path = output_dir / "resource_registry.sqlite"
    if registry_path.exists():
        registry_path.unlink()

    registry = ConnectedResourceRegistry(registry_path)
    try:
        registry.ensure_seeded()
        inventory_registration = registry.upsert_inventory_resource(
            GARAGE_LIGHT_INVENTORY_RESOURCE,
            aliases=["garage ceiling light", "garage ceiling bulb", "garage light"],
            source_receipt="bridge-receipt-google-home-inventory-garage-light",
        )
    finally:
        registry.close()

    reference = _extract_resource_reference(message)
    operation_hints = _operation_hints(message)
    request = make_resolve_resources_request(
        refs=[reference],
        actor_scope={
            "actor_ref": "back",
            "caller_role": "guardian",
            "household_or_space_scope": "household:demo",
        },
        resource_kind_hints=["lighting_device"],
        operation_hints=operation_hints,
        connector_scope={
            "resource_registry_path": str(registry_path),
            "connector_ids": ["com.google.home"],
        },
    )
    universe = resolve_resources(request)
    validation = validate_resource_universe(universe)
    projected_resource = _first_resource(universe)
    translated_resource = _translation_card(projected_resource)

    unsupported_request = copy.deepcopy(request)
    unsupported_request["operation_hints"] = ["lighting.turn_on"]
    unsupported_universe = resolve_resources(unsupported_request)

    no_inventory_path = output_dir / "resource_registry_without_inventory.sqlite"
    if no_inventory_path.exists():
        no_inventory_path.unlink()
    no_inventory_registry = ConnectedResourceRegistry(no_inventory_path)
    try:
        no_inventory_registry.ensure_seeded()
    finally:
        no_inventory_registry.close()
    no_inventory_request = copy.deepcopy(request)
    no_inventory_request["connector_scope"]["resource_registry_path"] = str(no_inventory_path)
    no_inventory_universe = resolve_resources(no_inventory_request)

    checks = {
        "message_reference_extracted": reference == "garage ceiling light",
        "operation_hint_extracted": operation_hints == ["lighting.turn_off"],
        "inventory_registration_accepted": inventory_registration["accepted"] is True,
        "validation_accepted": validation["accepted"],
        "resource_id_from_inventory": translated_resource.get("resource_id")
        == GARAGE_LIGHT_INVENTORY_RESOURCE["resource_id"],
        "display_label_from_inventory": translated_resource.get("display_label")
        == GARAGE_LIGHT_INVENTORY_RESOURCE["display_label"],
        "room_ref_from_inventory": translated_resource.get("room_ref")
        == GARAGE_LIGHT_INVENTORY_RESOURCE["room_ref"],
        "connector_id_from_inventory": translated_resource.get("connector_id")
        == GARAGE_LIGHT_INVENTORY_RESOURCE["connector_id"],
        "supported_operation_admitted": "lighting.turn_off"
        in translated_resource.get("supported_operation_refs", []),
        "unsupported_operation_does_not_bind": not unsupported_universe.get("resources"),
        "missing_inventory_does_not_bind": not no_inventory_universe.get("resources"),
        "scope_proof_names_bridge_inventory": "bridge_ifl_inventory"
        in universe.get("projection_sources", []),
    }
    return {
        "milestone": "M3-USER-MESSAGE-RESOURCE-PROJECTION",
        "targeted_command": (
            "python scripts\\probe_user_message_resource_projection.py "
            '--message "turn off the garage ceiling light" --json'
        ),
        "user_message": message,
        "message_parse": {
            "resource_reference": reference,
            "operation_hints": operation_hints,
            "llm_may_select": ["resource_reference", "operation_hints"],
            "llm_must_not_supply": ["resource_id", "connector_id", "supported_operation_refs"],
        },
        "bridge_inventory_resource": GARAGE_LIGHT_INVENTORY_RESOURCE,
        "inventory_registration": inventory_registration,
        "resolve_resources_request": request,
        "translated_resource": translated_resource,
        "resource_universe": universe,
        "validation": validation,
        "negative_checks": {
            "unsupported_operation_resources": unsupported_universe.get("resources", []),
            "missing_inventory_resources": no_inventory_universe.get("resources", []),
        },
        "checks": checks,
        "verdict": "pass" if all(checks.values()) else "fail",
    }


def _extract_resource_reference(message: str) -> str:
    normalized = " ".join(message.lower().replace("please", "").replace(".", "").split())
    for prefix in ("turn off the ", "turn off ", "switch off the ", "switch off "):
        if normalized.startswith(prefix):
            return normalized[len(prefix) :].strip()
    return normalized.strip()


def _operation_hints(message: str) -> list[str]:
    normalized = message.lower()
    if "turn off" in normalized or "switch off" in normalized:
        return ["lighting.turn_off"]
    return []


def _first_resource(universe: dict[str, Any]) -> dict[str, Any]:
    resources = universe.get("resources") or []
    return resources[0] if resources else {}


def _translation_card(resource: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "resource_id",
        "display_label",
        "room_ref",
        "connector_id",
        "supported_operation_refs",
    ]
    return {key: resource[key] for key in keys if key in resource}


def main() -> int:
    args = _parse_args()
    report = run_probe(message=args.message, output_dir=args.output_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"User message resource projection verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
