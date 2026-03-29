from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..loaders.contract_loader import ContractLoader


class VersionValidator:
    """
    Validates version compatibility across contracts.

    - Ensures semantic versioning compliance
    - Validates version ranges and compatibility
    - Checks for version conflicts
    - Validates version metadata
    """

    def __init__(self, contract_loader: Optional[ContractLoader] = None):
        self.contract_loader = contract_loader or ContractLoader()

    def validate_versions(self, module_id: str) -> List[str]:
        """Validate versions for a module."""
        errors: List[str] = []

        try:
            # Load module contract
            module_contract = self.contract_loader.load_contract(
                self.contract_loader.contracts_dir / "modules" / module_id / "module.contract.yaml"
            )

            # Validate module version
            if "version" in module_contract:
                errors.extend(self._validate_version_format(module_contract["version"]))

            # Load and validate wiring versions
            wiring_file = (
                self.contract_loader.contracts_dir / "modules" / module_id / "wiring.contract.yaml"
            )
            if wiring_file.exists():
                wiring_contract = self.contract_loader.load_contract(wiring_file)
                errors.extend(self._validate_wiring_versions(wiring_contract))

            # Load and validate policy versions
            policy_file = (
                self.contract_loader.contracts_dir
                / "modules"
                / module_id
                / "policies.contract.yaml"
            )
            if policy_file.exists():
                policy_contract = self.contract_loader.load_contract(policy_file)
                errors.extend(self._validate_policy_versions(policy_contract))

        except Exception as e:
            errors.append(f"Version validation failed for {module_id}: {e}")

        return errors

    def validate_all_versions(self) -> Dict[str, List[str]]:
        """Validate versions across all modules."""
        results: Dict[str, List[str]] = {}

        modules_dir = self.contract_loader.contracts_dir / "modules"
        if modules_dir.exists():
            for module_dir in modules_dir.iterdir():
                if module_dir.is_dir():
                    module_id = module_dir.name
                    errors = self.validate_versions(module_id)
                    if errors:
                        results[module_id] = errors

        # Cross-module version validations
        global_errors = self._validate_global_version_consistency()
        if global_errors:
            results["GLOBAL"] = global_errors

        return results

    def _validate_version_format(self, version: str) -> List[str]:
        """Validate semantic version format."""
        errors: List[str] = []

        if not isinstance(version, str):
            errors.append(f"Version must be a string, got {type(version)}")
            return errors

        if not self._is_valid_semver(version):
            errors.append(f"Invalid semantic version format: '{version}'")

        return errors

    def _validate_wiring_versions(self, wiring_contract: Dict[str, Any]) -> List[str]:
        """Validate versions in wiring contract."""
        errors: List[str] = []

        # Validate capability versions
        for cap in wiring_contract.get("capabilities", {}).get("provides", []):
            if "version" in cap:
                errors.extend(self._validate_version_format(cap["version"]))

        for cap in wiring_contract.get("capabilities", {}).get("consumes", []):
            if "version" in cap:
                errors.extend(self._validate_version_format(cap["version"]))

        # Validate event schema versions (if any)
        for event in wiring_contract.get("events", {}).get("emits", []):
            if "version" in event:
                errors.extend(self._validate_version_format(event["version"]))

        for event in wiring_contract.get("events", {}).get("subscribes", []):
            if "version" in event:
                errors.extend(self._validate_version_format(event["version"]))

        return errors

    def _validate_policy_versions(self, policy_contract: Dict[str, Any]) -> List[str]:
        """Validate versions in policy contract."""
        errors: List[str] = []

        # Policy contracts might have version ranges or specific versions
        if "version" in policy_contract:
            errors.extend(self._validate_version_format(policy_contract["version"]))

        # Validate budget versions or ranges
        for budget in policy_contract.get("budgets", []):
            if "version" in budget:
                errors.extend(self._validate_version_format(budget["version"]))

        return errors

    def _validate_global_version_consistency(self) -> List[str]:
        """Validate version consistency across modules."""
        errors: List[str] = []

        # Collect all module versions
        module_versions: Dict[str, str] = {}

        modules_dir = self.contract_loader.contracts_dir / "modules"
        if modules_dir.exists():
            for module_dir in modules_dir.iterdir():
                if module_dir.is_dir():
                    module_id = module_dir.name
                    try:
                        contract = self.contract_loader.load_contract(
                            module_dir / "module.contract.yaml"
                        )
                        if "version" in contract:
                            module_versions[module_id] = contract["version"]
                    except Exception:
                        pass

        # Check for duplicate versions (unusual but possible)
        version_counts = {}
        for version in module_versions.values():
            version_counts[version] = version_counts.get(version, 0) + 1

        duplicates = [v for v, c in version_counts.items() if c > 1]
        if duplicates:
            for dup_version in duplicates:
                modules_with_dup = [m for m, v in module_versions.items() if v == dup_version]
                errors.append(
                    f"Version '{dup_version}' used by multiple modules: {modules_with_dup}"
                )

        return errors

    def _is_valid_semver(self, version: str) -> bool:
        """Basic semver validation."""
        import re

        semver_pattern = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
        return bool(re.match(semver_pattern, version))

    def compare_versions(self, v1: str, v2: str) -> int:
        """Compare two semantic versions. Returns -1 if v1 < v2, 0 if equal, 1 if v1 > v2."""

        def parse_version(v: str) -> Tuple[int, int, int, str, str]:
            match = re.match(
                r"^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.-]+))?(?:\+([a-zA-Z0-9.-]+))?$", v
            )
            if not match:
                raise ValueError(f"Invalid version: {v}")
            major, minor, patch, pre, build = match.groups()
            return int(major), int(minor), int(patch), pre or "", build or ""

        try:
            maj1, min1, pat1, pre1, bld1 = parse_version(v1)
            maj2, min2, pat2, pre2, bld2 = parse_version(v2)

            # Compare major.minor.patch
            if (maj1, min1, pat1) != (maj2, min2, pat2):
                return (
                    (maj1 > maj2) - (maj1 < maj2)
                    or (min1 > min2) - (min1 < min2)
                    or (pat1 > pat2) - (pat1 < pat2)
                )

            # If versions are equal, pre-release makes it lower
            if pre1 and not pre2:
                return -1
            if not pre1 and pre2:
                return 1
            if pre1 and pre2:
                return (pre1 > pre2) - (pre1 < pre2)

            return 0
        except ValueError:
            return 0  # If parsing fails, consider equal

    def get_version_report(self) -> Dict[str, Any]:
        """Generate a report on versions."""
        module_versions: Dict[str, str] = {}

        modules_dir = self.contract_loader.contracts_dir / "modules"
        if modules_dir.exists():
            for module_dir in modules_dir.iterdir():
                if module_dir.is_dir():
                    module_id = module_dir.name
                    try:
                        contract = self.contract_loader.load_contract(
                            module_dir / "module.contract.yaml"
                        )
                        if "version" in contract:
                            module_versions[module_id] = contract["version"]
                    except Exception:
                        pass

        report = {
            "total_modules": len(module_versions),
            "unique_versions": len(set(module_versions.values())),
            "version_distribution": {},
        }

        for version in module_versions.values():
            report["version_distribution"][version] = (
                report["version_distribution"].get(version, 0) + 1
            )

        return report
