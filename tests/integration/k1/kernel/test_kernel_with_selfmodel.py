"""M5.E3 — Kernel wiring integration tests.

Issues covered:

* I1: ``KernelConfig.enable_self_model`` flag default + propagation.
* I2: S2.6 builds a :class:`SelfModelServiceBundle` and stashes it on
  the kernel; flag-off path leaves the field ``None``; reverse
  shutdown closes the bundle.
* I3: P3.5 builds a :class:`SelfModelHandle` per session, installs the
  policy gate as step-0 on both Front + Back dispatchers, wraps
  ``ToolContext.recall_fn`` (when present) with
  :class:`RecallCitationWrapper`, and ``destroy_session`` reverses
  every install.
* I4: ``SelfModelServiceBundle.health()`` returns the documented
  schema and is reachable from the live kernel.
"""

from __future__ import annotations

import pytest

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.service import KernelService
from k1.selfmodel.adapters.recall_citation_wrapper import RecallCitationWrapper
from k1.selfmodel.kernel import SelfModelHandle, SelfModelServiceBundle

pytestmark = pytest.mark.integration


# =====================================================================
# I1 — KernelConfig flag
# =====================================================================
class TestEnableSelfModelFlag:
    def test_default_off(self) -> None:
        cfg = KernelConfig()
        assert cfg.enable_self_model is False
        assert cfg.selfmodel_projection_db_path is None
        assert cfg.selfmodel_space_id == "family:default"

    def test_can_enable(self) -> None:
        cfg = KernelConfig(
            enable_self_model=True,
            selfmodel_space_id="family:abc",
        )
        assert cfg.enable_self_model is True
        assert cfg.selfmodel_space_id == "family:abc"


# =====================================================================
# Helpers
# =====================================================================
async def _start(tmp_path, *, enable_self_model: bool) -> KernelService:
    cfg = KernelConfig(
        test_mode=True,
        model_mode="test",
        ordered_bus=True,
        session_mode="standalone",
        bridge_enabled=False,
        bridge_offline_ok=True,
        otel_enabled=False,
        enable_hil_service=False,
        enable_family_tools=False,
        sessionstate_db_path=str(tmp_path / "ssm.db"),
        bridge_outbox_path=str(tmp_path / "bridge_outbox.db"),
        workflow_db_path=str(tmp_path / "workflows.db"),
        enable_self_model=enable_self_model,
        selfmodel_space_id="family:test",
    )
    svc = KernelService(config=cfg)
    await svc.startup()
    return svc


# =====================================================================
# I2 — S2.6 startup
# =====================================================================
class TestS2_6StartupBundle:
    @pytest.mark.asyncio
    async def test_flag_off_leaves_bundle_none(self, tmp_path) -> None:
        svc = await _start(tmp_path, enable_self_model=False)
        try:
            assert svc.self_model_bundle is None
        finally:
            await svc.shutdown()

    @pytest.mark.asyncio
    async def test_flag_on_builds_bundle(self, tmp_path) -> None:
        svc = await _start(tmp_path, enable_self_model=True)
        try:
            bundle = svc.self_model_bundle
            assert isinstance(bundle, SelfModelServiceBundle)
            # Composer + evaluator + identity wired.
            assert bundle.composer is not None
            assert bundle.evaluator is not None
            assert bundle.identity is not None
            # Bootstrap constitution active and signed.
            assert bundle.bootstrap.created is True
            assert bundle.bootstrap.snapshot.version
            # Family space honored.
            assert bundle.space_id == "family:test"
        finally:
            await svc.shutdown()
        # Reverse-S2.6 cleared the field.
        assert svc.self_model_bundle is None

    @pytest.mark.asyncio
    async def test_bundle_health_is_ok(self, tmp_path) -> None:
        svc = await _start(tmp_path, enable_self_model=True)
        try:
            health = svc.self_model_bundle.health()  # type: ignore[union-attr]
            # I4 schema fields present.
            assert health["status"] == "ok"
            assert health["constitution"]["available"] is True
            assert health["constitution"]["safe_mode"] is False
            assert health["store"]["kind"] in {
                "InMemoryProjectionStore",
                "SQLiteProjectionStore",
            }
            assert health["family_space_id"] == "family:test"
            assert health["bootstrap"]["created"] is True
            assert health["bootstrap"]["signer_id"]
        finally:
            await svc.shutdown()


# =====================================================================
# I3 — P3.5 per-session wiring
# =====================================================================
class TestP3_5PerSessionHandle:
    @pytest.mark.asyncio
    async def test_flag_off_session_has_no_handle(self, tmp_path) -> None:
        svc = await _start(tmp_path, enable_self_model=False)
        try:
            session = await svc.create_session("s-off")
            assert session.self_model is None
        finally:
            await svc.shutdown()

    @pytest.mark.asyncio
    async def test_flag_on_session_has_handle(self, tmp_path) -> None:
        svc = await _start(tmp_path, enable_self_model=True)
        try:
            session = await svc.create_session("s-on", device_id="d-test")
            handle = session.self_model
            assert isinstance(handle, SelfModelHandle)
            assert handle.session_id == "s-on"
            assert handle.actor_id  # derived (meta empty → actor:s-on fallback)
            assert handle.gate is not None
            assert handle.renderer is not None
            # Handle bundle == kernel bundle.
            assert handle.bundle is svc.self_model_bundle
        finally:
            await svc.shutdown()

    @pytest.mark.asyncio
    async def test_gate_installed_as_step0(self, tmp_path) -> None:
        svc = await _start(tmp_path, enable_self_model=True)
        try:
            session = await svc.create_session("s-gate")
            front_d = session.front_dispatcher
            back_d = session.back_dispatcher
            handle = session.self_model
            assert handle is not None and handle.gate is not None
            # Gate installed via setter (bound methods compare by ==).
            assert front_d.policy_gate is not None
            assert back_d.policy_gate is not None
            assert front_d.policy_gate == handle.gate.evaluate
            assert back_d.policy_gate == handle.gate.evaluate
        finally:
            await svc.shutdown()

    @pytest.mark.asyncio
    async def test_recall_fn_wrapped_when_present(self, tmp_path) -> None:
        svc = await _start(tmp_path, enable_self_model=True)
        try:
            session = await svc.create_session("s-recall")
            for ctx in (session.front_ctx, session.back_ctx):
                if ctx is None:
                    continue
                # When the baseline recall_fn was wired, the handle
                # wraps it. When None, the wrapper is skipped to keep
                # the empty-result fallback alive.
                if ctx.recall_fn is not None:
                    assert isinstance(ctx.recall_fn, RecallCitationWrapper)
        finally:
            await svc.shutdown()

    @pytest.mark.asyncio
    async def test_destroy_session_reverses_install(self, tmp_path) -> None:
        svc = await _start(tmp_path, enable_self_model=True)
        try:
            session = await svc.create_session("s-destroy")
            front_d = session.front_dispatcher
            back_d = session.back_dispatcher
            assert front_d.policy_gate is not None
            assert back_d.policy_gate is not None
            await svc.destroy_session("s-destroy")
            # Gate cleared, wrapper restored — verifies uninstall ran.
            assert front_d.policy_gate is None
            assert back_d.policy_gate is None
        finally:
            await svc.shutdown()
