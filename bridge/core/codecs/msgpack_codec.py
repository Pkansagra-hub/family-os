"""MsgpackCodec — ``msgpack`` 1.0+, ``use_bin_type=True``."""

from __future__ import annotations

from typing import Any, ClassVar

import msgpack

from bridge.core.codecs.base import CodecError


class MsgpackCodec:
    """msgpack codec with binary-distinction enabled.

    ``use_bin_type=True`` (encode side) and ``raw=False`` (decode side)
    keep ``str`` and ``bytes`` distinct, matching JSON semantics. Tuples
    are decoded as lists (msgpack has no tuple type) — this matches the
    Pydantic ``model_dump(mode="json")`` shape callers always pass us.
    """

    name: ClassVar[str] = "msgpack"
    content_type: ClassVar[str] = "application/msgpack"

    def encode(self, body: dict[str, Any]) -> bytes:
        try:
            return msgpack.packb(body, use_bin_type=True)
        except (TypeError, ValueError) as exc:
            raise CodecError(f"MsgpackCodec.encode failed: {exc}") from exc

    def decode(self, raw: bytes) -> dict[str, Any]:
        try:
            value = msgpack.unpackb(raw, raw=False)
        except (msgpack.UnpackException, ValueError) as exc:
            raise CodecError(f"MsgpackCodec.decode failed: {exc}") from exc
        if not isinstance(value, dict):
            raise CodecError(
                f"MsgpackCodec.decode: expected dict at top level, got {type(value).__name__}"
            )
        return value
