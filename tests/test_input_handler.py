"""Test per il modulo input_handler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from computer_graphics.input_handler import InputHandler


class TestInputHandlerFromString:
    def test_valid_description(self) -> None:
        handler = InputHandler.from_string("una stanza con tavolo e sedia")
        result = handler.get_description()
        assert result == "una stanza con tavolo e sedia"

    def test_normalises_extra_spaces(self) -> None:
        handler = InputHandler.from_string("  una  stanza   con   tavolo  ")
        result = handler.get_description()
        assert result == "una stanza con tavolo"

    def test_raises_on_too_short(self) -> None:
        with pytest.raises(ValueError, match="breve"):
            InputHandler.from_string("ciao").get_description()

    def test_raises_on_too_long(self) -> None:
        with pytest.raises(ValueError, match="lunga"):
            InputHandler.from_string("a" * 2001).get_description()

    def test_exactly_min_length(self) -> None:
        text = "a" * 10
        handler = InputHandler.from_string(text)
        assert len(handler.get_description()) == 10

    def test_exactly_max_length(self) -> None:
        text = "a" * 2000
        handler = InputHandler.from_string(text)
        assert len(handler.get_description()) == 2000


class TestInputHandlerFromFile:
    def test_reads_file_correctly(self, tmp_path: Path) -> None:
        test_file = tmp_path / "scene.txt"
        test_file.write_text("una stanza con tavolo e sedia", encoding="utf-8")
        handler = InputHandler.from_file(test_file)
        assert handler.get_description() == "una stanza con tavolo e sedia"

    def test_strips_whitespace_from_file(self, tmp_path: Path) -> None:
        test_file = tmp_path / "scene.txt"
        test_file.write_text("  una stanza con tavolo  \n\n", encoding="utf-8")
        handler = InputHandler.from_file(test_file)
        assert handler.get_description() == "una stanza con tavolo"

    def test_raises_on_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            InputHandler.from_file("/percorso/inesistente/scene.txt")

    def test_raises_on_empty_file(self, tmp_path: Path) -> None:
        test_file = tmp_path / "empty.txt"
        test_file.write_text("   ", encoding="utf-8")
        with pytest.raises(ValueError):
            InputHandler.from_file(test_file).get_description()


class TestInputHandlerInteractive:
    def test_interactive_mode(self) -> None:
        handler = InputHandler()
        with patch(
            "computer_graphics.input_handler.Prompt.ask",
            return_value="una stanza con tavolo e sedia",
        ):
            result = handler.get_description()
        assert result == "una stanza con tavolo e sedia"

    def test_interactive_raises_on_short_input(self) -> None:
        handler = InputHandler()
        with (
            patch(
                "computer_graphics.input_handler.Prompt.ask",
                return_value="corto",
            ),
            pytest.raises(ValueError, match="breve"),
        ):
            handler.get_description()
