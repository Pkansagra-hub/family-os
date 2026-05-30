"""
Tests for Fabric production adapter issues 5.2.10, 5.2.11, and 5.2.12.

5.2.10 -- PromptSystemProdAdapter (YAML prompt loader)
5.2.11 -- DeltaBusProdAdapter (production delta bus via IBus)
5.2.12 -- EventPortProdAdapter (production event port via IBus)

Coverage:
  - Protocol satisfaction (structural subtyping)
  - Core operations (resolve, compile, emit, subscribe, unsubscribe)
  - Edge cases (missing dir, empty dir, malformed YAML, serialize errors)
  - Thread safety (concurrent operations)
  - Package exports via adapters __init__
"""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List
from unittest.mock import MagicMock

from k1.fabric.adapters.delta_bus_prod import DeltaBusProdAdapter
from k1.fabric.adapters.event_port_prod import EventPortProdAdapter
from k1.fabric.adapters.prompt_system_prod import PromptSystemProdAdapter
from k1.fabric.ports.delta_bus import IDeltaBusPort
from k1.fabric.ports.event_port import IEventPort, SubscriptionHandle
from k1.fabric.ports.prompt_system import IPromptSystemPort, PromptTemplate

# ===========================================================================
# Helpers
# ===========================================================================


def _write_yaml(directory: str, filename: str, content: str) -> str:
    """Write a YAML file and return its path."""
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


SAMPLE_PROMPT_YAML = """\
prompt_contract:
  name: greeting_v1
  version: "2.0"
  domain: social
  description: A greeting template
  template: "Hello {name}, welcome to {place}!"
  variables:
    - name: name
      type: string
      required: true
    - name: place
      type: string
      required: false
      default: FamilyOS
  max_tokens: 100
  output_format: text
"""

MINIMAL_PROMPT_YAML = """\
prompt_contract:
  name: minimal
  template: "Just a simple template."
"""

TEMPLATE_FILE_PROMPT_YAML = (
    "prompt_contract:\n"
    "  name: file_template_v1\n"
    '  version: "1.0.0"\n'
    "  domain:\n"
    "    - test\n"
    "  description: A prompt backed by a separate template file\n"
    "  template_file: template.md\n"
    "  variables:\n"
    "    - name: name\n"
    "      type: STRING\n"
    "      required: true\n"
    "      description: Person to greet\n"
    "  max_tokens: 100\n"
    "  output_format: TEXT\n"
    "  compatible_tools:\n"
    "    - tool.execute.calendar.create_event\n"
)

MISSING_TEMPLATE_FILE_PROMPT_YAML = (
    "prompt_contract:\n"
    "  name: missing_file_template_v1\n"
    '  version: "1.0.0"\n'
    "  domain:\n"
    "    - test\n"
    "  description: A prompt with a missing template file\n"
    "  template_file: missing.md\n"
    "  variables: []\n"
    "  max_tokens: 100\n"
    "  output_format: TEXT\n"
)

NO_NAME_YAML = """\
prompt_contract:
  template: "Template without a name."
"""


class FakeBusHandle:
    """Minimal bus subscription handle for testing."""

    def __init__(self, sub_id: str, pattern: str):
        self.subscription_id = sub_id
        self.pattern = pattern


class FakeBus:
    """Minimal IBus stub for testing production adapters."""

    def __init__(self) -> None:
        self.published: List[Any] = []
        self._handlers: Dict[str, List[Any]] = {}
        self._sub_counter = 0

    def publish(self, envelope: Any) -> None:
        self.published.append(envelope)
        # Dispatch to matching subscribers
        topic = envelope.topic
        for pattern, handlers in self._handlers.items():
            if topic == pattern or topic.startswith(pattern.rstrip("*")):
                for handler in handlers:
                    handler(envelope)

    def subscribe(self, pattern: str, handler: Any) -> FakeBusHandle:
        self._sub_counter += 1
        sub_id = f"sub-{self._sub_counter}"
        if pattern not in self._handlers:
            self._handlers[pattern] = []
        self._handlers[pattern].append(handler)
        return FakeBusHandle(sub_id, pattern)

    def unsubscribe(self, handle: FakeBusHandle) -> bool:
        pattern = handle.pattern
        if pattern in self._handlers and self._handlers[pattern]:
            self._handlers[pattern].pop(0)
            return True
        return False


