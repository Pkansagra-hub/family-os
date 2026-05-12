"""verticals.family — FamilyProfile schema and seeding utilities.

Lives in ``verticals/``, NOT ``k1/`` (see ADR-3). Production replacement
for ``poc.k1_poc.demo.smith_family`` + ``poc.k1_poc.demo.preloaded_memories``.

Main classes:
    FamilyProfile     — canonical family data model
    FamilyMember      — single member (richer than ``ActorRef``)
    FamilyMemoryEntry — single preloaded memory
    SpaceDataSeeder   — converts FamilyProfile → KernelConfig.seed_memories + self-model
"""

from verticals.family.profile import FamilyMember, FamilyMemoryEntry, FamilyProfile
from verticals.family.seeder import SpaceDataSeeder

__all__ = [
    "FamilyProfile",
    "FamilyMember",
    "FamilyMemoryEntry",
    "SpaceDataSeeder",
]
