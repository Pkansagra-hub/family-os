"""K0 IFL ingestion family (MS-5 PR#4).

The IFL family normalizes responses from Inbound Foreign-Language
adapters (Google Calendar, GitHub, etc.) into ``MemoryAtom`` rows
and feeds the **existing** P02 write-ingest pipeline. There is
**no** new pipeline number — locked decision #8 in the MS-5 plan
keeps the K0 side small.

Each IFL source ships a normalizer module under this package that
converts an adapter response → a list of ``dict[str, Any]`` payloads
matching the v2.2 ``MemoryAtom`` shape declared by
``memory.write.v1``. The shared :mod:`~k0.pipelines.p_ifl.ingest`
orchestrator drives one P02 ingest per atom, returning a list of
ack envelopes.
"""

from __future__ import annotations