class FakeEnvelope:
    """Minimal Envelope stub for testing event port deserialization."""

    def __init__(self, topic: str, payload: bytes, envelope_id: int = 1):
        self.topic = topic
        self.payload = payload
        self.envelope_id = envelope_id


# ===========================================================================
# 5.2.10 -- PromptSystemProdAdapter
# ===========================================================================


class TestPromptSystemProtocol:
    """Protocol satisfaction."""

    def test_satisfies_protocol(self, tmp_path: Any) -> None:
        adapter = PromptSystemProdAdapter(tmp_path)
        assert isinstance(adapter, IPromptSystemPort)

    def test_has_resolve_and_compile(self) -> None:
        assert hasattr(PromptSystemProdAdapter, "resolve")
        assert hasattr(PromptSystemProdAdapter, "compile")


class TestPromptSystemResolve:
    """resolve() tests."""

    def test_resolve_loaded_template(self, tmp_path: Any) -> None:
        _write_yaml(str(tmp_path), "greeting.yaml", SAMPLE_PROMPT_YAML)
        adapter = PromptSystemProdAdapter(tmp_path)
        result = adapter.resolve("greeting_v1")
        assert result is not None
        assert result.name == "greeting_v1"
        assert result.version == "2.0"
        assert "name" in result.variables
        assert "place" in result.variables
        assert "Hello {name}" in result.template

    def test_resolve_unknown_returns_none(self, tmp_path: Any) -> None:
        adapter = PromptSystemProdAdapter(tmp_path)
        assert adapter.resolve("nonexistent") is None

    def test_resolve_minimal_template(self, tmp_path: Any) -> None:
        _write_yaml(str(tmp_path), "minimal.yaml", MINIMAL_PROMPT_YAML)
        adapter = PromptSystemProdAdapter(tmp_path)
        result = adapter.resolve("minimal")
        assert result is not None
        assert result.name == "minimal"
        assert result.template == "Just a simple template."

    def test_resolve_template_file_relative_to_contract(self, tmp_path: Any) -> None:
        (tmp_path / "template.md").write_text(
            "Hello {name}, this came from a template file.", encoding="utf-8"
        )
        _write_yaml(str(tmp_path), "file_template.yaml", TEMPLATE_FILE_PROMPT_YAML)
        adapter = PromptSystemProdAdapter(tmp_path)
        result = adapter.resolve("file_template_v1")
        assert result is not None
        assert result.name == "file_template_v1"
        assert result.template == "Hello {name}, this came from a template file."
        assert result.variables == ["name"]
        assert result.metadata["template_file"] == "template.md"
        assert result.metadata["template_source"] == "template_file"
        assert result.metadata["template_file_resolved"].endswith("template.md")
        assert result.metadata["compatible_tools"] == ["tool.execute.calendar.create_event"]

    def test_skips_no_name_yaml(self, tmp_path: Any) -> None:
        _write_yaml(str(tmp_path), "bad.yaml", NO_NAME_YAML)
        adapter = PromptSystemProdAdapter(tmp_path)
        assert adapter.template_count == 0

    def test_loads_multiple_templates(self, tmp_path: Any) -> None:
        _write_yaml(str(tmp_path), "a.yaml", SAMPLE_PROMPT_YAML)
        _write_yaml(str(tmp_path), "b.yaml", MINIMAL_PROMPT_YAML)
        adapter = PromptSystemProdAdapter(tmp_path)
        assert adapter.template_count == 2
        assert set(adapter.list_names()) == {"greeting_v1", "minimal"}

    def test_ignores_non_yaml_files(self, tmp_path: Any) -> None:
        _write_yaml(str(tmp_path), "readme.txt", "not yaml")
        _write_yaml(str(tmp_path), "greeting.yaml", SAMPLE_PROMPT_YAML)
        adapter = PromptSystemProdAdapter(tmp_path)
        assert adapter.template_count == 1

    def test_resolve_increments_counter(self, tmp_path: Any) -> None:
        _write_yaml(str(tmp_path), "g.yaml", SAMPLE_PROMPT_YAML)
        adapter = PromptSystemProdAdapter(tmp_path)
        assert adapter.resolve_count == 0
        adapter.resolve("greeting_v1")
        adapter.resolve("nonexistent")
        assert adapter.resolve_count == 2


