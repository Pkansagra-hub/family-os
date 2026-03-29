#!/usr/bin/env python3
"""
Device Provisioning Script for K0 Kernel

This script provisions devices in the K0 kernel by:
1. Validating device credentials
2. Registering device in PostgreSQL database
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
        [--db-url postgresql://user:pass@host:5432/k0_kernel]
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional

import asyncpg


class K0DeviceProvisioner:
    """Provisions devices in K0 kernel."""

    def __init__(self, db_url: Optional[str] = None):
        """
        Initialize provisioner.

        Args:
            db_url: PostgreSQL connection URL
        """
        if db_url is None:
            db_url = os.getenv(
                "K0_DATABASE_URL", "postgresql://k0_user:k0_password@localhost:5432/k0_kernel"
            )
        self.db_url = db_url

    @staticmethod
    def _get_default_db_url() -> str:
        """Get default database URL from environment."""
        return os.getenv(
            "K0_DATABASE_URL", "postgresql://k0_user:k0_password@localhost:5432/k0_kernel"
        )

    async def provision_device(self, device_id, tenant_id, space_id, roles, band, public_key):
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
            conn = await asyncpg.connect(self.db_url)

            existing = await conn.fetchrow(
                "SELECT device_id FROM devices WHERE device_id = $1", device_id
            )

            if existing:
                print(f"⚠️  Device already provisioned: {device_id}")
                print("   Would you like to update? (y/n): ", end="")
                response = input().strip().lower()

                if response != "y":
                    await conn.close()
                    return {"status": "SKIPPED", "device_id": device_id}

                # Delete existing device
                await conn.execute("DELETE FROM devices WHERE device_id = $1", device_id)
                print("   ✅ Deleted existing device")

            # Insert new device
            await conn.execute(
                """
                INSERT INTO devices (
                    tenant_id, space_id, device_id, public_key, roles, band, status, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                tenant_id,
                space_id,
                device_id,
                public_key,
                roles,
                band,
                "ACTIVE",
                datetime.now(timezone.utc).isoformat(),
            )

            # Verify provisioning
            device_record = await conn.fetchrow(
                "SELECT * FROM devices WHERE device_id = $1", device_id
            )
            await conn.close()

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
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        except asyncpg.PostgresError as e:
            return {"status": "FAILED", "error": f"Database error: {str(e)}"}

    async def list_devices(self, tenant_id=None):
        """
        List provisioned devices.

        Args:
            tenant_id: Filter by tenant (None = all)

        Returns:
            List of device records
        """
        try:
            conn = await asyncpg.connect(self.db_url)

            if tenant_id:
                devices = await conn.fetch(
                    """
                    SELECT device_id, tenant_id, space_id, roles, band, status, created_at
                    FROM devices WHERE tenant_id = $1 ORDER BY created_at DESC
                    """,
                    tenant_id,
                )
            else:
                devices = await conn.fetch(
                    """
                    SELECT device_id, tenant_id, space_id, roles, band, status, created_at
                    FROM devices ORDER BY created_at DESC
                    """
                )

            await conn.close()
            return devices

        except asyncpg.PostgresError as e:
            print(f"❌ Error listing devices: {str(e)}")
            return []

    async def delete_device(self, device_id):
        """
        Delete provisioned device.

        Args:
            device_id: Device to delete

        Returns:
            Dictionary with deletion result
        """
        try:
            conn = await asyncpg.connect(self.db_url)

            # Check if exists
            existing = await conn.fetchrow(
                "SELECT device_id FROM devices WHERE device_id = $1", device_id
            )
            if not existing:
                await conn.close()
                return {"status": "FAILED", "error": f"Device not found: {device_id}"}

            # Delete device
            await conn.execute("DELETE FROM devices WHERE device_id = $1", device_id)
            await conn.close()

            return {"status": "SUCCESS", "device_id": device_id}

        except asyncpg.PostgresError as e:
            return {"status": "FAILED", "error": f"Database error: {str(e)}"}

    async def verify_provisioning(self, device_id):
        """
        Verify device is properly provisioned.

        Args:
            device_id: Device to verify

        Returns:
            Dictionary with verification result
        """
        try:
            conn = await asyncpg.connect(self.db_url)

            device = await conn.fetchrow(
                """
                SELECT device_id, tenant_id, space_id, roles, band, status, created_at
                FROM devices WHERE device_id = $1
                """,
                device_id,
            )
            await conn.close()

            if not device:
                return {"status": "FAILED", "error": f"Device not found: {device_id}"}

            return {
                "status": "SUCCESS",
                "device_id": device["device_id"],
                "tenant_id": device["tenant_id"],
                "space_id": device["space_id"],
                "roles": device["roles"],
                "band": device["band"],
                "status": device["status"],
                "created_at": device["created_at"],
            }

        except asyncpg.PostgresError as e:
            return {"status": "FAILED", "error": f"Database error: {str(e)}"}


async def async_main():
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
        "--db-url", help="PostgreSQL connection URL (or set K0_DATABASE_URL env var)"
    )

    # List command
    list_cmd = subparsers.add_parser("list", help="List provisioned devices")
    list_cmd.add_argument("--tenant-id", help="Filter by tenant ID")
    list_cmd.add_argument("--db-url", help="PostgreSQL connection URL")

    # Verify command
    verify_cmd = subparsers.add_parser("verify", help="Verify device provisioning")
    verify_cmd.add_argument("--device-id", required=True, help="Device ID to verify")
    verify_cmd.add_argument("--db-url", help="PostgreSQL connection URL")

    # Delete command
    delete_cmd = subparsers.add_parser("delete", help="Delete provisioned device")
    delete_cmd.add_argument("--device-id", required=True, help="Device ID to delete")
    delete_cmd.add_argument("--db-url", help="PostgreSQL connection URL")

    args = parser.parse_args()

    # Default command (backward compatibility)
    if not args.command:
        if hasattr(args, "device_id") and args.device_id:
            args.command = "provision"
        else:
            parser.print_help()
            return 1

    try:
        db_url = getattr(args, "db_url", None)
        provisioner = K0DeviceProvisioner(db_url=db_url)

        if args.command == "provision":
            result = await provisioner.provision_device(
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
            devices = await provisioner.list_devices(tenant_id=args.tenant_id)

            if not devices:
                print("No devices found")
                return 0

            print("\n" + "=" * 100)
            print(
                f"{'Device ID':<30} {'Tenant':<15} {'Space':<15} {'Roles':<20} {'Band':<8} {'Status':<10}"
            )
            print("=" * 100)

            for device in devices:
                print(
                    f"{device['device_id']:<30} {device['tenant_id']:<15} {device['space_id']:<15} "
                    f"{device['roles']:<20} {device['band']:<8} {device['status']:<10}"
                )

            print("=" * 100)
            return 0

        elif args.command == "verify":
            result = await provisioner.verify_provisioning(device_id=args.device_id)

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

            result = await provisioner.delete_device(device_id=args.device_id)

            if result["status"] == "SUCCESS":
                print(f"✅ Device deleted: {result['device_id']}")
                return 0
            else:
                print(f"❌ Deletion failed: {result['error']}")
                return 1

    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return 1

    return 0


def main():
    """Sync entry point for CLI."""
    return asyncio.run(async_main())


if __name__ == "__main__":
    sys.exit(main())
