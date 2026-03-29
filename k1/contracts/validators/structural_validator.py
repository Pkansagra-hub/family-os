from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..loaders.contract_loader import ContractLoader
from ..loaders.schema_validator import SchemaValidator


class StructuralValidator:
    """
    Validates contract structure: schema compliance, required fields, basic integrity.

    - Uses SchemaValidator for JSON Schema validation
    - Checks contract metadata consistency
    - Validates cross-references within contracts
    """

    def __init__(
        self,
        contract_loader: Optional[ContractLoader] = None,
        schema_validator: Optional[SchemaValidator] = None,
    ):
        self.contract_loader = contract_loader or ContractLoader()
        self.schema_validator = schema_validator or SchemaValidator()

    def validate_module_contract(self, module_id: str) -> List[str]:
        """Validate a module contract's structure."""
        errors: List[str] = []
        contract = self.contract_loader.load_module_contract(module_id)
        schema_id = "k1://schemas/module/module.contract.schema.yaml"
        try:
            self.schema_validator.validate_contract(contract, schema_id)

            # Additional structural checks
            errors.extend(self._validate_metadata(contract.get("metadata", {})))
            errors.extend(self._validate_exports(contract.get("exports", [])))
            errors.extend(self._validate_dependencies(contract.get("dependencies", [])))

        except Exception as e:
            errors.append(f"Module contract validation failed for {module_id}: {e}")

        return errors

    def validate_wiring_contract(self, module_id: str) -> List[str]:
        """Validate a wiring contract's structure."""
        errors: List[str] = []
        contract = self.contract_loader.load_wiring_contract(module_id)
        schema_id = "k1://schemas/wiring/wiring.contract.schema.yaml"
        try:
            self.schema_validator.validate_contract(contract, schema_id)

            # Additional checks
            errors.extend(self._validate_metadata(contract.get("metadata", {})))
            errors.extend(self._validate_imports(contract.get("imports", {})))

        except Exception as e:
            errors.append(f"Wiring contract validation failed for {module_id}: {e}")

        return errors

    def validate_policies_contract(self, module_id: str) -> List[str]:
        """Validate a policies contract's structure."""
        errors: List[str] = []
        contract = self.contract_loader.load_policies_contract(module_id)
        schema_id = "k1://schemas/module/policies.contract.schema.yaml"
        try:
            self.schema_validator.validate_contract(contract, schema_id)

            # Additional checks
            errors.extend(self._validate_metadata(contract.get("metadata", {})))

        except Exception as e:
            errors.append(f"Policies contract validation failed for {module_id}: {e}")

        return errors

    def validate_all_contracts(self) -> Dict[str, List[str]]:
        """Validate all contracts for all modules."""
        results: Dict[str, List[str]] = {}
        modules_dir = self.contract_loader.contracts_dir / "modules"

        if not modules_dir.exists():
            return results

        for module_dir in modules_dir.iterdir():
            if not module_dir.is_dir():
                continue
            module_id = module_dir.name
            errors: List[str] = []

            # Validate each contract type if it exists
            try:
                errors.extend(self.validate_module_contract(module_id))
            except FileNotFoundError:
                errors.append(f"Module contract missing for {module_id}")

            try:
                errors.extend(self.validate_wiring_contract(module_id))
            except FileNotFoundError:
                errors.append(f"Wiring contract missing for {module_id}")

            try:
                errors.extend(self.validate_policies_contract(module_id))
            except FileNotFoundError:
                errors.append(f"Policies contract missing for {module_id}")

            if errors:
                results[module_id] = errors

        return results

    def _validate_metadata(self, metadata: Dict[str, Any]) -> List[str]:
        """Validate contract metadata."""
        errors: List[str] = []
        if not metadata:
            errors.append("Metadata is missing")
            return errors

        required_fields = ["module_id", "owner", "band"]
        for field in required_fields:
            if field not in metadata:
                errors.append(f"Metadata missing required field: {field}")

        return errors

    def _validate_exports(self, exports: List[Dict[str, Any]]) -> List[str]:
        """Validate exports list."""
        errors: List[str] = []
        seen_symbols = set()

        for export in exports:
            symbol = export.get("symbol")
            from_file = export.get("from_file")

            if not symbol:
                errors.append("Export missing symbol")
            elif symbol in seen_symbols:
                errors.append(f"Duplicate export symbol: {symbol}")
            else:
                seen_symbols.add(symbol)

            if not from_file:
                errors.append(f"Export {symbol} missing from_file")
            elif not from_file.startswith("k1/"):
                errors.append(f"Export {symbol} from_file must start with k1/")

        return errors

    def _validate_dependencies(self, dependencies: List[Dict[str, Any]]) -> List[str]:
        """Validate dependencies list."""
        errors: List[str] = []
        seen_modules = set()

        for dep in dependencies:
            module = dep.get("module")
            version = dep.get("version")

            if not module:
                errors.append("Dependency missing module")
            elif module in seen_modules:
                errors.append(f"Duplicate dependency: {module}")
            else:
                seen_modules.add(module)

            if not version:
                errors.append(f"Dependency {module} missing version")

        return errors

    def _validate_imports(self, imports: Dict[str, Any]) -> List[str]:
        """Validate imports section."""
        errors: List[str] = []

        roots = imports.get("roots", [])
        if not roots:
            errors.append("Imports missing roots")
        else:
            if len(roots) != len(set(roots)):
                errors.append("Imports roots contains duplicates")
            for root in roots:
                if not root.startswith("k1/") or not root.endswith(".py"):
                    errors.append(f"Import root invalid: {root}")

        must_export = imports.get("must_export", [])
        seen_exports = set()
        for export in must_export:
            symbol = export.get("symbol")
            from_file = export.get("from_file")
            if not symbol or not from_file:
                errors.append("must_export entry incomplete")
            else:
                export_key = (symbol, from_file)
                if export_key in seen_exports:
                    errors.append(f"Duplicate must_export: {symbol} from {from_file}")
                else:
                    seen_exports.add(export_key)

        return errors
