"""
Orchestratore principale della pipeline NL2Scene3D.

Coordina le fasi 1-4:
    Input → Prompt → Ollama → Parsing → Validazione
con logica di retry automatico.
"""

from __future__ import annotations

import logging

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from computer_graphics.json_parser import JSONParseError, extract_json
from computer_graphics.ollama_client import OllamaClient, OllamaConnectionError
from computer_graphics.prompt_builder import PromptBuilder
from computer_graphics.validator import SceneObject, validate_objects

logger = logging.getLogger(__name__)
console = Console()


def generate_scene_objects(
    scene_description: str,
    model: str = "llama3",
    max_retries: int = 3,
    ollama_url: str = "http://localhost:11434",
    timeout: int = 180,
    verbose: bool = True,
) -> list[SceneObject]:
    """
    Funzione principale della pipeline.

    Prende una descrizione testuale e restituisce la lista
    di oggetti 3D validati pronti per Blender.

    Args:
        scene_description: Testo descrittivo della scena (linguaggio naturale).
        model: Nome del modello Ollama da usare.
        max_retries: Numero massimo di tentativi in caso di JSON non valido.
        ollama_url: URL del server Ollama.
        timeout: Secondi di timeout per la chiamata HTTP.
        verbose: Se True, stampa progress e risultati a terminale.

    Returns:
        Lista di SceneObject validati.

    Raises:
        OllamaConnectionError: Se Ollama non è raggiungibile dopo i retry.
        RuntimeError: Se dopo max_retries non si ottiene JSON valido.
    """
    client = OllamaClient(base_url=ollama_url, timeout=timeout)
    builder = PromptBuilder(model=model)

    # Verifica connessione Ollama
    if verbose:
        with console.status(
            "[bold yellow]Verifica connessione Ollama...[/bold yellow]"
        ):  # noqa: E501
            if not client.health_check():
                raise OllamaConnectionError(
                    "Ollama non risponde. Avviare con: ollama serve"
                )
        console.print("[bold green]✓[/bold green] Ollama connesso.")

    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        if verbose:
            console.print(
                f"\n[bold blue]Tentativo {attempt}/{max_retries}[/bold blue] "
                f"— Generazione scena con modello [cyan]{model}[/cyan]"
            )

        payload = builder.build(scene_description)

        # Chiamata al modello con spinner
        try:
            if verbose:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    progress.add_task(
                        description=f"Interrogazione {model}...", total=None
                    )
                    raw_text = client.chat(payload)
            else:
                raw_text = client.chat(payload)

        except OllamaConnectionError:
            raise  # Errori di rete non si risolvono con retry sul JSON

        # Parsing e validazione
        try:
            raw_objects = extract_json(raw_text)
            validated = validate_objects(raw_objects)

            if verbose:
                _print_results_table(validated)

            logger.info(
                "Pipeline completata: %d oggetti generati al tentativo %d.",
                len(validated),
                attempt,
            )
            return validated

        except (JSONParseError, ValueError) as exc:
            last_exception = exc
            logger.warning(
                "Tentativo %d/%d fallito: %s",
                attempt,
                max_retries,
                exc,
            )
            if verbose:
                console.print(
                    f"[bold red]✗[/bold red] Tentativo {attempt} fallito: {exc}"
                )

    raise RuntimeError(
        f"Impossibile generare oggetti validi dopo {max_retries} tentativi. "
        f"Ultimo errore: {last_exception}"
    ) from last_exception


def _print_results_table(objects: list[SceneObject]) -> None:
    """Stampa una tabella rich con i risultati."""
    table = Table(
        title="Oggetti generati",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Nome", style="cyan", no_wrap=True)
    table.add_column("X", justify="right")
    table.add_column("Y", justify="right")
    table.add_column("Z", justify="right")
    table.add_column("Rot Z (rad)", justify="right")
    table.add_column("Scale", justify="right")

    for obj in objects:
        table.add_row(
            obj.name,
            f"{obj.x:.3f}",
            f"{obj.y:.3f}",
            f"{obj.z:.3f}",
            f"{obj.rot_z:.3f}",
            f"{obj.scale:.2f}",
        )

    console.print(table)
    console.print(
        f"[bold green]✓[/bold green] {len(objects)} oggetti validati con successo."
    )
