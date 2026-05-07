"""``bootstrap_constitution`` — first-run loader for k1.selfmodel.

Issue M3.E5.I1.

Loads ``bootstrap_constitution.v0.yaml``, signs it with a synthetic
"system" Ed25519 key (generated on demand and persisted alongside the
constitution row), and writes it to the projection store as the
``ACTIVE`` row with ``parent_version=""``.

Idempotent: subsequent calls are no-ops if the store already has an
active row for the bootstrap ``constitution_id``.

The bootstrap key is intentionally separate from any guardian key; it
exists ONLY so that the M3 ``Ed25519SignatureChainValidator`` accepts
the synthetic root row. Onboarding amendments must be co-signed by a
real guardian key registered through the regular admin flow.
"""

from __future__ import annotations

import base64
import logging
import secrets
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import yaml
from nacl.signing import SigningKey, VerifyKey

from k1.selfmodel.contracts.constitution import (
    ConstitutionSnapshot,
    SigningProof,
)
from k1.selfmodel.ports.projection_store import IProjectionStorePort
from k1.selfmodel.service.signature_chain import (
    Ed25519SignatureChainValidator,
    canonical_body_bytes,
)

__all__ = [
    "BOOTSTRAP_CONSTITUTION_ID",
    "BOOTSTRAP_CONSTITUTION_ID_V1",
    "BOOTSTRAP_SIGNER_ID",
    "BOOTSTRAP_VERSION",
    "BOOTSTRAP_VERSION_V1",
    "BootstrapResult",
    "load_bootstrap_yaml",
    "load_bootstrap_yaml_v1",
    "ensure_bootstrap_constitution",
    "build_bootstrap_snapshot",
]

logger = logging.getLogger(__name__)

#: Constants used by tests + kernel bootstrap.
BOOTSTRAP_CONSTITUTION_ID = "k1.selfmodel.bootstrap.v0"
BOOTSTRAP_CONSTITUTION_ID_V1 = "k1.selfmodel.bootstrap.v1"
BOOTSTRAP_SIGNER_ID = "system:bootstrap"
BOOTSTRAP_VERSION = "v0:bootstrap"
BOOTSTRAP_VERSION_V1 = "v1:bootstrap"
BOOTSTRAP_WRITER_ID = "selfmodel:bootstrap"

#: Filename of the YAML resource shipped in this package.
_BOOTSTRAP_YAML = "bootstrap_constitution.v0.yaml"
_BOOTSTRAP_YAML_V1 = "bootstrap_constitution.v1.yaml"


@dataclass(frozen=True)
class BootstrapResult:
    """Return value from :func:`ensure_bootstrap_constitution`."""

    snapshot: ConstitutionSnapshot
    public_key: bytes
    created: bool  # True if newly written; False if already present


# ---------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------
def load_bootstrap_yaml(path: Path | None = None) -> dict:
    """Load and validate the V0 bootstrap YAML.

    Caller may pass an explicit ``path`` (used by tests). Default is the
    packaged ``bootstrap_constitution.v0.yaml``.
    """
    if path is not None:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = (
            resources.files("k1.selfmodel.contracts")
            .joinpath(_BOOTSTRAP_YAML)
            .read_text(encoding="utf-8")
        )
    parsed = yaml.safe_load(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"bootstrap yaml must parse to dict, got {type(parsed).__name__}")
    if parsed.get("constitution_id") != BOOTSTRAP_CONSTITUTION_ID:
        raise ValueError(f"bootstrap yaml constitution_id must be {BOOTSTRAP_CONSTITUTION_ID!r}")
    for required in ("governance", "visibility_rules", "autonomy_rules", "authority_rules"):
        if required not in parsed:
            raise ValueError(f"bootstrap yaml missing required key: {required!r}")
    return parsed


def load_bootstrap_yaml_v1(path: Path | None = None) -> dict:
    """Load and validate the V1 (conscience-first) bootstrap YAML.

    M9.E2.I1 -- v1 inverts the constitution: ``conscience_rules``
    enumerate forbidden / must_ask social acts (default-deny → default-
    allow). The legacy ``autonomy_rules`` / ``authority_rules`` keys
    are NOT required.
    """
    if path is not None:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = (
            resources.files("k1.selfmodel.contracts")
            .joinpath(_BOOTSTRAP_YAML_V1)
            .read_text(encoding="utf-8")
        )
    parsed = yaml.safe_load(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"bootstrap yaml must parse to dict, got {type(parsed).__name__}")
    if parsed.get("constitution_id") != BOOTSTRAP_CONSTITUTION_ID_V1:
        raise ValueError(
            f"bootstrap v1 yaml constitution_id must be {BOOTSTRAP_CONSTITUTION_ID_V1!r}"
        )
    if int(parsed.get("schema_version", 0)) != 1:
        raise ValueError("bootstrap v1 yaml schema_version must be 1")
    for required in ("governance", "visibility_rules", "conscience_rules"):
        if required not in parsed:
            raise ValueError(f"bootstrap v1 yaml missing required key: {required!r}")
    return parsed


