"""Probe service-backed Back runtime proof over M2 -> M12A."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.probe_resolution_executor import run_probe as run_resolution_executor_probe


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument("--record-proof", action="store_true", help="Write proof records.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "tmp" / "back_tool_contract" / "production_back_runtime",
    )
    return parser.parse_args()


async def run_probe(*, record_proof: bool, output_dir: Path) -> dict[str, Any]:
    m12a_report = await run_resolution_executor_probe(
        ["jordan_clear_write", "jordan_duplicate_hil"],
        record_proof=record_proof,
        output_dir=output_dir / "m12a_resolution_executor",
    )
    scenarios = m12a_report["scenarios"]
    clear = scenarios["jordan_clear_write"]
    duplicate = scenarios["jordan_duplicate_hil"]
    clear_observation = clear["execution_observation"]
    duplicate_observation = duplicate["execution_observation"]
    clear_universe = clear["resolution_envelope"]["candidate_universe"]
    duplicate_universe = duplicate["resolution_envelope"]["candidate_universe"]

    checks = {
        "m12a_scenarios_pass": m12a_report["verdict"] == "pass",
        "materialized_100k_registry": _materialized_100k(clear_universe)
        and _materialized_100k(duplicate_universe),
        "indexed_lookup_under_50_records": _indexed_lookup(clear_universe)
        and _indexed_lookup(duplicate_universe),
        "resource_projection_service_backed": _resource_projection_service_backed(clear_universe),
        "policy_engine_decision_visible": bool(clear_universe.get("policy_decision_evidence")),
        "task_and_reminder_reads_service_backed": _service_backed_reads(clear_observation),
        "no_fixture_boundaries": clear_observation.get("audit_fields", {}).get("fixture_boundaries")
        == []
        and duplicate_observation.get("audit_fields", {}).get("fixture_boundaries") == [],
        "back_completed_clear_calendar_task": clear_observation.get("status") == "completed"
        and clear_observation.get("submit_result", {}).get("status") == "completed",
        "duplicate_blocks_write_for_hil": duplicate_observation.get("status") == "needs_hil"
        and not duplicate_observation.get("write_observation"),
    }
    return {
        "milestone": "PROD-BACK-100K",
        "targeted_command": "python scripts\\probe_production_back_runtime.py --json --record-proof",
        "checks": checks,
        "m12a_report": m12a_report,
        "verdict": "pass" if all(checks.values()) else "fail",
    }


def _materialized_100k(universe: dict[str, Any]) -> bool:
    stats = universe.get("corpus_stats") or {}
    return (
        int(stats.get("corpus_size") or 0) >= 100000
        and int(stats.get("materialized_contracts") or 0) >= 100000
        and int(stats.get("virtual_noise_records") or 0) == 0
    )


def _indexed_lookup(universe: dict[str, Any]) -> bool:
    stats = universe.get("corpus_stats") or {}
    return int(stats.get("records_examined") or 999999) <= 50 and not stats.get(
        "raw_corpus_prompt_visible"
    )


def _resource_projection_service_backed(universe: dict[str, Any]) -> bool:
    sources = set((universe.get("scope_proof") or {}).get("projection_sources") or [])
    return "connected_resource_registry.sqlite" in sources


def _service_backed_reads(observation: dict[str, Any]) -> bool:
    reads = (observation.get("read_phase") or {}).get("observations") or []
    service_names = {
        str((read.get("audit_fields") or {}).get("service_backed_read") or "") for read in reads
    }
    return {"TasksToolService", "RemindersToolService"}.issubset(service_names)


async def _amain() -> int:
    args = _parse_args()
    report = await run_probe(record_proof=args.record_proof, output_dir=args.output_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Production Back 100k runtime verdict: {report['verdict']}")
    return 0 if report["verdict"] == "pass" else 1


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