class TestPromptSystemCompile:
    """compile() tests."""

    def test_compile_string_template(self, tmp_path: Any) -> None:
        adapter = PromptSystemProdAdapter(tmp_path)
        result = adapter.compile("Hello {name}!", {"name": "Alice"})
        assert result == "Hello Alice!"

    def test_compile_prompt_template_object(self, tmp_path: Any) -> None:
        pt = PromptTemplate(
            name="test",
            template="Hi {who}, from {where}.",
            version="1",
            variables=["who", "where"],
        )
        adapter = PromptSystemProdAdapter(tmp_path)
        result = adapter.compile(pt, {"who": "Bob", "where": "Home"})
        assert result == "Hi Bob, from Home."

    def test_compile_leaves_unresolved_placeholders(self, tmp_path: Any) -> None:
        adapter = PromptSystemProdAdapter(tmp_path)
        result = adapter.compile("Hello {name}, {mood}!", {"name": "Alice"})
        assert result == "Hello Alice, {mood}!"

    def test_compile_increments_counter(self, tmp_path: Any) -> None:
        adapter = PromptSystemProdAdapter(tmp_path)
        adapter.compile("a", {})
        adapter.compile("b", {})
        assert adapter.compile_count == 2


class TestPromptSystemEdgeCases:
    """Edge cases for PromptSystemProdAdapter."""

    def test_nonexistent_directory(self) -> None:
        """Adapter tolerates non-existent directory."""
        adapter = PromptSystemProdAdapter("/tmp/does_not_exist_xyz_123")
        assert adapter.template_count == 0
        assert adapter.resolve("anything") is None

    def test_empty_directory(self, tmp_path: Any) -> None:
        adapter = PromptSystemProdAdapter(tmp_path)
        assert adapter.template_count == 0

    def test_malformed_yaml(self, tmp_path: Any) -> None:
        _write_yaml(str(tmp_path), "bad.yaml", ": : :\n  - [invalid")
        adapter = PromptSystemProdAdapter(tmp_path)
        assert adapter.template_count == 0

    def test_missing_template_file_skips_template(self, tmp_path: Any) -> None:
        _write_yaml(str(tmp_path), "missing.yaml", MISSING_TEMPLATE_FILE_PROMPT_YAML)
        adapter = PromptSystemProdAdapter(tmp_path)
        assert adapter.template_count == 0
        assert adapter.resolve("missing_file_template_v1") is None

    def test_reload(self, tmp_path: Any) -> None:
        adapter = PromptSystemProdAdapter(tmp_path)
        assert adapter.template_count == 0
        _write_yaml(str(tmp_path), "greeting.yaml", SAMPLE_PROMPT_YAML)
        count = adapter.reload()
        assert count == 1
        assert adapter.resolve("greeting_v1") is not None

    def test_has_template(self, tmp_path: Any) -> None:
        _write_yaml(str(tmp_path), "g.yaml", SAMPLE_PROMPT_YAML)
        adapter = PromptSystemProdAdapter(tmp_path)
        assert adapter.has_template("greeting_v1")
        assert not adapter.has_template("nonexistent")

    def test_metadata_includes_extra_fields(self, tmp_path: Any) -> None:
        _write_yaml(str(tmp_path), "g.yaml", SAMPLE_PROMPT_YAML)
        adapter = PromptSystemProdAdapter(tmp_path)
        pt = adapter.resolve("greeting_v1")
        assert pt is not None
        assert pt.metadata.get("domain") == "social"
        assert pt.metadata.get("max_tokens") == 100
        assert pt.metadata.get("output_format") == "text"

    def test_repr(self, tmp_path: Any) -> None:
        adapter = PromptSystemProdAdapter(tmp_path)
        r = repr(adapter)
        assert "PromptSystemProdAdapter" in r

    def test_yml_extension(self, tmp_path: Any) -> None:
        _write_yaml(str(tmp_path), "test.yml", MINIMAL_PROMPT_YAML)
        adapter = PromptSystemProdAdapter(tmp_path)
        assert adapter.template_count == 1


