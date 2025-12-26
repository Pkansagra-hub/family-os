# K0 Governance Automation

**Two-way sync between codebase and `k0_architecture_master.md`**

No CI/CD required. Run on-demand before commits or when reviewing architecture.

## Quick Start

```bash
# Check sync status (validates, doesn't modify)
python -m governance.k0.scripts.sync --check

# Show detailed differences
python -m governance.k0.scripts.sync --diff

# Full report with all details
python -m governance.k0.scripts.sync --report

# Update timestamp only
python -m governance.k0.scripts.sync --update-timestamp
```

## What Gets Scanned

| Scanner | Source | Extracts | Master Section |
|---------|--------|----------|----------------|
| `syscall_scanner` | `k0/kernel/syscalls.py` | Methods, capabilities, tables | Part 7 |
| `module_scanner` | `k0/modules/*/README.md` | Module IDs, status, ADRs | Part 3 |
| `pipeline_scanner` | `k0/contracts/pipelines/*.yaml` | Pipeline IDs, stages, events | Part 2 |
| `adr_scanner` | `docs/architecture/decisions-K0/*.md` | ADR IDs, status, relations | Part 11 |
| `event_scanner` | Code + contracts + whiteboard | Topics, producers, consumers | Part 4 |

## How It Works

1. **Scanners** parse the actual codebase (Python AST, YAML, Markdown)
2. **Diff** compares scanned data with registered items in master document
3. **Report** shows what's missing in master vs what's missing in code

### Code -> Document (Discovery)

When you add new code:

1. Add a README.md to your module with standard table format
2. Add contract YAML with metadata section
3. Run `--diff` to see what needs to be registered
4. Update master document accordingly

### Document -> Code (Enforcement)

When master says something exists but code doesn't:

1. Either implement the code
2. Or remove from master (with ADR if significant)

## Individual Scanners

Run scanners independently for debugging:

```bash
# Syscalls (from k0/kernel/syscalls.py)
python -m governance.k0.scripts.syscall_scanner

# Modules (from k0/modules/*/README.md)
python -m governance.k0.scripts.module_scanner

# Pipelines (from k0/contracts/pipelines/*.yaml)
python -m governance.k0.scripts.pipeline_scanner

# ADRs (from docs/architecture/decisions-K0/*.md)
python -m governance.k0.scripts.adr_scanner

# Events (from code emit() calls + contracts)
python -m governance.k0.scripts.event_scanner
```

## Expected README Format (Modules)

For module scanner to pick up modules, use this table format in README.md:

```markdown
| Module | ID | File | Status | Performance | Tests | ADR |
|--------|-----|------|--------|-------------|-------|-----|
| **pattern_separate** | M01 | `pattern_separate.py` | Implemented | 0.88ms P95 | 16/16 | K003.1 |
```

## Exit Codes

- `0`: All synced (or report mode)
- `1`: Drift detected (with `--check`)

## Architecture

```
governance/k0/scripts/
  __init__.py          # Package init with docstring
  __main__.py          # CLI entry point
  sync.py              # Master orchestrator
  syscall_scanner.py   # Parse syscalls.py
  module_scanner.py    # Parse module READMEs
  pipeline_scanner.py  # Parse pipeline contracts
  adr_scanner.py       # Parse ADR documents
  event_scanner.py     # Scan for event emissions
```

## Future Enhancements

- [ ] `--update` mode to auto-regenerate master sections
- [ ] Pre-commit hook integration (optional)
- [ ] Config scanner for Part 13
- [ ] Storage table scanner from migrations
- [ ] Contract schema scanner from k0/contracts/schemas/
