"""
Render della scena e salvataggio output.
Eseguito internamente a Blender (richiede bpy).
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def configure_render(
    output_path: str | Path,
    resolution_x: int = 1920,
    resolution_y: int = 1080,
    samples: int = 64,
    engine: str = "CYCLES",
) -> None:
    """
    Configura i parametri di render della scena.

    Args:
        output_path: Percorso file PNG di output.
        resolution_x: Larghezza render in pixel.
        resolution_y: Altezza render in pixel.
        samples: Numero di campioni Cycles (più alto = qualità maggiore, più lento).
        engine: Motore di render ("CYCLES" o "BLENDER_EEVEE").
    """
    import bpy  # noqa: PLC0415

    scene = bpy.context.scene
    scene.render.engine = engine
    scene.render.resolution_x = resolution_x
    scene.render.resolution_y = resolution_y
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(output_path)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    if engine == "CYCLES":
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True

    logger.debug(
        "Render configurato: %s @ %dx%d, %d samples.",
        engine, resolution_x, resolution_y, samples,
    )


def render_scene(output_path: str | Path) -> Path:
    """
    Esegue il render e salva il file PNG.

    Args:
        output_path: Percorso completo del file di output.

    Returns:
        Path del file PNG generato.
    """
    import bpy  # noqa: PLC0415

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    configure_render(output)
    bpy.ops.render.render(write_still=True)

    logger.info("Render completato: %s", output)
    return output