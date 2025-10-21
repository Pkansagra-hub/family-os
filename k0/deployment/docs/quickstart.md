# Deployment Quick Start (Draft)

> **Status:** ADR-003 accepted; implementation of Pulumi/Ansible stacks is in progress.

## Prerequisites

- Python 3.11+ with repository `requirements.txt` installed
- Access to Pulumi CLI and Ansible (to be bundled in Issue 8.3.1 implementation)
- Telemetry assets generated via `python -m k0.telemetry.render`
- Kernel artifacts built using the standard `k0ctl build` pipeline (pending)

## Workflow Overview

1. Select a stack (`local-single-node`, `edge-cluster`, `datacenter-ha`).
2. Run the appropriate deployment script in preview mode to review changes.
3. Apply the stack and execute post-deployment smoke tests.
4. Capture telemetry snapshots and file the MCP memory entry for traceability.

## Commands (Placeholder)

```powershell
# Preview deployment
./k0/deployment/scripts/deploy.ps1 -Stack local-single-node -Preview

# Apply deployment once stacks are implemented
./k0/deployment/scripts/deploy.ps1 -Stack local-single-node

# Smoke test
./k0/deployment/scripts/smoke.ps1 -Stack local-single-node
```

```bash
# Preview deployment
bash k0/deployment/scripts/deploy.sh local-single-node preview

# Apply deployment once stacks are implemented
bash k0/deployment/scripts/deploy.sh local-single-node apply

# Smoke test
bash k0/deployment/scripts/smoke.sh local-single-node
```

## Telemetry & MCP Logging Alignment

- Telemetry snapshots must be written to `artifacts/telemetry` and published via
  the `k0.automation.verify_security_telemetry` harness.
- Each deployment run should produce an MCP memory entry containing:
  - Stack name and git SHA
  - Pulumi state digest or artifact checksum
  - Telemetry snapshot path and verification status
  - Operators on duty and escalation notes
- Ops stakeholders (M. Ortega, K. Ramos) will review memory entries during the
  deployment change advisory meeting scheduled every Tuesday.

Feedback should be captured in `docs/development/deployment/ops-alignment.md` as
implementation proceeds.
