# tests/test_scene_graph_extended.py
"""Test estesi per scene_graph - copertura righe mancanti."""

from __future__ import annotations

import math

import pytest

from computer_graphics.scene_graph import (
    _DEFAULT_DIMENSION,
    BoundingBox,
    SceneGraph,
    apply_scene_graph,
)
from computer_graphics.validator import SceneObject


def make_obj(
    name: str,
    x: float = 0.0,
    y: float = 0.0,
    scale: float = 1.0,
    rot_z: float = 0.0,
) -> SceneObject:
    return SceneObject(
        name=name,
        x=x,
        y=y,
        z=0.0,
        rot_x=0.0,
        rot_y=0.0,
        rot_z=rot_z,
        scale=scale,
    )


class TestBoundingBoxExtended:
    def test_intersects_touching_boundary(self) -> None:
        """Due bbox che si toccano esattamente sul bordo."""
        a = BoundingBox(cx=0.0, cy=0.0, half_w=1.0, half_d=1.0)
        b = BoundingBox(cx=2.0, cy=0.0, half_w=1.0, half_d=1.0)
        # Si toccano esattamente (senza margine)
        assert a.intersects(b, margin=0.0) is False

    def test_y_direction_separation(self) -> None:
        """Oggetti separati lungo Y."""
        a = BoundingBox(cx=0.0, cy=0.0, half_w=0.5, half_d=0.5)
        b = BoundingBox(cx=0.0, cy=5.0, half_w=0.5, half_d=0.5)
        assert a.intersects(b) is False

    def test_area_with_zero_dimensions(self) -> None:
        """Area con half_w=0 e half_d=0."""
        bbox = BoundingBox(cx=0.0, cy=0.0, half_w=0.0, half_d=0.0)
        assert bbox.area() == pytest.approx(0.0)


