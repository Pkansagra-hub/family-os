"""Epic 7.3A.4 -- MCP re-discovery end-to-end integration tests.

Focus:
- Orchestrator reacts to Fabric health events through ConnectorLifecycleManager.
- Workflow executions are dispatched through OrchestratorService.process().
- Gap detection occurs when MCP-backed capability is unavailable.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any
from uuid import uuid4

import pytest

from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import (
    PlanStep,
    ProcessResult,
    RegistryEntry,
    TriggerSpec,
    TriggerType,
    WorkflowRunRequest,
)
from k1.orchestrator.workflows.workflow_types import WorkflowSpec


class _Transport:
    """Small MCP transport test double for discovery.list_tools()."""

    def __init__(self, tools_by_server: dict[str, list[dict[str, Any]]]) -> None:
        self.tools_by_server = tools_by_server

    async def list_tools(self, server) -> list[dict[str, Any]]:
        return self.tools_by_server.get(server.id, [])


async def _svc():
    service = await OrchestratorFactory.create_standalone()
    engine = service._workflow_engine
    return (
        service,
        service._fabric_port,
        service._delta_port,
        service._event_port,
        service._connector_lifecycle,
        engine.registry,
        engine,
        engine.registry._storage,
    )


def _write_yaml(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.write(fd, content.encode("utf-8"))
    os.close(fd)
    return path


def _entry(name: str) -> RegistryEntry:
    return RegistryEntry(
        name=name,
        provider_type="MCP",
        safety_band_min="GREEN",
        availability="AVAILABLE",
        estimated_duration_ms=100,
    )


def _spec(workflow_id: str, capability: str) -> WorkflowSpec:
    return WorkflowSpec(
        workflow_id=workflow_id,
        name=f"wf-{workflow_id}",
        source_plan_id=f"plan-{workflow_id}",
        version="1.0.0",
        trigger=TriggerSpec(type=TriggerType.MANUAL),
        steps=[PlanStep(id="s1", capability=capability)],
        dependencies={},
        active=True,
    )


def _run_req(workflow_id: str) -> WorkflowRunRequest:
    return WorkflowRunRequest(
        workflow_id=workflow_id,
        version="1.0.0",
        trigger_type=TriggerType.MANUAL,
        trace_id=str(uuid4()),
    )


def _wire_discovered_tools_into_mock_fabric(fabric, delta, *, start_index: int = 0) -> list[str]:
    """Apply missing registration wiring in tests.

    In production, Fabric consumes MCP discovery events and registers capabilities.
    Test adapters are decoupled, so this helper mirrors that wiring in test setup.
    """
    payloads = delta.get_emitted("k1.mcp.tool.discovered.v1")
    wired: list[str] = []
    for payload in payloads[start_index:]:
        capability_id = payload["capability_id"]
        fabric.register_capability(capability_id, _entry(capability_id))
        wired.append(capability_id)
    return wired


class TestMCPRediscoveryE2E:
    @pytest.mark.asyncio
    async def test_monitoring_subscribes_to_fabric_health_topic(self) -> None:
        _, _, _, event, lifecycle, _, _, _ = await _svc()

        lifecycle.start_lifecycle_monitoring()
        event.assert_subscribed("k1.fabric.provider.health.changed.v1")

    @pytest.mark.asyncio
    async def test_healthy_mcp_tool_registered_workflow_succeeds(self) -> None:
        service, fabric, delta, _, lifecycle, registry, _, _ = await _svc()

        path = _write_yaml(
            """servers:
  - id: calendar
    type: remote
    endpoint: http://calendar
