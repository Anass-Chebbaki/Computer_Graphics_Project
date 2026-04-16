"""
Fase 5 — Costruzione della scena in Blender.

Questo modulo viene eseguito DENTRO Blender (richiede bpy).
Non importarlo in contesti Python standard.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import bpy  # noqa: F401

logger = logging.getLogger(__name__)


def clear_scene() -> None:
    """
    Elimina tutti gli oggetti presenti nella scena corrente.
    Blender aggiunge di default: cubo, camera, luce.
    """
    import bpy  # noqa: PLC0415

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    logger.debug("Scena pulita: tutti gli oggetti di default eliminati.")


def setup_lighting() -> None:
    """Aggiunge illuminazione di base alla scena."""
    import bpy  # noqa: PLC0415

    # Luce solare principale
    bpy.ops.object.light_add(type="SUN", location=(5.0, 5.0, 10.0))
    sun = bpy.context.object
    sun.name = "MainSun"
    sun.data.energy = 3.0

    # Luce ambiente fill (Area light)
    bpy.ops.object.light_add(type="AREA", location=(-3.0, -3.0, 6.0))
    fill = bpy.context.object
    fill.name = "FillLight"
    fill.data.energy = 100.0
    fill.data.size = 5.0

    logger.debug("Illuminazione configurata.")


def setup_camera(location: tuple = (7.0, -7.0, 5.0)) -> None:
    """
    Aggiunge e configura la camera della scena.

    Args:
        location: Posizione (x, y, z) della camera.
    """
    import bpy  # noqa: PLC0415
    import mathutils  # noqa: PLC0415

    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.object
    cam.name = "SceneCamera"

    # Orienta verso l'origine (centro scena)
    direction = mathutils.Vector((0.0, 0.0, 0.0)) - mathutils.Vector(location)
    rot_quat = direction.to_track_quat("-Z", "Y")
    cam.rotation_euler = rot_quat.to_euler()

    bpy.context.scene.camera = cam
    logger.debug("Camera posizionata in %s.", location)


def import_asset(name: str, assets_dir: str | Path) -> Any:
    """
    Importa un modello 3D dalla libreria locale.

    Cerca nell'ordine: .obj → .fbx → .glb → .blend
    Se non trova l'asset, crea un proxy cubo con le dimensioni di default.

    Args:
        name: Nome normalizzato dell'asset (es. "table").
        assets_dir: Percorso alla directory degli asset.

    Returns:
        Riferimento all'oggetto Blender importato o al proxy.
    """
    import bpy  # noqa: PLC0415

    assets_path = Path(assets_dir)

    # Deseleziona tutto prima dell'importazione
    bpy.ops.object.select_all(action="DESELECT")

    # Cerca il file asset nei formati supportati
    for ext in (".obj", ".fbx", ".glb", ".gltf"):
        filepath = assets_path / f"{name}{ext}"
        if filepath.exists():
            return _import_file(str(filepath), name, ext)

    # Fallback: prova a cercare in sottocartelle
    for subdir in assets_path.iterdir():
        if subdir.is_dir():
            for ext in (".obj", ".fbx", ".glb"):
                filepath = subdir / f"{name}{ext}"
                if filepath.exists():
                    return _import_file(str(filepath), name, ext)

    # Proxy geometrico se l'asset non è trovato
    logger.warning(
        "Asset '%s' non trovato in %s. Creo proxy cubo.",
        name,
        assets_dir,
    )
    return _create_proxy(name)


def _import_file(
    filepath: str,
    name: str,
    ext: str,
) -> Any:
    """Importa un file 3D in base all'estensione."""
    import bpy  # noqa: PLC0415

    bpy.ops.object.select_all(action="DESELECT")

    if ext == ".obj":
        bpy.ops.wm.obj_import(filepath=filepath)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=filepath)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=filepath)

    imported = bpy.context.selected_objects[0]
    imported.name = name
    logger.debug("Importato '%s' da %s.", name, filepath)
    return imported


def _create_proxy(name: str) -> Any:
    """
    Crea un cubo colorato come proxy per asset mancanti.

    Il cubo è rosso semitrasparente per renderlo visivamente
    distinguibile dagli asset reali.
    """
    import bpy  # noqa: PLC0415

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.0))
    proxy = bpy.context.object
    proxy.name = f"PROXY_{name}"

    # Materiale rosso per proxy
    mat = bpy.data.materials.new(name=f"ProxyMat_{name}")
    mat.use_nodes = True
    principled = mat.node_tree.nodes["Principled BSDF"]
    principled.inputs["Base Color"].default_value = (1.0, 0.1, 0.1, 1.0)
    principled.inputs["Alpha"].default_value = 0.5
    mat.blend_method = "BLEND"
    proxy.data.materials.append(mat)

    return proxy


def place_object(
    obj: Any,
    x: float,
    y: float,
    z: float,
    rot_x: float,
    rot_y: float,
    rot_z: float,
    scale: float = 1.0,
) -> None:
    """
    Applica posizione, rotazione e scala a un oggetto Blender.

    Args:
        obj: Oggetto Blender da posizionare.
        x, y, z: Coordinate di posizione.
        rot_x, rot_y, rot_z: Rotazioni Euler in radianti.
        scale: Fattore di scala uniforme.
    """
    import mathutils  # noqa: PLC0415

    obj.location = (x, y, z)
    obj.rotation_euler = mathutils.Euler((rot_x, rot_y, rot_z), "XYZ")
    obj.scale = (scale, scale, scale)

    logger.debug(
        "Oggetto '%s' → pos=(%.2f, %.2f, %.2f) rot_z=%.3f scale=%.2f",
        obj.name,
        x,
        y,
        z,
        rot_z,
        scale,
    )


def populate_scene(
    objects: list,
    assets_dir: str | Path,
) -> dict[str, list[str]]:
    """
    Popola la scena Blender con tutti gli oggetti della lista.

    Args:
        objects: Lista di SceneObject (o dict con stessi campi).
        assets_dir: Percorso alla directory degli asset 3D.

    Returns:
        Dizionario con "imported" e "skipped" (nomi degli oggetti).
    """
    assets_dir = Path(assets_dir)
    results: dict[str, list[str]] = {"imported": [], "skipped": [], "proxies": []}

    for obj_data in objects:
        # Supporta sia SceneObject Pydantic che dict
        data = obj_data.model_dump() if hasattr(obj_data, "model_dump") else obj_data
        name = data["name"]

        try:
            blender_obj = import_asset(name, assets_dir)

            place_object(
                blender_obj,
                x=data["x"],
                y=data["y"],
                z=data["z"],
                rot_x=data["rot_x"],
                rot_y=data["rot_y"],
                rot_z=data["rot_z"],
                scale=data.get("scale", 1.0),
            )

            if blender_obj.name.startswith("PROXY_"):
                results["proxies"].append(name)
            else:
                results["imported"].append(name)

        except Exception as exc:
            logger.error("Errore durante import di '%s': %s", name, exc)
            results["skipped"].append(name)

    logger.info(
        "Scena popolata: %d importati, %d proxy, %d saltati.",
        len(results["imported"]),
        len(results["proxies"]),
        len(results["skipped"]),
    )
    return results
