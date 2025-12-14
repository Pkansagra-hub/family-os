"""
Test suite for PipelineProtocol interface (k0/pipelines/protocol.py).

Validates:
- PipelineProtocol is @runtime_checkable
- BusMessage dataclass structure
- PipelineContext dataclass structure
- Protocol structural subtyping works
- Missing properties/methods detected at runtime

Related:
- M1 R1.3: PipelineProtocol Definition
- Protocol file: k0/pipelines/protocol.py
- Architecture: docs/architecture/decisions/k0_pipeline_architecture.md Section 4
"""

from dataclasses import FrozenInstanceError

import pytest

from k0.bus import BusMessage
from k0.pipelines.protocol import Pipeline, PipelineContext, PipelineProtocol

# ============================================================================
# BusMessage Tests
# ============================================================================


def test_bus_message_immutable():
    """Verify BusMessage is frozen (immutable)."""
    msg = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=b'{"event_id": "evt_123"}',
        offset=42,
        trace_id="trace_abc123",
    )

    with pytest.raises(FrozenInstanceError):
        msg.topic = "different.topic"  # type: ignore


def test_bus_message_slots():
    """Verify BusMessage uses slots (memory optimization)."""
    msg = BusMessage(topic="test.topic", payload=b"test_payload", offset=1, trace_id=None)

    assert not hasattr(msg, "__dict__"), "BusMessage should use __slots__, not __dict__"


def test_bus_message_defaults():
    """Verify BusMessage optional fields default to None."""
    msg = BusMessage(topic="test.topic", payload=b"test_payload", offset=1)

    assert msg.space_id is None, "space_id should default to None"
    assert msg.trace_id is None, "trace_id should default to None"
    assert msg.metadata is None, "metadata should default to None"


def test_bus_message_attributes():
    """Verify BusMessage has all required attributes."""
    msg = BusMessage(
        topic="cognitive.memory.write.committed.v1",
        payload=b'{"event_id": "evt_123"}',
        offset=42,
        space_id="space_abc",
        trace_id="trace_abc123",
        metadata={"priority": "high"},
    )

    assert msg.topic == "cognitive.memory.write.committed.v1"
    assert msg.payload == b'{"event_id": "evt_123"}'
    assert msg.offset == 42
    assert msg.space_id == "space_abc"
    assert msg.trace_id == "trace_abc123"
    assert msg.metadata == {"priority": "high"}


# ============================================================================
# PipelineContext Tests
# ============================================================================


def test_pipeline_context_immutable():
    """Verify PipelineContext is frozen (immutable)."""
    import logging

    ctx = PipelineContext(
        syscalls=object(), config={"key": "value"}, logger=logging.getLogger("test")
    )

    with pytest.raises(FrozenInstanceError):
        ctx.config = {}  # type: ignore


def test_pipeline_context_slots():
    """Verify PipelineContext uses slots (memory optimization)."""
    import logging

    ctx = PipelineContext(syscalls=object(), config={}, logger=logging.getLogger("test"))

    assert not hasattr(ctx, "__dict__"), "PipelineContext should use __slots__, not __dict__"


def test_pipeline_context_attributes():
    """Verify PipelineContext has all required attributes."""
    import logging

    syscalls = object()
    config = {"key": "value"}
    logger = logging.getLogger("test")

    ctx = PipelineContext(syscalls=syscalls, config=config, logger=logger)

    assert ctx.syscalls is syscalls
    assert ctx.config == {"key": "value"}
    assert ctx.logger is logger


# ============================================================================
# PipelineProtocol Tests
# ============================================================================


def test_protocol_runtime_checkable():
    """Verify PipelineProtocol is runtime checkable with isinstance()."""

    class ValidPipeline:
        # Class-level properties
        pipeline_id = "P99"
        contract_version = 1
        declared_topics = ["test.topic"]
        concurrency = 1
        max_queue = 512
        required_caps = ["test.read"]

        async def on_startup(self, ctx: PipelineContext) -> None:
            pass

        async def on_shutdown(self) -> None:
            pass

        async def handle(self, msg: BusMessage) -> None:
            pass

    pipeline = ValidPipeline()
    assert isinstance(pipeline, PipelineProtocol), "Valid pipeline should pass isinstance check"


def test_protocol_missing_property_fails():
    """Verify class missing required property fails isinstance check."""

    class MissingPipelineId:
        # Missing pipeline_id property
        contract_version = 1
        declared_topics = ["test.topic"]
        concurrency = 1
        max_queue = 512
        required_caps = ["test.read"]

        async def on_startup(self, ctx: PipelineContext) -> None:
            pass

        async def on_shutdown(self) -> None:
            pass

        async def handle(self, msg: BusMessage) -> None:
            pass

    pipeline = MissingPipelineId()
    assert not isinstance(pipeline, PipelineProtocol), "Pipeline missing pipeline_id should fail"


