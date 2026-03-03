"""Phase 6: 120 Hand-Crafted Validation Scenarios.

Each scenario defines an R1SignalVector with manually-set signals and an
expected importance tier. Scenarios are grouped thematically to cover the
full breadth of FamilyOS family events.

Pass criteria (scaled from original 15-scenario plan):
  - Scenario 1 (Sharvi's first word): score > 0.85  [HARD FAIL]
  - Scenario 2 (breakfast alone):     score < 0.25  [HARD FAIL]
  - Overall: >= 85% tier match (i.e. <= 18 mismatches out of 120)

Usage:
    python -m poc.r1_weight_research.scenarios [--config NAME] [--lambda FLOAT]
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import Dict

from .config import ALL_CONFIGS, CONFIG_A, CONFIG_B, CONFIG_C, CONFIG_D, WeightConfig
from .scorer import compute_importance, score_to_tier
from .signal_derive import R1SignalVector

# ---------------------------------------------------------------------------
# Scenario definition
# ---------------------------------------------------------------------------


@dataclass
class Scenario:
    """One hand-crafted test case."""

    id: int
    name: str
    category: str
    vec: R1SignalVector
    expected_tier: str  # CRITICAL / HIGH / MEDIUM_HIGH / MEDIUM / LOW_MEDIUM / LOW
    acceptable_tiers: list[str]  # tiers that count as "pass" (allows +-1 tolerance)
    notes: str = ""


def _v(
    event_id: str,
    sent: float = 0.0,
    val: float = 0.0,
    aro: float = 0.0,
    dom: float = 0.5,
    surprise: float = 0.0,
    participants: int = 1,
    intimacy: str = "LOW",
    activity: str = "message",
    intent: str = "other",
    novelty: str = "EXPECTED",
    elab: str = "MENTION",
    temporal: str = "PAST",
    identity: float = 0.0,
    reliability: float = 0.95,
    words: int = 10,
) -> R1SignalVector:
    """Shorthand constructor for scenario vectors."""
    return R1SignalVector(
        event_id=event_id,
        sentiment_score=sent,
        affect_valence=val,
        affect_arousal=aro,
        affect_dominance=dom,
        surprise_level=surprise,
        num_participants=participants,
        social_intimacy=intimacy,
        activity_type=activity,
        intent=intent,
        novelty=novelty,
        elaboration_depth=elab,
        temporal_orientation=temporal,
        identity_relevance=identity,
        source_type="user_stated",
        source_reliability=reliability,
        narrative_is_goal_event=False,
        narrative_arc_position="EXPOSITION",
        memory_tier="routine",
        proxy_tier="",
        word_count=words,
    )


# ===================================================================
# SCENARIO DEFINITIONS (120 scenarios, 13 categories)
# ===================================================================


def build_all_scenarios() -> list[Scenario]:
    """Build all 120 hand-crafted validation scenarios."""
    scenarios: list[Scenario] = []

    # ------------------------------------------------------------------
    # CATEGORY 1: CRITICAL MILESTONES (10 scenarios)
    # These are the most important family memories. System MUST score
    # them at or near the top.
    # ------------------------------------------------------------------

    scenarios.append(
        Scenario(
            id=1,
            name="Sharvi's first word -- Dad present, milestone",
            category="CRITICAL_MILESTONE",
            vec=_v(
                "s001",
                sent=0.90,
                val=0.90,
                aro=0.90,
                surprise=1.0,
                participants=3,
                intimacy="HIGH",
                activity="milestone",
                intent="share_news",
                novelty="SURPRISING",
                elab="DEEPLY_PROCESSED",
                identity=0.80,
                words=60,
            ),
            expected_tier="CRITICAL",
            acceptable_tiers=["CRITICAL"],
            notes="HARD REQUIREMENT: must score > 0.85",
        )
    )

    scenarios.append(
        Scenario(
            id=2,
            name="Child's first steps -- whole family watching",
            category="CRITICAL_MILESTONE",
            vec=_v(
                "s002",
                sent=0.90,
                val=0.85,
                aro=0.85,
                surprise=1.0,
                participants=4,
                intimacy="HIGH",
                activity="milestone",
                intent="share_news",
                novelty="SURPRISING",
                elab="ELABORATED",
                identity=0.70,
                words=45,
            ),
            expected_tier="CRITICAL",
            acceptable_tiers=["CRITICAL"],
        )
    )

    scenarios.append(
        Scenario(
            id=3,
            name="High school graduation ceremony",
            category="CRITICAL_MILESTONE",
            vec=_v(
                "s003",
                sent=0.85,
                val=0.80,
                aro=0.70,
                surprise=0.0,
                participants=5,
                intimacy="HIGH",
                activity="celebration",
                intent="share_news",
                novelty="NOVEL",
                elab="ELABORATED",
                identity=0.60,
                words=50,
            ),
            expected_tier="CRITICAL",
            acceptable_tiers=["CRITICAL", "HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=4,
            name="Wedding anniversary -- 25th, landmark",
            category="CRITICAL_MILESTONE",
            vec=_v(
                "s004",
                sent=0.90,
                val=0.85,
                aro=0.60,
                surprise=0.0,
                participants=2,
                intimacy="HIGH",
                activity="celebration",
                intent="reflect",
                novelty="NOVEL",
                elab="DEEPLY_PROCESSED",
                identity=0.50,
                words=70,
            ),
            expected_tier="CRITICAL",
            acceptable_tiers=["CRITICAL", "HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=5,
            name="Birth of a new baby in the family",
            category="CRITICAL_MILESTONE",
            vec=_v(
                "s005",
                sent=0.90,
                val=0.90,
                aro=0.95,
                surprise=0.80,
                participants=4,
                intimacy="HIGH",
                activity="milestone",
                intent="share_news",
                novelty="SURPRISING",
                elab="DEEPLY_PROCESSED",
                identity=0.90,
                words=80,
            ),
            expected_tier="CRITICAL",
            acceptable_tiers=["CRITICAL"],
        )
    )

    scenarios.append(
        Scenario(
            id=6,
            name="Child's college acceptance letter",
            category="CRITICAL_MILESTONE",
            vec=_v(
                "s006",
                sent=0.85,
                val=0.80,
                aro=0.80,
                surprise=0.70,
                participants=3,
                intimacy="HIGH",
                activity="milestone",
                intent="share_news",
                novelty="SURPRISING",
                elab="ELABORATED",
                identity=0.70,
                words=40,
            ),
            expected_tier="CRITICAL",
            acceptable_tiers=["CRITICAL", "HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=7,
            name="Adopting a pet -- family decision",
            category="CRITICAL_MILESTONE",
            vec=_v(
                "s007",
                sent=0.80,
                val=0.75,
                aro=0.70,
                surprise=0.50,
                participants=4,
                intimacy="HIGH",
                activity="celebration",
                intent="share_news",
                novelty="NOVEL",
                elab="ELABORATED",
                identity=0.40,
                words=35,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["CRITICAL", "HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=8,
            name="Grandparent's 80th birthday party",
            category="CRITICAL_MILESTONE",
            vec=_v(
                "s008",
                sent=0.85,
                val=0.80,
                aro=0.60,
                surprise=0.0,
                participants=8,
                intimacy="MEDIUM",
                activity="celebration",
                intent="share_news",
                novelty="NOVEL",
                elab="ELABORATED",
                identity=0.50,
                words=45,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["CRITICAL", "HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=9,
            name="First day of kindergarten",
            category="CRITICAL_MILESTONE",
            vec=_v(
                "s009",
                sent=0.70,
                val=0.60,
                aro=0.70,
                surprise=0.30,
                participants=2,
                intimacy="HIGH",
                activity="milestone",
                intent="share_news",
                novelty="NOVEL",
                elab="ELABORATED",
                identity=0.60,
                words=35,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["CRITICAL", "HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=10,
            name="Family tradition -- annual holiday ritual",
            category="CRITICAL_MILESTONE",
            vec=_v(
                "s010",
                sent=0.75,
                val=0.70,
                aro=0.50,
                surprise=0.0,
                participants=5,
                intimacy="HIGH",
                activity="celebration",
                intent="reflect",
                novelty="EXPECTED",
                elab="ELABORATED",
                identity=0.60,
                words=40,
            ),
            expected_tier="CRITICAL",
            acceptable_tiers=["CRITICAL", "HIGH"],
            notes="Celebration + 5 people + elaborated -> high multiplier stack",
        )
    )

    # ------------------------------------------------------------------
    # CATEGORY 2: HIGH-EMOTION EVENTS (10 scenarios)
    # Strong emotional events -- both positive and negative.
    # ------------------------------------------------------------------

    scenarios.append(
        Scenario(
            id=11,
            name="Getting fired from job -- solo, devastated",
            category="HIGH_EMOTION",
            vec=_v(
                "s011",
                sent=-0.90,
                val=-0.80,
                aro=0.90,
                surprise=1.0,
                participants=1,
                intimacy="LOW",
                activity="message",
                intent="express_feeling",
                novelty="SURPRISING",
                elab="ELABORATED",
                identity=0.50,
                words=50,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["CRITICAL", "HIGH"],
            notes="High emotion + surprise but solo",
        )
    )

    scenarios.append(
        Scenario(
            id=12,
            name="Emergency room visit -- health scare",
            category="HIGH_EMOTION",
            vec=_v(
                "s012",
                sent=-0.90,
                val=-0.90,
                aro=1.0,
                surprise=1.0,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="share_news",
                novelty="SURPRISING",
                elab="DEEPLY_PROCESSED",
                identity=0.80,
                words=60,
            ),
            expected_tier="CRITICAL",
            acceptable_tiers=["CRITICAL"],
        )
    )

    scenarios.append(
        Scenario(
            id=13,
            name="Child diagnosed with chronic illness",
            category="HIGH_EMOTION",
            vec=_v(
                "s013",
                sent=-0.90,
                val=-0.85,
                aro=0.85,
                surprise=0.80,
                participants=3,
                intimacy="HIGH",
                activity="message",
                intent="seek_advice",
                novelty="SURPRISING",
                elab="DEEPLY_PROCESSED",
                identity=0.90,
                words=70,
            ),
            expected_tier="CRITICAL",
            acceptable_tiers=["CRITICAL", "HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=14,
            name="Reconciliation after major family fight",
            category="HIGH_EMOTION",
            vec=_v(
                "s014",
                sent=0.60,
                val=0.50,
                aro=0.60,
                surprise=0.30,
                participants=3,
                intimacy="HIGH",
                activity="message",
                intent="reflect",
                novelty="NOVEL",
                elab="ELABORATED",
                identity=0.40,
                words=45,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=15,
            name="Death of a close family member",
            category="HIGH_EMOTION",
            vec=_v(
                "s015",
                sent=-0.90,
                val=-0.90,
                aro=0.80,
                surprise=0.50,
                participants=4,
                intimacy="HIGH",
                activity="message",
                intent="reflect",
                novelty="SURPRISING",
                elab="DEEPLY_PROCESSED",
                identity=0.90,
                words=80,
            ),
            expected_tier="CRITICAL",
            acceptable_tiers=["CRITICAL"],
        )
    )

    scenarios.append(
        Scenario(
            id=16,
            name="Winning local sports championship",
            category="HIGH_EMOTION",
            vec=_v(
                "s016",
                sent=0.85,
                val=0.80,
                aro=0.85,
                surprise=0.60,
                participants=3,
                intimacy="HIGH",
                activity="celebration",
                intent="share_news",
                novelty="SURPRISING",
                elab="ELABORATED",
                identity=0.50,
                words=40,
            ),
            expected_tier="CRITICAL",
            acceptable_tiers=["CRITICAL", "HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=17,
            name="Panic attack at work -- distressing call home",
            category="HIGH_EMOTION",
            vec=_v(
                "s017",
                sent=-0.80,
                val=-0.70,
                aro=0.90,
                surprise=0.50,
                participants=1,
                intimacy="LOW",
                activity="message",
                intent="express_feeling",
                novelty="NOVEL",
                elab="DISCUSSED",
                identity=0.30,
                words=25,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=18,
            name="Surprise pregnancy announcement",
            category="HIGH_EMOTION",
            vec=_v(
                "s018",
                sent=0.90,
                val=0.85,
                aro=0.90,
                surprise=1.0,
                participants=2,
                intimacy="HIGH",
                activity="milestone",
                intent="share_news",
                novelty="SURPRISING",
                elab="ELABORATED",
                identity=0.80,
                words=40,
            ),
            expected_tier="CRITICAL",
            acceptable_tiers=["CRITICAL"],
        )
    )

    scenarios.append(
        Scenario(
            id=19,
            name="Teen caught shoplifting -- shame and anger",
            category="HIGH_EMOTION",
            vec=_v(
                "s019",
                sent=-0.80,
                val=-0.75,
                aro=0.80,
                surprise=0.80,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="seek_advice",
                novelty="SURPRISING",
                elab="ELABORATED",
                identity=0.60,
                words=50,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["CRITICAL", "HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=20,
            name="Elderly parent takes first walk after surgery",
            category="HIGH_EMOTION",
            vec=_v(
                "s020",
                sent=0.80,
                val=0.75,
                aro=0.60,
                surprise=0.40,
                participants=3,
                intimacy="HIGH",
                activity="message",
                intent="share_news",
                novelty="NOVEL",
                elab="ELABORATED",
                identity=0.70,
                words=40,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["CRITICAL", "HIGH"],
        )
    )

    # ------------------------------------------------------------------
    # CATEGORY 3: SOCIAL FAMILY EVENTS (10 scenarios)
    # Multi-participant events with moderate emotional intensity.
    # ------------------------------------------------------------------

    scenarios.append(
        Scenario(
            id=21,
            name="Family dinner at restaurant -- normal weeknight",
            category="SOCIAL_FAMILY",
            vec=_v(
                "s021",
                sent=0.50,
                val=0.40,
                aro=0.30,
                surprise=0.0,
                participants=4,
                intimacy="HIGH",
                activity="message",
                intent="log_memory",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.30,
                words=15,
            ),
            expected_tier="MEDIUM",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=22,
            name="School play -- child performing, family watching",
            category="SOCIAL_FAMILY",
            vec=_v(
                "s022",
                sent=0.80,
                val=0.70,
                aro=0.70,
                surprise=0.0,
                participants=5,
                intimacy="HIGH",
                activity="celebration",
                intent="share_news",
                novelty="NOVEL",
                elab="ELABORATED",
                identity=0.50,
                words=40,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["CRITICAL", "HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=23,
            name="Sunday picnic in the park -- extended family",
            category="SOCIAL_FAMILY",
            vec=_v(
                "s023",
                sent=0.60,
                val=0.50,
                aro=0.40,
                surprise=0.0,
                participants=8,
                intimacy="MEDIUM",
                activity="message",
                intent="log_memory",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.30,
                words=20,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=24,
            name="Game night with kids -- lots of laughter",
            category="SOCIAL_FAMILY",
            vec=_v(
                "s024",
                sent=0.70,
                val=0.65,
                aro=0.60,
                surprise=0.0,
                participants=4,
                intimacy="HIGH",
                activity="message",
                intent="log_memory",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.20,
                words=18,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=25,
            name="Thanksgiving dinner -- traditional family gathering",
            category="SOCIAL_FAMILY",
            vec=_v(
                "s025",
                sent=0.75,
                val=0.70,
                aro=0.50,
                surprise=0.0,
                participants=10,
                intimacy="MEDIUM",
                activity="celebration",
                intent="log_memory",
                novelty="EXPECTED",
                elab="ELABORATED",
                identity=0.50,
                words=35,
            ),
            expected_tier="CRITICAL",
            acceptable_tiers=["CRITICAL", "HIGH"],
            notes="10 participants + celebration multiplier -> CRITICAL is justified",
        )
    )

    scenarios.append(
        Scenario(
            id=26,
            name="Weekend soccer game -- cheering for child",
            category="SOCIAL_FAMILY",
            vec=_v(
                "s026",
                sent=0.60,
                val=0.55,
                aro=0.60,
                surprise=0.0,
                participants=3,
                intimacy="HIGH",
                activity="message",
                intent="share_news",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.40,
                words=20,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=27,
            name="Visiting grandparents -- normal weekend trip",
            category="SOCIAL_FAMILY",
            vec=_v(
                "s027",
                sent=0.50,
                val=0.45,
                aro=0.30,
                surprise=0.0,
                participants=5,
                intimacy="MEDIUM",
                activity="message",
                intent="log_memory",
                novelty="EXPECTED",
                elab="MENTION",
                identity=0.30,
                words=12,
            ),
            expected_tier="MEDIUM",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=28,
            name="PTA meeting -- routine, minimal emotion",
            category="SOCIAL_FAMILY",
            vec=_v(
                "s028",
                sent=0.10,
                val=0.10,
                aro=0.20,
                surprise=0.0,
                participants=2,
                intimacy="LOW",
                activity="calendar",
                intent="log_memory",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.10,
                words=10,
            ),
            expected_tier="LOW_MEDIUM",
            acceptable_tiers=["MEDIUM", "LOW_MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=29,
            name="Neighbor's BBQ -- friendly but not deep",
            category="SOCIAL_FAMILY",
            vec=_v(
                "s029",
                sent=0.40,
                val=0.35,
                aro=0.30,
                surprise=0.0,
                participants=6,
                intimacy="LOW",
                activity="message",
                intent="log_memory",
                novelty="EXPECTED",
                elab="MENTION",
                identity=0.0,
                words=10,
            ),
            expected_tier="MEDIUM",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=30,
            name="Religious ceremony -- baptism of cousin's child",
            category="SOCIAL_FAMILY",
            vec=_v(
                "s030",
                sent=0.70,
                val=0.60,
                aro=0.40,
                surprise=0.0,
                participants=6,
                intimacy="MEDIUM",
                activity="celebration",
                intent="log_memory",
                novelty="NOVEL",
                elab="ELABORATED",
                identity=0.40,
                words=30,
            ),
            expected_tier="CRITICAL",
            acceptable_tiers=["CRITICAL", "HIGH"],
            notes="Celebration + NOVEL + 6 people + elaborated -> multiplier stack",
        )
    )

    # ------------------------------------------------------------------
    # CATEGORY 4: EVERYDAY FAMILY MOMENTS (15 scenarios)
    # The warm everyday stuff -- reading, cooking, helping with homework.
    # ------------------------------------------------------------------

    scenarios.append(
        Scenario(
            id=31,
            name="Reading bedtime story to child -- routine",
            category="EVERYDAY_FAMILY",
            vec=_v(
                "s031",
                sent=0.50,
                val=0.40,
                aro=0.20,
                surprise=0.0,
                participants=2,
                intimacy="HIGH",
                activity="routine",
                intent="log_memory",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.20,
                words=10,
            ),
            expected_tier="MEDIUM",
            acceptable_tiers=["MEDIUM", "LOW_MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=32,
            name="Helping child with math homework",
            category="EVERYDAY_FAMILY",
            vec=_v(
                "s032",
                sent=0.30,
                val=0.20,
                aro=0.30,
                surprise=0.0,
                participants=2,
                intimacy="HIGH",
                activity="routine",
                intent="log_memory",
                novelty="ROUTINE",
                elab="DISCUSSED",
                identity=0.20,
                words=15,
            ),
            expected_tier="LOW_MEDIUM",
            acceptable_tiers=["MEDIUM", "LOW_MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=33,
            name="Cooking dinner together -- weeknight",
            category="EVERYDAY_FAMILY",
            vec=_v(
                "s033",
                sent=0.40,
                val=0.35,
                aro=0.30,
                surprise=0.0,
                participants=3,
                intimacy="HIGH",
                activity="routine",
                intent="log_memory",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.10,
                words=12,
            ),
            expected_tier="LOW_MEDIUM",
            acceptable_tiers=["MEDIUM", "LOW_MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=34,
            name="Walking the dog together in morning",
            category="EVERYDAY_FAMILY",
            vec=_v(
                "s034",
                sent=0.30,
                val=0.25,
                aro=0.20,
                surprise=0.0,
                participants=2,
                intimacy="HIGH",
                activity="routine",
                intent="log_memory",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=8,
            ),
            expected_tier="LOW_MEDIUM",
            acceptable_tiers=["LOW_MEDIUM", "LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=35,
            name="Playing catch in the backyard",
            category="EVERYDAY_FAMILY",
            vec=_v(
                "s035",
                sent=0.50,
                val=0.45,
                aro=0.40,
                surprise=0.0,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="log_memory",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.20,
                words=10,
            ),
            expected_tier="MEDIUM",
            acceptable_tiers=["MEDIUM", "LOW_MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=36,
            name="Family movie night -- cozy Friday",
            category="EVERYDAY_FAMILY",
            vec=_v(
                "s036",
                sent=0.50,
                val=0.45,
                aro=0.30,
                surprise=0.0,
                participants=4,
                intimacy="HIGH",
                activity="message",
                intent="log_memory",
                novelty="EXPECTED",
                elab="MENTION",
                identity=0.10,
                words=12,
            ),
            expected_tier="MEDIUM",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=37,
            name="Driving kids to school -- mundane morning",
            category="EVERYDAY_FAMILY",
            vec=_v(
                "s037",
                sent=0.10,
                val=0.10,
                aro=0.10,
                surprise=0.0,
                participants=3,
                intimacy="HIGH",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=5,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW_MEDIUM", "LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=38,
            name="Bathtime with toddler -- playful routine",
            category="EVERYDAY_FAMILY",
            vec=_v(
                "s038",
                sent=0.50,
                val=0.45,
                aro=0.40,
                surprise=0.0,
                participants=2,
                intimacy="HIGH",
                activity="routine",
                intent="log_memory",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.20,
                words=10,
            ),
            expected_tier="LOW_MEDIUM",
            acceptable_tiers=["MEDIUM", "LOW_MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=39,
            name="Watching TV together -- regular evening",
            category="EVERYDAY_FAMILY",
            vec=_v(
                "s039",
                sent=0.20,
                val=0.15,
                aro=0.15,
                surprise=0.0,
                participants=3,
                intimacy="HIGH",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=6,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW_MEDIUM", "LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=40,
            name="Child's art project -- proud moment",
            category="EVERYDAY_FAMILY",
            vec=_v(
                "s040",
                sent=0.60,
                val=0.55,
                aro=0.40,
                surprise=0.20,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="share_news",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.30,
                words=20,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=41,
            name="Teaching child to ride a bike",
            category="EVERYDAY_FAMILY",
            vec=_v(
                "s041",
                sent=0.70,
                val=0.65,
                aro=0.60,
                surprise=0.30,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="share_news",
                novelty="NOVEL",
                elab="ELABORATED",
                identity=0.40,
                words=30,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=42,
            name="Child lost a tooth -- excited",
            category="EVERYDAY_FAMILY",
            vec=_v(
                "s042",
                sent=0.60,
                val=0.55,
                aro=0.50,
                surprise=0.40,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="share_news",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.30,
                words=18,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=43,
            name="Making breakfast together on Saturday",
            category="EVERYDAY_FAMILY",
            vec=_v(
                "s043",
                sent=0.40,
                val=0.35,
                aro=0.25,
                surprise=0.0,
                participants=3,
                intimacy="HIGH",
                activity="routine",
                intent="log_memory",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.10,
                words=10,
            ),
            expected_tier="LOW_MEDIUM",
            acceptable_tiers=["MEDIUM", "LOW_MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=44,
            name="Child shows report card -- good grades",
            category="EVERYDAY_FAMILY",
            vec=_v(
                "s044",
                sent=0.70,
                val=0.65,
                aro=0.50,
                surprise=0.20,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="share_news",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.40,
                words=20,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=45,
            name="Building LEGO set with child on rainy day",
            category="EVERYDAY_FAMILY",
            vec=_v(
                "s045",
                sent=0.50,
                val=0.45,
                aro=0.35,
                surprise=0.0,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="log_memory",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.20,
                words=15,
            ),
            expected_tier="MEDIUM",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    # ------------------------------------------------------------------
    # CATEGORY 5: LOW ROUTINE (15 scenarios)
    # Solo mundane activities that should score LOW.
    # ------------------------------------------------------------------

    scenarios.append(
        Scenario(
            id=46,
            name="Regular breakfast alone",
            category="LOW_ROUTINE",
            vec=_v(
                "s046",
                sent=0.10,
                val=0.0,
                aro=0.10,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=5,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
            notes="HARD REQUIREMENT: must score < 0.25",
        )
    )

    scenarios.append(
        Scenario(
            id=47,
            name="Morning commute to work",
            category="LOW_ROUTINE",
            vec=_v(
                "s047",
                sent=0.0,
                val=0.0,
                aro=0.10,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=4,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=48,
            name="Grocery shopping alone",
            category="LOW_ROUTINE",
            vec=_v(
                "s048",
                sent=0.0,
                val=0.0,
                aro=0.05,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=4,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=49,
            name="Doing laundry",
            category="LOW_ROUTINE",
            vec=_v(
                "s049",
                sent=0.0,
                val=0.0,
                aro=0.0,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=3,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=50,
            name="Checking email at desk",
            category="LOW_ROUTINE",
            vec=_v(
                "s050",
                sent=0.0,
                val=0.0,
                aro=0.10,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=5,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=51,
            name="Watching news alone",
            category="LOW_ROUTINE",
            vec=_v(
                "s051",
                sent=-0.20,
                val=-0.10,
                aro=0.20,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=5,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW", "LOW_MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=52,
            name="Taking out the trash",
            category="LOW_ROUTINE",
            vec=_v(
                "s052",
                sent=0.0,
                val=0.0,
                aro=0.0,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=3,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=53,
            name="Eating lunch at desk solo",
            category="LOW_ROUTINE",
            vec=_v(
                "s053",
                sent=0.10,
                val=0.05,
                aro=0.05,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=4,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=54,
            name="Parking the car",
            category="LOW_ROUTINE",
            vec=_v(
                "s054",
                sent=0.0,
                val=0.0,
                aro=0.0,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=3,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=55,
            name="Brushing teeth before bed",
            category="LOW_ROUTINE",
            vec=_v(
                "s055",
                sent=0.0,
                val=0.0,
                aro=0.0,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=3,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=56,
            name="Scrolling social media alone",
            category="LOW_ROUTINE",
            vec=_v(
                "s056",
                sent=0.10,
                val=0.05,
                aro=0.15,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="chat",
                intent="casual_chat",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=4,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW_MEDIUM", "LOW"],
            notes="chat activity 1.0x vs routine 0.5x pushes slightly above LOW",
        )
    )

    scenarios.append(
        Scenario(
            id=57,
            name="Making a cup of coffee",
            category="LOW_ROUTINE",
            vec=_v(
                "s057",
                sent=0.10,
                val=0.05,
                aro=0.05,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=4,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=58,
            name="Waiting room at dentist",
            category="LOW_ROUTINE",
            vec=_v(
                "s058",
                sent=-0.10,
                val=-0.05,
                aro=0.10,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=5,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=59,
            name="Filling gas in the car",
            category="LOW_ROUTINE",
            vec=_v(
                "s059",
                sent=0.0,
                val=0.0,
                aro=0.0,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="transaction",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=3,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=60,
            name="Paying monthly bills online",
            category="LOW_ROUTINE",
            vec=_v(
                "s060",
                sent=-0.10,
                val=-0.05,
                aro=0.10,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="transaction",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=5,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    # ------------------------------------------------------------------
    # CATEGORY 6: COMMUNICATION & SHARING (10 scenarios)
    # Messages, calls, photo sharing with varying intimacy.
    # ------------------------------------------------------------------

    scenarios.append(
        Scenario(
            id=61,
            name="Casual weather chat with friend",
            category="COMMUNICATION",
            vec=_v(
                "s061",
                sent=0.10,
                val=0.10,
                aro=0.10,
                surprise=0.0,
                participants=2,
                intimacy="LOW",
                activity="chat",
                intent="casual_chat",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=8,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW_MEDIUM", "LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=62,
            name="Sharing baby photo with grandparents",
            category="COMMUNICATION",
            vec=_v(
                "s062",
                sent=0.70,
                val=0.65,
                aro=0.40,
                surprise=0.0,
                participants=3,
                intimacy="HIGH",
                activity="photo",
                intent="share_news",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.50,
                words=15,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=63,
            name="Video call with deployed military spouse",
            category="COMMUNICATION",
            vec=_v(
                "s063",
                sent=0.60,
                val=0.50,
                aro=0.50,
                surprise=0.0,
                participants=2,
                intimacy="HIGH",
                activity="video",
                intent="express_feeling",
                novelty="EXPECTED",
                elab="ELABORATED",
                identity=0.40,
                words=30,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=64,
            name="Text from child saying 'I love you mom'",
            category="COMMUNICATION",
            vec=_v(
                "s064",
                sent=0.80,
                val=0.80,
                aro=0.50,
                surprise=0.30,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="express_feeling",
                novelty="EXPECTED",
                elab="MENTION",
                identity=0.50,
                words=5,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=65,
            name="Work slack message from colleague",
            category="COMMUNICATION",
            vec=_v(
                "s065",
                sent=0.0,
                val=0.0,
                aro=0.10,
                surprise=0.0,
                participants=2,
                intimacy="LOW",
                activity="chat",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=8,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW_MEDIUM", "LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=66,
            name="Sharing child's funny video with family group",
            category="COMMUNICATION",
            vec=_v(
                "s066",
                sent=0.70,
                val=0.65,
                aro=0.60,
                surprise=0.20,
                participants=5,
                intimacy="HIGH",
                activity="video",
                intent="share_news",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.30,
                words=15,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["CRITICAL", "HIGH"],
            notes="video 1.5x + share_news 1.3x + 5 people + warm emotion -> very high",
        )
    )

    scenarios.append(
        Scenario(
            id=67,
            name="Sending calendar invite for dentist",
            category="COMMUNICATION",
            vec=_v(
                "s067",
                sent=0.0,
                val=0.0,
                aro=0.05,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="calendar",
                intent="set_reminder",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=5,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW_MEDIUM", "LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=68,
            name="Voicemail from mom checking in",
            category="COMMUNICATION",
            vec=_v(
                "s068",
                sent=0.40,
                val=0.35,
                aro=0.20,
                surprise=0.0,
                participants=2,
                intimacy="HIGH",
                activity="voice",
                intent="express_feeling",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.20,
                words=10,
            ),
            expected_tier="MEDIUM",
            acceptable_tiers=["MEDIUM", "LOW_MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=69,
            name="Group chat planning weekend trip",
            category="COMMUNICATION",
            vec=_v(
                "s069",
                sent=0.50,
                val=0.45,
                aro=0.40,
                surprise=0.0,
                participants=4,
                intimacy="MEDIUM",
                activity="chat",
                intent="make_plan",
                novelty="NOVEL",
                elab="DISCUSSED",
                temporal="FUTURE_COMMITMENT",
                identity=0.10,
                words=20,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=70,
            name="Quick 'on my way' text to spouse",
            category="COMMUNICATION",
            vec=_v(
                "s070",
                sent=0.10,
                val=0.05,
                aro=0.05,
                surprise=0.0,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=4,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW_MEDIUM", "LOW"],
        )
    )

    # ------------------------------------------------------------------
    # CATEGORY 7: PLANNING & FUTURE (8 scenarios)
    # ------------------------------------------------------------------

    scenarios.append(
        Scenario(
            id=71,
            name="Planning family vacation to Disney",
            category="PLANNING_FUTURE",
            vec=_v(
                "s071",
                sent=0.70,
                val=0.65,
                aro=0.60,
                surprise=0.0,
                participants=4,
                intimacy="HIGH",
                activity="calendar",
                intent="make_plan",
                novelty="NOVEL",
                elab="ELABORATED",
                temporal="FUTURE_COMMITMENT",
                identity=0.20,
                words=35,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=72,
            name="Setting reminder to pick up prescription",
            category="PLANNING_FUTURE",
            vec=_v(
                "s072",
                sent=0.0,
                val=0.0,
                aro=0.05,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="calendar",
                intent="set_reminder",
                novelty="ROUTINE",
                elab="MENTION",
                temporal="FUTURE_COMMITMENT",
                identity=0.0,
                words=6,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW_MEDIUM", "LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=73,
            name="Making plans for child's birthday party",
            category="PLANNING_FUTURE",
            vec=_v(
                "s073",
                sent=0.70,
                val=0.60,
                aro=0.50,
                surprise=0.0,
                participants=3,
                intimacy="HIGH",
                activity="calendar",
                intent="make_plan",
                novelty="NOVEL",
                elab="ELABORATED",
                temporal="FUTURE_COMMITMENT",
                identity=0.40,
                words=30,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=74,
            name="Scheduling oil change for car",
            category="PLANNING_FUTURE",
            vec=_v(
                "s074",
                sent=0.0,
                val=0.0,
                aro=0.0,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="calendar",
                intent="set_reminder",
                novelty="ROUTINE",
                elab="MENTION",
                temporal="FUTURE_COMMITMENT",
                identity=0.0,
                words=5,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW_MEDIUM", "LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=75,
            name="Discussion about college fund savings plan",
            category="PLANNING_FUTURE",
            vec=_v(
                "s075",
                sent=0.30,
                val=0.20,
                aro=0.30,
                surprise=0.0,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="make_plan",
                novelty="EXPECTED",
                elab="ELABORATED",
                temporal="FUTURE_COMMITMENT",
                identity=0.50,
                words=40,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=76,
            name="Planning a surprise for spouse's birthday",
            category="PLANNING_FUTURE",
            vec=_v(
                "s076",
                sent=0.70,
                val=0.65,
                aro=0.50,
                surprise=0.20,
                participants=2,
                intimacy="HIGH",
                activity="calendar",
                intent="make_plan",
                novelty="NOVEL",
                elab="DISCUSSED",
                temporal="FUTURE_COMMITMENT",
                identity=0.30,
                words=20,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=77,
            name="Estate planning discussion -- will and trust",
            category="PLANNING_FUTURE",
            vec=_v(
                "s077",
                sent=-0.20,
                val=-0.10,
                aro=0.30,
                surprise=0.0,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="make_plan",
                novelty="NOVEL",
                elab="DEEPLY_PROCESSED",
                temporal="FUTURE_COMMITMENT",
                identity=0.60,
                words=60,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=78,
            name="Setting weekday alarm -- utterly mundane",
            category="PLANNING_FUTURE",
            vec=_v(
                "s078",
                sent=0.0,
                val=0.0,
                aro=0.0,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                temporal="FUTURE_COMMITMENT",
                identity=0.0,
                words=3,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    # ------------------------------------------------------------------
    # CATEGORY 8: IDENTITY & REFLECTION (10 scenarios)
    # Events touching core identity, self-concept, family identity.
    # ------------------------------------------------------------------

    scenarios.append(
        Scenario(
            id=79,
            name="Reflecting on deceased parent -- deep grief",
            category="IDENTITY_REFLECTION",
            vec=_v(
                "s079",
                sent=-0.50,
                val=-0.60,
                aro=0.40,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="message",
                intent="reflect",
                novelty="EXPECTED",
                elab="ELABORATED",
                identity=0.80,
                words=50,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
            notes="Elaboration + identity boosts despite solo + low social",
        )
    )

    scenarios.append(
        Scenario(
            id=80,
            name="Journal entry about career aspirations",
            category="IDENTITY_REFLECTION",
            vec=_v(
                "s080",
                sent=0.40,
                val=0.35,
                aro=0.30,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="message",
                intent="reflect",
                novelty="EXPECTED",
                elab="ELABORATED",
                identity=0.50,
                words=40,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=81,
            name="Realizing child resembles grandparent",
            category="IDENTITY_REFLECTION",
            vec=_v(
                "s081",
                sent=0.60,
                val=0.55,
                aro=0.30,
                surprise=0.30,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="reflect",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.70,
                words=20,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=82,
            name="Writing about family immigration history",
            category="IDENTITY_REFLECTION",
            vec=_v(
                "s082",
                sent=0.50,
                val=0.40,
                aro=0.30,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="message",
                intent="reflect",
                novelty="EXPECTED",
                elab="DEEPLY_PROCESSED",
                identity=0.90,
                words=80,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=83,
            name="Child asks 'where do we come from?'",
            category="IDENTITY_REFLECTION",
            vec=_v(
                "s083",
                sent=0.50,
                val=0.45,
                aro=0.40,
                surprise=0.30,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="reflect",
                novelty="NOVEL",
                elab="ELABORATED",
                identity=0.80,
                words=35,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=84,
            name="Spouse compliments parenting -- self-esteem boost",
            category="IDENTITY_REFLECTION",
            vec=_v(
                "s084",
                sent=0.70,
                val=0.65,
                aro=0.40,
                surprise=0.20,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="express_feeling",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.40,
                words=15,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=85,
            name="Feeling guilty about yelling at kids",
            category="IDENTITY_REFLECTION",
            vec=_v(
                "s085",
                sent=-0.60,
                val=-0.55,
                aro=0.50,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="message",
                intent="reflect",
                novelty="EXPECTED",
                elab="ELABORATED",
                identity=0.50,
                words=35,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=86,
            name="Rediscovering old family photo album",
            category="IDENTITY_REFLECTION",
            vec=_v(
                "s086",
                sent=0.70,
                val=0.60,
                aro=0.40,
                surprise=0.30,
                participants=1,
                intimacy="LOW",
                activity="photo",
                intent="reflect",
                novelty="NOVEL",
                elab="ELABORATED",
                identity=0.70,
                words=30,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=87,
            name="Idle thought about what's for dinner",
            category="IDENTITY_REFLECTION",
            vec=_v(
                "s087",
                sent=0.0,
                val=0.0,
                aro=0.05,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=5,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=88,
            name="Child named after deceased grandmother -- story",
            category="IDENTITY_REFLECTION",
            vec=_v(
                "s088",
                sent=0.60,
                val=0.50,
                aro=0.40,
                surprise=0.0,
                participants=3,
                intimacy="HIGH",
                activity="message",
                intent="reflect",
                novelty="EXPECTED",
                elab="DEEPLY_PROCESSED",
                identity=0.90,
                words=70,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["CRITICAL", "HIGH"],
        )
    )

    # ------------------------------------------------------------------
    # CATEGORY 9: SOURCE RELIABILITY VARIANTS (8 scenarios)
    # Same or similar events with different source types.
    # ------------------------------------------------------------------

    scenarios.append(
        Scenario(
            id=89,
            name="Device infers grocery trip from GPS",
            category="SOURCE_RELIABILITY",
            vec=_v(
                "s089",
                sent=0.0,
                val=0.0,
                aro=0.0,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="location",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                reliability=0.70,
                words=3,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=90,
            name="System infers bedtime from phone-lock pattern",
            category="SOURCE_RELIABILITY",
            vec=_v(
                "s090",
                sent=0.0,
                val=0.0,
                aro=0.0,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                reliability=0.50,
                words=3,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=91,
            name="Low-confidence inference about old event",
            category="SOURCE_RELIABILITY",
            vec=_v(
                "s091",
                sent=0.0,
                val=0.0,
                aro=0.0,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                reliability=0.35,
                words=3,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=92,
            name="Device detects family at park (GPS + photo)",
            category="SOURCE_RELIABILITY",
            vec=_v(
                "s092",
                sent=0.40,
                val=0.35,
                aro=0.30,
                surprise=0.0,
                participants=4,
                intimacy="HIGH",
                activity="location",
                intent="other",
                novelty="EXPECTED",
                elab="MENTION",
                identity=0.10,
                reliability=0.70,
                words=6,
            ),
            expected_tier="LOW_MEDIUM",
            acceptable_tiers=["MEDIUM", "LOW_MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=93,
            name="User confirms device-inferred park visit",
            category="SOURCE_RELIABILITY",
            vec=_v(
                "s093",
                sent=0.40,
                val=0.35,
                aro=0.30,
                surprise=0.0,
                participants=4,
                intimacy="HIGH",
                activity="location",
                intent="log_memory",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.10,
                reliability=0.95,
                words=15,
            ),
            expected_tier="MEDIUM",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=94,
            name="High-confidence device: kid at school (bus GPS)",
            category="SOURCE_RELIABILITY",
            vec=_v(
                "s094",
                sent=0.0,
                val=0.0,
                aro=0.0,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="location",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.10,
                reliability=0.80,
                words=4,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=95,
            name="User says: 'Sharvi had a bad day at school'",
            category="SOURCE_RELIABILITY",
            vec=_v(
                "s095",
                sent=-0.50,
                val=-0.45,
                aro=0.40,
                surprise=0.0,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="express_feeling",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.40,
                reliability=0.95,
                words=20,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=96,
            name="System infers child absent from school (no GPS)",
            category="SOURCE_RELIABILITY",
            vec=_v(
                "s096",
                sent=0.0,
                val=0.0,
                aro=0.0,
                surprise=0.30,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="EXPECTED",
                elab="MENTION",
                identity=0.10,
                reliability=0.40,
                words=5,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW_MEDIUM", "LOW"],
        )
    )

    # ------------------------------------------------------------------
    # CATEGORY 10: ELABORATION DEPTH VARIANTS (8 scenarios)
    # Same core event described at different lengths.
    # ------------------------------------------------------------------

    scenarios.append(
        Scenario(
            id=97,
            name="Beach trip -- brief mention: 'went to beach'",
            category="ELABORATION_DEPTH",
            vec=_v(
                "s097",
                sent=0.50,
                val=0.45,
                aro=0.30,
                surprise=0.0,
                participants=4,
                intimacy="HIGH",
                activity="message",
                intent="log_memory",
                novelty="EXPECTED",
                elab="MENTION",
                identity=0.10,
                words=5,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
            notes="4 people + HIGH intimacy + log_memory intent = MEDIUM_HIGH even at MENTION",
        )
    )

    scenarios.append(
        Scenario(
            id=98,
            name="Beach trip -- discussed: 'built sandcastles, swam'",
            category="ELABORATION_DEPTH",
            vec=_v(
                "s098",
                sent=0.50,
                val=0.45,
                aro=0.30,
                surprise=0.0,
                participants=4,
                intimacy="HIGH",
                activity="message",
                intent="log_memory",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.10,
                words=15,
            ),
            expected_tier="MEDIUM",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=99,
            name="Beach trip -- elaborated paragraph with feelings",
            category="ELABORATION_DEPTH",
            vec=_v(
                "s099",
                sent=0.50,
                val=0.45,
                aro=0.30,
                surprise=0.0,
                participants=4,
                intimacy="HIGH",
                activity="message",
                intent="log_memory",
                novelty="EXPECTED",
                elab="ELABORATED",
                identity=0.10,
                words=30,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=100,
            name="Beach trip -- deeply processed essay with meaning",
            category="ELABORATION_DEPTH",
            vec=_v(
                "s100",
                sent=0.50,
                val=0.45,
                aro=0.30,
                surprise=0.0,
                participants=4,
                intimacy="HIGH",
                activity="message",
                intent="log_memory",
                novelty="EXPECTED",
                elab="DEEPLY_PROCESSED",
                identity=0.10,
                words=50,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=101,
            name="Fight with spouse -- brief: 'we argued'",
            category="ELABORATION_DEPTH",
            vec=_v(
                "s101",
                sent=-0.60,
                val=-0.55,
                aro=0.60,
                surprise=0.0,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="express_feeling",
                novelty="EXPECTED",
                elab="MENTION",
                identity=0.20,
                words=5,
            ),
            expected_tier="MEDIUM",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=102,
            name="Fight with spouse -- elaborated with context",
            category="ELABORATION_DEPTH",
            vec=_v(
                "s102",
                sent=-0.60,
                val=-0.55,
                aro=0.60,
                surprise=0.0,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="express_feeling",
                novelty="EXPECTED",
                elab="ELABORATED",
                identity=0.20,
                words=40,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=103,
            name="Fight with spouse -- deeply processed reflection",
            category="ELABORATION_DEPTH",
            vec=_v(
                "s103",
                sent=-0.60,
                val=-0.55,
                aro=0.60,
                surprise=0.0,
                participants=2,
                intimacy="HIGH",
                activity="message",
                intent="reflect",
                novelty="EXPECTED",
                elab="DEEPLY_PROCESSED",
                identity=0.20,
                words=70,
            ),
            expected_tier="HIGH",
            acceptable_tiers=["HIGH", "MEDIUM_HIGH"],
        )
    )

    scenarios.append(
        Scenario(
            id=104,
            name="Mundane event elaborated doesn't become important",
            category="ELABORATION_DEPTH",
            vec=_v(
                "s104",
                sent=0.0,
                val=0.0,
                aro=0.05,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="DEEPLY_PROCESSED",
                identity=0.0,
                words=60,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW_MEDIUM", "LOW"],
            notes="Elaboration alone should NOT make a null-signal event important",
        )
    )

    # ------------------------------------------------------------------
    # CATEGORY 11: INTENT VARIETY (8 scenarios)
    # Same moderate family event with different intents.
    # ------------------------------------------------------------------

    scenarios.append(
        Scenario(
            id=105,
            name="Dinner event -- intent=casual_chat",
            category="INTENT_VARIETY",
            vec=_v(
                "s105",
                sent=0.50,
                val=0.45,
                aro=0.30,
                surprise=0.0,
                participants=3,
                intimacy="HIGH",
                activity="message",
                intent="casual_chat",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.10,
                words=15,
            ),
            expected_tier="MEDIUM",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=106,
            name="Dinner event -- intent=share_news",
            category="INTENT_VARIETY",
            vec=_v(
                "s106",
                sent=0.50,
                val=0.45,
                aro=0.30,
                surprise=0.0,
                participants=3,
                intimacy="HIGH",
                activity="message",
                intent="share_news",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.10,
                words=15,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=107,
            name="Dinner event -- intent=query_memory",
            category="INTENT_VARIETY",
            vec=_v(
                "s107",
                sent=0.50,
                val=0.45,
                aro=0.30,
                surprise=0.0,
                participants=3,
                intimacy="HIGH",
                activity="message",
                intent="query_memory",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.10,
                words=15,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=108,
            name="Dinner event -- intent=reflect",
            category="INTENT_VARIETY",
            vec=_v(
                "s108",
                sent=0.50,
                val=0.45,
                aro=0.30,
                surprise=0.0,
                participants=3,
                intimacy="HIGH",
                activity="message",
                intent="reflect",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.10,
                words=15,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=109,
            name="Dinner event -- intent=log_memory",
            category="INTENT_VARIETY",
            vec=_v(
                "s109",
                sent=0.50,
                val=0.45,
                aro=0.30,
                surprise=0.0,
                participants=3,
                intimacy="HIGH",
                activity="message",
                intent="log_memory",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.10,
                words=15,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=110,
            name="Dinner event -- intent=make_plan",
            category="INTENT_VARIETY",
            vec=_v(
                "s110",
                sent=0.50,
                val=0.45,
                aro=0.30,
                surprise=0.0,
                participants=3,
                intimacy="HIGH",
                activity="message",
                intent="make_plan",
                novelty="EXPECTED",
                elab="DISCUSSED",
                temporal="FUTURE_COMMITMENT",
                identity=0.10,
                words=15,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=111,
            name="Dinner event -- intent=seek_advice",
            category="INTENT_VARIETY",
            vec=_v(
                "s111",
                sent=0.50,
                val=0.45,
                aro=0.30,
                surprise=0.0,
                participants=3,
                intimacy="HIGH",
                activity="message",
                intent="seek_advice",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.10,
                words=15,
            ),
            expected_tier="MEDIUM_HIGH",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    scenarios.append(
        Scenario(
            id=112,
            name="Dinner event -- intent=express_feeling",
            category="INTENT_VARIETY",
            vec=_v(
                "s112",
                sent=0.50,
                val=0.45,
                aro=0.30,
                surprise=0.0,
                participants=3,
                intimacy="HIGH",
                activity="message",
                intent="express_feeling",
                novelty="EXPECTED",
                elab="DISCUSSED",
                identity=0.10,
                words=15,
            ),
            expected_tier="MEDIUM",
            acceptable_tiers=["MEDIUM_HIGH", "MEDIUM"],
        )
    )

    # ------------------------------------------------------------------
    # CATEGORY 12: EDGE CASES (8 scenarios)
    # Boundary conditions and unusual signal combinations.
    # ------------------------------------------------------------------

    scenarios.append(
        Scenario(
            id=113,
            name="EDGE: All signals at maximum",
            category="EDGE_CASE",
            vec=_v(
                "s113",
                sent=0.90,
                val=0.90,
                aro=1.0,
                surprise=1.0,
                participants=10,
                intimacy="HIGH",
                activity="milestone",
                intent="query_memory",
                novelty="SURPRISING",
                elab="DEEPLY_PROCESSED",
                identity=1.0,
                reliability=1.0,
                words=100,
            ),
            expected_tier="CRITICAL",
            acceptable_tiers=["CRITICAL"],
            notes="Score should be 1.0 (clamped)",
        )
    )

    scenarios.append(
        Scenario(
            id=114,
            name="EDGE: All signals at zero",
            category="EDGE_CASE",
            vec=_v(
                "s114",
                sent=0.0,
                val=0.0,
                aro=0.0,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                reliability=0.35,
                words=1,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
            notes="Score should be near 0.0",
        )
    )

    scenarios.append(
        Scenario(
            id=115,
            name="EDGE: High emotion but routine + solo + low novel",
            category="EDGE_CASE",
            vec=_v(
                "s115",
                sent=0.90,
                val=0.85,
                aro=0.80,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="casual_chat",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=5,
            ),
            expected_tier="LOW_MEDIUM",
            acceptable_tiers=["MEDIUM", "LOW_MEDIUM"],
            notes="High emotion suppressed by routine + casual + solo",
        )
    )

    scenarios.append(
        Scenario(
            id=116,
            name="EDGE: Zero emotion but max social + surprise",
            category="EDGE_CASE",
            vec=_v(
                "s116",
                sent=0.0,
                val=0.0,
                aro=0.0,
                surprise=1.0,
                participants=10,
                intimacy="HIGH",
                activity="message",
                intent="share_news",
                novelty="SURPRISING",
                elab="DISCUSSED",
                identity=0.50,
                words=15,
            ),
            expected_tier="CRITICAL",
            acceptable_tiers=["CRITICAL", "HIGH"],
            notes="Max social + max surprise + identity + share_news = CRITICAL even without emotion",
        )
    )

    scenarios.append(
        Scenario(
            id=117,
            name="EDGE: Extremely negative with low reliability",
            category="EDGE_CASE",
            vec=_v(
                "s117",
                sent=-0.90,
                val=-0.90,
                aro=1.0,
                surprise=1.0,
                participants=1,
                intimacy="LOW",
                activity="message",
                intent="express_feeling",
                novelty="SURPRISING",
                elab="ELABORATED",
                identity=0.30,
                reliability=0.35,
                words=40,
            ),
            expected_tier="LOW_MEDIUM",
            acceptable_tiers=["MEDIUM", "LOW_MEDIUM"],
            notes="0.35 reliability crushes strong signals to ~0.29 -- working as designed",
        )
    )

    scenarios.append(
        Scenario(
            id=118,
            name="EDGE: Milestone type but zero emotion/social",
            category="EDGE_CASE",
            vec=_v(
                "s118",
                sent=0.0,
                val=0.0,
                aro=0.0,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="milestone",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=3,
            ),
            expected_tier="MEDIUM",
            acceptable_tiers=["MEDIUM", "LOW_MEDIUM"],
            notes="Milestone 2.5x even on tiny base gives ~0.31 -- event_type multiplier floor",
        )
    )

    scenarios.append(
        Scenario(
            id=119,
            name="EDGE: Very short single word 'fine'",
            category="EDGE_CASE",
            vec=_v(
                "s119",
                sent=0.0,
                val=0.0,
                aro=0.0,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="chat",
                intent="casual_chat",
                novelty="ROUTINE",
                elab="MENTION",
                identity=0.0,
                words=1,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW"],
        )
    )

    scenarios.append(
        Scenario(
            id=120,
            name="EDGE: High identity but zero everything else",
            category="EDGE_CASE",
            vec=_v(
                "s120",
                sent=0.0,
                val=0.0,
                aro=0.0,
                surprise=0.0,
                participants=1,
                intimacy="LOW",
                activity="routine",
                intent="other",
                novelty="ROUTINE",
                elab="MENTION",
                identity=1.0,
                words=5,
            ),
            expected_tier="LOW",
            acceptable_tiers=["LOW_MEDIUM", "LOW"],
            notes="Identity alone with routine multiplier should not push high",
        )
    )

    return scenarios


# ===================================================================
# RUNNER
# ===================================================================

TIER_ORDER_MAP = {
    "CRITICAL": 6,
    "HIGH": 5,
    "MEDIUM_HIGH": 4,
    "MEDIUM": 3,
    "LOW_MEDIUM": 2,
    "LOW": 1,
}


def run_scenarios(
    scenarios: list[Scenario],
    cfg: WeightConfig,
    lam: float = 0.005,
    recency_age_h: float = 0.0,
) -> None:
    """Score all scenarios and print comparison table."""
    rf = math.exp(-lam * recency_age_h) if recency_age_h > 0 else 1.0

    print(f"\n{'=' * 80}")
    print("PHASE 6: Hand-Crafted Scenario Validation")
    print(f"Config: {cfg.name} | Lambda: {lam} | Age: {recency_age_h}h | RF: {rf:.3f}")
    print(f"Scenarios: {len(scenarios)}")
    print(f"{'=' * 80}\n")

    passes = 0
    fails = 0
    results: list[dict] = []
    hard_fail = False

    for s in scenarios:
        score = compute_importance(s.vec, cfg, recency_factor=rf)
        computed_tier = score_to_tier(score)
        match = computed_tier in s.acceptable_tiers
        if match:
            passes += 1
        else:
            fails += 1

        status = "PASS" if match else "FAIL"
        results.append(
            {
                "id": s.id,
                "name": s.name,
                "category": s.category,
                "score": score,
                "computed": computed_tier,
                "expected": s.expected_tier,
                "acceptable": s.acceptable_tiers,
                "match": match,
                "status": status,
            }
        )

        # Hard fail checks
        if s.id == 1 and score <= 0.85:
            hard_fail = True
        if s.id == 46 and score >= 0.25:
            hard_fail = True

    # Print results by category
    current_cat = ""
    for r in results:
        if r["category"] != current_cat:
            current_cat = r["category"]
            print(f"\n  --- {current_cat} ---")
        marker = "  " if r["match"] else ">>"
        print(
            f"  {marker} #{r['id']:3d} | {r['score']:.3f} {r['computed']:13s} "
            f"| exp={r['expected']:13s} | {r['status']:4s} | {r['name'][:50]}"
        )

    # Summary
    total = passes + fails
    pct = passes / total * 100 if total else 0

    print(f"\n{'=' * 80}")
    print(f"RESULTS: {passes}/{total} passed ({pct:.1f}%)")
    print(f"  Passes: {passes}")
    print(f"  Fails:  {fails}")

    # List all failures
    failed = [r for r in results if not r["match"]]
    if failed:
        print("\n  FAILURES:")
        for r in failed:
            print(
                f"    #{r['id']:3d} | score={r['score']:.3f} computed={r['computed']} "
                f"expected={r['expected']} acceptable={r['acceptable']}"
            )
            print(f"          {r['name']}")

    # Hard fail checks
    s1 = next(r for r in results if r["id"] == 1)
    s46 = next(r for r in results if r["id"] == 46)
    print("\n  HARD REQUIREMENTS:")
    s1_ok = s1["score"] > 0.85
    s46_ok = s46["score"] < 0.25
    print(
        f"    Scenario  1 (Sharvi's first word): score={s1['score']:.4f} "
        f"{'PASS (>0.85)' if s1_ok else 'HARD FAIL (<=0.85)'}"
    )
    print(
        f"    Scenario 46 (breakfast alone):     score={s46['score']:.4f} "
        f"{'PASS (<0.25)' if s46_ok else 'HARD FAIL (>=0.25)'}"
    )

    # Pass criteria
    pass_threshold = int(total * 0.85)
    criteria_met = passes >= pass_threshold and not hard_fail
    print(f"\n  ACCEPTANCE: need >= {pass_threshold}/{total} (85%) and no hard fails")
    print(f"  VERDICT: {'PASS' if criteria_met else 'FAIL'}")

    # Category breakdown
    cat_stats: Dict[str, list[bool]] = {}
    for r in results:
        cat_stats.setdefault(r["category"], []).append(r["match"])
    print("\n  CATEGORY BREAKDOWN:")
    for cat, matches in cat_stats.items():
        cat_pass = sum(matches)
        cat_total = len(matches)
        cat_pct = cat_pass / cat_total * 100
        marker = " " if cat_pass == cat_total else "*"
        print(f"   {marker} {cat:25s}: {cat_pass}/{cat_total} ({cat_pct:.0f}%)")

    print(f"\n{'=' * 80}")


# ===================================================================
# CLI
# ===================================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 6: Scenario Validation")
    parser.add_argument(
        "--config",
        type=str,
        default="B",
        choices=["A", "B", "C", "D", "all"],
        help="Weight config (default: B = winner)",
    )
    parser.add_argument(
        "--lambda", type=float, default=0.005, dest="lam", help="Recency lambda (default: 0.005)"
    )
    parser.add_argument(
        "--age", type=float, default=0.0, help="Simulated event age in hours (default: 0 = fresh)"
    )
    args = parser.parse_args()

    scenarios = build_all_scenarios()
    print(f"Built {len(scenarios)} scenarios")

    configs_map = {"A": CONFIG_A, "B": CONFIG_B, "C": CONFIG_C, "D": CONFIG_D}

    if args.config == "all":
        for cfg in ALL_CONFIGS:
            run_scenarios(scenarios, cfg, lam=args.lam, recency_age_h=args.age)
    else:
        cfg = configs_map[args.config]
        run_scenarios(scenarios, cfg, lam=args.lam, recency_age_h=args.age)


if __name__ == "__main__":
    main()
