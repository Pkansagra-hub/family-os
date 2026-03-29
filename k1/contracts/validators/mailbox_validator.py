from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..loaders.wiring_loader import WiringLoader


class MailboxValidator:
    """
    Validates mailbox configurations for message passing.

    - Ensures mailbox schemas are consistent
    - Validates mailbox routing and permissions
    - Checks for mailbox naming conflicts
    - Validates mailbox metadata
    """

    def __init__(self, wiring_loader: Optional[WiringLoader] = None):
        self.wiring_loader = wiring_loader or WiringLoader()

    def validate_mailboxes(self, module_id: str) -> List[str]:
        """Validate mailboxes for a module."""
        errors: List[str] = []

        try:
            spec = self.wiring_loader.load_wiring_spec(module_id)

            # Validate mailboxes
            for mailbox in spec["mailboxes"]:
                errors.extend(self._validate_mailbox_definition(mailbox))

            # Check for naming conflicts within module
            errors.extend(self._validate_no_mailbox_conflicts(spec))

        except Exception as e:
            errors.append(f"Mailbox validation failed for {module_id}: {e}")

        return errors

    def validate_all_mailboxes(self) -> Dict[str, List[str]]:
        """Validate mailboxes across all modules."""
        results: Dict[str, List[str]] = {}

        self.wiring_loader.index_all_modules()

        modules_dir = self.wiring_loader.contract_loader.contracts_dir / "modules"
        if modules_dir.exists():
            for module_dir in modules_dir.iterdir():
                if module_dir.is_dir():
                    module_id = module_dir.name
                    errors = self.validate_mailboxes(module_id)
                    if errors:
                        results[module_id] = errors

        # Cross-module validations
        global_errors = self._validate_global_mailbox_consistency()
        if global_errors:
            results["GLOBAL"] = global_errors

        return results

    def _validate_mailbox_definition(self, mailbox: Dict[str, Any]) -> List[str]:
        """Validate a single mailbox definition."""
        errors: List[str] = []

        # Required fields
        required = ["name", "type", "permissions"]
        for field in required:
            if field not in mailbox:
                errors.append(f"Missing required field '{field}' in mailbox")

        # Name format
        if "name" in mailbox:
            name = mailbox["name"]
            if not isinstance(name, str) or not name.replace("_", "").replace("-", "").isalnum():
                errors.append(f"Invalid mailbox name '{name}': must be alphanumeric with _ or -")

        # Type validation
        if "type" in mailbox:
            valid_types = ["queue", "topic", "direct"]
            if mailbox["type"] not in valid_types:
                errors.append(
                    f"Invalid mailbox type '{mailbox['type']}': must be one of {valid_types}"
                )

        # Permissions validation
        if "permissions" in mailbox:
            perms = mailbox["permissions"]
            if not isinstance(perms, dict):
                errors.append("Permissions must be an object")
            else:
                required_perms = ["read", "write"]
                for perm in required_perms:
                    if perm not in perms:
                        errors.append(f"Missing permission '{perm}' in mailbox permissions")
                    elif not isinstance(perms[perm], list):
                        errors.append(f"Permission '{perm}' must be a list of module IDs")

        # Capacity validation
        if "capacity" in mailbox:
            capacity = mailbox["capacity"]
            if not isinstance(capacity, int) or capacity <= 0:
                errors.append(f"Invalid capacity '{capacity}': must be positive integer")

        return errors

    def _validate_no_mailbox_conflicts(self, spec: Dict[str, Any]) -> List[str]:
        """Check for mailbox naming conflicts within a module."""
        errors: List[str] = []

        mailboxes = [mb["name"] for mb in spec.get("mailboxes", []) if "name" in mb]
        duplicates = set([name for name in mailboxes if mailboxes.count(name) > 1])
        if duplicates:
            errors.append(f"Duplicate mailbox names: {duplicates}")

        return errors

    def _validate_global_mailbox_consistency(self) -> List[str]:
        """Validate consistency across all mailboxes."""
        errors: List[str] = []

        self.wiring_loader.index_all_modules()

        # Collect all mailbox names and their modules
        mailbox_modules: Dict[str, List[str]] = {}

        for module_id in self.wiring_loader._wiring_specs:
            spec = self.wiring_loader._wiring_specs[module_id]
            for mailbox in spec.get("mailboxes", []):
                name = mailbox.get("name")
                if name:
                    if name not in mailbox_modules:
                        mailbox_modules[name] = []
                    mailbox_modules[name].append(module_id)

        # Check for global naming conflicts
        for name, modules in mailbox_modules.items():
            if len(modules) > 1:
                errors.append(f"Mailbox name '{name}' used by multiple modules: {modules}")

        # Check permissions consistency
        for module_id in self.wiring_loader._wiring_specs:
            spec = self.wiring_loader._wiring_specs[module_id]
            for mailbox in spec.get("mailboxes", []):
                errors.extend(self._validate_mailbox_permissions(mailbox, module_id))

        return errors

    def _validate_mailbox_permissions(self, mailbox: Dict[str, Any], module_id: str) -> List[str]:
        """Validate permissions for a mailbox."""
        errors: List[str] = []

        perms = mailbox.get("permissions", {})

        # Check that module has access to its own mailbox
        for perm_type in ["read", "write"]:
            if perm_type in perms:
                allowed_modules = perms[perm_type]
                if module_id not in allowed_modules:
                    errors.append(
                        f"Module '{module_id}' does not have {perm_type} permission for its own mailbox '{mailbox['name']}'"
                    )

        # Check that referenced modules exist
        for perm_type in ["read", "write"]:
            if perm_type in perms:
                for mod in perms[perm_type]:
                    if mod not in self.wiring_loader._wiring_specs:
                        errors.append(
                            f"Mailbox '{mailbox['name']}' references non-existent module '{mod}' in {perm_type} permissions"
                        )

        return errors

    def get_mailbox_report(self) -> Dict[str, Any]:
        """Generate a report on mailboxes."""
        self.wiring_loader.index_all_modules()

        total_mailboxes = 0
        mailbox_types = {"queue": 0, "topic": 0, "direct": 0}

        for spec in self.wiring_loader._wiring_specs.values():
            for mailbox in spec.get("mailboxes", []):
                total_mailboxes += 1
                mb_type = mailbox.get("type")
                if mb_type in mailbox_types:
                    mailbox_types[mb_type] += 1

        report = {
            "total_mailboxes": total_mailboxes,
            "mailbox_types": mailbox_types,
            "modules_with_mailboxes": len(
                [
                    spec
                    for spec in self.wiring_loader._wiring_specs.values()
                    if spec.get("mailboxes")
                ]
            ),
        }

        return report
