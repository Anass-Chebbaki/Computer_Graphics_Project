#!/usr/bin/env python3
"""
Script principale della pipeline NL2Scene3D.

Uso:
    python scripts/run_pipeline.py "una stanza con tavolo e sedia"
    python scripts/run_pipeline.py --interactive
    python scripts/run_pipeline.py --file descrizione.txt --model mistral
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler

# Aggiunge src al path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from computer_graphics.input_handler import InputHandler
from computer_graphics.ollama_client import OllamaConnectionError
from computer_graphics.orchestrator import generate_scene_objects

console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@click.command()
@click.argument("description", required=False, default=None)
@click.option(
    "--interactive", "-i",
    is_flag=True,
    help="Chiede la descrizione interattivamente.",
)
@click.option(
    "--file", "-f",
    type=click.Path(exists=True),
    help="Legge la descrizione da file .txt.",
)
@click.option(
    "--model", "-m",
    default="llama3",
    show_default=True,
    help="Nome del modello Ollama da usare.",
)
@click.option(
    "--output", "-o",
    default="scene_objects.json",
    show_default=True,
    help="File JSON di output con gli oggetti generati.",
)
@click.option(
    "--retries", "-r",
    default=3,
    show_default=True,
    help="Numero massimo di tentativi.",
)
@click.option(
    "--ollama-url",
    default="http://localhost:11434",
    show_default=True,
    help="URL del server Ollama.",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Output di debug dettagliato.",
)
def main(
    description: str | None,
    interactive: bool,
    file: str | None,
    model: str,
    output: str,
    retries: int,
    ollama_url: str,
    verbose: bool,
) -> None:
    """
    NL2Scene3D — Generazione automatica di scene 3D da linguaggio naturale.

    Esempi:

        nl2scene3d "una stanza con tavolo, sedia e lampada"

        nl2scene3d --interactive --model mistral

        nl2scene3d --file scene.txt --output objects.json
    """
    _setup_logging(verbose)

    # Raccolta input
    try:
        if file:
            handler = InputHandler.from_file(file)
        elif description:
            handler = InputHandler.from_string(description)
        elif interactive:
            handler = InputHandler()
        else:
            console.print(
                "[bold red]Errore:[/bold red] Fornire una descrizione, "
                "usare --interactive o --file.",
                err=True,
            )
            raise SystemExit(1)

        scene_description = handler.get_description()

    except (ValueError, FileNotFoundError) as exc:
        console.print(f"[bold red]Errore input:[/bold red] {exc}", err=True)
        raise SystemExit(1) from exc

    console.print(
        f"\n[bold]Scena da generare:[/bold] [italic]{scene_description}[/italic]\n"
    )

    # Esecuzione pipeline
    try:
        objects = generate_scene_objects(
            scene_description=scene_description,
            model=model,
            max_retries=retries,
            ollama_url=ollama_url,
            verbose=True,
        )
    except OllamaConnectionError as exc:
        console.print(f"\n[bold red]Errore connessione Ollama:[/bold red] {exc}", err=True)
        console.print(
            "\n[yellow]Suggerimento:[/yellow] Avviare Ollama con [bold]ollama serve[/bold] "
            "e scaricare il modello con [bold]ollama pull llama3[/bold]."
        )
        raise SystemExit(1) from exc
    except RuntimeError as exc:
        console.print(f"\n[bold red]Errore pipeline:[/bold red] {exc}", err=True)
        raise SystemExit(1) from exc

    # Salvataggio output JSON
    output_path = Path(output)
    output_data = [obj.model_dump() for obj in objects]

    with output_path.open("w", encoding="utf-8") as fp:
        json.dump(output_data, fp, indent=2, ensure_ascii=False)

    console.print(
        f"\n[bold green]✓[/bold green] Output salvato in: [cyan]{output_path.resolve()}[/cyan]"
    )
    console.print(
        "\n[dim]Passo successivo:[/dim] Eseguire Blender con:\n"
        f"  [bold]blender --background --python scripts/blender_runner.py "
        f"-- {output_path}[/bold]"
    )


if __name__ == "__main__":
    main()