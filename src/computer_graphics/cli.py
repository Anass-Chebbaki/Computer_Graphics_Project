#!/usr/bin/env python3
"""
Interfaccia CLI principale del progetto NL2Scene3D.

Questo modulo è l'entry point registrato in pyproject.toml:
    computer-graphics = "computer_graphics.cli:main"

È separato da run_pipeline.py per permettere l'installazione
come comando di sistema tramite pip.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel

from computer_graphics.config_loader import ConfigLoader
from computer_graphics.input_handler import InputHandler
from computer_graphics.ollama_client import OllamaConnectionError
from computer_graphics.orchestrator import generate_scene_objects

console = Console()
console_err = Console(file=sys.stderr)

BANNER = """
[bold cyan]
███╗   ██╗██╗     ██████╗ ███████╗██████╗ ███████╗███╗   ██╗███████╗██████╗ ██████╗
████╗  ██║██║     ╚════██╗██╔════╝██╔════╝██╔════╝████╗  ██║██╔════╝╚════██╗██╔══██╗
██╔██╗ ██║██║      █████╔╝███████╗██║     █████╗  ██╔██╗ ██║█████╗   █████╔╝██║  ██║
██║╚██╗██║██║     ██╔═══╝ ╚════██║██║     ██╔══╝  ██║╚██╗██║██╔══╝   ╚═══██╗██║  ██║
██║ ╚████║███████╗███████╗███████║╚██████╗███████╗██║ ╚████║███████╗██████╔╝██████╔╝
╚═╝  ╚═══╝╚══════╝╚══════╝╚══════╝ ╚═════╝╚══════╝╚═╝  ╚═══╝╚══════╝╚═════╝ ╚═════╝
[/bold cyan]
[dim]Natural Language → 3D Scene Generator — Powered by Ollama + Blender[/dim]
"""


def _setup_logging(verbose: bool) -> None:
    """Configura il logging con RichHandler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def _print_banner() -> None:
    """Stampa il banner ASCII art del progetto."""
    console.print(BANNER)


@click.group(invoke_without_command=True)
@click.version_option(version="1.0.0", prog_name="NL2Scene3D")
@click.pass_context
def main(ctx: click.Context) -> None:
    """
    NL2Scene3D — Generazione automatica di scene 3D da linguaggio naturale.

    Usa 'computer-graphics generate' per avviare la pipeline principale.
    Usa 'computer-graphics info' per visualizzare la configurazione attuale.
    Usa 'computer-graphics check' per verificare i prerequisiti di sistema.
    """
    if ctx.invoked_subcommand is None:
        _print_banner()
        console.print(ctx.get_help())