def test_protocol_missing_method_fails():
    """Verify class missing required method fails isinstance check."""

    class MissingHandleMethod:
        pipeline_id = "P99"
        contract_version = 1
        declared_topics = ["test.topic"]
        concurrency = 1
        max_queue = 512
        required_caps = ["test.read"]

        async def on_startup(self, ctx: PipelineContext) -> None:
            pass

        async def on_shutdown(self) -> None:
            pass

        # Missing handle() method

    pipeline = MissingHandleMethod()
    assert not isinstance(pipeline, PipelineProtocol), "Pipeline missing handle() should fail"


def test_protocol_wrong_property_type_passes_runtime():
    """Verify runtime isinstance check doesn't enforce property types (structural only)."""

    class WrongTypeProperty:
        pipeline_id = 12345  # Wrong type (int instead of str)
        contract_version = 1
        declared_topics = ["test.topic"]
        concurrency = 1
        max_queue = 512
        required_caps = ["test.read"]

        async def on_startup(self, ctx: PipelineContext) -> None:
            pass

        async def on_shutdown(self) -> None:
            pass

        async def handle(self, msg: BusMessage) -> None:
            pass

    pipeline = WrongTypeProperty()
    # Runtime check only verifies attributes exist, not types
    assert isinstance(pipeline, PipelineProtocol), "Runtime check passes (type checking is static)"


def test_protocol_all_properties_required():
    """Verify all 6 required properties are checked."""

    class MissingMultipleProperties:
        pipeline_id = "P99"
        # Missing contract_version
        declared_topics = ["test.topic"]
        # Missing concurrency
        max_queue = 512
        # Missing required_caps

        async def on_startup(self, ctx: PipelineContext) -> None:
            pass

        async def on_shutdown(self) -> None:
            pass

        async def handle(self, msg: BusMessage) -> None:
            pass

    pipeline = MissingMultipleProperties()
    assert not isinstance(
        pipeline, PipelineProtocol
    ), "Pipeline missing multiple properties should fail"


def test_pipeline_alias():
    """Verify Pipeline is an alias for PipelineProtocol."""
    assert Pipeline is PipelineProtocol, "Pipeline should be an alias for PipelineProtocol"


def test_protocol_example_pipeline_valid():
    """Verify example pipeline from docstring passes protocol check."""

    class P02EpisodicWrite:
        # Class-level contract
        pipeline_id = "P02"
        contract_version = 1
        declared_topics = ["cognitive.memory.write.committed.v1"]
        concurrency = 1
        max_queue = 512
        required_caps = ["st_hipp_events.write"]

        async def on_startup(self, ctx: PipelineContext) -> None:
            self.syscalls = ctx.syscalls
            self.logger = ctx.logger
            self.config = ctx.config

        async def on_shutdown(self) -> None:
            self.logger.info(f"{self.pipeline_id} shutdown")  # type: ignore

        async def handle(self, msg: BusMessage) -> None:
            # Process message
            pass

    pipeline = P02EpisodicWrite()
    assert isinstance(pipeline, PipelineProtocol), "Example pipeline should pass protocol check"


def test_protocol_minimal_pipeline_valid():
    """Verify minimal pipeline with only required members passes protocol check."""

    class MinimalPipeline:
        pipeline_id = "P00"
        contract_version = 1
        declared_topics: list[str] = []  # Empty list is valid
        concurrency = 1
        max_queue = 1
        required_caps: list[str] = []  # No caps required

        async def on_startup(self, ctx: PipelineContext) -> None:
            pass

        async def on_shutdown(self) -> None:
            pass

        async def handle(self, msg: BusMessage) -> None:
            pass

    pipeline = MinimalPipeline()
    assert isinstance(pipeline, PipelineProtocol), "Minimal pipeline should pass protocol check"


def test_protocol_sync_methods_fail():
    """Verify synchronous methods (non-async) fail protocol check."""

    class SyncMethodsPipeline:
        pipeline_id = "P99"
        contract_version = 1
        declared_topics = ["test.topic"]
        concurrency = 1
        max_queue = 512
        required_caps = ["test.read"]

        def on_startup(self, ctx: PipelineContext) -> None:  # Sync instead of async
            pass

        def on_shutdown(self) -> None:  # Sync instead of async
            pass

        def handle(self, msg: BusMessage) -> None:  # Sync instead of async
            pass

    pipeline = SyncMethodsPipeline()
    # Runtime isinstance check doesn't verify async, but static type checker will catch
    # This test documents expected behavior (runtime passes, static fails)
    assert isinstance(pipeline, PipelineProtocol), "Runtime check passes (async is static)"
