"""Tests for ``ManifestGenerator`` helpers (§E15.0.8)."""

from __future__ import annotations

from k1.tools.family.manifest import llm_tool_specs, openapi_paths, ui_manifest
from tests.k1.tools.family._stubs import DemoToolService


def test_ui_manifest_unfiltered_includes_all_actions() -> None:
    m = ui_manifest(DemoToolService.DEFINITION)
    assert m["adapter_id"] == "demo"
    names = [a["name"] for a in m["actions"]]
    assert set(names) == {"echo", "record_write", "boom", "bad_return", "adults_only"}


def test_ui_manifest_role_filter_hides_disallowed() -> None:
    m = ui_manifest(DemoToolService.DEFINITION, role="child")
    names = [a["name"] for a in m["actions"]]
    # child is in echo.allowed_roles but not in record_write, boom, bad_return, adults_only.
    assert "echo" in names
    assert "record_write" not in names


def test_ui_manifest_min_role_filter() -> None:
    # record_write has min_role=parent; guardian (3) < parent (4), so excluded.
    m = ui_manifest(DemoToolService.DEFINITION, role="guardian")
    names = [a["name"] for a in m["actions"]]
    assert "record_write" not in names


def test_llm_tool_specs_emit_both_names() -> None:
    specs = llm_tool_specs(DemoToolService.DEFINITION)
    by_name = {s["name"]: s for s in specs}
    assert "demo.echo" in by_name
    assert by_name["demo.echo"]["capability_name"] == "tool.execute.demo.echo"
    assert by_name["demo.adults_only"]["capability_name"] == "tool.read.demo.adults_only"


def test_llm_tool_specs_parameters_schema_has_required() -> None:
    specs = llm_tool_specs(DemoToolService.DEFINITION)
    echo = next(s for s in specs if s["name"] == "demo.echo")
    assert echo["parameters"]["properties"]["message"]["type"] == "string"
    assert echo["parameters"]["required"] == ["message"]


def test_openapi_paths_emits_get_for_read_post_for_write() -> None:
    paths = openapi_paths(DemoToolService.DEFINITION)
    assert "/k1/tools/demo/manifest" in paths
    assert "/k1/tools/demo/llm_specs" in paths
    assert "get" in paths["/k1/tools/demo/adults_only"]
    assert "post" in paths["/k1/tools/demo/record_write"]
