"""tests/verticals/family/test_profile.py — M13 FamilyProfile schema tests.

Run: python -m pytest tests/verticals/family/test_profile.py -q --no-cov
"""

from __future__ import annotations

from verticals.family.profile import FamilyMember, FamilyMemoryEntry, FamilyProfile
from verticals.family.smith import SMITH_PROFILE


class TestFamilyMember:
    def test_age_band_child(self):
        m = FamilyMember("riley", "Riley", "child", 8, [])
        assert m.age_band() == "child"

    def test_age_band_teen(self):
        m = FamilyMember("teen", "Teen", "child", 15, [])
        assert m.age_band() == "teen"

    def test_age_band_adult(self):
        m = FamilyMember("alex", "Alex", "parent", 38, [])
        assert m.age_band() == "adult"

    def test_age_band_infant(self):
        m = FamilyMember("baby", "Baby", "child", 1, [])
        assert m.age_band() == "infant"

    def test_role_parent_maps_to_guardian(self):
        m = FamilyMember("alex", "Alex", "parent", 38, [])
        assert m.role() == "guardian"

    def test_role_grandparent_maps_to_guardian(self):
        m = FamilyMember("nana", "Nana", "grandparent", 67, [])
        assert m.role() == "guardian"

    def test_role_child(self):
        m = FamilyMember("riley", "Riley", "child", 8, [])
        assert m.role() == "child"

    def test_to_seed_dict_has_required_keys(self):
        m = FamilyMember("alex", "Alex", "parent", 38, ["alex_phone"])
        d = m.to_seed_dict()
        assert d["actor_id"] == "alex"
        assert d["name"] == "Alex"
        assert d["device_ids"] == ["alex_phone"]
        assert "preferences" in d


class TestFamilyMemoryEntry:
    def test_to_seed_dict_minimal(self):
        e = FamilyMemoryEntry("semantic", "Hello", ["test"], "src")
        d = e.to_seed_dict()
        assert d["type"] == "semantic"
        assert d["content"] == "Hello"
        assert d["tags"] == ["test"]
        assert d["source"] == "src"
        assert "actor_id" not in d  # only set when provided

    def test_to_seed_dict_with_actor(self):
        e = FamilyMemoryEntry("episodic", "X", [], "", actor_id="alex")
        d = e.to_seed_dict()
        assert d["actor_id"] == "alex"


class TestSmithProfile:
    def test_has_4_members(self):
        assert len(SMITH_PROFILE.members) == 4

    def test_member_actor_ids(self):
        ids = {m.actor_id for m in SMITH_PROFILE.members}
        assert ids == {"alex", "jordan", "riley", "nana_liz"}

    def test_has_5_devices(self):
        assert len(SMITH_PROFILE.devices) == 5

    def test_has_at_least_19_memories(self):
        assert len(SMITH_PROFILE.memories) >= 19

    def test_space_id(self):
        assert SMITH_PROFILE.space_id == "family:smith"

    def test_member_by_device_alex_phone(self):
        m = SMITH_PROFILE.member_by_device("alex_phone")
        assert m is not None and m.actor_id == "alex"

    def test_member_by_device_jordan_phone(self):
        m = SMITH_PROFILE.member_by_device("jordan_phone")
        assert m is not None and m.actor_id == "jordan"

    def test_member_by_device_shared_hub_none(self):
        m = SMITH_PROFILE.member_by_device("kitchen_hub")
        assert m is None  # shared device — no single owner

    def test_member_by_device_unknown_returns_none(self):
        assert SMITH_PROFILE.member_by_device("nope") is None

    def test_member_by_actor(self):
        m = SMITH_PROFILE.member_by_actor("riley")
        assert m is not None and m.name == "Riley"

    def test_memories_for_actor_alex_nonempty(self):
        assert len(SMITH_PROFILE.memories_for_actor("alex")) > 0

    def test_primary_device_alex(self):
        assert SMITH_PROFILE.primary_device("alex") in ("alex_phone", "alex_laptop")

    def test_primary_device_riley_empty(self):
        # Riley has no device — parents relay.
        assert SMITH_PROFILE.primary_device("riley") == ""


class TestJsonRoundtrip:
    def test_roundtrip_preserves_members_and_memories(self):
        raw = SMITH_PROFILE.to_dict()
        rebuilt = FamilyProfile.from_dict(raw)
        assert len(rebuilt.members) == len(SMITH_PROFILE.members)
        assert len(rebuilt.memories) == len(SMITH_PROFILE.memories)
        assert rebuilt.space_id == SMITH_PROFILE.space_id
        assert rebuilt.family_name == SMITH_PROFILE.family_name
