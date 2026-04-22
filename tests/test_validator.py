"""Test estesi per validator."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from computer_graphics.validator import (
    LightObject,
    SceneObject,
    validate_lights,
    validate_objects,
)


class TestSceneObjectExtended:
    def test_name_non_string_raises(self) -> None:
        """Copre il ramo isinstance(v, str) in normalise_name."""
        with pytest.raises(ValidationError):
            SceneObject(
                name=123,  # type: ignore[arg-type]
                x=0.0,
                y=0.0,
                z=0.0,
                rot_x=0.0,
                rot_y=0.0,
                rot_z=0.0,
            )

    def test_name_empty_after_strip_raises(self) -> None:
        """Copre il ramo 'not normalised' in normalise_name."""
        with pytest.raises(ValidationError):
            SceneObject(
                name="   ",
                x=0.0,
                y=0.0,
                z=0.0,
                rot_x=0.0,
                rot_y=0.0,
                rot_z=0.0,
            )

    def test_coerce_numeric_invalid_string_raises(self) -> None:
        """Copre la ValueError nella coercizione numerica."""
        with pytest.raises(ValidationError):
            SceneObject(
                name="table",
                x="not_a_float",  # type: ignore[arg-type]
                y=0.0,
                z=0.0,
                rot_x=0.0,
                rot_y=0.0,
                rot_z=0.0,
            )

    def test_coerce_numeric_invalid_type_raises(self) -> None:
        """Copre il raise finale per tipo non supportato."""
        with pytest.raises(ValidationError):
            SceneObject(
                name="table",
                x=[1, 2, 3],  # type: ignore[arg-type]
                y=0.0,
                z=0.0,
                rot_x=0.0,
                rot_y=0.0,
                rot_z=0.0,
            )

    def test_out_of_bounds_coordinates_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Copre check_reasonable_bounds con valori fuori scala."""
        import logging

        with caplog.at_level(logging.WARNING, logger="computer_graphics.validator"):
            obj = SceneObject(
                name="table",
                x=100.0,  # fuori scala
                y=0.0,
                z=0.0,
                rot_x=0.0,
                rot_y=0.0,
                rot_z=0.0,
            )
        assert obj.x == pytest.approx(100.0)
        assert any("fuori scala" in record.message for record in caplog.records)

    def test_out_of_bounds_y_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """Copre check_reasonable_bounds per y."""
        import logging

        with caplog.at_level(logging.WARNING, logger="computer_graphics.validator"):
            obj = SceneObject(
                name="table",
                x=0.0,
                y=-60.0,
                z=0.0,
                rot_x=0.0,
                rot_y=0.0,
                rot_z=0.0,
            )
        assert obj.y == pytest.approx(-60.0)

    def test_suggest_asset_name_known(self) -> None:
        """Copre suggest_asset_name con nome in KNOWN_ASSET_NAMES."""
        obj = SceneObject(
            name="table",
            x=0.0,
            y=0.0,
            z=0.0,
            rot_x=0.0,
            rot_y=0.0,
            rot_z=0.0,
        )
        assert obj.suggest_asset_name() == "table"

    def test_suggest_asset_name_partial_match(self) -> None:
        """Copre suggest_asset_name con corrispondenza parziale."""
        # 'bookshelf' contiene 'shelf' -> no, ma 'bookshelf' in KNOWN
        # Usiamo un nome che ha corrispondenza parziale
        obj = SceneObject(
            name="office_table",
            x=0.0,
            y=0.0,
            z=0.0,
            rot_x=0.0,
            rot_y=0.0,
            rot_z=0.0,
        )
        suggestion = obj.suggest_asset_name()
        # 'table' è in 'office_table'
        assert suggestion == "table"

    def test_suggest_asset_name_no_match_returns_original(self) -> None:
        """Copre suggest_asset_name senza corrispondenza."""
        obj = SceneObject(
            name="xyz_unknown_obj",
            x=0.0,
            y=0.0,
            z=0.0,
            rot_x=0.0,
            rot_y=0.0,
            rot_z=0.0,
        )
        suggestion = obj.suggest_asset_name()
        assert suggestion == "xyz_unknown_obj"

    def test_coerce_integer_to_float(self) -> None:
        """Coerzione int -> float."""
        obj = SceneObject(
            name="lamp",
            x=1,
            y=2,
            z=0,  # type: ignore[arg-type]
            rot_x=0,
            rot_y=0,
            rot_z=0,
        )
        assert isinstance(obj.x, float)
        assert obj.x == pytest.approx(1.0)


