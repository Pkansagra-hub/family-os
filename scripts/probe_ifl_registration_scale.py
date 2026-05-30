"""Probe generic IFL provider registration into the materialized capability registry."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poc.back_tool_contract.capability_registry import MaterializedCapabilityRegistry
from poc.back_tool_contract.manifest_registration import (
    load_ifl_manifest,
    register_ifl_manifest,
    validate_capability_registration_batch,
)

DEFAULT_MANIFESTS = (
    REPO_ROOT / "fixtures" / "manifest_tesla_like.json",
    REPO_ROOT / "fixtures" / "manifest_finance_bank.json",
    REPO_ROOT / "fixtures" / "manifest_health_nutrition.json",
)

CATEGORIES = (
    "home",
    "health",
    "finance",
    "transport",
    "shopping",
    "calendar",
    "education",
    "communication",
    "media",
    "security",
    "energy",
    "custom",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifests",
        nargs="*",
        type=Path,
        default=list(DEFAULT_MANIFESTS),
        help="Provider manifest fixtures to register before the scale sweep.",
    )
    parser.add_argument(
        "--scale-contracts",
        type=int,
        default=100000,
        help="How many generated provider-owned capability schemas to register.",
    )
    parser.add_argument(
        "--capabilities-per-manifest",
        type=int,
        default=100,
        help="Generated executable capability templates per provider manifest.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "ifl_registration_scale",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def run_probe(
    *,
    manifest_paths: list[Path],
    scale_contracts: int,
    capabilities_per_manifest: int,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "capability_registry.sqlite"
    if db_path.exists():
        db_path.unlink()

    registry = MaterializedCapabilityRegistry(db_path)
    static_reports = []
    try:
        for path in manifest_paths:
            manifest = load_ifl_manifest(path)
            batch = register_ifl_manifest(manifest)
            validation = validate_capability_registration_batch(batch)
            insertion = registry.register_batch(batch, origin="provider_ifl_manifest")
            static_reports.append(
                {
                    "manifest_ref": str(path.relative_to(REPO_ROOT)),
                    "manifest_id": manifest.get("manifest_id"),
                    "connector_id": manifest.get("connector_id"),
                    "accepted": batch.get("accepted") is True and validation["accepted"],
                    "inserted_contracts": insertion["inserted_contracts"],
                    "capability_names": insertion["capability_names"],
                    "diagnostic_codes": [
                        item.get("code") for item in batch.get("registration_diagnostics", [])
                    ],
                }
            )

        scale_report = _register_generated_scale(
            registry=registry,
            scale_contracts=scale_contracts,
            capabilities_per_manifest=capabilities_per_manifest,
        )
        lookup_report = _lookup_report(registry, scale_report)
        checks = {
            "provider_manifests_accepted": all(item["accepted"] for item in static_reports),
            "provider_contracts_inserted": sum(
                item["inserted_contracts"] for item in static_reports
            )
            >= 7,
            "bank_transfer_exact_lookup": lookup_report["bank_transfer"].get("found") is True,
            "bank_transfer_red_hil_verifier": lookup_report["bank_transfer"].get("red_hil_verifier")
            is True,
            "nutrition_log_exact_lookup": lookup_report["nutrition_log"].get("found") is True,
            "tesla_climate_exact_lookup": lookup_report["tesla_climate"].get("found") is True,
            "schemas_are_provider_owned": lookup_report["all_sample_schema_sources"] is True,
            "scale_contracts_registered": scale_report["inserted_contracts"] == scale_contracts,
            "scale_manifest_batches_accepted": scale_report["rejected_batches"] == 0,
            "scale_exact_lookup": lookup_report["generated_sample"].get("found") is True,
        }
        return {
            "milestone": "M9-IFL-REGISTRATION-SCALE",
            "targeted_command": (
                "python scripts\\probe_ifl_registration_scale.py " "--scale-contracts 100000 --json"
            ),
            "registry_path": str(db_path),
            "static_provider_manifests": static_reports,
            "scale": scale_report,
            "lookups": lookup_report,
            "checks": checks,
            "verdict": "pass" if all(checks.values()) else "fail",
        }
    finally:
        registry.close()


def _register_generated_scale(
    *,
    registry: MaterializedCapabilityRegistry,
    scale_contracts: int,
    capabilities_per_manifest: int,
) -> dict[str, Any]:
    if scale_contracts <= 0:
        return {
            "requested_contracts": scale_contracts,
            "manifest_count": 0,
            "inserted_contracts": 0,
            "rejected_batches": 0,
            "sample_lookup_key": None,
        }

    per_manifest = max(1, capabilities_per_manifest)
    manifest_count = math.ceil(scale_contracts / per_manifest)
    inserted_contracts = 0
    rejected_batches = 0
    sample_lookup_key: dict[str, str] | None = None

    for manifest_index in range(manifest_count):
        remaining = scale_contracts - inserted_contracts
        template_count = min(per_manifest, remaining)
        manifest, first_write_key = _generated_manifest(manifest_index, template_count)
        batch = register_ifl_manifest(manifest)
        validation = validate_capability_registration_batch(batch)
        if batch.get("accepted") is not True or validation["accepted"] is not True:
            rejected_batches += 1
            continue
        insertion = registry.register_batch(batch, origin="generated_provider_ifl_manifest")
        inserted_contracts += insertion["inserted_contracts"]
        if sample_lookup_key is None:
            sample_lookup_key = first_write_key

    return {
        "requested_contracts": scale_contracts,
        "capabilities_per_manifest": per_manifest,
        "manifest_count": manifest_count,
        "inserted_contracts": inserted_contracts,
        "rejected_batches": rejected_batches,
        "sample_lookup_key": sample_lookup_key,
    }


def _generated_manifest(
    manifest_index: int, template_count: int
) -> tuple[dict[str, Any], dict[str, str]]:
    category = CATEGORIES[manifest_index % len(CATEGORIES)]
    connector_id = f"{category}.marketplace.provider{manifest_index:05d}"
    adapter_id = f"provider_{manifest_index:05d}"
    resource_model_id = f"resource.{connector_id}.record"
    resource_kind = f"{category}_marketplace_resource"
    verifier_ref = f"verifier.{connector_id}.readback.v1"
    templates = []
    required_for = []
    first_write_key: dict[str, str] | None = None
    for local_index in range(template_count):
        global_index = manifest_index * template_count + local_index
        is_write = global_index % 3 == 0
        operation = ("update_record" if is_write else "read_record") + f"_{global_index:06d}"
        required_inputs = ["resource_ref", "payload"] if is_write else ["resource_ref"]
        optional_inputs = ["idempotency_key"] if is_write else ["cursor"]
        template = {
            "template_id": f"{category}.{adapter_id}.{operation}.v1",
            "operation": operation,
            "kind": "write" if is_write else "read",
            "resource_model_ref": resource_model_id,
            "summary": f"{'Update' if is_write else 'Read'} a provider-owned {category} resource record.",
            "required_inputs": required_inputs,
            "optional_inputs": optional_inputs,
            "side_effect": is_write,
            "safety_band_min": "AMBER" if is_write else "GREEN",
            "requires_human_confirmation": False,
            "risk_class": "safety_sensitive" if is_write else "benign",
            "input_schema": _generated_input_schema(required_inputs, optional_inputs),
            "output_schema": _generated_output_schema(is_write),
        }
        if is_write:
            template["side_effect_class"] = "external_state_change"
            template["verifier_affordance_ref"] = verifier_ref
            required_for.append(operation)
            if first_write_key is None:
                first_write_key = {
                    "resource_kind": resource_kind,
                    "operation": operation,
                    "effect_type": "write",
                    "provider_id": f"connector:{connector_id}",
                }
        templates.append(template)

    manifest = {
        "contract_name": "bridge.ifl_manifest",
        "schema_version": 1,
        "manifest_id": f"manifest.{connector_id}.v1",
        "connector_id": connector_id,
        "adapter_id": adapter_id,
        "adapter_name": f"Marketplace Provider {manifest_index:05d}",
        "company": f"Marketplace Provider {manifest_index:05d}",
        "category": category,
        "hosting_mode": "company_hosted",
        "endpoint": f"https://provider{manifest_index:05d}.example/ifl/v1",
        "auth_flow": "oauth2_authorization_code",
        "signing_info": {
            "ca_id": "dev_familyos_root_v1",
            "signature_ref": f"sigref:provider{manifest_index:05d}:v1",
            "verified": True,
        },
        "resource_models": [
            {
                "resource_model_id": resource_model_id,
                "resource_kind": resource_kind,
                "identity_fields": ["resource_ref"],
                "display_fields": ["display_name", "status"],
                "state_fields": ["updated_at", "status"],
            }
        ],
        "capability_templates": templates,
        "event_topics": [
            {
                "topic": f"ifl.{category}.{connector_id}.record_changed.v1",
                "resource_model_ref": resource_model_id,
                "event_type": "record_changed",
                "event_schema": {
                    "type": "object",
                    "required": ["resource_ref", "observed_at"],
                    "properties": {
                        "resource_ref": {"type": "string"},
                        "observed_at": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            }
        ],
        "auth_scopes": ["records.read", "records.write"],
        "permissions_required": [
            {
                "scope": "records.read",
                "reason": "Read provider-owned resources for user-approved tasks.",
                "data_retention": "P30D",
                "data_shared_with": [f"Marketplace Provider {manifest_index:05d}"],
            }
        ],
        "safety_metadata": {
            "default_band": "GREEN",
            "side_effect_classes": ["external_state_change"],
            "data_retention": "P30D",
            "data_shared_with": [f"Marketplace Provider {manifest_index:05d}"],
        },
        "verifier_affordances": (
            [
                {
                    "verifier_ref": verifier_ref,
                    "verifier_type": "read_after_write",
                    "operation": "read_record_000001",
                    "required_for": required_for,
                }
            ]
            if required_for
            else []
        ),
        "freshness_guarantees": [
            {
                "resource_model_ref": resource_model_id,
                "fresh_for_ms": 300000,
                "source": "provider_event_or_readback",
            }
        ],
        "guide_cards": [
            {
                "guide_ref": f"guide.{connector_id}.safety.v1",
                "record_type": "guide_card",
                "summary": "Provider capabilities must obey declared schemas and verifier requirements.",
            }
        ],
    }
    return manifest, first_write_key or {
        "resource_kind": resource_kind,
        "operation": "read_record_000001",
        "effect_type": "read",
        "provider_id": f"connector:{connector_id}",
    }


def _generated_input_schema(
    required_inputs: list[str], optional_inputs: list[str]
) -> dict[str, Any]:
    properties = {
        "resource_ref": {"type": "string", "description": "Provider resource reference."},
        "payload": {"type": "object", "description": "Provider-authored action payload."},
        "idempotency_key": {"type": "string", "description": "Optional idempotency key."},
        "cursor": {"type": "string", "description": "Optional pagination cursor."},
    }
    return {
        "type": "object",
        "required": required_inputs,
        "properties": {name: properties[name] for name in [*required_inputs, *optional_inputs]},
        "additionalProperties": False,
    }


def _generated_output_schema(is_write: bool) -> dict[str, Any]:
    if is_write:
        return {
            "type": "object",
            "required": ["accepted", "resource_ref", "operation_id"],
            "properties": {
                "accepted": {"type": "boolean"},
                "resource_ref": {"type": "string"},
                "operation_id": {"type": "string"},
            },
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "required": ["resource_ref", "record"],
        "properties": {
            "resource_ref": {"type": "string"},
            "record": {"type": "object"},
        },
        "additionalProperties": False,
    }


def _lookup_report(
    registry: MaterializedCapabilityRegistry, scale_report: dict[str, Any]
) -> dict[str, Any]:
    bank_transfer, bank_examined = registry.lookup_contract(
        resource_kind="financial_account",
        operation="transfer_money",
        effect_type="write",
        provider_id="connector:finance.example.bank",
    )
    nutrition_log, nutrition_examined = registry.lookup_contract(
        resource_kind="nutrition_log",
        operation="log_meal",
        effect_type="write",
        provider_id="connector:health.example.nutrition",
    )
    tesla_climate, tesla_examined = registry.lookup_contract(
        resource_kind="vehicle",
        operation="start_climate",
        effect_type="write",
        provider_id="connector:transport.com.tesla",
    )
    generated_contract = None
    generated_examined = 0
    sample_key = scale_report.get("sample_lookup_key")
    if sample_key:
        generated_contract, generated_examined = registry.lookup_contract(**sample_key)

    samples = [
        item for item in [bank_transfer, nutrition_log, tesla_climate, generated_contract] if item
    ]
    return {
        "bank_transfer": _contract_lookup_summary(bank_transfer, bank_examined),
        "nutrition_log": _contract_lookup_summary(nutrition_log, nutrition_examined),
        "tesla_climate": _contract_lookup_summary(tesla_climate, tesla_examined),
        "generated_sample": _contract_lookup_summary(generated_contract, generated_examined),
        "all_sample_schema_sources": all(
            item.get("schema_source") == "provider_ifl_manifest"
            and item.get("provider_schema_digest")
            and isinstance(item.get("input_schema"), dict)
            and isinstance(item.get("output_schema"), dict)
            for item in samples
        ),
    }


def _contract_lookup_summary(
    contract: dict[str, Any] | None, records_examined: int
) -> dict[str, Any]:
    if contract is None:
        return {"found": False, "records_examined": records_examined}
    return {
        "found": True,
        "records_examined": records_examined,
        "name": contract.get("name"),
        "provider_id": contract.get("provider_id"),
        "resource_kind": contract.get("resource_kind"),
        "operation": contract.get("operation"),
        "effect_type": contract.get("effect_type"),
        "safety_band_min": contract.get("safety_band_min"),
        "schema_source": contract.get("schema_source"),
        "provider_schema_digest": contract.get("provider_schema_digest"),
        "red_hil_verifier": (
            contract.get("safety_band_min") in {"RED", "CRISIS"}
            and contract.get("requires_human_confirmation") is True
            and bool(contract.get("verifier_ref"))
        ),
    }


def main() -> int:
    args = _parse_args()
    report = run_probe(
        manifest_paths=args.manifests,
        scale_contracts=args.scale_contracts,
        capabilities_per_manifest=args.capabilities_per_manifest,
        output_dir=args.output_dir,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"IFL registration scale verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
