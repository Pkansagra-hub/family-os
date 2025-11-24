"""Edge case tests for k0.policy.redaction module.

This test suite targets the missing coverage areas identified in Phase 5:
- Import error handling for geohash2
- Edge cases in path normalization and masking
- Error handling in directives_from_obligations
- Comprehensive testing of mask_location_for_band function
"""

from __future__ import annotations

import pytest

from k0.policy.redaction import (
    RedactionDirective,
    RedactionError,
    _clone_value,
    _coerce_details_map,
    _ensure_mapping,
    _mask_path,
    _normalise_path,
    apply_redactions,
    directives_from_obligations,
    mask_location_for_band,
)


class TestPathNormalizationEdgeCases:
    """Test edge cases in _normalise_path function."""

    def test_normalise_path_none_input(self):
        """Test _normalise_path with None input."""
        result = _normalise_path(None)
        assert result == ()

    def test_normalise_path_empty_string(self):
        """Test _normalise_path with empty string."""
        result = _normalise_path("")
        assert result == ()

    def test_normalise_path_whitespace_only(self):
        """Test _normalise_path with whitespace-only segments."""
        result = _normalise_path("  .  .  ")
        assert result == ()

    def test_normalise_path_mixed_empty_segments(self):
        """Test _normalise_path with mixed empty and valid segments."""
        result = _normalise_path("field..nested.")
        assert result == ("field", "nested")

    def test_normalise_path_sequence_with_empty_parts(self):
        """Test _normalise_path with sequence containing empty parts."""
        result = _normalise_path(["", "field", "", "nested", ""])
        assert result == ("field", "nested")


class TestCloneValueEdgeCases:
    """Test edge cases in _clone_value function."""

    def test_clone_value_sequence_types(self):
        """Test _clone_value with different sequence types."""
        # Test list
        original_list = [1, 2, {"nested": "value"}]
        cloned_list = _clone_value(original_list)
        assert cloned_list == original_list
        assert cloned_list is not original_list
        assert cloned_list[2] is not original_list[2]  # nested dict should be cloned

        # Test tuple (treated as sequence)
        original_tuple = (1, 2, {"nested": "value"})
        cloned_tuple = _clone_value(original_tuple)
        assert cloned_tuple == list(original_tuple)  # converted to list
        assert isinstance(cloned_tuple, list)


class TestMaskPathEdgeCases:
    """Test edge cases in _mask_path function."""

    def test_mask_path_empty_path(self):
        """Test _mask_path with empty path."""
        root = {"field": "value"}
        result = _mask_path(root, (), "mask")
        assert result is False
        assert root == {"field": "value"}  # unchanged

    def test_mask_path_invalid_list_index_non_numeric(self):
        """Test _mask_path with non-numeric list index."""
        root = {"list": [1, 2, 3]}
        result = _mask_path(root, ("list", "invalid"), "mask")
        assert result is False

    def test_mask_path_list_index_out_of_bounds_negative(self):
        """Test _mask_path with negative list index out of bounds."""
        root = {"list": [1, 2, 3]}
        result = _mask_path(root, ("list", "-5"), "mask")
        assert result is False

    def test_mask_path_list_index_out_of_bounds_positive(self):
        """Test _mask_path with positive list index out of bounds."""
        root = {"list": [1, 2, 3]}
        result = _mask_path(root, ("list", "5"), "mask")
        assert result is False

    def test_mask_path_nested_structure_modification(self):
        """Test _mask_path with nested structure that needs cloning."""
        root = {"items": [{"data": {"secret": "value"}}]}
        result = _mask_path(root, ("items", "0", "data", "secret"), "MASKED")
        assert result is True
        assert root["items"][0]["data"]["secret"] == "MASKED"
        # Ensure the nested dict was properly cloned/modified
        assert isinstance(root["items"][0], dict)
        assert isinstance(root["items"][0]["data"], dict)

    def test_mask_path_deeply_nested_list_modification(self):
        """Test _mask_path with deeply nested list structures requiring cloning."""
        root = {"data": [{"items": [{"secret": "value"}]}]}
        result = _mask_path(root, ("data", "0", "items", "0", "secret"), "MASKED")
        assert result is True
        assert root["data"][0]["items"][0]["secret"] == "MASKED"
        # Ensure nested structures are properly cloned
        assert isinstance(root["data"], list)
        assert isinstance(root["data"][0]["items"], list)

    def test_mask_path_mixed_list_dict_navigation(self):
        """Test _mask_path navigating through mixed list and dict structures."""
        root = {
            "users": [
                {"profile": {"personal": {"ssn": "123-45-6789"}}},
                {"profile": {"personal": {"ssn": "987-65-4321"}}},
            ]
        }
        result = _mask_path(root, ("users", "1", "profile", "personal", "ssn"), "XXX-XX-XXXX")
        assert result is True
        assert root["users"][1]["profile"]["personal"]["ssn"] == "XXX-XX-XXXX"
        # Ensure first user is unchanged
        assert root["users"][0]["profile"]["personal"]["ssn"] == "123-45-6789"


