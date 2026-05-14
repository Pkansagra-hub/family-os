"""verticals.family.profile — Canonical FamilyProfile dataclass.

JSON schema: data/families/<name>.json
Load:        FamilyProfile.from_json("data/families/smith.json")
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class FamilyMember:
    """Single family member — richer than ``ActorRef`` (selfmodel)."""

    actor_id: str
    name: str
    relation: str  # "parent" | "child" | "grandparent" | "guardian" | ...
    age: int
    device_ids: List[str] = field(default_factory=list)
    occupation: str = ""
    grade: str = ""
    access_level: str = "full_adult"  # "full_adult" | "limited" | "child" | ...
    preferences: Dict[str, Any] = field(default_factory=dict)
    # Nicknames / aliases the family uses for this member. Surfaced into the
    # actor's [family] capsule block so the LLM can resolve casual references
    # (e.g. "little demon of house" -> Riley) without having to guess.
    aliases: List[str] = field(default_factory=list)

    def role(self) -> str:
        """Map ``relation`` → selfmodel ``ActorRef.role`` vocabulary."""
        rel = (self.relation or "").lower()
        if rel in ("parent", "guardian", "grandparent"):
            return "guardian"
        if rel == "child":
            return "child"
        if rel == "guest":
            return "guest"
        return "adult"

    def age_band(self) -> str:
        """Map ``age`` → selfmodel ``ActorRef.age_band``."""
        a = int(self.age or 0)
        if a < 3:
            return "infant"
        if a < 13:
            return "child"
        if a < 18:
            return "teen"
        return "adult"

    def to_seed_dict(self) -> Dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "name": self.name,
            "relation": self.relation,
            "age": self.age,
            "device_ids": list(self.device_ids),
            "occupation": self.occupation,
            "grade": self.grade,
            "access_level": self.access_level,
            "preferences": dict(self.preferences),
            "aliases": list(self.aliases),
        }


@dataclass
class FamilyMemoryEntry:
    """Single preloaded memory from the family's history."""

    memory_type: str  # "episodic" | "semantic" | "procedural"
    content: str
    tags: List[str] = field(default_factory=list)
    source: str = ""
    actor_id: Optional[str] = None

    def to_seed_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "type": self.memory_type,
            "content": self.content,
            "tags": list(self.tags),
            "source": self.source,
        }
        if self.actor_id:
            d["actor_id"] = self.actor_id
        return d


@dataclass
class FamilyProfile:
    """Canonical family profile — the central data object for M13."""

    family_name: str
    space_id: str  # e.g. "family:smith"
    location: str = ""
    timezone: str = "America/Chicago"
    members: List[FamilyMember] = field(default_factory=list)
    devices: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    memories: List[FamilyMemoryEntry] = field(default_factory=list)
    session_config: Dict[str, Any] = field(default_factory=dict)
    dietary_restrictions: List[str] = field(default_factory=list)
    accessibility_needs: List[str] = field(default_factory=list)
    preferred_language: str = "en"

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    def member_by_actor(self, actor_id: str) -> Optional[FamilyMember]:
        for m in self.members:
            if m.actor_id == actor_id:
                return m
        return None

    def member_by_device(self, device_id: str) -> Optional[FamilyMember]:
        entry = self.devices.get(device_id)
        if not entry:
            return None
        actor = entry.get("member_actor_id") or entry.get("actor_id")
        if not actor or actor == "shared":
            return None
        return self.member_by_actor(actor)

    def primary_device(self, actor_id: str) -> str:
        m = self.member_by_actor(actor_id)
        if m and m.device_ids:
            return m.device_ids[0]
        return ""

    def memories_for_actor(self, actor_id: str) -> List[FamilyMemoryEntry]:
        """Memories tagged with ``actor_id`` (case-insensitive) or directly attributed."""
        actor = (actor_id or "").lower()
        out: List[FamilyMemoryEntry] = []
        for entry in self.memories:
            if entry.actor_id and entry.actor_id.lower() == actor:
                out.append(entry)
                continue
            tags_lower = [t.lower() for t in entry.tags]
            if actor in tags_lower:
                out.append(entry)
        return out

    # ------------------------------------------------------------------
    # JSON I/O
    # ------------------------------------------------------------------
    @classmethod
    def from_json(cls, path: str | Path) -> "FamilyProfile":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "FamilyProfile":
        members = [
            FamilyMember(
                actor_id=m["actor_id"],
                name=m.get("name", m["actor_id"]),
                relation=m.get("relation", ""),
                age=int(m.get("age", 0)),
                device_ids=list(m.get("device_ids", [])),
                occupation=m.get("occupation", ""),
                grade=m.get("grade", ""),
                access_level=m.get("access_level", "full_adult"),
                preferences=dict(m.get("preferences", {})),
                aliases=list(m.get("aliases", [])),
            )
            for m in raw.get("members", [])
        ]
        memories = [
            FamilyMemoryEntry(
                memory_type=e.get("type", "semantic"),
                content=e.get("content", ""),
                tags=list(e.get("tags", [])),
                source=e.get("source", ""),
                actor_id=e.get("actor_id"),
            )
            for e in raw.get("memories", [])
        ]
        return cls(
            family_name=raw.get("family_name", ""),
            space_id=raw.get("space_id", "family:default"),
            location=raw.get("location", ""),
            timezone=raw.get("timezone", "America/Chicago"),
            members=members,
            devices=dict(raw.get("devices", {})),
            memories=memories,
            session_config=dict(raw.get("session_config", {})),
            dietary_restrictions=list(raw.get("dietary_restrictions", [])),
            accessibility_needs=list(raw.get("accessibility_needs", [])),
            preferred_language=raw.get("preferred_language", "en"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "family_name": self.family_name,
            "space_id": self.space_id,
            "location": self.location,
            "timezone": self.timezone,
            "preferred_language": self.preferred_language,
            "dietary_restrictions": list(self.dietary_restrictions),
            "accessibility_needs": list(self.accessibility_needs),
            "session_config": dict(self.session_config),
            "members": [m.to_seed_dict() for m in self.members],
            "devices": {k: dict(v) for k, v in self.devices.items()},
            "memories": [e.to_seed_dict() for e in self.memories],
        }
