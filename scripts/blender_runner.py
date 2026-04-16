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

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_blender_args() -> tuple[str, str | None]:
    """
    Recupera argomenti passati dopo '--' nell'invocazione Blender.

    Returns:
        Tupla (json_path, render_output_or_None).
    """
    argv = sys.argv
    try:
        sep_index = argv.index("--")
        args = argv[sep_index + 1 :]
    except ValueError:
        return OBJECTS_JSON_PATH, RENDER_OUTPUT if RENDER_ENABLED else None

    json_path = args[0] if args else OBJECTS_JSON_PATH
    render_out = None

    if "--render" in args:
        render_idx = args.index("--render")
        if render_idx + 1 < len(args):
            render_out = args[render_idx + 1]

    if "--no-render" in args:
        render_out = None

    return json_path, render_out


def main() -> None:
    """Entry point dello script Blender."""
    from computer_graphics.blender.scene_builder import (
        clear_scene,
        populate_scene,
        setup_camera,
        setup_lighting,
    )

    json_path, render_output = parse_blender_args()

    # Carica oggetti dal JSON
    json_file = Path(json_path)
    if not json_file.exists():
        logger.error("File JSON non trovato: %s", json_file.resolve())
        sys.exit(1)

    with json_file.open(encoding="utf-8") as fp:
        objects = json.load(fp)

    logger.info("Caricati %d oggetti da %s", len(objects), json_file)

    # Pipeline Blender
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

    # Render opzionale
    if render_output:
        from computer_graphics.blender.renderer import render_scene

        logger.info("Avvio render → %s", render_output)
        render_scene(render_output)
        logger.info("Render completato.")


if __name__ == "__main__":
    main()
