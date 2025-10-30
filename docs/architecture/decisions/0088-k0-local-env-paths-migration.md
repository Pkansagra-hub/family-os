# ADR-0088: Migrate k0 local env helpers from k0/deployment to k0/deploy

Status: IMPLEMENTED

Date: 2025-10-30

Authors: @github-copilot

## Context

We removed the legacy Pulumi/Ansible-based `k0/deployment` tree and consolidated local Docker workflows under `k0/deploy` with a single PowerShell orchestrator (`k0/deploy/k0.ps1`). Some development utilities still referenced paths under `k0/deployment`, notably `k0/local/env.py` for env file discovery and container path coercion for `/data/*`. This created a stale dependency on a deleted folder and risked broken local tooling.

Constraints:

- Preserve the ability to override env via `K0_ENV_FILE`.
- Keep default path resolution simple and aligned with `k0/deploy` layout created by `k0.ps1` (env/, data/, secrets/).

## Decision

Update `k0/local/env.py` to:

- Discover env overrides from:
  - Explicit `K0_ENV_FILE` if set
  - `k0/deploy/env/k0.env`
  - `k0/deploy/.env` (optional, if present)
- Map container paths starting with `/data/` to the host path `k0/deploy/data` by default, unless a custom `relative_base` is provided.

Rationale:

- Aligns helper utilities with the new, single-source-of-truth deploy folder
- Avoids broken references to the removed `k0/deployment` structure
- Maintains explicit override escape hatch via `K0_ENV_FILE`

## Alternatives Considered

- Keep old `k0/deployment` discovery paths: rejected because the directory is removed, and this would re-introduce drift and confusion.
- Introduce an additional compatibility layer that checks both old and new locations: rejected to keep behavior clear and avoid masking misconfigurations. `K0_ENV_FILE` provides an explicit compatibility option if needed.

## Consequences

Positive:

- Consistent local development experience aligned with `k0/deploy` and `k0.ps1`
- Removes stale references and reduces confusion

Risks/downsides:

- If a developer relied on the old generated locations without using `k0.ps1`, env discovery will no longer find those files. Mitigation: set `K0_ENV_FILE` explicitly or move env files to `k0/deploy/env/k0.env`.

Performance/Security:

- No performance impact; simple path lookups.
- No security impact; same env sourcing behavior and explicit override support.

## Related ADRs

- Relates to ongoing consolidation of local deployment workflows; no direct supersedes.

## Related Code

- Implementation: `k0/local/env.py`
- Orchestration: `k0/deploy/k0.ps1`
- Compose files: `k0/deploy/docker-compose.yml`, `k0/deploy/local-single-node-telemetry.yml`

## Revision History

- 2025-10-30: Implemented path migration in `k0/local/env.py` and recorded decision.
- 2025-10-30: Implemented path migration in `k0/local/env.py` and recorded decision.
