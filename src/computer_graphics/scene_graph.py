"""
Grafo spaziale della scena 3D con rilevamento collisioni OBB e layout automatico.

Sostituisce AABB con Oriented Bounding Boxes (OBB) per calcoli di intersezione
precisi rispetto all'orientamento rot_z degli oggetti. Le dimensioni degli asset
vengono calcolate dinamicamente dalla geometria dei file .obj/.fbx/.glb invece
di essere lette dal dizionario statico OBJECT_DIMENSIONS.
"""

from __future__ import annotations

import logging
import math
import struct
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from computer_graphics.validator import SceneObject


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dimensioni di fallback (usate solo se il file asset non è disponibile)
# ---------------------------------------------------------------------------
OBJECT_DIMENSIONS: dict[str, tuple[float, float, float]] = {
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

_DEFAULT_DIMENSION: tuple[float, float, float] = (0.8, 0.8, 1.0)

# Cache delle dimensioni calcolate dai file mesh
_mesh_dimensions_cache: dict[str, tuple[float, float, float]] = {}
_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Calcolo dinamico delle dimensioni dalla mesh
# ---------------------------------------------------------------------------


def compute_mesh_dimensions(
    asset_path: Path,
) -> tuple[float, float, float] | None:
    """Calcola le dimensioni (width_x, depth_y, height_z) analizzando i vertici.

    Supporta i formati .obj, .fbx e .glb/.gltf. Restituisce None se il file
    non è supportato o si verifica un errore di parsing.

    Args:
        asset_path: Percorso assoluto al file 3D.

    Returns:
        Tupla (width_x, depth_y, height_z) in unità Blender, oppure None.
    """
    ext = asset_path.suffix.lower()
    try:
        if ext == ".obj":
            return _parse_obj_dimensions(asset_path)
        if ext in (".glb", ".gltf"):
            return _parse_glb_dimensions(asset_path)
        # .fbx è binario proprietario: fallback alle dimensioni statiche
        logger.debug(
            "Formato '%s' non supportato per parsing vertici; uso fallback.", ext
        )
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Errore parsing dimensioni da '%s': %s. Uso fallback.", asset_path, exc
        )
        return None


