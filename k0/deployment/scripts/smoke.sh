#!/usr/bin/env bash
set -euo pipefail

STACK=${1:-}

if [[ -z "${STACK}" ]]; then
  echo "usage: $(basename "$0") <local-single-node|edge-cluster|datacenter-ha>" >&2
  exit 1
fi

echo "[k0] Running Pulumi preview smoke for stack '${STACK}'"

ARTIFACT_ROOT="artifacts/pulumi/${STACK}"

python -m k0.deployment.pulumi.smoke --stack "${STACK}" --artifacts-dir "${ARTIFACT_ROOT}"

python -m k0.deployment.pulumi.validation "${ARTIFACT_ROOT}/bundles/${STACK}"

python -m k0.automation.verify_security_telemetry -d artifacts/telemetry >/dev/null
