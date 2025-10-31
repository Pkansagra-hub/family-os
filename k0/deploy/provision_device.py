#!/usr/bin/env python3
"""
Device Provisioning Script for K0 Kernel

This script provisions devices in the K0 kernel by:
1. Validating device credentials
2. Registering device in SQLite database
3. Setting up role-based access control
4. Verifying provisioning with test command

Usage:
    python provision_device.py \
        --device-id device-mobile-001 \
        --tenant-id tenant-001 \
        --space-id space-home \
        --roles device,observer \
        --band GREEN \
        --public-key "MCowBQYDK2VwAyEA..." \
        [--kernel-url http://localhost:8080] \
        [--db-path /path/to/k0_kernel.db]
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


class K0DeviceProvisioner:
    """Provisions devices in K0 kernel."""

    def __init__(self, db_path=None):
        """
        Initialize provisioner.

        Args:
            db_path: Path to K0 SQLite database
        """
        if db_path is None:
            # Auto-detect database location
            db_path = self._find_database()

        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")

    @staticmethod
    def _find_database():
        """Find K0 database in docker volume or local path."""
        # Try common locations
        candidates = [
            Path("d:/familyos/k0_runtime.sqlite3"),
            Path("/data/k0_kernel.db"),
            Path("./k0_runtime.sqlite3"),
        ]

        for path in candidates:
            if path.exists():
                return path

        raise FileNotFoundError(
            "Could not find K0 database. Specify with --db-path or "
            "ensure docker-compose is running"
        )

    def provision_device(self, device_id, tenant_id, space_id, roles, band, public_key):
        """
        Provision device in K0 kernel.

        Args:
            device_id: Unique device identifier
            tenant_id: Tenant/organization ID
            space_id: Space/namespace within tenant
            roles: Comma-separated roles (e.g., "device,observer")
            band: Privacy band (GREEN, AMBER, RED)
            public_key: Ed25519 public key (PEM or hex format)

        Returns:
            Dictionary with provisioning result
        """
        # Validate inputs
        if not all([device_id, tenant_id, space_id, roles, band, public_key]):
            raise ValueError("All parameters are required")

        valid_bands = ["GREEN", "AMBER", "RED"]
        if band not in valid_bands:
            raise ValueError(f"Invalid band: {band}. Must be one of {valid_bands}")

        # Check if device already exists
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT device_id FROM devices WHERE device_id = ?", (device_id,))
            existing = cursor.fetchone()

            if existing:
                print(f"⚠️  Device already provisioned: {device_id}")
                print("   Would you like to update? (y/n): ", end="")
                response = input().strip().lower()

                if response != "y":
                    conn.close()
                    return {"status": "SKIPPED", "device_id": device_id}

                # Delete existing device
                cursor.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))
                conn.commit()
                print("   ✅ Deleted existing device")

            # Insert new device
            cursor.execute(
                """
                INSERT INTO devices (
                    tenant_id, space_id, device_id, public_key, roles, band, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    space_id,
                    device_id,
                    public_key,
                    roles,
                    band,
                    "ACTIVE",
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

            # Verify provisioning
            cursor.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,))
            device_record = cursor.fetchone()
            conn.close()

            if not device_record:
                raise RuntimeError("Device provisioning failed: not found after insert")

            return {
                "status": "SUCCESS",
                "device_id": device_id,
                "tenant_id": tenant_id,
                "space_id": space_id,
                "roles": roles,
                "band": band,
                "public_key_prefix": public_key[:20] + "...",
                "created_at": datetime.utcnow().isoformat(),
            }

        except sqlite3.Error as e:
            return {"status": "FAILED", "error": f"Database error: {str(e)}"}

    def list_devices(self, tenant_id=None):
        """
        List provisioned devices.

        Args:
            tenant_id: Filter by tenant (None = all)

        Returns:
            List of device records
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            if tenant_id:
                cursor.execute(
                    """
                    SELECT device_id, tenant_id, space_id, roles, band, status, created_at
                    FROM devices WHERE tenant_id = ? ORDER BY created_at DESC
                    """,
                    (tenant_id,),
                )
            else:
                cursor.execute(
                    """
                    SELECT device_id, tenant_id, space_id, roles, band, status, created_at
                    FROM devices ORDER BY created_at DESC
                    """
                )

            devices = cursor.fetchall()
            conn.close()

            return devices

        except sqlite3.Error as e:
            print(f"❌ Error listing devices: {str(e)}")
            return []

    def delete_device(self, device_id):
        """
        Delete provisioned device.

        Args:
            device_id: Device to delete

        Returns:
            Dictionary with deletion result
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Check if exists
            cursor.execute("SELECT device_id FROM devices WHERE device_id = ?", (device_id,))
            if not cursor.fetchone():
                conn.close()
                return {"status": "FAILED", "error": f"Device not found: {device_id}"}

            # Delete device
            cursor.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))
            conn.commit()
            conn.close()

            return {"status": "SUCCESS", "device_id": device_id}

        except sqlite3.Error as e:
            return {"status": "FAILED", "error": f"Database error: {str(e)}"}

    def verify_provisioning(self, device_id):
        """
        Verify device is properly provisioned.

        Args:
            device_id: Device to verify

        Returns:
            Dictionary with verification result
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT device_id, tenant_id, space_id, roles, band, status, created_at
                FROM devices WHERE device_id = ?
                """,
                (device_id,),
            )
            device = cursor.fetchone()
            conn.close()

            if not device:
                return {"status": "FAILED", "error": f"Device not found: {device_id}"}

            return {
                "status": "SUCCESS",
                "device_id": device[0],
                "tenant_id": device[1],
                "space_id": device[2],
                "roles": device[3],
                "band": device[4],
                "status": device[5],
                "created_at": device[6],
            }

        except sqlite3.Error as e:
            return {"status": "FAILED", "error": f"Database error: {str(e)}"}


