"""M0.E1.I2 — citation contract dataclasses are frozen and minimal-construct."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from k1.selfmodel.contracts.citation import Citation, CitationPack


def test_citation_min_construct() -> None:
    c = Citation(citation_id="c-1", source_layer="L3")
    assert c.citation_id == "c-1"
    assert c.source_layer == "L3"
    assert c.freshness == "fresh"
    assert c.confidence == 1.0
    assert c.payload == {}


def test_citation_pack_min_construct() -> None:
    p = CitationPack(actor_id="alice")
    assert p.actor_id == "alice"
    assert p.citations == ()
    assert p.composed_at_ms == 0


@pytest.mark.parametrize(
    "instance,field_name",
    [
        (Citation(citation_id="c", source_layer="L3"), "citation_id"),
        (CitationPack(actor_id="a"), "actor_id"),
    ],
)
def test_citation_dataclasses_are_frozen(instance: object, field_name: str) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(instance, field_name, "tampered")
