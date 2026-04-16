"""Test per il modulo json_parser."""

from __future__ import annotations

import pytest

from computer_graphics.json_parser import JSONParseError, extract_json


class TestExtractJson:
    def test_clean_json_array(self, sample_clean_json: str) -> None:
        result = extract_json(sample_clean_json)
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0]["name"] == "table"

    def test_dirty_text_with_backticks(self, sample_dirty_text: str) -> None:
        result = extract_json(sample_dirty_text)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_text_before_and_after_json(self) -> None:
        text = 'Ecco il JSON: [{"name": "table", "x": 0, "y": 0, "z": 0}] Fine.'
        result = extract_json(text)
        assert result[0]["name"] == "table"

    def test_raises_on_empty_string(self) -> None:
        with pytest.raises(JSONParseError, match="vuota"):
            extract_json("")

    def test_raises_when_no_array_found(self) -> None:
        with pytest.raises(JSONParseError):
            extract_json("Questa è solo una frase senza JSON.")

    def test_multiline_json(self) -> None:
        text = """
        [
            {
                "name": "desk",
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "rot_x": 0.0,
                "rot_y": 0.0,
                "rot_z": 0.0
            }
        ]
        """
        result = extract_json(text)
        assert result[0]["name"] == "desk"

    def test_numeric_values_preserved(self) -> None:
        text = '[{"name": "chair", "x": 1.5, "y": -0.8, "z": 0.0, "rot_x": 0.0, "rot_y": 0.0, "rot_z": 0.785}]'  # noqa: E501
        result = extract_json(text)
        assert result[0]["x"] == pytest.approx(1.5)
        assert result[0]["rot_z"] == pytest.approx(0.785)
