"""Test estesi per orchestrator."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from computer_graphics.llm_client import LLMConnectionError as OllamaConnectionError
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
        with patch("computer_graphics.orchestrator.get_llm_client") as mock_get_client:
            mock_client = mock_get_client.return_value
            mock_client.health_check.return_value = True
            mock_client.chat.return_value = VALID_JSON
            result = generate_scene_objects(
                "una stanza con tavolo",
                verbose=False,
            )
        assert len(result) >= 1

    def test_verbose_true_with_valid_response(self) -> None:
        """Copre il ramo verbose=True completo."""
        with patch("computer_graphics.orchestrator.get_llm_client") as mock_get_client:
            mock_client = mock_get_client.return_value
            mock_client.health_check.return_value = True
            mock_client.chat.return_value = VALID_JSON
            result = generate_scene_objects(
                "una stanza con tavolo",
                verbose=True,
            )
        assert len(result) >= 1

    def test_ollama_connection_error_propagates(self) -> None:
        """OllamaConnectionError durante chat deve propagarsi."""
        with patch("computer_graphics.orchestrator.get_llm_client") as mock_get_client:
            mock_client = mock_get_client.return_value
            mock_client.health_check.return_value = True
            mock_client.chat.side_effect = OllamaConnectionError("connection lost")

            with pytest.raises(OllamaConnectionError):
                generate_scene_objects("test", verbose=False)

    def test_runtime_error_message_contains_last_exception(self) -> None:
        """Verifica che RuntimeError contenga info sull'ultimo errore."""
        with patch("computer_graphics.orchestrator.get_llm_client") as mock_get_client:
            mock_client = mock_get_client.return_value
            mock_client.health_check.return_value = True
            mock_client.chat.return_value = "INVALID"

            with pytest.raises(RuntimeError) as exc_info:
                generate_scene_objects("test", max_retries=1, verbose=False)
            assert "tentativi" in str(exc_info.value)

    def test_verbose_prints_on_failed_attempt(self) -> None:
        """Copre il ramo verbose=True nel blocco except del retry."""
        call_count = 0

        def mock_chat(messages: list[dict[str, str]], **kwargs: dict[str, Any]) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "INVALID JSON"
            return VALID_JSON

        with patch("computer_graphics.orchestrator.get_llm_client") as mock_get_client:
            mock_client = mock_get_client.return_value
            mock_client.health_check.return_value = True
            mock_client.chat.side_effect = mock_chat
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
@patch("computer_graphics.orchestrator.get_llm_client")
def test_generate_scene_objects_full_flow(
    mock_get_client: MagicMock, mock_builder: MagicMock
) -> None:
    """Test successful full pipeline from description to validated objects."""
    mock_instance = mock_get_client.return_value
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
@patch("computer_graphics.orchestrator.get_llm_client")
def test_generate_scene_objects_health_check_fails(
    mock_get_client: MagicMock, mock_builder: MagicMock
) -> None:
    """Test that OllamaConnectionError is raised if health check fails."""
    mock_instance = mock_get_client.return_value
    mock_instance.health_check.return_value = False

    with pytest.raises(OllamaConnectionError, match="Ollama non risponde"):
        generate_scene_objects("A scene", verbose=True)


@patch("computer_graphics.orchestrator.PromptBuilder")
@patch("computer_graphics.orchestrator.get_llm_client")
def test_generate_scene_objects_network_error_on_chat(
    mock_get_client: MagicMock, mock_builder: MagicMock
) -> None:
    """Test handling of network errors during chat call."""
    mock_instance = mock_get_client.return_value
    mock_instance.health_check.return_value = True
    mock_instance.chat.side_effect = OllamaConnectionError("Connection failed")

    with pytest.raises(OllamaConnectionError, match="Connection failed"):
        generate_scene_objects("A scene", verbose=False)


