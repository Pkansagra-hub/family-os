from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .schema_validator import SchemaValidator


class ContractLoader:
    """
    Loads and validates contract YAML files.

    Key features:
    - Discovers contract files under contracts_dir (e.g., modules/, wiring/)
    - Auto-validates on load using SchemaValidator
    - Caches loaded contracts by module_id
    - Supports different contract types (module, wiring, policies)
    """

    def __init__(
        self,
        contracts_dir: Optional[Path] = None,
        schema_validator: Optional[SchemaValidator] = None,
    ):
        if contracts_dir is None:
            current_dir = Path(__file__).parent
            contracts_dir = current_dir.parent

        self.contracts_dir = contracts_dir
        self.schema_validator = schema_validator or SchemaValidator()
        self._contract_cache: Dict[str, Dict[str, Any]] = {}

    def load_contract(self, contract_path: Path, expected_schema_id: str) -> Dict[str, Any]:
        """
        Load a single contract file and validate it.

        Args:
            contract_path: Path to the contract YAML file
            expected_schema_id: The schema $id to validate against

        Returns:
            The loaded and validated contract data

        Raises:
            FileNotFoundError: If contract file doesn't exist
            ValueError: If validation fails or schema not found
        """
        if not contract_path.exists():
            raise FileNotFoundError(f"Contract file not found: {contract_path}")

        try:
            contract_data = self._load_yaml(contract_path)
        except Exception as e:
            raise ValueError(f"Failed to parse contract YAML {contract_path}: {e}") from e

        # Validate against schema
        self.schema_validator.validate_contract(contract_data, expected_schema_id)

        # Cache by module_id if present
        module_id = contract_data.get("metadata", {}).get("module_id")
        if module_id:
            self._contract_cache[module_id] = contract_data

        return contract_data

    def load_module_contract(self, module_id: str) -> Dict[str, Any]:
        """
        Load a module contract by module_id.

        Assumes file at contracts/modules/{module_id}/module.contract.yaml
        """
        contract_path = self.contracts_dir / "modules" / module_id / "module.contract.yaml"
        return self.load_contract(contract_path, "k1://schemas/module/module.contract.schema.yaml")

    def load_wiring_contract(self, module_id: str) -> Dict[str, Any]:
        """
        Load a wiring contract by module_id.

        Assumes file at contracts/modules/{module_id}/wiring.contract.yaml
        """
        contract_path = self.contracts_dir / "modules" / module_id / "wiring.contract.yaml"
        return self.load_contract(contract_path, "k1://schemas/wiring/wiring.contract.schema.yaml")

    def load_policies_contract(self, module_id: str) -> Dict[str, Any]:
        """
        Load a policies contract by module_id.

        Assumes file at contracts/modules/{module_id}/policies.contract.yaml
        """
        contract_path = self.contracts_dir / "modules" / module_id / "policies.contract.yaml"
        return self.load_contract(
            contract_path, "k1://schemas/module/policies.contract.schema.yaml"
        )

    def load_all_module_contracts(self) -> Dict[str, Dict[str, Any]]:
        """
        Discover and load all module contracts under contracts/modules/

        Returns:
            Dict of module_id -> contract_data
        """
        contracts = {}
        modules_dir = self.contracts_dir / "modules"

        if not modules_dir.exists():
            return contracts

        for module_dir in modules_dir.iterdir():
            if module_dir.is_dir():
                module_id = module_dir.name
                try:
                    contract = self.load_module_contract(module_id)
                    contracts[module_id] = contract
                except Exception as e:
                    # Log but continue loading others
                    print(f"Failed to load module contract for {module_id}: {e}")

        return contracts

    def get_cached_contract(self, module_id: str) -> Optional[Dict[str, Any]]:
        """Get a previously loaded contract from cache"""
        return self._contract_cache.get(module_id)

    def clear_cache(self):
        """Clear the contract cache"""
        self._contract_cache.clear()

    @staticmethod
    def _load_yaml(path: Path) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Contract YAML must be a mapping/object: {path}")
        return data
