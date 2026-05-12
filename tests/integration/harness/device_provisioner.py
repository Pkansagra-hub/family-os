"""Provision K1 devices into K0's PostgreSQL device ledger.

Required because the K0 ``minimal_gate`` rejects any envelope from a
device that does not have a row in ``st_devices`` + an ACTIVE row in
``st_device_keys`` — even if the envelope's signature is otherwise
well-formed. (See ``k0/ports/command.py`` ``DEVICE_NOT_PROVISIONED``.)

For the Epic 7.1 harness the K0 stack runs in Docker, so we shell into
``k0-postgres`` via ``docker exec`` rather than open an asyncpg
connection — the local PG port may be firewalled and the in-container
``psql`` is the same path the existing
``k0/deploy/scripts/provisioning/provision_and_submit.py`` uses.

The provisioner returns a ``dict[device_id, bytes]`` of HMAC secrets;
the harness wires those secrets into each K1's bridge runtime so that
HMAC signatures verify against the row we just inserted.
"""

from __future__ import annotations

import os
import secrets
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone

from .family_layout import FamilyLayout

DEFAULT_PG_CONTAINER = "k0-postgres"
DEFAULT_PG_USER = "k0user"
DEFAULT_PG_DB = "k0_kernel"
DEFAULT_MLS_GROUP = "mls-group-harness"
# Generated key id used by ``HmacSigning`` in :mod:`bridge.core.signing`
# follows the pattern ``did:device:<device_id>#hmac``.


class DeviceProvisioningError(RuntimeError):
    """Raised when a ``docker exec psql`` provisioning call fails."""


@dataclass(frozen=True)
class ProvisionedSecrets:
    """Result of provisioning a family layout into K0."""

    hmac_secrets: dict[str, bytes]  # device_id -> 32 raw bytes (idempotency)
    ed25519_seeds: dict[str, bytes]  # device_id -> 32-byte Ed25519 seed
    tenant_id: str
    space_id: str

    def secret_for(self, device_id: str) -> bytes:
        return self.hmac_secrets[device_id]

    def signing_seed_for(self, device_id: str) -> bytes:
        return self.ed25519_seeds[device_id]


# Schema URIs the bridge K1 generated clients publish under. Each must
# have an ACTIVE row in K0's ``schema_registry`` for the gate to admit
# the envelope.
DEFAULT_BRIDGE_SCHEMA_URIS: tuple[tuple[str, str], ...] = (
    ("bridge://contracts/schemas/memory.write.v1.json", "1.0"),
    ("bridge://contracts/schemas/recall.request.v1.json", "1.0"),
    ("bridge://contracts/schemas/recall.response.v1.json", "1.0"),
    ("bridge://contracts/schemas/feedback.envelope.v1.json", "1.0"),
    ("bridge://contracts/schemas/observability.payload.v1.json", "1.0"),
)


def provision_family(
    family: FamilyLayout,
    *,
    pg_container: str = DEFAULT_PG_CONTAINER,
    pg_user: str = DEFAULT_PG_USER,
    pg_db: str = DEFAULT_PG_DB,
    mls_group_id: str = DEFAULT_MLS_GROUP,
    schema_uris: tuple[tuple[str, str], ...] = DEFAULT_BRIDGE_SCHEMA_URIS,
) -> ProvisionedSecrets:
    """Insert/refresh device + key rows for every device in ``family``.

    Each device gets a freshly generated 32-byte HMAC secret. Existing
    rows are deleted first to avoid stale-cache issues in K0's
    ``ProvisioningLedger`` (it caches verifies by ``device_id``).
    """
    pg_container = os.environ.get("K0_PG_CONTAINER", pg_container)
    pg_user = os.environ.get("K0_PG_USER", pg_user)
    pg_db = os.environ.get("K0_PG_DB", pg_db)

    secrets_map: dict[str, bytes] = {}
    seeds_map: dict[str, bytes] = {}
    now = datetime.now(timezone.utc).isoformat()

    # Lazy import to keep harness module importable without PyNaCl
    import base64 as _b64

    from nacl.signing import SigningKey

    statements: list[str] = []
    for person in family.people:
        for device in person.devices:
            hmac_secret = secrets.token_bytes(32)
            secrets_map[device.device_id] = hmac_secret
            hmac_hex = hmac_secret.hex()

            seed = secrets.token_bytes(32)
            seeds_map[device.device_id] = seed
            signing_key = SigningKey(seed)
            verify_key_b64 = (
                _b64.urlsafe_b64encode(bytes(signing_key.verify_key)).rstrip(b"=").decode("ascii")
            )
            statements.extend(
                [
                    f"DELETE FROM st_device_keys WHERE device_id = '{device.device_id}'",
                    f"DELETE FROM st_devices WHERE device_id = '{device.device_id}'",
                    (
                        f"INSERT INTO st_devices "
                        f"(device_id, tenant_id, space_id, mls_group_id, provisioned_ts, hmac_secret) "
                        f"VALUES ('{device.device_id}', '{family.family_id}', "
                        f"'{family.family_id}', '{mls_group_id}', '{now}', '\\x{hmac_hex}')"
                    ),
                    (
                        f"INSERT INTO st_device_keys "
                        f"(device_id, key_version, verify_key, key_state, registered_ts, activated_ts) "
                        f"VALUES ('{device.device_id}', '1', '{verify_key_b64}', "
                        f"'ACTIVE', '{now}', '{now}')"
                    ),
                ]
            )

    if statements:
        _exec_psql(statements, pg_container=pg_container, pg_user=pg_user, pg_db=pg_db)

    # Register every bridge schema_uri so the K0 gate's schema-status
    # check passes. ON CONFLICT promotes any pre-existing row to ACTIVE.
    schema_stmts: list[str] = []
    import hashlib as _h

    for uri, ver in schema_uris:
        sha = _h.sha256(f"{uri}@{ver}".encode("utf-8")).hexdigest()
        schema_stmts.append(
            f"INSERT INTO schema_registry (schema_uri, version, sha256, status) "
            f"VALUES ('{uri}', '{ver}', '{sha}', 'ACTIVE') "
            f"ON CONFLICT (schema_uri, version) DO UPDATE SET status = 'ACTIVE'"
        )
    if schema_stmts:
        _exec_psql(schema_stmts, pg_container=pg_container, pg_user=pg_user, pg_db=pg_db)

    return ProvisionedSecrets(
        hmac_secrets=secrets_map,
        ed25519_seeds=seeds_map,
        tenant_id=family.family_id,
        space_id=family.family_id,
    )


