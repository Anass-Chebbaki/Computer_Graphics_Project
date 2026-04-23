#!/usr/bin/env python3
"""
Entry point eseguito da Blender in modalità background.

Invocazione da CLI:
    blender --background --python scripts/blender_runner.py -- \
        scene_objects.json \
        [--render assets/renders/output.png] \
        [--export-3d assets/renders/scene --export-format glb]

Blender passa tutto ciò che segue '--' in sys.argv. Questo script
estrae i propri argomenti ignorando quelli di Blender che precedono '--'.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _parse_args() -> dict:
    """
    Estrae gli argomenti dello script da sys.argv.

    Blender popola sys.argv con i propri argomenti prima di '--' e
    con quelli dello script dopo '--'. Questo parser ignora tutto
    ciò che precede '--'.

    Returns:
        Dizionario con le chiavi: json_file, render_output, export_3d,
        export_format.
    """
    try:
        separator_idx = sys.argv.index("--")
        script_args = sys.argv[separator_idx + 1:]
    except ValueError:
        logger.error(
            "Separatore '--' non trovato in sys.argv. "
            "Invocazione corretta: blender --background --python "
            "scripts/blender_runner.py -- scene.json"
        )
        sys.exit(1)

    if not script_args:
        logger.error("Nessun argomento fornito dopo '--'. Specificare il file JSON.")
        sys.exit(1)

    result: dict = {
        "json_file": script_args[0],
        "render_output": None,
        "assets_dir": "assets/models",
        "room_mode": False,
        "export_3d": None,
        "export_format": "glb",
    }

    i = 1
    while i < len(script_args):
        arg = script_args[i]
        if arg == "--render" and i + 1 < len(script_args):
            result["render_output"] = script_args[i + 1]
            i += 2
        elif arg == "--assets-dir" and i + 1 < len(script_args):
            result["assets_dir"] = script_args[i + 1]
            i += 2
        elif arg == "--room-mode":
            result["room_mode"] = True
            i += 1
        elif arg == "--export-3d" and i + 1 < len(script_args):
            result["export_3d"] = script_args[i + 1]
            i += 2
        elif arg == "--export-format" and i + 1 < len(script_args):
            result["export_format"] = script_args[i + 1]
            i += 2
        else:
            logger.warning("Argomento non riconosciuto: '%s'", arg)
            i += 1

    return result


def main() -> None:
    """
    Punto di ingresso principale del runner Blender.

    Flusso:
        1. Parsing argomenti
        2. Aggiunta del package src/ al sys.path
        3. Caricamento del JSON degli oggetti
        4. Pulizia della scena default di Blender
        5. Popolazione della scena (import asset, posizionamento, materiali)
        6. Render PNG (opzionale)
        7. Export 3D GLB/USDZ (opzionale)
    """
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(name)s: %(message)s",
    )

    args = _parse_args()
    json_path = Path(args["json_file"])

    if not json_path.exists():
        logger.error("File JSON non trovato: %s", json_path.resolve())
        sys.exit(1)

    # Aggiunge src/ al path per permettere l'import dei moduli blender specifici
    project_root = Path(__file__).parent.parent
    src_path = project_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    import json  # noqa: PLC0415

    with json_path.open(encoding="utf-8") as fp:
        json_data = json.load(fp)

    # Estrae oggetti e luci - assumiamo il JSON sia gia validato dalla CLI
    raw_objects = []
    raw_lights = []
    if isinstance(json_data, dict):
        raw_objects = json_data.get("objects", [])
        raw_lights = json_data.get("lights", [])
    elif isinstance(json_data, list):
        raw_objects = json_data

    assets_path = (project_root / args["assets_dir"]).absolute()

    # Importa moduli Blender (non dipendono da rich/pydantic/yaml)
    from computer_graphics.blender.scene_builder import (  # noqa: PLC0415
        clear_scene,
        populate_scene,
    )

    clear_scene()

    # Costruisci la scena
    results = populate_scene(
        objects=raw_objects,
        lights=raw_lights,
        assets_dir=assets_path,
        room_mode=args["room_mode"],
    )

    logger.info(
        "Scena popolata: %d importati, %d proxy, %d saltati.",
        len(results["imported"]),
        len(results["proxies"]),
        len(results["skipped"]),
    )

    if args["render_output"] is not None:
        from computer_graphics.blender.renderer import render_scene  # noqa: PLC0415

        render_output_path = Path(args["render_output"]).absolute()
        # Usa parametri di default robusti (compatibili con EEVEE/Cycles)
        render_scene(
            render_output_path,
            engine="CYCLES",
            resolution_x=1280,
            resolution_y=720,
            samples=64,
        )
        logger.info("Render completato: %s", render_output_path)

    if args["export_3d"] is not None:
        from computer_graphics.blender.renderer import export_scene_3d  # noqa: PLC0415

        fmt = args["export_format"]
        if fmt not in ("glb", "usdz"):
            logger.error(
                "Formato export non supportato: '%s'. Valori ammessi: glb, usdz.",
                fmt,
            )
            sys.exit(1)

        export_path = Path(args["export_3d"])
        export_scene_3d(export_path, fmt=fmt)
        logger.info(
            "Export 3D (%s) completato: %s",
            fmt.upper(),
            export_path.with_suffix(f".{fmt}").resolve(),
        )


if __name__ == "__main__":
    main()
