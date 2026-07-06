"""
POC v2: Contract Compiler — kernel-grade signal extraction
=============================================================
Compiles declarative app contracts into generic indexes.
No domain facts in router code. No if-else branches.

What this builds:
  1. EffectLexicon          — verb phrase → effect (compiled from declarative map)
  2. ResourcePhraseTrie     — phrase → resource_kind (compiled from all app contracts)
  3. BackendSlotIndex       — backend name → slot → native_app
  4. NativeAppContract      — unified contract for every app (real + stub)
  5. SignalExtractor        — generic extraction using compiled indexes

Usage:
  python scripts/poc_v2/contract_compiler.py --validate
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ═══════════════════════════════════════════════════════════════════════════
# Tokenizer (shared)
# ═══════════════════════════════════════════════════════════════════════════

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "to",
        "for",
        "of",
        "on",
        "in",
        "at",
        "my",
        "me",
        "i",
        "we",
        "our",
        "us",
        "he",
        "she",
        "it",
        "they",
        "them",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "do",
        "does",
        "did",
        "can",
        "could",
        "will",
        "would",
        "should",
        "may",
        "might",
        "have",
        "has",
        "had",
        "am",
        "you",
        "your",
        "with",
        "this",
        "that",
        "from",
        "not",
        "but",
        "or",
        "and",
        "if",
        "so",
        "no",
        "just",
        "about",
        "like",
        "get",
        "got",
        "need",
        "some",
        "any",
        "all",
        "up",
        "out",
        "what",
        "when",
        "where",
        "who",
        "how",
        "please",
        "hi",
        "hey",
        "ok",
        "okay",
        "yeah",
        "yes",
        "nah",
        "nope",
    }
)


def _tokenize(text: str) -> list[str]:
    text = text.lower().replace("_", " ")
    return [t for t in _TOKEN_RE.findall(text) if len(t) >= 2 and t not in _STOPWORDS]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Effect Lexicon — compiled from declarative data
# ═══════════════════════════════════════════════════════════════════════════

# The single source of truth for verb→effect mapping.
# Router code never references this directly — it uses the compiled EffectLexicon.
_DECLARATIVE_EFFECTS: dict[str, list[str]] = {
    "create": [
        "create",
        "add",
        "make",
        "schedule",
        "set",
        "start",
        "plan",
        "new",
        "book",
        "order",
        "assign",
    ],
    "read": [
        "show",
        "view",
        "get",
        "check",
        "list",
        "find",
        "search",
        "tell",
        "look",
        "see",
        "pull",
        "display",
        "what",
        "how",
        "did",
        "is",
        "are",
        "was",
        "were",
        "has",
        "have",
        "my",
    ],
    "update": [
        "change",
        "edit",
        "modify",
        "rename",
        "move",
        "reschedule",
        "adjust",
        "update",
        "switch",
        "toggle",
        "rotate",
    ],
    "delete": ["delete", "remove", "cancel", "clear", "drop", "archive"],
    "complete": ["done", "finish", "complete", "mark", "resolve", "close", "check", "bought"],
    "execute": [
        "run",
        "deploy",
        "trigger",
        "send",
        "submit",
        "process",
        "launch",
        "dispatch",
        "execute",
        "post",
        "push",
    ],
}


@dataclass
class EffectLexicon:
    """Compiled effect lexicon — verb token → effect."""

    _token_to_effect: dict[str, str] = field(default_factory=dict)

    @classmethod
    def compile(cls) -> "EffectLexicon":
        lexicon = cls()
        for effect, aliases in _DECLARATIVE_EFFECTS.items():
            for alias in aliases:
                # Store by tokenized form
                for token in _tokenize(alias):
                    if token not in lexicon._token_to_effect:
                        lexicon._token_to_effect[token] = effect
        return lexicon

    def extract(self, utterance: str) -> set[str]:
        """Extract effects from raw utterance. Generic — no domain facts."""
        tokens = _tokenize(utterance)
        effects: set[str] = set()
        for t in tokens:
            if t in self._token_to_effect:
                effects.add(self._token_to_effect[t])
        if not effects:
            effects.add("read")  # default
        return effects


# ═══════════════════════════════════════════════════════════════════════════
# 2. Resource Phrase Trie — compiled from all app contracts
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ResourcePhraseTrie:
    """Prefix tree mapping multi-word phrases → resource_kind.

    Built from declarative resource_phrase_aliases in every app contract.
    Router calls extract_phrases() — generic, no domain facts in router code.
    """

    _phrase_to_resource: dict[str, str] = field(default_factory=dict)
    # Trie: dict of token → {children, terminal_resource}
    _root: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def compile(cls, phrase_aliases: dict[str, list[str]]) -> "ResourcePhraseTrie":
        """Compile phrase→resource_kind mapping into a prefix trie.

        Args:
            phrase_aliases: {resource_kind: [phrase1, phrase2, ...]}
        """
        trie = cls()
        seen: dict[str, str] = {}  # phrase → resource_kind (first-wins)

        for resource_kind, phrases in phrase_aliases.items():
            for phrase in phrases:
                phrase_lower = phrase.lower().strip()
                if phrase_lower and phrase_lower not in seen:
                    seen[phrase_lower] = resource_kind

        trie._phrase_to_resource = seen

        # Build prefix trie for longest-match
        for phrase, resource_kind in seen.items():
            tokens = _tokenize(phrase)
            if not tokens:
                tokens = phrase.split()  # fallback
            node = trie._root
            for token in tokens:
                if token not in node:
                    node[token] = {}
                node = node[token]
            node["__resource__"] = resource_kind

        return trie

    def extract_phrases(self, utterance: str) -> set[str]:
        """Extract resource kinds from utterance using longest-match trie.

        No domain facts. No if-else. Just trie matching.
        """
        tokens = _tokenize(utterance)
        if not tokens:
            return set()

        found: set[str] = set()
        i = 0
        while i < len(tokens):
            node = self._root
            longest_match: str | None = None
            j = i
            while j < len(tokens) and tokens[j] in node:
                node = node[tokens[j]]
                j += 1
                if "__resource__" in node:
                    longest_match = node["__resource__"]
            if longest_match:
                found.add(longest_match)
                i = j  # skip past matched phrase
            else:
                i += 1

        # Also check single-token exact matches
        for token in tokens:
            if token in self._phrase_to_resource:
                found.add(self._phrase_to_resource[token])

        return found


# ═══════════════════════════════════════════════════════════════════════════
# 3. Backend Slot Index — compiled from backend_slots in contracts
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class BackendSlotIndex:
    """Maps backend names → slot_type → native_app.

    "Walmart" → grocery_retailers → family.shopping
    "Fitbit" → wearables → health.vitals
    """

    _backend_to_slot: dict[str, str] = field(default_factory=dict)  # backend_name → slot_type
    _slot_to_apps: dict[str, list[str]] = field(
        default_factory=dict
    )  # slot_type → [native_app_ids]

    @classmethod
    def compile(cls, backend_slots: dict[str, dict[str, list[str]]]) -> "BackendSlotIndex":
        """Compile from {native_app_id: {slot_type: [backend_names]}}."""
        index = cls()
        for app_id, slots in backend_slots.items():
            for slot_type, backend_names in slots.items():
                index._slot_to_apps.setdefault(slot_type, []).append(app_id)
                for name in backend_names:
                    name_clean = name.lower().replace("-", "").replace(" ", "")
                    if name_clean not in index._backend_to_slot:
                        index._backend_to_slot[name_clean] = slot_type
        return index

    def extract(self, utterance: str) -> list[tuple[str, str]]:
        """Extract backend hints from utterance.

        Returns: [(slot_type, native_app_id), ...]
        Generic — no "if Walmart" in router code.
        """
        tokens = set(_tokenize(utterance))
        results: list[tuple[str, str]] = []

        for backend_name, slot_type in self._backend_to_slot.items():
            # Check if any token or multi-word matches backend name
            name_tokens = set(_tokenize(backend_name))
            if name_tokens & tokens or backend_name in utterance.lower().replace(" ", ""):
                apps = self._slot_to_apps.get(slot_type, [])
                for app_id in apps:
                    results.append((slot_type, app_id))

        return results


# ═══════════════════════════════════════════════════════════════════════════
# 4. NativeAppContract — unified contract for ALL apps
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class NativeAppContract:
    """Unified contract for a native app — real or stub.

    All apps compile into this same shape. No asymmetry.
    """

    connector_id: str
    os_domain: str
    label: str
    description: str
    owns_resources: list[str]
    does_not_own_resources: list[str]
    owns_effects: list[str]
    concept_aliases: list[str]  # ← NOW PRESENT for ALL apps (real + stub)
    operation_aliases: list[str]  # ← NOW PRESENT for ALL apps
    ambiguous_with: dict[str, list[str]]
    backend_slots: dict[str, list[str]]


# ═══════════════════════════════════════════════════════════════════════════
# 5. NativeAppContractRegistry — compiles all indexes
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class SignalExtractor:
    """Generic signal extraction. No domain facts. Reads compiled indexes."""

    _effect_lexicon: EffectLexicon
    _resource_trie: ResourcePhraseTrie
    _backend_index: BackendSlotIndex

    def extract(self, utterance: str) -> "ExtractedSignals":
        """Extract all signals from a raw utterance."""
        return ExtractedSignals(
            effects=self._effect_lexicon.extract(utterance),
            resources=self._resource_trie.extract_phrases(utterance),
            backend_hints=self._backend_index.extract(utterance),
        )


@dataclass
class ExtractedSignals:
    """Signals extracted from a raw utterance — generic, no domain facts."""

    effects: set[str]
    resources: set[str]
    backend_hints: list[tuple[str, str]]  # [(slot_type, native_app_id), ...]


@dataclass
class NativeAppContractRegistry:
    """Central registry that compiles all contracts into searchable indexes."""

    contracts: dict[str, NativeAppContract]
    effect_lexicon: EffectLexicon
    resource_trie: ResourcePhraseTrie
    backend_index: BackendSlotIndex
    signal_extractor: SignalExtractor

    @classmethod
    def compile(
        cls,
        boundaries: dict[str, Any],  # NativeAppBoundary dicts
        stubs: dict[str, Any],  # NativeAppStub dicts
        family_docs: dict[str, Any],  # ConnectorDocument dicts for real apps
    ) -> "NativeAppContractRegistry":
        """Compile all contracts into indexes. One call builds everything."""

        contracts: dict[str, NativeAppContract] = {}

        # ── Build resource phrase aliases from all apps ──
        phrase_aliases: dict[str, list[str]] = defaultdict(list)

        # Compile effects FIRST — used to filter effect tokens out of resource phrases
        effect_lexicon = EffectLexicon.compile()
        effect_tokens: set[str] = set(effect_lexicon._token_to_effect.keys())

        # Generic tokens that are never useful as standalone resource signals
        _GENERIC_BLACKLIST: frozenset[str] = frozenset(
            {
                "data",
                "log",
                "note",
                "info",
                "entry",
                "item",
                "type",
                "kind",
                "name",
                "date",
                "time",
                "user",
                "role",
                "status",
                "state",
                "level",
                "rate",
                "view",
                "form",
                "file",
                "link",
            }
        )

        for app_id, boundary in boundaries.items():
            # Concept + operation aliases from stubs
            stub = stubs.get(app_id)
            concept_aliases: list[str] = list(stub.concept_aliases) if stub else []
            operation_aliases: list[str] = list(stub.operation_aliases) if stub else []

            # For real FamilyOS apps without stubs, extract aliases from doc text
            if not concept_aliases and app_id in family_docs:
                doc = family_docs[app_id]
                # Extract likely noun phrases from document text as concept aliases
                concept_aliases = _extract_aliases_from_doc(doc.text, "concept")
                operation_aliases = _extract_aliases_from_doc(doc.text, "operation")

            # Build phrase aliases for resource trie
            for rk in boundary.owns_resources:
                phrase_aliases[rk].append(rk)  # resource_kind name itself
                # Decompose compound names into individual tokens, filtering:
                #   - effect tokens (keep signal channels clean)
                #   - generic blacklist terms
                #   - tokens < 3 chars (too ambiguous alone)
                for rk_token in _tokenize(rk):
                    if len(rk_token) < 3:
                        continue
                    if rk_token in effect_tokens:
                        continue  # "run" is an effect, not a resource
                    if rk_token in _GENERIC_BLACKLIST:
                        continue  # "data", "log", "note" are too generic
                    if rk_token not in phrase_aliases[rk]:
                        phrase_aliases[rk].append(rk_token)
                # Add concept aliases as phrases for this resource kind
                for alias in concept_aliases:
                    if _is_related_phrase(alias, rk):
                        phrase_aliases[rk].append(alias)

            contracts[app_id] = NativeAppContract(
                connector_id=app_id,
                os_domain=boundary.os_domain,
                label=getattr(boundary, "label", app_id),
                description=getattr(boundary, "description", ""),
                owns_resources=list(boundary.owns_resources),
                does_not_own_resources=list(boundary.does_not_own_resources),
                owns_effects=list(boundary.owns_effects),
                concept_aliases=concept_aliases,
                operation_aliases=operation_aliases,
                ambiguous_with=dict(boundary.ambiguous_with),
                backend_slots=dict(boundary.backend_slots),
            )

        # ── Compile indexes ──
        resource_trie = ResourcePhraseTrie.compile(dict(phrase_aliases))
        backend_index = BackendSlotIndex.compile(
            {app_id: c.backend_slots for app_id, c in contracts.items()}
        )
        signal_extractor = SignalExtractor(effect_lexicon, resource_trie, backend_index)

        return cls(
            contracts=contracts,
            effect_lexicon=effect_lexicon,
            resource_trie=resource_trie,
            backend_index=backend_index,
            signal_extractor=signal_extractor,
        )

    def schema_score(
        self,
        app_id: str,
        signals: ExtractedSignals,
        *,
        _all_visible_apps: set[str] | None = None,
    ) -> float:
        """Score an app against extracted signals. Generic — reads contracts, no domain facts."""
        contract = self.contracts.get(app_id)
        if contract is None:
            return 0.0

        # 1. Hard veto: query resources intersect does_not_own
        not_owned = set(contract.does_not_own_resources)
        if signals.resources & not_owned:
            return 0.0

        score = 0.0
        owned = set(contract.owns_resources)

        # 2. Resource kind compatibility (weight: 0.30)
        if signals.resources:
            overlap = len(signals.resources & owned)
            score += (overlap / max(len(signals.resources), 1)) * 0.30

            # ── Specificity penalty: another visible app owns MORE query resources ──
            if _all_visible_apps and overlap > 0:
                best_other_overlap = 0
                for other_id in (_all_visible_apps - {app_id}):
                    other = self.contracts.get(other_id)
                    if other and not (signals.resources & set(other.does_not_own_resources)):
                        other_overlap = len(signals.resources & set(other.owns_resources))
                        if other_overlap > best_other_overlap:
                            best_other_overlap = other_overlap
                if best_other_overlap > overlap:
                    score -= 0.10 * (best_other_overlap - overlap) / max(len(signals.resources), 1)
                    score = max(score, 0.0)

        # 3. Effect compatibility (weight: 0.20)
        valid_effects = set(contract.owns_effects)
        if signals.effects:
            overlap = len(signals.effects & valid_effects)
            score += (overlap / max(len(signals.effects), 1)) * 0.20

        # 4. Concept alias overlap (weight: 0.25) — NOW WORKS FOR ALL APPS
        if signals.resources:
            alias_tokens = set(_tokenize(" ".join(contract.concept_aliases)))
            query_tokens = set(_tokenize(" ".join(signals.resources)))
            if query_tokens:
                overlap = len(query_tokens & alias_tokens)
                score += (overlap / max(len(query_tokens), 1)) * 0.25

        # 5. Operation alias overlap (weight: 0.25) — NOW WORKS FOR ALL APPS
        if signals.effects:
            op_tokens = set(_tokenize(" ".join(contract.operation_aliases)))
            query_tokens = set(_tokenize(" ".join(signals.resources)))
            if query_tokens:
                overlap = len(query_tokens & op_tokens)
                score += (overlap / max(len(query_tokens), 1)) * 0.25

        # 6. Backend-slot boost (weight: 0.10 bonus)
        for slot_type, hint_app_id in signals.backend_hints:
            if hint_app_id == app_id:
                score += 0.10
                break

        return min(score, 1.0)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _extract_aliases_from_doc(doc_text: str, kind: str) -> list[str]:
    """Extract likely concept/operation aliases from a FamilyOS connector document.

    POC-grade extraction from constitution/description text.
    In production, these would be declarative fields in the definition.
    """
    tokens = _tokenize(doc_text)
    if kind == "concept":
        # Extract 2-3 word noun phrases as concept aliases
        aliases: list[str] = []
        bigrams: dict[str, int] = defaultdict(int)
        for i in range(len(tokens) - 1):
            bigram = f"{tokens[i]} {tokens[i+1]}"
            bigrams[bigram] += 1
        # Take top bigrams as concept aliases
        for phrase, count in sorted(bigrams.items(), key=lambda x: -x[1])[:30]:
            if count >= 1:
                aliases.append(phrase)
        return aliases

    if kind == "operation":
        # Extract single-token verbs as operation aliases
        verb_indicators = {
            "create",
            "manage",
            "view",
            "check",
            "update",
            "delete",
            "add",
            "set",
            "list",
            "track",
            "sync",
            "share",
            "compare",
            "schedule",
            "assign",
            "approve",
            "reject",
            "complete",
        }
        aliases = []
        for token in tokens:
            if token in verb_indicators and token not in aliases:
                aliases.append(token)
        return aliases

    return []


def _is_related_phrase(alias: str, resource_kind: str) -> bool:
    """Check if an alias phrase is semantically related to a resource kind.

    Only returns True when alias and resource_kind share at least one token.
    No length-based fallback — short aliases are not automatically related.
    """
    alias_tokens = set(_tokenize(alias))
    rk_tokens = set(_tokenize(resource_kind))
    return len(alias_tokens & rk_tokens) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if "--validate" in sys.argv:
        from scripts.poc_v2.boundary_contracts import ALL_BOUNDARIES
        from scripts.poc_v2.context_factory import create_context
        from scripts.poc_v2.native_app_stubs import ALL_STUBS

        print("=== Contract Compiler — Validation ===\n")

        ctx = create_context()
        registry = NativeAppContractRegistry.compile(
            boundaries=ALL_BOUNDARIES,
            stubs=ALL_STUBS,
            family_docs=ctx.docs,
        )

        print(f"  Contracts: {len(registry.contracts)} apps")
        print(f"  Effect lexicon: {len(registry.effect_lexicon._token_to_effect)} tokens")
        print(f"  Resource trie: {len(registry.resource_trie._phrase_to_resource)} phrases")
        print(f"  Backend index: {len(registry.backend_index._backend_to_slot)} backend names")

        # Check signal extraction
        test_utterances = [
            "remind me to take my blood pressure medication",
            "add milk to my grocery list",
            "deploy the auth service to staging",
            "order milk from Walmart",
        ]
        for utt in test_utterances:
            signals = registry.signal_extractor.extract(utt)
            print(f"\n  '{utt}'")
            print(f"    effects:   {signals.effects}")
            print(f"    resources: {signals.resources}")
            print(f"    backends:  {signals.backend_hints}")

        # Check that real FamilyOS apps get alias scoring (not just stubs)
        for app_id in ["family.shopping", "health.vitals"]:
            contract = registry.contracts.get(app_id)
            if contract:
                print(f"\n  {app_id}:")
                print(
                    f"    concept_aliases:  {len(contract.concept_aliases)} aliases (sample: {contract.concept_aliases[:5]})"
                )
                print(
                    f"    operation_aliases: {len(contract.operation_aliases)} aliases (sample: {contract.operation_aliases[:5]})"
                )
                assert len(contract.concept_aliases) > 0, f"{app_id} has NO concept aliases!"
                assert len(contract.operation_aliases) > 0, f"{app_id} has NO operation aliases!"

        print("\n  ✅ All validations passed. Contracts unified. Signal extraction generic.")
    else:
        print("Usage: python scripts/poc_v2/contract_compiler.py --validate")
