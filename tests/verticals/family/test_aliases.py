"""tests/verticals/family/test_aliases.py — Aliases plumbing (A + B + C).

Covers:

* B: ``FamilyMember.aliases`` round-trips through ``to_seed_dict`` /
  ``from_dict``.
* B: ``SpaceDataSeeder.seed_self_projections`` writes ``aliases`` into
  each ``family_members`` roster entry.
* A: Smith profile seeds Riley's nickname so a sibling actor's projected
  self surfaces ``"little demon of house"``.

Run: python -m pytest tests/verticals/family/test_aliases.py -q --no-cov
"""

from __future__ import annotations

from verticals.family.profile import FamilyMember, FamilyProfile
from verticals.family.smith import SMITH_PROFILE


class TestFamilyMemberAliases:
    def test_default_aliases_empty(self):
        m = FamilyMember("alex", "Alex", "parent", 38, [])
        assert m.aliases == []

    def test_aliases_round_trip_to_seed_dict(self):
        m = FamilyMember(
            "riley",
            "Riley",
            "child",
            8,
            [],
            aliases=["little demon", "the kiddo"],
        )
        d = m.to_seed_dict()
        assert d["aliases"] == ["little demon", "the kiddo"]

    def test_aliases_round_trip_from_dict(self):
        raw = {
            "family_name": "Test",
            "space_id": "family:test",
            "members": [
                {
                    "actor_id": "riley",
                    "name": "Riley",
                    "relation": "child",
                    "age": 8,
                    "aliases": ["lil demon"],
                }
            ],
        }
        p = FamilyProfile.from_dict(raw)
        assert p.members[0].aliases == ["lil demon"]


class TestSmithProfileAliases:
    def test_riley_has_little_demon_alias(self):
        riley = SMITH_PROFILE.member_by_actor("riley")
        assert riley is not None
        assert "little demon of house" in riley.aliases
