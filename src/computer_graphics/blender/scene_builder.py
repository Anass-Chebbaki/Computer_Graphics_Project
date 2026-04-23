"""
Costruzione della scena in Blender

Questo modulo viene eseguito DENTRO Blender (richiede bpy).
Non importarlo in contesti Python standard.
"""

from __future__ import annotations

import logging
import math
import threading
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


def _bl_version() -> tuple[int, int, int]:
    """Restituisce la versione di Blender come tupla (major, minor, patch)."""
    return tuple(bpy.app.version)  # type: ignore[return-value]


def _socket_name(node: Any, *candidates: str) -> str:
    """
    Restituisce il primo nome di socket presente nell'insieme inputs/outputs
    del nodo tra quelli forniti come candidati.

    Utilizzato per gestire la rinomina dei socket tra versioni di Blender.

    Args:
        node: Nodo del material node tree.
        *candidates: Nomi candidati in ordine di preferenza.

    Returns:
        Il primo nome trovato tra inputs e outputs del nodo.

    Raises:
        KeyError: Se nessun candidato è presente nel nodo.
    """
    all_names: set[str] = set()
    try:
        all_names.update(s.name for s in node.inputs)
        all_names.update(s.name for s in node.outputs)
    except Exception:  # noqa: BLE001
        pass

    for name in candidates:
        if name in all_names:
            return name

    raise KeyError(
        f"Nessuno dei socket candidati {candidates} trovato nel nodo "
        f"'{getattr(node, 'bl_idname', '?')}'. "
        f"Socket disponibili: {all_names}"
    )


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
        if isinstance(color_raw, list | tuple) and len(color_raw) == 3:
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
    fov_deg: float = 50.0,  # Focale grandangolare per interni
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

    # Orienta verso il centro della scena a livello tavolo (z=0.5m)
    # Evita che oggetti alti (librerie) tirino lo sguardo troppo in alto
    scene_center = (
        _get_scene_center(imported_objects) if imported_objects else (0.0, 0.0, 0.0)
    )
    look_at = (scene_center[0], scene_center[1], 0.5)  # Livello tavolino
    direction = mathutils.Vector(look_at) - mathutils.Vector(cam_location)
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
    elevation_angle: float = 15.0,
) -> tuple[float, float, float]:
    """
    Calcola la posizione della camera per inquadratura interni ravvicinata.
    Vista quasi a livello occhi, grandangolare, simile a foto d'interni professionali.
    """

    all_x: list[float] = []
    all_y: list[float] = []
    all_z: list[float] = []

    for obj in objects:
        try:
            if not hasattr(obj, "data") or obj.data is None:
                continue
            mat = obj.matrix_world
            for vert in obj.data.vertices:
                world_co = mat @ vert.co
                all_x.append(world_co.x)
                all_y.append(world_co.y)
                all_z.append(world_co.z)
        except Exception:
            pass

    if not all_x:
        return (5.0, -5.0, 1.7)

    center_x = (min(all_x) + max(all_x)) / 2.0
    center_y = (min(all_y) + max(all_y)) / 2.0
    
    size_x = max(all_x) - min(all_x)
    size_y = max(all_y) - min(all_y)
    
    # Distanza basata solo sulla dimensione orizzontale (ignora Z)
    scene_span = max(size_x, size_y)
    fov_rad = math.radians(fov_deg)
    dist = (scene_span * 0.9) / math.sin(fov_rad / 2.0)
    dist = max(dist, 3.0)
    dist = min(dist, 8.0)

    # Inquadratura diagonale 3/4
    elev_rad = math.radians(elevation_angle)
    cam_x = center_x + dist * math.cos(elev_rad) * 0.707
    cam_y = center_y - dist * math.cos(elev_rad) * 0.707
    # Altezza: 1.5m sopra il pavimento (livello occhi) + leggera elevazione
    cam_z = min(all_z) + 1.5 + dist * math.sin(elev_rad)

    return (cam_x, cam_y, cam_z)


