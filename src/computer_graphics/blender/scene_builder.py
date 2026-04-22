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
# Configurazione della telecamera basata sul bounding box globale della scena
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
# Inizializzazione della configurazione dei materiali tramite file YAML
# ---------------------------------------------------------------------------

_MATERIALS_CONFIG: dict[str, Any] | None = None
_MATERIALS_CONFIG_PATH = (
    Path(__file__).parent.parent.parent.parent / "config" / "materials.yaml"
)


def _load_materials_config() -> dict[str, Any]:
    """Carica la configurazione dei materiali da config/materials.yaml.

    Returns:
        Dizionario con la sezione ``materials`` del file YAML.
        Dizionario vuoto se il file non esiste o non è leggibile.
    """
    global _MATERIALS_CONFIG  # noqa: PLW0603
    if _MATERIALS_CONFIG is not None:
        return _MATERIALS_CONFIG

    try:
        import yaml  # noqa: PLC0415

        if _MATERIALS_CONFIG_PATH.exists():
            with _MATERIALS_CONFIG_PATH.open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            _MATERIALS_CONFIG = data.get("materials", {})
            logger.debug(
                "Configurazione materiali caricata da: %s", _MATERIALS_CONFIG_PATH
            )
        else:
            logger.debug(
                "File materials.yaml non trovato in %s; uso parametri hardcoded.",
                _MATERIALS_CONFIG_PATH,
            )
            _MATERIALS_CONFIG = {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Errore lettura materials.yaml: %s", exc)
        _MATERIALS_CONFIG = {}

    return _MATERIALS_CONFIG


def _find_pbr_textures(
    material_semantics: str,
    assets_dir: Path,
) -> dict[str, Path]:
    """Cerca texture PBR nella directory assets_dir/textures/<semantica>/.

    Cerca i file con stem albedo/diffuse (Base Color), roughness, normal,
    displacement nei formati .png, .jpg, .exr, .tiff.

    Args:
        material_semantics: Nome del materiale (es. ``"wood"``).
        assets_dir: Directory radice degli asset.

    Returns:
        Dizionario ``{slot_name: Path}`` per le texture trovate.
        Slot: ``albedo``, ``roughness``, ``normal``, ``displacement``.
    """
    tex_dir = assets_dir / "textures" / material_semantics
    if not tex_dir.exists():
        return {}

    slots = {
        "albedo": ["albedo", "diffuse", "basecolor", "base_color", "color"],
        "roughness": ["roughness", "rough"],
        "normal": ["normal", "nor", "nrm"],
        "displacement": ["displacement", "disp", "height"],
    }
    extensions = [".png", ".jpg", ".jpeg", ".exr", ".tiff", ".tga"]
    found: dict[str, Path] = {}

    for slot, stems in slots.items():
        for stem in stems:
            for ext in extensions:
                candidate = tex_dir / f"{stem}{ext}"
                if candidate.exists():
                    found[slot] = candidate
                    break
            if slot in found:
                break

    if found:
        logger.debug(
            "Texture PBR trovate per '%s': %s",
            material_semantics,
            list(found.keys()),
        )
    return found


def _apply_procedural_material(
    obj: object,
    material_semantics: str,
    assets_dir: Path | None = None,
) -> None:
    """Applica uno shader procedurale PBR all'oggetto in base alla semantica.

    I parametri vengono letti da ``config/materials.yaml``. Se vengono
    trovate texture PBR nella directory ``assets_dir/textures/<semantica>/``,
    vengono collegate automaticamente al nodo Principled BSDF.

    Args:
        obj: Oggetto Blender target.
        material_semantics: Stringa semantica del materiale (es. ``"wood"``).
        assets_dir: Directory degli asset per la ricerca delle texture PBR.
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    mat_name = f"Procedural_{material_semantics}_{obj.name}"  # type: ignore[attr-defined]

    if hasattr(obj, "data") and hasattr(obj.data, "materials"):  # type: ignore[attr-defined]
        obj.data.materials.clear()  # type: ignore[attr-defined]

    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (600, 0)

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (200, 0)
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    # ---- Parametri dal YAML ----
    cfg = _load_materials_config()
    sem = material_semantics.lower()
    params = cfg.get(sem, {})

    # Applicazione del colore di base configurato (o del valore predefinito)
    base_color = params.get("base_color")
    if base_color:
        bsdf.inputs["Base Color"].default_value = tuple(base_color)

    for key, bsdf_key in [
        ("metallic", "Metallic"),
        ("roughness", "Roughness"),
        ("ior", "IOR"),
        ("transmission_weight", "Transmission Weight"),
        ("sheen_weight", "Sheen Weight"),
        ("specular_ior_level", "Specular IOR Level"),
    ]:
        if key in params:
            bsdf.inputs[bsdf_key].default_value = float(params[key])

    if params.get("blend_method"):
        mat.blend_method = params["blend_method"]

    # ---- Nodi texture procedurali dal YAML ----
    noise_cfg = params.get("noise_texture")
    musgrave_cfg = params.get("musgrave_texture")
    ramp_cfg = params.get("color_ramp")

    tex_node: Any = None

    if noise_cfg:
        tex_node = nodes.new("ShaderNodeTexNoise")
        tex_node.location = (-400, 0)
        for attr, input_name in [
            ("scale", "Scale"),
            ("detail", "Detail"),
            ("roughness", "Roughness"),
            ("distortion", "Distortion"),
        ]:
            if attr in noise_cfg:
                tex_node.inputs[input_name].default_value = float(noise_cfg[attr])

    elif musgrave_cfg:
        tex_node = nodes.new("ShaderNodeTexMusgrave")
        tex_node.location = (-400, 0)
        for attr, input_name in [("scale", "Scale"), ("detail", "Detail")]:
            if attr in musgrave_cfg:
                tex_node.inputs[input_name].default_value = float(musgrave_cfg[attr])

    if tex_node and ramp_cfg:
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.location = (-150, 0)
        output_socket = (
            "Fac" if tex_node.bl_idname == "ShaderNodeTexNoise" else "Height"
        )
        links.new(tex_node.outputs[output_socket], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        for i, stop in enumerate(ramp_cfg[:2]):
            if i < len(ramp.color_ramp.elements):
                ramp.color_ramp.elements[i].color = tuple(stop["color"])
    elif tex_node:
        links.new(tex_node.outputs["Fac"], bsdf.inputs["Roughness"])

    # ---- Texture PBR da file ----
    if assets_dir is not None:
        pbr = _find_pbr_textures(sem, assets_dir)
        _link_pbr_textures(nodes, links, bsdf, pbr)

    if hasattr(obj, "data") and hasattr(obj.data, "materials"):  # type: ignore[attr-defined]
        obj.data.materials.append(mat)  # type: ignore[attr-defined]

    logger.debug(
        "Materiale '%s' applicato a '%s'.",
        material_semantics,
        obj.name,  # type: ignore[attr-defined]
    )


def _link_pbr_textures(
    nodes: Any,
    links: Any,
    bsdf: Any,
    pbr: dict[str, Path],
) -> None:
    """Collega le texture PBR trovate al nodo Principled BSDF.

    Args:
        nodes: Collezione nodi del material node tree.
        links: Collezione link del material node tree.
        bsdf: Nodo Principled BSDF.
        pbr: Dizionario ``{slot: Path}`` delle texture trovate.
    """
    if not pbr:
        return

    x_offset = -600

    if "albedo" in pbr:
        tex = nodes.new("ShaderNodeTexImage")
        tex.location = (x_offset, 300)
        tex.image = bpy.data.images.load(str(pbr["albedo"]))  # type: ignore[union-attr]
        links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        logger.debug("PBR albedo collegata: %s", pbr["albedo"])

    if "roughness" in pbr:
        tex = nodes.new("ShaderNodeTexImage")
        tex.location = (x_offset, 0)
        tex.image = bpy.data.images.load(str(pbr["roughness"]))  # type: ignore[union-attr]
        tex.image.colorspace_settings.name = "Non-Color"
        links.new(tex.outputs["Color"], bsdf.inputs["Roughness"])
        logger.debug("PBR roughness collegata: %s", pbr["roughness"])

    if "normal" in pbr:
        tex = nodes.new("ShaderNodeTexImage")
        tex.location = (x_offset, -300)
        tex.image = bpy.data.images.load(str(pbr["normal"]))  # type: ignore[union-attr]
        tex.image.colorspace_settings.name = "Non-Color"
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.location = (x_offset + 200, -300)
        links.new(tex.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
        logger.debug("PBR normal map collegata: %s", pbr["normal"])

    if "displacement" in pbr:
        tex = nodes.new("ShaderNodeTexImage")
        tex.location = (x_offset, -600)
        tex.image = bpy.data.images.load(str(pbr["displacement"]))  # type: ignore[union-attr]
        tex.image.colorspace_settings.name = "Non-Color"
        disp_node = nodes.new("ShaderNodeDisplacement")
        disp_node.location = (x_offset + 200, -600)
        output_node = next(
            n for n in nodes if n.bl_idname == "ShaderNodeOutputMaterial"
        )
        links.new(tex.outputs["Color"], disp_node.inputs["Height"])
        links.new(disp_node.outputs["Displacement"], output_node.inputs["Displacement"])
        logger.debug("PBR displacement collegata: %s", pbr["displacement"])


# ---------------------------------------------------------------------------
# Supporto per l'illuminazione ambientale tramite mappe HDRI
# ---------------------------------------------------------------------------


def setup_lighting(
    lights: list[Any] | None = None,
    hdri_path: str | Path | None = None,
    hdri_strength: float = 1.0,
) -> None:
    """Configura l'illuminazione della scena con supporto HDRI.

    Se ``hdri_path`` è fornito, carica la mappa HDRI come sfondo ambientale
    World (illuminazione globale IBL). Le luci LLM e l'illuminazione di default
    vengono comunque configurate in aggiunta all'HDRI.

    Args:
        lights: Lista di LightObject Pydantic (opzionale).
        hdri_path: Percorso a un file .hdr o .exr per l'illuminazione ambientale.
        hdri_strength: Intensità dell'HDRI (default 1.0).
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    if hdri_path is not None:
        _setup_hdri_world(Path(hdri_path), hdri_strength)

    if lights:
        _setup_lights_from_llm(lights)
    elif hdri_path is None:
        # Solo illuminazione di default se non c'è né HDRI né luci LLM
        _setup_default_lighting()


def _setup_hdri_world(hdri_path: Path, strength: float) -> None:
    """Carica una mappa HDRI come illuminazione ambientale World.

    Args:
        hdri_path: Percorso al file .hdr / .exr.
        strength: Intensità dell'ambiente (nodo Background).
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    if not hdri_path.exists():
        logger.warning("File HDRI non trovato: %s. Skip.", hdri_path)
        return

    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("NL2Scene3DWorld")
        bpy.context.scene.world = world

    world.use_nodes = True
    w_nodes = world.node_tree.nodes
    w_links = world.node_tree.links
    w_nodes.clear()

    env_tex = w_nodes.new("ShaderNodeTexEnvironment")
    env_tex.location = (-300, 0)
    env_tex.image = bpy.data.images.load(str(hdri_path))

    background = w_nodes.new("ShaderNodeBackground")
    background.location = (0, 0)
    background.inputs["Strength"].default_value = strength

    output = w_nodes.new("ShaderNodeOutputWorld")
    output.location = (300, 0)

    w_links.new(env_tex.outputs["Color"], background.inputs["Color"])
    w_links.new(background.outputs["Background"], output.inputs["Surface"])

    logger.info("HDRI caricata: %s (strength=%.2f)", hdri_path, strength)


# ---------------------------------------------------------------------------
# Import asset + proxy
# ---------------------------------------------------------------------------
def import_asset(
    name: str,
    assets_dir: str | Path,
    material_semantics: str | None = None,
    similarity_threshold: float = 0.1,
) -> object:
    """Importa un modello 3D dalla libreria locale con ricerca semantica.

    Invece di richiedere che il nome del file corrisponda esattamente al
    campo ``name`` generato dall'LLM, utilizza ``AssetIndex`` per trovare
    l'asset più simile semanticamente. Questo consente di gestire varianti
    lessicali (es. ``"wooden_table"`` -> ``table.obj``).

    Cerca nell'ordine: match esatto -> ricerca semantica -> proxy cubo.

    Se il modello non ha materiali o è un proxy, applica shader procedurale
    in base a ``material_semantics``.

    Args:
        name: Nome normalizzato dell'asset (es. ``"table"``).
        assets_dir: Percorso alla directory degli asset.
        material_semantics: Semantica del materiale per shader procedurale.
        similarity_threshold: Soglia cosine similarity per il RAG (default 0.1).

    Returns:
        Riferimento all'oggetto Blender importato o al proxy.
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    from computer_graphics.asset_retriever import AssetIndex  # noqa: PLC0415

    assets_path = Path(assets_dir)
    bpy.ops.object.select_all(action="DESELECT")

    # Costruzione / recupero dell'indice (la classe gestisce la scansione)
    index = AssetIndex(assets_path)
    found_path = index.find_best_match_path_for_name(
        name, assets_path, threshold=similarity_threshold
    )

    if found_path is not None:
        blender_obj = _import_file(str(found_path), name, found_path.suffix)
        if blender_obj is not None:
            _maybe_apply_semantic_material(
                blender_obj, material_semantics, is_proxy=False
            )
            return blender_obj

    # Proxy geometrico
    logger.warning(
        "Asset '%s' non trovato in %s (RAG threshold=%.2f). Creo proxy cubo.",
        name,
        assets_dir,
        similarity_threshold,
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
        # Molte mesh esterne usano Y-Up; forziamo Z-Up in Blender
        bpy.ops.wm.obj_import(filepath=filepath, forward_axis="NEGATIVE_Z", up_axis="Y")
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=filepath, axis_forward="-Z", axis_up="Y")
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

    # Materiale di fallback per i proxy; sovrascritto dall'implementazione
    # dei materiali se material_semantics è fornita
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
# Gestione delle relazioni gerarchiche tra gli oggetti importati
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
# Posizionamento degli oggetti sulle superfici tramite raycasting
# ---------------------------------------------------------------------------


def snap_objects_to_surface(
    imported_objects: list[Any],
    ray_distance: float = 100.0,
) -> None:
    """Posiziona gli oggetti sulla superficie sottostante via raycasting.

    Proietta un raggio verso il basso (asse -Z) dall'origine di ogni oggetto.
    Se il raggio colpisce una superficie, l'oggetto viene traslato in modo che
    il suo punto più basso coincida con il punto di impatto.

    Questo metodo sostituisce la simulazione Rigid Body da 80 frame con
    un'operazione O(n) immediata e deterministica.

    Args:
        imported_objects: Lista di oggetti Blender da posizionare.
        ray_distance: Distanza massima del raggio in unità Blender.
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    if not imported_objects:
        return

    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()

    for obj in imported_objects:
        try:
            origin = obj.location.copy()  # type: ignore[attr-defined]
            direction = (0.0, 0.0, -1.0)

            # Calcola l'offset tra l'origine dell'oggetto e il suo punto più basso
            # analizzando i vertici in spazio mondo
            z_bottom_offset = 0.0
            if (
                hasattr(obj, "data")
                and obj.data is not None  # type: ignore[attr-defined]
                and hasattr(obj.data, "vertices")  # type: ignore[attr-defined]
            ):
                mat = obj.matrix_world  # type: ignore[attr-defined]
                world_zs = [
                    (mat @ v.co).z  # type: ignore[attr-defined]
                    for v in obj.data.vertices  # type: ignore[attr-defined]
                ]
                if world_zs:
                    z_bottom_offset = obj.location.z - min(world_zs)  # type: ignore[attr-defined]

            # Lancia il raggio verso il basso escludendo l'oggetto stesso
            hit, location, _normal, _index, _hit_obj, _matrix = scene.ray_cast(
                depsgraph,
                origin,
                direction,
                distance=ray_distance,
            )

            if hit:
                # Posiziona l'oggetto in modo che il fondo tocchi la superficie
                obj.location.z = location.z + z_bottom_offset  # type: ignore[attr-defined]
                logger.debug(
                    "Snap '%s': z %.3f -> %.3f (surface z=%.3f)",
                    obj.name,  # type: ignore[attr-defined]
                    origin.z,
                    obj.location.z,  # type: ignore[attr-defined]
                    location.z,
                )
            else:
                logger.debug(
                    "Snap '%s': nessuna superficie trovata entro %.1f m.",
                    obj.name,  # type: ignore[attr-defined]
                    ray_distance,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Snap fallito per '%s': %s",
                getattr(obj, "name", "?"),
                exc,
            )

    logger.info("Surface snap completato per %d oggetti.", len(imported_objects))


# Alias per retrocompatibilità con codice esistente che chiama apply_physics_settling
apply_physics_settling = snap_objects_to_surface


# ---------------------------------------------------------------------------
# Orchestrazione principale della scena: caricamento, posizionamento e materiali
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

    # Applicazione delle relazioni di parentela gerarchica tra gli oggetti
    logger.info("Applicazione gerarchia parent-child...")
    _apply_parent_relationships(name_to_blender, all_objects_data)

    # Posizionamento istantaneo degli oggetti sulle superfici di supporto
    if enable_physics and imported_blender_objects:
        logger.info("Avvio surface snap via raycasting...")
        snap_objects_to_surface(imported_blender_objects)

    # Regolazione della telecamera per l'inquadratura ottimale della scena
    logger.info("Aggiornamento camera sul bounding box della scena...")
    setup_camera(imported_objects=imported_blender_objects)

    # Configurazione dell'illuminazione semantica basata sul contesto
    setup_lighting(lights=lights)

    logger.info(
        "Scena popolata: %d importati, %d proxy, %d saltati.",
        len(results["imported"]),
        len(results["proxies"]),
        len(results["skipped"]),
    )
    return results
