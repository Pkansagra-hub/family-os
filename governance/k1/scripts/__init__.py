"""
K1 Governance Automation Scripts.

Two-way sync between K1 codebase and ADR registry.
Run on-demand with `python -m governance.k1.scripts.sync`.

Scanners:
- adr_scanner: Extract ADRs from k1/docs/adrs/*.md (YAML frontmatter)
- module_scanner: Extract modules from k1/*/ directories
- event_scanner: Extract events from k1/ code (.emit(), contracts)
- contract_scanner: Extract contracts from k1/contracts/
- port_scanner: Extract port interfaces and adapter implementations

Usage:
    python -m governance.k1.scripts.sync --check    # Validate only (no changes)
    python -m governance.k1.scripts.sync --report   # Full report
    python -m governance.k1.scripts.sync --diff     # Show differences
"""