# ---------------------------------------------------------------------------
# Inizializzazione della configurazione dei materiali tramite file YAML
# ---------------------------------------------------------------------------

_MATERIALS_CONFIG: dict[str, Any] | None = None
_materials_lock = threading.Lock()
_MATERIALS_CONFIG_PATH = (
    Path(__file__).parent.parent.parent.parent / "config" / "materials.yaml"
)


def _load_materials_config() -> dict[str, Any]:
    """
    Carica la configurazione dei materiali da config/materials.yaml.

    Usa un singolo lock per l'intera operazione di check-and-load
    per evitare race condition in ambienti multi-thread.

    Returns:
        Dizionario con la sezione ``materials`` del file YAML.
        Dizionario vuoto se il file non esiste o non è leggibile.
    """
    global _MATERIALS_CONFIG  # noqa: PLW0603

    with _materials_lock:
        if _MATERIALS_CONFIG is not None:
            return _MATERIALS_CONFIG

        _MATERIALS_CONFIG = {}  # Default vuoto
        try:
            import yaml  # noqa: PLC0415

            if _MATERIALS_CONFIG_PATH.exists():
                with _MATERIALS_CONFIG_PATH.open(encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
                _MATERIALS_CONFIG = data.get("materials", {})
                logger.debug(
                    "Configurazione materiali caricata da: %s",
                    _MATERIALS_CONFIG_PATH,
                )
        except ImportError:
            # Silenzioso: previsto dentro Blender
            pass
        except Exception as exc:  # noqa: BLE001
            logger.debug("Errore caricamento materiali: %s", exc)

        return _MATERIALS_CONFIG

        return _MATERIALS_CONFIG


def clear_materials_config_cache() -> None:
    """Svuota la cache della configurazione dei materiali (utile per i test)."""
    global _MATERIALS_CONFIG  # noqa: PLW0603
    with _materials_lock:
        _MATERIALS_CONFIG = None


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
    color_override: tuple[float, float, float] | None = None,
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
            try:
                bsdf.inputs[bsdf_key].default_value = float(params[key])
            except (KeyError, TypeError):
                pass

    if params.get("blend_method"):
        # mat.blend_method è stato rimosso in Blender 4.2+.
        # La gestione della trasparenza usa ora mat.surface_render_method.
        if _bl_version() >= (4, 2, 0):
            # "BLENDED" per trasparenza alpha-blended, "DITHERED" per dithered.
            # BLEND in blend_method corrisponde a BLENDED nel nuovo sistema.
            blend_val = params["blend_method"]
            if blend_val == "BLEND":
                mat.surface_render_method = "BLENDED"  # type: ignore[attr-defined]
            else:
                mat.surface_render_method = "DITHERED"  # type: ignore[attr-defined]
        else:
            mat.blend_method = params["blend_method"]  # type: ignore[attr-defined]

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
                try:
                    tex_node.inputs[input_name].default_value = float(
                        noise_cfg[attr]
                    )
                except (KeyError, TypeError):
                    pass
    elif musgrave_cfg:
        # ShaderNodeTexMusgrave è deprecato da Blender 3.4 e rimosso in 4.1+.
        # Dalla versione 4.1 il tipo Musgrave è stato integrato in ShaderNodeTexNoise
        # con parametri aggiuntivi. Usiamo sempre ShaderNodeTexNoise per uniformità.
        tex_node = nodes.new("ShaderNodeTexNoise")
        tex_node.location = (-400, 0)
        for attr, input_name in [("scale", "Scale"), ("detail", "Detail")]:
            if attr in musgrave_cfg:
                try:
                    tex_node.inputs[input_name].default_value = float(
                        musgrave_cfg[attr]
                    )
                except (KeyError, TypeError):
                    pass

    if tex_node and ramp_cfg:
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.location = (-150, 0)

        # Il socket di output del Noise Texture si chiamava "Fac" fino a
        # Blender 3.x e "Factor" da Blender 4.0+. Analogo per il Color Ramp.
        try:
            noise_out_socket = _socket_name(tex_node, "Factor", "Fac")
        except KeyError:
            noise_out_socket = "Fac"

        try:
            ramp_in_socket = _socket_name(ramp, "Factor", "Fac")
        except KeyError:
            ramp_in_socket = "Fac"

        links.new(tex_node.outputs[noise_out_socket], ramp.inputs[ramp_in_socket])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

        for i, stop in enumerate(ramp_cfg[:2]):
            if i < len(ramp.color_ramp.elements):
                ramp.color_ramp.elements[i].color = tuple(stop["color"])

    elif tex_node:
        try:
            noise_out_socket = _socket_name(tex_node, "Factor", "Fac")
        except KeyError:
            noise_out_socket = "Fac"
        links.new(tex_node.outputs[noise_out_socket], bsdf.inputs["Roughness"])

    # ---- Texture PBR da file ----
    if assets_dir is not None:
        pbr = _find_pbr_textures(sem, assets_dir)
        _link_pbr_textures(nodes, links, bsdf, pbr)

    # ---- Override Colore ----
    if color_override:
        color_socket = bsdf.inputs["Base Color"]
        if color_socket.is_linked:
            mix_node = nodes.new("ShaderNodeMix")
            try:
                # Blender 4.0+ richiede l'impostazione esplicita del data_type
                # prima di accedere ai socket per nome.
                mix_node.data_type = "RGBA"  # type: ignore[attr-defined]
                mix_node.blend_type = "MIX"  # type: ignore[attr-defined]

                # Accesso ai socket tramite nome invece di indice numerico
                # per garantire compatibilità cross-version.
                mix_node.inputs["Factor"].default_value = 0.5  # type: ignore[index]

                old_link = color_socket.links[0]
                source_output = old_link.from_socket

                # In Blender 4.x con data_type RGBA i socket si chiamano
                # "A" e "B" per i colori di input e "Result" per l'output.
                try:
                    links.new(source_output, mix_node.inputs["A"])
                    mix_node.inputs["B"].default_value = (  # type: ignore[index]
                        *color_override,
                        1.0,
                    )
                    links.new(mix_node.outputs["Result"], color_socket)
                except KeyError:
                    # Fallback per versioni in cui i socket usano nomi diversi
                    links.new(source_output, mix_node.inputs[6])  # type: ignore[index]
                    mix_node.inputs[7].default_value = (  # type: ignore[index]
                        *color_override,
                        1.0,
                    )
                    links.new(mix_node.outputs[2], color_socket)  # type: ignore[index]

            except (AttributeError, KeyError) as exc:
                logger.warning(
                    "Mix node color override fallito (%s): "
                    "applicazione diretta del colore.", exc
                )
                color_socket.default_value = (*color_override, 1.0)
        else:
            color_socket.default_value = (*color_override, 1.0)

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
    color_override: tuple[float, float, float] | None = None,
    similarity_threshold: float = 0.45,
    _index: Any | None = None,
) -> object:
    """
    Importa un modello 3D dalla libreria locale con ricerca semantica.

    Args:
        name: Nome normalizzato dell'asset (es. ``"table"``).
        assets_dir: Percorso alla directory degli asset.
        material_semantics: Semantica del materiale per shader procedurale.
        color_override: Override del colore RGB per il materiale procedurale.
        similarity_threshold: Soglia cosine similarity per il RAG (default 0.45).
        _index: Istanza di AssetIndex precostruita. Se None viene costruita
            internamente. Passare un'istanza precostruita evita scansioni
            ripetute del filesystem in loop multi-oggetto.

    Returns:
        Riferimento all'oggetto Blender importato o al proxy.
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    from computer_graphics.asset_retriever import AssetIndex  # noqa: PLC0415

    assets_path = Path(assets_dir)
    bpy.ops.object.select_all(action="DESELECT")

    index = _index if _index is not None else AssetIndex(assets_path)

    found_path = index.find_best_match_path_for_name(
        name, assets_path, threshold=similarity_threshold
    )

    if found_path is not None:
        blender_obj = _import_file(str(found_path), name, found_path.suffix)
        if blender_obj is not None:
            _maybe_apply_semantic_material(
                blender_obj,
                material_semantics,
                is_proxy=False,
                color_override=color_override,
            )
            return blender_obj

    # Secondo tentativo: usa la stessa mappa semantica di Poly Haven
    # così ogni asset che il downloader sa risolvere, l'importer lo trova
    try:
        from computer_graphics.poly_haven_catalog import _SEMANTIC_MAPPING  # noqa: PLC0415
        ph_synonyms = _SEMANTIC_MAPPING.get(name, [])
    except ImportError:
        ph_synonyms = []

    for synonym in ph_synonyms:
        syn_path = index.find_best_match_path_for_name(
            synonym, assets_path, threshold=0.5
        )
        if syn_path:
            blender_obj = _import_file(str(syn_path), name, syn_path.suffix)
            if blender_obj:
                _maybe_apply_semantic_material(
                    blender_obj, material_semantics, is_proxy=False, color_override=color_override
                )
                return blender_obj

    logger.warning(
        "Asset '%s' non trovato in %s (RAG threshold=%.2f). Creo proxy cubo.",
        name,
        assets_dir,
        similarity_threshold,
    )
    proxy = _create_proxy(name)
    _maybe_apply_semantic_material(
        proxy, material_semantics, is_proxy=True, color_override=color_override
    )
    return proxy


def _maybe_apply_semantic_material(
    obj: object,
    material_semantics: str | None,
    *,
    is_proxy: bool,
    color_override: tuple[float, float, float] | None = None,
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
        color_override: Override del colore RGB.
    """
    if material_semantics is None:
        return

    has_materials = (
        hasattr(obj, "data")  # type: ignore[attr-defined]
        and hasattr(obj.data, "materials")  # type: ignore[attr-defined]
        and len(obj.data.materials) > 0  # type: ignore[attr-defined]
    )

    if is_proxy or not has_materials:
        _apply_procedural_material(
            obj, material_semantics, color_override=color_override
        )


