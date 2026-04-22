#!/usr/bin/env python3
"""
Script da eseguire DENTRO Blender per costruire la scena 3D.

Uso da terminale:
    blender --background --python scripts/blender_runner.py -- objects.json
    blender --background --python scripts/blender_runner.py -- \
        objects.json --render output.png

Uso da Blender Text Editor:
    Impostare OBJECTS_JSON_PATH e ASSETS_DIR nella sezione CONFIG
    e premere Run Script.
"""

from __future__ import annotations

import json
import logging
import site
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# CONFIG (modifica qui se esegui dall'editor interno di Blender)
# ---------------------------------------------------------------------------
OBJECTS_JSON_PATH: str = "scene_objects.json"
ASSETS_DIR: str = str(Path(__file__).parent.parent / "assets" / "models")
_BASE_RENDER_DIR = Path(__file__).parent.parent / "assets" / "renders"
RENDER_OUTPUT: str = str(_BASE_RENDER_DIR / "output.png")
RENDER_ENABLED: bool = True
# ---------------------------------------------------------------------------

# Setup path per trovare i moduli del progetto
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
# Aggiunge le librerie installate dall'utente (rich, pydantic, ecc.)

sys.path.insert(0, site.getusersitepackages())
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_blender_args() -> tuple[str, str | None, str | None, str]:
    """Recupera argomenti passati dopo '--' nell'invocazione Blender.

    Returns:
        Tupla ``(json_path, render_output_or_None, export_path_or_None,
        export_format)``.
    """
    argv = sys.argv
    try:
        sep_index = argv.index("--")
        args = argv[sep_index + 1 :]
    except ValueError:
        return (
            OBJECTS_JSON_PATH,
            RENDER_OUTPUT if RENDER_ENABLED else None,
            None,
            "glb",
        )

    json_path = args[0] if args else OBJECTS_JSON_PATH
    render_out: str | None = None
    export_path: str | None = None
    export_format: str = "glb"

    if "--render" in args:
        render_idx = args.index("--render")
        if render_idx + 1 < len(args):
            render_out = str((PROJECT_ROOT / args[render_idx + 1]).resolve())

    if "--no-render" in args:
        render_out = None

    if "--export-3d" in args:
        exp_idx = args.index("--export-3d")
        if exp_idx + 1 < len(args):
            export_path = str((PROJECT_ROOT / args[exp_idx + 1]).resolve())

    if "--export-format" in args:
        fmt_idx = args.index("--export-format")
        if fmt_idx + 1 < len(args):
            export_format = args[fmt_idx + 1].lower()

    return json_path, render_out, export_path, export_format


def main() -> None:
    """Entry point dello script Blender."""
    from computer_graphics.blender.scene_builder import (
        clear_scene,
        populate_scene,
        setup_camera,
        setup_lighting,
    )

    json_path, render_output, export_path, export_format = parse_blender_args()

    json_file = Path(json_path)
    if not json_file.exists():
        logger.error("File JSON non trovato: %s", json_file.resolve())
        sys.exit(1)

    with json_file.open(encoding="utf-8") as fp:
        objects = json.load(fp)

    logger.info("Caricati %d oggetti da %s", len(objects), json_file)

    logger.info("Pulizia scena...")
    clear_scene()

    logger.info("Configurazione luci e camera...")
    setup_lighting()
    setup_camera()

    logger.info("Importazione oggetti in scena...")
    results = populate_scene(objects, ASSETS_DIR)
    logger.info(
        "Scena pronta: %d importati, %d proxy, %d saltati.",
        len(results["imported"]),
        len(results["proxies"]),
        len(results["skipped"]),
    )

    # Render 2D (opzionale)
    if render_output:
        from computer_graphics.blender.renderer import render_scene

        logger.info("Avvio render 2D -> %s", render_output)
        render_scene(render_output)
        logger.info("Render 2D completato.")

    # Esportazione 3D (opzionale)
    if export_path:
        from computer_graphics.blender.renderer import export_scene_3d

        logger.info(
            "Avvio esportazione 3D (%s) -> %s", export_format.upper(), export_path
        )
        try:
            out = export_scene_3d(
                export_path,
                fmt=export_format,  # type: ignore[arg-type]
                selected_only=False,
            )
            logger.info("Esportazione 3D completata: %s", out)
        except Exception as exc:  # noqa: BLE001
            logger.error("Esportazione 3D fallita: %s", exc)


if __name__ == "__main__":
    main()
