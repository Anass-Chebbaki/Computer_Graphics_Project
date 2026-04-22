"""Test estesi per orchestrator."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from computer_graphics.ollama_client import OllamaConnectionError
from computer_graphics.orchestrator import _print_results_table, generate_scene_objects
from computer_graphics.validator import SceneObject


def _make_scene_object(name: str = "table") -> SceneObject:
    return SceneObject(
        name=name, x=0.0, y=0.0, z=0.0, rot_x=0.0, rot_y=0.0, rot_z=0.0, scale=1.0
    )


VALID_JSON = json.dumps(
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
        }
    ]
)


class TestGenerateSceneObjectsExtended:
    def test_verbose_false_skips_status(self) -> None:
        """Copre il ramo verbose=False (nessun console.status)."""
        with (
            patch(
                "computer_graphics.orchestrator.OllamaClient.health_check",
                return_value=True,
            ),
            patch(
                "computer_graphics.orchestrator.OllamaClient.chat",
                return_value=VALID_JSON,
            ),
        ):
            result = generate_scene_objects(
                "una stanza con tavolo",
                verbose=False,
            )
        assert len(result) >= 1

    def test_verbose_true_with_valid_response(self) -> None:
        """Copre il ramo verbose=True completo."""
        with (
            patch(
                "computer_graphics.orchestrator.OllamaClient.health_check",
                return_value=True,
            ),
            patch(
                "computer_graphics.orchestrator.OllamaClient.chat",
                return_value=VALID_JSON,
            ),
        ):
            result = generate_scene_objects(
                "una stanza con tavolo",
                verbose=True,
            )
        assert len(result) >= 1

    def test_ollama_connection_error_propagates(self) -> None:
        """OllamaConnectionError durante chat deve propagarsi."""
        with (
            patch(
                "computer_graphics.orchestrator.OllamaClient.health_check",
                return_value=True,
            ),
            patch(
                "computer_graphics.orchestrator.OllamaClient.chat",
                side_effect=OllamaConnectionError("connection lost"),
            ),
            pytest.raises(OllamaConnectionError),
        ):
            generate_scene_objects("test", verbose=False)

    def test_runtime_error_message_contains_last_exception(self) -> None:
        """Verifica che RuntimeError contenga info sull'ultimo errore."""
        with (
            patch(
                "computer_graphics.orchestrator.OllamaClient.health_check",
                return_value=True,
            ),
            patch(
                "computer_graphics.orchestrator.OllamaClient.chat",
                return_value="INVALID",
            ),
            pytest.raises(RuntimeError) as exc_info,
        ):
            generate_scene_objects("test", max_retries=1, verbose=False)
        assert "tentativi" in str(exc_info.value)

    def test_verbose_prints_on_failed_attempt(self) -> None:
        """Copre il ramo verbose=True nel blocco except del retry."""
        call_count = 0

        def mock_chat(payload: dict) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "INVALID JSON"
            return VALID_JSON

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
            result = generate_scene_objects("test", max_retries=3, verbose=True)
        assert len(result) >= 1
        assert call_count == 2


class TestPrintResultsTable:
    def test_prints_without_error(self) -> None:
        """Copre _print_results_table."""
        objects = [
            _make_scene_object("table"),
            _make_scene_object("chair"),
        ]
        # Non deve sollevare eccezioni
        _print_results_table(objects)

    def test_prints_empty_list(self) -> None:
        """_print_results_table con lista vuota."""
        _print_results_table([])


# ====== Tests da test_orchestrator_coverage.py ======


from unittest.mock import MagicMock  # noqa: E402


@patch("computer_graphics.orchestrator.PromptBuilder")
@patch("computer_graphics.orchestrator.OllamaClient")
def test_generate_scene_objects_full_flow(
    mock_client: MagicMock, mock_builder: MagicMock
) -> None:
    """Test successful full pipeline from description to validated objects."""
    mock_instance = mock_client.return_value
    mock_instance.health_check.return_value = True

    mock_instance.chat.return_value = """[
        {"name": "chair", "x": 0.5, "y": 1.0, "z": 0.0, "scale": 0.8, "rot_z": 1.57},
        {"name": "desk", "x": 2.0, "y": 1.5, "z": 0.0, "scale": 2.0, "rot_z": 0.0}
    ]"""

    mock_builder_instance = mock_builder.return_value
    mock_builder_instance.build.return_value = {
        "model": "llama3",
        "messages": [],
    }

    result = generate_scene_objects("A room with furniture", verbose=False)
    assert len(result) == 2
    names = {obj.name for obj in result}
    assert names == {"chair", "desk"}


