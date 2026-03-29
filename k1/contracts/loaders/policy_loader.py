from __future__ import annotations

from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Optional, Set

from .contract_loader import ContractLoader


class PolicyLoader:
    """
    Loads and enforces policies contracts for governance.

    - Loads policies contracts via ContractLoader
    - Indexes granted capabilities, budgets, egress rules
    - Validates policy compliance and resource limits
    - Enforces audit requirements
    """

    def __init__(self, contract_loader: Optional[ContractLoader] = None):
        self.contract_loader = contract_loader or ContractLoader()
        self._indexed: bool = False
        self._policy_specs: Dict[str, Dict[str, Any]] = {}
        self._index_errors: Dict[str, str] = {}  # Store indexing errors per module

        # Indexes
        self._granted_caps: DefaultDict[str, Set[str]] = defaultdict(set)
        self._budgets: Dict[str, Dict[str, Any]] = {}
        self._egress_rules: Dict[str, Dict[str, Any]] = {}
        self._audit_settings: Dict[str, Dict[str, Any]] = {}

    def load_policy_spec(self, module_id: str) -> Dict[str, Any]:
        """Load the policy specification for a module."""
        policy_contract = self.contract_loader.load_policies_contract(module_id)
        return {
            "capabilities": policy_contract.get("capabilities", {}),
            "budgets": policy_contract.get("budgets", {}),
            "egress": policy_contract.get("egress", {}),
            "audit": policy_contract.get("audit", {}),
            "metadata": policy_contract.get("metadata", {}),
        }

    def index_all_modules(self) -> None:
        """Load all module policies and build indexes."""
        self._granted_caps.clear()
        self._budgets.clear()
        self._egress_rules.clear()
        self._audit_settings.clear()
        self._policy_specs.clear()
        self._index_errors.clear()

        modules_dir = self.contract_loader.contracts_dir / "modules"
        if not modules_dir.exists():
            self._indexed = True
            return

        for module_dir in modules_dir.iterdir():
            if not module_dir.is_dir():
                continue
            module_id = module_dir.name
            try:
                spec = self.load_policy_spec(module_id)
                self._policy_specs[module_id] = spec

                # Index granted capabilities
                granted = spec["capabilities"].get("granted", []) or []
                self._granted_caps[module_id] = set(granted)

                # Index budgets
                self._budgets[module_id] = spec["budgets"]

                # Index egress
                self._egress_rules[module_id] = spec["egress"]

                # Index audit
                self._audit_settings[module_id] = spec["audit"]

            except Exception as e:
                # Store error for later surfacing
                self._index_errors[module_id] = str(e)
                continue

        self._indexed = True

    def _ensure_indexed(self) -> None:
        if not self._indexed:
            self.index_all_modules()

    def get_granted_capabilities(self, module_id: str) -> Set[str]:
        """Get the set of capabilities granted to a module."""
        self._ensure_indexed()
        return self._granted_caps.get(module_id, set())

    def is_capability_granted(self, module_id: str, capability: str) -> bool:
        """Check if a capability is granted to a module."""
        return capability in self.get_granted_capabilities(module_id)

    def validate_budget_limits(self, module_id: str, usage: Dict[str, Any]) -> List[str]:
        """
        Validate that current usage is within budget limits.

        Args:
            module_id: Module to check
            usage: Dict with keys like 'latency_ms_p95', 'cost_usd_per_session', etc.

        Returns:
            List of violation messages
        """
        self._ensure_indexed()
        errors: List[str] = []
        budgets = self._budgets.get(module_id, {})

        # Check latency
        if "latency_ms_p95" in usage and "latency_ms_p95" in budgets:
            if usage["latency_ms_p95"] > budgets["latency_ms_p95"]:
                errors.append(
                    f"Latency {usage['latency_ms_p95']}ms exceeds budget {budgets['latency_ms_p95']}ms"
                )

        # Check cost
        if "cost_usd_per_session" in usage and "cost_usd_per_session_max" in budgets:
            if usage["cost_usd_per_session"] > budgets["cost_usd_per_session_max"]:
                errors.append(
                    f"Cost ${usage['cost_usd_per_session']} exceeds budget ${budgets['cost_usd_per_session_max']}"
                )

        # Check KV cache
        if "kv_cache_mb" in usage and "kv_cache_mb_max" in budgets:
            if usage["kv_cache_mb"] > budgets["kv_cache_mb_max"]:
                errors.append(
                    f"KV cache {usage['kv_cache_mb']}MB exceeds budget {budgets['kv_cache_mb_max']}MB"
                )

        return errors

    def validate_egress_rules(self, module_id: str, request: Dict[str, Any]) -> List[str]:
        """
        Validate that a network/filesystem request complies with egress rules.

        Args:
            module_id: Module making the request
            request: Dict with 'type' ('network' or 'filesystem'), 'target' (domain/path), etc.

        Returns:
            List of violation messages
        """
        self._ensure_indexed()
        errors: List[str] = []
        egress = self._egress_rules.get(module_id, {})

        req_type = request.get("type")
        target = request.get("target")

        if req_type == "network":
            allowed_domains = egress.get("network", {}).get("allowed_domains", [])
            allowed_ips = egress.get("network", {}).get("allowed_ips", [])
            if target and target not in allowed_domains and target not in allowed_ips:
                # Check suffix matching for domains
                domain_allowed = any(
                    target == d or target.endswith("." + d) for d in allowed_domains
                )
                if not domain_allowed and target not in allowed_ips:
                    errors.append(f"Network access to {target} not allowed by policy")

        elif req_type == "filesystem":
            allowed_paths = egress.get("filesystem", {}).get("allowed_paths", [])
            if target and not any(target.startswith(path) for path in allowed_paths):
                errors.append(f"Filesystem access to {target} not allowed by policy")

        return errors

    def requires_audit_receipts(self, module_id: str) -> bool:
        """Check if module must emit audit receipts."""
        self._ensure_indexed()
        return self._audit_settings.get(module_id, {}).get("emit_receipts", False)

    def get_audit_topic(self, module_id: str) -> Optional[str]:
        """Get the audit receipt topic for a module."""
        self._ensure_indexed()
        return self._audit_settings.get(module_id, {}).get("receipt_topic")

    def get_index_errors(self) -> Dict[str, str]:
        """Get any errors encountered during indexing."""
        self._ensure_indexed()
        return dict(self._index_errors)

    def validate_policy_compliance(self, module_id: str, operation: Dict[str, Any]) -> List[str]:
        """
        Comprehensive policy validation for an operation.

        Args:
            operation: Dict describing the operation (capabilities used, resources, egress, etc.)

        Returns:
            List of policy violations
        """
        errors: List[str] = []

        # Check granted capabilities
        required_caps = operation.get("capabilities", [])
        for cap in required_caps:
            if not self.is_capability_granted(module_id, cap):
                errors.append(f"Capability '{cap}' not granted to module '{module_id}'")

        # Check budgets
        usage = operation.get("usage", {})
        errors.extend(self.validate_budget_limits(module_id, usage))

        # Check egress
        egress_req = operation.get("egress")
        if egress_req:
            errors.extend(self.validate_egress_rules(module_id, egress_req))

        return errors
