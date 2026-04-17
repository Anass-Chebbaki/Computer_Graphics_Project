"""Test per il modulo validator."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from computer_graphics.validator import SceneObject, validate_objects


class TestSceneObject:
    def test_valid_object(self) -> None:
        obj = SceneObject(
            name="table",
            x=0.0,
            y=0.0,
            z=0.0,
            rot_x=0.0,
            rot_y=0.0,
            rot_z=0.0,
            scale=1.0,
        )
        assert obj.name == "table"
        assert obj.scale == 1.0

    def test_name_normalised_to_lowercase(self) -> None:
        obj = SceneObject(
            name="TABLE", x=0.0, y=0.0, z=0.0, rot_x=0.0, rot_y=0.0, rot_z=0.0
        )
        assert obj.name == "table"

    def test_name_spaces_to_underscores(self) -> None:
        obj = SceneObject(
            name="office chair", x=0.0, y=0.0, z=0.0, rot_x=0.0, rot_y=0.0, rot_z=0.0
        )
        assert obj.name == "office_chair"

    def test_string_numerics_coerced(self) -> None:
        obj = SceneObject(
            name="lamp",
            x="1.5",  # type: ignore[arg-type]
            y="-0.8",  # type: ignore[arg-type]
            z="0.0",  # type: ignore[arg-type]
            rot_x="0.0",  # type: ignore[arg-type]
            rot_y="0.0",  # type: ignore[arg-type]
            rot_z="0.785",  # type: ignore[arg-type]
        )
        assert obj.x == pytest.approx(1.5)
        assert obj.rot_z == pytest.approx(0.785)

    def test_invalid_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            SceneObject(name="", x=0.0, y=0.0, z=0.0, rot_x=0.0, rot_y=0.0, rot_z=0.0)

    def test_negative_scale_raises(self) -> None:
        with pytest.raises(ValidationError):
            SceneObject(
                name="table",
                x=0.0,
                y=0.0,
                z=0.0,
                rot_x=0.0,
                rot_y=0.0,
                rot_z=0.0,
                scale=-1.0,
            )


class TestValidateObjects:
    def test_valid_list(self, valid_objects_list: list[dict]) -> None:
        result = validate_objects(valid_objects_list)
        assert len(result) == 2
        assert all(isinstance(o, SceneObject) for o in result)

    def test_adds_missing_rotation_fields(self) -> None:
        objects = [{"name": "table", "x": 0.0, "y": 0.0, "z": 0.0}]
        result = validate_objects(objects)
        assert result[0].rot_x == 0.0
        assert result[0].rot_y == 0.0
        assert result[0].rot_z == 0.0

    def test_raises_on_empty_list(self) -> None:
        with pytest.raises(ValueError, match="vuota"):
            validate_objects([])

    def test_partial_valid_list_warns_but_returns(self) -> None:
        objects = [
            {"name": "table", "x": 0.0, "y": 0.0, "z": 0.0},
            {"name": "", "x": 0.0, "y": 0.0, "z": 0.0},  # invalido
        ]
        result = validate_objects(objects)
        assert len(result) == 1  # solo il valido

    def test_raises_when_all_invalid(self) -> None:
        with pytest.raises(ValueError):
            validate_objects([{"x": 0.0}, {"y": 1.0}])  # nessun name
