"""E8 invariant -- every fabric capability declares a risk class (M9.E3.I1).

Per the M9 contract the constitution becomes a pure social document
and risk metadata moves to fabric. Each registered capability MUST
therefore expose a non-empty ``risk_class`` (one of low / medium /
high / safety_sensitive) and either:

* a non-empty ``social_act`` -- bound to a constitution act id, OR
* be listed in :data:`INFRASTRUCTURE_ONLY` -- read/cognitive verbs
  that need no social binding (e.g. ``recall_memory``,
  ``summarize_context``).

This is a *contract-level* test: it inspects every
:class:`CapabilityContract` round-tripped through ``from_dict`` to
guarantee the schema accepts the new fields. End-to-end coverage of a
freshly-loaded ModuleRegistry lives in
``test_loader_registry_retrieval.py``.
"""

from __future__ import annotations

from k1.fabric.types import CapabilityContract

# Capabilities that intentionally have no social-act binding (pure
# reads / cognitive verbs). The constitution NEVER gates these.
INFRASTRUCTURE_ONLY: frozenset[str] = frozenset(
    {
        "recall_memory",
        "search_memory",
        "summarize_context",
        "list_routines",
        "list_reminders",
        "submit_result",
        "needs_human",
    }
)

_VALID_RISK_VALUES: frozenset[str] = frozenset({"low", "medium", "high", "safety_sensitive"})


def test_capability_contract_round_trips_risk_metadata() -> None:
    """``from_dict`` accepts and preserves risk_class/social_act."""
    payload = {
        "name": "send_message",
        "version": "1.0.0",
        "domain": ["communication"],
        "description": "Send a message to a household member.",
        "risk_class": "high",
        "social_act": "send_message",
    }
    c = CapabilityContract.from_dict(payload)
    assert c.risk_class == "high"
    assert c.social_act == "send_message"
    round_tripped = c.to_dict()
    assert round_tripped["risk_class"] == "high"
    assert round_tripped["social_act"] == "send_message"


def test_capability_contract_defaults_fail_closed() -> None:
    """Missing risk_class falls back to safety_sensitive; social_act None."""
    c = CapabilityContract.from_dict({"name": "ghost", "version": "1.0.0"})
    assert c.risk_class == "safety_sensitive"
    assert c.social_act is None


def test_risk_class_values_are_valid() -> None:
    """The set of allowed values matches selfmodel's RiskClass enum."""
    from k1.selfmodel.contracts.policy import RiskClass

    enum_values = {r.value for r in RiskClass}
    assert enum_values == _VALID_RISK_VALUES


def test_infrastructure_only_acts_have_no_social_binding_required() -> None:
    """An INFRASTRUCTURE_ONLY capability passes E8 with social_act=None."""
    for name in INFRASTRUCTURE_ONLY:
        c = CapabilityContract.from_dict({"name": name, "version": "1.0.0", "risk_class": "low"})
        assert c.risk_class in _VALID_RISK_VALUES
        assert c.social_act is None
