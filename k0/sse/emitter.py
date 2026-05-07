"""K0-side SSE emitter (MS-3d Epic 3d.3).

Producer-side seam: the codegen-emitted ``<Topic>Client.emit(payload)``
calls ``runtime._sse_emitter.emit(topic=..., schema_uri=..., payload=...)``;
this module is what fills that slot. It is the **only** place P05/P06/P03
emit code paths need to know about \u2014 the underlying durable replay
buffer + in-process fanout broker are wiring details kept inside.

Idempotency: every emit must carry a stable ``envelope_id`` (a ULID) in
the payload. The replay buffer's ``UNIQUE(topic, envelope_id)`` index
makes retries safe: a duplicate ``envelope_id`` returns the existing
``seq`` and is not re-fanout-d (the buffer raises no error; the emitter
detects the duplicate via ``seq`` not advancing past the previous
cursor and skips fanout).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from k0.sse.fanout import FanoutEvent, SSEFanout
from k0.sse.replay_buffer import SSEReplayBuffer

logger = logging.getLogger(__name__)


class K0SSEEmitter:
    """Append-then-fanout emitter wired to a buffer and a fanout broker.

    The emitter is intentionally synchronous about durability (the
    SQLite ``INSERT`` blocks the calling task until commit) and async
    only at the fanout boundary. This ordering is essential: a crash
    between ``append`` and ``publish`` is recovered by the next K1
    reconnect (replay buffer holds the event); a crash between
    ``publish`` and ``append`` would lose the event entirely.
    """

    def __init__(self, *, replay_buffer: SSEReplayBuffer, fanout: SSEFanout) -> None:
        self._buffer = replay_buffer
        self._fanout = fanout

    async def emit(
        self,
        *,
        topic: str,
        schema_uri: str,
        payload: BaseModel | dict[str, Any],
    ) -> str:
        """Append ``payload`` to the buffer and fan it out to live subs.

        Returns the ``envelope_id`` (taken from ``payload.envelope_id``).
        Raises :class:`ValueError` if the payload is missing
        ``envelope_id`` \u2014 K0 never autogenerates IDs at the SSE seam;
        producers are required to mint a ULID upstream so the cursor
        protocol stays consistent across retries.
        """
        body = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else dict(payload)
        envelope_id = body.get("envelope_id")
        if not isinstance(envelope_id, str) or not envelope_id:
            raise ValueError(
                f"K0SSEEmitter: payload for topic={topic!r} missing required "
                "'envelope_id' field (producers must mint a ULID upstream)."
            )
        seq, was_new = self._buffer.append(topic=topic, envelope_id=envelope_id, payload=body)
        if not was_new:
            logger.debug(
                "k0_sse_emitter: duplicate envelope_id=%s on topic=%s seq=%d; "
                "skipping fanout (already in buffer)",
                envelope_id,
                topic,
                seq,
            )
            return envelope_id
        # Schema URI is recorded in the manifest, not on the wire (the
        # ``event:`` SSE field already disambiguates by topic). Logged
        # here for trace correlation only.
        logger.debug(
            "k0_sse_emitter: emit topic=%s envelope_id=%s schema_uri=%s seq=%d",
            topic,
            envelope_id,
            schema_uri,
            seq,
        )
        self._fanout.publish(FanoutEvent(topic=topic, envelope_id=envelope_id, payload=body))
        return envelope_id


__all__ = ("K0SSEEmitter",)
