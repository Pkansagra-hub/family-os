# K1 Governance Automation

Automated sync tooling for K1 architecture governance. Scans K1 codebase and validates consistency across ADRs, modules, contracts, events, and ports.

## Quick Start

```powershell
# Full report (default)
python -m governance.k1.scripts.sync --report

# Check only (exit 1 on issues)
python -m governance.k1.scripts.sync --check

# Show detailed issues
python -m governance.k1.scripts.sync --diff

# Run single scanner
python -m governance.k1.scripts.sync --scan adrs
python -m governance.k1.scripts.sync --scan events
python -m governance.k1.scripts.sync --scan modules
python -m governance.k1.scripts.sync --scan contracts
python -m governance.k1.scripts.sync --scan ports
```

## Scanners

| Scanner | Source | What It Scans |
|---------|--------|---------------|
| `adr_scanner` | `k1/docs/adrs/*.md` | ADR YAML frontmatter, ID validation, cross-refs |
| `event_scanner` | `k1/**/*.py`, `k1/contracts/` | Event emissions, subscriptions, contract events |
| `module_scanner` | `k1/*/` directories | Module directories, contracts, ports, tests |
| `contract_scanner` | `k1/contracts/**/*.yaml` | Module contracts, schemas, wiring, policies |
| `port_scanner` | `k1/**/ports/*.py` | Port interfaces (ABC/Protocol), adapter implementations |
| `sync` | All scanners | Master orchestrator, cross-reference validation |

## Architecture

```
governance/k1/
  scripts/
    __init__.py          # Package init with docstring
    __main__.py          # Entry point: python -m governance.k1.scripts.sync
    sync.py              # Master orchestrator (8 checks + cross-refs)
    adr_scanner.py       # ADR scanner (YAML frontmatter + legacy support)
    event_scanner.py     # Event scanner (emit/subscribe + contracts)
    module_scanner.py    # Module scanner (directories + contracts)
    contract_scanner.py  # Contract scanner (YAML contracts + schemas)
    port_scanner.py      # Port/adapter scanner (hexagonal pattern)
    README.md            # This file
```

## Check Categories

The sync orchestrator runs 8 checks:

| # | Check | Description |
|---|-------|-------------|
| 1 | ADRs | ADR format, IDs, status, cross-references |
| 2 | Events | Event emissions vs contracts, producers, consumers |
| 3 | Modules | Module completeness (contract, README, init, tests) |
| 4 | Contracts | Contract validity, schema refs, required fields |
| 5 | Ports | Port interface coverage, adapter implementations |
| 6 | ADR-Event XRefs | Events referenced in ADRs exist in code |
| 7 | ADR-Contract XRefs | Contracts referenced in ADRs exist |
| 8 | ADR-Port XRefs | Ports referenced in ADRs exist |

## ADR Format

K1 ADRs use YAML frontmatter for machine-parseable sync. See `k1/docs/adrs/README.md` for full format documentation.

Key fields:
- `adr_id`: Module-prefixed ID (FAB-001, SS-001, K1-001)
- `status`: Proposed, Accepted, Deprecated, Superseded
- `module`: Target module (fabric, sessionstate, etc.)
- `related_events`, `related_contracts`, `related_ports`: Cross-references
- `implements_issue`: Link to implementation plan issue

## Differences from K0 Governance

| Aspect | K0 | K1 |
|--------|----|----|
| ADR Format | Inline markdown (`**Status**: Accepted`) | YAML frontmatter |
| ADR IDs | Sequential (K001, K002) | Module-prefixed (FAB-001, SS-001) |
| Master Doc | `k0_architecture_master.md` (central) | Per-scanner validation (distributed) |
| Port Scanner | N/A (no hex pattern) | Full port/adapter scanning |
| Cross-Refs | Manual | Automated ADR -> event/contract/port |
| Contracts | `k0/contracts/modules/*.yaml` | `k1/contracts/modules/<mod>/*.yaml` |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | Issues detected (--check mode) or scanner error |

## Adding New Scanners

1. Create `governance/k1/scripts/<name>_scanner.py`
2. Implement: `scan_<name>()`, `generate_markdown_table()`, `diff_with_registry()`
3. Add `check_<name>()` function in `sync.py`
4. Register in `run_all_checks()` and `run_single_check()` maps
5. Update this README