class TestEnsureMappingEdgeCases:
    """Test edge cases in _ensure_mapping function."""

    def test_ensure_mapping_already_dict(self):
        """Test _ensure_mapping with dict input."""
        original = {"key": "value"}
        result = _ensure_mapping(original)
        assert result is original
        assert result == {"key": "value"}

    def test_ensure_mapping_other_mapping(self):
        """Test _ensure_mapping with other mapping type."""
        from collections import OrderedDict

        original = OrderedDict([("key", "value")])
        result = _ensure_mapping(original)
        assert result == {"key": "value"}
        assert isinstance(result, dict)


class TestApplyRedactionsEdgeCases:
    """Test edge cases in apply_redactions function."""

    def test_apply_redactions_empty_directives(self):
        """Test apply_redactions with empty directives list."""
        body = {"field": "value"}
        result = apply_redactions(body, [])
        assert result == body
        assert result is not body  # should be cloned

    def test_apply_redactions_directive_with_empty_field_path(self):
        """Test apply_redactions with directive that produces empty field path."""
        body = {"field": "value"}
        directives = [RedactionDirective(obligation="test", fields="", target=None)]  # empty string
        with pytest.raises(RedactionError, match="produced empty field path"):
            apply_redactions(body, directives)

    def test_apply_redactions_directive_with_empty_target_and_field(self):
        """Test apply_redactions with both empty target and field."""
        body = {"field": "value"}
        directives = [
            RedactionDirective(obligation="test", fields=[""], target="")  # empty field in list
        ]
        with pytest.raises(RedactionError, match="produced empty field path"):
            apply_redactions(body, directives)


class TestDirectivesFromObligationsEdgeCases:
    """Test edge cases in directives_from_obligations function."""

    def test_directives_from_obligations_invalid_target_type(self):
        """Test directives_from_obligations with invalid target type."""
        obligations = [
            {
                "name": "kernel.redact.field",
                "details": {
                    "fields": ["field"],
                    "target": 123,  # invalid: should be str or sequence
                },
            }
        ]
        with pytest.raises(RedactionError, match="'target' must be string or sequence"):
            directives_from_obligations(obligations)

    def test_directives_from_obligations_empty_fields_sequence(self):
        """Test directives_from_obligations with empty fields sequence."""
        obligations = [
            {
                "name": "kernel.redact.field",
                "details": {"fields": [], "target": "body"},  # empty sequence
            }
        ]
        directives = directives_from_obligations(obligations)
        # Should create directive with empty fields list
        assert len(directives) == 1
        assert directives[0].fields == []

    def test_directives_from_obligations_invalid_fields_type(self):
        """Test directives_from_obligations with invalid fields type."""
        obligations = [
            {
                "name": "kernel.redact.field",
                "details": {"fields": 123, "target": "body"},  # invalid: not str or sequence
            }
        ]
        with pytest.raises(RedactionError, match="missing 'fields' sequence or string"):
            directives_from_obligations(obligations)

    def test_directives_from_obligations_invalid_fields_type_dict(self):
        """Test directives_from_obligations with dict as fields."""
        obligations = [
            {
                "name": "kernel.redact.field",
                "details": {
                    "fields": {"invalid": "dict"},  # invalid: dict not allowed
                    "target": "body",
                },
            }
        ]
        with pytest.raises(RedactionError, match="missing 'fields' sequence or string"):
            directives_from_obligations(obligations)

    def test_directives_from_obligations_non_redact_obligation(self):
        """Test directives_from_obligations with non-redact obligation."""
        obligations = [
            {
                "name": "kernel.other.action",  # not kernel.redact.field
                "details": {"fields": ["field"]},
            }
        ]
        directives = directives_from_obligations(obligations)
        assert directives == []  # should be ignored

    def test_directives_from_obligations_invalid_obligation_structure(self):
        """Test directives_from_obligations with invalid obligation structures."""
        # Test with None name
        obligations = [
            {"name": None, "details": {"fields": ["field"]}},
            {"name": "", "details": {"fields": ["field"]}},  # empty name
            {"details": {"fields": ["field"]}},  # missing name
        ]
        directives = directives_from_obligations(obligations)
        assert directives == []  # all should be ignored

    def test_directives_from_obligations_mixed_valid_invalid(self):
        """Test directives_from_obligations with mix of valid and invalid obligations."""
        obligations = [
            {"name": "kernel.redact.field", "details": {"fields": ["field1"]}},
            {"name": "kernel.other.action", "details": {"fields": ["field2"]}},  # ignored
            {"name": "kernel.redact.field", "details": {"fields": ["field3"]}},
        ]
        directives = directives_from_obligations(obligations)
        assert len(directives) == 2
        assert directives[0].fields == ["field1"]
        assert directives[1].fields == ["field3"]


