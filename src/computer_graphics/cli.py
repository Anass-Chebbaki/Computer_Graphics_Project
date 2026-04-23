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
from computer_graphics.llm_client import LLMConnectionError
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
[dim]Natural Language -> 3D Scene Generator --- Powered by Ollama + Blender[/dim]
"""


def _setup_logging(verbose: bool) -> None:
    """Configura il logging con RichHandler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def _find_blender_path() -> str | None:
    """Trova il percorso dell'eseguibile Blender in modo cross-platform."""
    import shutil  # noqa: PLC0415
    import sys  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    # 1. Prova nel PATH standard
    path = shutil.which("blender")
    if path:
        return path

    # 2. Ricerca in percorsi comuni su Windows
    if sys.platform == "win32":
        common_paths = [
            Path("C:/Program Files/Blender Foundation"),
            Path("C:/Program Files (x86)/Blender Foundation"),
        ]
        found_versions = []
        for base in common_paths:
            if base.exists():
                # Glob ricorsivo limitato per trovare blender.exe nelle sottocartelle Blender X.Y
                for p in base.glob("Blender */blender.exe"):
                    found_versions.append(p)

        if found_versions:
            # Ritorna la versione più recente (ordinamento alfabetico delle cartelle)
            return str(sorted(found_versions)[-1])

    # 3. Ricerca su macOS
    if sys.platform == "darwin":
        mac_path = "/Applications/Blender.app/Contents/MacOS/Blender"
        if Path(mac_path).exists():
            return mac_path

    return None


def _print_banner() -> None:
    """Stampa il banner ASCII art del progetto."""
    console.print(BANNER)


def _select_model_interactively(ollama_url: str) -> str:
    """Permette all'utente di scegliere un modello Ollama da una lista."""
    from computer_graphics.ollama_client import OllamaClient  # noqa: PLC0415

    client = OllamaClient(base_url=ollama_url)
    try:
        with console.status(
            "[bold yellow]Recupero modelli disponibili...[/bold yellow]"
        ):
            models = client.list_models()
    except Exception as exc:
        console_err.print(
            f"[bold red]Errore nel recupero dei modelli:[/bold red] {exc}"
        )
        raise RuntimeError(
            f"Impossibile recuperare i modelli da Ollama: {exc}"
        ) from exc

    if not models:
        console_err.print(
            "[bold yellow]Nessun modello trovato in Ollama.[/bold yellow]"
        )
        raise RuntimeError(
            "Nessun modello trovato in Ollama. Eseguire 'ollama pull <model>' prima."
        )

    # Pulisce i nomi (alcuni hanno :latest, altri no)
    unique_models = sorted({m.split(":")[0] for m in models})

    console.print("\n[bold cyan]Modelli disponibili in Ollama:[/bold cyan]")
    for i, name in enumerate(unique_models, 1):
        console.print(f"  {i}. [green]{name}[/green]")

    choice = click.prompt(
        "\nSeleziona un modello (numero o nome)",
        default="1",
        type=str,
    )

    if str(choice).isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(unique_models):
            return unique_models[idx]

    return str(choice) if choice in unique_models else unique_models[0]


