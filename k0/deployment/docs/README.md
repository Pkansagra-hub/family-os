# FamilyOS Deployment Toolchain

This directory accompanies ADR-003 (accepted) and provides operator-facing
artifacts for running Pulumi stacks, hydrating Ansible roles, and executing
deployment smoke tests. Content will continue to grow alongside the
implementation milestones tracked in `k0/plan.md`.

## Contents

- `pulumi/` – Infrastructure programs, bundle utilities, validation helpers.
- `ansible/` – Host configuration, secret management, and post-deploy checks.
- `compose/` – Jinja templates used to build Docker Compose bundles.
- `scripts/` – Cross-platform deploy/smoke helpers.
- `docs/` – Reference documentation (this file, quick start guides, runbooks).

## Pulumi Preview Smoke Harness

Use the new automation harness to execute a Pulumi preview for any supported
stack, materialise Compose fragments, and validate bundle manifests. The helper
scripts wrap the harness for POSIX shells and PowerShell:

- POSIX: `./k0/deployment/scripts/smoke.sh local-single-node`
- PowerShell: `pwsh ./k0/deployment/scripts/smoke.ps1 -Stack local-single-node`

Each run writes artifacts under `artifacts/pulumi/<stack>/`:

- `workspace/` – ephemeral Pulumi automation workspace.
- `state/` – local Pulumi backend state (file:// encoded) used for the preview.
- `bundles/<stack>/` – rendered bundle manifests and Compose fragments.

The harness performs schema validation on the generated JSON/YAML manifests and
fails fast if the Pulumi preview reports resource changes when `--expect-no-changes`
is supplied. Additional config can be provided via YAML using
`--config path/to/config.yaml` where keys map directly to Pulumi namespaces,
for example:

```yaml
config:
	k0-storage:
		kernel_port: 9000
secrets:
	- key: k0-secrets:secret:api-token
		value: example-value
```

## Bundle Manifest Layout

Bundle manifests are emitted as `<stack>-bundle.json` and `<stack>-bundle.yaml`.
Schema validation is enforced via `k0/deployment/pulumi/schema/bundle_manifest.schema.json`.
The documents contain:

- `stack` – stack identifier (`local-single-node`, `edge-cluster`, etc.).
- `generated_at` – UTC timestamp in ISO 8601 format.
- `components` – rendered artifacts with `component`, `path`, `sha256`, `size_bytes`.
- `secrets` – sync metadata, including items missing from Pulumi config.
- `extra.outputs` – optional module-specific metadata (storage, telemetry outputs).

Run the validator directly against any path or directory:

```shell
python -m k0.deployment.pulumi.validation artifacts/pulumi/local-single-node/bundles/local-single-node
```

## Telemetry Snapshots

The smoke scripts continue to invoke `python -m k0.automation.verify_security_telemetry`
after the Pulumi preview. Ensure `artifacts/telemetry/` contains the latest
Prometheus security snapshots before running the smoke harness so metric coverage
remains enforced during CI and local validation.

## Deployment Orchestration

The deployment scripts (`deploy.ps1` / `deploy.sh`) orchestrate the complete deployment workflow:

### Quick Start

**PowerShell (Windows):**
```powershell
# Mock mode (test without Pulumi/Ansible installed)
.\k0\deployment\scripts\deploy.ps1 -Stack local-single-node -Preview -Mock
.\k0\deployment\scripts\deploy.ps1 -Stack local-single-node -Mock

# Preview mode (Pulumi preview only - requires Pulumi)
.\k0\deployment\scripts\deploy.ps1 -Stack local-single-node -Preview

# Full deployment (Pulumi apply + Ansible playbooks + telemetry - requires Pulumi + Ansible)
.\k0\deployment\scripts\deploy.ps1 -Stack local-single-node

# Specify custom inventory
.\k0\deployment\scripts\deploy.ps1 -Stack edge-cluster -Inventory my-inventory

# Custom artifacts directory
.\k0\deployment\scripts\deploy.ps1 -Stack datacenter-ha -ArtifactsRoot "D:\artifacts"
```

**Bash (Linux/macOS):**
```bash
# Preview mode
./k0/deployment/scripts/deploy.sh local-single-node preview

# Full deployment
./k0/deployment/scripts/deploy.sh local-single-node apply

# Specify custom inventory
./k0/deployment/scripts/deploy.sh edge-cluster apply my-inventory
```

> **Note**: Use the `-Mock` flag (PowerShell) to test deployment workflows without installing Pulumi or Ansible. Mock mode simulates tool execution and creates realistic artifacts for testing.

### Workflow Steps

The deployment script executes these steps in sequence:

1. **Pulumi Operation** (`preview` or `up --yes`)
   - Selects the target stack
   - Generates infrastructure manifests and Compose bundles
   - Exports stack outputs to `artifacts/pulumi/<stack>/`

2. **Ansible Playbook Execution** (apply mode only)
   - Auto-detects inventory based on stack:
     - `local-single-node` → `sample-dev`
     - `edge-cluster`, `datacenter-ha` → `sample-prod`
   - Executes `playbooks/site.yml` with all three roles
   - Stages secrets, compose bundles, and telemetry configurations

3. **Telemetry Snapshot Capture** (apply mode only)
   - Runs `verify_security_telemetry` to validate metrics
   - Stores snapshots in `artifacts/telemetry/<stack>/`

4. **Timeline Artifact Generation**
   - Creates `deployment-timeline-<stack>-<timestamp>.json`
   - Captures step outcomes, exit codes, and error details
   - Enables post-mortem analysis and CI auditing

### Timeline JSON Format

```json
{
  "stack": "local-single-node",
  "mode": "apply",
  "started_at": "2025-01-03T12:00:00Z",
  "completed_at": "2025-01-03T12:05:00Z",
  "status": "success",
  "steps": [
    {
      "name": "pulumi_operation",
      "status": "completed",
      "timestamp": "2025-01-03T12:01:30Z",
      "metadata": {"command": "pulumi up --yes", "exit_code": 0}
    },
    {
      "name": "ansible_playbook",
      "status": "completed",
      "timestamp": "2025-01-03T12:04:15Z",
      "metadata": {"inventory": "sample-dev", "playbook": "site.yml", "exit_code": 0}
    },
    {
      "name": "telemetry_snapshot",
      "status": "completed",
      "timestamp": "2025-01-03T12:05:00Z",
      "metadata": {"directory": "artifacts/telemetry/local-single-node"}
    }
  ]
}
```

## Ansible Roles

Three Ansible roles (`secrets`, `kernel`, `telemetry`) consume Pulumi bundle
artifacts to configure hosts without ad-hoc scripting:

- **`secrets`** reads `*-bundle.json`, copies generated secret metadata under
	`/etc/familyos/secrets/`, emits `*.value` files for material available in
	Pulumi config, and records a machine-readable `state.yml` with available and
	missing keys.
- **`kernel`** stages compose fragments under `/opt/familyos/compose/`, copies the
	bundle manifest for auditing, optionally applies `docker compose up -d`, and
	renders a `familyos@<stack>.service` unit when `familyos_systemd_manage=true`.
- **`telemetry`** stores telemetry compose overlays, writes `telemetry-outputs.json`
	with exported ports, and executes
	`python -m k0.automation.verify_security_telemetry --directory <snapshots>` to
	enforce snapshot coverage without sleeps.

### Role Invocation Examples

Execute the roles through `playbooks/site.yml`. The deployment scripts handle this
automatically, but for manual execution:

**PowerShell:**
```powershell
cd k0\deployment\ansible

# Local single-node deployment
ansible-playbook -i inventories\sample-dev\hosts.yml playbooks\site.yml

# Edge cluster with custom variables
ansible-playbook -i inventories\sample-prod\hosts.yml playbooks\site.yml `
	-e deployment_role=edge-cluster `
	-e familyos_bundle_manifest="artifacts/pulumi/edge-cluster/bundles/edge-cluster/edge-cluster-bundle.json" `
	-e familyos_compose_apply=true `
	-e familyos_systemd_manage=true
```

**Bash:**
```bash
cd k0/deployment/ansible

# Local single-node deployment
ansible-playbook -i inventories/sample-dev/hosts.yml playbooks/site.yml

# Datacenter-HA with custom variables
ansible-playbook -i inventories/sample-prod/hosts.yml playbooks/site.yml \
	-e deployment_role=datacenter-ha \
	-e familyos_bundle_manifest="artifacts/pulumi/datacenter-ha/bundles/datacenter-ha/datacenter-ha-bundle.json" \
	-e familyos_compose_apply=true \
	-e familyos_systemd_manage=true
```

### Role Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `deployment_role` | `local-single-node` | Stack identifier for configuration selection |
| `familyos_repo_root` | `{{ playbook_dir }}/../../..` | Repository root path |
| `familyos_bundle_manifest` | Auto-detected | Path to bundle JSON manifest |
| `familyos_secret_destination_root` | `/etc/familyos/secrets` | Secrets storage directory |
| `familyos_compose_root` | `/opt/familyos/compose` | Compose bundle staging directory |
| `familyos_compose_apply` | `false` | Execute `docker compose up -d` after staging |
| `familyos_systemd_manage` | `false` | Install and enable systemd service unit |
| `familyos_telemetry_snapshot_directory` | `artifacts/security-telemetry` | Telemetry snapshot output path |

### Validation

Validate Ansible roles syntax and structure:

```powershell
# Run validation script
python k0\deployment\ansible\validate.py

# Skip dry-run (syntax check only)
python k0\deployment\ansible\validate.py --skip-dry-run

# Validate specific inventory
python k0\deployment\ansible\validate.py --inventory sample-dev
```

The validation script checks:
- Role directory structure completeness
- Playbook YAML syntax via `ansible-playbook --syntax-check`
- Dry-run execution via `ansible-playbook --check` (optional)

## Next Steps

- Expand stack coverage (`edge-cluster`, `datacenter-ha`) using the same smoke
	harness and manifest validation flow.
- Wire Ansible roles to consume the generated bundle manifests and secrets.
- Publish operator runbooks detailing telemetry dashboards and troubleshooting
	procedures for each deployment tier.