@dataclass(frozen=True)
class AdHocDevice:
    """Provisioning result for a one-off device bound to a (tenant, space).

    Used by Epic 7.2 partition-isolation tests that need to write into
    sibling sub-spaces under one family's tenant. Each band is modeled
    as its own ``space_id`` — and because the K0 minimal_gate enforces
    ``SPACE_TENANT_MISMATCH`` against the device's *provisioned* binding,
    each scope-band space requires its own device row.
    """

    device_id: str
    tenant_id: str
    space_id: str
    hmac_secret: bytes
    ed25519_seed: bytes


def provision_extra_device(
    *,
    device_id: str,
    tenant_id: str,
    space_id: str,
    pg_container: str = DEFAULT_PG_CONTAINER,
    pg_user: str = DEFAULT_PG_USER,
    pg_db: str = DEFAULT_PG_DB,
    mls_group_id: str = DEFAULT_MLS_GROUP,
) -> AdHocDevice:
    """Insert a single device row bound to ``(tenant_id, space_id)``.

    Returns the freshly generated HMAC secret + Ed25519 seed so callers
    can sign envelopes for this device. Existing rows for ``device_id``
    are deleted first (mirrors :func:`provision_family`'s idempotency).
    """
    pg_container = os.environ.get("K0_PG_CONTAINER", pg_container)
    pg_user = os.environ.get("K0_PG_USER", pg_user)
    pg_db = os.environ.get("K0_PG_DB", pg_db)

    import base64 as _b64

    from nacl.signing import SigningKey

    hmac_secret = secrets.token_bytes(32)
    seed = secrets.token_bytes(32)
    signing_key = SigningKey(seed)
    verify_key_b64 = (
        _b64.urlsafe_b64encode(bytes(signing_key.verify_key)).rstrip(b"=").decode("ascii")
    )
    now = datetime.now(timezone.utc).isoformat()
    hmac_hex = hmac_secret.hex()

    statements = [
        f"DELETE FROM st_device_keys WHERE device_id = '{device_id}'",
        f"DELETE FROM st_devices WHERE device_id = '{device_id}'",
        (
            f"INSERT INTO st_devices "
            f"(device_id, tenant_id, space_id, mls_group_id, provisioned_ts, hmac_secret) "
            f"VALUES ('{device_id}', '{tenant_id}', '{space_id}', "
            f"'{mls_group_id}', '{now}', '\\x{hmac_hex}')"
        ),
        (
            f"INSERT INTO st_device_keys "
            f"(device_id, key_version, verify_key, key_state, registered_ts, activated_ts) "
            f"VALUES ('{device_id}', '1', '{verify_key_b64}', "
            f"'ACTIVE', '{now}', '{now}')"
        ),
    ]
    _exec_psql(statements, pg_container=pg_container, pg_user=pg_user, pg_db=pg_db)
    return AdHocDevice(
        device_id=device_id,
        tenant_id=tenant_id,
        space_id=space_id,
        hmac_secret=hmac_secret,
        ed25519_seed=seed,
    )


def _exec_psql(statements: list[str], *, pg_container: str, pg_user: str, pg_db: str) -> str:
    sql = "; ".join(statements)
    cmd = [
        "docker",
        "exec",
        "-i",
        pg_container,
        "psql",
        "-U",
        pg_user,
        "-d",
        pg_db,
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        sql,
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise DeviceProvisioningError(
            f"docker exec psql failed (rc={proc.returncode}): "
            f"{proc.stderr.decode('utf-8', errors='replace')}"
        )
    return proc.stdout.decode("utf-8", errors="replace")
    return proc.stdout.decode("utf-8", errors="replace")
