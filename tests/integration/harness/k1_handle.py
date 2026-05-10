"""K1 handle for the live-system harness.

A ``K1Handle`` represents one running K1 process *plus* an in-process
bridge surface that the harness uses to drive the live K0 with that
K1's person/device identity.

Why both? In Epic 7.1 the test goal is "a real K1 OS process is up,
healthy, holds resources, and shuts down cleanly under SIGTERM" while
also being able to round-trip a ``memory.write.v1`` against the live
Docker K0. K1's runner does not yet expose a remote test-control API,
so the harness drives K0 directly via an in-process
:class:`bridge.runtime.BridgeRuntime` configured to point at the same
live K0 the subprocess talks to. This keeps the K0 side fully real
(no mocks) while preserving subprocess isolation for K1 lifecycle
testing — a true subprocess-driven publish API can be layered in a
later PR without changing the harness contract.
"""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .family_layout import DeviceSpec, FamilyLayout, PersonSpec
from .process_supervisor import ProcessHandle, ProcessSupervisor

logger = logging.getLogger(__name__)


@dataclass
class K1Handle:
    person: PersonSpec
    device: DeviceSpec
    family: FamilyLayout
    process: ProcessHandle
    workdir: Path
    test_api_port: int  # reserved for future K1 test control API
    k0_base_url: str
    hmac_secret: bytes | None = None
    signing_seed: bytes | None = None
    started_at: float = field(default_factory=time.monotonic)
    _bridge_runtime: Any = field(default=None, repr=False)

    # -- identity ---------------------------------------------------------
    @property
    def pid(self) -> int:
        return self.process.pid

    @property
    def person_id(self) -> str:
        return self.person.person_id

    @property
    def device_id(self) -> str:
        return self.device.device_id

    @property
    def is_alive(self) -> bool:
        return self.process.is_alive()

    # -- bridge surface (in-process, points at the *live* K0) -------------
    def bridge_runtime(self) -> Any:
        """Return a lazily constructed in-process BridgeRuntime.

        The runtime is wired in K1 role and points at the same K0
        ``base_url`` the subprocess would use. This is the seam tests use
        to publish ``memory.write.v1`` and drive ``query.recall`` against
        the live Docker K0.
        """
        if self._bridge_runtime is None:
            self._bridge_runtime = _build_k1_bridge_runtime(
                self.k0_base_url,
                person_id=self.person.person_id,
                device_id=self.device.device_id,
                family_id=self.family.family_id,
                hmac_secret=self.hmac_secret,
                signing_seed=self.signing_seed,
            )
        return self._bridge_runtime

    # -- health -----------------------------------------------------------
    def health(self) -> dict[str, Any]:
        """Coarse health: subprocess alive + K0 reachable."""
        return {
            "process_alive": self.is_alive,
            "pid": self.pid,
            "person_id": self.person_id,
            "device_id": self.device_id,
            "k0_reachable": _k0_reachable(self.k0_base_url),
        }

    # -- envelope publishing (real K0 over HTTP) --------------------------
    async def publish_memory_write_v1(
        self,
        *,
        text: str,
        topics: list[str] | None = None,
        sentiment_label: str = "neutral",
        affect: dict[str, float] | None = None,
        source_type: str = "user_stated",
        novelty: str = "NOVEL",
        elaboration_depth: str = "MENTION",
        temporal_orientation: str = "ONGOING",
        confidence: float = 0.9,
        conversation_turn: int = 1,
        language: str = "en",
        session_id: str | None = None,
        trace_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Publish a ``memory.write.v1`` envelope to the live K0.

        Builds a fully-validated :class:`MemoryWriteV1` Pydantic body
        (the contract defines ``extra: forbid``, so callers must pass
        only declared fields), ships it through this K1's
        :class:`BridgeRuntime` over real HTTP to the running K0, and
        returns the parsed K0 response body. ``trace_id`` lives in the
        envelope, not the body — pass it through ``extra`` only if you
        intentionally want to overflow the schema.
        """
        from bridge._generated.k1.models.memory_write_v1 import (
            MemoryWriteV1,
        )

        body: dict[str, Any] = {
            "schema_version": "2.2",
            "operation": "UPSERT",
            "text": text,
            "topics": topics or ["integration"],
            "sentiment_label": sentiment_label,
            "affect": affect or {"valence": 0.5, "arousal": 0.4, "dominance": 0.5},
            "source_type": source_type,
            "novelty": novelty,
            "elaboration_depth": elaboration_depth,
            "temporal_orientation": temporal_orientation,
            "confidence": confidence,
            "conversation_turn": conversation_turn,
            "language": language,
            "session_id": session_id or f"sess-{self.person_id}",
        }
        if extra:
            body.update(extra)

        payload = MemoryWriteV1.model_validate(body)
        runtime = self.bridge_runtime()
        # The envelope's trace_id is set by the transport layer; we expose
        # it here in case future iterations propagate it through.
        _ = trace_id
        return await runtime.client.memory_write_v1.publish(payload)

    async def publish_memory_write_v1_native(
        self,
        *,
        text: str,
        topics: list[str] | None = None,
        sentiment_label: str = "neutral",
        affect: dict[str, float] | None = None,
        source_type: str = "user_stated",
        novelty: str = "NOVEL",
        elaboration_depth: str = "MENTION",
        temporal_orientation: str = "ONGOING",
        confidence: float = 0.9,
        conversation_turn: int = 1,
        language: str = "en",
        session_id: str | None = None,
        space_id: str | None = None,
        tenant_id: str | None = None,
        actor: str | None = None,
        band: str = "GREEN",
        topic: str = "memory.write",
        schema_uri: str = "schema://k0/topics/memory_write.body.json",
        schema_version: str = "2.2",
        policy_version: str = "2025-09-28",
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ship a ``memory.write`` envelope using K0's own wire helpers.

        This bypasses the bridge ``EnvelopeBuilder`` and follows the
        proven pattern from ``k0/deploy/scripts/events/family_life_events.py``
        and ``k0/deploy/scripts/provisioning/provision_and_submit.py``: the
        canonical hash and signature use the *exact* same K0-side helpers,
        which guarantees round-trip parity with the kernel gate. The bridge
        envelope_builder has known divergences (sig_alg label, idem_key
        formula, kid format) that are tracked separately; this method
        gives Epic 7.1/7.2/7.3 a real happy-path channel without that
        rewrite blocking us.

        Returns the parsed JSON response from ``POST /k0/command.submit``.
        """
        import json
        import uuid
        from datetime import datetime, timezone

        import httpx
        from nacl.signing import SigningKey

        from k0.security import (
            canonical_envelope,
            canonical_json,
            compute_envelope_sha256,
            hash_payload,
        )
        from k0.security.crypto import encode_base64url

        if self.signing_seed is None:
            raise RuntimeError(
                "publish_memory_write_v1_native requires an Ed25519 signing seed; "
                "spawn this K1 with provisioned secrets via LiveSystem."
            )

        body: dict[str, Any] = {
            "schema_version": "2.2",
            "operation": "UPSERT",
            "text": text,
            "topics": topics or ["integration"],
            "sentiment_label": sentiment_label,
            "affect": affect or {"valence": 0.5, "arousal": 0.4, "dominance": 0.5},
            "source_type": source_type,
            "novelty": novelty,
            "elaboration_depth": elaboration_depth,
            "temporal_orientation": temporal_orientation,
            "confidence": confidence,
            "conversation_turn": conversation_turn,
            "language": language,
            "session_id": session_id or f"sess-{self.person_id}",
        }
        if extra_body:
            body.update(extra_body)

        body_bytes = canonical_json(body).encode("utf-8")
        payload_sha256 = hash_payload(body_bytes)

        envelope: dict[str, Any] = {
            "cognitive_trace_id": str(uuid.uuid4()),
            "tenant_id": tenant_id or self.family.family_id,
            "space_id": space_id or self.family.family_id,
            "topic": topic,
            "schema_uri": schema_uri,
            "schema_version": schema_version,
            "actor": actor or self.person_id,
            "device_id": self.device_id,
            "band": band,
            "policy_version": policy_version,
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "payload_sha256": payload_sha256,
            "sig_alg": "Ed25519SHA512",
            "sig_kid": f"{self.device_id}#1",
            "body": body,
            "policy": {"abac": {"roles": ["guest"]}},
        }
        envelope["envelope_sha256"] = compute_envelope_sha256(envelope)
        signing_key = SigningKey(self.signing_seed)
        envelope["sig"] = encode_base64url(signing_key.sign(canonical_envelope(envelope)).signature)

        url = f"{self.k0_base_url.rstrip('/')}/k0/command.submit"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                content=json.dumps(envelope).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
        try:
            data = response.json()
        except Exception:  # noqa: BLE001
            data = {"raw_text": response.text}
        return {
            "http_status": response.status_code,
            "body": data,
            "envelope_sha256": envelope["envelope_sha256"],
            "cognitive_trace_id": envelope["cognitive_trace_id"],
        }

    async def recall_request_v1(
        self,
        *,
        selectors: list[dict[str, Any]] | None = None,
        space_id: str | None = None,
        tenant_id: str | None = None,
        max_results: int = 8,
        max_latency_ms: int = 200,
        trace_id: str | None = None,
    ) -> Any:
        """Issue a ``recall.request.v1`` query against the live K0."""
        from bridge._generated.k1.models.recall_request_v1 import (
            RecallRequestV1,
        )

        body: dict[str, Any] = {
            "selectors": selectors
            or [
                {"type": "semantic", "topic": "integration", "limit": 5, "query": "*"},
            ],
            "space_id": space_id or self.family.family_id,
            "tenant_id": tenant_id or self.person_id,
            "max_results": max_results,
            "max_latency_ms": max_latency_ms,
            "fail_fast": False,
        }
        if trace_id is not None:
            body["trace_id"] = trace_id
        payload = RecallRequestV1.model_validate(body)
        runtime = self.bridge_runtime()
        return await runtime.query.recall_request_v1.request(payload)

    async def stop_bridge_runtime(self) -> None:
        """Tear down the lazily-built bridge runtime if any."""
        if self._bridge_runtime is not None:
            try:
                await self._bridge_runtime.stop()
            except Exception:  # noqa: BLE001 - defensive teardown
                logger.exception("k1_handle.stop_bridge_runtime failed")
            self._bridge_runtime = None

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def k1_runner_argv() -> list[str]:
        return [sys.executable, "-m", "k1.kernel.runner", "--log-level", "WARNING"]


def _build_k1_bridge_runtime(
    k0_base_url: str,
    *,
    person_id: str,
    device_id: str,
    family_id: str,
    hmac_secret: bytes | None = None,
    signing_seed: bytes | None = None,
) -> Any:
    """Wire a K1-role BridgeRuntime against the live K0.

    Imports are deferred so the harness module is importable even in
    environments where the bridge package's heavier dependencies are
    not installed (e.g. tooling-only checks). The transport is given a
    real :class:`EnvelopeBuilder` so generated clients can build & sign
    envelopes — the runtime factory ``BridgeRuntime.from_registry`` does
    not inject one.

    K0's ``minimal_gate`` verifies envelope signatures with Ed25519 against
    ``st_device_keys.verify_key``, so we always prefer ``Ed25519Signing``
    when a ``signing_seed`` is provided. ``hmac_secret`` is unused for the
    signature path — K0 uses it only for HMAC-based idempotency derivation.
    """
    import os

    from bridge.core.envelope_builder import BridgeConfig, EnvelopeBuilder
    from bridge.core.signing import Ed25519Signing, HmacSigning
    from bridge.core.transport import HttpTransport, TransportConfig
    from bridge.runtime import BridgeRuntime, Role

    contracts_path = Path(__file__).resolve().parents[3] / "bridge" / "contracts"

    bridge_cfg = BridgeConfig(
        tenant_id=family_id,
        space_id=family_id,
        device_id=device_id,
        actor=person_id,
    )
    if signing_seed is not None:
        signer = Ed25519Signing(
            signing_key_bytes=signing_seed,
            key_id=f"{device_id}#1",
        )
    else:
        signer = HmacSigning(
            secret=hmac_secret if hmac_secret is not None else os.urandom(32),
            key_id=f"{device_id}#hmac",
        )
    envelope_builder = EnvelopeBuilder(config=bridge_cfg, signer=signer)
    transport = HttpTransport(
        TransportConfig(base_url=k0_base_url),
        envelope_builder=envelope_builder,
    )
    return BridgeRuntime.from_registry(
        contracts_path=contracts_path, role=Role.K1, transport=transport
    )


def _k0_reachable(base_url: str) -> bool:
    try:
        with httpx.Client(timeout=1.0) as client:
            r = client.get(f"{base_url}/healthz")
            return r.status_code == 200
    except httpx.HTTPError:
        return False


def spawn_k1(
    *,
    person: PersonSpec,
    device: DeviceSpec,
    family: FamilyLayout,
    supervisor: ProcessSupervisor,
    workdir: Path,
    k0_base_url: str,
    test_api_port: int,
    extra_env: dict[str, str] | None = None,
    hmac_secret: bytes | None = None,
    signing_seed: bytes | None = None,
) -> K1Handle:
    """Spawn one K1 subprocess and wrap it in a :class:`K1Handle`."""
    workdir.mkdir(parents=True, exist_ok=True)
    log_path = workdir / "k1.log"

    env: dict[str, str] = {
        "K0_BASE_URL": k0_base_url,
        "K1_PERSON_ID": person.person_id,
        "K1_DEVICE_ID": device.device_id,
        "K1_FAMILY_ID": family.family_id,
        "K1_TEST_API_PORT": str(test_api_port),
        "PYTHONUNBUFFERED": "1",
    }
    if extra_env:
        env.update(extra_env)

    handle = supervisor.spawn(
        name=f"k1[{person.role}:{person.person_id[:8]}]",
        argv=K1Handle.k1_runner_argv(),
        cwd=Path(__file__).resolve().parents[3],  # repo root
        env=env,
        log_path=log_path,
    )
    return K1Handle(
        person=person,
        device=device,
        family=family,
        process=handle,
        workdir=workdir,
        test_api_port=test_api_port,
        k0_base_url=k0_base_url,
        hmac_secret=hmac_secret,
        signing_seed=signing_seed,
    )