class TestPromptSystemThreadSafety:
    """Concurrent access."""

    def test_concurrent_resolve(self, tmp_path: Any) -> None:
        _write_yaml(str(tmp_path), "g.yaml", SAMPLE_PROMPT_YAML)
        adapter = PromptSystemProdAdapter(tmp_path)
        results: List[Any] = []

        def _resolve() -> None:
            for _ in range(50):
                r = adapter.resolve("greeting_v1")
                results.append(r)

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(_resolve) for _ in range(4)]
            for f in futures:
                f.result()

        assert len(results) == 200
        assert all(r is not None for r in results)


# ===========================================================================
# 5.2.11 -- DeltaBusProdAdapter
# ===========================================================================


class TestDeltaBusProdProtocol:
    """Protocol satisfaction."""

    def test_satisfies_protocol(self) -> None:
        bus = FakeBus()
        adapter = DeltaBusProdAdapter(bus)
        assert isinstance(adapter, IDeltaBusPort)

    def test_has_emit_delta(self) -> None:
        assert hasattr(DeltaBusProdAdapter, "emit_delta")


class TestDeltaBusProdEmit:
    """emit_delta() tests."""

    def test_emit_publishes_envelope(self) -> None:
        bus = MagicMock()
        adapter = DeltaBusProdAdapter(bus)
        adapter.emit_delta("agent-1", "plan_update", "plan", {"step": 1})
        assert bus.publish.call_count == 1
        envelope = bus.publish.call_args[0][0]
        assert envelope.topic == "k1.agent.agent-1.delta.v1"

    def test_emit_payload_is_json(self) -> None:
        bus = MagicMock()
        adapter = DeltaBusProdAdapter(bus)
        adapter.emit_delta("a1", "ctx_change", "context", {"key": "val"})
        envelope = bus.publish.call_args[0][0]
        data = json.loads(envelope.payload.decode("utf-8"))
        assert data["agent_id"] == "a1"
        assert data["delta_type"] == "ctx_change"
        assert data["section"] == "context"
        assert data["data"] == {"key": "val"}

    def test_emit_increments_counter(self) -> None:
        bus = MagicMock()
        adapter = DeltaBusProdAdapter(bus)
        assert adapter.emit_count == 0
        adapter.emit_delta("a1", "t", "s", {})
        adapter.emit_delta("a2", "t", "s", {})
        assert adapter.emit_count == 2

    def test_emit_uses_realtime_priority(self) -> None:
        bus = MagicMock()
        adapter = DeltaBusProdAdapter(bus)
        adapter.emit_delta("a1", "t", "s", {})
        envelope = bus.publish.call_args[0][0]
        # Priority.REALTIME == 1
        assert envelope.priority.value == 1 or envelope.priority == 1

    def test_emit_topic_pattern(self) -> None:
        bus = MagicMock()
        adapter = DeltaBusProdAdapter(bus)
        adapter.emit_delta("my-agent-42", "status", "status", {})
        envelope = bus.publish.call_args[0][0]
        assert envelope.topic == "k1.agent.my-agent-42.delta.v1"


class TestDeltaBusProdEdgeCases:
    """Edge cases for DeltaBusProdAdapter."""

    def test_bus_publish_failure_does_not_raise(self) -> None:
        bus = MagicMock()
        bus.publish.side_effect = RuntimeError("bus down")
        adapter = DeltaBusProdAdapter(bus)
        # Should not raise
        adapter.emit_delta("a1", "t", "s", {})
        assert adapter.emit_count == 1

    def test_repr(self) -> None:
        bus = MagicMock()
        adapter = DeltaBusProdAdapter(bus)
        r = repr(adapter)
        assert "DeltaBusProdAdapter" in r

    def test_bus_property(self) -> None:
        bus = MagicMock()
        adapter = DeltaBusProdAdapter(bus)
        assert adapter.bus is bus


