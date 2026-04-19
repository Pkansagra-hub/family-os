"""
K1 Master Sync Orchestrator - Scan K1 codebase and validate consistency.

Operations:
    --check    : Validate consistency (exit 1 on drift)
    --diff     : Show differences and issues
    --report   : Generate full sync report (default)
    --scan     : Run specific scanner only

This tool scans K1 code, contracts, ADRs, ports, and events to:
- Detect drift between documentation and implementation
- Validate cross-references (ADR -> event, contract -> module)
- Report on port/adapter coverage
- Track module maturity and completeness

Usage:
    python -m governance.k1.scripts.sync --check
    python -m governance.k1.scripts.sync --report
    python -m governance.k1.scripts.sync --diff
    python -m governance.k1.scripts.sync --scan adrs
    python -m governance.k1.scripts.sync --scan events
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class SyncReport:
    """Report from a single scanner check."""

    category: str
    scanned_count: int
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        """Check if no issues found."""
        return not self.issues

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


def _get_repo_root() -> Path:
    """Get repository root from script location."""
    return Path(__file__).parent.parent.parent.parent


# --- Scanner Check Functions ---


def check_adrs() -> SyncReport:
    """Check ADR consistency and completeness."""
    from governance.k1.scripts.adr_scanner import (
        diff_with_registry,
        generate_summary,
        scan_adrs,
        scan_legacy_adrs,
    )

    adrs = scan_adrs()
    legacy = scan_legacy_adrs()

    diff = diff_with_registry(adrs)
    summary = generate_summary(adrs)

    warnings: list[str] = []
    if legacy:
        warnings.append(
            f"{len(legacy)} legacy ADRs in docs/architecture/decisions-K1/ "
            f"(not yet migrated to k1/docs/adrs/)"
        )

    return SyncReport(
        category="ADRs",
        scanned_count=len(adrs),
        issues=diff["issues"],
        warnings=warnings,
        details={
            "summary": summary,
            "legacy_count": len(legacy),
        },
    )


def check_events() -> SyncReport:
    """Check event consistency."""
    from governance.k1.scripts.event_scanner import diff_with_registry, scan_events

    events = scan_events()
    diff = diff_with_registry(events)

    issues = list(diff["issues"])
    warnings: list[str] = []

    if diff["code_only"]:
        warnings.append(f"{len(diff['code_only'])} events found in code but not in contracts")
    if diff["no_producer"]:
        warnings.append(
            f"{len(diff['no_producer'])} events have emit locations but no identified producer"
        )
    if diff["no_consumer"]:
        warnings.append(f"{len(diff['no_consumer'])} active events have no consumers")

    return SyncReport(
        category="Events",
        scanned_count=len(events),
        issues=issues,
        warnings=warnings,
        details={
            "code_only": diff["code_only"],
            "contract_only": diff["contract_only"],
            "no_producer": diff["no_producer"],
            "no_consumer": diff["no_consumer"],
        },
    )


def check_modules() -> SyncReport:
    """Check module consistency."""
    from governance.k1.scripts.module_scanner import (
        diff_with_registry,
        generate_summary,
        scan_modules,
    )

    modules = scan_modules()
    diff = diff_with_registry(modules)
    summary = generate_summary(modules)

    return SyncReport(
        category="Modules",
        scanned_count=len(modules),
        issues=diff["issues"],
        details={"summary": summary},
    )


def check_contracts() -> SyncReport:
    """Check contract consistency."""
    from governance.k1.scripts.contract_scanner import diff_with_registry, scan_contracts

    contracts = scan_contracts()
    diff = diff_with_registry(contracts)

    return SyncReport(
        category="Contracts",
        scanned_count=len(contracts),
        issues=diff["issues"],
        details={"by_type": diff.get("by_type", {})},
    )


def check_ports() -> SyncReport:
    """Check port/adapter consistency."""
    from governance.k1.scripts.port_scanner import diff_with_registry, generate_summary, scan_ports

    ports = scan_ports()
    diff = diff_with_registry(ports)
    summary = generate_summary(ports)

    warnings: list[str] = list(diff.get("warnings", []))
    if summary["unimplemented"]:
        warnings.append(f"{len(summary['unimplemented'])} ports have no production adapter")

    return SyncReport(
        category="Ports",
        scanned_count=len(ports),
        issues=diff["issues"],
        warnings=warnings,
        details={"summary": summary},
    )


def check_adr_event_xrefs() -> SyncReport:
    """
    Cross-reference ADRs with events.

    Validates that events referenced in ADRs actually exist in the codebase.
    Misses are reported as **warnings** rather than blocking issues because
    K1 ADRs frequently reference events that are *planned* but not yet
    landed (e.g. agent-fabric capability events) or that were renamed
    during the K1 migration. Wholesale reconciliation is tracked as a
    separate sweep; until then we surface drift without failing the gate.
    """
    from governance.k1.scripts.adr_scanner import scan_adrs
    from governance.k1.scripts.event_scanner import scan_events

    adrs = scan_adrs()
    events = scan_events()

    event_topics = {e.topic for e in events}
    warnings: list[str] = []

    for adr in adrs:
        for event_ref in adr.related_events:
            if event_ref not in event_topics:
                warnings.append(
                    f"{adr.adr_id}: references event '{event_ref}' "
                    f"which was not found in codebase"
                )

    return SyncReport(
        category="ADR-Event XRefs",
        scanned_count=len(adrs),
        issues=[],
        warnings=warnings,
    )


def check_adr_contract_xrefs() -> SyncReport:
    """
    Cross-reference ADRs with contracts.

    Validates that contracts referenced in ADRs exist. Misses are reported
    as **warnings** for the same reason as event XRefs: many ADR contract
    references point to FlatBuffers schemas and contract YAMLs that were
    planned but never landed (e.g. agent-fabric ``.fbs`` files). Wholesale
    reconciliation is a separate sweep.
    """
    from governance.k1.scripts.adr_scanner import scan_adrs
    from governance.k1.scripts.contract_scanner import scan_contracts

    adrs = scan_adrs()
    contracts = scan_contracts()

    contract_ids = {c.contract_id for c in contracts}
    warnings: list[str] = []

    for adr in adrs:
        for contract_ref in adr.related_contracts:
            if contract_ref not in contract_ids:
                warnings.append(
                    f"{adr.adr_id}: references contract '{contract_ref}' " f"which was not found"
                )

    return SyncReport(
        category="ADR-Contract XRefs",
        scanned_count=len(adrs),
        issues=[],
        warnings=warnings,
    )


def check_adr_port_xrefs() -> SyncReport:
    """
    Cross-reference ADRs with ports.

    Validates that ports referenced in ADRs exist. Misses are reported as
    **warnings**; many ADR port references (e.g. ``IEnvelopeCodec``,
    ``ISessionStateReader``) point to interfaces that were planned but
    never landed under their referenced names. Wholesale reconciliation
    is a separate sweep.
    """
    from governance.k1.scripts.adr_scanner import scan_adrs
    from governance.k1.scripts.port_scanner import scan_ports

    adrs = scan_adrs()
    ports = scan_ports()

    port_names = {p.port_name for p in ports}
    warnings: list[str] = []

    for adr in adrs:
        for port_ref in adr.related_ports:
            if port_ref not in port_names:
                warnings.append(f"{adr.adr_id}: references port '{port_ref}' " f"which was not found")

    return SyncReport(
        category="ADR-Port XRefs",
        scanned_count=len(adrs),
        issues=[],
        warnings=warnings,
    )


# --- Orchestrator ---


def run_all_checks() -> list[SyncReport]:
    """Run all K1 governance checks."""
    reports: list[SyncReport] = []

    checks = [
        ("ADRs", check_adrs),
        ("Events", check_events),
        ("Modules", check_modules),
        ("Contracts", check_contracts),
        ("Ports", check_ports),
        ("ADR-Event XRefs", check_adr_event_xrefs),
        ("ADR-Contract XRefs", check_adr_contract_xrefs),
        ("ADR-Port XRefs", check_adr_port_xrefs),
    ]

    total = len(checks)
    for i, (name, check_fn) in enumerate(checks, 1):
        print(f"  [{i}/{total}] Scanning {name}...", end=" ", flush=True)
        try:
            report = check_fn()
            reports.append(report)
            status = "OK" if report.is_clean else f"{report.issue_count} issues"
            print(f"found {report.scanned_count} ({status})")
        except Exception as e:
            print(f"ERROR: {e}")
            reports.append(
                SyncReport(
                    category=name,
                    scanned_count=0,
                    issues=[f"Scanner failed: {e}"],
                )
            )

    print()
    return reports


def run_single_check(scanner_name: str) -> list[SyncReport]:
    """Run a single scanner by name."""
    scanner_map = {
        "adrs": check_adrs,
        "events": check_events,
        "modules": check_modules,
        "contracts": check_contracts,
        "ports": check_ports,
        "xrefs-events": check_adr_event_xrefs,
        "xrefs-contracts": check_adr_contract_xrefs,
        "xrefs-ports": check_adr_port_xrefs,
    }

    if scanner_name not in scanner_map:
        print(f"Unknown scanner: {scanner_name}")
        print(f"Available: {', '.join(scanner_map.keys())}")
        return []

    print(f"  Running {scanner_name} scanner...", end=" ", flush=True)
    report = scanner_map[scanner_name]()
    status = "OK" if report.is_clean else f"{report.issue_count} issues"
    print(f"found {report.scanned_count} ({status})")
    print()

    return [report]


# --- Output Formatting ---


def print_summary(reports: list[SyncReport]) -> None:
    """Print sync summary table."""
    print("=" * 70)
    print("K1 SYNC STATUS SUMMARY")
    print("=" * 70)
    print()
    print(f"{'Category':<20} {'Scanned':<10} {'Issues':<10} {'Warnings':<10} {'Status':<10}")
    print("-" * 60)

    total_issues = 0
    total_warnings = 0
    for r in reports:
        status = "OK" if r.is_clean else f"ISSUES({r.issue_count})"
        total_issues += r.issue_count
        total_warnings += r.warning_count
        print(
            f"{r.category:<20} {r.scanned_count:<10} {r.issue_count:<10} "
            f"{r.warning_count:<10} {status:<10}"
        )

    print("-" * 60)
    overall = "CLEAN" if total_issues == 0 else f"ISSUES DETECTED ({total_issues})"
    print(f"{'OVERALL':<20} {'':<10} {total_issues:<10} {total_warnings:<10} {overall}")
    print()


def print_diff(reports: list[SyncReport]) -> None:
    """Print detailed diff for each category."""
    print()
    print("=" * 70)
    print("DETAILED ISSUES")
    print("=" * 70)

    has_output = False
    for r in reports:
        if r.is_clean and not r.warnings:
            continue

        has_output = True
        print(f"\n{r.category}:")
        print("-" * 40)

        if r.issues:
            print(f"  Issues ({r.issue_count}):")
            for item in r.issues[:15]:
                print(f"    ! {item}")
            if len(r.issues) > 15:
                print(f"    ... and {len(r.issues) - 15} more")

        if r.warnings:
            print(f"  Warnings ({r.warning_count}):")
            for item in r.warnings[:10]:
                print(f"    ~ {item}")

    if not has_output:
        print("\nAll categories clean (no issues to show).")


def print_module_details(reports: list[SyncReport]) -> None:
    """Print detailed module breakdown."""
    for r in reports:
        if r.category != "Modules":
            continue

        summary = r.details.get("summary", {})
        if not summary:
            continue

        print()
        print("=" * 70)
        print("MODULE BREAKDOWN")
        print("=" * 70)
        print()
        print(f"Total modules: {summary.get('total_modules', 0)}")
        print(f"Total files:   {summary.get('total_files', 0)}")
        print(f"Total lines:   {summary.get('total_lines', 0)}")
        print(f"With contract: {summary.get('with_contract', 0)}")
        print(f"With README:   {summary.get('with_readme', 0)}")
        print(f"Total ports:   {summary.get('total_ports', 0)}")
        print(f"Total tests:   {summary.get('total_tests', 0)}")

        by_status = summary.get("by_status", {})
        if by_status:
            print("\nBy Status:")
            for status, count in sorted(by_status.items()):
                print(f"  {status}: {count}")
        print()
        break


def print_port_details(reports: list[SyncReport]) -> None:
    """Print port/adapter breakdown."""
    for r in reports:
        if r.category != "Ports":
            continue

        summary = r.details.get("summary", {})
        if not summary:
            continue

        print()
        print("=" * 70)
        print("PORT/ADAPTER BREAKDOWN")
        print("=" * 70)
        print()
        print(f"Total ports:    {summary.get('total_ports', 0)}")
        print(f"Total adapters: {summary.get('total_adapters', 0)}")
        print(f"Null adapters:  {summary.get('total_null', 0)}")
        print(f"Mock adapters:  {summary.get('total_mock', 0)}")

        by_module = summary.get("by_module", {})
        if by_module:
            print("\nPorts by Module:")
            for mod, count in sorted(by_module.items()):
                print(f"  {mod}: {count}")

        unimplemented = summary.get("unimplemented", [])
        if unimplemented:
            print(f"\nUnimplemented ({len(unimplemented)}):")
            for name in unimplemented[:10]:
                print(f"  ! {name}")
        print()
        break


# --- Entry Point ---


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="K1 Architecture Sync Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m governance.k1.scripts.sync --check       # Validate only
    python -m governance.k1.scripts.sync --diff        # Show issues
    python -m governance.k1.scripts.sync --report      # Full report
    python -m governance.k1.scripts.sync --scan adrs   # Single scanner

Available scanners:
    adrs, events, modules, contracts, ports,
    xrefs-events, xrefs-contracts, xrefs-ports
        """,
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Check sync status (exit 1 if issues detected)",
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
        "--scan",
        type=str,
        metavar="SCANNER",
        help="Run single scanner (adrs, events, modules, contracts, ports)",
    )

    args = parser.parse_args()

    # Default to --report if no args
    if not any([args.check, args.diff, args.report, args.scan]):
        args.report = True

    print()
    print("K1 Architecture Sync Tool")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Run checks
    if args.scan:
        reports = run_single_check(args.scan)
    else:
        reports = run_all_checks()

    if not reports:
        return 1

    # Output
    print_summary(reports)

    if args.report:
        print_module_details(reports)
        print_port_details(reports)

    if args.diff or args.report:
        print_diff(reports)

    # Check mode: exit 1 if issues detected
    total_issues = sum(r.issue_count for r in reports)
    if args.check and total_issues > 0:
        print(f"\nIssues detected! {total_issues} items need attention.")
        print("Run with --diff for details.")
        return 1

    if total_issues == 0:
        print("All K1 governance checks passed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
