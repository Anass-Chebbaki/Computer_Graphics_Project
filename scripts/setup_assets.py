#!/usr/bin/env python3
"""
Utility per la configurazione della libreria di asset 3D.

Funzionalità:
- Verifica quali asset sono presenti in assets/models/
- Elenca gli asset mancanti rispetto alla lista supportata
- Scarica asset di esempio da Poly Haven (solo metadati, non i file binari)
- Genera un report sullo stato della libreria

Uso:
    python scripts/setup_assets.py --check
    python scripts/setup_assets.py --report
    python scripts/setup_assets.py --generate-proxies
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from computer_graphics.scene_graph import OBJECT_DIMENSIONS


console = Console()

SUPPORTED_FORMATS = [".obj", ".fbx", ".glb", ".gltf", ".blend"]

# Fonti gratuite consigliate per ogni asset
ASSET_SOURCES: dict[str, str] = {
    "table": "https://polyhaven.com/models/wooden_table",
    "chair": "https://polyhaven.com/models/wooden_chair",
    "lamp": "https://sketchfab.com/3d-models/floor-lamp",
    "sofa": "https://sketchfab.com/3d-models/sofa",
    "desk": "https://sketchfab.com/3d-models/desk",
    "bookshelf": "https://polyhaven.com/models/bookshelf",
    "bed": "https://polyhaven.com/models/bed",
    "monitor": "https://sketchfab.com/3d-models/monitor",
    "plant": "https://polyhaven.com/models/potted_plant",
    "fridge": "https://sketchfab.com/3d-models/refrigerator",
    "cabinet": "https://sketchfab.com/3d-models/cabinet",
    "rug": "https://polyhaven.com/models/rug",
}


def find_assets(assets_dir: Path) -> dict[str, list[Path]]:
    """
    Trova tutti gli asset presenti nella directory.

    Returns:
        Dict {nome_asset: [lista_file_trovati]}
    """
    found: dict[str, list[Path]] = {}
    if not assets_dir.exists():
        return found

    for fmt in SUPPORTED_FORMATS:
        for filepath in assets_dir.glob(f"*{fmt}"):
            name = filepath.stem.lower()
            if name not in found:
                found[name] = []
            found[name].append(filepath)

    # Cerca anche in sottodirectory
    for subdir in assets_dir.iterdir():
        if subdir.is_dir():
            for fmt in SUPPORTED_FORMATS:
                for filepath in subdir.glob(f"*{fmt}"):
                    name = filepath.stem.lower()
                    if name not in found:
                        found[name] = []
                    found[name].append(filepath)

    return found


@click.group()
def main() -> None:
    """Utility per la gestione della libreria di asset 3D."""


@main.command()
@click.option(
    "--assets-dir",
    default="assets/models",
    help="Directory degli asset.",
)
def check(assets_dir: str) -> None:
    """Verifica lo stato della libreria di asset."""
    assets_path = Path(assets_dir)
    found = find_assets(assets_path)

    supported = set(OBJECT_DIMENSIONS.keys())
    present = set(found.keys()) & supported
    missing = supported - present
    extra = set(found.keys()) - supported

    table = Table(title=f"Stato libreria asset: {assets_path}", border_style="blue")
    table.add_column("Asset", style="bold")
    table.add_column("Stato", justify="center")
    table.add_column("File", style="dim")
    table.add_column("Fonte suggerita")

    for name in sorted(supported):
        if name in present:
            files_str = ", ".join(f.name for f in found[name])
            table.add_row(name, "[green]✓[/green]", files_str, "")
        else:
            source = ASSET_SOURCES.get(name, "—")
            table.add_row(name, "[yellow]⚠ mancante[/yellow]", "—", source)

    console.print(table)

    console.print(
        f"\n[bold]Riepilogo:[/bold] "
        f"[green]{len(present)} presenti[/green] / "
        f"[yellow]{len(missing)} mancanti[/yellow] / "
        f"[dim]{len(extra)} extra[/dim]"
    )

    if missing:
        suggestion = (
            f"\n[dim]Suggerimento: eseguire [bold]make generate-primitives[/bold] "
            f"per creare asset primitivi per tutti i {len(missing)} "
            "asset mancanti.[/dim]"
        )
        console.print(suggestion)


@main.command()
@click.option(
    "--assets-dir",
    default="assets/models",
    help="Directory degli asset.",
)
@click.option("--output", default="asset_report.json", help="File di output report.")
def report(assets_dir: str, output: str) -> None:
    """Genera un report JSON sullo stato degli asset."""
    import json  # noqa: PLC0415

    assets_path = Path(assets_dir)
    found = find_assets(assets_path)
    supported = set(OBJECT_DIMENSIONS.keys())

    report_data: dict[str, Any] = {
        "assets_dir": str(assets_path.resolve()),
        "supported_count": len(supported),
        "present_count": len(set(found.keys()) & supported),
        "missing_count": len(supported - set(found.keys())),
        "assets": {},
    }

    for name in sorted(supported):
        dims = OBJECT_DIMENSIONS.get(name, (1.0, 1.0, 1.0))
        report_data["assets"][name] = {
            "present": name in found,
            "files": [str(f) for f in found.get(name, [])],
            "dimensions_m": {
                "width": dims[0],
                "depth": dims[1],
                "height": dims[2],
            },
            "source": ASSET_SOURCES.get(name),
        }

    output_path = Path(output)
    with output_path.open("w", encoding="utf-8") as fp:
        json.dump(report_data, fp, indent=2, ensure_ascii=False)

    msg = f"[green]✓ Report salvato:[/green] [cyan]{output_path.resolve()}[/cyan]"
    console.print(msg)


if __name__ == "__main__":
    main()
