"""GAP-P1-015: Connector Definition tests.

Epic 2, Issue 2.5.
"""

from __future__ import annotations

import pytest

from k1.fabric.connectors.builder import build_connector_definition
from k1.fabric.connectors.definition import (
    CapabilityDefinition,
    ConnectorDefinition,
    ServiceDefinition,
)
from k1.fabric.connectors.domain_catalog import (
    DOMAIN_SERVICES,
    build_all_corpora,
    build_domain_corpus,
)

# ── TestConnectorDefinitionShape ─────────────────────────────────────────


class TestConnectorDefinitionShape:
    def test_all_required_fields_present(self):
        svc = DOMAIN_SERVICES["family"][0]
        conn = build_connector_definition("family", svc)
        # 14 required fields from ConnectorDefinition
        assert conn.connector_id == "family.calendar"
        assert conn.connector_type == "native"
        assert conn.provider_type == "LOCAL"
        assert conn.label != ""
        assert conn.description != ""
        assert conn.version == "1.0.0"
        assert conn.provider_id == "native.family.calendar"
        assert len(conn.resource_kinds) >= 1
        assert conn.actor_scope == ["parent", "admin", "system"]
        assert conn.admission_verdict == "admitted"
        assert conn.registration_type == "static"
        assert len(conn.capabilities) >= 1
        assert conn.constitution is not None
        assert conn.policy is not None

    def test_capability_naming_convention(self):
        svc = DOMAIN_SERVICES["family"][0]
        conn = build_connector_definition("family", svc)
        for cap in conn.capabilities:
            assert cap.invocation_mode in ("read", "execute")
            assert cap.name != ""


# ── TestBuilderGeneratesAllCapabilities ──────────────────────────────────


class TestBuilderGeneratesAllCapabilities:
    def test_write_capable_connector(self):
        svc = DOMAIN_SERVICES["family"][0]  # calendar — write-capable
        conn = build_connector_definition("family", svc)
        names = {c.name for c in conn.capabilities}
        actions = {c.action_name for c in conn.capabilities}
        # 2 resource_kinds × (list + create + update + delete) = 8
        assert "list" in actions
        assert "create" in actions
        assert "update" in actions
        assert "delete" in actions
        # All write-capable caps should be execute
        for cap in conn.capabilities:
            if cap.action_name in ("create", "update", "delete"):
                assert cap.invocation_mode == "execute"

    def test_read_only_connector(self):
        svc = DOMAIN_SERVICES["enterprise"][9]  # analytics — write_op=None
        conn = build_connector_definition("enterprise", svc)
        for cap in conn.capabilities:
            assert cap.invocation_mode == "read"
            assert cap.effect == "read"


# ── TestBuilderDerivesProviderId ─────────────────────────────────────────


class TestBuilderDerivesProviderId:
    def test_provider_id_derivation(self):
        svc = DOMAIN_SERVICES["family"][0]
        conn = build_connector_definition("family", svc)
        assert conn.provider_id == "native.family.calendar"

    def test_all_50_have_valid_provider_id(self):
        corpora = build_all_corpora()
        for domain_id, corpus in corpora.items():
            for conn in corpus:
                assert conn.provider_id.startswith("native.")
                assert conn.connector_id in conn.provider_id


# ── TestBuilderConstitutionDefaults ──────────────────────────────────────


class TestBuilderConstitutionDefaults:
    def test_default_constitution_has_prerequisite_reads(self):
        svc = DOMAIN_SERVICES["family"][0]
        conn = build_connector_definition("family", svc)
        assert conn.constitution is not None
        assert len(conn.constitution.prerequisite_reads) >= 1
        preread = conn.constitution.prerequisite_reads[0]
        assert preread["required"] is True
        assert "operation" in preread
        assert "resource_kind" in preread

    def test_default_constitution_has_hil_gates(self):
        svc = DOMAIN_SERVICES["family"][0]
        conn = build_connector_definition("family", svc)
        # calendar has 5 write_inputs → 5 HIL gates
        assert len(conn.constitution.hil_gates) >= 1

    def test_default_constitution_has_verification(self):
        svc = DOMAIN_SERVICES["family"][0]
        conn = build_connector_definition("family", svc)
        assert len(conn.constitution.verification_requirements) >= 1
        methods = [v["method"] for v in conn.constitution.verification_requirements]
        assert "read_after_write" in methods

    def test_mutation_sequencing_has_phase(self):
        svc = DOMAIN_SERVICES["family"][0]
        conn = build_connector_definition("family", svc)
        for step in conn.constitution.mutation_sequencing:
            assert "phase" in step, f"mutation_sequencing step missing phase: {step}"
            assert step["phase"] in ("read", "mutate")
            assert "operation" in step


# ── TestBuilderOntologyIdentity ──────────────────────────────────────────


class TestBuilderOntologyIdentity:
    def test_identity_concept_aliases_generated(self):
        svc = DOMAIN_SERVICES["family"][1]  # tasks
        conn = build_connector_definition("family", svc)
        assert conn.ontology is not None
        aliases = [a["canonical_concept"] for a in conn.ontology.concept_aliases]
        assert "task" in aliases

    def test_resource_connector_edges_have_role(self):
        svc = DOMAIN_SERVICES["family"][0]
        conn = build_connector_definition("family", svc)
        for edge in conn.ontology.resource_connector_edges:
            assert "role" in edge
            assert edge["role"] == "primary"


# ── TestAll50ConnectorsBuild ─────────────────────────────────────────────


class TestAll50ConnectorsBuild:
    def test_all_50_build(self):
        corpora = build_all_corpora()
        total = sum(len(c) for c in corpora.values())
        assert total == 50

    def test_every_connector_has_capabilities(self):
        corpora = build_all_corpora()
        for domain_id, corpus in corpora.items():
            for conn in corpus:
                assert len(conn.capabilities) >= 1, f"{conn.connector_id} has zero capabilities"


# ── TestCapabilityNamesUnique ────────────────────────────────────────────


class TestCapabilityNamesUnique:
    def test_no_duplicate_capability_names(self):
        corpora = build_all_corpora()
        seen: set[str] = set()
        for corpus in corpora.values():
            for conn in corpus:
                for cap in conn.capabilities:
                    # Each capability is identified by (name, invocation_mode, resource_kind, connector_id)
                    key = (
                        f"{cap.name}|{cap.invocation_mode}|{cap.resource_kind}|{conn.connector_id}"
                    )
                    assert key not in seen, f"Duplicate capability key: {key}"
                    seen.add(key)

    def test_send_only_for_communication_connectors(self):
        """Step 6 rule: send only for messaging/team_chat/notifications/dispatch."""
        communication_ids = {"messaging", "team_chat", "notifications", "dispatch"}
        corpora = build_all_corpora()
        for domain_id, corpus in corpora.items():
            for conn in corpus:
                svc_id = conn.connector_id.split(".")[-1]
                has_send = any(cap.action_name == "send" for cap in conn.capabilities)
                if svc_id in communication_ids:
                    assert has_send, f"{conn.connector_id} should have send"
                else:
                    assert (
                        not has_send
                    ), f"{conn.connector_id} should NOT have send (not a communication connector)"