class TestValidateObjectsExtended:
    def test_raises_on_non_list_input(self) -> None:
        """Copre il controllo isinstance(raw_objects, list)."""
        with pytest.raises((ValueError, TypeError)):
            validate_objects({"name": "table"})  # type: ignore[arg-type]

    def test_skips_non_dict_items(self) -> None:
        """Copre il controllo isinstance(obj, dict) nel loop."""
        objects = [
            {"name": "table", "x": 0.0, "y": 0.0, "z": 0.0},
            "not_a_dict",  # type: ignore[list-item]
            42,  # type: ignore[list-item]
        ]
        # Deve estrarre solo l'oggetto valido
        result = validate_objects(objects)  # type: ignore[arg-type]
        assert len(result) == 1
        assert result[0].name == "table"

    def test_raises_when_all_non_dict(self) -> None:
        """Tutti non-dict: deve sollevare ValueError."""
        with pytest.raises(ValueError):
            validate_objects(["string1", "string2"])  # type: ignore[arg-type,list-item]

    def test_multiple_valid_objects(self) -> None:
        """Validazione con più oggetti validi."""
        objects = [
            {"name": "table", "x": 0.0, "y": 0.0, "z": 0.0},
            {"name": "chair", "x": 1.0, "y": -1.0, "z": 0.0},
            {"name": "lamp", "x": -2.0, "y": -2.0, "z": 0.0},
        ]
        result = validate_objects(objects)
        assert len(result) == 3

    def test_default_values_applied(self) -> None:
        """Verifica che i default vengano applicati."""
        objects = [{"name": "sofa", "x": 1.0, "y": 2.0, "z": 0.0}]
        result = validate_objects(objects)
        assert result[0].scale == pytest.approx(1.0)
        assert result[0].rot_x == pytest.approx(0.0)


