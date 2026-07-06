"""
POC v2: Context Factory — GPS + 33 native apps + embeddings
=============================================================
Creates an isolated in-memory GPS per benchmark run, registers
6 real FamilyOS connectors + 27 stub native apps, builds connector
documents and MiniLM embeddings.

NO fake distractors (chase.*, nest.*, fitbit.*, etc.).
NO namespace prior.
OS domain from active_os_set only.

Usage:
  python scripts/poc_v2/context_factory.py --validate   # smoketest
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from k1.fabric.manifest_translator import register_definition_to_store
from k1.fabric.stores.global_projection_store import GlobalProjectionStore
from k1.tools.family.calendar.definition import CALENDAR_DEFINITION
from k1.tools.family.chores.definition import CHORES_DEFINITION
from k1.tools.family.family_settings.definition import FAMILY_SETTINGS_DEFINITION
from k1.tools.family.reminders.definition import REMINDERS_DEFINITION
from k1.tools.family.shopping.definition import SHOPPING_DEFINITION
from k1.tools.family.tasks.definition import TASKS_DEFINITION
from scripts.poc_v2.native_app_stubs import ALL_STUBS, NativeAppStub

# ═══════════════════════════════════════════════════════════════════════════
# Real FamilyOS definitions
# ═══════════════════════════════════════════════════════════════════════════

REAL_FAMILY_DEFS: dict[str, Any] = {
    "family.calendar": CALENDAR_DEFINITION,
    "family.shopping": SHOPPING_DEFINITION,
    "family.tasks": TASKS_DEFINITION,
    "family.reminders": REMINDERS_DEFINITION,
    "family.chores": CHORES_DEFINITION,
    "family.family_settings": FAMILY_SETTINGS_DEFINITION,
}

# OS domain for FamilyOS apps
FAMILY_OS_DOMAIN = "family"

# All 33 native apps
ALL_NATIVE_APP_IDS = list(REAL_FAMILY_DEFS.keys()) + list(ALL_STUBS.keys())

# connector_id → os_domain
OS_DOMAIN_MAP: dict[str, str] = {}
for cid in REAL_FAMILY_DEFS:
    OS_DOMAIN_MAP[cid] = "family"
for cid, stub in ALL_STUBS.items():
    OS_DOMAIN_MAP[cid] = stub.os_domain


# ═══════════════════════════════════════════════════════════════════════════
# Document builder
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ConnectorDocument:
    """A searchable document for one native app."""

    connector_id: str
    os_domain: str
    text: str  # The full text that gets embedded
    label: str


def build_document_text(stub: NativeAppStub) -> str:
    """Build searchable text for a stub app."""
    return stub.to_document_text()


def build_family_document_text(connector_id: str, definition: Any) -> str:
    """Build searchable text for a real FamilyOS connector from its definition."""
    parts: list[str] = []

    # Type-safe attribute access
    title: str = getattr(definition, "title", "") or getattr(definition, "adapter_id", connector_id)
    desc: str = getattr(definition, "description", "") or getattr(definition, "summary", "")

    parts.append(f"{title}. {desc}")

    # Domain tags
    domain_tags: list[str] = list(getattr(definition, "domain_tags", []) or [])
    if domain_tags:
        parts.append(f"Tags: {', '.join(domain_tags)}")

    # Tool action names + descriptions
    actions: list[Any] = list(getattr(definition, "actions", []) or [])
    if actions:
        action_texts: list[str] = []
        for action in actions:
            action_name: str = getattr(action, "action_name", "") or getattr(action, "name", "")
            action_desc: str = getattr(action, "description", "")
            if action_name:
                if action_desc:
                    action_texts.append(f"{action_name}: {action_desc}")
                else:
                    action_texts.append(action_name)
        if action_texts:
            parts.append(f"Tools: {'; '.join(action_texts)}")

    # Constitution — teaching surface prose
    constitution: dict[str, Any] | None = getattr(definition, "constitution", None)
    if constitution and isinstance(constitution, dict):
        summary: str = constitution.get("precondition_summary", "") or ""
        companion: str = constitution.get("companion_resource_summary", "") or ""
        hil: str = constitution.get("hil_trigger_summary", "") or ""
        if summary:
            parts.append(summary)
        if companion:
            parts.append(companion)
        if hil:
            parts.append(hil)

    return " ".join(parts)


def build_all_documents() -> dict[str, ConnectorDocument]:
    """Build one ConnectorDocument per native app (6 real + 27 stubs)."""
    docs: dict[str, ConnectorDocument] = {}

    # Real FamilyOS definitions
    for connector_id, definition in REAL_FAMILY_DEFS.items():
        text = build_family_document_text(connector_id, definition)
        docs[connector_id] = ConnectorDocument(
            connector_id=connector_id,
            os_domain="family",
            text=text,
            label=connector_id,
        )

    # Stub definitions
    for connector_id, stub in ALL_STUBS.items():
        text = build_document_text(stub)
        docs[connector_id] = ConnectorDocument(
            connector_id=connector_id,
            os_domain=stub.os_domain,
            text=text,
            label=stub.label,
        )

    return docs


# ═══════════════════════════════════════════════════════════════════════════
# Embedding index
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class EmbeddingIndex:
    """Simple embedding index — pre-computed MiniLM embeddings + cosine similarity."""

    connector_ids: list[str]
    embeddings: Any  # numpy array (n_docs, 384)
    _model: Any = field(default=None, repr=False)

    @classmethod
    def build(cls, docs: dict[str, ConnectorDocument]) -> "EmbeddingIndex":
        """Build index from documents using MiniLM-L6."""
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("all-MiniLM-L6-v2")
        connector_ids = list(docs.keys())
        texts = [docs[cid].text for cid in connector_ids]
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return cls(connector_ids=connector_ids, embeddings=embeddings, _model=model)

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        candidate_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        """Search for top-k connectors by cosine similarity.

        Args:
            query: User utterance
            top_k: Number of results to return
            candidate_ids: If provided, only search within these connector IDs
        """
        import numpy as np

        query_vec = self._model.encode([query], normalize_embeddings=True, show_progress_bar=False)
        scores = np.dot(self.embeddings, query_vec.T).flatten()

        # Build (connector_id, score) pairs, filter by candidates if provided
        results: list[tuple[str, float]] = []
        for i, cid in enumerate(self.connector_ids):
            if candidate_ids is None or cid in candidate_ids:
                results.append((cid, float(scores[i])))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]


# ═══════════════════════════════════════════════════════════════════════════
# Context factory — main entry point
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class PocContext:
    """Fresh isolated context for a POC v2 benchmark run."""

    docs: dict[str, ConnectorDocument]
    index: EmbeddingIndex
    os_domain_map: dict[str, str]


def create_context() -> PocContext:
    """Create a fresh POC context with all 33 native apps loaded.

    Returns a PocContext with:
      - 33 ConnectorDocuments (6 real FamilyOS + 27 stubs)
      - MiniLM embedding index
      - OS domain map
    """
    t0 = time.monotonic()

    docs = build_all_documents()
    assert len(docs) == 33, f"Expected 33 docs, got {len(docs)}"

    index = EmbeddingIndex.build(docs)

    elapsed = (time.monotonic() - t0) * 1000
    print(
        f"  POC context ready: {len(docs)} native apps, {len(index.connector_ids)} indexed, {elapsed:.0f}ms"
    )
    return PocContext(docs=docs, index=index, os_domain_map=dict(OS_DOMAIN_MAP))


# ═══════════════════════════════════════════════════════════════════════════
# Active-OS gating helper
# ═══════════════════════════════════════════════════════════════════════════


def get_visible_apps(ctx: PocContext, active_os_set: set[str]) -> set[str]:
    """Return the set of connector_ids visible in the given active OS domains."""
    return {cid for cid, domain in ctx.os_domain_map.items() if domain in active_os_set}


# ═══════════════════════════════════════════════════════════════════════════
# Smoketest
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if "--validate" in sys.argv:
        print("=== POC v2 Context Factory — Validation ===")
        ctx = create_context()

        # Check we have all 33
        assert len(ctx.docs) == 33, f"Expected 33, got {len(ctx.docs)}"
        family_apps = [c for c, d in ctx.os_domain_map.items() if d == "family"]
        health_apps = [c for c, d in ctx.os_domain_map.items() if d == "health"]
        finance_apps = [c for c, d in ctx.os_domain_map.items() if d == "finance"]
        pharma_apps = [c for c, d in ctx.os_domain_map.items() if d == "pharma"]
        enterprise_apps = [c for c, d in ctx.os_domain_map.items() if d == "enterprise"]

        print(f"  FamilyOS:     {len(family_apps)} apps ({', '.join(family_apps)})")
        print(f"  HealthOS:     {len(health_apps)} apps ({', '.join(health_apps)})")
        print(f"  FinanceOS:    {len(finance_apps)} apps ({', '.join(finance_apps)})")
        print(f"  PharmaOS:     {len(pharma_apps)} apps ({', '.join(pharma_apps)})")
        print(f"  EnterpriseOS: {len(enterprise_apps)} apps ({', '.join(enterprise_apps)})")

        # Check embedding dimension
        assert ctx.index.embeddings.shape == (
            33,
            384,
        ), f"Bad embedding shape: {ctx.index.embeddings.shape}"

        # Check active-OS gating
        family_visible = get_visible_apps(ctx, {"family"})
        assert len(family_visible) == 6, f"Family gating wrong: {len(family_visible)}"
        assert "health.records" not in family_visible

        health_visible = get_visible_apps(ctx, {"health"})
        assert len(health_visible) == 7

        health_family = get_visible_apps(ctx, {"health", "family"})
        assert len(health_family) == 13
        assert "health.records" in health_family
        assert "family.shopping" in health_family

        enterprise_visible = get_visible_apps(ctx, {"enterprise"})
        assert len(enterprise_visible) == 8
        assert "family.calendar" not in enterprise_visible

        # Quick search smoketest
        results = ctx.index.search("check my blood pressure", top_k=3, candidate_ids=health_family)
        print(f"\n  Query 'check my blood pressure' (family+health):")
        for cid, score in results:
            print(f"    {cid}: {score:.4f}")

        # No backend-named connectors
        for cid in ctx.docs:
            assert not cid.startswith("chase."), f"Backend connector leaked: {cid}"
            assert not cid.startswith("nest."), f"Backend connector leaked: {cid}"
            assert not cid.startswith("fitbit."), f"Backend connector leaked: {cid}"

        print("\n  ✅ All validations passed.")
    else:
        print("Usage: python scripts/poc_v2/context_factory.py --validate")