@patch("computer_graphics.orchestrator.PromptBuilder")
@patch("computer_graphics.orchestrator.OllamaClient")
def test_generate_scene_objects_health_check_fails(
    mock_client: MagicMock, mock_builder: MagicMock
) -> None:
    """Test that OllamaConnectionError is raised if health check fails."""
    mock_instance = mock_client.return_value
    mock_instance.health_check.return_value = False

    with pytest.raises(OllamaConnectionError, match="Ollama non risponde"):
        generate_scene_objects("A scene", verbose=True)


@patch("computer_graphics.orchestrator.PromptBuilder")
@patch("computer_graphics.orchestrator.OllamaClient")
def test_generate_scene_objects_network_error_on_chat(
    mock_client: MagicMock, mock_builder: MagicMock
) -> None:
    """Test handling of network errors during chat call."""
    mock_instance = mock_client.return_value
    mock_instance.health_check.return_value = True
    mock_instance.chat.side_effect = OllamaConnectionError("Connection failed")

    with pytest.raises(OllamaConnectionError, match="Connection failed"):
        generate_scene_objects("A scene", verbose=False)


@patch("computer_graphics.orchestrator.PromptBuilder")
@patch("computer_graphics.orchestrator.OllamaClient")
def test_generate_scene_objects_retries_on_invalid_json(
    mock_client: MagicMock, mock_builder: MagicMock
) -> None:
    """Test retry mechanism when JSON is malformed."""
    mock_instance = mock_client.return_value
    mock_instance.health_check.return_value = True

    mock_instance.chat.side_effect = [
        "not valid json",
        "also not json",
        """[{"name": "obj", "x": 0, "y": 0, "z": 0, "scale": 1.0, "rot_z": 0}]""",
    ]

    result = generate_scene_objects("A scene", max_retries=3, verbose=False)
    assert len(result) == 1
    assert mock_instance.chat.call_count == 3


@patch("computer_graphics.orchestrator.PromptBuilder")
@patch("computer_graphics.orchestrator.OllamaClient")
def test_generate_scene_objects_exceeds_max_retries(
    mock_client: MagicMock, mock_builder: MagicMock
) -> None:
    """Test that RuntimeError is raised after max retries."""
    mock_instance = mock_client.return_value
    mock_instance.health_check.return_value = True
    mock_instance.chat.return_value = "invalid"

    with pytest.raises(
        RuntimeError, match="Impossibile generare oggetti validi dopo 2"
    ):
        generate_scene_objects("A scene", max_retries=2, verbose=False)


@patch("computer_graphics.orchestrator.PromptBuilder")
@patch("computer_graphics.orchestrator.OllamaClient")
def test_generate_scene_objects_empty_array(
    mock_client: MagicMock, mock_builder: MagicMock
) -> None:
    """Test handling of empty object list from model."""
    mock_instance = mock_client.return_value
    mock_instance.health_check.return_value = True
    mock_instance.chat.return_value = "[]"

    with pytest.raises(RuntimeError):
        generate_scene_objects("A scene", max_retries=1, verbose=False)


def test_print_results_table_single_object() -> None:
    """Test printing results table with single object."""
    objs = [SceneObject(name="lamp", x=1.0, y=2.0, z=3.0, scale=1.5, rot_z=0.785)]
    _print_results_table(objs)


def test_print_results_table_multiple_objects() -> None:
    """Test printing results table with multiple objects."""
    objs = [
        SceneObject(name="couch", x=0.0, y=0.0, z=0.0, scale=1.0, rot_z=0.0),
        SceneObject(name="table", x=2.0, y=1.0, z=0.0, scale=2.0, rot_z=1.57),
        SceneObject(name="plant", x=3.0, y=2.0, z=0.5, scale=0.5, rot_z=3.14),
    ]
    _print_results_table(objs)


class TestOrchestratorAdditional:
    """Test aggiuntivi per orchestrator.py coverage."""

    @patch("computer_graphics.orchestrator.OllamaClient")
    @patch("computer_graphics.orchestrator.PromptBuilder")
    def test_model_parameter_applied_in_payload(
        self, mock_builder: MagicMock, mock_client: MagicMock
    ) -> None:
        """Testa che il parametro model viene configurato nel payload."""
        mock_instance = mock_client.return_value
        mock_instance.health_check.return_value = True
        mock_instance.chat.return_value = (
            '[{"name": "obj", "x": 0, "y": 0, "z": 0, "scale": 1.0}]'
        )

        mock_builder_instance = mock_builder.return_value
        mock_builder_instance.build.return_value = {"messages": [], "model": "custom"}

        generate_scene_objects("A scene", model="custom", verbose=False)
        mock_builder_instance.build.assert_called_once()