class TestCoerceDetailsMapEdgeCases:
    """Test edge cases in _coerce_details_map function."""

    def test_coerce_details_map_none(self):
        """Test _coerce_details_map with None input."""
        result = _coerce_details_map(None)
        assert result == {}

    def test_coerce_details_map_valid_mapping(self):
        """Test _coerce_details_map with valid mapping."""
        input_data = {"key": "value", 123: "number_key"}
        result = _coerce_details_map(input_data)
        assert result == {"key": "value", "123": "number_key"}

    def test_coerce_details_map_invalid_type(self):
        """Test _coerce_details_map with invalid type."""
        with pytest.raises(RedactionError, match="Obligation details must be a mapping"):
            _coerce_details_map("invalid_string")

        with pytest.raises(RedactionError, match="Obligation details must be a mapping"):
            _coerce_details_map(123)

        with pytest.raises(RedactionError, match="Obligation details must be a mapping"):
            _coerce_details_map(["list"])


class TestMaskLocationForBandEdgeCases:
    """Test edge cases in mask_location_for_band function."""

    def test_mask_location_missing_geohash2(self):
        """Test mask_location_for_band when geohash2 is not available."""
        # Temporarily mock the geohash2 import as None
        import k0.policy.redaction

        original_geohash2 = k0.policy.redaction.geohash2
        k0.policy.redaction.geohash2 = None

        try:
            body = {"location_lat": 37.7749, "location_lon": -122.4194}
            with pytest.raises(RedactionError, match="geohash2 library not installed"):
                mask_location_for_band(body, "GREEN")
        finally:
            k0.policy.redaction.geohash2 = original_geohash2

    def test_mask_location_no_location_fields(self):
        """Test mask_location_for_band when no location fields are present."""
        body = {"other_field": "value"}
        result = mask_location_for_band(body, "AMBER")
        assert result == body  # unchanged

    def test_mask_location_partial_coordinates_lat_only(self):
        """Test mask_location_for_band with only latitude provided."""
        body = {"location_lat": 37.7749}
        with pytest.raises(RedactionError, match="Partial location data.*both.*must be present"):
            mask_location_for_band(body, "AMBER")

    def test_mask_location_partial_coordinates_lon_only(self):
        """Test mask_location_for_band with only longitude provided."""
        body = {"location_lon": -122.4194}
        with pytest.raises(RedactionError, match="Partial location data.*both.*must be present"):
            mask_location_for_band(body, "AMBER")

    def test_mask_location_invalid_latitude_range_high(self):
        """Test mask_location_for_band with latitude out of range (too high)."""
        body = {"location_lat": 91.0, "location_lon": -122.4194}
        with pytest.raises(RedactionError, match="Invalid latitude 91.0.*must be in range"):
            mask_location_for_band(body, "GREEN")

    def test_mask_location_invalid_latitude_range_low(self):
        """Test mask_location_for_band with latitude out of range (too low)."""
        body = {"location_lat": -91.0, "location_lon": -122.4194}
        with pytest.raises(RedactionError, match="Invalid latitude -91.0.*must be in range"):
            mask_location_for_band(body, "GREEN")

    def test_mask_location_invalid_longitude_range_high(self):
        """Test mask_location_for_band with longitude out of range (too high)."""
        body = {"location_lat": 37.7749, "location_lon": 181.0}
        with pytest.raises(RedactionError, match="Invalid longitude 181.0.*must be in range"):
            mask_location_for_band(body, "GREEN")

    def test_mask_location_invalid_longitude_range_low(self):
        """Test mask_location_for_band with longitude out of range (too low)."""
        body = {"location_lat": 37.7749, "location_lon": -181.0}
        with pytest.raises(RedactionError, match="Invalid longitude -181.0.*must be in range"):
            mask_location_for_band(body, "GREEN")

    def test_mask_location_invalid_coordinate_types(self):
        """Test mask_location_for_band with invalid coordinate types."""
        # String coordinates
        body = {"location_lat": "37.7749", "location_lon": "-122.4194"}
        result = mask_location_for_band(body, "GREEN")
        assert "location_geohash" in result
        assert result["location_precision_m"] == 1

        # Invalid string
        body = {"location_lat": "invalid", "location_lon": -122.4194}
        with pytest.raises(RedactionError, match="Invalid location coordinates"):
            mask_location_for_band(body, "GREEN")

    def test_mask_location_green_band(self):
        """Test mask_location_for_band with GREEN band (no masking)."""
        body = {"location_lat": 37.7749, "location_lon": -122.4194, "other": "data"}
        result = mask_location_for_band(body, "green")  # lowercase should work

        assert result["location_lat"] == 37.7749  # preserved
        assert result["location_lon"] == -122.4194  # preserved
        assert "location_geohash" in result
        assert result["location_precision_m"] == 1
        assert result["other"] == "data"  # other fields preserved

    def test_mask_location_amber_band(self):
        """Test mask_location_for_band with AMBER band."""
        body = {"location_lat": 37.7749, "location_lon": -122.4194, "other": "data"}
        result = mask_location_for_band(body, "AMBER")

        assert result["location_lat"] is None  # cleared
        assert result["location_lon"] is None  # cleared
        assert "location_geohash" in result
        assert result["location_precision_m"] == 5000
        assert result["other"] == "data"  # other fields preserved

    def test_mask_location_red_band(self):
        """Test mask_location_for_band with RED band."""
        body = {"location_lat": 37.7749, "location_lon": -122.4194, "other": "data"}
        result = mask_location_for_band(body, "RED")

        assert result["location_lat"] is None  # cleared
        assert result["location_lon"] is None  # cleared
        assert "location_geohash" in result
        assert result["location_precision_m"] == 25000
        assert result["other"] == "data"  # other fields preserved

    def test_mask_location_unknown_band_defaults_to_red(self):
        """Test mask_location_for_band with unknown band (defaults to RED)."""
        body = {"location_lat": 37.7749, "location_lon": -122.4194}
        result = mask_location_for_band(body, "UNKNOWN")

        assert result["location_lat"] is None  # cleared like RED
        assert result["location_lon"] is None  # cleared like RED
        assert result["location_precision_m"] == 25000  # RED precision

    def test_mask_location_custom_field_names(self):
        """Test mask_location_for_band with custom field names."""
        body = {"lat": 37.7749, "lon": -122.4194}
        result = mask_location_for_band(body, "AMBER", lat_field="lat", lon_field="lon")

        assert result["lat"] is None
        assert result["lon"] is None
        assert "location_geohash" in result
        assert result["location_precision_m"] == 5000

    def test_mask_location_none_coordinates(self):
        """Test mask_location_for_band with explicit None coordinates."""
        body = {"location_lat": None, "location_lon": None}
        result = mask_location_for_band(body, "AMBER")
        assert result == body  # unchanged</content>