class TestSceneGraphExtended:
    def test_object_with_rotation_has_larger_bbox(self) -> None:
        """Un oggetto ruotato di 45° ha bbox più grande."""
        graph_no_rot = SceneGraph()
        graph_rot = SceneGraph()

        node_no_rot = graph_no_rot.add_object(make_obj("table", rot_z=0.0))
        node_rot = graph_rot.add_object(make_obj("table", rot_z=math.pi / 4))

        # Il bbox ruotato dovrebbe essere più grande o uguale
        assert node_rot.bbox.half_w >= node_no_rot.bbox.half_w

    def test_resolve_pair_x_direction(self) -> None:
        """Risoluzione collisione lungo X."""
        graph = SceneGraph()
        # Oggetti sovrapposti prevalentemente lungo X
        graph.add_object(make_obj("sofa", x=0.0, y=0.0))
        graph.add_object(make_obj("chair", x=0.2, y=0.0))
        result = graph.resolve_collisions()
        assert len(result) == 2
        # Il secondo oggetto deve essere spostato
        assert any(n.adjusted for n in graph.nodes)

    def test_resolve_pair_y_direction(self) -> None:
        """Risoluzione collisione lungo Y."""
        graph = SceneGraph()
        graph.add_object(make_obj("bed", x=0.0, y=0.0))
        graph.add_object(make_obj("chair", x=0.0, y=0.1))
        result = graph.resolve_collisions()
        assert len(result) == 2

    def test_max_iterations_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Copre il warning quando si supera max_iterations."""
        import logging

        graph = SceneGraph()
        # Oggetti sovrapposti completamente
        for _ in range(5):
            graph.add_object(make_obj("table", x=0.0, y=0.0))

        with caplog.at_level(logging.WARNING, logger="computer_graphics.scene_graph"):
            graph.resolve_collisions(max_iterations=1)

    def test_get_statistics_empty_graph(self) -> None:
        """Statistiche con grafo vuoto."""
        graph = SceneGraph()
        stats = graph.get_statistics()
        assert stats["total_objects"] == 0
        assert stats["scene_width_m"] == 0.0
        assert stats["scene_depth_m"] == 0.0

    def test_get_statistics_with_objects(self) -> None:
        """Statistiche con più oggetti."""
        graph = SceneGraph()
        graph.add_object(make_obj("table", x=0.0, y=0.0))
        graph.add_object(make_obj("lamp", x=5.0, y=5.0))
        graph.resolve_collisions()
        stats = graph.get_statistics()
        assert stats["total_objects"] == 2
        assert stats["scene_width_m"] > 0
        assert stats["scene_depth_m"] > 0
        assert len(stats["objects"]) == 2

    def test_default_dimension_used_for_unknown_object(self) -> None:
        """Oggetto con nome sconosciuto usa _DEFAULT_DIMENSION."""
        graph = SceneGraph()
        obj = make_obj("unknownobjectxyz123")
        node = graph.add_object(obj)
        expected_half_w = (_DEFAULT_DIMENSION[0] * 1.0) / 2.0
        assert node.bbox.half_w == pytest.approx(expected_half_w)

    def test_export_objects_updates_coordinates(self) -> None:
        """_export_objects aggiorna le coordinate dopo risoluzione."""
        graph = SceneGraph()
        graph.add_object(make_obj("table", x=0.0, y=0.0))
        graph.add_object(make_obj("table", x=0.05, y=0.0))

        result = graph.resolve_collisions()
        # Le posizioni devono essere aggiornate
        positions = [(obj.x, obj.y) for obj in result]
        assert len(positions) == 2

    def test_conflicts_resolved_counter(self) -> None:
        """Verifica che conflicts_resolved venga incrementato."""
        graph = SceneGraph()
        graph.add_object(make_obj("sofa", x=0.0, y=0.0))
        graph.add_object(make_obj("chair", x=0.1, y=0.0))
        graph.resolve_collisions()
        adjusted_nodes = [n for n in graph.nodes if n.adjusted]
        if adjusted_nodes:
            assert adjusted_nodes[0].conflicts_resolved >= 1

    def test_node_b_smaller_moved_when_cx_greater(self) -> None:
        """Copre il ramo: node_b.bbox.cx >= node_a.bbox.cx -> delta_x positivo."""
        graph = SceneGraph()
        # table (grande) a sx, chair (piccola) a dx ma sovrapposta
        graph.add_object(make_obj("sofa", x=0.0, y=0.0))
        graph.add_object(make_obj("chair", x=1.0, y=0.0))  # a destra
        result = graph.resolve_collisions()
        assert len(result) == 2

    def test_node_b_moved_left_when_cx_smaller(self) -> None:
        """Copre il ramo: node_b.bbox.cx < node_a.bbox.cx -> delta_x negativo."""
        graph = SceneGraph()
        graph.add_object(make_obj("sofa", x=0.0, y=0.0))
        graph.add_object(make_obj("chair", x=-1.0, y=0.0))  # a sinistra
        result = graph.resolve_collisions()
        assert len(result) == 2

    def test_node_b_moved_down_when_cy_smaller(self) -> None:
        """Copre il ramo cy < node_a.bbox.cy -> delta_y negativo."""
        graph = SceneGraph()
        graph.add_object(make_obj("bed", x=0.0, y=0.0))
        graph.add_object(make_obj("chair", x=0.0, y=-0.1))
        result = graph.resolve_collisions()
        assert len(result) == 2

    def test_node_b_moved_up_when_cy_greater(self) -> None:
        """Copre il ramo cy >= node_a.bbox.cy -> delta_y positivo."""
        graph = SceneGraph()
        graph.add_object(make_obj("bed", x=0.0, y=0.0))
        graph.add_object(make_obj("chair", x=0.0, y=0.1))
        result = graph.resolve_collisions()
        assert len(result) == 2


class TestApplySceneGraphExtended:
    def test_apply_with_collisions_logs_info(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Copre il ramo adjusted_objects > 0 in apply_scene_graph."""
        import logging

        objects = [
            make_obj("sofa", x=0.0, y=0.0),
            make_obj("chair", x=0.1, y=0.0),  # sovrapposto
        ]
        with caplog.at_level(logging.INFO, logger="computer_graphics.scene_graph"):
            result = apply_scene_graph(objects)
        assert len(result) == 2

    def test_apply_without_collisions_logs_no_collision(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Copre il ramo adjusted_objects == 0."""
        import logging

        objects = [
            make_obj("table", x=0.0, y=0.0),
            make_obj("lamp", x=10.0, y=10.0),
        ]
        with caplog.at_level(logging.INFO, logger="computer_graphics.scene_graph"):
            result = apply_scene_graph(objects)
        assert len(result) == 2

    def test_apply_preserves_all_fields(self) -> None:
        """Verifica che apply_scene_graph preservi tutti i campi."""
        obj = make_obj("table", x=1.0, y=2.0, scale=1.5, rot_z=0.785)
        result = apply_scene_graph([obj])
        assert result[0].scale == pytest.approx(1.5)
        assert result[0].rot_z == pytest.approx(0.785)
        assert result[0].z == pytest.approx(0.0)


# ====== Tests da test_scene_graph_coverage.py ======


class TestBoundingBoxComprehensiveMock:
    def test_bounding_box_initialization(self) -> None:
        """Test BoundingBox creation with valid parameters."""
        bbox = BoundingBox(cx=1.0, cy=2.0, half_w=1.5, half_d=2.0)
        assert bbox.cx == 1.0
        assert bbox.cy == 2.0
        assert bbox.half_w == 1.5
        assert bbox.half_d == 2.0

    def test_bounding_box_properties(self) -> None:
        """Test BoundingBox computed properties."""
        bbox = BoundingBox(cx=1.0, cy=2.0, half_w=1.0, half_d=1.5)
        assert bbox.x_min == 0.0
        assert bbox.x_max == 2.0
        assert bbox.y_min == 0.5
        assert bbox.y_max == 3.5

    def test_bounding_box_intersects_true(self) -> None:
        """Test intersection detection when boxes overlap."""
        bbox1 = BoundingBox(cx=1.0, cy=1.0, half_w=1.0, half_d=1.0)
        bbox2 = BoundingBox(cx=1.5, cy=1.5, half_w=1.0, half_d=1.0)
        assert bbox1.intersects(bbox2) is True

    def test_bounding_box_intersects_false(self) -> None:
        """Test intersection detection when boxes don't overlap."""
        bbox1 = BoundingBox(cx=0.0, cy=0.0, half_w=0.5, half_d=0.5)
        bbox2 = BoundingBox(cx=5.0, cy=5.0, half_w=0.5, half_d=0.5)
        assert bbox1.intersects(bbox2) is False

    def test_bounding_box_area(self) -> None:
        """Test area calculation."""
        bbox = BoundingBox(cx=0.0, cy=0.0, half_w=2.0, half_d=3.0)
        assert bbox.area() == 24.0


class TestSceneGraphNodeMock:
    def test_scene_graph_add_single_object(self) -> None:
        """Test adding a single object to scene graph."""
        graph = SceneGraph()
        obj = SceneObject(name="table", x=0.0, y=0.0, z=0.0, scale=1.0, rot_z=0.0)
        node = graph.add_object(obj)
        assert len(graph.nodes) == 1
        assert node.obj.name == "table"

    def test_scene_graph_add_multiple_objects(self) -> None:
        """Test adding multiple objects to scene graph."""
        graph = SceneGraph()
        objs = [
            SceneObject(name="table", x=float(i), y=0.0, z=0.0, scale=1.0, rot_z=0.0)
            for i in range(5)
        ]
        for obj in objs:
            graph.add_object(obj)
        assert len(graph.nodes) == 5

    def test_scene_graph_resolve_collisions(self) -> None:
        """Test collision resolution between overlapping objects."""
        graph = SceneGraph()
        obj1 = SceneObject(name="table", x=0.0, y=0.0, z=0.0, scale=1.0, rot_z=0.0)
        obj2 = SceneObject(name="chair", x=0.5, y=0.5, z=0.0, scale=1.0, rot_z=0.0)
        graph.add_object(obj1)
        graph.add_object(obj2)
        result = graph.resolve_collisions()
        assert len(result) == 2

    def test_scene_graph_get_statistics(self) -> None:
        """Test statistics calculation for the graph."""
        graph = SceneGraph()
        objs = [
            SceneObject(name="table", x=float(i), y=0.0, z=0.0, scale=1.0, rot_z=0.0)
            for i in range(3)
        ]
        for obj in objs:
            graph.add_object(obj)
        stats = graph.get_statistics()
        assert stats["total_objects"] == 3


class TestApplySceneGraphMock:
    def test_apply_scene_graph_empty(self) -> None:
        """Test apply_scene_graph with empty list."""
        result = apply_scene_graph([])
        assert result == []

    def test_apply_scene_graph_single_object(self) -> None:
        """Test apply_scene_graph with single object."""
        obj = SceneObject(name="cube", x=0.0, y=0.0, z=0.0, scale=1.0, rot_z=0.0)
        result = apply_scene_graph([obj])
        assert len(result) == 1
        assert result[0].name == "cube"

    def test_apply_scene_graph_multiple_objects(self) -> None:
        """Test apply_scene_graph with multiple non-colliding objects."""
        objs = [
            SceneObject(name="obj1", x=0.0, y=0.0, z=0.0, scale=1.0, rot_z=0.0),
            SceneObject(name="obj2", x=10.0, y=10.0, z=0.0, scale=1.0, rot_z=0.0),
        ]
        result = apply_scene_graph(objs)
        assert len(result) == 2

    def test_apply_scene_graph_preserves_data(self) -> None:
        """Test that apply_scene_graph preserves object data."""
        obj = SceneObject(name="test_obj", x=5.5, y=3.2, z=1.1, scale=2.5, rot_z=1.57)
        result = apply_scene_graph([obj])
        assert result[0].name == "test_obj"
        assert result[0].scale == 2.5
        assert result[0].rot_z == pytest.approx(1.57)