def _parse_obj_dimensions(
    path: Path,
) -> tuple[float, float, float] | None:
    """Estrae le dimensioni da un file Wavefront OBJ leggendo i vertici 'v'.

    Args:
        path: Percorso al file .obj.

    Returns:
        Tupla (width_x, depth_y, height_z) oppure None se nessun vertice trovato.
    """
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []

    with path.open(encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if not line.startswith("v "):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            xs.append(float(parts[1]))
            ys.append(float(parts[2]))
            zs.append(float(parts[3]))

    if not xs:
        return None

    # OBJ è Y-up: l'altezza è rappresentata dalla coordinata Y.
    # Quando importato in Blender con forward=Y e up=Z, le coordinate
    # mapperanno (X_obj -> X_blender), (Y_obj -> Z_blender), (Z_obj -> -Y_blender).
    # Quindi le dimensioni finali saranno:
    #   width_x = max(xs) - min(xs)
    #   depth_y = max(zs) - min(zs)
    #   height_z = max(ys) - min(ys)
    return (
        max(xs) - min(xs),
        max(zs) - min(zs),
        max(ys) - min(ys),
    )


def _parse_glb_dimensions(
    path: Path,
) -> tuple[float, float, float] | None:
    """Estrae le dimensioni da un file .glb leggendo i min/max degli accessor.

    Legge gli accessor di tipo POSITION dal JSON del chunk 0 del formato
    GLB binario (header 12 byte + chunk JSON).

    Args:
        path: Percorso al file .glb.

    Returns:
        Tupla (width_x, depth_y, height_z) oppure None.
    """
    import json as _json  # noqa: PLC0415

    raw = path.read_bytes()
    if len(raw) < 20:
        return None

    # Leggi header GLB: magic(4) + version(4) + length(4)
    magic = raw[:4]
    if magic != b"glTF":
        return None

    # Iterate through chunks to find JSON chunk
    offset = 12
    gltf = None
    while offset + 8 <= len(raw):
        chunk_len = struct.unpack_from("<I", raw, offset)[0]
        chunk_type = raw[offset + 4 : offset + 8]
        if chunk_type == b"JSON":
            json_bytes = raw[offset + 8 : offset + 8 + chunk_len]
            gltf = _json.loads(json_bytes.decode("utf-8"))
            break
        offset += 8 + chunk_len

    if gltf is None:
        return None

    accessors = gltf.get("accessors", [])
    global_min = [float("inf")] * 3
    global_max = [float("-inf")] * 3
    found = False

    for acc in accessors:
        if acc.get("type") != "VEC3":
            continue
        mn = acc.get("min")
        mx = acc.get("max")
        if mn and mx and len(mn) == 3 and len(mx) == 3:
            for i in range(3):
                global_min[i] = min(global_min[i], mn[i])
                global_max[i] = max(global_max[i], mx[i])
            found = True

    if not found:
        return None

    return (
        global_max[0] - global_min[0],
        global_max[1] - global_min[1],
        global_max[2] - global_min[2],
    )


def get_asset_dimensions(
    name: str,
    assets_dir: Path | None = None,
) -> tuple[float, float, float]:
    """Restituisce le dimensioni dell'asset, calcolandole dalla mesh se possibile.

    Strategia di ricerca:
    1. Cache in memoria per il nome.
    2. Parsing dei vertici dal file .obj / .glb trovato in assets_dir.
    3. Fallback al dizionario statico OBJECT_DIMENSIONS.
    4. Fallback a _DEFAULT_DIMENSION.

    Args:
        name: Nome normalizzato dell'asset (es. ``"table"``).
        assets_dir: Directory in cui cercare i file asset.

    Returns:
        Tupla ``(width_x, depth_y, height_z)`` in unità Blender.
    """
    with _cache_lock:
        if name in _mesh_dimensions_cache:
            return _mesh_dimensions_cache[name]

    if assets_dir is not None:
        for ext in (".obj", ".glb", ".gltf", ".fbx"):
            candidate = assets_dir / f"{name}{ext}"
            if candidate.exists():
                dims = compute_mesh_dimensions(candidate)
                if dims is not None and all(d > 0 for d in dims):
                    logger.debug(
                        "Dimensioni '%s' calcolate da mesh: %.2f x %.2f x %.2f",
                        name,
                        *dims,
                    )
                    with _cache_lock:
                        _mesh_dimensions_cache[name] = dims
                    return dims

    # Fallback statico
    dims = OBJECT_DIMENSIONS.get(name, _DEFAULT_DIMENSION)
    with _cache_lock:
        _mesh_dimensions_cache[name] = dims
    return dims


def clear_mesh_dimensions_cache() -> None:
    """Svuota la cache delle dimensioni mesh (utile per i test)."""
    with _cache_lock:
        _mesh_dimensions_cache.clear()


# ---------------------------------------------------------------------------
# Oriented Bounding Box (OBB) 2-D (proiezione XY)
# ---------------------------------------------------------------------------


@dataclass
class OBB:
    """Oriented Bounding Box 2-D per la proiezione XY della scena.

    Attributes:
        cx: Centro X in unità Blender.
        cy: Centro Y in unità Blender.
        half_w: Metà larghezza lungo l'asse locale X dell'oggetto.
        half_d: Metà profondità lungo l'asse locale Y dell'oggetto.
        angle: Rotazione attorno a Z in radianti (rot_z dell'oggetto).
    """

    cx: float
    cy: float
    half_w: float
    half_d: float
    angle: float = 0.0

    # ------------------------------------------------------------------
    # Proprietà di compatibilità (usate da get_statistics e _resolve_pair)
    # ------------------------------------------------------------------

    @property
    def x_min(self) -> float:
        """Estremo minimo X dell'AABB che contiene l'OBB."""
        return self.cx - self._aabb_half_w()

    @property
    def x_max(self) -> float:
        """Estremo massimo X dell'AABB che contiene l'OBB."""
        return self.cx + self._aabb_half_w()

    @property
    def y_min(self) -> float:
        """Estremo minimo Y dell'AABB che contiene l'OBB."""
        return self.cy - self._aabb_half_d()

    @property
    def y_max(self) -> float:
        """Estremo massimo Y dell'AABB che contiene l'OBB."""
        return self.cy + self._aabb_half_d()

    def area(self) -> float:
        """Area della proiezione XY dell'OBB."""
        return (self.half_w * 2) * (self.half_d * 2)

    # ------------------------------------------------------------------
    # Metodi privati
    # ------------------------------------------------------------------

    def _aabb_half_w(self) -> float:
        cos_a = abs(math.cos(self.angle))
        sin_a = abs(math.sin(self.angle))
        return self.half_w * cos_a + self.half_d * sin_a

    def _aabb_half_d(self) -> float:
        cos_a = abs(math.cos(self.angle))
        sin_a = abs(math.sin(self.angle))
        return self.half_w * sin_a + self.half_d * cos_a

    def _axes(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Restituisce i due assi locali dell'OBB (versori unitari)."""
        cos_a = math.cos(self.angle)
        sin_a = math.sin(self.angle)
        return (cos_a, sin_a), (-sin_a, cos_a)

    def _corners(self) -> list[tuple[float, float]]:
        """Calcola i 4 angoli dell'OBB nello spazio mondo."""
        ax, ay = self._axes()[0]
        bx, by = self._axes()[1]
        return [
            (
                self.cx + self.half_w * ax + self.half_d * bx,
                self.cy + self.half_w * ay + self.half_d * by,
            ),
            (
                self.cx - self.half_w * ax + self.half_d * bx,
                self.cy - self.half_w * ay + self.half_d * by,
            ),
            (
                self.cx - self.half_w * ax - self.half_d * bx,
                self.cy - self.half_w * ay - self.half_d * by,
            ),
            (
                self.cx + self.half_w * ax - self.half_d * bx,
                self.cy + self.half_w * ay - self.half_d * by,
            ),
        ]

    def intersects(self, other: OBB, margin: float = 0.1) -> bool:
        """Verifica intersezione OBB-OBB con il Separating Axis Theorem (SAT).

        Espande entrambi i box del ``margin`` prima del test.

        Args:
            other: L'OBB con cui testare l'intersezione.
            margin: Distanza minima di sicurezza in unità Blender.

        Returns:
            ``True`` se i due OBB si sovrappongono o sono più vicini del margine.
        """
        # Espansione del margine
        a = OBB(
            self.cx,
            self.cy,
            self.half_w + margin / 2,
            self.half_d + margin / 2,
            self.angle,
        )
        b = OBB(
            other.cx,
            other.cy,
            other.half_w + margin / 2,
            other.half_d + margin / 2,
            other.angle,
        )

        axes = list(a._axes()) + list(b._axes())
        corners_a = a._corners()
        corners_b = b._corners()

        for ax, ay in axes:
            proj_a = [ax * cx + ay * cy for cx, cy in corners_a]
            proj_b = [ax * cx + ay * cy for cx, cy in corners_b]
            if max(proj_a) <= min(proj_b) or max(proj_b) <= min(proj_a):
                return False  # asse separante trovato
        return True


# ---------------------------------------------------------------------------
# Nodi e grafo
# ---------------------------------------------------------------------------


@dataclass
class SceneNode:
    """Nodo del grafo della scena: un oggetto con il suo OBB."""

    obj: SceneObject
    bbox: OBB
    adjusted: bool = False
    conflicts_resolved: int = 0


@dataclass
class SceneGraph:
    """Grafo spaziale della scena 3D basato su OBB.

    Gestisce il posizionamento degli oggetti garantendo assenza di
    sovrapposizioni tenendo conto dell'orientamento rot_z.
    """

    nodes: list[SceneNode] = field(default_factory=list)
    safety_margin: float = 0.15
    assets_dir: Path | None = None

    def add_object(self, obj: SceneObject) -> SceneNode:
        """Aggiunge un oggetto al grafo calcolando il suo OBB.

        Le dimensioni vengono calcolate dinamicamente dalla mesh se
        ``assets_dir`` è impostato, altrimenti si usano i valori statici.

        Args:
            obj: ``SceneObject`` Pydantic da aggiungere.

        Returns:
            Il nodo creato.
        """
        dims = get_asset_dimensions(obj.name, self.assets_dir)
        half_w = (dims[0] * obj.scale) / 2.0
        half_d = (dims[1] * obj.scale) / 2.0

        obb = OBB(
            cx=obj.x,
            cy=obj.y,
            half_w=half_w,
            half_d=half_d,
            angle=obj.rot_z,
        )
        node = SceneNode(obj=obj, bbox=obb)
        self.nodes.append(node)
        return node

    def resolve_collisions(self, max_iterations: int = 10) -> list[SceneObject]:
        """Risolve le collisioni OBB spostando gli oggetti in conflitto.

        Ordina per area decrescente (oggetti grandi mantengono la posizione)
        e itera fino a nessun conflitto o ``max_iterations``.

        Args:
            max_iterations: Numero massimo di iterazioni di risoluzione.

        Returns:
            Lista di ``SceneObject`` con posizioni aggiornate.
        """
        self.nodes.sort(key=lambda n: n.bbox.area(), reverse=True)

        for iteration in range(max_iterations):
            conflicts_found = False
            for i, node_a in enumerate(self.nodes):
                for node_b in self.nodes[i + 1 :]:
                    if node_a.bbox.intersects(node_b.bbox, self.safety_margin):
                        conflicts_found = True
                        self._resolve_pair(node_a, node_b)
            if not conflicts_found:
                logger.debug("Collisioni OBB risolte in %d iterazioni.", iteration + 1)
                break
        else:
            logger.warning(
                "Risoluzione OBB terminata dopo %d iterazioni "
                "(potrebbero esistere sovrapposizioni residue).",
                max_iterations,
            )

        return self._export_objects()

    def get_statistics(self) -> dict[str, Any]:
        """Restituisce statistiche sul layout della scena.

        Returns:
            Dizionario con metriche sul layout (oggetti totali, aggiustati,
            dimensioni della scena).
        """
        total = len(self.nodes)
        adjusted = sum(1 for n in self.nodes if n.adjusted)
        total_conflicts_resolved = sum(n.conflicts_resolved for n in self.nodes)

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

    def _resolve_pair(self, node_a: SceneNode, node_b: SceneNode) -> None:
        """Risolve la collisione tra due nodi spostando il più piccolo (node_b).

        Usa la direzione di minima penetrazione (AABB) per lo spostamento.

        Args:
            node_a: Nodo fisso (più grande per area).
            node_b: Nodo da spostare.
        """
        dx = node_b.bbox.cx - node_a.bbox.cx
        dy = node_b.bbox.cy - node_a.bbox.cy

        overlap_x = min(
            node_a.bbox.x_max - node_b.bbox.x_min,
            node_b.bbox.x_max - node_a.bbox.x_min,
        )
        overlap_y = min(
            node_a.bbox.y_max - node_b.bbox.y_min,
            node_b.bbox.y_max - node_a.bbox.y_min,
        )

        if overlap_x < overlap_y:
            sign = 1 if dx > 0 else -1
            node_b.bbox.cx += sign * (overlap_x + self.safety_margin)
        else:
            sign = 1 if dy > 0 else -1
            node_b.bbox.cy += sign * (overlap_y + self.safety_margin)

        node_b.adjusted = True
        node_b.conflicts_resolved += 1
        logger.debug(
            "OBB collision resolved: '%s' moved to (%.2f, %.2f).",
            node_b.obj.name,
            node_b.bbox.cx,
            node_b.bbox.cy,
        )

    def _export_objects(self) -> list[SceneObject]:
        """Esporta i nodi come lista di SceneObject con posizioni aggiornate."""
        result = []
        for node in self.nodes:
            updated = node.obj.model_copy(
                update={
                    "x": round(node.bbox.cx, 4),
                    "y": round(node.bbox.cy, 4),
                }
            )
            result.append(updated)
        return result


# ---------------------------------------------------------------------------
# Funzione di convenienza
# ---------------------------------------------------------------------------


def apply_scene_graph(
    objects: list[SceneObject],
    assets_dir: Path | None = None,
) -> list[SceneObject]:
    """Applica il grafo spaziale OBB a una lista di oggetti.

    Args:
        objects: Lista di ``SceneObject`` validati dall'orchestratore.
        assets_dir: Directory degli asset per il calcolo dinamico delle dimensioni.

    Returns:
        Lista di ``SceneObject`` con posizioni eventualmente aggiustate.
    """
    if not objects:
        return objects

    graph = SceneGraph(assets_dir=assets_dir)
    for obj in objects:
        graph.add_object(obj)

    adjusted = graph.resolve_collisions()
    stats = graph.get_statistics()

    if stats["adjusted_objects"] > 0:
        logger.info(
            "Scene graph (OBB): %d/%d oggetti riposizionati. "
            "Scena: %.1f m x %.1f m.",
            stats["adjusted_objects"],
            stats["total_objects"],
            stats["scene_width_m"],
            stats["scene_depth_m"],
        )
    else:
        logger.info(
            "Scene graph (OBB): nessuna collisione rilevata. "
            "Scena: %.1f m x %.1f m.",
            stats["scene_width_m"],
            stats["scene_depth_m"],
        )

    return adjusted
