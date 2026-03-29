from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..loaders.wiring_loader import WiringLoader


class StateAccessValidator:
    """
    Validates state access configurations.

    - Ensures state schemas are consistent
    - Validates state access permissions
    - Checks for state naming conflicts
    - Validates state metadata
    """

    def __init__(self, wiring_loader: Optional[WiringLoader] = None):
        self.wiring_loader = wiring_loader or WiringLoader()

    def validate_state_access(self, module_id: str) -> List[str]:
        """Validate state access for a module."""
        errors: List[str] = []

        try:
            spec = self.wiring_loader.load_wiring_spec(module_id)

            # Validate state access
            for state in spec["state_access"]:
                errors.extend(self._validate_state_definition(state))

            # Check for naming conflicts within module
            errors.extend(self._validate_no_state_conflicts(spec))

        except Exception as e:
            errors.append(f"State access validation failed for {module_id}: {e}")

        return errors

    def validate_all_state_access(self) -> Dict[str, List[str]]:
        """Validate state access across all modules."""
        results: Dict[str, List[str]] = {}

        self.wiring_loader.index_all_modules()

        modules_dir = self.wiring_loader.contract_loader.contracts_dir / "modules"
        if modules_dir.exists():
            for module_dir in modules_dir.iterdir():
                if module_dir.is_dir():
                    module_id = module_dir.name
                    errors = self.validate_state_access(module_id)
                    if errors:
                        results[module_id] = errors

        # Cross-module validations
        global_errors = self._validate_global_state_consistency()
        if global_errors:
            results["GLOBAL"] = global_errors

        return results

    def _validate_state_definition(self, state: Dict[str, Any]) -> List[str]:
        """Validate a single state access definition."""
        errors: List[str] = []

        # Required fields
        required = ["name", "type", "permissions"]
        for field in required:
            if field not in state:
                errors.append(f"Missing required field '{field}' in state access")

        # Name format
        if "name" in state:
            name = state["name"]
            if not isinstance(name, str) or not name.replace("_", "").replace("-", "").isalnum():
                errors.append(f"Invalid state name '{name}': must be alphanumeric with _ or -")

        # Type validation
        if "type" in state:
            valid_types = ["persistent", "transient", "shared", "local"]
            if state["type"] not in valid_types:
                errors.append(f"Invalid state type '{state['type']}': must be one of {valid_types}")

        # Permissions validation
        if "permissions" in state:
            perms = state["permissions"]
            if not isinstance(perms, dict):
                errors.append("Permissions must be an object")
            else:
                required_perms = ["read", "write"]
                for perm in required_perms:
                    if perm not in perms:
                        errors.append(f"Missing permission '{perm}' in state permissions")
                    elif not isinstance(perms[perm], list):
                        errors.append(f"Permission '{perm}' must be a list of module IDs")

        # Schema validation
        if "schema" in state:
            schema = state["schema"]
            if not isinstance(schema, dict):
                errors.append("Schema must be an object")
            else:
                if "$schema" not in schema:
                    errors.append("Schema must specify '$schema'")
                if "type" not in schema:
                    errors.append("Schema must have 'type' field")

        return errors

    def _validate_no_state_conflicts(self, spec: Dict[str, Any]) -> List[str]:
        """Check for state naming conflicts within a module."""
        errors: List[str] = []

        states = [st["name"] for st in spec.get("state_access", []) if "name" in st]
        duplicates = set([name for name in states if states.count(name) > 1])
        if duplicates:
            errors.append(f"Duplicate state names: {duplicates}")

        return errors

    def _validate_global_state_consistency(self) -> List[str]:
        """Validate consistency across all state access."""
        errors: List[str] = []

        self.wiring_loader.index_all_modules()

        # Collect all state names and their modules
        state_modules: Dict[str, List[str]] = {}

        for module_id in self.wiring_loader._wiring_specs:
            spec = self.wiring_loader._wiring_specs[module_id]
            for state in spec.get("state_access", []):
                name = state.get("name")
                if name:
                    if name not in state_modules:
                        state_modules[name] = []
                    state_modules[name].append(module_id)

        # Check for global naming conflicts (shared states should be unique)
        for name, modules in state_modules.items():
            if len(modules) > 1:
                # Check if any are shared
                shared_count = 0
                for module_id in modules:
                    spec = self.wiring_loader._wiring_specs[module_id]
                    for state in spec.get("state_access", []):
                        if state.get("name") == name and state.get("type") == "shared":
                            shared_count += 1
                if shared_count > 1:
                    errors.append(f"Shared state '{name}' accessed by multiple modules: {modules}")

        # Check permissions consistency
        for module_id in self.wiring_loader._wiring_specs:
            spec = self.wiring_loader._wiring_specs[module_id]
            for state in spec.get("state_access", []):
                errors.extend(self._validate_state_permissions(state, module_id))

        return errors

    def _validate_state_permissions(self, state: Dict[str, Any], module_id: str) -> List[str]:
        """Validate permissions for a state."""
        errors: List[str] = []

        perms = state.get("permissions", {})

        # Check that module has access to its own state
        for perm_type in ["read", "write"]:
            if perm_type in perms:
                allowed_modules = perms[perm_type]
                if module_id not in allowed_modules:
                    errors.append(
                        f"Module '{module_id}' does not have {perm_type} permission for its own state '{state['name']}'"
                    )

        # Check that referenced modules exist
        for perm_type in ["read", "write"]:
            if perm_type in perms:
                for mod in perms[perm_type]:
                    if mod not in self.wiring_loader._wiring_specs:
                        errors.append(
                            f"State '{state['name']}' references non-existent module '{mod}' in {perm_type} permissions"
                        )

        # For shared states, ensure proper access
        if state.get("type") == "shared":
            read_modules = set(perms.get("read", []))
            write_modules = set(perms.get("write", []))
            if not read_modules or not write_modules:
                errors.append(
                    f"Shared state '{state['name']}' must have both read and write permissions defined"
                )

        return errors

    def get_state_report(self) -> Dict[str, Any]:
        """Generate a report on state access."""
        self.wiring_loader.index_all_modules()

        total_states = 0
        state_types = {"persistent": 0, "transient": 0, "shared": 0, "local": 0}

        for spec in self.wiring_loader._wiring_specs.values():
            for state in spec.get("state_access", []):
                total_states += 1
                st_type = state.get("type")
                if st_type in state_types:
                    state_types[st_type] += 1

        report = {
            "total_states": total_states,
            "state_types": state_types,
            "modules_with_state_access": len(
                [
                    spec
                    for spec in self.wiring_loader._wiring_specs.values()
                    if spec.get("state_access")
                ]
            ),
        }

        return report
