"""
Render della scena e salvataggio output in formati 2D e 3D.

Eseguito internamente a Blender (richiede bpy).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal


logger = logging.getLogger(__name__)

try:
    import bpy
except ImportError:
    bpy = None  # type: ignore[assignment]

# Formati 3D supportati per l'esportazione
ExportFormat = Literal["glb", "usdz"]


def configure_render(
    output_path: str | Path,
    # resolution_x: int = 1920,
    # resolution_y: int = 1080,
    resolution_x: int = 640,
    resolution_y: int = 360,
    samples: int = 64,
    # engine: str = "CYCLES", MOTORE GRAFICO PIU PERFORMANTE
    engine: str = "BLENDER_EEVEE",  # UTLIZZIAMO QUESTO PER DEBUG AL MOMENTO
) -> None:
    """Configura i parametri di render della scena.

    Args:
        output_path: Percorso file PNG di output.
        resolution_x: Larghezza render in pixel.
        resolution_y: Altezza render in pixel.
        samples: Numero di campioni Cycles.
        engine: Motore di render (``"CYCLES"`` o ``"BLENDER_EEVEE"``).
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    scene = bpy.context.scene
    scene.render.engine = engine
    scene.render.resolution_x = resolution_x
    scene.render.resolution_y = resolution_y
    # scene.render.resolution_percentage = 100
    scene.render.resolution_percentage = 75
    scene.render.filepath = str(output_path)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    if engine == "CYCLES":
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True

    logger.debug(
        "Render configurato: %s @ %dx%d, %d samples.",
        engine,
        resolution_x,
        resolution_y,
        samples,
    )


def render_scene(output_path: str | Path) -> Path:
    """Esegue il render 2D e salva il file PNG.

    Args:
        output_path: Percorso completo del file PNG di output.

    Returns:
        Path del file PNG generato.
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    from computer_graphics.config_loader import ConfigLoader

    blender_cfg = ConfigLoader.get("blender", default={})
    engine = blender_cfg.get("render_engine", "CYCLES")
    res_x = blender_cfg.get("resolution_x", 1920)
    res_y = blender_cfg.get("resolution_y", 1080)
    samples = blender_cfg.get("samples", 64)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    configure_render(
        output,
        resolution_x=res_x,
        resolution_y=res_y,
        samples=samples,
        engine=engine,
    )

    bpy.ops.render.render(write_still=True)
    logger.info("Render 2D completato: %s", output)
    return output


def export_scene_3d(
    output_path: str | Path,
    fmt: ExportFormat = "glb",
    selected_only: bool = False,
) -> Path:
    """Esporta l'intera scena assemblata in formato 3D (.glb o .usdz).

    Affianca la pipeline di rendering 2D (``render_scene``) consentendo
    di salvare la scena in un formato interoperabile con motori 3D e
    visualizzatori AR/XR.

    Args:
        output_path: Percorso di output (l'estensione viene forzata al formato).
        fmt: Formato di esportazione: ``"glb"`` (GL Transmission Format) oppure
            ``"usdz"`` (Universal Scene Description compresso).
        selected_only: Se ``True``, esporta solo gli oggetti selezionati.

    Returns:
        Path del file 3D esportato.

    Raises:
        ImportError: Se ``bpy`` non è disponibile.
        ValueError: Se il formato richiesto non è supportato.
        RuntimeError: Se Blender non riesce a completare l'esportazione.
    """
    if bpy is None:
        raise ImportError("Questo modulo richiede Blender e il modulo bpy")

    output = Path(output_path).with_suffix(f".{fmt}")
    output.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "glb":
        _export_glb(output, selected_only=selected_only)
    elif fmt == "usdz":
        _export_usdz(output, selected_only=selected_only)
    else:
        raise ValueError(
            f"Formato di esportazione non supportato: '{fmt}'. "
            "Valori ammessi: 'glb', 'usdz'."
        )

    if not output.exists():
        raise RuntimeError(
            f"Esportazione fallita: il file '{output}' non è stato creato."
        )

    logger.info("Scena 3D esportata in formato %s: %s", fmt.upper(), output)
    return output


def _export_glb(output: Path, *, selected_only: bool) -> None:
    """Esegue l'esportazione GLTF/GLB tramite bpy.

    Args:
        output: Percorso di output .glb.
        selected_only: Esporta solo gli oggetti selezionati.
    """
    bpy.ops.export_scene.gltf(  # type: ignore[union-attr]
        filepath=str(output),
        export_format="GLB",
        use_selection=selected_only,
        export_apply=True,  # Applicazione dei modificatori durante l'esportazione
        export_texcoords=True,
        export_normals=True,
        export_materials="EXPORT",
        export_colors=True,
        export_cameras=True,
        export_lights=True,
    )
    logger.debug("GLB export completato: %s", output)


def _export_usdz(output: Path, *, selected_only: bool) -> None:
    """Esegue l'esportazione USD/USDZ tramite bpy.

    Richiede il plugin USD di Blender 3.0+ abilitato.

    Args:
        output: Percorso di output .usdz.
        selected_only: Esporta solo gli oggetti selezionati.
    """
    # Il formato USDZ è supportato da Blender 3.0+ tramite io_scene_usd
    try:
        bpy.ops.wm.usd_export(  # type: ignore[union-attr]
            filepath=str(output),
            selected_objects_only=selected_only,
            export_animation=False,
            export_hair=False,
            export_uvmaps=True,
            export_normals=True,
            export_materials=True,
            export_meshes=True,
            export_lights=True,
            export_cameras=True,
        )
    except AttributeError as exc:
        raise RuntimeError(
            "Esportazione USDZ non supportata in questa versione di Blender. "
            "È richiesto Blender 3.0+ con il plugin USD abilitato."
        ) from exc
    logger.debug("USDZ export completato: %s", output)
