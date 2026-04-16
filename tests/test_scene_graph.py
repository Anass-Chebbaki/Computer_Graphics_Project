"""Test per il modulo scene_graph."""

from __future__ import annotations

import pytest

from computer_graphics.scene_graph import (
    BoundingBox,
    SceneGraph,
    apply_scene_graph,
)
from computer_graphics.validator import SceneObject


def make_object(
    name: str,
    x: float = 0.0,
    y: float = 0.0,
    scale: float = 1.0,
    rot_z: float = 0.0,
) -> SceneObject:
    """Factory per creare SceneObject di test."""
    return SceneObject(
        name=name, x=x, y=y, z=0.0, rot_x=0.0, rot_y=0.0, rot_z=rot_z, scale=scale
    )


class TestBoundingBox:
    def test_properties_correct(self) -> None:
        bbox = BoundingBox(cx=0.0, cy=0.0, half_w=1.0, half_d=0.5)
        assert bbox.x_min == pytest.approx(-1.0)
        assert bbox.x_max == pytest.approx(1.0)
        assert bbox.y_min == pytest.approx(-0.5)
        assert bbox.y_max == pytest.approx(0.5)

    def test_intersects_overlapping(self) -> None:
        a = BoundingBox(cx=0.0, cy=0.0, half_w=1.0, half_d=1.0)
        b = BoundingBox(cx=0.5, cy=0.0, half_w=1.0, half_d=1.0)
        assert a.intersects(b) is True

    def test_not_intersects_distant(self) -> None:
        a = BoundingBox(cx=0.0, cy=0.0, half_w=0.5, half_d=0.5)
        b = BoundingBox(cx=5.0, cy=0.0, half_w=0.5, half_d=0.5)
        assert a.intersects(b) is False

    def test_area_calculation(self) -> None:
        bbox = BoundingBox(cx=0.0, cy=0.0, half_w=2.0, half_d=1.0)
        assert bbox.area() == pytest.approx(8.0)

    def test_margin_detection(self) -> None:
        # Due box vicini ma non sovrapposti
        a = BoundingBox(cx=0.0, cy=0.0, half_w=0.5, half_d=0.5)
        b = BoundingBox(cx=1.05, cy=0.0, half_w=0.5, half_d=0.5)
        # Senza margine: non si intersecano
        assert a.intersects(b, margin=0.0) is False
        # Con margine di 0.1: si intersecano (distanza 0.05 < margine 0.1)
        assert a.intersects(b, margin=0.1) is True


class TestSceneGraph:
    def test_add_object_creates_node(self) -> None:
        graph = SceneGraph()
        obj = make_object("table", x=0.0, y=0.0)
        node = graph.add_object(obj)
        assert node.obj.name == "table"
        assert len(graph.nodes) == 1

    def test_no_collision_no_adjustment(self) -> None:
        graph = SceneGraph()
        graph.add_object(make_object("table", x=0.0, y=0.0))
        graph.add_object(make_object("lamp", x=5.0, y=5.0))  # molto distante
        result = graph.resolve_collisions()
        # Nessun aggiustamento necessario
        assert not any(n.adjusted for n in graph.nodes)
        assert len(result) == 2

    def test_collision_resolved(self) -> None:
        graph = SceneGraph()
        # Due tavoli sovrapposti
        graph.add_object(make_object("table", x=0.0, y=0.0))
        graph.add_object(make_object("table", x=0.1, y=0.0))  # quasi sovrapposto
        result = graph.resolve_collisions()
        # Il secondo deve essere stato spostato
        assert any(n.adjusted for n in graph.nodes)
        assert len(result) == 2

    def test_after_resolution_no_overlap(self) -> None:
        graph = SceneGraph()
        graph.add_object(make_object("table", x=0.0, y=0.0))
        graph.add_object(make_object("chair", x=0.1, y=0.0))
        graph.resolve_collisions()
        # Verifica che dopo la risoluzione non ci siano più sovrapposizioni
        nodes = graph.nodes
        for i, na in enumerate(nodes):
            for nb in nodes[i + 1 :]:
                assert not na.bbox.intersects(
                    nb.bbox, margin=0.0
                ), f"Ancora sovrapposizione tra {na.obj.name} e {nb.obj.name}"

    def test_statistics(self) -> None:
        graph = SceneGraph()
        graph.add_object(make_object("table", x=0.0, y=0.0))
        graph.add_object(make_object("lamp", x=3.0, y=3.0))
        graph.resolve_collisions()
        stats = graph.get_statistics()
        assert stats["total_objects"] == 2
        assert "scene_width_m" in stats
        assert "scene_depth_m" in stats

    def test_scale_affects_bbox(self) -> None:
        graph = SceneGraph()
        node = graph.add_object(make_object("table", x=0.0, y=0.0, scale=2.0))
        # Con scala 2x il bbox deve essere più grande
        from computer_graphics.scene_graph import OBJECT_DIMENSIONS  # noqa: PLC0415

        dims = OBJECT_DIMENSIONS.get("table", (0.8, 0.8, 1.0))
        expected_half_w = (dims[0] * 2.0) / 2.0
        assert node.bbox.half_w == pytest.approx(expected_half_w)


class TestApplySceneGraph:
    def test_empty_list_returns_empty(self) -> None:
        result = apply_scene_graph([])
        assert result == []

    def test_single_object_unchanged(self) -> None:
        obj = make_object("table", x=1.0, y=2.0)
        result = apply_scene_graph([obj])
        assert len(result) == 1
        assert result[0].name == "table"

    def test_returns_scene_objects(self) -> None:
        objects = [
            make_object("table", x=0.0, y=0.0),
            make_object("chair", x=0.0, y=-1.5),
            make_object("lamp", x=3.0, y=3.0),
        ]
        result = apply_scene_graph(objects)
        assert len(result) == 3
        assert all(isinstance(obj, SceneObject) for obj in result)
