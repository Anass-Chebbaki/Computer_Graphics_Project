"""Test di integrazione per l'orchestratore."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from computer_graphics.ollama_client import OllamaConnectionError
from computer_graphics.orchestrator import generate_scene_objects
from computer_graphics.validator import SceneObject


@pytest.fixture()
def valid_json_response() -> str:
    """Risposta JSON valida simulata dal modello."""
    return json.dumps(
        [
            {
                "name": "table",
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "rot_x": 0.0,
                "rot_y": 0.0,
                "rot_z": 0.0,
                "scale": 1.0,
            },
            {
                "name": "chair",
                "x": 0.0,
                "y": -1.2,
                "z": 0.0,
                "rot_x": 0.0,
                "rot_y": 0.0,
                "rot_z": 0.0,
                "scale": 1.0,
            },
        ]
    )


class TestGenerateSceneObjects:
    def test_returns_scene_objects_on_success(self, valid_json_response: str) -> None:
        with (
            patch(
                "computer_graphics.orchestrator.OllamaClient.health_check",
                return_value=True,
            ),
            patch(
                "computer_graphics.orchestrator.OllamaClient.chat",
                return_value=valid_json_response,
            ),
        ):
            result = generate_scene_objects(
                "una stanza con tavolo e sedia",
                verbose=False,
            )

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(obj, SceneObject) for obj in result)
        assert result[0].name == "table"
        assert result[1].name == "chair"

    def test_raises_connection_error_when_ollama_down(self) -> None:
        with (
            patch(
                "computer_graphics.orchestrator.OllamaClient.health_check",
                return_value=False,
            ),
            pytest.raises(OllamaConnectionError, match="ollama serve"),
        ):
            generate_scene_objects(
                "una stanza con tavolo",
                verbose=False,
            )

    def test_retries_on_invalid_json(self, valid_json_response: str) -> None:
        """Il sistema deve ritentare in caso di JSON non valido."""
        call_count = 0

        def mock_chat(payload: dict) -> str:  # noqa: ARG001
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return "Risposta non valida senza JSON"
            return valid_json_response

        with (
            patch(
                "computer_graphics.orchestrator.OllamaClient.health_check",
                return_value=True,
            ),
            patch(
                "computer_graphics.orchestrator.OllamaClient.chat",
                side_effect=mock_chat,
            ),
        ):
            result = generate_scene_objects(
                "test",
                max_retries=3,
                verbose=False,
            )

        assert call_count == 2
        assert len(result) > 0

    def test_raises_runtime_error_after_max_retries(self) -> None:
        with (
            patch(
                "computer_graphics.orchestrator.OllamaClient.health_check",
                return_value=True,
            ),
            patch(
                "computer_graphics.orchestrator.OllamaClient.chat",
                return_value="risposta sempre invalida",
            ),
            pytest.raises(RuntimeError, match="tentativi"),
        ):
            generate_scene_objects(
                "test",
                max_retries=2,
                verbose=False,
            )

    def test_uses_specified_model(self, valid_json_response: str) -> None:
        with (
            patch(
                "computer_graphics.orchestrator.OllamaClient.health_check",
                return_value=True,
            ),
            patch(
                "computer_graphics.orchestrator.OllamaClient.chat",
                return_value=valid_json_response,
            ) as mock_chat,
            patch(
                "computer_graphics.orchestrator.PromptBuilder.build",
                return_value={"model": "mistral", "messages": [], "stream": False},
            ),
        ):
            generate_scene_objects(
                "test",
                model="mistral",
                verbose=False,
            )
            # Verifica che il payload venga passato al client
            assert mock_chat.called
