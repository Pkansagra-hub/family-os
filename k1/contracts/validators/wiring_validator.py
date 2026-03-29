from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..loaders.wiring_loader import WiringLoader


class WiringValidator:
    """
    Validates wiring connectivity: capability matching, event routing, mailbox consistency.

    - Uses WiringLoader for indexed wiring data
    - Checks for connectivity issues across modules
    - Validates wiring contract integrity
    """

    def __init__(self, wiring_loader: Optional[WiringLoader] = None):
        self.wiring_loader = wiring_loader or WiringLoader()

    def validate_module_wiring(self, module_id: str) -> List[str]:
        """Validate wiring for a single module."""
        errors: List[str] = []

        # Use WiringLoader's validation
        errors.extend(self.wiring_loader.validate_wiring_connections(module_id))

        # Additional cross-module checks
        spec = self.wiring_loader.load_wiring_spec(module_id)
        try:
            # Check for self-referencing issues
            errors.extend(self._validate_no_self_reference(module_id, spec))

            # Check for circular dependencies (basic)
            errors.extend(self._validate_no_obvious_cycles(module_id))

            # New validation sections
            errors.extend(self.validate_code_requirements(module_id))
            errors.extend(self.validate_wiring_implementations(module_id))
            errors.extend(self.validate_file_structure(module_id))
            errors.extend(self.validate_runtime_assertions(module_id))

        except Exception as e:
            errors.append(f"Wiring validation failed for {module_id}: {e}")

        return errors

    def validate_all_wiring(self) -> Dict[str, List[str]]:
        """Validate wiring across all modules."""
        results: Dict[str, List[str]] = {}

        # Ensure indexing
        self.wiring_loader.index_all_modules()

        # Validate each module
        modules_dir = self.wiring_loader.contract_loader.contracts_dir / "modules"
        if modules_dir.exists():
            for module_dir in modules_dir.iterdir():
                if module_dir.is_dir():
                    module_id = module_dir.name
                    errors = self.validate_module_wiring(module_id)
                    if errors:
                        results[module_id] = errors

        # Cross-module validations
        global_errors = self._validate_global_connectivity()
        if global_errors:
            results["GLOBAL"] = global_errors

        return results

    def _validate_no_self_reference(self, module_id: str, spec: Dict[str, Any]) -> List[str]:
        """Check that module doesn't reference itself inappropriately."""
        errors: List[str] = []

        # Check capabilities
        for cap in spec["capabilities"].get("provides", []):
            if cap.get("provider") == module_id:
                errors.append(f"Capability {cap['name']} provider should not be self")

        # Note: consumers can reference self if needed for internal wiring

        return errors

    def _validate_no_obvious_cycles(self, module_id: str) -> List[str]:
        """Basic cycle detection in dependency graph."""
        errors: List[str] = []

        # Get dependencies
        deps = self.wiring_loader.get_module_dependencies(module_id)

        # Check if any dependency depends back (simple check)
        for dep in deps:
            try:
                dep_deps = self.wiring_loader.get_module_dependencies(dep)
                if module_id in dep_deps:
                    errors.append(
                        f"Circular dependency detected: {module_id} -> {dep} -> {module_id}"
                    )
            except Exception:
                pass  # Skip if dep not found

        return errors

    def _validate_global_connectivity(self) -> List[str]:
        """Validate global wiring connectivity."""
        errors: List[str] = []

        # Check for orphan capabilities (provided but never consumed)
        all_providers = set()
        all_consumers = set()

        for module_id in self.wiring_loader._wiring_specs:
            spec = self.wiring_loader._wiring_specs[module_id]
            for cap in spec["capabilities"].get("provides", []):
                all_providers.add(cap["name"])
            for cap in spec["capabilities"].get("consumes", []):
                all_consumers.add(cap["name"])

        orphan_provides = all_providers - all_consumers
        if orphan_provides:
            errors.append(f"Orphan provided capabilities: {sorted(orphan_provides)}")

        # Check for missing providers
        missing_consumes = all_consumers - all_providers
        if missing_consumes:
            errors.append(f"Consumed capabilities without providers: {sorted(missing_consumes)}")

        # Similar for events
        all_emitters = set()
        all_subscribers = set()

        for module_id in self.wiring_loader._wiring_specs:
            spec = self.wiring_loader._wiring_specs[module_id]
            for ev in spec["events"].get("emits", []):
                all_emitters.add(ev["topic"])
            for ev in spec["events"].get("subscribes", []):
                all_subscribers.add(ev["topic"])

        orphan_emits = all_emitters - all_subscribers
        if orphan_emits:
            errors.append(f"Orphan emitted events: {sorted(orphan_emits)}")

        missing_subscribes = all_subscribers - all_emitters
        if missing_subscribes:
            errors.append(f"Subscribed events without emitters: {sorted(missing_subscribes)}")

        return errors

    def validate_code_requirements(self, module_id: str) -> List[str]:
        """Validate code.required_files section against actual filesystem."""
        errors: List[str] = []
        spec = self.wiring_loader.load_wiring_spec(module_id)

        code_reqs = spec.get("code", {}).get("required_files", [])
        if not code_reqs:
            return errors

        for req in code_reqs:
            file_path = req["path"]
            full_path = self.wiring_loader.contract_loader.contracts_dir.parent.parent / file_path

            # Check file exists
            if not full_path.exists():
                errors.append(f"Required file missing: {file_path}")
                continue

            # Check exports if specified
            if "must_export" in req:
                try:
                    spec = importlib.util.spec_from_file_location("temp_module", full_path)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        for export in req["must_export"]:
                            if not hasattr(module, export):
                                errors.append(
                                    f"Required export '{export}' missing from {file_path}"
                                )
                except Exception as e:
                    errors.append(f"Failed to check exports in {file_path}: {e}")

            # Check constants if specified
            if "must_contain_constants" in req:
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    tree = ast.parse(content)
                    defined_names = set()
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Assign):
                            for target in node.targets:
                                if isinstance(target, ast.Name):
                                    defined_names.add(target.id)
                        elif isinstance(node, ast.AnnAssign):
                            if isinstance(node.target, ast.Name):
                                defined_names.add(node.target.id)

                    for const in req["must_contain_constants"]:
                        if const not in defined_names:
                            errors.append(f"Required constant '{const}' not defined in {file_path}")
                except Exception as e:
                    errors.append(f"Failed to check constants in {file_path}: {e}")

        return errors

    def validate_wiring_implementations(self, module_id: str) -> List[str]:
        """Validate wiring.implementations section."""
        errors: List[str] = []
        spec = self.wiring_loader.load_wiring_spec(module_id)

        implementations = spec.get("wiring", {}).get("implementations", {})
        if not implementations:
            return errors

        # Check that all provided capabilities have implementations
        provided_caps = {cap["name"] for cap in spec["capabilities"].get("provides", [])}
        implemented_caps = set(implementations.keys())

        missing_impls = provided_caps - implemented_caps
        if missing_impls:
            errors.append(f"Capabilities without implementations: {sorted(missing_impls)}")

        # Check that implementation files exist
        for cap_name, impl_data in implementations.items():
            if "files" in impl_data:
                for file_path in impl_data["files"]:
                    full_path = (
                        self.wiring_loader.contract_loader.contracts_dir.parent.parent / file_path
                    )
                    if not full_path.exists():
                        errors.append(f"Implementation file missing for {cap_name}: {file_path}")

        return errors

    def validate_file_structure(self, module_id: str) -> List[str]:
        """Validate files.required and forbidden_patterns sections."""
        errors: List[str] = []
        spec = self.wiring_loader.load_wiring_spec(module_id)

        files_spec = spec.get("files", {})

        # Check required files
        required_files = files_spec.get("required", [])
        for req_file in required_files:
            file_path = req_file["path"]
            full_path = self.wiring_loader.contract_loader.contracts_dir.parent.parent / file_path
            if not full_path.exists():
                errors.append(f"Required file missing: {file_path}")

        # Check forbidden patterns
        forbidden_patterns = files_spec.get("forbidden_patterns", [])
        roots = spec.get("code", {}).get("roots", [])
        for root in roots:
            root_path = self.wiring_loader.contract_loader.contracts_dir.parent.parent / root
            if root_path.exists():
                for pattern in forbidden_patterns:
                    # Simple glob check (could be enhanced)
                    if pattern in str(root_path):
                        errors.append(f"Forbidden pattern found: {pattern} in {root}")

        return errors

    def validate_runtime_assertions(self, module_id: str) -> List[str]:
        """Validate runtime_assertions section (basic syntax check)."""
        errors: List[str] = []
        spec = self.wiring_loader.load_wiring_spec(module_id)

        assertions = spec.get("runtime_assertions", {})
        if not assertions:
            return errors

        # Check on_load assertions (basic syntax)
        for assertion in assertions.get("on_load", []):
            condition = assertion.get("condition", "")
            test_code = assertion.get("test", "")
            if not condition or not test_code:
                errors.append("Invalid assertion format: missing condition or test")

        # Check invariants (basic syntax)
        for assertion in assertions.get("invariants", []):
            condition = assertion.get("condition", "")
            test_code = assertion.get("test", "")
            if not condition or not test_code:
                errors.append("Invalid invariant format: missing condition or test")

        return errors

    def get_connectivity_report(self) -> Dict[str, Any]:
        """Generate a report on wiring connectivity."""
        self.wiring_loader.index_all_modules()

        report = {
            "capability_connectivity": {
                "total_provided": len(set().union(*[self.wiring_loader._cap_providers.values()])),
                "total_consumed": len(set().union(*[self.wiring_loader._cap_consumers.values()])),
                "orphans": list(
                    set(self.wiring_loader._cap_providers.keys())
                    - set(self.wiring_loader._cap_consumers.keys())
                ),
                "missing": list(
                    set(self.wiring_loader._cap_consumers.keys())
                    - set(self.wiring_loader._cap_providers.keys())
                ),
            },
            "event_connectivity": {
                "total_emitted": len(set().union(*[self.wiring_loader._event_emitters.values()])),
                "total_subscribed": len(
                    set().union(*[self.wiring_loader._event_subscribers.values()])
                ),
                "orphans": list(
                    set(self.wiring_loader._event_emitters.keys())
                    - set(self.wiring_loader._event_subscribers.keys())
                ),
                "missing": list(
                    set(self.wiring_loader._event_subscribers.keys())
                    - set(self.wiring_loader._event_emitters.keys())
                ),
            },
            "modules_indexed": len(self.wiring_loader._wiring_specs),
        }

        return report