@patch("computer_graphics.orchestrator.PromptBuilder")
@patch("computer_graphics.orchestrator.get_llm_client")
def test_generate_scene_objects_retries_on_invalid_json(
    mock_get_client: MagicMock, mock_builder: MagicMock
) -> None:
    """Test retry mechanism when JSON is malformed."""
    mock_instance = mock_get_client.return_value
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
@patch("computer_graphics.orchestrator.get_llm_client")
def test_generate_scene_objects_exceeds_max_retries(
    mock_get_client: MagicMock, mock_builder: MagicMock
) -> None:
    """Test that RuntimeError is raised after max retries."""
    mock_instance = mock_get_client.return_value
    mock_instance.health_check.return_value = True
    mock_instance.chat.return_value = "invalid"

    with pytest.raises(
        RuntimeError, match="Impossibile generare oggetti validi dopo 2"
    ):
        generate_scene_objects("A scene", max_retries=2, verbose=False)


@patch("computer_graphics.orchestrator.PromptBuilder")
@patch("computer_graphics.orchestrator.get_llm_client")
def test_generate_scene_objects_empty_array(
    mock_get_client: MagicMock, mock_builder: MagicMock
) -> None:
    """Test handling of empty object list from model."""
    mock_instance = mock_get_client.return_value
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

    @patch("computer_graphics.orchestrator.get_llm_client")
    @patch("computer_graphics.orchestrator.PromptBuilder")
    def test_model_parameter_applied_in_payload(
        self, mock_builder: MagicMock, mock_get_client: MagicMock
    ) -> None:
        """Testa che il parametro model viene configurato nel payload."""
        mock_instance = mock_get_client.return_value
        mock_instance.health_check.return_value = True
        mock_instance.chat.return_value = (
            '[{"name": "obj", "x": 0, "y": 0, "z": 0, "scale": 1.0}]'
        )

        mock_builder_instance = mock_builder.return_value
        mock_builder_instance.build.return_value = {"messages": [], "model": "custom"}

        generate_scene_objects("A scene", model="custom", verbose=False)
        mock_builder_instance.build.assert_called_once()

    def test_generate_scene_objects_openai_provider(self) -> None:
        """Verifica che generate_scene_objects funzioni con provider openai."""
        with (
            patch("computer_graphics.config_loader.ConfigLoader.get") as mock_get,
            patch("computer_graphics.orchestrator.get_llm_client") as mock_get_client,
            patch("computer_graphics.orchestrator.console.print"),
        ):
            # Mock ConfigLoader per restituire "openai"
            def mock_get_logic(*args: tuple, **kwargs: dict) -> str:  # noqa: ANN401
                if len(args) >= 2 and args[0] == "llm" and args[1] == "provider":
                    return "openai"
                if len(args) >= 1 and args[0] == "ollama":
                    return {"max_connection_retries": 3, "retry_delay": 2.0}
                return "test-val"

            mock_get.side_effect = mock_get_logic

            mock_client = mock_get_client.return_value
            mock_client.health_check.return_value = True
            mock_client.chat.return_value = (
                '[{"name": "obj1", "x": 0, "y": 0, "z": 0, "scale": 1.0}]'
            )

            result = generate_scene_objects("test", verbose=True)

            assert len(result) == 1
            args, kwargs = mock_get_client.call_args
            assert args[0] == "openai"
            assert kwargs["api_key"] == "test-val"
            assert kwargs["base_url"] == "test-val"

    def test_health_check_fail_non_ollama(self) -> None:
        """Test errore health check per provider generico."""
        with (
            patch(
                "computer_graphics.config_loader.ConfigLoader.get",
            ) as mock_get,
            patch("computer_graphics.orchestrator.get_llm_client") as mock_get_client,
            patch("computer_graphics.orchestrator.console.print"),
        ):

            def mock_get_logic(*args: tuple, **kwargs: dict) -> str:  # noqa: ANN401
                if len(args) >= 2 and args[0] == "llm" and args[1] == "provider":
                    return "generic"
                if len(args) >= 1 and args[0] == "ollama":
                    return {}
                return "test-val"

            mock_get.side_effect = mock_get_logic
            mock_client = mock_get_client.return_value
            mock_client.health_check.return_value = False

            from computer_graphics.llm_client import LLMConnectionError

            with pytest.raises(
                LLMConnectionError,
                match="Provider generic non risponde",
            ):
                generate_scene_objects("test", verbose=True)