class TestDeltaBusProdThreadSafety:
    """Concurrent emit_delta calls."""

    def test_concurrent_emit(self) -> None:
        bus = MagicMock()
        adapter = DeltaBusProdAdapter(bus)

        def _emit() -> None:
            for i in range(50):
                adapter.emit_delta(f"agent-{i}", "update", "plan", {"i": i})

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(_emit) for _ in range(4)]
            for f in futures:
                f.result()

        assert adapter.emit_count == 200
        assert bus.publish.call_count == 200


# ===========================================================================
# 5.2.12 -- EventPortProdAdapter
# ===========================================================================


class TestEventPortProdProtocol:
    """Protocol satisfaction."""

    def test_satisfies_protocol(self) -> None:
        bus = FakeBus()
        adapter = EventPortProdAdapter(bus)
        assert isinstance(adapter, IEventPort)

    def test_has_emit_subscribe_unsubscribe(self) -> None:
        assert hasattr(EventPortProdAdapter, "emit")
        assert hasattr(EventPortProdAdapter, "subscribe")
        assert hasattr(EventPortProdAdapter, "unsubscribe")


class TestEventPortProdEmit:
    """emit() tests."""

    def test_emit_publishes_envelope(self) -> None:
        bus = MagicMock()
        adapter = EventPortProdAdapter(bus)
        adapter.emit("k1.fabric.test.v1", {"data": "hello"})
        assert bus.publish.call_count == 1
        envelope = bus.publish.call_args[0][0]
        assert envelope.topic == "k1.fabric.test.v1"

    def test_emit_payload_is_json(self) -> None:
        bus = MagicMock()
        adapter = EventPortProdAdapter(bus)
        adapter.emit("t", {"key": "val", "cognitive_trace_id": "tr-1"})
        envelope = bus.publish.call_args[0][0]
        data = json.loads(envelope.payload.decode("utf-8"))
        assert data["key"] == "val"
        assert data["cognitive_trace_id"] == "tr-1"

    def test_emit_extracts_trace_id(self) -> None:
        bus = MagicMock()
        adapter = EventPortProdAdapter(bus)
        adapter.emit("t", {"cognitive_trace_id": "abc-123"})
        envelope = bus.publish.call_args[0][0]
        assert envelope.cognitive_trace_id == "abc-123"

    def test_emit_increments_counter(self) -> None:
        bus = MagicMock()
        adapter = EventPortProdAdapter(bus)
        adapter.emit("t1", {})
        adapter.emit("t2", {})
        assert adapter.emit_count == 2

    def test_emit_handles_dataclass_with_to_dict(self) -> None:
        """Payload with to_dict() method is auto-converted."""
        bus = MagicMock()
        adapter = EventPortProdAdapter(bus)

        class FakePayload:
            def to_dict(self) -> Dict[str, Any]:
                return {"foo": "bar"}

        adapter.emit("t", FakePayload())
        envelope = bus.publish.call_args[0][0]
        data = json.loads(envelope.payload.decode("utf-8"))
        assert data["foo"] == "bar"


