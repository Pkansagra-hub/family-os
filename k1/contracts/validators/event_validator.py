from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..loaders.wiring_loader import WiringLoader


class EventValidator:
    """
    Validates event definitions and routing.

    - Ensures event schemas are consistent
    - Validates emitter/subscriber compatibility
    - Checks for event topic naming conflicts
    - Validates event metadata
    """

    def __init__(self, wiring_loader: Optional[WiringLoader] = None):
        self.wiring_loader = wiring_loader or WiringLoader()

    def validate_events(self, module_id: str) -> List[str]:
        """Validate events for a module."""
        errors: List[str] = []

        try:
            spec = self.wiring_loader.load_wiring_spec(module_id)

            # Validate emits
            for event in spec["events"].get("emits", []):
                errors.extend(self._validate_event_definition(event, "emit"))

            # Validate subscribes
            for event in spec["events"].get("subscribes", []):
                errors.extend(self._validate_event_definition(event, "subscribe"))

            # Check for topic conflicts within module
            errors.extend(self._validate_no_topic_conflicts(spec))

        except Exception as e:
            errors.append(f"Event validation failed for {module_id}: {e}")

        return errors

    def validate_all_events(self) -> Dict[str, List[str]]:
        """Validate events across all modules."""
        results: Dict[str, List[str]] = {}

        self.wiring_loader.index_all_modules()

        modules_dir = self.wiring_loader.contract_loader.contracts_dir / "modules"
        if modules_dir.exists():
            for module_dir in modules_dir.iterdir():
                if module_dir.is_dir():
                    module_id = module_dir.name
                    errors = self.validate_events(module_id)
                    if errors:
                        results[module_id] = errors

        # Cross-module validations
        global_errors = self._validate_global_event_consistency()
        if global_errors:
            results["GLOBAL"] = global_errors

        return results

    def _validate_event_definition(self, event: Dict[str, Any], event_type: str) -> List[str]:
        """Validate a single event definition."""
        errors: List[str] = []

        # Required fields
        required = ["topic", "schema"]
        for field in required:
            if field not in event:
                errors.append(f"Missing required field '{field}' in {event_type} event")

        # Topic format
        if "topic" in event:
            topic = event["topic"]
            if not isinstance(topic, str) or not topic:
                errors.append(f"Invalid topic '{topic}': must be non-empty string")
            elif not self._is_valid_topic(topic):
                errors.append(
                    f"Invalid topic format '{topic}': must be lowercase, alphanumeric with . or _"
                )

        # Schema validation
        if "schema" in event:
            schema = event["schema"]
            if not isinstance(schema, dict):
                errors.append("Schema must be an object")
            else:
                # Basic schema checks
                if "$schema" not in schema:
                    errors.append("Schema must specify '$schema'")
                if "type" not in schema:
                    errors.append("Schema must have 'type' field")

        return errors

    def _validate_no_topic_conflicts(self, spec: Dict[str, Any]) -> List[str]:
        """Check for topic conflicts within a module."""
        errors: List[str] = []

        emits = {event["topic"] for event in spec["events"].get("emits", []) if "topic" in event}
        subscribes = {
            event["topic"] for event in spec["events"].get("subscribes", []) if "topic" in event
        }

        conflicts = emits & subscribes
        if conflicts:
            errors.append(f"Topic conflicts: events both emitted and subscribed: {conflicts}")

        return errors

    def _validate_global_event_consistency(self) -> List[str]:
        """Validate consistency across all events."""
        errors: List[str] = []

        self.wiring_loader.index_all_modules()

        # Check schema compatibility for each topic
        for topic in self.wiring_loader._event_emitters:
            emitter_schemas = set()
            subscriber_schemas = set()

            # Collect emitter schemas
            for emitter in self.wiring_loader._event_emitters[topic]:
                try:
                    spec = self.wiring_loader.load_wiring_spec(emitter)
                    for event in spec["events"].get("emits", []):
                        if event.get("topic") == topic:
                            schema_str = str(event.get("schema", {}))
                            emitter_schemas.add(schema_str)
                except Exception:
                    pass

            # Collect subscriber schemas
            for subscriber in self.wiring_loader._event_subscribers[topic]:
                try:
                    spec = self.wiring_loader.load_wiring_spec(subscriber)
                    for event in spec["events"].get("subscribes", []):
                        if event.get("topic") == topic:
                            schema_str = str(event.get("schema", {}))
                            subscriber_schemas.add(schema_str)
                except Exception:
                    pass

            # Check for schema mismatches
            if len(emitter_schemas) > 1:
                errors.append(f"Multiple emitter schemas for topic '{topic}'")

            if emitter_schemas and subscriber_schemas:
                # Subscribers should match emitter schema
                if not subscriber_schemas.issubset(emitter_schemas):
                    errors.append(
                        f"Schema mismatch for topic '{topic}': emitters and subscribers have different schemas"
                    )

        return errors

    def _is_valid_topic(self, topic: str) -> bool:
        """Validate topic format."""
        import re

        # Topics should be lowercase, alphanumeric with dots or underscores
        return bool(re.match(r"^[a-z0-9_.]+$", topic))

    def get_event_report(self) -> Dict[str, Any]:
        """Generate a report on events."""
        self.wiring_loader.index_all_modules()

        report = {
            "total_topics": len(self.wiring_loader._event_emitters),
            "total_emitters": sum(
                len(emits) for emits in self.wiring_loader._event_emitters.values()
            ),
            "total_subscribers": sum(
                len(subs) for subs in self.wiring_loader._event_subscribers.values()
            ),
            "topics_with_multiple_emitters": [
                topic
                for topic, emits in self.wiring_loader._event_emitters.items()
                if len(emits) > 1
            ],
            "topics_without_subscribers": [
                topic
                for topic in self.wiring_loader._event_emitters
                if topic not in self.wiring_loader._event_subscribers
            ],
            "topics_without_emitters": [
                topic
                for topic in self.wiring_loader._event_subscribers
                if topic not in self.wiring_loader._event_emitters
            ],
        }

        return report
