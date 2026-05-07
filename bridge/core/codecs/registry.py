"""CodecRegistry — manifest-driven codec selection + Accept negotiation."""

from __future__ import annotations

from typing import Any, ClassVar

from bridge.core.codecs.base import Codec, UnsupportedCodecError
from bridge.core.codecs.cbor_codec import CBORCodec
from bridge.core.codecs.json_codec import JSONCodec
from bridge.core.codecs.msgpack_codec import MsgpackCodec

# Negotiation policy values mirrored in ``manifest.schema.json``.
CODEC_NEGOTIATION_FIXED: str = "fixed"
CODEC_NEGOTIATION_DEFAULT: str = "client_choice_in_allowed"


class UnsupportedMediaTypeError(Exception):
    """Raised when a client ``Accept`` header asks for a codec the
    manifest does not allow under ``codec_negotiation: fixed`` or when
    the codec is unknown to the registry.

    K0 ingress maps this to HTTP 406 with a structured body:

        {"error": "unsupported_media_type", "supported": ["application/json"]}
    """

    def __init__(self, *, requested: str | None, supported: list[str]) -> None:
        self.requested = requested
        self.supported = supported
        super().__init__(f"unsupported media type: requested={requested!r} supported={supported!r}")


class CodecRegistry:
    """Lookup table from codec name → :class:`Codec` instance.

    The registry is **immutable after construction**. Three codecs are
    always registered: ``json``, ``msgpack``, ``cbor``. The future
    ``flatbuffers`` value listed in the meta-schema is intentionally
    not implemented yet (no MS-4 use case); attempts to resolve it
    raise :class:`UnsupportedCodecError`.
    """

    _BUILTINS: ClassVar[tuple[type, ...]] = (JSONCodec, MsgpackCodec, CBORCodec)

    def __init__(self) -> None:
        self._by_name: dict[str, Codec] = {cls.name: cls() for cls in self._BUILTINS}
        self._by_content_type: dict[str, Codec] = {
            c.content_type: c for c in self._by_name.values()
        }

    # -- raw lookup ---------------------------------------------------------

    def get(self, name: str) -> Codec:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise UnsupportedCodecError(
                f"unknown codec name: {name!r}; " f"registered={sorted(self._by_name)}"
            ) from exc

    def by_content_type(self, content_type: str) -> Codec:
        try:
            return self._by_content_type[content_type]
        except KeyError as exc:
            raise UnsupportedCodecError(f"unknown content-type: {content_type!r}") from exc

    @property
    def supported_content_types(self) -> list[str]:
        return sorted(self._by_content_type)

    # -- manifest-driven selection -----------------------------------------

    def for_manifest(self, manifest_delivery: dict[str, Any]) -> Codec:
        """Return the manifest-declared default codec (defaults to JSON)."""
        codec_name = manifest_delivery.get("codec", "json")
        return self.get(codec_name)

    def codecs_allowed(self, manifest_delivery: dict[str, Any]) -> list[Codec]:
        """Return the ordered list of codecs the manifest permits.

        Defaults to ``[manifest.codec]`` when ``codecs_allowed`` is
        absent — backward compatible with every pre-MS-4 manifest.
        """
        default = self.for_manifest(manifest_delivery)
        names = manifest_delivery.get("codecs_allowed")
        if not names:
            return [default]
        return [self.get(n) for n in names]

    def for_negotiation(
        self,
        manifest_delivery: dict[str, Any],
        accept_header: str | None,
    ) -> Codec:
        """Select a codec honouring an HTTP ``Accept`` header.

        Behaviour matrix:

        * No ``Accept`` header → manifest default codec.
        * ``Accept`` matches an allowed content-type → return that codec.
        * ``Accept`` does not match any allowed content-type:
            * ``codec_negotiation: client_choice_in_allowed`` (default) →
              fall back to manifest default.
            * ``codec_negotiation: fixed`` →
              raise :class:`UnsupportedMediaTypeError` (caller maps to 406).
        """
        default = self.for_manifest(manifest_delivery)
        if not accept_header or accept_header.strip() in ("*/*", ""):
            return default
        allowed = self.codecs_allowed(manifest_delivery)
        allowed_types = {c.content_type for c in allowed}
        # Parse a basic ``Accept: a/b, c/d;q=0.9`` list (q-values are
        # honoured by ordering but a single match is sufficient for our
        # finite codec set; we do not need full RFC 7231 q-value math).
        for piece in accept_header.split(","):
            media = piece.split(";", 1)[0].strip().lower()
            if media in allowed_types:
                return self.by_content_type(media)
            if media == "*/*":
                return default
        policy = manifest_delivery.get("codec_negotiation", CODEC_NEGOTIATION_DEFAULT)
        if policy == CODEC_NEGOTIATION_FIXED:
            raise UnsupportedMediaTypeError(
                requested=accept_header,
                supported=sorted(allowed_types),
            )
        return default
