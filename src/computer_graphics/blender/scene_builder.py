"""
Costruzione della scena in Blender

Questo modulo viene eseguito DENTRO Blender (richiede bpy).
Non importarlo in contesti Python standard.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Lazy import di bpy e moduli Blender - disponibili solo dentro Blender
try:
    import bpy  # noqa: F401
    import mathutils  # noqa: F401
except ImportError:
    bpy = None  # type: ignore[assignment]
    mathutils = None  # type: ignore[assignment]

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------
_PHYSICS_SETTLE_FRAMES: int = 80  # frame da simulare per lo settling
_PROXY_PREFIX: str = "PROXY_"


# ---------------------------------------------------------------------------
# clear_scene
# ---------------------------------------------------------------------------
def clear_scene() -> None:
    """
    Elimina tutti gli oggetti presenti nella scena corrente.

    Blender aggiunge di default: cubo, camera, luce.
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    logger.debug("Scena pulita: tutti gli oggetti di default eliminati.")


# ---------------------------------------------------------------------------
# Feature C — setup_lighting semantico
# ---------------------------------------------------------------------------
def setup_lighting(
    lights: list[Any] | None = None,
) -> None:
    """
    Configura l'illuminazione della scena.

    Se viene passata una lista di LightObject generati dall'LLM, li istanzia
    in Blender con i parametri specificati . Altrimenti usa un
    setup di base con luce solare e fill.

    Args:
        lights: Lista di LightObject Pydantic (opzionale). Se None o vuota,
            usa l'illuminazione di default.
    """

    if lights:
        _setup_lights_from_llm(lights)
    else:
        _setup_default_lighting()


def _setup_default_lighting() -> None:
    """Illuminazione di base: sole principale + fill area."""
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    bpy.ops.object.light_add(type="SUN", location=(5.0, 5.0, 10.0))
    sun = bpy.context.object
    sun.name = "MainSun"
    sun.data.energy = 3.0

    bpy.ops.object.light_add(type="AREA", location=(-3.0, -3.0, 6.0))
    fill = bpy.context.object
    fill.name = "FillLight"
    fill.data.energy = 100.0
    fill.data.size = 5.0

    logger.debug("Illuminazione di default configurata.")


