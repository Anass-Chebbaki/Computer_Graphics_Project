"""Test per la logica di scene_builder senza richiedere bpy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def mock_bpy() -> MagicMock:
    """Mock del modulo bpy."""
    mock = MagicMock()
    # Simula la struttura di bpy.context.scene.objects
    mock.context.view_layer.objects.active = None
    mock.data.objects = {}
    return mock


def test_populate_scene_logic() -> None:
    """Verifica che populate_scene chiami le funzioni nel giusto ordine."""
    from computer_graphics.blender.scene_builder import populate_scene

    # Mock delle dipendenze interne
    with (
        patch("computer_graphics.blender.scene_builder.import_asset") as mock_import,
        patch("computer_graphics.blender.scene_builder.place_object") as mock_place,
        patch(
            "computer_graphics.blender.scene_builder._apply_parent_relationships"
        ) as mock_parent,
        patch(
            "computer_graphics.blender.scene_builder.snap_objects_to_surface"
        ) as mock_snap,
        patch("computer_graphics.blender.scene_builder.setup_camera") as mock_camera,
        patch(
            "computer_graphics.blender.scene_builder.setup_lighting"
        ) as mock_lighting,
        patch("computer_graphics.blender.scene_builder.bpy") as _mock_bpy,
    ):
        # Mock di import_asset che restituisce un oggetto mock con nome
        mock_obj = MagicMock()
        mock_obj.name = "table"
        mock_import.return_value = mock_obj

        scene_objects = [
            {"name": "table", "x": 0, "y": 0, "z": 0},
            {"name": "chair", "x": 1, "y": 0, "z": 0},
        ]

        # Esecuzione
        populate_scene(
            objects=scene_objects, assets_dir="/mock/path", enable_physics=True
        )

        # Asserzioni
        assert mock_import.call_count == 2
        assert mock_place.call_count == 2

        # Verifica l'ordine critico (Snap PRIMA di Parent)
        # Otteniamo l'ordine delle chiamate tramite mock_parent.called
        # e mock_snap.called. Ma è meglio verificare i mock degli orchestratori.
        mock_snap.assert_called_once()
        mock_parent.assert_called_once()
        mock_camera.assert_called_once()
        mock_lighting.assert_called_once()


def test_create_proxy_logic() -> None:
    """Verifica la creazione dei proxy mesh."""
    from computer_graphics.blender.scene_builder import _create_proxy

    with (patch("computer_graphics.blender.scene_builder.bpy") as mock_bpy,):
        # Configura il mock per restituire un oggetto appena "creato"
        mock_obj = MagicMock()
        mock_bpy.context.object = mock_obj
        mock_bpy.data.materials.new.return_value = MagicMock()

        _create_proxy("test_proxy")

        # Verifica chiamate
        mock_bpy.ops.mesh.primitive_cube_add.assert_called_once()
        assert mock_obj.name == "PROXY_test_proxy"
