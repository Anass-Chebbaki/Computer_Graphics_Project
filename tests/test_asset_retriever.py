"""Test per il modulo asset_retriever."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from computer_graphics.asset_retriever import (
    AssetIndex,
    _cosine_similarity,
    _term_freq,
    _tokenize,
)


def test_tokenize() -> None:
    assert _tokenize("Wooden Table") == ["wooden", "table"]
    assert _tokenize("modern_desk-large") == ["modern", "desk", "large"]
    assert _tokenize("  chair  ") == ["chair"]
    assert _tokenize("") == []


def test_term_freq() -> None:
    tokens = ["a", "b", "a"]
    tf = _term_freq(tokens)
    assert tf == {"a": 2 / 3, "b": 1 / 3}
    assert _term_freq([]) == {}


def test_cosine_similarity() -> None:
    vec_a = {"wooden": 0.5, "table": 0.5}
    vec_b = {"wooden": 0.5, "table": 0.5}
    assert _cosine_similarity(vec_a, vec_b) == pytest.approx(1.0)

    vec_c = {"chair": 1.0}
    assert _cosine_similarity(vec_a, vec_c) == 0.0

    vec_d = {"wooden": 1.0}
    # dot = 0.5 * 1.0 = 0.5
    # norm_a = sqrt(0.25 + 0.25) = sqrt(0.5) = 0.707
    # norm_b = sqrt(1.0) = 1.0
    # sim = 0.5 / 0.707 = 0.707
    assert _cosine_similarity(vec_a, vec_d) == pytest.approx(0.707, abs=1e-3)


class TestAssetIndex:
    def test_build_index_and_match(self, tmp_path: Path) -> None:
        # Crea finti file asset
        (tmp_path / "wooden_table.obj").touch()
        (tmp_path / "modern_chair.fbx").touch()
        (tmp_path / "lamp.glb").touch()

        index = AssetIndex(tmp_path)

        # Match esatto
        assert index.find_best_match("wooden_table") == tmp_path / "wooden_table.obj"

        # Match parziale/semantico
        # "table" -> match con "wooden_table" (score elevato)
        match = index.find_best_match("table")
        assert match is not None
        assert match.name == "wooden_table.obj"

        # "modern" -> "modern_chair"
        match = index.find_best_match("modern")
        assert match is not None
        assert match.name == "modern_chair.fbx"

    def test_find_best_match_no_results(self, tmp_path: Path) -> None:
        index = AssetIndex(tmp_path)
        assert index.find_best_match("anything") is None

    def test_find_best_match_below_threshold(self, tmp_path: Path) -> None:
        (tmp_path / "table.obj").touch()
        index = AssetIndex(tmp_path)
        # "chair" non ha token in comune con "table"
        assert index.find_best_match("chair", threshold=0.1) is None

    def test_find_best_match_path_for_name(self, tmp_path: Path) -> None:
        (tmp_path / "desk.obj").touch()
        index = AssetIndex(tmp_path)

        # Esatto
        assert (
            index.find_best_match_path_for_name("desk", tmp_path)
            == tmp_path / "desk.obj"
        )

        # Semantico fallback
        (tmp_path / "large_desk.glb").touch()
        # Ri-indicizzazione necessaria se vogliamo che large_desk sia nell'indice
        index = AssetIndex(tmp_path)
        assert (
            index.find_best_match_path_for_name("large", tmp_path)
            == tmp_path / "large_desk.glb"
        )

    def test_export_metadata(self, tmp_path: Path) -> None:
        (tmp_path / "table.obj").touch()
        index = AssetIndex(tmp_path)
        output = tmp_path / "metadata.json"
        index.export_metadata(output)

        assert output.exists()
        with output.open(encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["name"] == "table"
