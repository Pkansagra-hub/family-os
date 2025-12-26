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

    @property
    def is_synced(self) -> bool:
        """Check if code and master are in sync."""
        return (
            not self.missing_in_master and not self.missing_in_code and not self.status_mismatches
        )

    @property
    def drift_count(self) -> int:
        """Total number of drift items."""
        return len(self.missing_in_master) + len(self.missing_in_code) + len(self.status_mismatches)


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


def run_all_checks() -> list[SyncReport]:
    """Run all sync checks and return reports."""
    reports = []

    print("Scanning codebase...")
    print()

    print("  [1/5] Scanning syscalls...", end=" ", flush=True)
    reports.append(check_syscalls())
    print(f"found {reports[-1].scanned_count}")

    print("  [2/5] Scanning pipelines...", end=" ", flush=True)
    reports.append(check_pipelines())
    print(f"found {reports[-1].scanned_count}")

    print("  [3/5] Scanning modules...", end=" ", flush=True)
    reports.append(check_modules())
    print(f"found {reports[-1].scanned_count}")

    print("  [4/5] Scanning ADRs...", end=" ", flush=True)
    reports.append(check_adrs())
    print(f"found {reports[-1].scanned_count}")

    print("  [5/5] Scanning events...", end=" ", flush=True)
    reports.append(check_events())
    print(f"found {reports[-1].scanned_count}")

    print()
    return reports


def print_summary(reports: list[SyncReport]) -> None:
    """Print sync summary."""
    print("=" * 70)
    print("SYNC STATUS SUMMARY")
    print("=" * 70)
    print()
    print(
        f"{'Category':<15} {'Scanned':<10} {'Registered':<12} {'Missing(M)':<12} {'Missing(C)':<12} {'Status':<10}"
    )
    print("-" * 70)

    total_drift = 0
    for r in reports:
        status = "OK" if r.is_synced else f"DRIFT({r.drift_count})"
        total_drift += r.drift_count
        print(
            f"{r.category:<15} {r.scanned_count:<10} {r.registered_count:<12} "
            f"{len(r.missing_in_master):<12} {len(r.missing_in_code):<12} {status:<10}"
        )

    print("-" * 70)
    overall = "SYNCED" if total_drift == 0 else f"DRIFT DETECTED ({total_drift} items)"
    print(f"{'OVERALL':<15} {'':<10} {'':<12} {'':<12} {'':<12} {overall}")
    print()


def print_diff(reports: list[SyncReport]) -> None:
    """Print detailed diff for each category."""
    print()
    print("=" * 70)
    print("DETAILED DIFF")
    print("=" * 70)

    for r in reports:
        if r.is_synced:
            continue

        print(f"\n{r.category}:")
        print("-" * 40)

        if r.missing_in_master:
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