def _setup_lights_from_llm(lights: list[Any]) -> None:
    """
    Istanzia le luci generate dall'LLM in Blender.

    Args:
        lights: Lista di LightObject Pydantic.
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    for light_obj in lights:
        # Supporta sia LightObject Pydantic che dict
        data = (
            light_obj.model_dump()  # type: ignore[attr-defined]
            if hasattr(light_obj, "model_dump")
            else dict(light_obj)  # type: ignore[call-overload]
        )
        light_type: str = str(data.get("light_type", "POINT"))
        location: tuple[float, float, float] = (
            float(data.get("x", 0.0)),
            float(data.get("y", 0.0)),
            float(data.get("z", 3.0)),
        )

        bpy.ops.object.light_add(type=light_type, location=location)
        bl_light = bpy.context.object
        bl_light.name = str(data.get("name", "LLMLight"))

        # Colore ed energia
        color_raw = data.get("color", (1.0, 1.0, 1.0))
        if isinstance(color_raw, (list, tuple)) and len(color_raw) == 3:
            bl_light.data.color = (
                float(color_raw[0]),
                float(color_raw[1]),
                float(color_raw[2]),
            )

        bl_light.data.energy = float(data.get("energy", 100.0))

        # Parametri specifici per SPOT
        if light_type == "SPOT":
            bl_light.data.spot_size = float(data.get("spot_size", 0.785))

        logger.debug(
            "Luce '%s' (%s) aggiunta in (%.2f, %.2f, %.2f) energy=%.1f.",
            bl_light.name,
            light_type,
            *location,
            bl_light.data.energy,
        )

    logger.info("Configurate %d luci dall'LLM.", len(lights))


# ---------------------------------------------------------------------------
# Feature C — setup_camera con bounding box globale
# ---------------------------------------------------------------------------
def setup_camera(
    imported_objects: list[Any] | None = None,
    fov_deg: float = 50.0,
    location: tuple[float, float, float] | None = None,
) -> None:
    """
    Aggiunge e configura la camera della scena.

    Se viene fornita la lista degli oggetti importati, calcola la posizione
    ottimale della camera usando il bounding box globale dei vertici mesh
    . Altrimenti usa la posizione di default.

    Args:
        imported_objects: Lista di oggetti Blender importati (opzionale).
            Se fornita, la camera viene posizionata per inquadrare l'intera
            scena calcolando il bounding box globale.
        fov_deg: Campo visivo della camera in gradi.
        location: Posizione manuale (sovrascrive il calcolo automatico).
    """
    if bpy is None or mathutils is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    cam_location: tuple[float, float, float]

    if location is not None:
        cam_location = location
    elif imported_objects:
        cam_location = _compute_optimal_camera_location(
            imported_objects, fov_deg=fov_deg
        )
    else:
        cam_location = (7.0, -7.0, 5.0)

    bpy.ops.object.camera_add(location=cam_location)
    cam = bpy.context.object
    cam.name = "SceneCamera"

    # Imposta il FOV
    cam.data.lens_unit = "FOV"
    cam.data.angle = math.radians(fov_deg)

    # Orienta verso il centro geometrico della scena
    scene_center = (
        _get_scene_center(imported_objects) if imported_objects else (0.0, 0.0, 0.0)
    )
    direction = mathutils.Vector(scene_center) - mathutils.Vector(cam_location)
    rot_quat = direction.to_track_quat("-Z", "Y")
    cam.rotation_euler = rot_quat.to_euler()

    bpy.context.scene.camera = cam
    logger.debug(
        "Camera posizionata in %s, punta verso %s.", cam_location, scene_center
    )


def _get_scene_center(
    objects: list[Any],
) -> tuple[float, float, float]:
    """
    Calcola il centro geometrico di una lista di oggetti Blender.

    Args:
        objects: Lista di oggetti Blender.

    Returns:
        Tupla (cx, cy, cz) del centro.
    """

    all_x: list[float] = []
    all_y: list[float] = []
    all_z: list[float] = []

    for obj in objects:
        try:
            if not hasattr(obj, "data") or obj.data is None:  # type: ignore[attr-defined]
                continue
            if not hasattr(obj.data, "vertices"):  # type: ignore[attr-defined]
                all_x.append(obj.location.x)  # type: ignore[attr-defined]
                all_y.append(obj.location.y)  # type: ignore[attr-defined]
                all_z.append(obj.location.z)  # type: ignore[attr-defined]
                continue
            mat = obj.matrix_world  # type: ignore[attr-defined]
            for vert in obj.data.vertices:  # type: ignore[attr-defined]
                world_co = mat @ vert.co
                all_x.append(world_co.x)
                all_y.append(world_co.y)
                all_z.append(world_co.z)
        except Exception:  # noqa: BLE001
            pass

    if not all_x:
        return (0.0, 0.0, 0.0)

    return (
        (min(all_x) + max(all_x)) / 2.0,
        (min(all_y) + max(all_y)) / 2.0,
        (min(all_z) + max(all_z)) / 2.0,
    )


def _compute_optimal_camera_location(
    objects: list[Any],
    fov_deg: float = 50.0,
    elevation_factor: float = 0.6,
) -> tuple[float, float, float]:
    """
    Calcola la posizione ottimale della camera in base al bounding box globale.

    Usa la trigonometria per garantire che la camera inquadri l'intera scena
    dato il campo visivo specificato .

    Args:
        objects: Lista di oggetti Blender importati.
        fov_deg: Campo visivo in gradi.
        elevation_factor: Fattore di elevazione (0=orizzontale, 1=zenitale).

    Returns:
        Tupla (x, y, z) della posizione ottimale.
    """

    all_x: list[float] = []
    all_y: list[float] = []
    all_z: list[float] = []

    for obj in objects:
        try:
            if not hasattr(obj, "data") or obj.data is None:  # type: ignore[attr-defined]
                continue
            if hasattr(obj.data, "vertices"):  # type: ignore[attr-defined]
                mat = obj.matrix_world  # type: ignore[attr-defined]
                for vert in obj.data.vertices:  # type: ignore[attr-defined]
                    world_co = mat @ vert.co
                    all_x.append(world_co.x)
                    all_y.append(world_co.y)
                    all_z.append(world_co.z)
            else:
                all_x.append(obj.location.x)  # type: ignore[attr-defined]
                all_y.append(obj.location.y)  # type: ignore[attr-defined]
                all_z.append(obj.location.z)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    if not all_x:
        return (7.0, -7.0, 5.0)

    # Bounding box globale
    bb_min_x, bb_max_x = min(all_x), max(all_x)
    bb_min_y, bb_max_y = min(all_y), max(all_y)
    bb_max_z = max(all_z)

    center_x = (bb_min_x + bb_max_x) / 2.0
    center_y = (bb_min_y + bb_max_y) / 2.0
    scene_width = bb_max_x - bb_min_x
    scene_depth = bb_max_y - bb_min_y
    scene_height = bb_max_z

    # Dimensione diagonale della scena (worst case)
    diag = math.sqrt(scene_width**2 + scene_depth**2)

    # Distanza minima per inquadrare l'intera scena con il FOV dato
    fov_rad = math.radians(fov_deg)
    dist = (diag / 2.0) / math.tan(fov_rad / 2.0)
    dist = max(dist, 3.0)  # minimo 3 m

    # Eleva la camera in modo proporzionale all'altezza della scena
    cam_z = scene_height + dist * elevation_factor

    # Posiziona la camera a 45° rispetto alla scena (angolo classico 3/4)
    cam_x = center_x + dist * 0.707
    cam_y = center_y - dist * 0.707

    logger.debug(
        "Camera ottimale: scene_diag=%.2fm, dist=%.2fm -> (%.2f, %.2f, %.2f)",
        diag,
        dist,
        cam_x,
        cam_y,
        cam_z,
    )
    return (cam_x, cam_y, cam_z)


# ---------------------------------------------------------------------------
# Feature E — Materiali procedurali
# ---------------------------------------------------------------------------
def _apply_procedural_material(
    obj: object,
    material_semantics: str,
) -> None:
    """
    Applica uno shader procedurale all'oggetto in base alla semantica.

    Shader implementati:
    - "wood": Noise Texture → ColorRamp → Base Color (venatura legno)
    - "glass": Principled BSDF con Transmission=1.0, IOR=1.45
    - "fabric": Noise Texture rugosità + Base Color morbido
    - "metal": Metallic=1.0, Roughness bassa
    - "plastic": Base Color saturo, Roughness media
    - "concrete": Musgrave Texture grigio per ruvidità
    - "ceramic": Base Color bianco/colorato, lucido
    - "leather": Noise sottile + Base Color caldo
    - "marble": Noise complessa → ColorRamp bianco/grigio
    - "rubber": Base Color scuro, Roughness alta

    Args:
        obj: Oggetto Blender a cui applicare il materiale.
        material_semantics: Stringa semantica del materiale.
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    mat_name = f"Procedural_{material_semantics}_{obj.name}"  # type: ignore[attr-defined]

    # Rimuove materiali esistenti sull'oggetto
    if hasattr(obj, "data") and hasattr(obj.data, "materials"):  # type: ignore[attr-defined]
        obj.data.materials.clear()  # type: ignore[attr-defined]

    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    # Nodo output
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (400, 0)

    # Nodo Principled BSDF (base per tutti gli shader)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    sem = material_semantics.lower()

    if sem == "glass":
        bsdf.inputs["Base Color"].default_value = (0.9, 0.95, 1.0, 1.0)
        bsdf.inputs["Metallic"].default_value = 0.0
        bsdf.inputs["Roughness"].default_value = 0.0
        bsdf.inputs["IOR"].default_value = 1.45
        bsdf.inputs["Transmission Weight"].default_value = 1.0
        mat.blend_method = "BLEND"

    elif sem == "wood":
        noise = nodes.new("ShaderNodeTexNoise")
        noise.location = (-400, 0)
        noise.inputs["Scale"].default_value = 12.0
        noise.inputs["Detail"].default_value = 8.0
        noise.inputs["Roughness"].default_value = 0.6
        noise.inputs["Distortion"].default_value = 2.0

        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.location = (-150, 0)
        ramp.color_ramp.elements[0].color = (0.35, 0.18, 0.05, 1.0)
        ramp.color_ramp.elements[1].color = (0.65, 0.40, 0.18, 1.0)

        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.7

    elif sem == "fabric":
        noise = nodes.new("ShaderNodeTexNoise")
        noise.location = (-400, 0)
        noise.inputs["Scale"].default_value = 40.0
        noise.inputs["Detail"].default_value = 4.0
        noise.inputs["Roughness"].default_value = 0.8

        links.new(noise.outputs["Fac"], bsdf.inputs["Roughness"])
        bsdf.inputs["Base Color"].default_value = (0.6, 0.4, 0.8, 1.0)
        bsdf.inputs["Sheen Weight"].default_value = 0.5

    elif sem == "metal":
        bsdf.inputs["Base Color"].default_value = (0.8, 0.8, 0.85, 1.0)
        bsdf.inputs["Metallic"].default_value = 1.0
        bsdf.inputs["Roughness"].default_value = 0.15

    elif sem == "plastic":
        bsdf.inputs["Base Color"].default_value = (0.2, 0.5, 0.9, 1.0)
        bsdf.inputs["Metallic"].default_value = 0.0
        bsdf.inputs["Roughness"].default_value = 0.4

    elif sem == "concrete":
        musgrave = nodes.new("ShaderNodeTexMusgrave")
        musgrave.location = (-400, 0)
        musgrave.inputs["Scale"].default_value = 8.0
        musgrave.inputs["Detail"].default_value = 6.0

        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.location = (-150, 0)
        ramp.color_ramp.elements[0].color = (0.4, 0.4, 0.4, 1.0)
        ramp.color_ramp.elements[1].color = (0.65, 0.65, 0.65, 1.0)

        links.new(musgrave.outputs["Height"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.9

    elif sem == "ceramic":
        bsdf.inputs["Base Color"].default_value = (0.95, 0.95, 0.9, 1.0)
        bsdf.inputs["Metallic"].default_value = 0.0
        bsdf.inputs["Roughness"].default_value = 0.05
        bsdf.inputs["Specular IOR Level"].default_value = 0.8

    elif sem == "leather":
        noise = nodes.new("ShaderNodeTexNoise")
        noise.location = (-400, 0)
        noise.inputs["Scale"].default_value = 25.0
        noise.inputs["Detail"].default_value = 3.0
        noise.inputs["Roughness"].default_value = 0.5

        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.location = (-150, 0)
        ramp.color_ramp.elements[0].color = (0.25, 0.12, 0.05, 1.0)
        ramp.color_ramp.elements[1].color = (0.45, 0.22, 0.10, 1.0)

        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.6

    elif sem == "marble":
        noise = nodes.new("ShaderNodeTexNoise")
        noise.location = (-550, 0)
        noise.inputs["Scale"].default_value = 5.0
        noise.inputs["Detail"].default_value = 10.0
        noise.inputs["Roughness"].default_value = 0.7
        noise.inputs["Distortion"].default_value = 1.5

        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.location = (-200, 0)
        ramp.color_ramp.elements[0].color = (0.9, 0.9, 0.9, 1.0)
        ramp.color_ramp.elements[1].color = (0.2, 0.2, 0.25, 1.0)

        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.1
        bsdf.inputs["Specular IOR Level"].default_value = 1.0

    elif sem == "rubber":
        bsdf.inputs["Base Color"].default_value = (0.05, 0.05, 0.05, 1.0)
        bsdf.inputs["Metallic"].default_value = 0.0
        bsdf.inputs["Roughness"].default_value = 0.95

    else:
        # Fallback generico
        bsdf.inputs["Base Color"].default_value = (0.5, 0.5, 0.5, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.7

    # Assegna il materiale all'oggetto
    if hasattr(obj, "data") and hasattr(obj.data, "materials"):  # type: ignore[attr-defined]
        obj.data.materials.append(mat)  # type: ignore[attr-defined]

    logger.debug(
        "Materiale procedurale '%s' applicato a '%s'.",
        material_semantics,
        obj.name,  # type: ignore[attr-defined]
    )


# ---------------------------------------------------------------------------
# Import asset + proxy
# ---------------------------------------------------------------------------
def import_asset(
    name: str,
    assets_dir: str | Path,
    material_semantics: str | None = None,
) -> object:
    """
    Importa un modello 3D dalla libreria locale.

    Cerca nell'ordine: .obj → .fbx → .glb → .gltf
    Se non trova l'asset, crea un proxy cubo.
    Se il modello non ha materiali o è un proxy, applica shader procedurale
    in base a material_semantics .

    Args:
        name: Nome normalizzato dell'asset (es. "table").
        assets_dir: Percorso alla directory degli asset.
        material_semantics: Semantica del materiale per shader procedurale.

    Returns:
        Riferimento all'oggetto Blender importato o al proxy.
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    assets_path = Path(assets_dir)
    bpy.ops.object.select_all(action="DESELECT")

    # Cerca il file asset nei formati supportati
    for ext in (".obj", ".fbx", ".glb", ".gltf"):
        filepath = assets_path / f"{name}{ext}"
        if filepath.exists():
            blender_obj = _import_file(str(filepath), name, ext)

            if blender_obj is not None:
                _maybe_apply_semantic_material(
                    blender_obj, material_semantics, is_proxy=False
                )
            return blender_obj

    # Fallback: cerca in sottocartelle
    for subdir in assets_path.iterdir():
        if subdir.is_dir():
            for ext in (".obj", ".fbx", ".glb"):
                filepath = subdir / f"{name}{ext}"
                if filepath.exists():
                    blender_obj = _import_file(str(filepath), name, ext)
                    if blender_obj is not None:
                        _maybe_apply_semantic_material(
                            blender_obj, material_semantics, is_proxy=False
                        )
                    return blender_obj

    # Proxy geometrico
    logger.warning(
        "Asset '%s' non trovato in %s. Creo proxy cubo.",
        name,
        assets_dir,
    )
    proxy = _create_proxy(name)

    _maybe_apply_semantic_material(proxy, material_semantics, is_proxy=True)
    return proxy


def _maybe_apply_semantic_material(
    obj: object,
    material_semantics: str | None,
    *,
    is_proxy: bool,
) -> None:
    """
    Applica il materiale procedurale se opportuno .

    Logica:
    - Se is_proxy=True e material_semantics è fornita → applica sempre.
    - Se is_proxy=False e il modello .obj non ha materiali → applica.
    - Se is_proxy=False e ha già materiali → non sovrascrive.

    Args:
        obj: Oggetto Blender target.
        material_semantics: Semantica del materiale o None.
        is_proxy: True se l'oggetto è un proxy cubo (asset mancante).
    """
    if material_semantics is None:
        return

    has_materials = (
        hasattr(obj, "data")  # type: ignore[attr-defined]
        and hasattr(obj.data, "materials")  # type: ignore[attr-defined]
        and len(obj.data.materials) > 0  # type: ignore[attr-defined]
    )

    if is_proxy or not has_materials:
        _apply_procedural_material(obj, material_semantics)


def _import_file(
    filepath: str,
    name: str,
    ext: str,
) -> object:
    """
    Importa un file 3D in base all'estensione.

    Args:
        filepath: Percorso assoluto al file.
        name: Nome da assegnare all'oggetto importato.
        ext: Estensione del file (.obj, .fbx, .glb, .gltf).

    Returns:
        Oggetto Blender importato.
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    bpy.ops.object.select_all(action="DESELECT")

    if ext == ".obj":
        bpy.ops.wm.obj_import(filepath=filepath)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=filepath)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=filepath)

    if not bpy.context.selected_objects:
        logger.error("Importazione di '%s' non ha prodotto oggetti.", filepath)
        return _create_proxy(name)

    imported = bpy.context.selected_objects[0]
    imported.name = name
    logger.debug("Importato '%s' da %s.", name, filepath)
    return imported


def _create_proxy(name: str) -> object:
    """
    Crea un cubo colorato come proxy per asset mancanti.

    Il cubo è rosso semitrasparente per renderlo visivamente distinguibile.

    Args:
        name: Nome dell'asset mancante.

    Returns:
        Oggetto Blender proxy.
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.0))
    proxy = bpy.context.object
    proxy.name = f"{_PROXY_PREFIX}{name}"

    # Materiale rosso di default per proxy (Feature E lo sovrascriverà se
    # material_semantics è fornita)
    mat = bpy.data.materials.new(name=f"ProxyMat_{name}")
    mat.use_nodes = True
    principled = mat.node_tree.nodes["Principled BSDF"]
    principled.inputs["Base Color"].default_value = (1.0, 0.1, 0.1, 1.0)
    principled.inputs["Alpha"].default_value = 0.5
    mat.blend_method = "BLEND"
    proxy.data.materials.append(mat)

    return proxy


# ---------------------------------------------------------------------------
# place_object
# ---------------------------------------------------------------------------
def place_object(
    obj: object,
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
        x: Coordinata X.
        y: Coordinata Y.
        z: Coordinata Z.
        rot_x: Rotazione attorno a X in radianti.
        rot_y: Rotazione attorno a Y in radianti.
        rot_z: Rotazione attorno a Z in radianti.
        scale: Fattore di scala uniforme.
    """
    import mathutils  # noqa: PLC0415

    obj.location = (x, y, z)  # type: ignore[attr-defined]
    obj.rotation_euler = mathutils.Euler((rot_x, rot_y, rot_z), "XYZ")  # type: ignore[attr-defined]
    obj.scale = (scale, scale, scale)  # type: ignore[attr-defined]

    logger.debug(
        "Oggetto '%s' -> pos=(%.2f, %.2f, %.2f) rot_z=%.3f scale=%.2f",
        obj.name,  # type: ignore[attr-defined]
        x,
        y,
        z,
        rot_z,
        scale,
    )


# ---------------------------------------------------------------------------
# Feature A — Parentela gerarchica
# ---------------------------------------------------------------------------
def _apply_parent_relationships(
    name_to_blender: dict[str, object],
    objects_data: list[dict[str, object]],
) -> None:
    """
    Applica le relazioni di parentela tra oggetti Blender .

    Esegue un secondo passaggio dopo l'importazione di tutti gli oggetti,
    impostando obj.parent = parent_obj e mantenendo le trasformazioni
    relative corrette tramite bpy.ops.object.parent_set(keep_transform=False).

    Args:
        name_to_blender: Mappa {nome_oggetto: blender_object}.
        objects_data: Lista di dict con i dati degli SceneObject
            (incluso il campo "parent").
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    for data in objects_data:
        child_name = str(data.get("name", ""))
        parent_name = data.get("parent")

        if not parent_name or not isinstance(parent_name, str):
            continue

        child_obj = name_to_blender.get(child_name)
        parent_obj = name_to_blender.get(parent_name)

        if child_obj is None:
            logger.warning(
                "Gerarchia: oggetto figlio '%s' non trovato in scena.",
                child_name,
            )
            continue

        if parent_obj is None:
            logger.warning(
                "Gerarchia: parent '%s' di '%s' non trovato in scena. "
                "L'oggetto rimane a radice.",
                parent_name,
                child_name,
            )
            continue

        # Deseleziona tutto, seleziona figlio e parent, applica parent
        bpy.ops.object.select_all(action="DESELECT")
        child_obj.select_set(True)  # type: ignore[attr-defined]
        parent_obj.select_set(True)  # type: ignore[attr-defined]
        bpy.context.view_layer.objects.active = parent_obj  # type: ignore[assignment]

        # keep_transform=False: le coordinate sono già relative al parent
        bpy.ops.object.parent_set(type="OBJECT", keep_transform=False)

        logger.debug("Gerarchia: '%s'.parent = '%s'.", child_name, parent_name)

    # Deseleziona tutto alla fine
    bpy.ops.object.select_all(action="DESELECT")


# ---------------------------------------------------------------------------
# Feature B — Simulazione Rigid Body per posizionamento fisico
# ---------------------------------------------------------------------------
def apply_physics_settling(
    imported_objects: list[Any],
    settle_frames: int = _PHYSICS_SETTLE_FRAMES,
) -> None:
    """
    Applica la simulazione Rigid Body per il posizionamento fisico realistico.

    Algoritmo :
    1. Crea un pavimento invisibile con Rigid Body "Passive".
    2. Assegna Rigid Body "Active" (Mesh collision) a tutti gli oggetti.
    3. Avanza la timeline di `settle_frames` frame per lo "settling".
    4. Esegue "Bake to Transforms" (Apply Visual Transform) per fissare
       le posizioni calcolate dalla fisica.
    5. Rimuove i modificatori Rigid Body da tutti gli oggetti.
    6. Rimuove il pavimento invisibile.

    Args:
        imported_objects: Lista di oggetti Blender a cui applicare la fisica.
        settle_frames: Numero di frame da simulare (default: 80).
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    if not imported_objects:
        return

    scene = bpy.context.scene

    # 1. Crea il pavimento invisibile con Rigid Body Passive
    bpy.ops.mesh.primitive_plane_add(size=30.0, location=(0.0, 0.0, -0.01))
    floor_obj = bpy.context.object
    floor_obj.name = "_PhysicsFloor_NL2Scene3D"
    floor_obj.hide_render = True

    bpy.ops.object.select_all(action="DESELECT")
    floor_obj.select_set(True)
    bpy.context.view_layer.objects.active = floor_obj  # type: ignore[assignment]
    bpy.ops.rigidbody.object_add()
    floor_obj.rigid_body.type = "PASSIVE"
    floor_obj.rigid_body.collision_shape = "MESH"
    floor_obj.rigid_body.friction = 0.8

    # 2. Assegna Rigid Body Active a tutti gli oggetti importati
    for obj in imported_objects:
        try:
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)  # type: ignore[attr-defined]
            bpy.context.view_layer.objects.active = obj  # type: ignore[assignment]
            bpy.ops.rigidbody.object_add()
            obj.rigid_body.type = "ACTIVE"  # type: ignore[attr-defined]
            # Usa CONVEX_HULL per performance, MESH per precisione
            obj.rigid_body.collision_shape = "CONVEX_HULL"  # type: ignore[attr-defined]
            obj.rigid_body.friction = 0.7  # type: ignore[attr-defined]
            obj.rigid_body.restitution = 0.1  # type: ignore[attr-defined]
            obj.rigid_body.mass = 1.0  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Impossibile aggiungere Rigid Body a '%s': %s",
                obj.name,  # type: ignore[attr-defined]
                exc,
            )

    # 3. Configura e avanza la timeline per lo settling
    scene.frame_start = 1
    scene.frame_end = settle_frames + 10
    scene.frame_set(1)

    logger.info("Avanzamento fisica Rigid Body per %d frame...", settle_frames)
    for frame in range(1, settle_frames + 1):
        scene.frame_set(frame)

    # Posiziona al frame finale per catturare le posizioni stabilizzate
    scene.frame_set(settle_frames)

    # 4. Bake to Transforms: applica le posizioni visive come trasformazioni reali
    for obj in imported_objects:
        try:
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)  # type: ignore[attr-defined]
            bpy.context.view_layer.objects.active = obj  # type: ignore[assignment]
            # Applica le trasformazioni visive (equivalente di "Bake to Transforms")
            bpy.ops.object.visual_transform_apply()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Impossibile applicare visual transform a '%s': %s",
                obj.name,  # type: ignore[attr-defined]
                exc,
            )

    # 5. Rimuove i Rigid Body da tutti gli oggetti
    for obj in imported_objects:
        try:
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)  # type: ignore[attr-defined]
            bpy.context.view_layer.objects.active = obj  # type: ignore[assignment]
            if obj.rigid_body is not None:  # type: ignore[attr-defined]
                bpy.ops.rigidbody.object_remove()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Impossibile rimuovere Rigid Body da '%s': %s",
                obj.name,  # type: ignore[attr-defined]
                exc,
            )

    # Rimuove il Rigid Body dal pavimento
    try:
        bpy.ops.object.select_all(action="DESELECT")
        floor_obj.select_set(True)
        bpy.context.view_layer.objects.active = floor_obj  # type: ignore[assignment]
        bpy.ops.rigidbody.object_remove()
    except Exception:  # noqa: BLE001
        pass

    # 6. Rimuove il pavimento invisibile dalla scena
    bpy.ops.object.select_all(action="DESELECT")
    floor_obj.select_set(True)
    bpy.ops.object.delete(use_global=False)

    # Ripristina la timeline
    scene.frame_set(1)

    logger.info(
        "Physics settling completato: %d oggetti stabilizzati.",
        len(imported_objects),
    )


