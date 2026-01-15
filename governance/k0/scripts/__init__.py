"""
K0 Governance Automation Scripts.

Two-way sync between codebase and k0_architecture_master.md.
No CI/CD required - run on-demand with `python -m governance.k0.scripts.sync`.

Scanners:
- syscall_scanner: Extract syscalls from k0/kernel/syscalls.py
- module_scanner: Extract modules from k0/modules/*/README.md
- pipeline_scanner: Extract pipelines from k0/contracts/pipelines/*.yaml
- event_scanner: Extract events from code (.emit(), .publish())
- adr_scanner: Extract ADRs from docs/architecture/decisions-K0/*.md
- config_scanner: Extract config from k0/config/*.yaml

Usage:
    python -m governance.k0.scripts.sync --check    # Validate only (no changes)
    python -m governance.k0.scripts.sync --update   # Update master document
    python -m governance.k0.scripts.sync --diff     # Show differences
"""