@main.command()
@click.argument("description", required=False, default=None)
@click.option("--interactive", "-i", is_flag=True, help="Modalità interattiva.")
@click.option(
    "--file",
    "-f",
    type=click.Path(exists=True),
    help="Legge la descrizione da file .txt.",
)
@click.option("--model", "-m", default=None, show_default=True, help="Modello Ollama.")
@click.option(
    "--output",
    "-o",
    default="scene_objects.json",
    show_default=True,
    help="File JSON di output.",
)
@click.option("--retries", "-r", default=None, type=int, help="Numero max tentativi.")
@click.option("--ollama-url", default=None, help="URL server Ollama.")
@click.option("--verbose", "-v", is_flag=True, help="Output dettagliato.")
@click.option(
    "--blender",
    "-b",
    is_flag=True,
    help="Lancia automaticamente Blender al termine.",
)
@click.option(
    "--render",
    is_flag=True,
    help="Aggiunge il render PNG 2D (richiede --blender).",
)
@click.option(
    "--render-output",
    default="assets/renders/output.png",
    show_default=True,
    help="Percorso output PNG del render.",
)
# ---- Gestione delle opzioni di esportazione della scena 3D ----
@click.option(
    "--export-glb",
    is_flag=True,
    default=False,
    help=(
        "Esporta la scena assemblata in formato .glb "
        "(GL Transmission Format). Richiede --blender."
    ),
)
@click.option(
    "--export-usdz",
    is_flag=True,
    default=False,
    help=(
        "Esporta la scena assemblata in formato .usdz "
        "(Universal Scene Description). Richiede --blender e Blender 3.0+."
    ),
)
@click.option(
    "--export-output",
    default="assets/renders/scene",
    show_default=True,
    help=(
        "Percorso base del file 3D di output senza estensione "
        "(es. assets/renders/my_scene). "
        "L'estensione viene aggiunta automaticamente."
    ),
)
def generate(  # noqa: PLR0913
    description: str | None,
    interactive: bool,
    file: str | None,
    model: str | None,
    output: str,
    retries: int | None,
    ollama_url: str | None,
    verbose: bool,
    blender: bool,
    render: bool,
    render_output: str,
    export_glb: bool,
    export_usdz: bool,
    export_output: str,
) -> None:
    """Genera una scena 3D da una descrizione in linguaggio naturale.

    Esempi:

        computer-graphics generate "una cucina con tavolo e frigorifero"

        computer-graphics generate --interactive --model mistral

        computer-graphics generate "stanza" --blender --export-glb

        computer-graphics generate "studio" --blender --export-usdz \\
            --export-output assets/renders/studio
    """
    _print_banner()
    _setup_logging(verbose)

    # Carica configurazione
    cfg = ConfigLoader.load()
    effective_model = model or cfg.get("ollama", {}).get("model", "llama3")
    effective_url = ollama_url or cfg.get("ollama", {}).get(
        "url", "http://localhost:11434"
    )
    effective_retries = retries or cfg.get("pipeline", {}).get("max_retries", 3)

    # Validazione opzioni
    if (export_glb or export_usdz) and not blender:
        console_err.print(
            "[bold red]Errore:[/bold red] --export-glb e --export-usdz "
            "richiedono --blender."
        )
        raise SystemExit(1)

    if export_glb and export_usdz:
        console_err.print(
            "[bold red]Errore:[/bold red] Specificare solo uno tra "
            "--export-glb e --export-usdz."
        )
        raise SystemExit(1)

    console.print(
        Panel(
            f"[bold]Modello:[/bold] {effective_model}\n"
            f"[bold]Ollama URL:[/bold] {effective_url}\n"
            f"[bold]Max retry:[/bold] {effective_retries}\n"
            f"[bold]Output JSON:[/bold] {output}\n"
            f"[bold]Export GLB:[/bold] {export_glb}\n"
            f"[bold]Export USDZ:[/bold] {export_usdz}",
            title="[cyan]Configurazione Pipeline[/cyan]",
            border_style="cyan",
        )
    )

    # Raccolta input
    try:
        if file:
            handler = InputHandler.from_file(file)
        elif description:
            handler = InputHandler.from_string(description)
        elif interactive:
            handler = InputHandler()
        else:
            console_err.print(
                "[bold red]Errore:[/bold red] Specificare una descrizione, "
                "usare --interactive o --file.",
            )
            raise SystemExit(1)
        scene_description = handler.get_description()
    except (ValueError, FileNotFoundError) as exc:
        console_err.print(f"[bold red]Errore input:[/bold red] {exc}")
        raise SystemExit(1) from exc

    console.print(
        Panel(
            f"[italic]{scene_description}[/italic]",
            title="[green]Scena da generare[/green]",
            border_style="green",
        )
    )

    # Pipeline principale
    try:
        objects = generate_scene_objects(
            scene_description=scene_description,
            model=effective_model,
            max_retries=effective_retries,
            ollama_url=effective_url,
            verbose=True,
        )
    except OllamaConnectionError as exc:
        console_err.print(
            f"[bold red]Errore connessione Ollama:[/bold red] {exc}",
        )
        console.print(
            f"\n[yellow]Suggerimento:[/yellow] Avviare Ollama con "
            f"[bold]ollama serve[/bold] e scaricare il modello con "
            f"[bold]ollama pull {effective_model}[/bold]."
        )
        raise SystemExit(1) from exc
    except RuntimeError as exc:
        console_err.print(f"\n[bold red]Errore pipeline:[/bold red] {exc}")
        raise SystemExit(1) from exc

    # Salvataggio JSON
    import json as _json  # noqa: PLC0415

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_data = [obj.model_dump() for obj in objects]
    with output_path.open("w", encoding="utf-8") as fp:
        _json.dump(output_data, fp, indent=2, ensure_ascii=False)

    console.print(
        Panel(
            f"[bold green]✓[/bold green] JSON salvato in: "
            f"[cyan]{output_path.resolve()}[/cyan]\n\n"
            f"[dim]Passo successivo --- costruisci la scena in Blender:[/dim]\n"
            f"[bold]blender --background --python scripts/blender_runner.py -- "
            f"{output_path}[/bold]",
            title="[green]Pipeline Completata[/green]",
            border_style="green",
        )
    )

    # Lancio automatico Blender
    if blender:
        import subprocess  # noqa: PLC0415

        cmd = [
            "blender",
            "--background",
            "--python",
            "scripts/blender_runner.py",
            "--",
            str(output_path),
        ]

        if render:
            cmd += ["--render", render_output]

        if export_glb:
            cmd += ["--export-3d", export_output, "--export-format", "glb"]
        elif export_usdz:
            cmd += ["--export-3d", export_output, "--export-format", "usdz"]

        console.print(
            f"\n[bold yellow]Lancio Blender...[/bold yellow]\n"
            f"[dim]{' '.join(cmd)}[/dim]"
        )
        result = subprocess.run(cmd, check=False)  # noqa: S603
        if result.returncode != 0:
            console_err.print(
                "[bold red]Blender ha terminato con errori.[/bold red]",
            )
            raise SystemExit(result.returncode)

        if render:
            render_path = Path(render_output)
            if render_path.exists():
                console.print(
                    f"\n[bold green]✓ Render 2D salvato:[/bold green] "
                    f"[cyan]{render_path.resolve()}[/cyan]"
                )

        if export_glb or export_usdz:
            fmt = "glb" if export_glb else "usdz"
            export_path = Path(export_output).with_suffix(f".{fmt}")
            if export_path.exists():
                console.print(
                    f"\n[bold green]✓ Scena 3D esportata ({fmt.upper()}):[/bold green] "
                    f"[cyan]{export_path.resolve()}[/cyan]"
                )


