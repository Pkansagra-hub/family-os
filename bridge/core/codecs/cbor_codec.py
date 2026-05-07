"""CBORCodec — ``cbor2`` 5.6+ (RFC 8949)."""

from __future__ import annotations

from typing import Any, ClassVar

import cbor2

from bridge.core.codecs.base import CodecError


class CBORCodec:
    """RFC 8949 CBOR codec.

    Datetime tagging is handled by ``cbor2`` natively when needed; for
    bridge envelopes we always operate on JSON-shaped dicts (Pydantic
    ``model_dump(mode="json")`` upstream), so all values are already
    one of ``str|int|float|bool|None|list|dict``.
    """

    name: ClassVar[str] = "cbor"
    content_type: ClassVar[str] = "application/cbor"

    def encode(self, body: dict[str, Any]) -> bytes:
        try:
            return cbor2.dumps(body)
        except (cbor2.CBOREncodeError, TypeError, ValueError) as exc:
            raise CodecError(f"CBORCodec.encode failed: {exc}") from exc

    def decode(self, raw: bytes) -> dict[str, Any]:
        try:
            value = cbor2.loads(raw)
        except (cbor2.CBORDecodeError, ValueError) as exc:
            raise CodecError(f"CBORCodec.decode failed: {exc}") from exc
        if not isinstance(value, dict):
            raise CodecError(
                f"CBORCodec.decode: expected dict at top level, got {type(value).__name__}"
            )
        return value