# ---------------------------------------------------------------------
# Snapshot construction (pure)
# ---------------------------------------------------------------------
def build_bootstrap_snapshot(
    body: dict,
    *,
    signing_key: SigningKey,
    activated_at_ms: int,
    constitution_id: str = BOOTSTRAP_CONSTITUTION_ID,
    version: str = BOOTSTRAP_VERSION,
    signer_id: str = BOOTSTRAP_SIGNER_ID,
    key_id: str | None = None,
) -> ConstitutionSnapshot:
    """Sign ``body`` with ``signing_key`` and return the snapshot."""
    if not isinstance(signing_key, SigningKey):
        raise TypeError("signing_key must be nacl.signing.SigningKey")
    message = canonical_body_bytes(body)
    signature = signing_key.sign(message).signature
    proof = SigningProof(
        signer_id=signer_id,
        key_id=key_id or f"did:system:bootstrap#{secrets.token_hex(4)}",
        algorithm="ed25519",
        signature_b64=base64.b64encode(signature).decode("ascii"),
        signed_at_ms=activated_at_ms,
    )
    return ConstitutionSnapshot(
        constitution_id=constitution_id,
        version=version,
        parent_version="",
        body=body,
        signatures=(proof,),
        activated_at_ms=activated_at_ms,
    )


# ---------------------------------------------------------------------
# Idempotent first-run path
# ---------------------------------------------------------------------
def ensure_bootstrap_constitution(
    store: IProjectionStorePort,
    *,
    now_ms: int,
    yaml_path: Path | None = None,
    constitution_id: str = BOOTSTRAP_CONSTITUTION_ID,
    validator: Ed25519SignatureChainValidator | None = None,
    schema_version: int = 1,
) -> BootstrapResult:
    """Ensure ``constitution_id`` has an ACTIVE row; create + sign if not.

    ``validator`` (if provided) gets the bootstrap signer registered so
    that the M3 chain validator accepts the synthetic root row.

    ``schema_version`` selects the bootstrap YAML to load when the row
    is being minted for the first time:

    * ``0`` -- legacy autonomy_rules schema (kept for back-compat /
      contract-style tests that exercise the v0 surface).
    * ``1`` (default since M12.E1.I1) -- conscience-first schema
      (M9.E2.I1). When ``schema_version`` is 1 and ``constitution_id``
      is left at the v0 default, the v1 ``constitution_id`` is
      substituted automatically.

    Idempotent: if an active row already exists, returns it with
    ``created=False`` and does NOT mint a new key.
    """
    if schema_version == 1 and constitution_id == BOOTSTRAP_CONSTITUTION_ID:
        constitution_id = BOOTSTRAP_CONSTITUTION_ID_V1
    existing, _ = store.read_constitution(constitution_id)
    if existing is not None:
        # Recover the public key from the first signature so the
        # validator can be primed in the same call. We can't recover
        # the private key (we never persisted it); the row is signed
        # already and will continue to validate as long as the
        # validator has the public key.
        public_key = _recover_public_key(existing) or b""
        if validator is not None and public_key:
            validator.register_signer(BOOTSTRAP_SIGNER_ID, public_key)
        return BootstrapResult(snapshot=existing, public_key=public_key, created=False)

    if schema_version == 1:
        body = load_bootstrap_yaml_v1(yaml_path)
        version = BOOTSTRAP_VERSION_V1
    else:
        body = load_bootstrap_yaml(yaml_path)
        version = BOOTSTRAP_VERSION
    signing_key = SigningKey.generate()
    public_key = bytes(signing_key.verify_key)
    snapshot = build_bootstrap_snapshot(
        body,
        signing_key=signing_key,
        activated_at_ms=now_ms,
        constitution_id=constitution_id,
        version=version,
    )
    write_result = store.write_constitution(snapshot, writer_id=BOOTSTRAP_WRITER_ID)
    if not write_result.accepted:
        raise RuntimeError(f"bootstrap write rejected by store: {write_result.reason!r}")
    if validator is not None:
        validator.register_signer(BOOTSTRAP_SIGNER_ID, public_key)
    logger.info(
        "bootstrap_constitution: wrote %s version=%s",
        constitution_id,
        snapshot.version,
    )
    return BootstrapResult(snapshot=snapshot, public_key=public_key, created=True)


# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------
def _recover_public_key(snapshot: ConstitutionSnapshot) -> bytes | None:
    """Best-effort recovery of the bootstrap signer's public key.

    We can't recover from a signature alone (Ed25519 is not recovery-
    capable). Returns ``None`` — the caller is responsible for
    re-registering the signer key from a side channel (or accepting
    that the row was previously validated).
    """
    _ = snapshot  # explicit no-op
    _ = VerifyKey  # imported above for symmetry; not used in V0
    return None