@main.command()
def info() -> None:
    """Mostra la configurazione corrente del sistema."""
    _setup_logging(False)
    cfg = ConfigLoader.load()

    from rich.table import Table  # noqa: PLC0415

    table = Table(title="Configurazione NL2Scene3D", border_style="cyan")
    table.add_column("Sezione", style="bold cyan")
    table.add_column("Chiave", style="yellow")
    table.add_column("Valore", style="white")

    def _flatten(d: dict, prefix: str = "") -> list[tuple[str, str, str]]:
        rows = []
        for k, v in d.items():
            if isinstance(v, dict):
                rows.extend(_flatten(v, prefix=k))
            else:
                rows.append((prefix, k, str(v)))
        return rows

    for section, key, value in _flatten(cfg):
        table.add_row(section, key, value)

    console.print(table)


@main.command()
def check() -> None:
    """Verifica i prerequisiti di sistema (Ollama, Blender, Python)."""
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    _setup_logging(False)
    _print_banner()

    from rich.table import Table  # noqa: PLC0415

    table = Table(title="Verifica Prerequisiti", border_style="blue")
    table.add_column("Componente", style="bold")
    table.add_column("Stato", justify="center")
    table.add_column("Dettaglio")

    # Python version
    py_ver = sys.version.split()[0]
    py_ok = tuple(int(x) for x in py_ver.split(".")) >= (3, 10)
    table.add_row(
        "Python",
        "[green]✓[/green]" if py_ok else "[red]✗[/red]",
        f"{py_ver} {'(OK)' if py_ok else '(richiesto >= 3.10)'}",
    )

    # Ollama
    from computer_graphics.ollama_client import OllamaClient  # noqa: PLC0415

    cfg = ConfigLoader.load()
    ollama_url = cfg.get("ollama", {}).get("url", "http://localhost:11434")
    client = OllamaClient(base_url=ollama_url)
    ollama_ok = client.health_check()
    models_str = ""
    if ollama_ok:
        try:
            models = client.list_models()
            models_str = f"{len(models)} modelli disponibili: {', '.join(models[:3])}"
        except Exception:  # noqa: BLE001
            models_str = "connesso"
    table.add_row(
        "Ollama",
        "[green]✓[/green]" if ollama_ok else "[red]✗[/red]",
        models_str if ollama_ok else f"Non raggiungibile su {ollama_url}",
    )

    # Blender
    blender_path = shutil.which("blender")
    blender_ok = blender_path is not None
    if blender_ok:
        try:
            result = subprocess.run(
                ["blender", "--version"],  # noqa: S603, S607
                capture_output=True,
                text=True,
                timeout=5,
            )
            blender_ver = result.stdout.split("\n")[0]
        except Exception:  # noqa: BLE001
            blender_ver = blender_path or ""
    else:
        blender_ver = "Non trovato nel PATH"

    table.add_row(
        "Blender",
        "[green]✓[/green]" if blender_ok else "[yellow]⚠[/yellow]",
        blender_ver,
    )

    # Assets directory
    assets_dir = Path(cfg.get("paths", {}).get("assets_dir", "assets/models"))
    assets_ok = assets_dir.exists()
    asset_count = len(list(assets_dir.glob("*.obj"))) if assets_ok else 0
    table.add_row(
        "Assets Directory",
        "[green]✓[/green]" if assets_ok else "[yellow]⚠[/yellow]",
        (
            f"{assets_dir} — {asset_count} file .obj trovati"
            if assets_ok
            else f"{assets_dir} non trovata"
        ),
    )

    console.print(table)

    # Suggerimenti
    if not ollama_ok:
        console.print("\n[yellow]→ Avviare Ollama:[/yellow] [bold]ollama serve[/bold]")
    if not blender_ok:
        console.print(
            "\n[yellow]→ Installare Blender:[/yellow] https://www.blender.org/download/"
        )
    if asset_count == 0:
        console.print(
            f"\n[yellow]→ Nessun asset .obj in {assets_dir}.[/yellow] "
            "Eseguire [bold]make generate-primitives[/bold] per creare asset di base."
        )


@main.command()
@click.argument("json_file", type=click.Path(exists=True))
def validate(json_file: str) -> None:
    """
    Valida un file JSON di oggetti scena esistente.

    Esempio:

        computer-graphics validate scene_objects.json
    """
    _setup_logging(False)

    from computer_graphics.validator import validate_objects  # noqa: PLC0415

    with open(json_file, encoding="utf-8") as fp:  # noqa: PTH123
        raw = json.load(fp)

    try:
        objects = validate_objects(raw)
        console.print(
            f"[bold green]✓ Validazione OK:[/bold green] "
            f"{len(objects)} oggetti validi in [cyan]{json_file}[/cyan]"
        )
        for obj in objects:
            console.print(
                f"  • [cyan]{obj.name}[/cyan] @ "
                f"({obj.x:.2f}, {obj.y:.2f}, {obj.z:.2f}) "
                f"scale={obj.scale:.2f}"
            )
    except ValueError as exc:
        console_err.print(f"[bold red]✗ Validazione fallita:[/bold red] {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
