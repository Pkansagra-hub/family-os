"""
k1.memory_writer.envelope -- Stage 4: Envelope construction + privacy enforcement.

Re-exports:
  - FieldMapper: MemoryAtom → K0 body dict (34 fields + 7 derived)
  - EnvelopeBuilder: body dict → envelope dict with headers
  - PrivacyEnforcer: band-based field stripping (GREEN/AMBER/RED)
"""

from k1.memory_writer.envelope.envelope_builder import EnvelopeBuilder
from k1.memory_writer.envelope.field_mapper import FieldMapper
from k1.memory_writer.envelope.privacy_enforcer import PrivacyEnforcer

__all__ = [
    "EnvelopeBuilder",
    "FieldMapper",
    "PrivacyEnforcer",
]
