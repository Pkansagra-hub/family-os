"""
EnvelopeBuilder -- Build MWEnvelopes from MemoryAtom list.

Uses FieldMapper for body construction.
Injects headers from ExtractionContext metadata.

MW-10: Every envelope carries cognitive_trace_id (asserted).
"""

from __future__ import annotations

from typing import List

from k1.memory_writer.envelope.field_mapper import FieldMapper
from k1.memory_writer.invariants import assert_mw10_trace_id
from k1.memory_writer.types import ExtractionContext, MemoryAtom


class EnvelopeBuilder:
    """Build envelope dicts from MemoryAtom list.

    Uses FieldMapper for body construction.
    Injects headers from ExtractionContext metadata.

    MW-10: Every envelope carries cognitive_trace_id (asserted).
    """

    TOPIC = "memory.delta"
    SCHEMA_URI = "schema://memory.delta"
    SCHEMA_VERSION = "1.0"

    __slots__ = ("_field_mapper",)

    def __init__(self, field_mapper: FieldMapper) -> None:
        self._field_mapper = field_mapper

    def build(
        self,
        atoms: List[MemoryAtom],
        context: ExtractionContext,
        trace_id: str,
    ) -> List[dict]:
        """Build envelope dicts from validated MemoryAtom list.

        Each envelope is a dict with: topic, schema_uri, body, trace_id, headers.
        Ready for IBridgeCommandPort.submit_batch().

        Args:
            atoms: Validated MemoryAtom list from ExtractionValidator.
            context: ExtractionContext for header metadata.
            trace_id: cognitive_trace_id (MW-10).

        Returns:
            List of envelope dicts. Empty if atoms is empty.
        """
        # MW-10: trace_id required
        assert_mw10_trace_id(trace_id)

        envelopes: List[dict] = []

        for atom in atoms:
            body = self._field_mapper.map_atom_to_body(atom, context, trace_id)

            envelope = {
                "topic": self.TOPIC,
                "schema_uri": self.SCHEMA_URI,
                "body": body,
                "trace_id": trace_id,
                "headers": self._build_headers(context, trace_id),
            }
            envelopes.append(envelope)

        return envelopes

    def _build_headers(self, context: ExtractionContext, trace_id: str) -> dict:
        """Build MW-side headers. Bridge adds crypto headers later."""
        meta = context.control_context or {}
        return {
            "cognitive_trace_id": trace_id,
            "tenant_id": meta.get("tenant_id", ""),
            "space_id": meta.get("space_id", ""),
            "topic": self.TOPIC,
            "schema_uri": self.SCHEMA_URI,
            "schema_version": self.SCHEMA_VERSION,
            "actor": meta.get("user_id", ""),
            "device_id": meta.get("device_id", ""),
            "band": meta.get("safety_band", "GREEN"),
        }
