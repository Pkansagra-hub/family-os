"""Run all bridge CI gates as subprocesses, aggregate, exit nonzero on failure.

Each gate is invoked as ``python -m tooling.ci.gates.<name>`` so a single
gate's crash cannot poison the rest of the run. Per-gate exit codes:

* 0 — clean (no violations, or violations suppressed by ``--warn-only``).
* 1 — violations and gate is enforcing.
* 2 — gate crashed (report but do not block).

Orchestrator emits to stderr a final JSON line for log scrapers::

    {"gates": [{"name": ..., "exit_code": ..., "duration_ms": ...}, ...],
     "failed": ["..."], "crashed": ["..."]}

Plus a human-readable ``::error::N gate(s) failed`` line when any gate
exits 1, so GitHub Actions surfaces it as a job-level error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# (gate-module, default-mode). MS-2.5 closed all six gates as enforcing
# at exit-criterion (Epic 2.5.6). Override per-run via ``--enforce`` or
# ``--warn-only`` if you need to land an emergency manifest.
_GATES: tuple[tuple[str, str], ...] = (
    ("tooling.ci.gates.no_cross_kernel_imports", "fail"),
    ("tooling.ci.gates.bridge_not_imported_from_kernels", "fail"),
    ("tooling.ci.gates.manifest_implementation_bound", "fail"),
    ("tooling.ci.gates.schema_checksum_stable", "fail"),
    ("tooling.ci.gates.bus_yaml_aligned_with_registry", "fail"),
    ("tooling.ci.gates.single_ibridge_port_definition", "fail"),
    ("tooling.ci.gates.bridge_client_construction_via_runtime_only", "fail"),
    ("tooling.ci.gates.degraded_mode_derived_only", "fail"),
    ("tooling.ci.gates.adapter_loc_budget", "fail"),
    ("tooling.ci.gates.ca_bundle_not_placeholder", "fail"),
    ("tooling.ci.gates.manifest_signatures_valid", "fail"),
    ("tooling.ci.gates.dev_trust_anchor_audit_present", "fail"),
)


@dataclass
class GateResult:
    name: str
    exit_code: int
    duration_ms: int
    stdout: str
    stderr: str


def _short(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def _run_gate(
    module: str,
    mode: str,
    *,
    extra_args: list[str],
    repo_root: Path,
) -> GateResult:
    cmd = [sys.executable, "-m", module]
    if mode == "fail":
        cmd.append("--fail-on-violation")
    elif mode == "warn":
        cmd.append("--warn-only")
    cmd.extend(extra_args)

    # The subprocess imports ``tooling.ci.gates.*``, which lives next to
    # this file. ``cwd`` is the cwd we hand the subprocess: we use the
    # source-checkout root (parent of the ``tooling`` package), NOT the
    # ``repo_root`` we are inspecting (which may be a temp fixture).
    source_root = Path(__file__).resolve().parents[2]

    started = time.perf_counter()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(source_root),
        check=False,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return GateResult(
        name=_short(module),
        exit_code=proc.returncode,
        duration_ms=elapsed_ms,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tooling.ci.run_all_gates",
        description="Run all bridge CI gates and aggregate results.",
    )
    parser.add_argument(
        "--enforce-all",
        action="store_true",
        help="Force every gate into --fail-on-violation mode.",
    )
    parser.add_argument(
        "--warn-all",
        action="store_true",
        help="Force every gate into --warn-only mode (smoke check).",
    )
    parser.add_argument(
        "--repo-root",
        type=str,
        default=str(Path(__file__).resolve().parents[2]),
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    extra: list[str] = ["--repo-root", str(repo_root)]

    results: list[GateResult] = []
    for module, default_mode in _GATES:
        mode = default_mode
        if args.enforce_all:
            mode = "fail"
        elif args.warn_all:
            mode = "warn"
        r = _run_gate(module, mode, extra_args=extra, repo_root=repo_root)
        results.append(r)
        # Stream the gate's own stderr / stdout to ours, prefix-tagged.
        for line in r.stderr.splitlines():
            print(line, file=sys.stderr)
        for line in r.stdout.splitlines():
            print(line)

    failed = [r.name for r in results if r.exit_code == 1]
    crashed = [r.name for r in results if r.exit_code == 2]

    summary = {
        "gates": [
            {
                "name": r.name,
                "exit_code": r.exit_code,
                "duration_ms": r.duration_ms,
            }
            for r in results
        ],
        "failed": failed,
        "crashed": crashed,
    }
    print(json.dumps(summary), file=sys.stderr)

    if failed:
        print(
            f"::error::{len(failed)} gate(s) failed: {', '.join(failed)}",
            file=sys.stderr,
        )
        return 1
    if crashed:
        print(
            f"::warning::{len(crashed)} gate(s) crashed: {', '.join(crashed)}",
            file=sys.stderr,
        )
        return 0
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