# ---------------------------------------------------------------------------
# populate_scene — orchestrazione principale (Feature A + B + C + E)
# ---------------------------------------------------------------------------
def populate_scene(
    objects: list[Any],
    assets_dir: str | Path,
    lights: list[Any] | None = None,
    enable_physics: bool = False,
) -> dict[str, list[str]]:
    """
    Popola la scena Blender con tutti gli oggetti della lista.

    Flusso:
    1. Importa e posiziona ogni oggetto (con materiale procedurale se richiesto).
    2. Applica la gerarchia parent-child .
    3. Opzionalmente esegue la simulazione Rigid Body .
    4. Aggiorna la camera per inquadrare la scena completa .
    5. Configura le luci semantiche .

    Args:
        objects: Lista di SceneObject (o dict con stessi campi).
        assets_dir: Percorso alla directory degli asset 3D.
        lights: Lista di LightObject per illuminazione semantica .
        enable_physics: Se True, esegue il settling fisico .

    Returns:
        Dizionario con chiavi "imported", "proxies", "skipped".
    """

    assets_dir = Path(assets_dir)
    results: dict[str, list[str]] = {
        "imported": [],
        "proxies": [],
        "skipped": [],
    }

    # Mappa nome → oggetto Blender per la gerarchia
    name_to_blender: dict[str, object] = {}
    # Lista oggetti dati (dict) per il secondo passaggio di parentela
    all_objects_data: list[dict[str, object]] = []
    # Lista oggetti Blender importati con successo
    imported_blender_objects: list[Any] = []

    for obj_data in objects:
        # Supporta sia SceneObject Pydantic che dict
        data: dict[str, object] = (
            obj_data.model_dump()  # type: ignore[attr-defined]
            if hasattr(obj_data, "model_dump")
            else dict(obj_data)  # type: ignore[arg-type]
        )
        name = str(data["name"])
        material_semantics = data.get("material_semantics")
        mat_sem_str: str | None = (
            str(material_semantics) if material_semantics else None
        )

        all_objects_data.append(data)

        try:
            blender_obj = import_asset(name, assets_dir, mat_sem_str)

            place_object(
                blender_obj,
                x=float(data.get("x", 0.0)),  # type: ignore[arg-type]
                y=float(data.get("y", 0.0)),  # type: ignore[arg-type]
                z=float(data.get("z", 0.0)),  # type: ignore[arg-type]
                rot_x=float(data.get("rot_x", 0.0)),  # type: ignore[arg-type]
                rot_y=float(data.get("rot_y", 0.0)),  # type: ignore[arg-type]
                rot_z=float(data.get("rot_z", 0.0)),  # type: ignore[arg-type]
                scale=float(data.get("scale", 1.0)),  # type: ignore[arg-type]
            )

            # Registra nella mappa per la gerarchia
            name_to_blender[name] = blender_obj
            imported_blender_objects.append(blender_obj)

            if str(blender_obj.name).startswith(_PROXY_PREFIX):  # type: ignore[attr-defined]
                results["proxies"].append(name)
            else:
                results["imported"].append(name)

        except Exception as exc:  # noqa: BLE001
            logger.error("Errore durante import di '%s': %s", name, exc)
            results["skipped"].append(name)

    # Feature A — Secondo passaggio: applica relazioni di parentela
    logger.info("Applicazione gerarchia parent-child...")
    _apply_parent_relationships(name_to_blender, all_objects_data)

    # Feature B — Simulazione fisica (opzionale)
    if enable_physics and imported_blender_objects:
        logger.info("Avvio simulazione Rigid Body ...")
        apply_physics_settling(imported_blender_objects)

    # Feature C — Aggiorna camera per inquadrare la scena completa
    logger.info("Aggiornamento camera sul bounding box della scena...")
    setup_camera(imported_objects=imported_blender_objects)

    # Feature C — Illuminazione semantica
    setup_lighting(lights=lights)

    logger.info(
        "Scena popolata: %d importati, %d proxy, %d saltati.",
        len(results["imported"]),
        len(results["proxies"]),
        len(results["skipped"]),
    )
    return results
