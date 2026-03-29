"""Demo script showing improved generator outputs."""

from k0.modules.consolidation.algorithms.text_generators.episodic import (
    EpisodicTextGenerator,
)
from k0.modules.consolidation.algorithms.text_generators.kg_entity import (
    KGEntityTextGenerator,
)
from k0.modules.consolidation.algorithms.text_generators.prospective import (
    ProspectiveTextGenerator,
)
from k0.modules.consolidation.algorithms.text_generators.social import (
    SocialTextGenerator,
)


def main():
    print("=== EPISODIC (st_epi) ===")
    gen = EpisodicTextGenerator()
    result = gen.generate(
        {
            "episode_summary": "Routine at Home",
            "start_time_utc": 1768496936000,
            "end_time_utc": 1768496949000,  # 13 seconds
            "primary_location": "Home",
            "participants_json": '["Mom", "Panda", "Prince"]',
        }
    )
    print("BEFORE: Routine at Home (0h) episode. Context: Home, with Panda and 1 others")
    print(f"AFTER:  {result.embedding_text}")

    print()
    print("=== SOCIAL (st_social) ===")
    gen = SocialTextGenerator()
    result = gen.generate(
        {
            "actor_a_id": "Prince",
            "actor_b_id": "Mom",
            "relationship_type": "FRIEND",
            "relationship_strength": 0.65,
            "typical_activities_json": '["routine"]',
        }
    )
    print("BEFORE: Prince is friend of Mom: close relationship, shared activities include routine")
    print(f"AFTER:  {result.embedding_text}")

    print()
    print("=== PROSPECTIVE (st_prospective) ===")
    gen = ProspectiveTextGenerator()
    result = gen.generate(
        {
            "intention_description": "take Mom to the botanical garden",
            "status": "ACTIVE",
        }
    )
    print("BEFORE: Intention: take Mom to the botanical garden. Context: Status: pending")
    print(f"AFTER:  {result.embedding_text}")

    print()
    print("=== KG ENTITY (st_kg_dom) ===")
    gen = KGEntityTextGenerator()
    result = gen.generate(
        {
            "entity_type": "FAMILY_MEMBER",
            "canonical_name": "parents",
            "aliases_json": '["parents"]',
        }
    )
    print("BEFORE: Family Member: parents (also known as parents)")
    print(f"AFTER:  {result.embedding_text}")


if __name__ == "__main__":
    main()
