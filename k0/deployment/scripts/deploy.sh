#!/usr/bin/env bash
set -euo pipefail

STACK=${1:-}
MODE=${2:-apply}
INVENTORY=${3:-}
ARTIFACTS_ROOT=${ARTIFACTS_ROOT:-artifacts}

if [[ -z "${STACK}" ]]; then
  echo "usage: $(basename "$0") <local-single-node|edge-cluster|datacenter-ha> [preview|apply] [inventory]" >&2
  exit 1
fi

if [[ "${MODE}" != "preview" && "${MODE}" != "apply" ]]; then
  echo "invalid mode '${MODE}'. choose 'preview' or 'apply'" >&2
  exit 1
fi

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
DEPLOYMENT_ROOT="${REPO_ROOT}/k0/deployment"
ARTIFACTS_DIR="${REPO_ROOT}/${ARTIFACTS_ROOT}"
TIMELINE_FILE="${ARTIFACTS_DIR}/deployment-timeline-${STACK}-$(date +%Y%m%d-%H%M%S).json"

# Initialize timeline
TIMELINE_STEPS=()

add_timeline_step() {
  local name="$1"
  local status="$2"
  local metadata="${3:-{}}"

  TIMELINE_STEPS+=("{\"name\":\"${name}\",\"status\":\"${status}\",\"timestamp\":\"$(date -Iseconds)\",\"metadata\":${metadata}}")
}

save_timeline() {
  local status="$1"
  local error="${2:-}"

  mkdir -p "$(dirname "${TIMELINE_FILE}")"

  local steps_json="$(printf '%s\n' "${TIMELINE_STEPS[@]}" | jq -s '.')"

  jq -n \
    --arg stack "${STACK}" \
    --arg mode "${MODE}" \
    --arg started "$(date -Iseconds)" \
    --arg completed "$(date -Iseconds)" \
    --arg status "${status}" \
    --arg error "${error}" \
    --argjson steps "${steps_json}" \
    '{stack: $stack, mode: $mode, started_at: $started, completed_at: $completed, status: $status, error: $error, steps: $steps}' \
    > "${TIMELINE_FILE}"

  echo "[k0] Timeline saved to: ${TIMELINE_FILE}"
}

cleanup() {
  local exit_code=$?
  if [[ ${exit_code} -ne 0 ]]; then
    save_timeline "failed" "Deployment failed with exit code ${exit_code}"
  fi
}

trap cleanup EXIT

echo "[k0] Starting deployment for stack '${STACK}'"
echo "[k0] Mode: ${MODE^^}"

# Step 1: Pulumi operation
add_timeline_step "pulumi_operation" "started"

PULUMI_CMD="${MODE}"
[[ "${MODE}" == "apply" ]] && PULUMI_CMD="up --yes"

echo "[k0] Running Pulumi ${PULUMI_CMD} for stack '${STACK}'"

cd "${DEPLOYMENT_ROOT}/pulumi"

export PULUMI_CONFIG_PASSPHRASE=""

pulumi stack select "${STACK}" || {
  echo "[k0] Failed to select Pulumi stack" >&2
  exit 1
}

if pulumi ${PULUMI_CMD} --stack "${STACK}"; then
  add_timeline_step "pulumi_operation" "completed" "{\"command\":\"pulumi ${PULUMI_CMD}\",\"exit_code\":0}"
  echo "[k0] Pulumi operation completed successfully"
else
  echo "[k0] Pulumi operation failed" >&2
  exit 1
fi

cd "${REPO_ROOT}"

# Step 2: Ansible playbook execution (only for apply mode)
if [[ "${MODE}" == "apply" ]]; then
  add_timeline_step "ansible_playbook" "started"

  # Auto-detect inventory based on stack
  if [[ -z "${INVENTORY}" ]]; then
    case "${STACK}" in
      local-single-node) INVENTORY="sample-dev" ;;
      edge-cluster|datacenter-ha) INVENTORY="sample-prod" ;;
      *) echo "[k0] Unknown stack '${STACK}'" >&2; exit 1 ;;
    esac
  fi

  INVENTORY_PATH="${DEPLOYMENT_ROOT}/ansible/inventories/${INVENTORY}/hosts.yml"
  PLAYBOOK_PATH="${DEPLOYMENT_ROOT}/ansible/playbooks/site.yml"

  if [[ ! -f "${INVENTORY_PATH}" ]]; then
    echo "[k0] Inventory not found: ${INVENTORY_PATH}" >&2
    exit 1
  fi

  echo "[k0] Running Ansible playbook with inventory '${INVENTORY}'"

  export FAMILYOS_REPO_ROOT="${REPO_ROOT}"
  export FAMILYOS_TELEMETRY_SNAPSHOT="${ARTIFACTS_DIR}/telemetry"

  if ansible-playbook -i "${INVENTORY_PATH}" "${PLAYBOOK_PATH}"; then
    add_timeline_step "ansible_playbook" "completed" "{\"inventory\":\"${INVENTORY}\",\"playbook\":\"site.yml\",\"exit_code\":0}"
    echo "[k0] Ansible playbook completed successfully"
  else
    echo "[k0] Ansible playbook failed" >&2
    exit 1
  fi

  # Step 3: Capture telemetry snapshot
  add_timeline_step "telemetry_snapshot" "started"

  TELEMETRY_DIR="${ARTIFACTS_DIR}/telemetry/${STACK}"
  mkdir -p "${TELEMETRY_DIR}"

  echo "[k0] Capturing telemetry snapshot"

  if python -m k0.automation.verify_security_telemetry -d "${TELEMETRY_DIR}" 2>/dev/null; then
    add_timeline_step "telemetry_snapshot" "completed" "{\"directory\":\"${TELEMETRY_DIR}\"}"
    echo "[k0] Telemetry snapshot captured"
  else
    add_timeline_step "telemetry_snapshot" "warning" "{\"message\":\"Telemetry verification had warnings\"}"
    echo "[k0] Telemetry snapshot captured with warnings"
  fi
fi

# Success
save_timeline "success"
echo "[k0] Deployment completed successfully!"
exit 0