@click.group(invoke_without_command=True)
@click.version_option(version="1.0.0", prog_name="NL2Scene3D")
@click.pass_context
def main(ctx: click.Context) -> None:
    """
    NL2Scene3D --- Generazione automatica di scene 3D da linguaggio naturale.

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
@click.option("--model", "-m", default=None, show_default=True, help="Modello LLM.")
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
@click.option(
    "--preview",
    is_flag=True,
    help="Genera una mappa 2D (PNG) del layout prima di Blender.",
)
@click.option(
    "--preview-output",
    default="assets/renders/preview.png",
    show_default=True,
    help="Percorso output PNG dell'anteprima 2D.",
)
# ---- Opzioni Gemini ----
@click.option(
    "--gemini",
    is_flag=True,
    default=False,
    help=(
        "Usa Gemini 3.0 Flash come provider LLM al posto di Ollama. "
        "Richiede GEMINI_API_KEY nell'ambiente o in .env."
    ),
)
@click.option(
    "--gemini-api-key",
    default=None,
    envvar="GEMINI_API_KEY",
    help="Chiave API Google Gemini (alternativa a GEMINI_API_KEY env var).",
)
@click.option(
    "--gemini-model",
    default="gemini-3-flash-preview",
    show_default=True,
    help="Modello Gemini da utilizzare.",
)
# ---- Opzioni Critic Loop ----
@click.option(
    "--critic",
    is_flag=True,
    default=False,
    help=(
        "Attiva il critic loop visivo MLLM dopo il render preliminare. "
        "Richiede --blender e --render, e un client Gemini configurato."
    ),
)
@click.option(
    "--critic-iterations",
    default=2,
    show_default=True,
    type=int,
    help="Numero massimo di iterazioni del critic loop.",
)
# ---- Opzioni Poly Haven ----
@click.option(
    "--polyhaven",
    is_flag=True,
    default=False,
    help=(
        "Scarica asset PBR da Poly Haven (CC0) prima di avviare Blender. "
        "Sostituisce i modelli primitivi locali con modelli realistici."
    ),
)
@click.option(
    "--polyhaven-quality",
    default="2k",
    show_default=True,
    type=click.Choice(["1k", "2k", "4k"]),
    help="Qualità delle texture Poly Haven.",
)
@click.option(
    "--polyhaven-hdri",
    is_flag=True,
    default=False,
    help="Scarica e usa un HDRI da Poly Haven per l'illuminazione ambientale.",
)
# ---- Opzioni Constraint Solver ----
@click.option(
    "--no-constraint-solver",
    is_flag=True,
    default=False,
    help="Disabilita il ConstraintSolver deterministico (usa solo SceneGraph OBB).",
)
@click.option(
    "--room",
    is_flag=True,
    default=False,
    help="Genera automaticamente pavimenti e pareti (Room Mode).",
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
    preview: bool,
    preview_output: str,
    gemini: bool,
    gemini_api_key: str | None,
    gemini_model: str,
    critic: bool,
    critic_iterations: int,
    polyhaven: bool,
    polyhaven_quality: str,
    polyhaven_hdri: bool,
    no_constraint_solver: bool,
    room: bool,
) -> None:
    """Genera una scena 3D da una descrizione in linguaggio naturale.

    Esempi:

        computer-graphics generate "una cucina con tavolo e frigorifero"

        computer-graphics generate --interactive --model mistral

        computer-graphics generate "stanza" --blender --export-glb

        computer-graphics generate "studio" --gemini --polyhaven --critic \\
                --blender --render

        computer-graphics generate "ufficio" --gemini \\
                --gemini-api-key YOUR_KEY --critic --critic-iterations 3
    """
    _print_banner()
    _setup_logging(verbose)

    # Carica configurazione
    cfg = ConfigLoader.load()

    # Determina provider LLM
    effective_model = None
    effective_url = "-"
    
    # Se l'utente specifica opzioni Gemini, forziamo il provider
    if gemini or gemini_model != "gemini-3-flash-preview" or gemini_api_key:
        effective_provider = "gemini"
        effective_model = model or gemini_model
        api_key = gemini_api_key or cfg.get("llm", {}).get("api_key", "")
        if not api_key:
            console_err.print(
                "[bold red]Errore:[/bold red] Il provider Gemini richiede una chiave API. "
                "Usare --gemini-api-key oppure impostare GEMINI_API_KEY."
            )
            raise SystemExit(1)
        # Aggiorna config temporaneamente
        ConfigLoader.invalidate_cache()
        import os  # noqa: PLC0415
        os.environ["LLM_PROVIDER"] = "gemini"
        os.environ["LLM_API_KEY"] = api_key
        os.environ["LLM_MODEL"] = effective_model
    else:
        effective_provider = cfg.get("llm", {}).get("provider", "ollama")
        effective_url = ollama_url or cfg.get("ollama", {}).get("url")

    # Selezione definitiva del modello se non ancora individuato tramite flag/provider
    if not effective_model:
        if model:
            effective_model = model
        else:
            # Recupera dalla configurazione in base al provider effettivo
            if effective_provider == "gemini":
                effective_model = cfg.get("llm", {}).get("model", "gemini-3-flash-preview")
            else:
                effective_model = cfg.get("ollama", {}).get("model")

        # Se ancora nullo e siamo su Ollama, prova interattivo
        if not effective_model and effective_provider == "ollama":
            if not sys.stdin.isatty():
                effective_model = "llama3"
            else:
                effective_model = _select_model_interactively(
                    effective_url or "http://localhost:11434"
                )
        elif not effective_model:
            effective_model = "gemini-3-flash-preview"

    effective_retries = retries or cfg.get("pipeline", {}).get("max_retries") or 3

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

    if critic and not (blender and render):
        console_err.print(
            "[bold red]Errore:[/bold red] --critic richiede --blender e --render."
        )
        raise SystemExit(1)

    if critic and not gemini and not gemini_api_key:
        console_err.print(
            "[bold red]Errore:[/bold red] --critic richiede un client Gemini. "
            "Usare --gemini oppure impostare GEMINI_API_KEY."
        )
        raise SystemExit(1)

    console.print(
        Panel(
            f"[bold]Provider LLM:[/bold] {effective_provider}\n"
            f"[bold]Modello:[/bold] {effective_model}\n"
            f"[bold]Ollama URL:[/bold] {effective_url}\n"
            f"[bold]Max retry:[/bold] {effective_retries}\n"
            f"[bold]Output JSON:[/bold] {output}\n"
            f"[bold]Constraint Solver:[/bold] {not no_constraint_solver}\n"
            f"[bold]Poly Haven:[/bold] {polyhaven}\n"
            f"[bold]Critic Loop:[/bold] {critic} "
            f"(max {critic_iterations} iterazioni)\n"
            f"[bold]Export GLB:[/bold] {export_glb}\n"
            f"[bold]Export USDZ:[/bold] {export_usdz}",
            title="[cyan]Configurazione Pipeline[/cyan]",
            border_style="cyan",
        )
    )

    # Raccolta input (Auto-interactive se mancano argomenti)
    try:
        if file:
            handler = InputHandler.from_file(file)
        elif description:
            handler = InputHandler.from_string(description)
        elif interactive or sys.stdin.isatty():
            # Entra in modalità interattiva se richiesto o se siamo
            # in un terminale senza input
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
    assets_dir_str = cfg.get("paths", {}).get("assets_dir", "assets/models")

    try:
        objects = generate_scene_objects(
            scene_description=scene_description,
            model=effective_model,
            max_retries=effective_retries,
            ollama_url=(
                ollama_url or cfg.get("ollama", {}).get("url")
                if not gemini
                else None
            ),
            verbose=verbose,
            use_constraint_solver=not no_constraint_solver,
            assets_dir=assets_dir_str,
        )
    except LLMConnectionError as exc:
        console_err.print(
            f"[bold red]Errore connessione LLM:[/bold red] {exc}",
        )
        raise SystemExit(1) from exc
    except RuntimeError as exc:
        console_err.print(f"\n[bold red]Errore pipeline:[/bold red] {exc}")
        raise SystemExit(1) from exc

    # Poly Haven prefetch
    if polyhaven:
        _run_polyhaven_prefetch(
            objects=objects,
            assets_dir=assets_dir_str,
            quality=polyhaven_quality,
            download_hdri=polyhaven_hdri,
        )

    # Salvataggio JSON
    import json as _json  # noqa: PLC0415

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_data = [obj.model_dump() for obj in objects]
    with output_path.open("w", encoding="utf-8") as fp:
        _json.dump(output_data, fp, indent=2, ensure_ascii=False)

    # Tabella riassuntiva
    from rich.table import Table as _Table  # noqa: PLC0415

    table = _Table(
        title="[bold]Riepilogo Scena Generata[/bold]",
        box=None,
        header_style="bold magenta",
    )
    table.add_column("Nome", style="cyan")
    table.add_column("Posizione (X, Y, Z)", justify="right")
    table.add_column("Materiale", style="green")
    table.add_column("Parent", style="dim")

    for obj in objects:
        pos = f"({obj.x:.2f}, {obj.y:.2f}, {obj.z:.2f})"
        table.add_row(
            obj.name, pos, obj.material_semantics or "-", obj.parent or "-"
        )
    console.print(table)

    if preview:
        from computer_graphics.preview import generate_2d_preview  # noqa: PLC0415

        generate_2d_preview(objects, preview_output)

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

    # Lancio Blender
    if blender:
        import subprocess  # noqa: PLC0415

        blender_exe = _find_blender_path()
        if not blender_exe:
            console_err.print(
                "\n[bold red]Errore:[/bold red] Blender non trovato. "
                "Assicurarsi che sia installato o nel PATH."
            )
            raise SystemExit(1)

        cmd = [
            blender_exe,
            "--background",
            "--python",
            "scripts/blender_runner.py",
            "--",
            str(output_path),
            "--assets-dir",
            str(assets_dir_str),
        ]

        if room:
            cmd.append("--room-mode")

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
        result = subprocess.run(cmd, check=False)  # nosec B603
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

            # Critic loop visivo
            if critic and render_path.exists():
                _run_critic_loop(
                    objects=objects,
                    render_path=render_path,
                    scene_description=scene_description,
                    output_path=output_path,
                    gemini_api_key=gemini_api_key or "",
                    gemini_model=gemini_model,
                    max_iterations=critic_iterations,
                    verbose=verbose,
                )

        if export_glb or export_usdz:
            fmt = "glb" if export_glb else "usdz"
            export_path = Path(export_output).with_suffix(f".{fmt}")
            if export_path.exists():
                console.print(
                    f"\n[bold green]✓ Scena 3D esportata ({fmt.upper()}):[/bold green] "
                    f"[cyan]{export_path.resolve()}[/cyan]"
                )


def _run_polyhaven_prefetch(
    objects: list,
    assets_dir: str,
    quality: str,
    download_hdri: bool,
) -> None:
    """
    Pre-scarica asset Poly Haven per gli oggetti nella scena.

    Args:
        objects: Lista di SceneObject da preparare.
        assets_dir: Directory degli asset locale.
        quality: Qualità dei modelli (``"1k"``, ``"2k"``, ``"4k"``).
        download_hdri: Se True, scarica anche un HDRI.
    """
    from computer_graphics.poly_haven_catalog import (  # noqa: PLC0415
        PolyHavenCatalog,
    )

    assets_path = Path(assets_dir)
    catalog = PolyHavenCatalog(cache_dir=assets_path, quality=quality)

    asset_names = list({obj.name for obj in objects})

    console.print(
        f"\n[bold yellow]Poly Haven: download di {len(asset_names)} asset "
        f"in qualità {quality}...[/bold yellow]"
    )

    with console.status("[bold yellow]Download in corso...[/bold yellow]"):
        results = catalog.prefetch_assets(asset_names)

    found = sum(1 for v in results.values() if v is not None)
    console.print(
        f"[bold green]Poly Haven:[/bold green] {found}/{len(asset_names)} "
        f"asset scaricati in [cyan]{assets_path}[/cyan]"
    )

    if download_hdri:
        with console.status("[bold yellow]Download HDRI...[/bold yellow]"):
            hdri_path = catalog.get_hdri_path(category="indoor")
        if hdri_path:
            console.print(
                f"[bold green]HDRI scaricata:[/bold green] "
                f"[cyan]{hdri_path}[/cyan]"
            )
        else:
            console.print(
                "[bold yellow]HDRI non disponibile. "
                "Verrà usata l'illuminazione di default.[/bold yellow]"
            )


def _run_critic_loop(
    objects: list,
    render_path: Path,
    scene_description: str,
    output_path: Path,
    gemini_api_key: str,
    gemini_model: str,
    max_iterations: int,
    verbose: bool,
) -> None:
    """
    Esegue il critic loop visivo con Gemini Vision.

    Args:
        objects: Lista di SceneObject correnti.
        render_path: Percorso al render PNG preliminare.
        scene_description: Descrizione testuale della scena.
        output_path: Percorso al file JSON di output da aggiornare.
        gemini_api_key: Chiave API Google Gemini.
        gemini_model: Nome del modello Gemini Vision.
        max_iterations: Numero massimo di iterazioni critic.
        verbose: Se True, stampa dettagli a terminale.
    """
    from computer_graphics.critic_loop import CriticLoop  # noqa: PLC0415
    from computer_graphics.gemini_client import GeminiClient  # noqa: PLC0415

    if not gemini_api_key:
        console.print(
            "[bold yellow]Critic loop: nessuna chiave Gemini disponibile. "
            "Skip.[/bold yellow]"
        )
        return

    console.print(
        f"\n[bold cyan]Avvio critic loop visivo "
        f"(max {max_iterations} iterazioni)...[/bold cyan]"
    )

    gemini_client = GeminiClient(
        api_key=gemini_api_key,
        model=gemini_model,
    )
    critic = CriticLoop(
        gemini_client=gemini_client,
        max_iterations=max_iterations,
    )

    with console.status(
        "[bold yellow]Analisi visiva del render in corso...[/bold yellow]"
    ):
        corrected_objects, results = critic.run(
            objects=objects,
            render_path=render_path,
            scene_description=scene_description,
        )

    total_corrections = sum(len(r.corrections) for r in results)
    console.print(
        f"[bold green]Critic loop completato:[/bold green] "
        f"{len(results)} iterazioni, "
        f"{total_corrections} correzioni applicate."
    )

    if total_corrections > 0:
        # Aggiorna il file JSON con gli oggetti corretti
        import json as _json  # noqa: PLC0415

        output_data = [obj.model_dump() for obj in corrected_objects]
        with output_path.open("w", encoding="utf-8") as fp:
            _json.dump(output_data, fp, indent=2, ensure_ascii=False)
        console.print(
            f"[bold green]JSON aggiornato con correzioni critic:[/bold green] "
            f"[cyan]{output_path.resolve()}[/cyan]"
        )

        if verbose:
            for i, result in enumerate(results, 1):
                if result.has_corrections:
                    console.print(
                        f"\n[dim]Iterazione {i}: "
                        f"{len(result.corrections)} correzioni[/dim]"
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
    """Verifica i prerequisiti di sistema (Ollama, Gemini, Blender, Python)."""
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
            models_str = (
                f"{len(models)} modelli disponibili: {', '.join(models[:3])}"
            )
        except Exception:  # noqa: BLE001
            models_str = "connesso"
    table.add_row(
        "Ollama",
        "[green]✓[/green]" if ollama_ok else "[red]✗[/red]",
        models_str if ollama_ok else f"Non raggiungibile su {ollama_url}",
    )

    # Gemini
    gemini_key = cfg.get("llm", {}).get("api_key", "") or ""
    if not gemini_key:
        import os  # noqa: PLC0415

        gemini_key = os.environ.get("GEMINI_API_KEY", "")
    gemini_configured = bool(gemini_key)
    if gemini_configured:
        from computer_graphics.gemini_client import GeminiClient  # noqa: PLC0415

        gemini_client = GeminiClient(api_key=gemini_key)
        gemini_ok = gemini_client.health_check()
    else:
        gemini_ok = False
    table.add_row(
        "Gemini API",
        "[green]✓[/green]" if gemini_ok else "[yellow]⚠[/yellow]",
        (
            f"Connesso ({cfg.get('llm', {}).get('model', 'gemini-3-flash-preview')})"
            if gemini_ok
            else (
                "API key non configurata (impostare GEMINI_API_KEY)"
                if not gemini_configured
                else "API key configurata ma non raggiungibile"
            )
        ),
    )

    # Blender discovery
    blender_path = _find_blender_path()
    blender_ok = blender_path is not None
    if blender_ok:
        try:
            result = subprocess.run(
                ["blender", "--version"],  # nosec B603 B607
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
    glb_count = len(list(assets_dir.glob("*.glb"))) if assets_ok else 0
    table.add_row(
        "Assets Directory",
        "[green]✓[/green]" if assets_ok else "[yellow]⚠[/yellow]",
        (
            f"{assets_dir} — {asset_count} .obj, {glb_count} .glb"
            if assets_ok
            else f"{assets_dir} non trovata"
        ),
    )

    # Poly Haven connectivity
    try:
        import requests  # noqa: PLC0415

        ph_response = requests.get(
            "https://api.polyhaven.com/assets?t=models&limit=1", timeout=5
        )
        ph_ok = ph_response.status_code == 200
    except Exception:  # noqa: BLE001
        ph_ok = False
    table.add_row(
        "Poly Haven API",
        "[green]✓[/green]" if ph_ok else "[yellow]⚠[/yellow]",
        "Raggiungibile (CC0 assets)" if ph_ok else "Non raggiungibile",
    )

    console.print(table)

    if not ollama_ok and not gemini_ok:
        console.print(
            "\n[yellow]-> Nessun provider LLM disponibile.[/yellow]\n"
            "   Avviare Ollama: [bold]ollama serve[/bold]\n"
            "   oppure configurare Gemini: [bold]export GEMINI_API_KEY=...[/bold]"
        )
    if not blender_ok:
        console.print(
            "\n[yellow]-> Installare Blender:[/yellow] "
            "https://www.blender.org/download/"
        )
    if asset_count == 0 and glb_count == 0:
        console.print(
            f"\n[yellow]-> Nessun asset in {assets_dir}.[/yellow] "
            "Eseguire [bold]make generate-primitives[/bold] "
            "o usare [bold]--polyhaven[/bold] per scaricare asset realistici."
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
            console_err.print(
                f"  • [cyan]{obj.name}[/cyan] @ "
                f"({obj.x:.2f}, {obj.y:.2f}, {obj.z:.2f}) "
                f"scale={obj.scale:.2f}"
            )
    except ValueError as exc:
        console_err.print(f"[bold red]✗ Validazione fallita:[/bold red] {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