def _import_file(
    filepath: str,
    name: str,
    ext: str,
) -> object:
    """
    Importa un file 3D in base all'estensione applicando la correzione
    degli assi necessaria per portare ogni formato in Z-up (convenzione Blender).

    Args:
        filepath: Percorso assoluto al file.
        name: Nome da assegnare all'oggetto radice importato.
        ext: Estensione del file (.obj, .fbx, .glb, .gltf).

    Returns:
        Oggetto Blender radice importato, oppure proxy cubo se l'import fallisce.
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    bpy.ops.object.select_all(action="DESELECT")

    pre_import_objects: set[str] = {o.name for o in bpy.data.objects}

    try:
        if ext == ".obj":
            # OBJ usa Y-up per specifica Wavefront.
            # forward_axis="Y" + up_axis="Z" porta correttamente in Z-up
            # senza applicare rotazioni spurie sull'asse X.
            bpy.ops.wm.obj_import(
                filepath=filepath,
                forward_axis="Y",
                up_axis="Z",
            )
        elif ext == ".fbx":
            # FBX può avere assi variabili a seconda del software di origine.
            # axis_forward="-Z" + axis_up="Y" è la convenzione Maya/3ds Max → Blender.
            # use_manual_orientation=True forza l'applicazione ignorando
            # eventuali metadati di orientamento embedded nel file.
            bpy.ops.import_scene.fbx(
                filepath=filepath,
                axis_forward="-Z",
                axis_up="Y",
                use_manual_orientation=True,
                use_anim=False,
            )
        elif ext in (".glb", ".gltf"):
            # glTF/GLB usa Y-up per specifica (glTF 2.0 §3.3).
            # Blender gestisce automaticamente la conversione Y-up → Z-up
            # nell'importatore ufficiale; non serve correzione manuale.
            bpy.ops.import_scene.gltf(
                filepath=filepath,
                merge_vertices=False,
                import_shading="NORMALS",
            )
        else:
            logger.error("Estensione '%s' non supportata per l'import.", ext)
            return _create_proxy(name)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Import di '%s' fallito con eccezione: %s", filepath, exc
        )
        return _create_proxy(name)

    # Individua gli oggetti aggiunti dall'operazione di import
    post_import_objects = [
        o for o in bpy.data.objects if o.name not in pre_import_objects
    ]

    if not post_import_objects:
        logger.error(
            "L'import di '%s' non ha prodotto oggetti nella scena.", filepath
        )
        return _create_proxy(name)

    # Trova l'oggetto radice tra quelli importati: è quello senza parent
    # oppure il cui parent non appartiene al set appena importato.
    imported_names: set[str] = {o.name for o in post_import_objects}
    roots = [
        o for o in post_import_objects
        if o.parent is None or o.parent.name not in imported_names
    ]

    if not roots:
        # Fallback: usa il primo oggetto di tipo MESH trovato
        mesh_objects = [o for o in post_import_objects if o.type == "MESH"]
        root_obj = mesh_objects[0] if mesh_objects else post_import_objects[0]
    else:
        root_obj = roots[0]

    root_obj.name = name
    logger.debug("Importato '%s' da %s (root: %s).", name, filepath, root_obj.name)
    return root_obj


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
    nodes = mat.node_tree.nodes
    nodes.clear()
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    output = nodes.new("ShaderNodeOutputMaterial")
    mat.node_tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])
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
    name_to_blender: dict[str, Any],
    objects_data: list[dict[str, object]],
) -> None:
    """
    Applica le relazioni di parentela tra oggetti Blender.

    Imposta obj.parent e aggiorna matrix_parent_inverse per preservare
    la posizione mondiale dell'oggetto figlio dopo l'assegnazione della
    parentela. Senza questo aggiornamento, Blender applica la trasformazione
    del parent alla posizione locale del figlio, causando uno spostamento
    visivo non desiderato.

    Args:
        name_to_blender: Mappa {nome_oggetto: blender_object}.
        objects_data: Lista di dict con i dati degli SceneObject
            (incluso il campo "parent").
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    try:
        import mathutils as _mu  # noqa: PLC0415
    except ImportError:
        logger.error(
            "_apply_parent_relationships: mathutils non disponibile."
        )
        return

    for data in objects_data:
        child_name = str(data.get("name", ""))
        parent_name = data.get("parent")

        if not parent_name or not isinstance(parent_name, str):
            continue

        child_obj = name_to_blender.get(child_name)
        parent_obj = name_to_blender.get(parent_name)

        if child_obj is None:
            logger.warning(
                "Gerarchia: oggetto figlio '%s' non trovato nella scena.",
                child_name,
            )
            continue

        if parent_obj is None:
            logger.warning(
                "Gerarchia: parent '%s' di '%s' non trovato nella scena. "
                "L'oggetto rimane a radice.",
                parent_name,
                child_name,
            )
            continue

        # Salva la matrice mondiale corrente del figlio prima dell'assegnazione.
        # Dopo child_obj.parent = parent_obj, Blender ricalcola la posizione
        # locale del figlio in base al parent. Impostando matrix_parent_inverse
        # all'inverso della matrice mondiale del parent, si annulla questo
        # effetto preservando la posizione mondiale originale del figlio.
        world_matrix_before = child_obj.matrix_world.copy()  # type: ignore[attr-defined]

        child_obj.parent = parent_obj  # type: ignore[attr-defined]
        child_obj.matrix_parent_inverse = (  # type: ignore[attr-defined]
            parent_obj.matrix_world.inverted()  # type: ignore[attr-defined]
        )

        # Ripristina la matrice mondiale per garantire coerenza dopo
        # eventuali aggiornamenti del dependency graph.
        child_obj.matrix_world = world_matrix_before  # type: ignore[attr-defined]

        logger.debug(
            "Gerarchia applicata: '%s'.parent = '%s'.", child_name, parent_name
        )


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
            current_origin = origin.copy()
            hit = True
            while hit:
                hit, location, _normal, _index, _hit_obj, _matrix = scene.ray_cast(
                    depsgraph,
                    current_origin,
                    direction,
                    distance=ray_distance,
                )
                if hit and _hit_obj == obj:
                    current_origin = location.copy()
                    current_origin.z -= 0.001
                else:
                    break

            if hit:
                # Verifica che la normale del piano colpito sia prettamente verticale (+Z)
                # per evitare snap su pareti verticali o superfici inclinate eccessivamente.
                if _normal.z < 0.7:
                    logger.warning(
                        "Snap '%s' rilevato su superficie inclinata (normal.z=%.2f). "
                        "Il posizionamento potrebbe essere errato.",
                        obj.name, _normal.z
                    )
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