class TestEventPortProdSubscribe:
    """subscribe() tests."""

    def test_subscribe_returns_handle(self) -> None:
        bus = FakeBus()
        adapter = EventPortProdAdapter(bus)
        handle = adapter.subscribe("k1.test.*", lambda t, p: None)
        assert isinstance(handle, SubscriptionHandle)
        assert handle.topic == "k1.test.*"
        assert handle.subscription_id != ""

    def test_subscribe_increments_counter(self) -> None:
        bus = FakeBus()
        adapter = EventPortProdAdapter(bus)
        adapter.subscribe("t1", lambda t, p: None)
        adapter.subscribe("t2", lambda t, p: None)
        assert adapter.subscribe_count == 2
        assert adapter.active_subscriptions == 2

    def test_subscribe_handler_receives_deserialized_data(self) -> None:
        """End-to-end: emit → bus → handler receives dict."""
        bus = FakeBus()
        adapter = EventPortProdAdapter(bus)
        received: List[Any] = []

        def handler(topic: str, payload: Any) -> None:
            received.append((topic, payload))

        adapter.subscribe("k1.test.v1", handler)
        adapter.emit("k1.test.v1", {"msg": "hello"})

        assert len(received) == 1
        assert received[0][0] == "k1.test.v1"
        assert received[0][1]["msg"] == "hello"


class TestEventPortProdUnsubscribe:
    """unsubscribe() tests."""

    def test_unsubscribe_returns_true(self) -> None:
        bus = FakeBus()
        adapter = EventPortProdAdapter(bus)
        handle = adapter.subscribe("t", lambda t, p: None)
        assert adapter.unsubscribe(handle) is True
        assert adapter.active_subscriptions == 0

    def test_unsubscribe_unknown_handle_returns_false(self) -> None:
        bus = FakeBus()
        adapter = EventPortProdAdapter(bus)
        handle = SubscriptionHandle(subscription_id="fake", topic="t")
        assert adapter.unsubscribe(handle) is False

    def test_double_unsubscribe_returns_false(self) -> None:
        bus = FakeBus()
        adapter = EventPortProdAdapter(bus)
        handle = adapter.subscribe("t", lambda t, p: None)
        assert adapter.unsubscribe(handle) is True
        assert adapter.unsubscribe(handle) is False


class TestEventPortProdEdgeCases:
    """Edge cases for EventPortProdAdapter."""

    def test_emit_publish_failure_does_not_raise(self) -> None:
        bus = MagicMock()
        bus.publish.side_effect = RuntimeError("bus down")
        adapter = EventPortProdAdapter(bus)
        adapter.emit("t", {"data": 1})
        assert adapter.emit_count == 1

    def test_handler_exception_does_not_propagate(self) -> None:
        bus = FakeBus()
        adapter = EventPortProdAdapter(bus)

        def bad_handler(topic: str, payload: Any) -> None:
            raise ValueError("handler error")

        adapter.subscribe("t", bad_handler)
        # Should not raise
        adapter.emit("t", {"x": 1})

    def test_repr(self) -> None:
        bus = MagicMock()
        adapter = EventPortProdAdapter(bus)
        r = repr(adapter)
        assert "EventPortProdAdapter" in r

    def test_bus_property(self) -> None:
        bus = MagicMock()
        adapter = EventPortProdAdapter(bus)
        assert adapter.bus is bus


class TestEventPortProdThreadSafety:
    """Concurrent operations."""

    def test_concurrent_emit_and_subscribe(self) -> None:
        bus = FakeBus()
        adapter = EventPortProdAdapter(bus)
        received: List[Any] = []
        lock = threading.Lock()

        def handler(topic: str, payload: Any) -> None:
            with lock:
                received.append(payload)

        adapter.subscribe("t", handler)

        def _emit() -> None:
            for i in range(50):
                adapter.emit("t", {"i": i})

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(_emit) for _ in range(4)]
            for f in futures:
                f.result()

        assert adapter.emit_count == 200


# ===========================================================================
# Package export tests
# ===========================================================================


class TestPackageExports:
    """Verify the 3 new adapters are exported from __init__."""

    def test_prompt_system_prod_exported(self) -> None:
        from k1.fabric.adapters import PromptSystemProdAdapter as Cls

        assert Cls is PromptSystemProdAdapter

    def test_delta_bus_prod_exported(self) -> None:
        from k1.fabric.adapters import DeltaBusProdAdapter as Cls

        assert Cls is DeltaBusProdAdapter

    def test_event_port_prod_exported(self) -> None:
        from k1.fabric.adapters import EventPortProdAdapter as Cls

        assert Cls is EventPortProdAdapter
