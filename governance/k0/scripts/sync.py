"""
Master Sync Orchestrator - Bidirectional sync between code and k0_architecture_master.md.

Operations:
    --check    : Validate consistency (no changes, exit 1 on drift)
    --diff     : Show differences between code and master
    --update   : Update master document from code (one-way: code -> doc)
    --report   : Generate full sync report

This is NOT CI - run on demand before commits or when reviewing architecture.

Usage:
    python -m governance.k0.scripts.sync --check
    python -m governance.k0.scripts.sync --diff
    python -m governance.k0.scripts.sync --update
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class SyncReport:
    """Report from sync operation."""

    category: str
    scanned_count: int
    registered_count: int
    missing_in_master: list[str]
    missing_in_code: list[str]
    status_mismatches: list[str]
    is_curated: bool = False  # Curated categories don't count missing_in_master as drift

    @property
    def is_synced(self) -> bool:
        """Check if code and master are in sync."""
        if self.is_curated:
            # Curated categories only check missing_in_code (doc errors)
            return not self.missing_in_code and not self.status_mismatches
        return (
            not self.missing_in_master and not self.missing_in_code and not self.status_mismatches
        )

    @property
    def drift_count(self) -> int:
        """Total number of drift items."""
        if self.is_curated:
            # Curated categories don't count undocumented items as drift
            return len(self.missing_in_code) + len(self.status_mismatches)
        return len(self.missing_in_master) + len(self.missing_in_code) + len(self.status_mismatches)

    @property
    def undocumented_count(self) -> int:
        """Count of items in code but not in master (informational for curated)."""
        return len(self.missing_in_master) if self.is_curated else 0


def _get_repo_root() -> Path:
    """Get repository root from script location."""
    return Path(__file__).parent.parent.parent.parent


def _get_master_path() -> Path:
    """Get path to k0_architecture_master.md."""
    return _get_repo_root() / "governance" / "k0" / "k0_architecture_master.md"


def check_syscalls() -> SyncReport:
    """Check syscalls sync status."""
    from governance.k0.scripts.syscall_scanner import diff_with_master, scan_syscalls

    syscalls = scan_syscalls()
    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="Syscalls",
            scanned_count=len(syscalls),
            registered_count=0,
            missing_in_master=[s.method for s in syscalls],
            missing_in_code=[],
            status_mismatches=[],
        )

    diff = diff_with_master(syscalls, master_path)

    return SyncReport(
        category="Syscalls",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff["missing_in_master"]),
        missing_in_code=list(diff["missing_in_code"]),
        status_mismatches=[],
    )


def check_pipelines() -> SyncReport:
    """Check pipelines sync status."""
    from governance.k0.scripts.pipeline_scanner import diff_with_master, scan_pipelines

    pipelines = scan_pipelines()
    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="Pipelines",
            scanned_count=len(pipelines),
            registered_count=0,
            missing_in_master=[p.pipeline_id for p in pipelines],
            missing_in_code=[],
            status_mismatches=[],
        )

    diff = diff_with_master(pipelines, master_path)

    return SyncReport(
        category="Pipelines",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff["missing_in_master"]),
        missing_in_code=list(diff["missing_in_code"]),
        status_mismatches=[],
    )


def check_modules() -> SyncReport:
    """Check modules sync status."""
    from governance.k0.scripts.module_scanner import diff_with_master, scan_modules

    modules = scan_modules()
    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="Modules",
            scanned_count=len(modules),
            registered_count=0,
            missing_in_master=[m.module_id for m in modules],
            missing_in_code=[],
            status_mismatches=[],
        )

    diff = diff_with_master(modules, master_path)

    return SyncReport(
        category="Modules",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff["missing_in_master"]),
        missing_in_code=list(diff["missing_in_code"]),
        status_mismatches=[],
    )


def check_adrs() -> SyncReport:
    """Check ADRs sync status."""
    from governance.k0.scripts.adr_scanner import diff_with_master, scan_adrs

    adrs = scan_adrs()
    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="ADRs",
            scanned_count=len(adrs),
            registered_count=0,
            missing_in_master=[a.adr_id for a in adrs],
            missing_in_code=[],
            status_mismatches=[],
        )

    diff = diff_with_master(adrs, master_path)

    return SyncReport(
        category="ADRs",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff["missing_in_master"]),
        missing_in_code=list(diff["missing_in_code"]),
        status_mismatches=[],
    )


def check_events() -> SyncReport:
    """Check events sync status."""
    from governance.k0.scripts.event_scanner import diff_with_master, scan_events

    events = scan_events()
    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="Events",
            scanned_count=len(events),
            registered_count=0,
            missing_in_master=[e.topic for e in events],
            missing_in_code=[],
            status_mismatches=[],
        )

    diff = diff_with_master(events, master_path)

    return SyncReport(
        category="Events",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff["missing_in_master"]),
        missing_in_code=list(diff["missing_in_code"]),
        status_mismatches=[],
    )


def check_tables() -> SyncReport:
    """Check storage tables sync status."""
    from governance.k0.scripts.storage_scanner import (
        diff_tables_with_master,
        scan_tables,
    )

    tables = scan_tables()
    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="Tables",
            scanned_count=len(tables),
            registered_count=0,
            missing_in_master=[t.table_name for t in tables],
            missing_in_code=[],
            status_mismatches=[],
        )

    diff = diff_tables_with_master(tables, master_path)

    return SyncReport(
        category="Tables",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff["missing_in_master"]),
        missing_in_code=list(diff["missing_in_code"]),
        status_mismatches=[],
    )


def check_migrations() -> SyncReport:
    """Check migrations sync status."""
    from governance.k0.scripts.storage_scanner import (
        diff_migrations_with_master,
        scan_migrations,
    )

    migrations = scan_migrations()
    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="Migrations",
            scanned_count=len(migrations),
            registered_count=0,
            missing_in_master=[m.migration_id for m in migrations],
            missing_in_code=[],
            status_mismatches=[],
        )

    diff = diff_migrations_with_master(migrations, master_path)

    return SyncReport(
        category="Migrations",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff["missing_in_master"]),
        missing_in_code=list(diff["missing_in_code"]),
        status_mismatches=[],
    )


def check_indexes() -> SyncReport:
    """Check indexes sync status."""
    from governance.k0.scripts.storage_scanner import (
        diff_indexes_with_master,
        scan_indexes,
    )

    indexes = scan_indexes()
    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="Indexes",
            scanned_count=len(indexes),
            registered_count=0,
            missing_in_master=[i.index_name for i in indexes],
            missing_in_code=[],
            status_mismatches=[],
        )

    diff = diff_indexes_with_master(indexes, master_path)

    return SyncReport(
        category="Indexes",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff["missing_in_master"]),
        missing_in_code=list(diff["missing_in_code"]),
        status_mismatches=[],
    )


def check_module_contracts() -> SyncReport:
    """Check module contracts sync status."""
    from governance.k0.scripts.contract_scanner import (
        diff_module_contracts_with_master,
        scan_module_contracts,
    )

    contracts = scan_module_contracts()
    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="ModuleContracts",
            scanned_count=len(contracts),
            registered_count=0,
            missing_in_master=[c.contract_name for c in contracts],
            missing_in_code=[],
            status_mismatches=[],
        )

    diff = diff_module_contracts_with_master(contracts, master_path)

    return SyncReport(
        category="ModuleContracts",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff["missing_in_master"]),
        missing_in_code=list(diff["missing_in_code"]),
        status_mismatches=[],
    )


def check_pipeline_contracts() -> SyncReport:
    """Check pipeline contracts sync status."""
    from governance.k0.scripts.contract_scanner import (
        diff_pipeline_contracts_with_master,
        scan_pipeline_contracts,
    )

    contracts = scan_pipeline_contracts()
    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="PipelineContracts",
            scanned_count=len(contracts),
            registered_count=0,
            missing_in_master=[c.contract_name for c in contracts],
            missing_in_code=[],
            status_mismatches=[],
        )

    diff = diff_pipeline_contracts_with_master(contracts, master_path)

    return SyncReport(
        category="PipelineContracts",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff["missing_in_master"]),
        missing_in_code=list(diff["missing_in_code"]),
        status_mismatches=[],
    )


def check_event_schemas() -> SyncReport:
    """Check event schemas sync status."""
    from governance.k0.scripts.contract_scanner import (
        diff_event_schemas_with_master,
        scan_event_schemas,
    )

    schemas = scan_event_schemas()
    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="EventSchemas",
            scanned_count=len(schemas),
            registered_count=0,
            missing_in_master=[s.schema_name for s in schemas],
            missing_in_code=[],
            status_mismatches=[],
        )

    diff = diff_event_schemas_with_master(schemas, master_path)

    return SyncReport(
        category="EventSchemas",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff["missing_in_master"]),
        missing_in_code=list(diff["missing_in_code"]),
        status_mismatches=[],
    )


def check_capabilities() -> SyncReport:
    """Check capability checks sync status."""
    from governance.k0.scripts.capability_scanner import (
        diff_capability_checks_with_master,
        scan_capability_checks,
    )

    checks = scan_capability_checks()
    master_path = _get_master_path()

    if not master_path.exists():
        unique_caps = set(
            c.capability_name for c in checks if not c.capability_name.startswith("<")
        )
        return SyncReport(
            category="Capabilities",
            scanned_count=len(unique_caps),
            registered_count=0,
            missing_in_master=list(unique_caps),
            missing_in_code=[],
            status_mismatches=[],
        )

    diff = diff_capability_checks_with_master(checks, master_path)

    return SyncReport(
        category="Capabilities",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff["missing_in_master"]),
        missing_in_code=list(diff["missing_in_code"]),
        status_mismatches=[],
    )


def check_fabric_providers() -> SyncReport:
    """Check fabric providers sync status."""
    from governance.k0.scripts.capability_scanner import (
        diff_fabric_providers_with_master,
        scan_fabric_providers_from_yaml,
    )

    providers = scan_fabric_providers_from_yaml()
    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="FabricProviders",
            scanned_count=len(providers),
            registered_count=0,
            missing_in_master=[p.capability_name for p in providers],
            missing_in_code=[],
            status_mismatches=[],
        )

    diff = diff_fabric_providers_with_master(providers, master_path)

    return SyncReport(
        category="FabricProviders",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff["missing_in_master"]),
        missing_in_code=list(diff["missing_in_code"]),
        status_mismatches=[],
    )


def check_kernel_hooks() -> SyncReport:
    """Check kernel hooks sync status (Part 9.2)."""
    from governance.k0.scripts.scheduler_scanner import (
        diff_kernel_hooks_with_master,
        scan_kernel_hooks_from_master,
    )

    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="KernelHooks",
            scanned_count=0,
            registered_count=0,
            missing_in_master=[],
            missing_in_code=[],
            status_mismatches=[],
        )

    hooks = scan_kernel_hooks_from_master(master_path)
    diff = diff_kernel_hooks_with_master(hooks, master_path)

    return SyncReport(
        category="KernelHooks",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff.get("missing_in_master", [])),
        missing_in_code=list(diff.get("missing_in_code", [])),
        status_mismatches=[],
    )


def check_background_workers() -> SyncReport:
    """Check background workers sync status (Part 9.3)."""
    from governance.k0.scripts.scheduler_scanner import (
        diff_background_workers_with_master,
        scan_background_workers_from_master,
    )

    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="BackgroundWorkers",
            scanned_count=0,
            registered_count=0,
            missing_in_master=[],
            missing_in_code=[],
            status_mismatches=[],
        )

    workers = scan_background_workers_from_master(master_path)
    diff = diff_background_workers_with_master(workers, master_path)

    return SyncReport(
        category="BackgroundWorkers",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff.get("missing_in_master", [])),
        missing_in_code=list(diff.get("missing_in_code", [])),
        status_mismatches=[],
    )


def check_metrics() -> SyncReport:
    """Check prometheus metrics sync status (Part 10.1)."""
    from governance.k0.scripts.metrics_scanner import (
        diff_metrics_with_master,
        scan_prometheus_metrics_from_code,
    )

    metrics = scan_prometheus_metrics_from_code()
    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="Metrics",
            scanned_count=len(metrics),
            registered_count=0,
            missing_in_master=[m.name for m in metrics],
            missing_in_code=[],
            status_mismatches=[],
        )

    diff = diff_metrics_with_master(metrics, master_path)

    return SyncReport(
        category="Metrics",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff["missing_in_master"]),
        missing_in_code=list(diff["missing_in_code"]),
        status_mismatches=[],
    )


def check_config_keys() -> SyncReport:
    """Check config keys sync status (Part 13.1).

    ConfigKeys is a CURATED category - master documents important keys only,
    not every single config key in YAML files. Undocumented keys are shown
    but don't count as drift.
    """
    from governance.k0.scripts.config_scanner import (
        diff_config_with_master,
        scan_config_keys_from_yaml,
    )

    configs = scan_config_keys_from_yaml()
    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="ConfigKeys",
            scanned_count=len(configs),
            registered_count=0,
            missing_in_master=[c.key_path for c in configs],
            missing_in_code=[],
            status_mismatches=[],
            is_curated=True,
        )

    diff = diff_config_with_master(configs, master_path)

    return SyncReport(
        category="ConfigKeys",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff["missing_in_master"]),
        missing_in_code=list(diff["missing_in_code"]),
        status_mismatches=[],
        is_curated=diff.get("is_curated", True),
    )


def check_feature_flags() -> SyncReport:
    """Check feature flags sync status (Part 13.2)."""
    from governance.k0.scripts.config_scanner import (
        diff_feature_flags_with_master,
        scan_feature_flags,
    )

    flags = scan_feature_flags()
    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="FeatureFlags",
            scanned_count=len(flags),
            registered_count=0,
            missing_in_master=[f.name for f in flags],
            missing_in_code=[],
            status_mismatches=[],
        )

    diff = diff_feature_flags_with_master(flags, master_path)

    return SyncReport(
        category="FeatureFlags",
        scanned_count=diff["scanned_count"],
        registered_count=diff["registered_count"],
        missing_in_master=list(diff["missing_in_master"]),
        missing_in_code=list(diff["missing_in_code"]),
        status_mismatches=[],
    )


def check_config_versions() -> SyncReport:
    """Check config file version consistency (Part 14.1)."""
    from governance.k0.scripts.version_scanner import (
        diff_config_versions,
        scan_config_versions,
        scan_config_versions_from_master,
    )

    code_versions = scan_config_versions()
    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="ConfigVersions",
            scanned_count=len(code_versions),
            registered_count=0,
            missing_in_master=[v.file_name for v in code_versions],
            missing_in_code=[],
            status_mismatches=[],
        )

    master_versions = scan_config_versions_from_master(master_path)
    missing_in_master, missing_in_code, version_mismatch = diff_config_versions(
        code_versions, master_versions
    )

    # Version mismatches are reported as status_mismatches
    mismatches = [f"{k}: code={v[0]} master={v[1]}" for k, v in version_mismatch.items()]

    return SyncReport(
        category="ConfigVersions",
        scanned_count=len(code_versions),
        registered_count=len(master_versions),
        missing_in_master=list(missing_in_master),
        missing_in_code=list(missing_in_code),
        status_mismatches=mismatches,
    )


def check_contract_versions() -> SyncReport:
    """Check contract version consistency (Part 14.2)."""
    from governance.k0.scripts.version_scanner import (
        diff_contract_versions,
        scan_contract_versions,
        scan_contract_versions_from_master,
    )

    code_versions = scan_contract_versions()
    master_path = _get_master_path()

    if not master_path.exists():
        return SyncReport(
            category="ContractVersions",
            scanned_count=len(code_versions),
            registered_count=0,
            missing_in_master=[v.contract_id for v in code_versions],
            missing_in_code=[],
            status_mismatches=[],
        )

    master_versions = scan_contract_versions_from_master(master_path)
    missing_in_master, missing_in_code, version_mismatch = diff_contract_versions(
        code_versions, master_versions
    )

    # Version mismatches are reported as status_mismatches
    mismatches = [f"{k}: code={v[0]} master={v[1]}" for k, v in version_mismatch.items()]

    return SyncReport(
        category="ContractVersions",
        scanned_count=len(code_versions),
        registered_count=len(master_versions),
        missing_in_master=list(missing_in_master),
        missing_in_code=list(missing_in_code),
        status_mismatches=mismatches,
        is_curated=True,  # Contract versions are selectively documented
    )


def check_artifact_checksums() -> SyncReport:
    """Check contract artifact checksum integrity (Part 14.3)."""
    from governance.k0.scripts.version_scanner import (
        scan_artifact_versions,
        verify_artifact_checksums,
    )

    artifacts = scan_artifact_versions()
    checksums = verify_artifact_checksums()

    # Group invalid checksums by artifact type for clear reporting
    invalid: list[str] = []
    for result in checksums:
        if not result.is_valid:
            # Format: "module: affect.analyze.v1 (checksum mismatch)"
            artifact_name = result.file_path.replace("/", ".").replace("\\", ".")
            if artifact_name.endswith(".yaml"):
                artifact_name = artifact_name[:-5]
            elif artifact_name.endswith(".json"):
                artifact_name = artifact_name[:-5]
            invalid.append(f"{result.artifact_type}: {artifact_name} ({result.error})")

    return SyncReport(
        category="ArtifactChecksums",
        scanned_count=len(checksums),
        registered_count=len(artifacts),
        missing_in_master=[],
        missing_in_code=[],
        status_mismatches=invalid,
    )


def run_all_checks() -> list[SyncReport]:
    """Run all sync checks and return reports."""
    reports = []

    print("Scanning codebase...")
    print()

    print("  [1/21] Scanning syscalls...", end=" ", flush=True)
    reports.append(check_syscalls())
    print(f"found {reports[-1].scanned_count}")

    print("  [2/21] Scanning pipelines...", end=" ", flush=True)
    reports.append(check_pipelines())
    print(f"found {reports[-1].scanned_count}")

    print("  [3/21] Scanning modules...", end=" ", flush=True)
    reports.append(check_modules())
    print(f"found {reports[-1].scanned_count}")

    print("  [4/21] Scanning ADRs...", end=" ", flush=True)
    reports.append(check_adrs())
    print(f"found {reports[-1].scanned_count}")

    print("  [5/21] Scanning events...", end=" ", flush=True)
    reports.append(check_events())
    print(f"found {reports[-1].scanned_count}")

    print("  [6/21] Scanning tables...", end=" ", flush=True)
    reports.append(check_tables())
    print(f"found {reports[-1].scanned_count}")

    print("  [7/21] Scanning migrations...", end=" ", flush=True)
    reports.append(check_migrations())
    print(f"found {reports[-1].scanned_count}")

    print("  [8/21] Scanning indexes...", end=" ", flush=True)
    reports.append(check_indexes())
    print(f"found {reports[-1].scanned_count}")

    print("  [9/21] Scanning module contracts...", end=" ", flush=True)
    reports.append(check_module_contracts())
    print(f"found {reports[-1].scanned_count}")

    print("  [10/21] Scanning pipeline contracts...", end=" ", flush=True)
    reports.append(check_pipeline_contracts())
    print(f"found {reports[-1].scanned_count}")

    print("  [11/21] Scanning event schemas...", end=" ", flush=True)
    reports.append(check_event_schemas())
    print(f"found {reports[-1].scanned_count}")

    print("  [12/21] Scanning capabilities...", end=" ", flush=True)
    reports.append(check_capabilities())
    print(f"found {reports[-1].scanned_count}")

    print("  [13/21] Scanning fabric providers...", end=" ", flush=True)
    reports.append(check_fabric_providers())
    print(f"found {reports[-1].scanned_count}")

    print("  [14/21] Scanning kernel hooks...", end=" ", flush=True)
    reports.append(check_kernel_hooks())
    print(f"found {reports[-1].scanned_count}")

    print("  [15/21] Scanning background workers...", end=" ", flush=True)
    reports.append(check_background_workers())
    print(f"found {reports[-1].scanned_count}")

    print("  [16/21] Scanning metrics...", end=" ", flush=True)
    reports.append(check_metrics())
    print(f"found {reports[-1].scanned_count}")

    print("  [17/21] Scanning config keys...", end=" ", flush=True)
    reports.append(check_config_keys())
    print(f"found {reports[-1].scanned_count}")

    print("  [18/21] Scanning feature flags...", end=" ", flush=True)
    reports.append(check_feature_flags())
    print(f"found {reports[-1].scanned_count}")

    print("  [19/21] Scanning config versions...", end=" ", flush=True)
    reports.append(check_config_versions())
    print(f"found {reports[-1].scanned_count}")

    print("  [20/21] Scanning contract versions...", end=" ", flush=True)
    reports.append(check_contract_versions())
    print(f"found {reports[-1].scanned_count}")

    print("  [21/21] Verifying artifact checksums...", end=" ", flush=True)
    reports.append(check_artifact_checksums())
    print(f"found {reports[-1].scanned_count}")

    print()
    return reports


def print_summary(reports: list[SyncReport]) -> None:
    """Print sync summary."""
    print("=" * 70)
    print("SYNC STATUS SUMMARY")
    print("=" * 70)
    print()
    print("Note: Registered includes Planning items (not checked for code presence)")
    print("      * = Curated category (undocumented items don't count as drift)")
    print()
    print(
        f"{'Category':<17} {'Scanned':<10} {'Registered':<12} {'Undoc':<8} {'Missing(C)':<12} {'Status':<10}"
    )
    print("-" * 80)

    total_drift = 0
    for r in reports:
        status = "OK" if r.is_synced else f"DRIFT({r.drift_count})"
        total_drift += r.drift_count

        # For curated categories, show undocumented count separately
        if r.is_curated:
            undoc_display = str(r.undocumented_count)
            cat_display = f"{r.category}*"
        else:
            undoc_display = str(len(r.missing_in_master))
            cat_display = r.category

        print(
            f"{cat_display:<17} {r.scanned_count:<10} {r.registered_count:<12} "
            f"{undoc_display:<8} {len(r.missing_in_code):<12} {status:<10}"
        )

    print("-" * 80)
    overall = "SYNCED" if total_drift == 0 else f"DRIFT DETECTED ({total_drift} items)"
    print(f"{'OVERALL':<17} {'':<10} {'':<12} {'':<8} {'':<12} {overall}")
    print()


def print_diff(reports: list[SyncReport]) -> None:
    """Print detailed diff for each category."""
    print()
    print("=" * 70)
    print("DETAILED DIFF")
    print("=" * 70)

    has_diff = False
    for r in reports:
        # Skip if synced and no undocumented items in curated categories
        if r.is_synced and not (r.is_curated and r.undocumented_count > 0):
            continue

        has_diff = True
        curated_marker = " (curated)" if r.is_curated else ""
        print(f"\n{r.category}{curated_marker}:")
        print("-" * 40)

        if r.missing_in_master:
            if r.is_curated:
                print(f"  Undocumented in master ({r.undocumented_count} keys - informational):")
            else:
                print("  Missing in master document (exists in code):")
            for item in r.missing_in_master[:10]:
                print(f"    + {item}")
            if len(r.missing_in_master) > 10:
                print(f"    ... and {len(r.missing_in_master) - 10} more")

        if r.missing_in_code:
            print("  Missing in code (exists in master):")
            for item in r.missing_in_code[:10]:
                print(f"    - {item}")
            if len(r.missing_in_code) > 10:
                print(f"    ... and {len(r.missing_in_code) - 10} more")

        if r.status_mismatches:
            print("  Status mismatches:")
            for item in r.status_mismatches[:10]:
                print(f"    ! {item}")

    if not has_diff:
        print("\nAll categories in sync (no differences to show).")


def update_master_timestamp() -> None:
    """Update the Last Updated timestamp in master document."""
    master_path = _get_master_path()
    if not master_path.exists():
        print("Master document not found!")
        return

    content = master_path.read_text(encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")

    # Update Last Updated line
    content = re.sub(
        r"\*\*Last Updated\*\*:\s*\d{4}-\d{2}-\d{2}",
        f"**Last Updated**: {today}",
        content,
    )

    master_path.write_text(content, encoding="utf-8")
    print(f"Updated timestamp to {today}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="K0 Architecture Master Document Sync Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m governance.k0.scripts.sync --check    # Validate only
    python -m governance.k0.scripts.sync --diff     # Show differences
    python -m governance.k0.scripts.sync --report   # Full report

This tool scans the codebase and compares with k0_architecture_master.md.
It does NOT modify the master document (use --update for that).
        """,
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Check sync status (exit 1 if drift detected)",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Show detailed differences",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate full sync report",
    )
    parser.add_argument(
        "--update-timestamp",
        action="store_true",
        help="Update the Last Updated timestamp in master",
    )

    args = parser.parse_args()

    # Default to --report if no args
    if not any([args.check, args.diff, args.report, args.update_timestamp]):
        args.report = True

    print()
    print("K0 Architecture Sync Tool")
    print("Master: governance/k0/k0_architecture_master.md")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    if args.update_timestamp:
        update_master_timestamp()
        return 0

    reports = run_all_checks()
    print_summary(reports)

    if args.diff or args.report:
        print_diff(reports)

    # Check mode: exit 1 if drift detected
    total_drift = sum(r.drift_count for r in reports)
    if args.check and total_drift > 0:
        print(f"\nDrift detected! {total_drift} items out of sync.")
        print("Run with --diff for details.")
        return 1

    if total_drift == 0:
        print("All components in sync with master document.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
