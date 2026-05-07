# Bridge CI Gates

The bridge substrate keeps K0 and K1 cleanly separated. Six CI gates enforce
the wall and the contract registry on every PR.

| Gate | Module | What it catches |
| ---- | ------ | --------------- |
| `no_cross_kernel_imports` | `tooling.ci.gates.no_cross_kernel_imports` | Any `*.py` under `k0/` importing `k1.*` (or the reverse). |
| `bridge_not_imported_from_kernels` | `tooling.ci.gates.bridge_not_imported_from_kernels` | Any kernel module importing private bridge subpackages (`bridge.core`, `bridge.kernel`, `bridge.sync`, `bridge.connector`, `bridge.codecs`, `bridge.adapters`). Public seam (`bridge.client`, `bridge.contracts`, `bridge.testing`, `bridge.ports`, `bridge._generated.<own_role>.*`) is allowed. |
| `manifest_implementation_bound` | `tooling.ci.gates.manifest_implementation_bound` | Any `status: active` manifest lacking a generated handler/client under `bridge/_generated/`. WARNs on day-one (empty `_generated/`); fails after MS-2.5 close. |
| `schema_checksum_stable` | `tooling.ci.gates.schema_checksum_stable` | Manifest `checksums.{schema_sha256, manifest_sha256}` disagreeing with the file on disk. Auto-fix: `--update`. |
| `bus_yaml_aligned_with_registry` | `tooling.ci.gates.bus_yaml_aligned_with_registry` | Cross-kernel topic prefix in `k1/config/bus.yaml` (`k0.*`, `memory.*`, `feedback.*`, `recall.*`, `curiosity.*`, `p0[1-9].*`, `family.*`, `ifl.*`, `k1.k0.*`) without at least one matching manifest. |
| `single_ibridge_port_definition` | `tooling.ci.gates.single_ibridge_port_definition` | Any reappearance of the legacy `IBridgePort` class — definition or subclass. |

## Run locally

```bash
# All gates with the day-one mode mix (some warn, some enforce):
python -m tooling.ci.run_all_gates

# Force every gate to enforce (mirrors MS-2.5 close state):
python -m tooling.ci.run_all_gates --enforce-all

# Smoke run (every gate warn-only):
python -m tooling.ci.run_all_gates --warn-all

# Run a single gate:
python -m tooling.ci.gates.no_cross_kernel_imports
```

## Output format

Each gate prints exactly one summary line to stderr:

```text
[<gate-name>] <OK|WARN|FAIL|CRASH> (<n> violation(s)) in <duration_ms> ms
```

Offending lines go to stdout (one per line, format `<relpath>:<lineno>: <reason>`)
so log scrapers can grep them. The orchestrator emits a JSON summary line
on stderr after every gate runs:

```json
{"gates": [{"name": "...", "exit_code": 0, "duration_ms": 12}, ...],
 "failed": ["..."], "crashed": ["..."]}
```

## Allowlists

`bridge_not_imported_from_kernels` consults
`tooling/ci/known_violations/bridge_imports.txt`. Each non-comment line is
`<relpath>:<lineno>` matching exactly the leading `<relpath>:<lineno>` token
the gate prints. Add a comment after `#` describing the remediation
milestone. New entries require team approval; the file should shrink.

`no_cross_kernel_imports` allows per-line opt-out via a comment marker:

```python
from k0 import legacy  # noqa: cross-kernel — MS-3 remediation
```

The marker must include a free-form reason after the dash; the parser
only checks for the `noqa: cross-kernel` substring.

## Day-one expected state (PR#1 close, MS-2.5)

| Gate | State |
| ---- | ----- |
| `no_cross_kernel_imports` | GREEN |
| `bridge_not_imported_from_kernels` | GREEN (2 known violations allowlisted) |
| `manifest_implementation_bound` | WARN (empty `_generated/`) |
| `schema_checksum_stable` | GREEN |
| `bus_yaml_aligned_with_registry` | WARN (intentional fail-loud surface) |
| `single_ibridge_port_definition` | GREEN |

## MS-2.5 close state (PR#3)

All gates `--fail-on-violation`. `_generated/` carries `memory.write.v1`.
Stub `status: proposed` manifests cover every cross-kernel prefix in
`bus.yaml`. The 2 known wall violations remain allowlisted, scheduled for
MS-3a and MS-3b.

## Adding a new gate

1. Create `tooling/ci/gates/<name>.py`. Implement `_body(args) -> list[str]`
   returning violation lines. Wrap it with
   `tooling.ci.gates._harness.run_gate("<name>", _body)`.
2. Register the gate in `tooling.ci.run_all_gates._GATES` with its initial
   mode (`fail` or `warn`).
3. Add a row to this runbook.
4. Write `test_<name>_passes_on_clean_fixture` and
   `test_<name>_fails_on_violating_fixture_with_path_in_stderr` in
   `tests/tooling/ci/gates/test_each_gate.py`. Use `_make_minimal_repo`
   for the fixture root and `_run` to subprocess the gate.

## CI surface

* `.github/workflows/bridge_ci.yml` runs `python -m tooling.ci.run_all_gates`
  on every PR touching `bridge/`, `k0/`, `k1/`, or `tooling/`.
* `.github/workflows/codegen_no_diff.yml` runs `python -m tooling.contracts.codegen --check`
  followed by `git diff --exit-code bridge/_generated/` to catch un-vendored
  codegen drift.
