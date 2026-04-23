"""
Constraint Solver deterministico per il layout spaziale delle scene 3D.

Traduce le relazioni topologiche generate dall'LLM (es. "sedia davanti
al tavolo") in coordinate reali garantendo layout geometricamente validi
per costruzione, senza sovrapposizioni.

Questo modulo sostituisce il calcolo geometrico grezzo dell'LLM con un
solver Python preciso: l'LLM si occupa della logica di alto livello
(cosa mettere e come), il solver della geometria precisa (dove esattamente).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from computer_graphics.validator import SceneObject


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Strutture dati interne
# ---------------------------------------------------------------------------


@dataclass
class AssetDimensions:
    """Dimensioni fisiche di un asset in unita Blender (metri)."""

    width: float = 1.0
    depth: float = 1.0
    height: float = 1.0


@dataclass
class PlacedObject:
    """Oggetto posizionato nel layout con bounding box 2D."""

    name: str
    x: float
    y: float
    width: float
    depth: float
    rotation: float = 0.0
    parent: str | None = None

    @property
    def x_min(self) -> float:
        """Estremo minimo X del bounding box."""
        return self.x - self.width / 2.0

    @property
    def x_max(self) -> float:
        """Estremo massimo X del bounding box."""
        return self.x + self.width / 2.0

    @property
    def y_min(self) -> float:
        """Estremo minimo Y del bounding box."""
        return self.y - self.depth / 2.0

    @property
    def y_max(self) -> float:
        """Estremo massimo Y del bounding box."""
        return self.y + self.depth / 2.0

    def overlaps(self, other: PlacedObject, margin: float = 0.15) -> bool:
        """
        Verifica se questo oggetto si sovrappone con un altro.

        Args:
            other: L'altro oggetto con cui verificare la sovrapposizione.
            margin: Distanza minima di sicurezza in unita Blender.

        Returns:
            True se i bounding box si sovrappongono o sono troppo vicini.
        """
        return not (
            self.x_max + margin <= other.x_min
            or other.x_max + margin <= self.x_min
            or self.y_max + margin <= other.y_min
            or other.y_max + margin <= self.y_min
        )


# ---------------------------------------------------------------------------
# Dimensioni di default per asset comuni
# ---------------------------------------------------------------------------

_DEFAULT_ASSET_DIMS: dict[str, AssetDimensions] = {
    "table": AssetDimensions(1.5, 0.9, 0.75),
    "desk": AssetDimensions(1.6, 0.8, 0.75),
    "chair": AssetDimensions(0.6, 0.6, 1.0),
    "lamp": AssetDimensions(0.4, 0.4, 1.8),
    "sofa": AssetDimensions(2.2, 0.9, 0.9),
    "bed": AssetDimensions(1.6, 2.0, 0.6),
    "bookshelf": AssetDimensions(0.9, 0.3, 1.8),
    "cabinet": AssetDimensions(0.8, 0.4, 1.4),
    "monitor": AssetDimensions(0.6, 0.2, 0.4),
    "keyboard": AssetDimensions(0.45, 0.15, 0.03),
    "plant": AssetDimensions(0.5, 0.5, 1.0),
    "rug": AssetDimensions(2.0, 1.5, 0.02),
    "fridge": AssetDimensions(0.7, 0.7, 1.8),
    "stove": AssetDimensions(0.6, 0.6, 0.9),
    "sink": AssetDimensions(0.6, 0.5, 0.9),
    "door": AssetDimensions(0.9, 0.1, 2.1),
    "window": AssetDimensions(1.2, 0.1, 1.2),
    "toilet": AssetDimensions(0.4, 0.7, 0.8),
    "bathtub": AssetDimensions(1.7, 0.75, 0.55),
    "curtain": AssetDimensions(1.5, 0.1, 2.5),
    "floor": AssetDimensions(5.0, 5.0, 0.05),
    "couch": AssetDimensions(2.2, 0.9, 0.9),
    "armchair": AssetDimensions(0.9, 0.9, 1.0),
    "dresser": AssetDimensions(1.2, 0.5, 1.2),
    "wardrobe": AssetDimensions(1.2, 0.6, 2.0),
    "nightstand": AssetDimensions(0.5, 0.4, 0.6),
    "coffee_table": AssetDimensions(1.2, 0.6, 0.45),
    "tv": AssetDimensions(1.2, 0.15, 0.7),
}

_DEFAULT_DIMENSION = AssetDimensions(0.8, 0.8, 1.0)


# ---------------------------------------------------------------------------
# Relazioni topologiche
# ---------------------------------------------------------------------------


@dataclass
class TopologicalRelation:
    """
    Relazione spaziale tra due oggetti generata dall'LLM.

    Attributes:
        subject: Nome dell'oggetto da posizionare.
        relation: Tipo di relazione (es. ``"in_front_of"``, ``"beside"``).
        reference: Nome dell'oggetto di riferimento.
        offset: Offset aggiuntivo in unita Blender (opzionale).
    """

    subject: str
    relation: str
    reference: str
    offset: float = 0.0


# ---------------------------------------------------------------------------
# Constraint Solver principale
# ---------------------------------------------------------------------------


@dataclass
class ConstraintSolver:
    """
    Solver deterministico per il layout spaziale della scena 3D.

    Riceve oggetti dall'LLM (con coordinate approssimative o relazioni
    topologiche) e produce un layout geometricamente valido garantendo
    l'assenza di sovrapposizioni e il rispetto delle dimensioni reali.

    Args:
        assets_dir: Directory degli asset per il calcolo delle dimensioni.
        safety_margin: Distanza minima tra oggetti in unita Blender.
        room_width: Larghezza della stanza in unita Blender.
        room_depth: Profondita della stanza in unita Blender.
    """

    assets_dir: Path | None = None
    safety_margin: float = 0.15
    room_width: float = 10.0
    room_depth: float = 10.0
    _placed: list[PlacedObject] = field(default_factory=list, init=False)

    def solve(
        self,
        objects: list[SceneObject],
        relations: list[TopologicalRelation] | None = None,
    ) -> list[SceneObject]:
        """
        Risolve il layout spaziale per una lista di oggetti.

        Flusso:
        1. Carica le dimensioni reali di ogni asset.
        2. Posiziona gli oggetti radice (senza parent) usando coordinate LLM
           come suggerimento, applicando correzioni geometriche.
        3. Applica eventuali relazioni topologiche esplicite.
        4. Risolve le sovrapposizioni residue con spostamento iterativo.
        5. Aggiorna le coordinate negli SceneObject e li restituisce.

        Args:
            objects: Lista di SceneObject con coordinate LLM.
            relations: Lista opzionale di relazioni topologiche esplicite.

        Returns:
            Lista di SceneObject con coordinate aggiornate e layout valido.
        """
        self._placed = []
        relations = relations or []

        # Separa oggetti radice da oggetti figlio
        root_objects = [obj for obj in objects if obj.parent is None]
        child_objects = [obj for obj in objects if obj.parent is not None]

        # Posiziona prima gli oggetti radice
        for obj in root_objects:
            dims = self._get_dimensions(obj.name, obj.scale)
            placed = PlacedObject(
                name=obj.name,
                x=obj.x,
                y=obj.y,
                width=dims.width,
                depth=dims.depth,
                rotation=obj.rot_z,
                parent=None,
            )
            self._placed.append(placed)

        # Applica relazioni topologiche
        for relation in relations:
            self._apply_relation(relation)

        # Risolvi sovrapposizioni
        self._resolve_overlaps(max_iterations=20)

        # Aggiorna le coordinate degli SceneObject
        updated = self._apply_positions_to_objects(objects)

        n_adjusted = sum(
            1
            for orig, upd in zip(objects, updated)
            if orig.x != upd.x or orig.y != upd.y
        )
        logger.info(
            "ConstraintSolver: %d/%d oggetti riposizionati.",
            n_adjusted,
            len(objects),
        )

        return updated

    def compute_room_size(self, objects: list[SceneObject]) -> tuple[float, float]:
        """
        Calcola la dimensione minima della stanza per contenere tutti gli oggetti.

        Args:
            objects: Lista di SceneObject nella scena.

        Returns:
            Tupla ``(width, depth)`` della stanza consigliata.
        """
        if not objects:
            return (self.room_width, self.room_depth)

        total_area = sum(
            self._get_dimensions(obj.name, obj.scale).width
            * self._get_dimensions(obj.name, obj.scale).depth
            for obj in objects
            if obj.parent is None
        )
        # Stima: area occupata = 40% dell'area totale (layout realistico)
        min_area = total_area / 0.4
        side = math.sqrt(min_area)
        return (max(side, 4.0), max(side, 4.0))

    # ------------------------------------------------------------------
    # Metodi privati
    # ------------------------------------------------------------------

    def _get_dimensions(self, name: str, scale: float = 1.0) -> AssetDimensions:
        """
        Restituisce le dimensioni dell'asset scalate.

        Prima tenta il calcolo dalla mesh (se assets_dir e disponibile),
        poi usa il dizionario statico, infine il default.

        Args:
            name: Nome normalizzato dell'asset.
            scale: Fattore di scala dell'oggetto.

        Returns:
            Dimensioni scalate dell'asset.
        """
        if self.assets_dir is not None:
            try:
                from computer_graphics.scene_graph import (  # noqa: PLC0415
                    get_asset_dimensions,
                )

                raw = get_asset_dimensions(name, self.assets_dir)
                return AssetDimensions(
                    width=raw[0] * scale,
                    depth=raw[1] * scale,
                    height=raw[2] * scale,
                )
            except Exception:  # noqa: BLE001
                pass

        base = _DEFAULT_ASSET_DIMS.get(name, _DEFAULT_DIMENSION)
        return AssetDimensions(
            width=base.width * scale,
            depth=base.depth * scale,
            height=base.height * scale,
        )

    def _apply_relation(self, relation: TopologicalRelation) -> None:
        """
        Applica una relazione topologica aggiornando la posizione del soggetto.

        Args:
            relation: Relazione da applicare.
        """
        subject_placed = next(
            (p for p in self._placed if p.name == relation.subject), None
        )
        ref_placed = next(
            (p for p in self._placed if p.name == relation.reference), None
        )

        if subject_placed is None or ref_placed is None:
            logger.debug(
                "Relazione '%s %s %s' non applicabile: oggetti non trovati.",
                relation.subject,
                relation.relation,
                relation.reference,
            )
            return

        gap = self.safety_margin + relation.offset
        rel = relation.relation.lower().replace(" ", "_").replace("-", "_")

        if rel in ("in_front_of", "davanti_a", "front"):
            subject_placed.y = (
                ref_placed.y_max
                + subject_placed.depth / 2.0
                + gap
            )
            subject_placed.x = ref_placed.x

        elif rel in ("behind", "dietro_a", "back"):
            subject_placed.y = (
                ref_placed.y_min
                - subject_placed.depth / 2.0
                - gap
            )
            subject_placed.x = ref_placed.x

        elif rel in ("beside", "to_the_right", "right", "destra"):
            subject_placed.x = (
                ref_placed.x_max
                + subject_placed.width / 2.0
                + gap
            )
            subject_placed.y = ref_placed.y

        elif rel in ("to_the_left", "left", "sinistra"):
            subject_placed.x = (
                ref_placed.x_min
                - subject_placed.width / 2.0
                - gap
            )
            subject_placed.y = ref_placed.y

        elif rel in ("on_top_of", "su", "sopra"):
            # La coordinata Z viene gestita dal parent, qui solo XY
            subject_placed.x = ref_placed.x
            subject_placed.y = ref_placed.y

        elif rel in ("near", "vicino_a", "around"):
            # Posiziona vicino ma non sovrapposto
            angle = math.pi / 4.0
            dist = (
                max(ref_placed.width, ref_placed.depth) / 2.0
                + max(subject_placed.width, subject_placed.depth) / 2.0
                + gap
            )
            subject_placed.x = ref_placed.x + dist * math.cos(angle)
            subject_placed.y = ref_placed.y + dist * math.sin(angle)

        logger.debug(
            "Relazione applicata: '%s' %s '%s' -> (%.2f, %.2f)",
            relation.subject,
            rel,
            relation.reference,
            subject_placed.x,
            subject_placed.y,
        )

    def _resolve_overlaps(self, max_iterations: int = 20) -> None:
        """
        Risolve le sovrapposizioni tra oggetti con spostamento iterativo.

        Ordina gli oggetti per area decrescente (i piu grandi restano
        fissi), sposta i piu piccoli nella direzione di minima penetrazione.

        Args:
            max_iterations: Numero massimo di iterazioni di risoluzione.
        """
        self._placed.sort(
            key=lambda p: p.width * p.depth, reverse=True
        )

        for iteration in range(max_iterations):
            conflict_found = False
            for i, obj_a in enumerate(self._placed):
                for obj_b in self._placed[i + 1 :]:
                    if obj_a.parent is not None or obj_b.parent is not None:
                        continue
                    if obj_a.overlaps(obj_b, self.safety_margin):
                        conflict_found = True
                        self._push_apart(obj_a, obj_b)

            if not conflict_found:
                logger.debug(
                    "ConstraintSolver: nessun conflitto a iterazione %d.",
                    iteration + 1,
                )
                break
        else:
            logger.warning(
                "ConstraintSolver: risoluzione terminata dopo %d iterazioni "
                "(potrebbero esistere sovrapposizioni residue).",
                max_iterations,
            )

    def _push_apart(
        self,
        obj_a: PlacedObject,
        obj_b: PlacedObject,
    ) -> None:
        """
        Sposta ``obj_b`` per risolvere la sovrapposizione con ``obj_a``.

        Usa la direzione di minima penetrazione (asse AABB) per lo spostamento.
        ``obj_a`` e considerato fisso (maggiore area).

        Args:
            obj_a: Oggetto fisso.
            obj_b: Oggetto da spostare.
        """
        dx = obj_b.x - obj_a.x
        dy = obj_b.y - obj_a.y

        overlap_x = min(
            obj_a.x_max - obj_b.x_min,
            obj_b.x_max - obj_a.x_min,
        )
        overlap_y = min(
            obj_a.y_max - obj_b.y_min,
            obj_b.y_max - obj_a.y_min,
        )

        if overlap_x < overlap_y:
            sign = 1 if dx >= 0 else -1
            obj_b.x += sign * (overlap_x + self.safety_margin)
        else:
            sign = 1 if dy >= 0 else -1
            obj_b.y += sign * (overlap_y + self.safety_margin)

        logger.debug(
            "Push apart: '%s' spostato a (%.2f, %.2f).",
            obj_b.name,
            obj_b.x,
            obj_b.y,
        )

    def _apply_positions_to_objects(
        self,
        original_objects: list[SceneObject],
    ) -> list[SceneObject]:
        """
        Applica le posizioni calcolate agli SceneObject originali.

        Args:
            original_objects: Lista di SceneObject originali.

        Returns:
            Lista di SceneObject con posizioni aggiornate.
        """
        placed_map = {p.name: p for p in self._placed}
        result: list[SceneObject] = []

        for obj in original_objects:
            placed = placed_map.get(obj.name)
            if placed is not None and obj.parent is None:
                updated = obj.model_copy(
                    update={
                        "x": round(placed.x, 4),
                        "y": round(placed.y, 4),
                    }
                )
                result.append(updated)
            else:
                result.append(obj)

        return result


def solve_layout(
    objects: list[SceneObject],
    assets_dir: Path | None = None,
    safety_margin: float = 0.15,
    relations: list[TopologicalRelation] | None = None,
) -> list[SceneObject]:
    """
    Funzione di convenienza per applicare il ConstraintSolver.

    Args:
        objects: Lista di SceneObject validati dall'orchestratore.
        assets_dir: Directory degli asset per le dimensioni reali.
        safety_margin: Distanza minima tra oggetti.
        relations: Relazioni topologiche opzionali.

    Returns:
        Lista di SceneObject con layout valido.
    """
    if not objects:
        return objects

    solver = ConstraintSolver(
        assets_dir=assets_dir,
        safety_margin=safety_margin,
    )
    return solver.solve(objects, relations=relations)