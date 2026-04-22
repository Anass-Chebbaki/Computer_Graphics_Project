"""Test per il modulo preview."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from computer_graphics.preview import generate_2d_preview
from computer_graphics.validator import SceneObject


@pytest.fixture
def mock_objects() -> list[SceneObject]:
    """Lista di oggetti mock per i test."""
    return [
        SceneObject(name="table", x=0.0, y=0.0, z=0.0, scale=1.0),
        SceneObject(name="chair", x=2.0, y=0.0, z=0.0, scale=0.5, parent="table"),
        SceneObject(name="lamp", x=-2.0, y=1.0, z=0.0, scale=0.3, light_type="POINT"),
    ]


def test_generate_2d_preview_success(
    mock_objects: list[SceneObject],
    tmp_path: Path,
) -> None:
    """Test generazione preview con successo."""
    output_file = tmp_path / "preview.png"

    # Mockiamo matplotlib per evitare di caricarlo davvero e per velocità
    with (
        patch("matplotlib.pyplot.subplots", return_value=(MagicMock(), MagicMock())),
        patch("matplotlib.pyplot.savefig"),
        patch("matplotlib.pyplot.close"),
    ):
        result = generate_2d_preview(mock_objects, output_file)
        assert result == output_file
        assert isinstance(result, Path)


def test_generate_2d_preview_no_matplotlib(
    mock_objects: list[SceneObject],
    tmp_path: Path,
) -> None:
    """Test comportamento quando matplotlib non è installato."""
    output_file = tmp_path / "preview.png"

    with patch("builtins.__import__", side_effect=ImportError("matplotlib not found")):
        result = generate_2d_preview(mock_objects, output_file)
        # Se fallisce l'import, dovrebbe restituire il path ma non fare nulla
        assert result == output_file


def test_generate_2d_preview_empty_list(tmp_path: Path) -> None:
    """Test con lista oggetti vuota."""
    output_file = tmp_path / "preview_empty.png"

    with (
        patch("matplotlib.pyplot.subplots", return_value=(MagicMock(), MagicMock())),
        patch("matplotlib.pyplot.savefig"),
        patch("matplotlib.pyplot.close"),
    ):
        result = generate_2d_preview([], output_file)
        assert result == output_file


def test_generate_2d_preview_save_error(
    mock_objects: list[SceneObject],
    tmp_path: Path,
) -> None:
    """Test errore durante salvataggio."""
    output_file = tmp_path / "invalid_dir" / "preview.png"

    # Non mockiamo savefig per far scattare un errore reale di scrittura
    # Ma matplotlib creerebbe la dir se usiamo plt.savefig...
    # Proviamo a mockare savefig per lanciare eccezione
    with (
        patch("matplotlib.pyplot.subplots", return_value=(MagicMock(), MagicMock())),
        patch("matplotlib.pyplot.savefig", side_effect=RuntimeError("Save failed")),
        patch("matplotlib.pyplot.close"),
        pytest.raises(RuntimeError, match="Save failed"),
    ):
        generate_2d_preview(mock_objects, output_file)