"""
        )
        try:
            lifecycle._discovery._config_path = path  # type: ignore[attr-defined]
            lifecycle._discovery._transport = _Transport(  # type: ignore[attr-defined]
                {"calendar": [{"name": "create_event", "description": "Create calendar event"}]}
            )

            result = await lifecycle.discover_and_register()
            assert result.registered == 1
            wired = _wire_discovered_tools_into_mock_fabric(fabric, delta)
            assert wired
            cap_id = wired[-1]

            wf_id = "wf-mcp-healthy"
            await registry.save(_spec(wf_id, cap_id))

            run = await service.process(_run_req(wf_id))
            assert run == ProcessResult.COMPLETED
            fabric.assert_called(cap_id, times=1)
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_crash_event_simulated_by_health_degraded_transition(self) -> None:
        _, _, _, event, lifecycle, _, _, _ = await _svc()

        lifecycle.server_capabilities["calendar"] = ["tool.execute.calendar.create_event"]
        lifecycle.start_lifecycle_monitoring()
        event.fire(
            "k1.fabric.provider.health.changed.v1",
            {
                "provider_id": "mcp.calendar",
                "old_state": "HEALTHY",
                "new_state": "DEGRADED",
            },
        )

        # Recovery queue should remain empty on crash/degrade events.
        assert lifecycle.get_pending_refreshes() == []

    @pytest.mark.asyncio
    async def test_tool_unavailable_emits_gap_and_workflow_fails(self) -> None:
        service, fabric, delta, _, lifecycle, registry, _, _ = await _svc()

        path = _write_yaml(
            """servers:
  - id: calendar
    type: remote
    endpoint: http://calendar
"""
        )
        try:
            lifecycle._discovery._config_path = path  # type: ignore[attr-defined]
            lifecycle._discovery._transport = _Transport(  # type: ignore[attr-defined]
                {"calendar": [{"name": "create_event", "description": "Create calendar event"}]}
            )
            await lifecycle.discover_and_register()
            cap_id = _wire_discovered_tools_into_mock_fabric(fabric, delta)[-1]

            wf_id = "wf-mcp-gap"
            await registry.save(_spec(wf_id, cap_id))
            first = await service.process(_run_req(wf_id))
            assert first == ProcessResult.COMPLETED

            fabric.registry.pop(cap_id, None)
            gaps_before = len(delta.get_emitted("k1.orchestration.gap.detected"))
            second = await service.process(_run_req(wf_id))

            assert second == ProcessResult.FAILED
            assert len(delta.get_emitted("k1.orchestration.gap.detected")) > gaps_before
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_health_recovery_event_queues_refresh_for_server(self) -> None:
        _, _, _, event, lifecycle, _, _, _ = await _svc()

        lifecycle.server_capabilities["calendar"] = ["tool.execute.calendar.create_event"]
        lifecycle.start_lifecycle_monitoring()

        event.fire(
            "k1.fabric.provider.health.changed.v1",
            {
                "provider_id": "mcp.calendar",
                "old_state": "DEGRADED",
                "new_state": "HEALTHY",
            },
        )

        assert lifecycle.get_pending_refreshes() == ["calendar"]

    @pytest.mark.asyncio
    async def test_non_mcp_provider_recovery_is_ignored(self) -> None:
        _, _, _, event, lifecycle, _, _, _ = await _svc()

        lifecycle.server_capabilities["calendar"] = ["tool.execute.calendar.create_event"]
        lifecycle.start_lifecycle_monitoring()
        event.fire(
            "k1.fabric.provider.health.changed.v1",
            {
                "provider_id": "fabric-http-default",
                "old_state": "DEGRADED",
                "new_state": "HEALTHY",
            },
        )

        assert lifecycle.get_pending_refreshes() == []

    @pytest.mark.asyncio
    async def test_recovery_refresh_rediscovers_and_emits_registration(self) -> None:
        service, fabric, delta, _, lifecycle, _, _, _ = await _svc()

        path = _write_yaml(
            """servers:
  - id: calendar
    type: remote
    endpoint: http://calendar
"""
        )
        try:
            lifecycle._discovery._config_path = path  # type: ignore[attr-defined]
            lifecycle._discovery._transport = _Transport(  # type: ignore[attr-defined]
                {"calendar": [{"name": "create_event", "description": "Create calendar event"}]}
            )

            await lifecycle.discover_and_register()
            discovered_before = len(delta.get_emitted("k1.mcp.tool.discovered.v1"))

            refreshed = await lifecycle.refresh("calendar")
            assert refreshed.registered == 1
            assert len(delta.get_emitted("k1.mcp.tool.discovered.v1")) > discovered_before
            wired = _wire_discovered_tools_into_mock_fabric(
                fabric,
                delta,
                start_index=discovered_before,
            )
            assert wired
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_recovered_tool_allows_workflow_success_again(self) -> None:
        service, fabric, delta, event, lifecycle, registry, _, _ = await _svc()

        path = _write_yaml(
            """servers:
  - id: calendar
    type: remote
    endpoint: http://calendar
