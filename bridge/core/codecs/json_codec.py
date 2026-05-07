"""JSONCodec — stdlib ``json``, the always-available default."""

from __future__ import annotations

import json
from typing import Any, ClassVar

from bridge.core.codecs.base import CodecError


class JSONCodec:
    """Deterministic JSON codec.

    Uses ``sort_keys=True`` + ``ensure_ascii=False`` + tight separators
    so the output is canonical: same input dict yields same bytes,
    regardless of insertion order. This matches the canonicalisation
    contract envelope signing relies on.
    """

    name: ClassVar[str] = "json"
    content_type: ClassVar[str] = "application/json"

    def encode(self, body: dict[str, Any]) -> bytes:
        try:
            return json.dumps(
                body,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise CodecError(f"JSONCodec.encode failed: {exc}") from exc

    def decode(self, raw: bytes) -> dict[str, Any]:
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CodecError(f"JSONCodec.decode failed: {exc}") from exc
        if not isinstance(value, dict):
            raise CodecError(
                f"JSONCodec.decode: expected dict at top level, got {type(value).__name__}"
            )
        return value