def main():
    parser = argparse.ArgumentParser(
        description="Provision devices in K0 kernel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Provision command
    provision_cmd = subparsers.add_parser("provision", help="Provision a new device")
    provision_cmd.add_argument("--device-id", required=True, help="Device ID")
    provision_cmd.add_argument("--tenant-id", required=True, help="Tenant ID")
    provision_cmd.add_argument("--space-id", required=True, help="Space ID")
    provision_cmd.add_argument(
        "--roles", required=True, help="Comma-separated roles (e.g., device,observer)"
    )
    provision_cmd.add_argument("--band", required=True, help="Privacy band (GREEN, AMBER, RED)")
    provision_cmd.add_argument("--public-key", required=True, help="Ed25519 public key")
    provision_cmd.add_argument(
        "--db-path", help="Path to K0 SQLite database (auto-detected if omitted)"
    )

    # List command
    list_cmd = subparsers.add_parser("list", help="List provisioned devices")
    list_cmd.add_argument("--tenant-id", help="Filter by tenant ID")
    list_cmd.add_argument("--db-path", help="Path to K0 SQLite database")

    # Verify command
    verify_cmd = subparsers.add_parser("verify", help="Verify device provisioning")
    verify_cmd.add_argument("--device-id", required=True, help="Device ID to verify")
    verify_cmd.add_argument("--db-path", help="Path to K0 SQLite database")

    # Delete command
    delete_cmd = subparsers.add_parser("delete", help="Delete provisioned device")
    delete_cmd.add_argument("--device-id", required=True, help="Device ID to delete")
    delete_cmd.add_argument("--db-path", help="Path to K0 SQLite database")

    args = parser.parse_args()

    # Default command (backward compatibility)
    if not args.command:
        if hasattr(args, "device_id") and args.device_id:
            args.command = "provision"
        else:
            parser.print_help()
            return 1

    try:
        provisioner = K0DeviceProvisioner(db_path=args.db_path)

        if args.command == "provision":
            result = provisioner.provision_device(
                device_id=args.device_id,
                tenant_id=args.tenant_id,
                space_id=args.space_id,
                roles=args.roles,
                band=args.band,
                public_key=args.public_key,
            )

            if result["status"] == "SUCCESS":
                print("\n✅ Device provisioned successfully!")
                print(f"   Device ID: {result['device_id']}")
                print(f"   Tenant: {result['tenant_id']}")
                print(f"   Space: {result['space_id']}")
                print(f"   Roles: {result['roles']}")
                print(f"   Band: {result['band']}")
                print(f"   Public Key: {result['public_key_prefix']}")
                return 0
            elif result["status"] == "SKIPPED":
                print(f"⏭️  Provisioning skipped for {result['device_id']}")
                return 0
            else:
                print(f"❌ Provisioning failed: {result['error']}")
                return 1

        elif args.command == "list":
            devices = provisioner.list_devices(tenant_id=args.tenant_id)

            if not devices:
                print("No devices found")
                return 0

            print("\n" + "=" * 100)
            print(
                f"{'Device ID':<30} {'Tenant':<15} {'Space':<15} {'Roles':<20} {'Band':<8} {'Status':<10}"
            )
            print("=" * 100)

            for device in devices:
                device_id, tenant_id, space_id, roles, band, status, _ = device
                print(
                    f"{device_id:<30} {tenant_id:<15} {space_id:<15} {roles:<20} {band:<8} {status:<10}"
                )

            print("=" * 100)
            return 0

        elif args.command == "verify":
            result = provisioner.verify_provisioning(device_id=args.device_id)

            if result["status"] == "SUCCESS":
                print("\n✅ Device provisioning verified!")
                print(json.dumps(result, indent=2))
                return 0
            else:
                print(f"❌ Verification failed: {result['error']}")
                return 1

        elif args.command == "delete":
            print(f"Delete device: {args.device_id}? (y/n): ", end="")
            response = input().strip().lower()

            if response != "y":
                print("Cancelled")
                return 0

            result = provisioner.delete_device(device_id=args.device_id)

            if result["status"] == "SUCCESS":
                print(f"✅ Device deleted: {result['device_id']}")
                return 0
            else:
                print(f"❌ Deletion failed: {result['error']}")
                return 1

    except FileNotFoundError as e:
        print(f"❌ Error: {str(e)}")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
