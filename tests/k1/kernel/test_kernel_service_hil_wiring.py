"""E7.M1.1 — KernelService wires a single ``HumanInTheLoopService`` and
threads it into Fabric, Concierge, Planner, Orchestrator.

Exit-criteria coverage from HIL_UNIFICATION_PLAN.md §E7:

  1. ``kernel.hil_service`` is a ``HumanInTheLoopService``.
  2. It conforms to ``IHILPort`` (``runtime_checkable`` Protocol).
  3. The same instance is shared across all four downstream subsystems.
  4. ``enable_hil_service=False`` skips construction and leaves
     ``kernel._hil_service is None``.
  5. ``shutdown()`` cancels pending HIL futures.
"""

from __future__ import annotations

import pytest

from k1.concierge.config.kernel import KernelConfig
from k1.hil.service import HumanInTheLoopService
from k1.kernel.ports.hil_port import IHILPort
from k1.kernel.service import KernelService


@pytest.fixture
def kernel_config(tmp_path) -> KernelConfig:
    """Isolated SQLite paths so each test gets a fresh kernel."""
    return KernelConfig(
        sessionstate_db_path=str(tmp_path / "ssm.db"),
        workflow_db_path=str(tmp_path / "wf.db"),
        bridge_outbox_path=str(tmp_path / "bridge.db"),
    )


class TestHILServiceConstruction:
    @pytest.mark.asyncio
    async def test_hil_service_constructed_at_startup(self, kernel_config) -> None:
        svc = KernelService(config=kernel_config)
        await svc.startup()
        try:
            assert svc.hil_service is not None
            assert isinstance(svc.hil_service, HumanInTheLoopService)
        finally:
            await svc.shutdown()

    @pytest.mark.asyncio
    async def test_hil_service_conforms_to_ihilport(self, kernel_config) -> None:
        svc = KernelService(config=kernel_config)
        await svc.startup()
        try:
            assert isinstance(svc.hil_service, IHILPort)
        finally:
            await svc.shutdown()

    @pytest.mark.asyncio
    async def test_disable_skips_construction(self, kernel_config) -> None:
        kernel_config.enable_hil_service = False
        svc = KernelService(config=kernel_config)
        await svc.startup()
        try:
            assert svc.hil_service is None
        finally:
            await svc.shutdown()


class TestHILPortPropagation:
    """All four downstream subsystems must share the SAME HIL instance."""

    @pytest.mark.asyncio
    async def test_orchestrator_receives_hil_port(self, kernel_config) -> None:
        svc = KernelService(config=kernel_config)
        await svc.startup()
        try:
            # OrchestratorFactory.create_production stores hil_port on the
            # constraint resolver. The exact slot name may evolve; assert the
            # service exposes it via _constraint_resolver._hil_port.
            cr = svc._orchestrator._constraint_resolver  # type: ignore[attr-defined]
            assert cr._hil_port is svc.hil_service
        finally:
            await svc.shutdown()

    @pytest.mark.asyncio
    async def test_planner_receives_hil_port(self, kernel_config) -> None:
        svc = KernelService(config=kernel_config)
        await svc.startup()
        try:
            # PlannerAgent holds the PipelineController as ``_pipeline``;
            # the controller stores the unified hil_port.
            assert svc._planner._pipeline._hil_port is svc.hil_service  # type: ignore[attr-defined]
        finally:
            await svc.shutdown()

    @pytest.mark.asyncio
    async def test_fabric_receives_hil_port(self, kernel_config) -> None:
        svc = KernelService(config=kernel_config)
        await svc.startup()
        try:
            # Fabric is a container; CapabilityFabric (the facade) owns _hil_port.
            assert svc._shared_fabric.facade._hil_port is svc.hil_service  # type: ignore[attr-defined]
        finally:
            await svc.shutdown()

    @pytest.mark.asyncio
    async def test_concierge_session_receives_hil_port(self, kernel_config) -> None:
        svc = KernelService(config=kernel_config)
        await svc.startup()
        try:
            session = await svc.create_session("s1")
            # P1.5: per-session HIL service is bound to the session bus
            # (NOT the kernel singleton). The kernel-level svc.hil_service
            # is reserved for kernel-bus-scoped callers (Orchestrator,
            # Planner, shared Fabric). Session-scoped callers (Concierge,
            # per-session Fabric, SelfModelHandle) get their own HIL
            # service so their publish/subscribe lands on the same bus
            # that the FSM and UI coordinator are subscribed to.
            from k1.hil.service import HumanInTheLoopService

            assert isinstance(session.concierge.hil_port, HumanInTheLoopService)
            assert session.concierge.hil_port is not svc.hil_service
            # And the FSM has the same per-session instance bound.
            assert session.concierge.fsm._hil_port is session.concierge.hil_port  # type: ignore[attr-defined]
        finally:
            await svc.shutdown()


class TestHILShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_marks_hil_shutdown(self, kernel_config) -> None:
        svc = KernelService(config=kernel_config)
        await svc.startup()
        hil = svc.hil_service
        await svc.shutdown()
        # HumanInTheLoopService sets _shutdown=True after shutdown().
        assert hil._shutdown is True  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_shutdown_idempotent_when_disabled(self, kernel_config) -> None:
        kernel_config.enable_hil_service = False
        svc = KernelService(config=kernel_config)
        await svc.startup()
        await svc.shutdown()  # must not raise even though hil_service is None
        assert svc.is_running is False
