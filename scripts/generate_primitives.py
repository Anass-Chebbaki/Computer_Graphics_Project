#!/usr/bin/env python3
"""
Generatore automatico di asset 3D primitivi per Blender.

Questo script crea modelli 3D semplici (cubo, cilindro, ecc.) per tutti gli
oggetti presenti in KNOWN_ASSET_NAMES, esportandoli come file .obj nella
directory assets/models/.

È pensato come soluzione di bootstrap: permette di dimostrare la pipeline
completa (NL → JSON → Blender → render) senza dover scaricare asset esterni.

Uso:
    # Da terminale (richiede bpy installato come modulo standalone)
    python scripts/generate_primitives.py

    # All'interno di Blender
    blender --background --python scripts/generate_primitives.py

    # Tramite make
    make generate-primitives
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


# Setup path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    import bpy
except ImportError:
    bpy = None

# Definizioni degli asset: nome → (tipo_primitivo, parametri, colore_RGB, scala)
ASSET_DEFINITIONS: dict[str, dict] = {
    "table": {
        "type": "table_composite",
        "color": (0.55, 0.35, 0.18),
        "description": "Tavolo con piano e 4 gambe",
    },
    "chair": {
        "type": "chair_composite",
        "color": (0.3, 0.2, 0.1),
        "description": "Sedia con sedile, schienale e 4 gambe",
    },
    "lamp": {
        "type": "lamp_composite",
        "color": (0.9, 0.8, 0.5),
        "description": "Lampada da terra con base e paralume",
    },
    "desk": {
        "type": "box",
        "size": (1.6, 0.8, 0.75),
        "color": (0.4, 0.3, 0.2),
        "description": "Scrivania",
    },
    "sofa": {
        "type": "sofa_composite",
        "color": (0.5, 0.5, 0.7),
        "description": "Divano a 3 posti",
    },
    "bookshelf": {
        "type": "bookshelf_composite",
        "color": (0.6, 0.4, 0.2),
        "description": "Libreria con ripiani",
    },
    "monitor": {
        "type": "monitor_composite",
        "color": (0.1, 0.1, 0.1),
        "description": "Monitor da scrivania",
    },
    "plant": {
        "type": "plant_composite",
        "color": (0.2, 0.6, 0.2),
        "description": "Pianta in vaso",
    },
    "bed": {
        "type": "bed_composite",
        "color": (0.8, 0.8, 0.9),
        "description": "Letto matrimoniale",
    },
    "cabinet": {
        "type": "box",
        "size": (0.8, 0.4, 1.4),
        "color": (0.7, 0.6, 0.5),
        "description": "Armadio",
    },
    "rug": {
        "type": "flat_box",
        "size": (2.0, 1.5, 0.02),
        "color": (0.7, 0.3, 0.3),
        "description": "Tappeto",
    },
    "fridge": {
        "type": "box",
        "size": (0.7, 0.7, 1.8),
        "color": (0.9, 0.9, 0.9),
        "description": "Frigorifero",
    },
}


def _create_material(bpy: Any, name: str, color: tuple[float, float, float]) -> Any:
    """Crea un materiale Principled BSDF con il colore specificato."""
    mat = bpy.data.materials.new(name=name)  # type: ignore[attr-defined]
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.7
    return mat


def _add_box(
    bpy: Any,
    location: tuple,
    size: tuple[float, float, float],
    name: str,
) -> Any:
    """Aggiunge un cubo scalato nella posizione specificata."""
    bpy.ops.mesh.primitive_cube_add(location=location)  # type: ignore[attr-defined]
    obj = bpy.context.object  # type: ignore[attr-defined]
    obj.name = name
    obj.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)  # type: ignore[attr-defined]
    return obj


def _build_table(bpy: Any) -> list[Any]:
    """Costruisce un tavolo composito: piano + 4 gambe."""
    objects = []
    # Piano del tavolo
    top = _add_box(bpy, (0, 0, 0.72), (1.4, 0.8, 0.05), "table_top")
    objects.append(top)
    # 4 gambe
    leg_positions = [
        (0.63, 0.33, 0.36),
        (-0.63, 0.33, 0.36),
        (0.63, -0.33, 0.36),
        (-0.63, -0.33, 0.36),
    ]
    for i, pos in enumerate(leg_positions):
        leg = _add_box(bpy, pos, (0.06, 0.06, 0.72), f"table_leg_{i}")
        objects.append(leg)
    return objects


def _build_chair(bpy: Any) -> list[Any]:
    """Costruisce una sedia composita: sedile + schienale + 4 gambe."""
    objects = []
    # Sedile
    seat = _add_box(bpy, (0, 0, 0.45), (0.55, 0.55, 0.05), "chair_seat")
    objects.append(seat)
    # Schienale
    back = _add_box(bpy, (0, -0.26, 0.75), (0.55, 0.05, 0.6), "chair_back")
    objects.append(back)
    # 4 gambe
    leg_positions = [
        (0.24, 0.24, 0.22),
        (-0.24, 0.24, 0.22),
        (0.24, -0.24, 0.22),
        (-0.24, -0.24, 0.22),
    ]
    for i, pos in enumerate(leg_positions):
        leg = _add_box(bpy, pos, (0.04, 0.04, 0.44), f"chair_leg_{i}")
        objects.append(leg)
    return objects


def _build_lamp(bpy: Any) -> list[Any]:
    """Costruisce una lampada da terra: base + asta + paralume."""
    objects = []
    # Base
    bpy.ops.mesh.primitive_cylinder_add(  # type: ignore[attr-defined]
        radius=0.18, depth=0.08, location=(0, 0, 0.04)
    )
    base = bpy.context.object  # type: ignore[attr-defined]
    base.name = "lamp_base"
    objects.append(base)
    # Asta
    bpy.ops.mesh.primitive_cylinder_add(  # type: ignore[attr-defined]
        radius=0.025, depth=1.5, location=(0, 0, 0.83)
    )
    pole = bpy.context.object  # type: ignore[attr-defined]
    pole.name = "lamp_pole"
    objects.append(pole)
    # Paralume (cono)
    bpy.ops.mesh.primitive_cone_add(  # type: ignore[attr-defined]
        radius1=0.25, radius2=0.08, depth=0.35, location=(0, 0, 1.67)
    )
    shade = bpy.context.object  # type: ignore[attr-defined]
    shade.name = "lamp_shade"
    objects.append(shade)
    return objects


def _build_sofa(bpy: Any) -> list[Any]:
    """Costruisce un divano composito."""
    objects = []
    # Seduta
    seat = _add_box(bpy, (0, 0, 0.22), (2.1, 0.85, 0.2), "sofa_seat")
    objects.append(seat)
    # Schienale
    back = _add_box(bpy, (0, -0.38, 0.6), (2.1, 0.12, 0.55), "sofa_back")
    objects.append(back)
    # Braccioli
    for side, x in [("left", 1.02), ("right", -1.02)]:
        arm = _add_box(bpy, (x, 0, 0.42), (0.12, 0.85, 0.4), f"sofa_arm_{side}")
        objects.append(arm)
    return objects


def _build_bookshelf(bpy: Any) -> list[Any]:
    """Costruisce una libreria con 4 ripiani."""
    objects = []
    # Struttura esterna
    frame = _add_box(bpy, (0, 0, 0.9), (0.9, 0.3, 1.8), "shelf_frame")
    objects.append(frame)
    # 4 ripiani interni
    for i, z in enumerate([0.2, 0.55, 0.9, 1.25]):
        shelf = _add_box(bpy, (0, 0, z), (0.85, 0.27, 0.03), f"shelf_plank_{i}")
        objects.append(shelf)
    return objects


def _build_monitor(bpy: Any) -> list[Any]:
    """Costruisce un monitor da scrivania."""
    objects = []
    # Schermo
    screen = _add_box(bpy, (0, 0, 0.5), (0.55, 0.05, 0.35), "monitor_screen")
    objects.append(screen)
    # Base
    base = _add_box(bpy, (0, 0, 0.03), (0.25, 0.2, 0.06), "monitor_base")
    objects.append(base)
    # Collo
    neck = _add_box(bpy, (0, 0, 0.22), (0.04, 0.04, 0.35), "monitor_neck")
    objects.append(neck)
    return objects


def _build_plant(bpy: Any) -> list[Any]:
    """Costruisce una pianta in vaso."""
    objects = []
    # Vaso (cono troncato)
    bpy.ops.mesh.primitive_cone_add(  # type: ignore[attr-defined]
        radius1=0.18, radius2=0.12, depth=0.22, location=(0, 0, 0.11)
    )
    pot = bpy.context.object  # type: ignore[attr-defined]
    pot.name = "plant_pot"
    objects.append(pot)
    # Fogliame (icosfera)
    bpy.ops.mesh.primitive_ico_sphere_add(  # type: ignore[attr-defined]
        radius=0.28, location=(0, 0, 0.55)
    )
    foliage = bpy.context.object  # type: ignore[attr-defined]
    foliage.name = "plant_foliage"
    objects.append(foliage)
    return objects


def _build_bed(bpy: Any) -> list[Any]:
    """Costruisce un letto matrimoniale."""
    objects = []
    # Base/struttura
    base = _add_box(bpy, (0, 0, 0.2), (1.6, 2.0, 0.35), "bed_base")
    objects.append(base)
    # Materasso
    mattress = _add_box(bpy, (0, 0, 0.45), (1.55, 1.95, 0.18), "bed_mattress")
    objects.append(mattress)
    # Testiera
    headboard = _add_box(bpy, (0, -0.95, 0.75), (1.6, 0.08, 0.6), "bed_headboard")
    objects.append(headboard)
    return objects


# Mapping tipo → funzione costruttore
_BUILDERS = {
    "table_composite": _build_table,
    "chair_composite": _build_chair,
    "lamp_composite": _build_lamp,
    "sofa_composite": _build_sofa,
    "bookshelf_composite": _build_bookshelf,
    "monitor_composite": _build_monitor,
    "plant_composite": _build_plant,
    "bed_composite": _build_bed,
}


def generate_all_primitives(output_dir: str | Path | None = None) -> dict[str, bool]:
    """
    Genera tutti gli asset 3D primitivi ed esporta in formato .obj.

    Args:
        output_dir: Directory di output. Default: assets/models/

    Returns:
        Dizionario {nome_asset: successo}.
    """
    if bpy is None:
        print(  # noqa: T201
            "ERRORE: bpy non disponibile. Eseguire dentro Blender:\n"
            "  blender --background --python scripts/generate_primitives.py"
        )
        sys.exit(1)

    if output_dir is None:
        output_dir = PROJECT_ROOT / "assets" / "models"

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results: dict[str, bool] = {}

    for asset_name, definition in ASSET_DEFINITIONS.items():
        print(f"[generate_primitives] Generazione: {asset_name}...")  # noqa: T201

        try:
            # Pulisci scena
            bpy.ops.object.select_all(action="SELECT")
            bpy.ops.object.delete()

            color = definition.get("color", (0.5, 0.5, 0.5))
            asset_type = definition["type"]

            # Costruzione geometria
            if asset_type in _BUILDERS:
                obj_list = _BUILDERS[asset_type](bpy)
            elif asset_type in ("box", "flat_box"):
                size = definition.get("size", (1.0, 1.0, 1.0))
                z_center = size[2] / 2
                obj_list = [_add_box(bpy, (0, 0, z_center), size, asset_name)]
            else:
                print(f"  [SKIP] Tipo '{asset_type}' non riconosciuto.")  # noqa: T201
                results[asset_name] = False
                continue

            # Applica materiale a tutti gli oggetti
            mat = _create_material(bpy, f"mat_{asset_name}", color)
            for obj in obj_list:
                obj.data.materials.clear()
                obj.data.materials.append(mat)

            # Seleziona tutti e unisci in un unico mesh
            bpy.ops.object.select_all(action="SELECT")
            bpy.context.view_layer.objects.active = obj_list[0]
            if len(obj_list) > 1:
                bpy.ops.object.join()

            # Rinomina oggetto finale
            bpy.context.object.name = asset_name

            # Esporta in .obj
            export_path = str(output_path / f"{asset_name}.obj")
            bpy.ops.wm.obj_export(
                filepath=export_path,
                export_selected_objects=True,
                export_materials=True,
                export_uv=True,
                export_normals=True,
            )

            print(f"  [OK] Esportato: {export_path}")  # noqa: T201
            results[asset_name] = True

        except Exception as exc:  # noqa: BLE001
            print(f"  [ERROR] {asset_name}: {exc}")  # noqa: T201
            results[asset_name] = False

    # Report finale
    ok = sum(1 for v in results.values() if v)
    total = len(results)
    msg = f"[generate_primitives] Completato: {ok}/{total} asset generati in {output_path}"  # noqa: E501
    print(f"\n{msg}")  # noqa: T201

    return results


if __name__ == "__main__":
    generate_all_primitives()
