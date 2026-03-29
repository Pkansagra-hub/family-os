from __future__ import annotations

from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Optional, Set

from .contract_loader import ContractLoader


class WiringLoader:
    """
    Loads and indexes wiring contracts for connectivity analysis.

    - Loads wiring contracts via ContractLoader
    - Builds indexes: capability providers/consumers, event emitters/subscribers
    - Exposes helpers for validation & dependency lookup
    """

    def __init__(self, contract_loader: Optional[ContractLoader] = None):
        self.contract_loader = contract_loader or ContractLoader()
        self._indexed: bool = False
        self._wiring_specs: Dict[str, Dict[str, Any]] = {}

        self._cap_providers: DefaultDict[str, List[str]] = defaultdict(list)
        self._cap_consumers: DefaultDict[str, List[str]] = defaultdict(list)
        self._event_emitters: DefaultDict[str, List[str]] = defaultdict(list)
        self._event_subscribers: DefaultDict[str, List[str]] = defaultdict(list)

    def load_wiring_spec(self, module_id: str) -> Dict[str, Any]:
        wiring_contract = self.contract_loader.load_wiring_contract(module_id)
        return {
            "capabilities": wiring_contract.get("capabilities", {}),
            "events": wiring_contract.get("events", {}),
            "mailboxes": wiring_contract.get("mailboxes", {}),
            "state": wiring_contract.get("state", {}),
            "imports": wiring_contract.get("imports", {}),
            "code": wiring_contract.get("code", {}),
            "wiring": wiring_contract.get("wiring", {}),
            "files": wiring_contract.get("files", {}),
            "runtime_assertions": wiring_contract.get("runtime_assertions", {}),
            "metadata": wiring_contract.get("metadata", {}),
        }

    def index_all_modules(self) -> None:
        """Load all module wiring contracts and build indexes."""
        self._cap_providers.clear()
        self._cap_consumers.clear()
        self._event_emitters.clear()
        self._event_subscribers.clear()
        self._wiring_specs.clear()

        modules_dir = self.contract_loader.contracts_dir / "modules"
        if not modules_dir.exists():
            self._indexed = True
            return

        for module_dir in modules_dir.iterdir():
            if not module_dir.is_dir():
                continue
            module_id = module_dir.name
            try:
                spec = self.load_wiring_spec(module_id)
                self._wiring_specs[module_id] = spec

                for cap in spec["capabilities"].get("provides", []) or []:
                    self._cap_providers[cap["name"]].append(module_id)
                for cap in spec["capabilities"].get("consumes", []) or []:
                    self._cap_consumers[cap["name"]].append(module_id)

                for ev in spec["events"].get("emits", []) or []:
                    self._event_emitters[ev["topic"]].append(module_id)
                for ev in spec["events"].get("subscribes", []) or []:
                    self._event_subscribers[ev["topic"]].append(module_id)

            except Exception:
                # keep indexing others; validators will surface this later
                continue

        self._indexed = True

    def _ensure_indexed(self) -> None:
        if not self._indexed:
            self.index_all_modules()

    def get_capability_consumers(self, capability_name: str) -> List[str]:
        self._ensure_indexed()
        return list(self._cap_consumers.get(capability_name, []))

    def get_capability_providers(self, capability_name: str) -> List[str]:
        self._ensure_indexed()
        return list(self._cap_providers.get(capability_name, []))

    def validate_wiring_connections(self, module_id: str) -> List[str]:
        self._ensure_indexed()
        errors: List[str] = []

        spec = self._wiring_specs.get(module_id) or self.load_wiring_spec(module_id)

        # Capabilities: every consumed cap must have at least one provider
        for cap in spec["capabilities"].get("consumes", []) or []:
            cap_name = cap["name"]
            if not self._cap_providers.get(cap_name):
                errors.append(f"Capability '{cap_name}' is consumed but has no provider")

        # Events: every subscribed topic must have at least one emitter
        for ev in spec["events"].get("subscribes", []) or []:
            topic = ev["topic"]
            if not self._event_emitters.get(topic):
                errors.append(f"Event '{topic}' is subscribed but has no emitter")

        # Mailboxes: route.from must match an actor mailbox (not actor id)
        mailboxes = spec.get("mailboxes", {}) or {}
        actors = mailboxes.get("actors", []) or []
        routes = mailboxes.get("routes", []) or []
        actor_mailboxes = {a.get("mailbox") for a in actors if a.get("mailbox")}

        for route in routes:
            src = route.get("from")
            if src and src not in actor_mailboxes:
                errors.append(f"Mailbox route 'from={src}' has no matching actor mailbox")

        return errors

    def get_module_dependencies(self, module_id: str) -> Set[str]:
        spec = self.load_wiring_spec(module_id)
        deps: Set[str] = set()

        for cap in spec["capabilities"].get("consumes", []) or []:
            provider = cap.get("provider")
            if provider:
                deps.add(provider)

        return deps
