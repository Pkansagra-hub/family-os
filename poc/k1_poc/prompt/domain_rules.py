"""
poc.k1_poc.prompt.domain_rules -- Domain-specific safety rules.

V2 Design Ref: Section 6.1 (Domain Rule Injection)

When the current conversation has a detected domain (from Phase 1
domain classification or ss.control.domain_context), domain-specific
rules are injected into the prompt to enforce safety floors and
behavioral constraints.

Six domains are defined, each with a safety floor classification
documented in the V2 design table:

    health       AMBER   Never diagnose or recommend treatments
    finance      AMBER   All financial actions require explicit approval
    elder_care   GREEN   Simpler language, confirm understanding
    children     AMBER   Route through parent profile, filter content
    legal        RED     Never provide legal advice
    emergency    RED     User safety first, no confirmation delays

Domain rules are cumulative with the mode's existing safety band.
They add ADDITIONAL constraints -- they don't replace the safety
band system.

Coherence hierarchy (V2 Section 16.3):
    DOMAIN_RULES > SAFETY_HITL > AFFECT_TONE_BLOCKS
    > CLARIFY_DEPTH_BLOCKS > base PROMPT_SECTIONS

Exports:
    DOMAIN_RULES: Domain name -> prompt injection text
    get_domain_rules: Lookup helper returning text or ""
"""

from __future__ import annotations

# =========================================================================
# DOMAIN_RULES -- domain -> prompt injection text
# =========================================================================
# Authoritative text from V2 Design Doc Section 6.1.
# DynamicPromptBuilder appends the matching block when a domain is detected.

DOMAIN_RULES: dict[str, str] = {
    "health": (
        "== DOMAIN: HEALTH ==\n"
        "NEVER diagnose conditions or recommend treatments.\n"
        "NEVER interpret lab results, symptoms, or medication interactions.\n"
        "You CAN: schedule appointments, find providers, set medication reminders,\n"
        "track wellness data the user volunteers.\n"
        "If user describes symptoms: 'That sounds worth checking with your doctor.\n"
        "Want me to find availability with Dr. [name from persona]?'"
    ),
    "finance": (
        "== DOMAIN: FINANCE ==\n"
        "ALL financial actions require AMBER safety band minimum.\n"
        "State EXACT amounts -- never round or approximate.\n"
        "State the payment method explicitly.\n"
        "For amounts above $500: require explicit verbal confirmation.\n"
        "Never auto-approve recurring charges or subscriptions."
    ),
    "elder_care": (
        "== DOMAIN: ELDER CARE ==\n"
        "Use simpler language. Short sentences. Max 3 options.\n"
        "Confirm understanding: 'Just to make sure -- you'd like X, right?'\n"
        "Speak slightly more slowly (RhythmController hint: pace='slow').\n"
        "If user seems confused, offer to repeat or simplify."
    ),
    "children": (
        "== DOMAIN: CHILDREN ==\n"
        "All action requests for a minor route through parent profile.\n"
        "Filter age-inappropriate content (violence, explicit, drugs).\n"
        "For child users: playful, simple language. Educational framing.\n"
        "Never share child location data outside the family."
    ),
    "legal": (
        "== DOMAIN: LEGAL ==\n"
        "NEVER provide legal interpretations, advice, or opinions.\n"
        "NEVER draft legal documents or contracts.\n"
        "You CAN: find legal professionals, schedule consultations,\n"
        "summarize publicly available legal information with disclaimers."
    ),
    "emergency": (
        "== DOMAIN: EMERGENCY ==\n"
        "PRIORITY: USER SAFETY FIRST.\n"
        "If physical danger: provide emergency numbers IMMEDIATELY.\n"
        "Do NOT wait for clarification. Do NOT ask 'are you sure?'\n"
        "Emergency numbers: 911 (US), 112 (EU), 999 (UK).\n"
        "After immediate response: offer to notify family members."
    ),
    "iot": (
        "== DOMAIN: IoT / SMART HOME ==\n"
        "ALWAYS dispatch_task for device actions -- the AMBER safety band ensures\n"
        "the execution layer confirms with the user before side effects.\n"
        "Do NOT ask clarification questions yourself; dispatch and let the\n"
        "system handle confirmation. Say 'On it -- locking the front door.'\n"
        "State device name explicitly when you know it from beliefs/context.\n"
        "If the specific device is genuinely ambiguous (e.g. 'turn on the light'\n"
        "when multiple rooms exist), resolve via scoreboard referents or ask ONCE."
    ),
    "communication": (
        "== DOMAIN: COMMUNICATION ==\n"
        "Never compose messages that impersonate family members.\n"
        "Drafts require approval before sending.\n"
        "Show draft to user: 'Here\\'s what I\\'d send -- want me to adjust?'\n"
        "Never send messages without explicit user consent."
    ),
}


# =========================================================================
# Safety floor per domain (V2 Design Doc Section 6.1)
# =========================================================================
# The safety floor is the MINIMUM safety band for any action in that domain.
# Domain floors are cumulative with the mode's existing safety band.

DOMAIN_SAFETY_FLOORS: dict[str, str] = {
    "health": "AMBER",
    "finance": "AMBER",
    "elder_care": "GREEN",
    "children": "AMBER",
    "legal": "RED",
    "emergency": "RED",
    "iot": "GREEN",
    "communication": "GREEN",
}


# =========================================================================
# Mode applicability per domain (V2 Design Doc Section 6.1)
# =========================================================================
# Which prompt modes each domain's rules apply to.
# "ALL" means inject for every mode.

DOMAIN_APPLICABLE_MODES: dict[str, list[str] | str] = {
    "health": ["standard", "clarify_ask", "hitl_relay"],
    "finance": ["standard", "hitl_relay", "present"],
    "elder_care": "ALL",
    "children": ["standard", "clarify_ask", "present"],
    "legal": ["standard", "hitl_relay"],
    "emergency": "ALL",
    "iot": ["standard", "hitl_relay"],
    "communication": ["standard", "hitl_relay"],
}


def get_domain_rules(domain: str | None) -> str:
    """Return domain-specific prompt block.

    Args:
        domain: Domain identifier from Phase 1 classification or
            ss.control.domain_context. May be None for general
            conversation.

    Returns:
        Domain-specific prompt injection text, or empty string
        if no domain is detected or no rules exist for that domain.
    """
    if not domain:
        return ""
    return DOMAIN_RULES.get(domain, "")


def get_domain_safety_floor(domain: str | None) -> str:
    """Return minimum safety band for a domain.

    The safety floor determines the lowest permissible safety band
    for actions in this domain. Domain floors are enforced on top of
    the mode's existing safety band.

    Args:
        domain: Domain identifier or None.

    Returns:
        "GREEN", "AMBER", or "RED". Defaults to "GREEN" for unknown
        or unspecified domains.
    """
    if not domain:
        return "GREEN"
    return DOMAIN_SAFETY_FLOORS.get(domain, "GREEN")


def is_domain_applicable(domain: str, mode_value: str) -> bool:
    """Check if domain rules apply to the given prompt mode.

    Some domains (elder_care, emergency) apply to ALL modes.
    Others only apply to specific modes listed in DOMAIN_APPLICABLE_MODES.

    Args:
        domain: Domain identifier (e.g. "health").
        mode_value: PromptMode.value string (e.g. "standard").

    Returns:
        True if domain rules should be injected for this mode.
    """
    applicable = DOMAIN_APPLICABLE_MODES.get(domain)
    if applicable is None:
        return False
    if applicable == "ALL":
        return True
    return mode_value in applicable
