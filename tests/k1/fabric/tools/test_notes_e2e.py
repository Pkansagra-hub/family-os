"""
Integration tests for Phase 3 -- Notes MCP Server (FastMCP, stdio).

Tests the full notes tool stack:
  - Note model (frozen, to_dict, to_summary, to_search_result, from_dict)
  - NoteStorage (SQLite CRUD, in-memory)
  - FastMCP server (tool registration, call_tool via Client)
  - Contract YAML parsing and validation

NO MOCKS -- all tests use real components with in-memory SQLite.

References:
  - fabric_tool_implementation_plan.md Phase 3, Section 5.1
  - tests/k1/fabric/tools/test_calendar_e2e.py (pattern)
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from fastmcp import Client

from k1.fabric.contracts import parse_contract
from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.types import CapabilityContract
from k1.tools.mcp_servers.notes.models import Note
from k1.tools.mcp_servers.notes.server import create_server, mcp
from k1.tools.mcp_servers.notes.storage import NoteStorage

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONTRACTS_DIR = Path(__file__).resolve().parents[4] / "k1" / "contracts" / "tools"


# =========================================================================
# Section 1: Note model
# =========================================================================


class TestNoteModel:
    """Note frozen dataclass behavior."""

    def test_default_construction(self) -> None:
        note = Note()
        assert note.title == ""
        assert note.content == ""
        assert note.tags == ()
        assert note.note_id != ""  # UUID auto-generated

    def test_full_construction(self) -> None:
        note = Note(
            note_id="n-1",
            title="Shopping List",
            content="Milk, Eggs, Bread",
            tags=("groceries", "urgent"),
            created_at="2025-03-14T10:00:00Z",
        )
        assert note.note_id == "n-1"
        assert note.title == "Shopping List"
        assert note.tags == ("groceries", "urgent")

    def test_frozen_immutability(self) -> None:
        note = Note(title="Test")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            note.title = "Changed"  # type: ignore[misc]

    def test_to_dict(self) -> None:
        note = Note(note_id="n-2", title="Hello", content="World", tags=("a", "b"))
        d = note.to_dict()
        assert d["note_id"] == "n-2"
        assert d["title"] == "Hello"
        assert d["content"] == "World"
        assert d["tags"] == ["a", "b"]

    def test_to_summary(self) -> None:
        note = Note(note_id="n-3", title="Summary", content="Long text here")
        s = note.to_summary()
        assert s["note_id"] == "n-3"
        assert s["title"] == "Summary"
        assert "content" not in s  # summary excludes content

    def test_to_search_result(self) -> None:
        note = Note(note_id="n-4", title="Search", content="Some searchable content")
        r = note.to_search_result(snippet="...searchable...")
        assert r["snippet"] == "...searchable..."
        assert "content" not in r

    def test_to_search_result_default_snippet(self) -> None:
        note = Note(note_id="n-5", title="Auto", content="Short content")
        r = note.to_search_result()
        assert r["snippet"] == "Short content"

    def test_from_dict_roundtrip(self) -> None:
        data = {
            "note_id": "n-6",
            "title": "Roundtrip",
            "content": "Body",
            "tags": ["x", "y"],
        }
        note = Note.from_dict(data)
        assert note.note_id == "n-6"
        assert note.tags == ("x", "y")

    def test_from_dict_tags_as_csv_string(self) -> None:
        note = Note.from_dict({"title": "CSV", "tags": "a, b, c"})
        assert note.tags == ("a", "b", "c")

    def test_from_dict_missing_optional(self) -> None:
        note = Note.from_dict({"title": "Min"})
        assert note.title == "Min"
        assert note.content == ""
        assert note.tags == ()


# =========================================================================
# Section 2: NoteStorage (SQLite, in-memory)
# =========================================================================


class TestNoteStorage:
    """NoteStorage CRUD with real in-memory SQLite."""

    @pytest.fixture()
    def storage(self) -> NoteStorage:
        s = NoteStorage(db_path=":memory:")
        yield s  # type: ignore[misc]
        s.close()

    @pytest.mark.asyncio
    async def test_create_note(self, storage: NoteStorage) -> None:
        note = await storage.create_note(title="Test", content="Body")
        assert note.title == "Test"
        assert note.content == "Body"
        assert note.note_id != ""
        assert note.created_at != ""

    @pytest.mark.asyncio
    async def test_create_note_with_tags(self, storage: NoteStorage) -> None:
        note = await storage.create_note(title="Tagged", content="Body", tags="a,b,c")
        assert note.tags == ("a", "b", "c")

    @pytest.mark.asyncio
    async def test_list_notes_empty(self, storage: NoteStorage) -> None:
        notes = await storage.list_notes()
        assert notes == []

    @pytest.mark.asyncio
    async def test_list_notes_returns_created(self, storage: NoteStorage) -> None:
        await storage.create_note(title="N1", content="C1")
        await storage.create_note(title="N2", content="C2")
        notes = await storage.list_notes()
        assert len(notes) == 2

    @pytest.mark.asyncio
    async def test_list_notes_respects_max_results(self, storage: NoteStorage) -> None:
        for i in range(5):
            await storage.create_note(title=f"Note {i}", content=f"Content {i}")
        notes = await storage.list_notes(max_results=3)
        assert len(notes) == 3

    @pytest.mark.asyncio
    async def test_list_notes_filter_by_tag(self, storage: NoteStorage) -> None:
        await storage.create_note(title="Groceries", content="Milk", tags="shopping")
        await storage.create_note(title="Meeting", content="Standup", tags="work")
        notes = await storage.list_notes(tag="shopping")
        assert len(notes) == 1
        assert notes[0].title == "Groceries"

    @pytest.mark.asyncio
    async def test_search_notes_by_title(self, storage: NoteStorage) -> None:
        await storage.create_note(title="Python Tutorial", content="Learn Python")
        await storage.create_note(title="Grocery List", content="Eggs")
        results = await storage.search_notes(query="Python")
        assert len(results) == 1
        assert results[0].title == "Python Tutorial"

    @pytest.mark.asyncio
    async def test_search_notes_by_content(self, storage: NoteStorage) -> None:
        await storage.create_note(title="Memo", content="Remember to buy eggs")
        results = await storage.search_notes(query="eggs")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_notes_no_match(self, storage: NoteStorage) -> None:
        await storage.create_note(title="Note", content="Something")
        results = await storage.search_notes(query="nonexistent")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_get_note_by_id(self, storage: NoteStorage) -> None:
        note = await storage.create_note(title="Find Me", content="Here")
        found = await storage.get_note(note.note_id)
        assert found is not None
        assert found.title == "Find Me"

    @pytest.mark.asyncio
    async def test_get_note_not_found(self, storage: NoteStorage) -> None:
        found = await storage.get_note("nonexistent-id")
        assert found is None


# =========================================================================
# Section 3: FastMCP Server (via Client)
# =========================================================================


class TestNotesMCPServer:
    """Notes MCP server via FastMCP Client -- in-process testing."""

    @pytest.fixture(autouse=True)
    def _setup_server(self) -> None:
        """Fresh storage for each test."""
        create_server(":memory:")

    @pytest.mark.asyncio
    async def test_list_tools(self) -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = {t.name for t in tools}
            assert names == {"notes_list", "notes_create", "notes_search"}

    @pytest.mark.asyncio
    async def test_create_note(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool("notes_create", {"title": "Test", "content": "Body"})
            assert result.data["status"] == "created"
            assert result.data["note_id"] != ""

    @pytest.mark.asyncio
    async def test_create_note_with_tags(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "notes_create", {"title": "Tagged", "content": "X", "tags": "a,b"}
            )
            assert result.data["status"] == "created"

    @pytest.mark.asyncio
    async def test_create_then_list(self) -> None:
        async with Client(mcp) as client:
            await client.call_tool("notes_create", {"title": "Listed", "content": "Body"})
            result = await client.call_tool("notes_list", {})
            assert result.data["count"] == 1
            assert result.data["notes"][0]["title"] == "Listed"

    @pytest.mark.asyncio
    async def test_list_with_tag_filter(self) -> None:
        async with Client(mcp) as client:
            await client.call_tool("notes_create", {"title": "A", "content": "X", "tags": "work"})
            await client.call_tool("notes_create", {"title": "B", "content": "Y", "tags": "home"})
            result = await client.call_tool("notes_list", {"tag": "work"})
            assert result.data["count"] == 1

    @pytest.mark.asyncio
    async def test_search(self) -> None:
        async with Client(mcp) as client:
            await client.call_tool(
                "notes_create", {"title": "Python Guide", "content": "Learn async"}
            )
            await client.call_tool("notes_create", {"title": "Groceries", "content": "Milk eggs"})
            result = await client.call_tool("notes_search", {"query": "Python"})
            assert result.data["count"] == 1
            assert result.data["results"][0]["title"] == "Python Guide"

    @pytest.mark.asyncio
    async def test_search_no_results(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool("notes_search", {"query": "nonexistent"})
            assert result.data["count"] == 0

    @pytest.mark.asyncio
    async def test_create_missing_title_returns_error(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "notes_create",
                {"title": "", "content": "Body"},
                raise_on_error=False,
            )
            assert result.is_error is True

    @pytest.mark.asyncio
    async def test_create_missing_content_returns_error(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "notes_create",
                {"title": "Title", "content": ""},
                raise_on_error=False,
            )
            assert result.is_error is True

    @pytest.mark.asyncio
    async def test_search_missing_query_returns_error(self) -> None:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "notes_search",
                {"query": ""},
                raise_on_error=False,
            )
            assert result.is_error is True

    @pytest.mark.asyncio
    async def test_multiple_creates_then_list(self) -> None:
        async with Client(mcp) as client:
            for i in range(5):
                await client.call_tool(
                    "notes_create", {"title": f"Note {i}", "content": f"Content {i}"}
                )
            result = await client.call_tool("notes_list", {"max_results": 3})
            assert result.data["count"] == 3

    @pytest.mark.asyncio
    async def test_search_in_content(self) -> None:
        async with Client(mcp) as client:
            await client.call_tool(
                "notes_create", {"title": "Memo", "content": "Remember dentist appointment"}
            )
            result = await client.call_tool("notes_search", {"query": "dentist"})
            assert result.data["count"] == 1


# =========================================================================
# Section 4: Contract YAML parsing
# =========================================================================


class TestNotesContracts:
    """Parse and validate notes contract YAML files."""

    @pytest.fixture()
    def validator(self) -> ContractValidator:
        return ContractValidator()

    def test_list_contract_parses(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "notes_list.yaml", validator=validator)
        assert isinstance(contract, CapabilityContract)
        assert contract.name == "tool.read.notes_list"
        assert contract.version == "1.0.0"

    def test_list_contract_green_band(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "notes_list.yaml", validator=validator)
        assert contract.safety_band_min == "GREEN"

    def test_list_contract_provider(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "notes_list.yaml", validator=validator)
        assert contract.provider_type == "MCP"
        assert contract.provider_id == "notes_mcp_stdio"

    def test_create_contract_parses(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "notes_create.yaml", validator=validator)
        assert contract.name == "tool.write.notes_create"
        assert contract.safety_band_min == "AMBER"

    def test_create_contract_required_inputs(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "notes_create.yaml", validator=validator)
        required = [inp.name for inp in contract.required_inputs]
        assert "title" in required
        assert "content" in required

    def test_search_contract_parses(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "notes_search.yaml", validator=validator)
        assert contract.name == "tool.read.notes_search"
        assert contract.safety_band_min == "GREEN"

    def test_search_contract_required_inputs(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "notes_search.yaml", validator=validator)
        required = [inp.name for inp in contract.required_inputs]
        assert "query" in required

    def test_all_notes_share_provider_id(self, validator: ContractValidator) -> None:
        ids = set()
        for name in ["notes_list.yaml", "notes_create.yaml", "notes_search.yaml"]:
            c = parse_contract(CONTRACTS_DIR / name, validator=validator)
            ids.add(c.provider_id)
        assert ids == {"notes_mcp_stdio"}

    def test_all_notes_share_domain(self, validator: ContractValidator) -> None:
        for name in ["notes_list.yaml", "notes_create.yaml", "notes_search.yaml"]:
            c = parse_contract(CONTRACTS_DIR / name, validator=validator)
            assert "NOTES" in c.domain

    def test_list_output_schema(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "notes_list.yaml", validator=validator)
        props = contract.output.get("properties", {})
        assert "notes" in props
        assert "count" in props

    def test_create_output_schema(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "notes_create.yaml", validator=validator)
        props = contract.output.get("properties", {})
        assert "note_id" in props
        assert "status" in props

    def test_search_output_schema(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "notes_search.yaml", validator=validator)
        props = contract.output.get("properties", {})
        assert "results" in props
        assert "count" in props