def _create_room_geometry(
    imported_objects: list[Any],
    margin: float = 1.0,
    wall_height: float = 2.5,
    ceiling: bool = False,
) -> None:
    """
    Genera pavimento e pareti calcolando il bounding box degli oggetti
    presenti nella scena e aggiungendo un margine configurabile.

    Args:
        imported_objects: Lista di oggetti Blender già posizionati nella scena.
        margin: Margine aggiuntivo oltre il bounding box degli oggetti.
        wall_height: Altezza delle pareti.
        ceiling: Se True, genera anche il soffitto.
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    try:
        import mathutils as _mu  # noqa: PLC0415
    except ImportError:
        logger.error(
            "_create_room_geometry: mathutils non disponibile."
        )
        return

    if not imported_objects:
        return

    global_min = [float("inf")] * 3
    global_max = [float("-inf")] * 3
    found = False

    for obj in imported_objects:
        if not hasattr(obj, "type") or obj.type != "MESH":
            continue
        if not hasattr(obj, "bound_box"):
            continue
        for corner in obj.bound_box:
            world_corner = obj.matrix_world @ _mu.Vector(corner)
            for i in range(3):
                if world_corner[i] < global_min[i]:
                    global_min[i] = world_corner[i]
                if world_corner[i] > global_max[i]:
                    global_max[i] = world_corner[i]
        found = True

    if not found:
        return

    min_x = global_min[0] - margin
    max_x = global_max[0] + margin
    min_y = global_min[1] - margin
    max_y = global_max[1] + margin
    floor_z = global_min[2]  # Il pavimento è al minimo Z degli oggetti, non a 0

    width = max_x - min_x   # Estensione sull'asse X
    depth = max_y - min_y   # Estensione sull'asse Y
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0

    # --- Pavimento con materiale ---
    bpy.ops.mesh.primitive_plane_add(
        size=1.0,
        location=(center_x, center_y, floor_z),
    )
    floor_obj = bpy.context.object
    floor_obj.name = "Room_Floor"
    # Il plane primitivo ha dimensione 1x1 nello spazio locale.
    # La scala porta alle dimensioni reali in unità Blender.
    floor_obj.scale = (width, depth, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    # Materiale pavimento (parquet caldo)
    floor_mat = bpy.data.materials.new(name="Floor_Material")
    floor_mat.use_nodes = True
    floor_bsdf = floor_mat.node_tree.nodes.get("Principled BSDF")
    if floor_bsdf:
        floor_bsdf.inputs["Base Color"].default_value = (0.45, 0.32, 0.22, 1.0)
        floor_bsdf.inputs["Roughness"].default_value = 0.7
    floor_obj.data.materials.append(floor_mat)

    # --- Pareti ---
    # Generiamo 4 pareti ma ne nascondiamo una per la visibilità (quella vicina alla camera)
    walls_data = [
        # (Posizione, Rotazione Z, Nome, Scala X)
        ((center_x, min_y, floor_z + wall_height / 2), 0.0, "Wall_South", width),
        ((center_x, max_y, floor_z + wall_height / 2), 3.14159, "Wall_North", width),
        ((min_x, center_y, floor_z + wall_height / 2), 1.5708, "Wall_West", depth),
        ((max_x, center_y, floor_z + wall_height / 2), -1.5708, "Wall_East", depth),
    ]

    # Trova la camera — può chiamarsi "SceneCamera" o "Camera"
    cam = bpy.data.objects.get("SceneCamera") or bpy.data.objects.get("Camera")
    if cam:
        cam_pos = _mu.Vector(cam.location)
    else:
        # Fallback: camera nel quadrante sud-ovest (vista 3/4 classica)
        cam_pos = _mu.Vector((center_x + 5, center_y - 5, 3))

    # Materiale pareti (bianco crema opaco)
    wall_mat = bpy.data.materials.new(name="Wall_Material")
    wall_mat.use_nodes = True
    wall_bsdf = wall_mat.node_tree.nodes.get("Principled BSDF")
    if wall_bsdf:
        wall_bsdf.inputs["Base Color"].default_value = (0.92, 0.90, 0.87, 1.0)
        wall_bsdf.inputs["Roughness"].default_value = 0.9

    for pos, rot, name, w_scale in walls_data:
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=pos)
        wall = bpy.context.object
        wall.name = name
        wall.rotation_euler[0] = 1.5708  # 90° su X
        wall.rotation_euler[2] = rot
        wall.scale = (w_scale, wall_height, 1.0)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        wall.data.materials.append(wall_mat)

        # Nascondi i 2 muri che ostruiscono la visuale
        is_obstructing = False
        if "South" in name and cam_pos.y < center_y: is_obstructing = True
        if "North" in name and cam_pos.y > center_y: is_obstructing = True
        if "West" in name and cam_pos.x < center_x: is_obstructing = True
        if "East" in name and cam_pos.x > center_x: is_obstructing = True

        if is_obstructing:
            wall.hide_render = True
            wall.hide_viewport = True
            logger.info("Muro '%s' nascosto (camera a %.1f, %.1f).", name, cam_pos.x, cam_pos.y)

    # --- Soffitto (opzionale) ---
    if ceiling:
        bpy.ops.mesh.primitive_plane_add(
            size=1.0,
            location=(center_x, center_y, floor_z + wall_height),
            # Il soffitto è un plane orizzontale ruotato di 180° su X
            # in modo che la normale punti verso il basso (nell'interno).
            rotation=(math.radians(180.0), 0.0, 0.0),
        )
        ceil_obj = bpy.context.object
        ceil_obj.name = "Room_Ceiling"
        ceil_obj.scale = (width, depth, 1.0)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    logger.info(
        "Geometria stanza generata: %.2f m x %.2f m x %.2f m (margin=%.1f).",
        width,
        depth,
        wall_height,
        margin,
    )


# ---------------------------------------------------------------------------
# Orchestrazione principale della scena: caricamento, posizionamento e materiali
# ---------------------------------------------------------------------------
def populate_scene(
    objects: list[Any],
    assets_dir: str | Path,
    lights: list[Any] | None = None,
    enable_physics: bool = False,
    room_mode: bool = False,
) -> dict[str, list[str]]:
    """
    Popola la scena Blender con tutti gli oggetti della lista.

    Flusso:
    1. Importa e posiziona ogni oggetto (con materiale procedurale se richiesto).
    2. Applica la gerarchia parent-child.
    3. Genera la geometria della stanza (Room Mode).
    4. Esegue lo snap degli oggetti sulle superfici.
    5. Configura la camera sul bounding box finale.
    6. Configura l'illuminazione.

    Args:
        objects: Lista di SceneObject (o dict con stessi campi).
        assets_dir: Percorso alla directory degli asset 3D.
        lights: Lista di LightObject per illuminazione semantica.
        enable_physics: Se True, esegue il settling fisico.

    Returns:
        Dizionario con chiavi "imported", "proxies", "skipped".
    """

    assets_dir = Path(assets_dir)

    # Costruisce l'indice semantico una sola volta per tutta la pipeline
    # di importazione. Evita N scansioni del filesystem per N oggetti.
    from computer_graphics.asset_retriever import AssetIndex  # noqa: PLC0415
    asset_index = AssetIndex(assets_dir)

    results: dict[str, list[str]] = {
        "imported": [],
        "proxies": [],
        "skipped": [],
    }

    # Mappa nome → oggetto Blender per la gerarchia
    name_to_blender: dict[str, Any] = {}
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
        # type: ignore[attr-defined]
        color_override_val = data.get("color_override")
        color_override_tuple: tuple[float, float, float] | None = None
        if color_override_val and isinstance(color_override_val, list | tuple):
            color_override_tuple = (
                float(color_override_val[0]),
                float(color_override_val[1]),
                float(color_override_val[2]),
            )

        all_objects_data.append(data)

        try:
            blender_obj = import_asset(
                name,
                assets_dir,
                mat_sem_str,
                color_override=color_override_tuple,
                _index=asset_index,
            )

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

    # Passo 1: Applicazione delle relazioni di parentela gerarchica.
    # Deve avvenire prima dello snap per avere le posizioni mondiali corrette.
    logger.info("Applicazione gerarchia parent-child...")
    _apply_parent_relationships(name_to_blender, all_objects_data)

    # Passo 2: Configurazione della camera sul bounding box aggiornato.
    # Viene calcolata prima della stanza per permettere ai muri di nascondersi correttamente.
    logger.info("Aggiornamento camera sul bounding box della scena...")
    setup_camera(imported_objects=imported_blender_objects)

    # Passo 3: Generazione della geometria della stanza (se abilitata).
    if room_mode:
        logger.info("Generazione automatica stanza (Room Mode)...")
        _create_room_geometry(
            imported_blender_objects,
            margin=0.5,
            wall_height=3.0,
            ceiling=False,
        )
        # Illuminazione studio per interni
        logger.info("Configurazione illuminazione studio per interni...")
        sc = _get_scene_center(imported_blender_objects)
        wh = 2.5  # Wall height usata per _create_room_geometry
        # Luce principale dall'alto (simula luce naturale)
        bpy.ops.object.light_add(type='AREA', location=(sc[0] - 1, sc[1], wh - 0.3))
        key_light = bpy.context.object
        key_light.name = "Room_KeyLight"
        key_light.data.energy = 300.0
        key_light.data.size = 3.0
        key_light.data.color = (1.0, 0.96, 0.92)
        key_light.rotation_euler = (0.5, 0.0, 0.0)
        # Luce di riempimento dal lato opposto
        bpy.ops.object.light_add(type='AREA', location=(sc[0] + 2, sc[1] - 2, wh * 0.6))
        fill_light = bpy.context.object
        fill_light.name = "Room_FillLight"
        fill_light.data.energy = 100.0
        fill_light.data.size = 4.0
        fill_light.data.color = (0.95, 0.95, 1.0)

    # Passo 4: Snap degli oggetti sulle superfici via raycasting.
    # Eseguito dopo la generazione della stanza per avere il pavimento
    # disponibile come superficie di atterraggio.
    if enable_physics and imported_blender_objects:
        logger.info("Avvio surface snap via raycasting...")
        snap_objects_to_surface(imported_blender_objects)

    # Passo 5: Configurazione dell'illuminazione.
    setup_lighting(lights=lights)

    logger.info(
        "Scena popolata: %d importati, %d proxy, %d saltati.",
        len(results["imported"]),
        len(results["proxies"]),
        len(results["skipped"]),
    )
    return results
