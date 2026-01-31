from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..loaders.wiring_loader import WiringLoader


class CapabilityValidator:
    """
    Validates capability definitions and matching.

    - Ensures capability schemas are consistent
    - Validates provider/consumer compatibility
    - Checks for capability naming conflicts
    - Validates capability metadata
    """

    def __init__(self, wiring_loader: Optional[WiringLoader] = None):
        self.wiring_loader = wiring_loader or WiringLoader()

    def validate_capabilities(self, module_id: str) -> List[str]:
        """Validate capabilities for a module."""
        errors: List[str] = []

        try:
            spec = self.wiring_loader.load_wiring_spec(module_id)

            # Validate provides
            for cap in spec["capabilities"].get("provides", []):
                errors.extend(self._validate_capability_definition(cap, "provide"))

            # Validate consumes
            for cap in spec["capabilities"].get("consumes", []):
                errors.extend(self._validate_capability_definition(cap, "consume"))

            # Check for naming conflicts within module
            errors.extend(self._validate_no_naming_conflicts(spec))

        except Exception as e:
            errors.append(f"Capability validation failed for {module_id}: {e}")

        return errors

    def validate_all_capabilities(self) -> Dict[str, List[str]]:
        """Validate capabilities across all modules."""
        results: Dict[str, List[str]] = {}

        self.wiring_loader.index_all_modules()

        modules_dir = self.wiring_loader.contract_loader.contracts_dir / "modules"
        if modules_dir.exists():
            for module_dir in modules_dir.iterdir():
                if module_dir.is_dir():
                    module_id = module_dir.name
                    errors = self.validate_capabilities(module_id)
                    if errors:
                        results[module_id] = errors

        # Cross-module validations
        global_errors = self._validate_global_capability_consistency()
        if global_errors:
            results["GLOBAL"] = global_errors

        return results

    def _validate_capability_definition(self, cap: Dict[str, Any], cap_type: str) -> List[str]:
        """Validate a single capability definition."""
        errors: List[str] = []

        # Required fields
        required = ["name", "interface", "version"]
        for field in required:
            if field not in cap:
                errors.append(f"Missing required field '{field}' in {cap_type} capability")

        # Name format
        if "name" in cap:
            name = cap["name"]
            if not isinstance(name, str) or not name.replace("_", "").replace("-", "").isalnum():
                errors.append(f"Invalid capability name '{name}': must be alphanumeric with _ or -")

        # Version format (semver)
        if "version" in cap:
            version = cap["version"]
            if not self._is_valid_semver(version):
                errors.append(f"Invalid version '{version}': must be semver")

        # Interface validation
        if "interface" in cap:
            interface = cap["interface"]
            if not isinstance(interface, dict):
                errors.append("Interface must be an object")
            else:
                # Check for required interface fields
                if "methods" not in interface:
                    errors.append("Interface must have 'methods' field")
                else:
                    for method in interface["methods"]:
                        if not isinstance(method, dict) or "name" not in method:
                            errors.append("Each method must have a 'name' field")

        return errors

    def _validate_no_naming_conflicts(self, spec: Dict[str, Any]) -> List[str]:
        """Check for naming conflicts within a module."""
        errors: List[str] = []

        provides = {
            cap["name"] for cap in spec["capabilities"].get("provides", []) if "name" in cap
        }
        consumes = {
            cap["name"] for cap in spec["capabilities"].get("consumes", []) if "name" in cap
        }

        conflicts = provides & consumes
        if conflicts:
            errors.append(f"Naming conflicts: capabilities both provided and consumed: {conflicts}")

        return errors

    def _validate_global_capability_consistency(self) -> List[str]:
        """Validate consistency across all capabilities."""
        errors: List[str] = []

        self.wiring_loader.index_all_modules()

        # Check version compatibility for each capability
        for cap_name in self.wiring_loader._cap_providers:
            provider_versions = set()
            consumer_versions = set()

            # Collect provider versions
            for provider in self.wiring_loader._cap_providers[cap_name]:
                try:
                    spec = self.wiring_loader.load_wiring_spec(provider)
                    for cap in spec["capabilities"].get("provides", []):
                        if cap.get("name") == cap_name:
                            provider_versions.add(cap.get("version"))
                except Exception:
                    pass

            # Collect consumer versions
            for consumer in self.wiring_loader._cap_consumers[cap_name]:
                try:
                    spec = self.wiring_loader.load_wiring_spec(consumer)
                    for cap in spec["capabilities"].get("consumes", []):
                        if cap.get("name") == cap_name:
                            consumer_versions.add(cap.get("version"))
                except Exception:
                    pass

            # Check for version mismatches
            if len(provider_versions) > 1:
                errors.append(
                    f"Multiple provider versions for '{cap_name}': {sorted(provider_versions)}"
                )

            if provider_versions and consumer_versions:
                # Simple check: consumers should match provider versions
                if not consumer_versions.issubset(provider_versions):
                    errors.append(
                        f"Version mismatch for '{cap_name}': providers {sorted(provider_versions)}, consumers {sorted(consumer_versions)}"
                    )

        return errors

    def _is_valid_semver(self, version: str) -> bool:
        """Basic semver validation."""
        import re

        semver_pattern = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
        return bool(re.match(semver_pattern, version))

    def get_capability_report(self) -> Dict[str, Any]:
        """Generate a report on capabilities."""
        self.wiring_loader.index_all_modules()

        report = {
            "total_capabilities": len(self.wiring_loader._cap_providers),
            "total_providers": sum(
                len(provs) for provs in self.wiring_loader._cap_providers.values()
            ),
            "total_consumers": sum(
                len(cons) for cons in self.wiring_loader._cap_consumers.values()
            ),
            "capabilities_with_multiple_providers": [
                cap for cap, provs in self.wiring_loader._cap_providers.items() if len(provs) > 1
            ],
            "capabilities_without_consumers": [
                cap
                for cap in self.wiring_loader._cap_providers
                if cap not in self.wiring_loader._cap_consumers
            ],
            "capabilities_without_providers": [
                cap
                for cap in self.wiring_loader._cap_consumers
                if cap not in self.wiring_loader._cap_providers
            ],
        }

        return report