"""
        )
        try:
            lifecycle._discovery._config_path = path  # type: ignore[attr-defined]
            lifecycle._discovery._transport = _Transport(  # type: ignore[attr-defined]
                {"calendar": [{"name": "create_event", "description": "Create calendar event"}]}
            )

            await lifecycle.discover_and_register()
            cap_id = _wire_discovered_tools_into_mock_fabric(fabric, delta)[-1]

            wf_id = "wf-mcp-recovery"
            await registry.save(_spec(wf_id, cap_id))

            first = await service.process(_run_req(wf_id))
            assert first == ProcessResult.COMPLETED

            # Simulate outage.
            fabric.registry.pop(cap_id, None)
            failed = await service.process(_run_req(wf_id))
            assert failed == ProcessResult.FAILED

            # Simulate provider recovery event and refresh cycle.
            lifecycle.start_lifecycle_monitoring()
            event.fire(
                "k1.fabric.provider.health.changed.v1",
                {
                    "provider_id": "mcp.calendar",
                    "old_state": "DEGRADED",
                    "new_state": "HEALTHY",
                },
            )
            for server_id in lifecycle.get_pending_refreshes():
                before = len(delta.get_emitted("k1.mcp.tool.discovered.v1"))
                await lifecycle.refresh(server_id)
                _wire_discovered_tools_into_mock_fabric(fabric, delta, start_index=before)

            latest_cap_id = delta.get_emitted("k1.mcp.tool.discovered.v1")[-1]["capability_id"]

            retried = await service.process(_run_req(wf_id))
            assert retried == ProcessResult.COMPLETED
            fabric.assert_called(latest_cap_id, times=2)
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_refresh_unknown_server_returns_error_result(self) -> None:
        _, _, _, _, lifecycle, _, _, _ = await _svc()

        result = await lifecycle.refresh("does-not-exist")
        assert result.registered == 0
        assert result.errors

    @pytest.mark.asyncio
    async def test_recovered_tool_supports_scheduled_workflow_run(self) -> None:
        service, fabric, delta, event, lifecycle, registry, engine, storage = await _svc()

        path = _write_yaml(
            """servers:
  - id: calendar
    type: remote
    endpoint: http://calendar
"""
        )
        try:
            lifecycle._discovery._config_path = path  # type: ignore[attr-defined]
            lifecycle._discovery._transport = _Transport(  # type: ignore[attr-defined]
                {"calendar": [{"name": "create_event", "description": "Create calendar event"}]}
            )

            await lifecycle.discover_and_register()
            cap_id = _wire_discovered_tools_into_mock_fabric(fabric, delta)[-1]

            wf_id = "wf-mcp-scheduled-recovery"
            spec = WorkflowSpec(
                workflow_id=wf_id,
                name=f"wf-{wf_id}",
                source_plan_id=f"plan-{wf_id}",
                version="1.0.0",
                trigger=TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *"),
                steps=[PlanStep(id="s1", capability=cap_id)],
                dependencies={},
                active=True,
            )
            await registry.save(spec)
            await storage.save_trigger(wf_id, spec.trigger)

            # Outage then recovery.
            fabric.registry.pop(cap_id, None)
            lifecycle.start_lifecycle_monitoring()
            event.fire(
                "k1.fabric.provider.health.changed.v1",
                {
                    "provider_id": "mcp.calendar",
                    "old_state": "DEGRADED",
                    "new_state": "HEALTHY",
                },
            )
            for server_id in lifecycle.get_pending_refreshes():
                before = len(delta.get_emitted("k1.mcp.tool.discovered.v1"))
                await lifecycle.refresh(server_id)
                _wire_discovered_tools_into_mock_fabric(fabric, delta, start_index=before)

            await engine.scheduler._tick()
            msg = service._mailbox.dequeue()
            assert isinstance(msg, WorkflowRunRequest)
            assert msg.workflow_id == wf_id

            result = await service.process(msg)
            assert result == ProcessResult.COMPLETED
        finally:
            os.unlink(path)
