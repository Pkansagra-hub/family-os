"""Tests for ``SelfModelService.add_member_alias`` (C).

The mutator appends an alias to a roster entry in the viewer's L3
``family_members``. If the alias targets the viewer themselves, it is
recorded in ``L3.aliases`` instead.

Run: python -m pytest tests/k1/selfmodel/service/test_add_member_alias.py -q --no-cov
"""

from __future__ import annotations

import pytest

from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot
from k1.selfmodel.service.errors import UnknownActorError
from k1.selfmodel.service.self_model import SELF_MODEL_WRITER_ID
from tests.k1.selfmodel.service._helpers import (
    T0_MS,
    build_bundle,
    make_actor,
)


def _seed_roster(bundle, viewer="a1", roster=None) -> None:
    """Replace the viewer's L3.family_members with ``roster`` (a list of dicts)."""
    snap = K1SelfModelSnapshot(
        actor_id=viewer,
        L1_core={"actor_id": viewer},
        L2_identity={},
        L3_pattern={"family_members": roster or []},
        composed_at_ms=T0_MS,
    )
    bundle.store.write_self(snap, writer_id=SELF_MODEL_WRITER_ID)


def test_add_member_alias_appends_new_alias() -> None:
    bundle = build_bundle(actors=(make_actor("a1"),))
    _seed_roster(
        bundle,
        roster=[
            {"member_id": "riley", "display_name": "Riley", "role": "child"},
        ],
    )

    added = bundle.self_model.add_member_alias("a1", member_id="riley", alias="little demon")
    assert added is True

    res = bundle.self_model.get("a1")
    assert res is not None
    roster = res.snapshot.L3_pattern["family_members"]
    assert roster[0]["aliases"] == ["little demon"]


def test_add_member_alias_idempotent() -> None:
    bundle = build_bundle(actors=(make_actor("a1"),))
    _seed_roster(
        bundle,
        roster=[
            {
                "member_id": "riley",
                "display_name": "Riley",
                "role": "child",
                "aliases": ["lil demon"],
            }
        ],
    )
    added = bundle.self_model.add_member_alias("a1", member_id="riley", alias="lil demon")
    assert added is False
    res = bundle.self_model.get("a1")
    assert res is not None
    assert res.snapshot.L3_pattern["family_members"][0]["aliases"] == ["lil demon"]


def test_add_member_alias_unknown_member_is_noop() -> None:
    bundle = build_bundle(actors=(make_actor("a1"),))
    _seed_roster(
        bundle,
        roster=[{"member_id": "riley", "display_name": "Riley", "role": "child"}],
    )
    added = bundle.self_model.add_member_alias("a1", member_id="ghost", alias="nope")
    assert added is False


def test_add_self_alias_writes_l3_aliases() -> None:
    bundle = build_bundle(actors=(make_actor("a1"),))
    _seed_roster(bundle, roster=[])
    added = bundle.self_model.add_member_alias("a1", member_id="a1", alias="captain")
    assert added is True
    res = bundle.self_model.get("a1")
    assert res is not None
    assert res.snapshot.L3_pattern.get("aliases") == ["captain"]


def test_add_member_alias_rejects_empty_args() -> None:
    bundle = build_bundle(actors=(make_actor("a1"),))
    _seed_roster(bundle, roster=[])
    with pytest.raises(ValueError):
        bundle.self_model.add_member_alias("", member_id="r", alias="x")
    with pytest.raises(ValueError):
        bundle.self_model.add_member_alias("a1", member_id="", alias="x")
    with pytest.raises(ValueError):
        bundle.self_model.add_member_alias("a1", member_id="r", alias="   ")


def test_add_member_alias_unknown_actor_raises() -> None:
    bundle = build_bundle()
    with pytest.raises(UnknownActorError):
        bundle.self_model.add_member_alias("ghost", member_id="riley", alias="x")
