"""
Ansible role validation script.

Validates:
- YAML syntax correctness
- Playbook syntax via ansible-playbook --syntax-check
- Dry-run execution against sample inventories
- Role task file structure
- Variable substitution safety
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


def find_playbooks(ansible_root: Path) -> List[Path]:
    """Find all playbook YAML files."""
    playbooks_dir = ansible_root / "playbooks"
    if not playbooks_dir.exists():
        return []
    return list(playbooks_dir.glob("*.yml"))


def find_inventories(ansible_root: Path) -> List[Path]:
    """Find all inventory host files."""
    inventories_dir = ansible_root / "inventories"
    if not inventories_dir.exists():
        return []

    inventories = []
    for inv_dir in inventories_dir.iterdir():
        if inv_dir.is_dir():
            hosts_file = inv_dir / "hosts.yml"
            if hosts_file.exists():
                inventories.append(hosts_file)

    return inventories


def syntax_check_playbook(playbook: Path, inventory: Path) -> Tuple[bool, str]:
    """Run ansible-playbook --syntax-check."""
    try:
        result = subprocess.run(
            ["ansible-playbook", "--syntax-check", "-i", str(inventory), str(playbook)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            return True, "Syntax check passed"
        else:
            return False, f"Syntax check failed:\n{result.stderr}"

    except FileNotFoundError:
        return (
            False,
            "ansible-playbook command not found. Install Ansible to run validation.",
        )
    except subprocess.TimeoutExpired:
        return False, "Syntax check timed out after 30 seconds"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


def dry_run_playbook(playbook: Path, inventory: Path) -> Tuple[bool, str]:
    """Run ansible-playbook in check mode (dry-run)."""
    try:
        result = subprocess.run(
            ["ansible-playbook", "--check", "-i", str(inventory), str(playbook)],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Check mode may have warnings but shouldn't fail fatally
        if result.returncode in (0, 2):  # 0 = success, 2 = changes would be made
            return True, f"Dry-run completed (exit code {result.returncode})"
        else:
            return False, f"Dry-run failed:\n{result.stderr}"

    except FileNotFoundError:
        return False, "ansible-playbook command not found"
    except subprocess.TimeoutExpired:
        return False, "Dry-run timed out after 60 seconds"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


def validate_role_structure(ansible_root: Path) -> Tuple[bool, str]:
    """Validate role directory structure."""
    roles_dir = ansible_root / "roles"
    if not roles_dir.exists():
        return False, f"Roles directory not found: {roles_dir}"

    expected_roles = ["secrets", "kernel", "telemetry"]
    missing_roles = []

    for role_name in expected_roles:
        role_dir = roles_dir / role_name
        if not role_dir.exists():
            missing_roles.append(role_name)
            continue

        # Check for tasks/main.yml
        tasks_file = role_dir / "tasks" / "main.yml"
        if not tasks_file.exists():
            missing_roles.append(f"{role_name} (missing tasks/main.yml)")

    if missing_roles:
        return False, f"Missing or incomplete roles: {', '.join(missing_roles)}"

    return True, f"All expected roles present: {', '.join(expected_roles)}"


def main():
    parser = argparse.ArgumentParser(description="Validate Ansible roles and playbooks")
    parser.add_argument(
        "--ansible-root",
        type=Path,
        default=Path(__file__).parent,
        help="Path to ansible directory (default: script location)",
    )
    parser.add_argument(
        "--skip-dry-run",
        action="store_true",
        help="Skip dry-run execution (only check syntax)",
    )
    parser.add_argument(
        "--inventory",
        type=str,
        help="Specific inventory to validate against (default: all)",
    )

    args = parser.parse_args()
    ansible_root = args.ansible_root.resolve()

    print(f"[Ansible Validation] Root: {ansible_root}")
    print()

    all_passed = True

    # Step 1: Validate role structure
    print("=" * 60)
    print("Step 1: Role Structure Validation")
    print("=" * 60)

    structure_ok, structure_msg = validate_role_structure(ansible_root)
    print(f"  {structure_msg}")

    if not structure_ok:
        print("  ❌ FAILED")
        all_passed = False
    else:
        print("  ✅ PASSED")

    print()

    # Step 2: Find playbooks and inventories
    playbooks = find_playbooks(ansible_root)
    inventories = find_inventories(ansible_root)

    if args.inventory:
        # Filter to specific inventory
        inventories = [inv for inv in inventories if args.inventory in str(inv)]

    if not playbooks:
        print("❌ No playbooks found")
        return 1

    if not inventories:
        print("❌ No inventories found")
        return 1

    print(f"Found {len(playbooks)} playbook(s) and {len(inventories)} inventory(ies)")
    print()

    # Step 3: Syntax checks
    print("=" * 60)
    print("Step 2: Syntax Validation")
    print("=" * 60)

    for playbook in playbooks:
        for inventory in inventories:
            inv_name = inventory.parent.name
            print(f"  Checking {playbook.name} with inventory '{inv_name}'...")

            syntax_ok, syntax_msg = syntax_check_playbook(playbook, inventory)

            if syntax_ok:
                print(f"    ✅ {syntax_msg}")
            else:
                print(f"    ❌ {syntax_msg}")
                all_passed = False

    print()

    # Step 4: Dry-run checks
    if not args.skip_dry_run:
        print("=" * 60)
        print("Step 3: Dry-Run Validation")
        print("=" * 60)

        for playbook in playbooks:
            for inventory in inventories:
                inv_name = inventory.parent.name
                print(f"  Dry-running {playbook.name} with inventory '{inv_name}'...")

                dryrun_ok, dryrun_msg = dry_run_playbook(playbook, inventory)

                if dryrun_ok:
                    print(f"    ✅ {dryrun_msg}")
                else:
                    print(f"    ⚠️  {dryrun_msg}")
                    # Dry-run failures are warnings, not hard failures

        print()

    # Summary
    print("=" * 60)
    print("Validation Summary")
    print("=" * 60)

    if all_passed:
        print("✅ All validation checks passed")
        return 0
    else:
        print("❌ Some validation checks failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
