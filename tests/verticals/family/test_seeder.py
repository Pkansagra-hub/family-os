"""tests/verticals/family/test_seeder.py — M13 SpaceDataSeeder tests.

Run: python -m pytest tests/verticals/family/test_seeder.py -q --no-cov
"""

from __future__ import annotations

import pytest

from k1.selfmodel.adapters.memory_projection_store import InMemoryProjectionStore
from k1.selfmodel.contracts.space_graph import SpaceGraphSnapshot
from k1.selfmodel.kernel import build_self_model_bundle, build_self_model_handle
from k1.selfmodel.service.space_graph import SPACE_GRAPH_WRITER_ID
from verticals.family.seeder import SpaceDataSeeder
from verticals.family.smith import SMITH_PROFILE


# ---------------------------------------------------------------------------
# Stub bundle that exposes only the fields the seeder touches.
# ---------------------------------------------------------------------------
class _StubBundle:
    def __init__(self) -> None:
        self.store = InMemoryProjectionStore(allowed_writers=(SPACE_GRAPH_WRITER_ID,))


class TestBuildSeedMemories:
    def test_returns_at_least_4_synthetic_plus_profile_memories(self):
        seeder = SpaceDataSeeder()
        out = seeder.build_seed_memories(SMITH_PROFILE, device_id="alex_phone")
        assert len(out) >= 4 + len(SMITH_PROFILE.memories)

    def test_active_member_resolves_from_device(self):
        seeder = SpaceDataSeeder()
        out = seeder.build_seed_memories(SMITH_PROFILE, device_id="alex_phone")
        active = next((m for m in out if "active_member" in m.get("tags", [])), None)
        assert active is not None
        assert "Alex" in active["content"]
        assert active.get("actor_id") == "alex"

    def test_unknown_device_yields_unknown_speaker(self):
        seeder = SpaceDataSeeder()
        out = seeder.build_seed_memories(SMITH_PROFILE, device_id="bogus")
        active = next((m for m in out if "active_member" in m.get("tags", [])), None)
        assert active is not None
        assert "unknown" in active["content"].lower()

    def test_each_entry_has_required_keys(self):
        seeder = SpaceDataSeeder()
        out = seeder.build_seed_memories(SMITH_PROFILE, device_id="alex_phone")
        for entry in out:
            assert "type" in entry
            assert "content" in entry
            assert "tags" in entry
            assert "source" in entry


class TestSeedSpaceProjection:
    def test_writes_snapshot_with_all_members(self):
        seeder = SpaceDataSeeder()
        bundle = _StubBundle()
        wrote = seeder.seed_space_projection(bundle, SMITH_PROFILE)
        assert wrote is True
        snap, _ = bundle.store.read_space(SMITH_PROFILE.space_id)
        assert isinstance(snap, SpaceGraphSnapshot)
        assert len(snap.members) == len(SMITH_PROFILE.members)

    def test_parent_of_edges_built(self):
        seeder = SpaceDataSeeder()
        bundle = _StubBundle()
        seeder.seed_space_projection(bundle, SMITH_PROFILE)
        snap, _ = bundle.store.read_space(SMITH_PROFILE.space_id)
        edges = [(e.from_member, e.to_member, e.kind) for e in snap.relations]
        # Two parents × one child (Riley) = 2 parent_of edges
        parent_of = [e for e in edges if e[2] == "parent_of"]
        assert len(parent_of) == 2
        assert ("alex", "riley", "parent_of") in edges
        assert ("jordan", "riley", "parent_of") in edges

    def test_idempotent_skip_on_second_call(self):
        seeder = SpaceDataSeeder()
        bundle = _StubBundle()
        first = seeder.seed_space_projection(bundle, SMITH_PROFILE)
        second = seeder.seed_space_projection(bundle, SMITH_PROFILE)
        assert first is True
        assert second is False

    def test_raises_on_bundle_none(self):
        seeder = SpaceDataSeeder()
        with pytest.raises(ValueError):
            seeder.seed_space_projection(None, SMITH_PROFILE)


class TestSeedSelfProjections:
    def test_normalizes_roles_and_seeds_family_consent(self):
        seeder = SpaceDataSeeder()
        bundle = build_self_model_bundle(
            space_id=SMITH_PROFILE.space_id,
            publish_startup=False,
        )

        assert seeder.seed_self_projections(bundle, SMITH_PROFILE) == len(SMITH_PROFILE.members)

        alex, _ = bundle.store.read_self("alex")
        assert alex is not None
        assert alex.L1_core["role"] == "guardian"
        assert alex.L2_identity["role_in_family"] == "guardian"
        assert alex.L2_identity["family_relation"] == "parent"
        assert set(alex.L1_core["consent_posture"]["family"]) >= {
            "display_name",
            "role",
            "age_band",
        }

    def test_seeded_selfmodel_renders_typed_space_and_guardian_conscience(self):
        seeder = SpaceDataSeeder()
        bundle = build_self_model_bundle(
            space_id=SMITH_PROFILE.space_id,
            publish_startup=False,
        )
        seeder.seed_space_projection(bundle, SMITH_PROFILE)
        seeder.seed_self_projections(bundle, SMITH_PROFILE)
        handle = build_self_model_handle(
            bundle,
            session_id="web-test",
            actor_id="alex",
            device_id="alex_phone",
            situation_kind="caregiver_context_briefing",
        )

        frame = handle.current_frame()
        capsule = handle.render_capsule()

        assert frame.self_view is not None
        assert frame.self_view.role == "guardian"
        assert "riley" in frame.visibility.can_see_members
        assert any(other.member_id == "riley" for other in frame.relations.projected_others)
        assert capsule is not None
        assert capsule.space_graph_block.startswith("[space]")
        assert "Riley" in capsule.space_graph_block
        assert "must_ask=send_message" in capsule.conscience_block
        assert "forbidden=prescribe_medication" in capsule.conscience_block


class TestSeedK0Memories:
    @pytest.mark.asyncio
    async def test_no_op_when_bridge_none(self):
        seeder = SpaceDataSeeder()
        n = await seeder.seed_k0_memories(None, SMITH_PROFILE)
        assert n == 0

    @pytest.mark.asyncio
    async def test_submits_envelopes_when_bridge_present(self):
        captured = []

        class _Bridge:
            def submit_batch(self, envelopes):
                captured.extend(envelopes)
                return None

        seeder = SpaceDataSeeder()
        n = await seeder.seed_k0_memories(_Bridge(), SMITH_PROFILE)
        assert n == len(SMITH_PROFILE.memories)
        assert len(captured) == len(SMITH_PROFILE.memories)