class TestValidatorAdditional:
    """Test aggiuntivi per validator.py coverage."""

    def test_scene_object_with_all_rotation_fields(self) -> None:
        """Test SceneObject con tutti i campi di rotazione."""
        obj = SceneObject(
            name="cube",
            x=1.0,
            y=2.0,
            z=3.0,
            scale=1.5,
            rot_x=0.1,
            rot_y=0.2,
            rot_z=0.3,
        )
        assert obj.rot_x == 0.1
        assert obj.rot_y == 0.2
        assert obj.rot_z == 0.3

    def test_validate_objects_adds_missing_rotation(self) -> None:
        """Test che validate_objects aggiunge default rotation fields."""
        objects = [{"name": "table", "x": 0, "y": 0, "z": 0, "scale": 1.0}]
        result = validate_objects(objects)
        assert result[0].rot_x == 0.0
        assert result[0].rot_y == 0.0
        assert result[0].rot_z == 0.0

    def test_scene_object_name_normalization_with_special_chars(self) -> None:
        """Test normalizzazione nome con caratteri speciali."""
        obj = SceneObject(
            name="LARGE TABLE-123",
            x=0,
            y=0,
            z=0,
            scale=1.0,
        )
        # Hyphen è mantenuto, non convertito in underscore
        assert obj.name == "large_table-123"

    def test_coerce_numeric_with_float_string(self) -> None:
        """Test coercizione di stringa float."""
        objects = [
            {
                "name": "obj",
                "x": "1.5",
                "y": "2.7",
                "z": "0.0",
                "scale": "1.0",
            }
        ]
        result = validate_objects(objects)  # type: ignore[arg-type]
        assert result[0].x == 1.5
        assert result[0].y == 2.7

    def test_validate_objects_with_extra_fields(self) -> None:
        """Test che validate_objects ignora campi extra."""
        objects = [
            {
                "name": "obj",
                "x": 0,
                "y": 0,
                "z": 0,
                "scale": 1.0,
                "extra_field": "ignored",
                "another_field": 123,
            }
        ]
        result = validate_objects(objects)
        assert len(result) == 1
        assert result[0].name == "obj"

    def test_light_object_validation(self) -> None:
        """Test LightObject validation con campi RGB e numerici."""
        from computer_graphics.validator import LightObject

        light = LightObject(
            name="lamp1",
            x=1.0,
            y=2.0,
            z=3.0,
            color=(0.8, 0.9, 1.0),
            energy=1500.0,
            spot_size=45.0,
        )
        assert light.name == "lamp1"
        assert light.color == (0.8, 0.9, 1.0)
        assert light.energy == 1500.0
        assert light.spot_size == 45.0

    def test_light_object_color_clamping(self) -> None:
        """Test che LightObject clamp valori RGB fuori range [0, 1]."""
        from computer_graphics.validator import LightObject

        light = LightObject(
            name="bright_lamp",
            x=0,
            y=0,
            z=5.0,
            color=(1.5, -0.2, 0.5),  # Out of range
            energy=2000.0,
        )
        # Clamp to [0, 1]
        assert light.color == (1.0, 0.0, 0.5)

    def test_scene_object_out_of_bounds_warning(self) -> None:
        """Test che SceneObject warns su coordinate fuori scala."""
        obj = SceneObject(
            name="far_object",
            x=100.0,  # Way beyond max_coord=50
            y=0.0,
            z=0.0,
        )
        # Should not raise, just log warning
        assert obj.x == 100.0

    def test_validate_lights_function(self) -> None:
        """Test validate_lights con lista di dizionari."""
        from computer_graphics.validator import validate_lights

        raw_lights = [
            {
                "name": "sun",
                "x": 0,
                "y": 10,
                "z": 5,
                "color": [1.0, 0.95, 0.8],
                "energy": 2000.0,
            }
        ]
        result = validate_lights(raw_lights)
        assert len(result) == 1
        assert result[0].name == "sun"
        assert result[0].energy == 2000.0

    def test_validate_lights_with_invalid_item(self) -> None:
        """Test validate_lights scarta item non validi."""
        from computer_graphics.validator import validate_lights

        raw_lights = [
            {
                "name": "lamp1",
                "x": 0,
                "y": 0,
                "z": 0,
                "color": [1, 1, 1],
                "energy": 1500.0,
            },
            "invalid_item",  # Not a dict
            {
                "name": "lamp2",
                "x": 1,
                "y": 2,
                "z": 3,
                "color": [0.5, 0.5, 0.5],
                "energy": 1000.0,
            },
        ]
        result = validate_lights(raw_lights)  # type: ignore[arg-type]
        # Should have 2 valid lights (skipped the string)
        assert len(result) == 2

    def test_suggest_asset_name_known(self) -> None:
        """Test suggest_asset_name per asset noto."""
        obj = SceneObject(
            name="cube",
            x=0,
            y=0,
            z=0,
            scale=1.0,
        )
        # Verifica presenza in KNOWN_ASSET_NAMES
        assert obj.suggest_asset_name() == "cube"

    def test_suggest_asset_name_fallback(self) -> None:
        """Test suggest_asset_name fallback per asset sconosciuto."""
        obj = SceneObject(
            name="cuboid",  # Not in list but contains "cube"
            x=0,
            y=0,
            z=0,
            scale=1.0,
        )
        # Verifica del suggerimento "cube" come fallback (controllo di contenimento)
        suggested = obj.suggest_asset_name()
        assert suggested in ["cube", "cuboid"]  # Either found or returns self

    def test_orchestrator_collision_retry_path(self) -> None:
        """Test che orchestrator retry con feedback su collisione."""
        from unittest.mock import patch

        from computer_graphics.orchestrator import (
            CollisionResolutionError,
            generate_scene_objects,
        )

        with (
            patch("computer_graphics.orchestrator.get_llm_client") as mock_get_client,
            patch("computer_graphics.orchestrator.PromptBuilder") as mock_builder,
            patch("computer_graphics.orchestrator.extract_json"),
            patch("computer_graphics.orchestrator.validate_objects") as mock_validate,
            patch(
                "computer_graphics.orchestrator._apply_scene_graph_with_collision_check"
            ) as mock_sg,
        ):
            mock_instance = mock_get_client.return_value
            mock_instance.health_check.return_value = True

            # Prima volta: collisione, seconda volta: successo
            mock_instance.chat.side_effect = [
                '[{"name": "a", "x": 0, "y": 0, "z": 0, "scale": 1}]',
                '[{"name": "b", "x": 1, "y": 1, "z": 0, "scale": 1}]',
            ]

            mock_builder_instance = mock_builder.return_value
            mock_builder_instance.build.return_value = {
                "messages": [],
                "model": "test",
            }

            # Crea un mock SceneObject
            obj = SceneObject(
                name="obj1",
                x=0.0,
                y=0.0,
                z=0.0,
                scale=1.0,
            )
            mock_validate.side_effect = [[obj], [obj]]
            mock_sg.side_effect = [
                CollisionResolutionError("a", "b"),
                [obj],
            ]

            result = generate_scene_objects("test scene", max_retries=3, verbose=False)
            assert len(result) == 1
            # Chat deve essere chiamato 2 volte
            assert mock_instance.chat.call_count == 2

    def test_orchestrator_verbose_mode_health_check_fail(self) -> None:
        """Test orchestrator verbose=True con health_check che fallisce."""
        from unittest.mock import patch

        from computer_graphics.llm_client import LLMConnectionError
        from computer_graphics.orchestrator import generate_scene_objects

        with patch("computer_graphics.orchestrator.get_llm_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.health_check.return_value = False

            with pytest.raises(LLMConnectionError):
                generate_scene_objects("test scene", verbose=True)

    def test_orchestrator_verbose_mode_with_spinner(self) -> None:
        """Test orchestrator verbose=True con spinner e output."""
        from unittest.mock import patch

        from computer_graphics.orchestrator import generate_scene_objects

        with (
            patch("computer_graphics.orchestrator.get_llm_client") as mock_get_client,
            patch("computer_graphics.orchestrator.PromptBuilder") as mock_builder,
            patch("computer_graphics.orchestrator.extract_json") as mock_extract,
            patch("computer_graphics.orchestrator.validate_objects") as mock_validate,
            patch(
                "computer_graphics.orchestrator._apply_scene_graph_with_collision_check"
            ) as mock_sg,
            patch(
                "computer_graphics.orchestrator._print_results_table"
            ) as mock_print_table,
        ):
            mock_instance = mock_get_client.return_value
            mock_instance.health_check.return_value = True
            mock_instance.chat.return_value = (
                '[{"name": "obj1", "x": 0, "y": 0, "z": 0, "scale": 1.0}]'
            )

            mock_builder_instance = mock_builder.return_value
            mock_builder_instance.build.return_value = {
                "messages": [],
                "model": "test",
            }

            mock_extract.return_value = [
                {"name": "obj1", "x": 0, "y": 0, "z": 0, "scale": 1.0}
            ]

            obj = SceneObject(
                name="obj1",
                x=0.0,
                y=0.0,
                z=0.0,
                scale=1.0,
            )
            mock_validate.return_value = [obj]
            mock_sg.return_value = [obj]

            result = generate_scene_objects("test scene", verbose=True)
            assert len(result) == 1
            # _print_results_table deve essere chiamato
            mock_print_table.assert_called_once()

    def test_orchestrator_json_parse_error_retry(self) -> None:
        """Test orchestrator retry su JSONParseError."""
        from unittest.mock import patch

        from computer_graphics.orchestrator import (
            JSONParseError,
            generate_scene_objects,
        )

        with (
            patch("computer_graphics.orchestrator.get_llm_client") as mock_get_client,
            patch("computer_graphics.orchestrator.PromptBuilder") as mock_builder,
            patch("computer_graphics.orchestrator.extract_json") as mock_extract,
            patch("computer_graphics.orchestrator.validate_objects") as mock_validate,
            patch(
                "computer_graphics.orchestrator._apply_scene_graph_with_collision_check"
            ) as mock_sg,
        ):
            mock_instance = mock_get_client.return_value
            mock_instance.health_check.return_value = True
            json_payload = '[{"name": "obj1", "x": 0, "y": 0, "z": 0, "scale": 1.0}]'
            mock_instance.chat.side_effect = [
                "invalid json",  # Prima volta: errore parsing
                json_payload,  # Seconda volta: ok
            ]

            mock_builder_instance = mock_builder.return_value
            mock_builder_instance.build.return_value = {
                "messages": [],
                "model": "test",
            }

            # Prima volta: JSONParseError, seconda volta: ok
            mock_extract.side_effect = [
                JSONParseError("Invalid JSON"),
                [{"name": "obj1", "x": 0, "y": 0, "z": 0, "scale": 1.0}],
            ]

            obj = SceneObject(
                name="obj1",
                x=0.0,
                y=0.0,
                z=0.0,
                scale=1.0,
            )
            mock_validate.return_value = [obj]
            mock_sg.return_value = [obj]

            result = generate_scene_objects("test scene", max_retries=3, verbose=False)
            assert len(result) == 1
            # Chat deve essere chiamato 2 volte
            assert mock_instance.chat.call_count == 2

    def test_orchestrator_verbose_json_error_with_console(self) -> None:
        """Test orchestrator verbose path con JSONParseError."""
        from unittest.mock import patch

        from computer_graphics.orchestrator import (
            JSONParseError,
            generate_scene_objects,
        )

        with (
            patch("computer_graphics.orchestrator.get_llm_client") as mock_get_client,
            patch("computer_graphics.orchestrator.PromptBuilder") as mock_builder,
            patch("computer_graphics.orchestrator.extract_json") as mock_extract,
            patch("computer_graphics.orchestrator.validate_objects") as mock_validate,
            patch(
                "computer_graphics.orchestrator._apply_scene_graph_with_collision_check"
            ) as mock_sg,
        ):
            mock_instance = mock_get_client.return_value
            mock_instance.health_check.return_value = True
            mock_instance.chat.side_effect = [
                "invalid json",
                '[{"name": "obj1", "x": 0, "y": 0, "z": 0, "scale": 1.0}]',
            ]

            mock_builder_instance = mock_builder.return_value
            mock_builder_instance.build.return_value = {
                "messages": [],
                "model": "test",
            }

            mock_extract.side_effect = [
                JSONParseError("Bad JSON"),
                [{"name": "obj1", "x": 0, "y": 0, "z": 0, "scale": 1.0}],
            ]

            obj = SceneObject(
                name="obj1",
                x=0.0,
                y=0.0,
                z=0.0,
                scale=1.0,
            )
            mock_validate.return_value = [obj]
            mock_sg.return_value = [obj]

            # Usa verbose=True per esercitare il console.print path
            result = generate_scene_objects("test scene", verbose=True, max_retries=3)
            assert len(result) == 1

    def test_orchestrator_real_flow_verbose(self) -> None:
        """Test orchestrator flow reale con verbose."""
        from unittest.mock import patch

        from computer_graphics.orchestrator import generate_scene_objects

        # Real JSON string
        json_output = '[{"name": "table", "x": 0, "y": 0, "z": 0, "scale": 1.0}]'

        with (
            patch("computer_graphics.orchestrator.get_llm_client") as mock_get_client,
            patch("computer_graphics.orchestrator.PromptBuilder") as mock_builder,
            patch(
                "computer_graphics.orchestrator._apply_scene_graph_with_collision_check"
            ) as mock_sg,
            patch("computer_graphics.orchestrator._print_results_table"),
        ):
            mock_instance = mock_get_client.return_value
            mock_instance.health_check.return_value = True
            mock_instance.chat.return_value = json_output

            mock_builder_instance = mock_builder.return_value
            mock_builder_instance.build.return_value = {
                "messages": [
                    {"role": "system", "content": "You are a 3D scene generator"},
                    {"role": "user", "content": "Create a scene"},
                ],
                "model": "test_model",
            }

            obj = SceneObject(name="table", x=0.0, y=0.0, z=0.0, scale=1.0)
            mock_sg.return_value = [obj]

            result = generate_scene_objects("Create a simple room", verbose=True)
            assert len(result) == 1
            assert result[0].name == "table"


class TestValidatorCoverageMerged:
    def test_light_object_invalid_color_type(self) -> None:
        """Test linea 101: colore non tripla."""
        with pytest.raises(ValueError, match="color"):
            LightObject(color="red")  # type: ignore

    def test_coerce_numeric_invalid_string(self) -> None:
        """Test linea 115: stringa non numerica."""
        with pytest.raises(ValueError, match="Impossibile convertire"):
            LightObject.coerce_numeric("abc")

    def test_coerce_numeric_invalid_type(self) -> None:
        """Test linea 116: tipo non supportato."""
        with pytest.raises(ValueError, match="Tipo non supportato"):
            LightObject.coerce_numeric([])

    def test_validate_color_override_none(self) -> None:
        """Test linea 180: override None."""
        obj = SceneObject(name="test", color_override=None)
        assert obj.color_override is None

    def test_normalise_parent_invalid_type(self) -> None:
        """Test linea 218: parent non stringa."""
        with pytest.raises(ValueError, match="parent"):
            SceneObject(name="test", parent=123)  # type: ignore

    def test_validate_color_override_valid(self) -> None:
        """Test linea 181: override con colore valido."""
        obj = SceneObject(name="test", color_override=(0.5, 0.5, 0.5))
        assert obj.color_override == (0.5, 0.5, 0.5)

    def test_reasonable_bounds_warnings(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test linee 250, 259: warning rotazione e scala."""
        SceneObject(name="test", rot_x=20.0, scale=200.0)
        assert "rotazione rot_x" in caplog.text
        assert "scala 200.00 fuori scala" in caplog.text

    def test_validate_objects_exception_handling(self) -> None:
        """Test linea 335-336: eccezione durante creazione SceneObject."""
        # Passiamo un dict che fallisce la validazione
        raw = [{"name": "test", "scale": -1.0}]
        # validate_objects cattura l'eccezione internamente e la logga/raccoglie
        with pytest.raises(ValueError, match="Nessun oggetto valido estratto"):
            validate_objects(raw)

    def test_validate_lights_empty(self) -> None:
        """Test linea 368: lista luci vuota."""
        assert validate_lights([]) == []

    def test_validate_lights_exception_handling(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test linea 378-379: eccezione in validate_lights."""
        raw = [{"name": "light", "energy": -10.0}]
        res = validate_lights(raw)
        assert len(res) == 0
        assert "Luce #0" in caplog.text
