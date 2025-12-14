from __future__ import annotations

import dataclasses

import pytest

from k0.policy.redaction import (
    RedactionDirective,
    RedactionError,
    apply_redactions,
    directives_from_obligations,
)


def test_apply_redactions_masks_simple_field():
    body = {"email": "user@example.com", "name": "Jill"}
    directives = [
        RedactionDirective(
            obligation="kernel.redact.field",
            fields="email",
            mask="***",
        )
    ]

    sanitized = apply_redactions(body, directives)

    assert sanitized["email"] == "***"
    assert sanitized["name"] == "Jill"
    assert body["email"] == "user@example.com"


def test_apply_redactions_nested_target_and_multiple_fields():
    body = {
        "profile": {
            "contact": {"email": "user@example.com", "phone": "+1555123456"},
            "metadata": {"roles": ["admin"]},
        }
    }
    directives = [
        RedactionDirective(
            obligation="kernel.redact.field",
            target="profile.contact",
            fields=("email", "phone"),
            mask="[MASKED]",
        )
    ]

    sanitized = apply_redactions(body, directives)

    assert sanitized["profile"]["contact"]["email"] == "[MASKED]"
    assert sanitized["profile"]["contact"]["phone"] == "[MASKED]"
    # Ensure other sections untouched
    assert sanitized["profile"]["metadata"] == {"roles": ["admin"]}


def test_apply_redactions_handles_missing_paths_gracefully():
    body = {"profile": {"contact": {"email": "user@example.com"}}}
    directives = [
        RedactionDirective(
            obligation="kernel.redact.field",
            target="profile.contact",
            fields=("phone",),
        )
    ]

    sanitized = apply_redactions(body, directives)

    assert sanitized == body


def test_apply_redactions_masks_list_entries():
    body = {
        "household": {
            "members": [
                {"name": "Jill", "ssn": "111-22-3333"},
                {"name": "Joe", "ssn": "222-33-4444"},
            ]
        }
    }
    directives = [
        RedactionDirective(
            obligation="kernel.redact.field",
            target="household.members.0",
            fields="ssn",
            mask="XXX-XX-XXXX",
        ),
        RedactionDirective(
            obligation="kernel.redact.field",
            target="household.members.1",
            fields="ssn",
            mask="XXX-XX-XXXX",
        ),
    ]

    sanitized = apply_redactions(body, directives)

    assert sanitized["household"]["members"][0]["ssn"] == "XXX-XX-XXXX"
    assert sanitized["household"]["members"][1]["ssn"] == "XXX-XX-XXXX"
    # Ensure list length preserved
    assert len(sanitized["household"]["members"]) == 2


def test_apply_redactions_raises_for_non_mapping_root():
    with pytest.raises(RedactionError):
        apply_redactions(["not", "a", "mapping"], [])  # type: ignore[arg-type]


def test_directives_from_obligations_with_mapping_details():
    obligations = [
        {
            "name": "kernel.redact.field",
            "details": {
                "fields": ["payload.secret", "payload.nested.0"],
                "target": "body",
                "mask": "***REDACTED***",
            },
        }
    ]

    directives = directives_from_obligations(obligations)

    assert len(directives) == 1
    directive = directives[0]
    assert directive.target == "body"
    assert list(directive.fields) == ["payload.secret", "payload.nested.0"]
    assert directive.mask == "***REDACTED***"


@dataclasses.dataclass
class _Obligation:
    name: str
    details: dict[str, object]


def test_directives_from_obligations_accepts_dataclass_objects():
    obligation = _Obligation(
        name="kernel.redact.field",
        details={"fields": "email"},
    )

    directives = directives_from_obligations([obligation], default_mask="XX")

    assert len(directives) == 1
    assert directives[0].fields == "email"
    assert directives[0].mask == "XX"


def test_directives_from_obligations_rejects_missing_fields():
    obligations = [
        {"name": "kernel.redact.field", "details": {"target": "profile"}}
    ]

    with pytest.raises(RedactionError):
        directives_from_obligations(obligations)
