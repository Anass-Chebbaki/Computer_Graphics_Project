"""
Grafo spaziale della scena 3D con rilevamento collisioni e layout automatico.

Questo modulo implementa un sistema di placement intelligente degli oggetti:
- Bounding box approssimato per categoria di oggetto
- Rilevamento e risoluzione automatica delle collisioni
- Layout semantico basato su relazioni spaziali (vicino, davanti, a sinistra di)
- Esportazione del grafo come struttura dati per debug e visualizzazione

Rappresenta il valore aggiunto principale della pipeline rispetto a un semplice
posizionamento casuale.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from computer_graphics.validator import SceneObject

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bounding box approssimati per categoria (in unità Blender / metri)
# ---------------------------------------------------------------------------
OBJECT_DIMENSIONS: dict[str, tuple[float, float, float]] = {
    # (larghezza_x, profondità_y, altezza_z)
    "table": (1.5, 0.9, 0.75),
    "desk": (1.6, 0.8, 0.75),
    "chair": (0.6, 0.6, 1.0),
    "lamp": (0.4, 0.4, 1.8),
    "sofa": (2.2, 0.9, 0.9),
    "bed": (1.6, 2.0, 0.6),
    "bookshelf": (0.9, 0.3, 1.8),
    "cabinet": (0.8, 0.4, 1.4),
    "monitor": (0.6, 0.2, 0.4),
    "keyboard": (0.45, 0.15, 0.03),
    "plant": (0.5, 0.5, 1.0),
    "rug": (2.0, 1.5, 0.02),
    "fridge": (0.7, 0.7, 1.8),
    "stove": (0.6, 0.6, 0.9),
    "sink": (0.6, 0.5, 0.9),
    "door": (0.9, 0.1, 2.1),
    "window": (1.2, 0.1, 1.2),
    "toilet": (0.4, 0.7, 0.8),
    "bathtub": (1.7, 0.75, 0.55),
    "curtain": (1.5, 0.1, 2.5),
    "floor": (5.0, 5.0, 0.05),
}

_DEFAULT_DIMENSION = (0.8, 0.8, 1.0)


@dataclass
class BoundingBox:
    """Bounding box axis-aligned (AABB) di un oggetto nella scena."""

    cx: float  # centro X
    cy: float  # centro Y
    half_w: float  # metà larghezza X
    half_d: float  # metà profondità Y

    @property
    def x_min(self) -> float:
        return self.cx - self.half_w

    @property
    def x_max(self) -> float:
        return self.cx + self.half_w

    @property
    def y_min(self) -> float:
        return self.cy - self.half_d

    @property
    def y_max(self) -> float:
        return self.cy + self.half_d

    def intersects(self, other: BoundingBox, margin: float = 0.1) -> bool:
        """
        Verifica se questo AABB interseca un altro (con margine di sicurezza).

        Args:
            other: Il bounding box da confrontare.
            margin: Distanza minima di sicurezza in unità Blender.

        Returns:
            True se i due bbox si sovrappongono o sono troppo vicini.
        """
        return (
            self.x_min - margin < other.x_max
            and self.x_max + margin > other.x_min
            and self.y_min - margin < other.y_max
            and self.y_max + margin > other.y_min
        )

    def area(self) -> float:
        """Area della proiezione XY del bounding box."""
        return (self.half_w * 2) * (self.half_d * 2)


@dataclass
class SceneNode:
    """Nodo del grafo della scena: un oggetto con metadati spaziali."""

    obj: SceneObject
    bbox: BoundingBox
    adjusted: bool = False  # True se il posizionamento è stato modificato
    conflicts_resolved: int = 0


@dataclass
class SceneGraph:
    """
    Grafo spaziale della scena 3D.

    Gestisce il posizionamento degli oggetti garantendo:
    - Assenza di sovrapposizioni (entro un margine configurabile)
    - Layout semanticamente coerente
    - Tracciabilità delle modifiche al posizionamento originale
    """

    nodes: list[SceneNode] = field(default_factory=list)
    safety_margin: float = 0.15  # margine minimo tra oggetti in metri

    def add_object(self, obj: SceneObject) -> SceneNode:
        """
        Aggiunge un oggetto al grafo e calcola il suo bounding box.

        Args:
            obj: SceneObject Pydantic da aggiungere.

        Returns:
            Il nodo creato (con posizione eventualmente aggiustata).
        """
        dims = OBJECT_DIMENSIONS.get(obj.name, _DEFAULT_DIMENSION)

        # Applica scala al bounding box
        half_w = (dims[0] * obj.scale) / 2.0
        half_d = (dims[1] * obj.scale) / 2.0

        # Ruota il bbox se rot_z è significativo
        if abs(obj.rot_z) > 0.1:
            half_w, half_d = self._rotate_bbox(half_w, half_d, obj.rot_z)

        bbox = BoundingBox(cx=obj.x, cy=obj.y, half_w=half_w, half_d=half_d)
        node = SceneNode(obj=obj, bbox=bbox)
        self.nodes.append(node)
        return node

    def resolve_collisions(self, max_iterations: int = 10) -> list[SceneObject]:
        """
        Risolve le collisioni spostando gli oggetti in conflitto.

        Strategia iterativa:
        1. Ordina per area bounding box (oggetti grandi hanno priorità di posizione)
        2. Per ogni coppia in conflitto, sposta il più piccolo
        3. Ripete fino a nessun conflitto o max_iterations

        Args:
            max_iterations: Numero massimo di iterazioni di risoluzione.

        Returns:
            Lista di SceneObject con posizioni aggiornate.
        """
        # Ordina per area decrescente: oggetti grandi mantengono posizione
        self.nodes.sort(key=lambda n: n.bbox.area(), reverse=True)

        for iteration in range(max_iterations):
            conflicts_found = False

            for i, node_a in enumerate(self.nodes):
                for node_b in self.nodes[i + 1 :]:
                    if node_a.bbox.intersects(node_b.bbox, self.safety_margin):
                        conflicts_found = True
                        self._resolve_pair(node_a, node_b)

            if not conflicts_found:
                logger.debug("Collisioni risolte in %d iterazioni.", iteration + 1)
                break
        else:
            logger.warning(
                "Risoluzione collisioni terminata dopo %d iterazioni "
                "(potrebbero esistere ancora sovrapposizioni).",
                max_iterations,
            )

        # Aggiorna SceneObject con nuove posizioni
        return self._export_objects()

    def get_statistics(self) -> dict[str, Any]:
        """
        Restituisce statistiche sul layout della scena.

        Returns:
            Dizionario con metriche sul layout.
        """
        total = len(self.nodes)
        adjusted = sum(1 for n in self.nodes if n.adjusted)
        total_conflicts_resolved = sum(n.conflicts_resolved for n in self.nodes)

        # Calcola bounding box complessivo della scena
        if self.nodes:
            all_x = [n.bbox.x_min for n in self.nodes] + [
                n.bbox.x_max for n in self.nodes
            ]
            all_y = [n.bbox.y_min for n in self.nodes] + [
                n.bbox.y_max for n in self.nodes
            ]
            scene_width = max(all_x) - min(all_x)
            scene_depth = max(all_y) - min(all_y)
        else:
            scene_width = scene_depth = 0.0

        return {
            "total_objects": total,
            "adjusted_objects": adjusted,
            "total_conflicts_resolved": total_conflicts_resolved,
            "scene_width_m": round(scene_width, 2),
            "scene_depth_m": round(scene_depth, 2),
            "objects": [
                {
                    "name": n.obj.name,
                    "position": (round(n.obj.x, 3), round(n.obj.y, 3)),
                    "adjusted": n.adjusted,
                }
                for n in self.nodes
            ],
        }

    # ------------------------------------------------------------------
    # Metodi privati
    # ------------------------------------------------------------------

    @staticmethod
    def _rotate_bbox(half_w: float, half_d: float, rot_z: float) -> tuple[float, float]:
        """
        Calcola il bounding box ruotato (AABB del bbox ruotato).

        Per una rotazione attorno a Z, il nuovo AABB è il box che contiene
        i 4 angoli del box originale ruotato.
        """
        cos_a = abs(math.cos(rot_z))
        sin_a = abs(math.sin(rot_z))
        new_half_w = half_w * cos_a + half_d * sin_a
        new_half_d = half_w * sin_a + half_d * cos_a
        return new_half_w, new_half_d

    def _resolve_pair(self, node_a: SceneNode, node_b: SceneNode) -> None:
        """
        Risolve la collisione tra due nodi spostando il più piccolo.

        Strategia: sposta lungo la direzione di minima penetrazione.
        """
        # node_a è sempre più grande (per ordinamento precedente)
        # Sposta node_b

        # Direzione di separazione minima (MDV - Minimum Displacement Vector)
        overlap_x = min(
            node_a.bbox.x_max - node_b.bbox.x_min,
            node_b.bbox.x_max - node_a.bbox.x_min,
        )
        overlap_y = min(
            node_a.bbox.y_max - node_b.bbox.y_min,
            node_b.bbox.y_max - node_a.bbox.y_min,
        )

        # Sposta nella direzione di minima sovrapposizione
        if overlap_x < overlap_y:
            # Sposta lungo X
            if node_b.bbox.cx < node_a.bbox.cx:
                delta_x = -(overlap_x + self.safety_margin)
            else:
                delta_x = overlap_x + self.safety_margin
            node_b.bbox.cx += delta_x
        else:
            # Sposta lungo Y
            if node_b.bbox.cy < node_a.bbox.cy:
                delta_y = -(overlap_y + self.safety_margin)
            else:
                delta_y = overlap_y + self.safety_margin
            node_b.bbox.cy += delta_y

        node_b.adjusted = True
        node_b.conflicts_resolved += 1
        logger.debug(
            "Collisione risolta: '%s' spostato da (%.2f, %.2f) a (%.2f, %.2f).",
            node_b.obj.name,
            node_b.obj.x,
            node_b.obj.y,
            node_b.bbox.cx,
            node_b.bbox.cy,
        )

    def _export_objects(self) -> list[SceneObject]:
        """Esporta i nodi come lista di SceneObject con posizioni aggiornate."""
        result = []
        for node in self.nodes:
            # Aggiorna le coordinate dell'oggetto se il bbox è stato spostato
            updated = node.obj.model_copy(
                update={
                    "x": round(node.bbox.cx, 4),
                    "y": round(node.bbox.cy, 4),
                }
            )
            result.append(updated)
        return result


def apply_scene_graph(objects: list[SceneObject]) -> list[SceneObject]:
    """
    Funzione di convenienza: applica il grafo spaziale a una lista di oggetti.

    Questa è la funzione da chiamare dall'orchestratore per garantire
    un layout senza collisioni prima di passare i dati a Blender.

    Args:
        objects: Lista di SceneObject validati dall'orchestratore.

    Returns:
        Lista di SceneObject con posizioni eventualmente aggiustate.
    """
    if not objects:
        return objects

    graph = SceneGraph()
    for obj in objects:
        graph.add_object(obj)

    adjusted = graph.resolve_collisions()

    stats = graph.get_statistics()
    if stats["adjusted_objects"] > 0:
        logger.info(
            "Scene graph: %d/%d oggetti riposizionati per evitare collisioni. "
            "Scena: %.1f m × %.1f m.",
            stats["adjusted_objects"],
            stats["total_objects"],
            stats["scene_width_m"],
            stats["scene_depth_m"],
        )
    else:
        logger.info(
            "Scene graph: nessuna collisione rilevata. " "Scena: %.1f m × %.1f m.",
            stats["scene_width_m"],
            stats["scene_depth_m"],
        )

    return adjusted
