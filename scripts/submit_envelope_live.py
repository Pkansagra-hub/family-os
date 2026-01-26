"""Submit an envelope to the K0 kernel and watch memory formation live.

This script is a client-side debugging tool. It:
- (Optionally) provisions a device key directly in Postgres.
- Builds and signs a V1 envelope (or submits a provided envelope JSON).
- Submits to `/k0/command.submit`.
- (Optionally) triggers P03 consolidation via `/k0/admin/pipelines/P03_CONSOLIDATION/trigger`.
- Watches Postgres for:
  - `st_hipp_events` (ingest)
  - `st_vec` (embeddings)
  - `st_observations` (truth writes across layers; includes st_kg_edges)

Notes:
- This script intentionally avoids modifying kernel code. It only uses public HTTP
  endpoints and DB reads/writes (for provisioning).
- No emojis in output to keep logs clean and tool-friendly.

Examples (optional; run from repo root):
- Build from a body JSON file:
    python scripts/submit_envelope_live.py --body-file data/body.json --provision-device --trigger-p03

- Submit an existing fully-formed envelope:
    python scripts/submit_envelope_live.py --envelope-file data/envelope.json --trigger-p03
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import secrets
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import asyncpg
import httpx
from nacl.signing import SigningKey


def _ensure_repo_root_on_path() -> None:
    """Ensure repo root is importable.

    Many dev scripts in this repo run without installing the package.
    """

    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_PG_DSN = "postgresql://k0user:changeme@localhost:5432/k0_kernel"

DEFAULT_TENANT_ID = "tenant-test"
DEFAULT_SPACE_ID = "space-home"
DEFAULT_DEVICE_ID = "device-test-1"
DEFAULT_ACTOR = "actor-test-123"

DEFAULT_SCHEMA_URI = "schema://memory.delta"
DEFAULT_SCHEMA_VERSION = "1.0"
DEFAULT_TOPIC = "memory.delta"
DEFAULT_POLICY_VERSION = "2025-09-28"


@dataclass(frozen=True)
class WatchConfig:
    poll_interval_s: float
    timeout_s: float
    tail_limit: int


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_unix_ms() -> int:
    return int(time.time() * 1000)


def _load_json(path: str) -> Any:
    if path == "-":
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode_key_material(raw: str) -> bytes:
    """Decode key material supplied via CLI.

    Accepts:
    - base64url (unpadded/padded)
    - base64 (standard)
    - hex

    Returns raw bytes.
    """

    raw = raw.strip()

    # hex
    if all(c in "0123456789abcdefABCDEF" for c in raw) and len(raw) % 2 == 0:
        try:
            return bytes.fromhex(raw)
        except ValueError:
            pass

    # base64url / base64
    padded = raw + "=" * (-len(raw) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            return decoder(padded)
        except Exception:
            continue

    raise ValueError("Could not decode key material (expected hex/base64/base64url)")


def _default_persistent_key_path() -> Path:
    """Use the same persistent test key path as the deploy scripts."""

    project_root = Path(__file__).resolve().parent.parent
    return project_root / "k0" / "deploy" / "data" / "test_device_key.b64"


def _get_or_create_persistent_signing_key() -> SigningKey:
    """Load a persistent Ed25519 signing key from file, or create one."""

    _ensure_repo_root_on_path()
    from k0.security.crypto import encode_base64url

    key_file = _default_persistent_key_path()
    if key_file.exists():
        key_b64 = key_file.read_text(encoding="utf-8").strip()
        key_bytes = _decode_key_material(key_b64)
        # File stores raw SigningKey bytes (64) or seed (32). Normalize.
        if len(key_bytes) == 32:
            return SigningKey(key_bytes)
        if len(key_bytes) == 64:
            return SigningKey(key_bytes[:32])
        raise ValueError(
            f"Unexpected key length in {key_file}: {len(key_bytes)} bytes (expected 32 or 64)"
        )

    signing_key = SigningKey.generate()
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(encode_base64url(bytes(signing_key)), encoding="utf-8")
    return signing_key


def _signing_key_from_args(args: argparse.Namespace) -> SigningKey:
    if args.signing_key is None:
        # Default to a persistent key so repeated runs against a long-lived kernel
        # don't fight the provisioning key cache.
        return _get_or_create_persistent_signing_key()

    key_bytes = _decode_key_material(args.signing_key)

    # PyNaCl SigningKey supports either 32-byte seed or 64-byte private key.
    if len(key_bytes) == 32:
        return SigningKey(key_bytes)
    if len(key_bytes) == 64:
        return SigningKey(key_bytes[:32])

    raise ValueError(f"Unsupported signing key length: {len(key_bytes)} bytes (expected 32 or 64)")


async def _provision_device(
    conn: asyncpg.Connection,
    *,
    tenant_id: str,
    space_id: str,
    device_id: str,
    verify_key_b64url: str,
    schema_uri: str,
    schema_version: str,
) -> None:
    """Provision the device and its verify key directly in Postgres.

    This mirrors the dev scripts under k0/deploy/scripts, but avoids Docker.

    It deletes any prior device/device_key rows to force cache invalidation.
    """

    now = _utc_iso()

    schema_sha = _sha256_hex(f"{schema_uri}@{schema_version}".encode("utf-8"))

    # NOTE: This is intentionally destructive for the target device_id.
    await conn.execute("DELETE FROM st_device_keys WHERE device_id = $1", device_id)
    await conn.execute("DELETE FROM st_devices WHERE device_id = $1", device_id)

    # Align with deploy scripts: include an HMAC secret for idempotency/HMAC tests.
    hmac_secret = secrets.token_bytes(32)

    await conn.execute(
        """
        INSERT INTO st_devices (
            device_id, tenant_id, space_id, mls_group_id, provisioned_ts, hmac_secret
        )
        VALUES ($1, $2, $3, 'mls-group-1', $4, $5)
        """,
        device_id,
        tenant_id,
        space_id,
        now,
        hmac_secret,
    )

    await conn.execute(
        """
        INSERT INTO st_device_keys (
            device_id, key_version, verify_key, key_state, registered_ts, activated_ts
        )
        VALUES ($1, '1', $2, 'ACTIVE', $3, $3)
        """,
        device_id,
        verify_key_b64url,
        now,
    )

    await conn.execute(
        """
        INSERT INTO schema_registry (schema_uri, version, sha256, status)
        VALUES ($1, $2, $3, 'ACTIVE')
        ON CONFLICT (schema_uri, version) DO NOTHING
        """,
        schema_uri,
        schema_version,
        schema_sha,
    )

    # Best-effort sanity check: ensure the join the kernel uses will succeed.
    row = await conn.fetchrow(
        """
        SELECT d.device_id, d.tenant_id, d.space_id, k.key_version, k.verify_key, k.key_state
        FROM st_devices d
        JOIN st_device_keys k ON d.device_id = k.device_id
        WHERE d.device_id = $1
        """,
        device_id,
    )
    if row is None:
        raise RuntimeError("Provisioning verification failed: device/key join returned no rows")


def _build_signed_envelope(
    *,
    body: dict[str, Any],
    tenant_id: str,
    space_id: str,
    device_id: str,
    actor: str,
    topic: str,
    schema_uri: str,
    schema_version: str,
    policy_version: str,
    roles: list[str],
    trace_id: str | None,
    signing_key: SigningKey,
) -> tuple[dict[str, Any], str]:
    """Build a V1 envelope and return (envelope, cognitive_trace_id)."""

    _ensure_repo_root_on_path()

    from k0.security import (
        canonical_envelope,
        canonical_json,
        compute_envelope_sha256,
        hash_payload,
    )
    from k0.security.crypto import encode_base64url

    if trace_id is None:
        trace_id = str(uuid.uuid4())

    body_json = canonical_json(body)
    body_bytes = body_json.encode("utf-8")
    payload_hash = hash_payload(body_bytes)

    envelope: dict[str, Any] = {
        "cognitive_trace_id": trace_id,
        "tenant_id": tenant_id,
        "space_id": space_id,
        "topic": topic,
        "schema_uri": schema_uri,
        "schema_version": schema_version,
        "actor": actor,
        "device_id": device_id,
        "band": "GREEN",
        "policy_version": policy_version,
        "ts": _utc_iso(),
        "payload_sha256": payload_hash,
        "sig_alg": "Ed25519SHA512",
        "sig_kid": f"{device_id}#1",
        "body": body,
        "policy": {"abac": {"roles": roles}},
    }

    envelope["envelope_sha256"] = compute_envelope_sha256(envelope)

    message = canonical_envelope(envelope)
    envelope["sig"] = encode_base64url(signing_key.sign(message).signature)

    return envelope, trace_id


async def _submit_envelope(
    client: httpx.AsyncClient, base_url: str, envelope: dict[str, Any]
) -> dict:
    url = f"{base_url}/k0/command.submit"
    resp = await client.post(url, json=envelope)
    if resp.status_code != 200:
        raise RuntimeError(f"command.submit failed ({resp.status_code}): {resp.text}")
    return resp.json()


async def _trigger_p03(
    client: httpx.AsyncClient,
    base_url: str,
    *,
    tenant_id: str,
    space_id: str,
    batch_size: int,
    reason: str,
) -> dict:
    url = f"{base_url}/k0/admin/pipelines/P03_CONSOLIDATION/trigger"
    payload = {
        "reason": reason,
        "options": {"tenant_id": tenant_id, "space_id": space_id, "batch_size": batch_size},
    }
    resp = await client.post(url, json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"P03 trigger failed ({resp.status_code}): {resp.text}")
    return resp.json()


async def _get_scheduler_status(client: httpx.AsyncClient, base_url: str) -> dict:
    url = f"{base_url}/k0/admin/scheduler/status"
    resp = await client.get(url)
    if resp.status_code != 200:
        raise RuntimeError(f"scheduler status failed ({resp.status_code}): {resp.text}")
    return resp.json()


async def _wait_for_hipp_event(
    conn: asyncpg.Connection,
    *,
    tenant_id: str,
    space_id: str,
    cognitive_trace_id: str,
    watch: WatchConfig,
) -> asyncpg.Record:
    deadline = time.time() + watch.timeout_s

    sql = """
        SELECT event_id, wal_pos, topic, event_time_utc, ingested_at, text, embedding_status, embedding_id
        FROM st_hipp_events
        WHERE tenant_id = $1
          AND space_id = $2
          AND cognitive_trace_id = $3
        ORDER BY ingested_at DESC
        LIMIT 1
    """

    while time.time() < deadline:
        row = await conn.fetchrow(sql, tenant_id, space_id, cognitive_trace_id)
        if row is not None:
            return row
        await asyncio.sleep(watch.poll_interval_s)

    raise TimeoutError("Timed out waiting for st_hipp_events row for cognitive_trace_id")


async def _poll_embedding(
    conn: asyncpg.Connection,
    *,
    tenant_id: str,
    space_id: str,
    event_id: str,
    watch: WatchConfig,
) -> None:
    """Poll st_vec / embedding readiness until timeout.

    This is best-effort: if embedding workers are not running, st_vec may not appear.
    """

    deadline = time.time() + watch.timeout_s
    last_status: str | None = None

    sql = """
        SELECT embedding_id, status, created_at, updated_at, indexed_at
        FROM st_vec
        WHERE tenant_id = $1 AND space_id = $2 AND event_id = $3
        ORDER BY created_at DESC
        LIMIT 1
    """

    while time.time() < deadline:
        row = await conn.fetchrow(sql, tenant_id, space_id, event_id)
        if row is None:
            await asyncio.sleep(watch.poll_interval_s)
            continue

        status = str(row["status"])
        if status != last_status:
            print(
                "embedding: "
                f"status={status} embedding_id={row['embedding_id']} created_at={row['created_at']}"
            )
            last_status = status

        if status in {"READY", "INDEXED"}:
            return

        await asyncio.sleep(watch.poll_interval_s)


async def _fetch_truth_summary(
    conn: asyncpg.Connection,
    *,
    layer: str,
    record_id: str,
) -> str | None:
    """Fetch a compact summary string for a truth-layer record."""

    try:
        if layer == "st_epi":
            row = await conn.fetchrow(
                "SELECT episode_summary, episode_type FROM st_epi WHERE episode_id = $1",
                record_id,
            )
            if row:
                return f"episode={row['episode_summary']} type={row['episode_type']}"

        if layer == "st_sem":
            row = await conn.fetchrow(
                "SELECT pattern_name, pattern_type FROM st_sem WHERE pattern_id = $1",
                record_id,
            )
            if row:
                return f"pattern={row['pattern_name']} type={row['pattern_type']}"

        if layer == "st_kg_dom":
            row = await conn.fetchrow(
                "SELECT canonical_name, entity_type FROM st_kg_dom WHERE entity_id = $1",
                record_id,
            )
            if row:
                return f"entity={row['canonical_name']} type={row['entity_type']}"

        if layer == "st_kg_edges":
            row = await conn.fetchrow(
                """
                SELECT e.relation_type,
                       s.canonical_name AS source_name,
                       t.canonical_name AS target_name
                FROM st_kg_edges e
                LEFT JOIN st_kg_dom s ON s.entity_id = e.source_entity_id
                LEFT JOIN st_kg_dom t ON t.entity_id = e.target_entity_id
                WHERE e.edge_id = $1
                """,
                record_id,
            )
            if row:
                src = row["source_name"] or "?"
                tgt = row["target_name"] or "?"
                return f"edge={src} -[{row['relation_type']}]-> {tgt}"

        if layer == "st_social":
            row = await conn.fetchrow(
                """
                SELECT relationship_label, relationship_type
                FROM st_social
                WHERE relationship_id = $1
                """,
                record_id,
            )
            if row:
                return f"relationship={row['relationship_label']} type={row['relationship_type']}"

        if layer == "st_prospective":
            row = await conn.fetchrow(
                """
                SELECT intention_type, intention_description, status
                FROM st_prospective
                WHERE intention_id = $1
                """,
                record_id,
            )
            if row:
                return (
                    f"intention={row['intention_description']} "
                    f"type={row['intention_type']} status={row['status']}"
                )

    except Exception:
        # Best-effort; keep watcher resilient.
        return None

    return None


async def _poll_observations(
    conn: asyncpg.Connection,
    *,
    tenant_id: str,
    source_event_id: str,
    since_ms: int,
    watch: WatchConfig,
) -> None:
    deadline = time.time() + watch.timeout_s
    seen: set[str] = set()

    sql = """
        SELECT observation_id, layer, record_id, observation_type, observed_at, source_event_id,
               sentiment_score, dominant_emotion
        FROM st_observations
        WHERE tenant_id = $1
          AND observed_at >= $3
          AND (source_event_id = $2 OR source_event_id IS NULL)
        ORDER BY observed_at ASC
        LIMIT $4
    """

    while time.time() < deadline:
        rows = await conn.fetch(sql, tenant_id, source_event_id, since_ms, watch.tail_limit)
        for row in rows:
            obs_id = str(row["observation_id"])
            if obs_id in seen:
                continue
            seen.add(obs_id)

            layer = str(row["layer"])
            record_id = str(row["record_id"])
            obs_type = str(row["observation_type"])
            observed_at = int(row["observed_at"])
            src_event = row["source_event_id"]
            src_part = f" source_event_id={src_event}" if src_event else " source_event_id=NULL"

            summary = await _fetch_truth_summary(conn, layer=layer, record_id=record_id)
            suffix = f" summary={summary}" if summary else ""

            sent = row["sentiment_score"]
            emo = row["dominant_emotion"]
            sent_part = f" sentiment={sent:.3f}" if sent is not None else ""
            emo_part = f" emotion={emo}" if emo else ""

            print(
                "observation: "
                f"layer={layer} type={obs_type} record_id={record_id} observed_at={observed_at}"
                f"{src_part}{sent_part}{emo_part}{suffix}"
            )

        await asyncio.sleep(watch.poll_interval_s)


def _parse_args(argv: Iterable[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(add_help=True)

    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--body-file", help="JSON body file (or '-' for stdin)")
    src.add_argument("--envelope-file", help="Full envelope JSON file (or '-' for stdin)")

    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--pg-dsn", default=os.getenv("K0_PG_DSN", DEFAULT_PG_DSN))

    p.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    p.add_argument("--space-id", default=DEFAULT_SPACE_ID)
    p.add_argument("--device-id", default=DEFAULT_DEVICE_ID)
    p.add_argument("--actor", default=DEFAULT_ACTOR)

    p.add_argument("--topic", default=DEFAULT_TOPIC)
    p.add_argument("--schema-uri", default=DEFAULT_SCHEMA_URI)
    p.add_argument("--schema-version", default=DEFAULT_SCHEMA_VERSION)
    p.add_argument("--policy-version", default=DEFAULT_POLICY_VERSION)

    p.add_argument(
        "--roles",
        default="guest",
        help="Comma-separated ABAC roles placed into envelope.policy.abac.roles",
    )

    p.add_argument(
        "--signing-key",
        default=os.getenv("K0_DEVICE_SIGNING_KEY"),
        help=(
            "Device signing key material (hex/base64/base64url). "
            "If omitted, a new random key is generated."
        ),
    )

    p.add_argument(
        "--trace-id",
        default=None,
        help="Optional cognitive_trace_id to use when building an envelope",
    )

    p.add_argument(
        "--provision-device",
        action="store_true",
        help="Provision device key in Postgres before submitting (destructive for device_id)",
    )

    p.add_argument("--trigger-p03", action="store_true", help="Trigger P03 after submission")
    p.add_argument(
        "--p03-batch-size",
        type=int,
        default=100,
        help="Batch size used when triggering P03",
    )
    p.add_argument(
        "--p03-reason",
        default="submit_envelope_live",
        help="Reason string used when triggering P03",
    )

    p.add_argument("--watch", action="store_true", help="Watch Postgres for downstream writes")
    p.add_argument("--timeout-s", type=float, default=60.0)
    p.add_argument("--poll-interval-s", type=float, default=0.5)
    p.add_argument("--tail-limit", type=int, default=200)

    return p.parse_args(list(argv))


async def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    watch_start_ms = _now_unix_ms()

    # If the kernel has previously looked up this device_id, it may have cached
    # keys (including an empty result or an older verify_key). Because this CLI
    # provisions by writing directly to Postgres (bypassing kernel cache
    # invalidation hooks), repeated runs with the same device_id can yield
    # INVALID_SIGNATURE even when the DB is correct.
    #
    # To keep this tool "just works" for live debugging, auto-randomize the
    # default device id when provisioning.
    if args.provision_device and args.device_id == DEFAULT_DEVICE_ID:
        suffix = uuid.uuid4().hex[:8]
        args.device_id = f"{DEFAULT_DEVICE_ID}-{suffix}"
        print(f"provision: using fresh device_id={args.device_id}")

    roles = [r.strip() for r in str(args.roles).split(",") if r.strip()]

    envelope: dict[str, Any]
    cognitive_trace_id: str

    if args.envelope_file:
        envelope_obj = _load_json(args.envelope_file)
        if not isinstance(envelope_obj, dict):
            raise ValueError("Envelope JSON must be an object")
        envelope = envelope_obj
        cognitive_trace_id = str(envelope.get("cognitive_trace_id") or "")
        if not cognitive_trace_id:
            raise ValueError("Envelope missing cognitive_trace_id")
    else:
        body_obj = _load_json(args.body_file)
        if not isinstance(body_obj, dict):
            raise ValueError("Body JSON must be an object")

        signing_key = _signing_key_from_args(args)

        _ensure_repo_root_on_path()
        from k0.security.crypto import encode_base64url

        verify_key_b64url = encode_base64url(signing_key.verify_key.encode())

        if args.provision_device:
            conn = await asyncpg.connect(args.pg_dsn)
            try:
                print(
                    "provision: "
                    f"device_id={args.device_id} tenant_id={args.tenant_id} space_id={args.space_id}"
                )
                await _provision_device(
                    conn,
                    tenant_id=args.tenant_id,
                    space_id=args.space_id,
                    device_id=args.device_id,
                    verify_key_b64url=verify_key_b64url,
                    schema_uri=args.schema_uri,
                    schema_version=args.schema_version,
                )
                print("provision: ok")
            finally:
                await conn.close()

        envelope, cognitive_trace_id = _build_signed_envelope(
            body=body_obj,
            tenant_id=args.tenant_id,
            space_id=args.space_id,
            device_id=args.device_id,
            actor=args.actor,
            topic=args.topic,
            schema_uri=args.schema_uri,
            schema_version=args.schema_version,
            policy_version=args.policy_version,
            roles=roles,
            trace_id=args.trace_id,
            signing_key=signing_key,
        )

    print(f"submit: cognitive_trace_id={cognitive_trace_id}")

    watch_cfg = WatchConfig(
        poll_interval_s=float(args.poll_interval_s),
        timeout_s=float(args.timeout_s),
        tail_limit=int(args.tail_limit),
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        submit_result = await _submit_envelope(client, args.base_url, envelope)
        print(
            "submit: ok "
            f"receipt_id={submit_result.get('receipt_id')} "
            f"commit_ts={submit_result.get('commit_ts')}"
        )

        # Consolidation (P03) produces most truth-layer writes and therefore most
        # st_observations rows. In a dev Docker setup, P03 may not be scheduled
        # frequently, so when the user is watching live, we auto-trigger it.
        if args.watch and not args.trigger_p03:
            args.trigger_p03 = True
            print("p03: auto-trigger enabled (because --watch was set)")

        if args.trigger_p03:
            before = await _get_scheduler_status(client, args.base_url)
            before_exec = {
                p["pipeline_id"]: p.get("execution_count") for p in before.get("pipelines", [])
            }

            trigger_result = await _trigger_p03(
                client,
                args.base_url,
                tenant_id=args.tenant_id,
                space_id=args.space_id,
                batch_size=int(args.p03_batch_size),
                reason=str(args.p03_reason),
            )
            print(f"p03: trigger ok result={trigger_result}")

            after = await _get_scheduler_status(client, args.base_url)
            after_exec = {
                p["pipeline_id"]: p.get("execution_count") for p in after.get("pipelines", [])
            }
            if before_exec != after_exec:
                print(f"scheduler: execution_count changed {before_exec} -> {after_exec}")

    if not args.watch:
        return 0

    # Note: asyncpg connections cannot be used concurrently for multiple queries.
    # Use one connection to find the event, then separate connections for the
    # concurrent pollers.
    conn_main = await asyncpg.connect(args.pg_dsn)
    try:
        hipp = await _wait_for_hipp_event(
            conn_main,
            tenant_id=args.tenant_id,
            space_id=args.space_id,
            cognitive_trace_id=cognitive_trace_id,
            watch=watch_cfg,
        )
        event_id = str(hipp["event_id"])
        print(
            "hipp_event: "
            f"event_id={event_id} wal_pos={hipp['wal_pos']} topic={hipp['topic']} "
            f"embedding_status={hipp['embedding_status']}"
        )
    finally:
        await conn_main.close()

    conn_embed = await asyncpg.connect(args.pg_dsn)
    conn_obs = await asyncpg.connect(args.pg_dsn)
    try:
        await asyncio.gather(
            _poll_embedding(
                conn_embed,
                tenant_id=args.tenant_id,
                space_id=args.space_id,
                event_id=event_id,
                watch=watch_cfg,
            ),
            _poll_observations(
                conn_obs,
                tenant_id=args.tenant_id,
                source_event_id=event_id,
                since_ms=watch_start_ms,
                watch=watch_cfg,
            ),
        )
    finally:
        await conn_embed.close()
        await conn_obs.close()

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main(sys.argv[1:])))
    except KeyboardInterrupt:
        # Keep the tool pleasant to use during live watching.
        raise SystemExit(0)
