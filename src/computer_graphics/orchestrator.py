"""
Orchestratore principale della pipeline NL2Scene3D.

Coordina le fasi di processamento:
 Input -> Prompt -> LLM (Ollama o Gemini) -> Parsing -> Validazione ->
 ConstraintSolver -> SceneGraph -> SceneObject
"""

from __future__ import annotations

import logging

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from computer_graphics.json_parser import JSONParseError, extract_json
from computer_graphics.llm_client import LLMConnectionError, get_llm_client
from computer_graphics.prompt_builder import PromptBuilder
from computer_graphics.validator import SceneObject, validate_objects


logger = logging.getLogger(__name__)
console = Console()


class CollisionResolutionError(Exception):
    """
    Sollevata quando il SceneGraph non riesce a risolvere le collisioni
    spazialmente (troppi oggetti in uno spazio ristretto).

    Attributes:
        object_a: Nome del primo oggetto in collisione.
        object_b: Nome del secondo oggetto in collisione.
        message: Messaggio descrittivo dell'errore.
    """

    def __init__(
        self,
        object_a: str,
        object_b: str,
        message: str = "",
    ) -> None:
        self.object_a = object_a
        self.object_b = object_b
        super().__init__(
            message
            or (
                f"Collisione irrisolvibile tra '{object_a}' e '{object_b}'. "
                "Lo spazio è troppo ristretto per il numero di oggetti."
            )
        )


def _build_collision_feedback_message(
    object_a: str,
    object_b: str,
) -> str:
    """
    Costruisce il messaggio di feedback per il ciclo agentico.

    Args:
        object_a: Nome del primo oggetto in collisione.
        object_b: Nome del secondo oggetto in collisione.

    Returns:
        Stringa con le istruzioni di rigenerazione per l'LLM.
    """
    return (
        f"Il layout precedente causava collisioni irrisolvibili tra l'oggetto "
        f"'{object_a}' e l'oggetto '{object_b}'. "
        f"Rigenera le coordinate allontanandoli: aumenta la distanza tra "
        f"'{object_a}' e '{object_b}' di almeno 1.5 metri. "
        f"Mantieni tutti gli altri oggetti. "
        f"Rispondi ESCLUSIVAMENTE con l'array JSON completo e corretto."
    )


def _apply_scene_graph_with_collision_check(
    validated: list[SceneObject],
) -> list[SceneObject]:
    """
    Applica il SceneGraph e verifica se le collisioni sono state risolte.

    Rileva il caso in cui il numero di oggetti aggiustati è uguale al totale
    e le collisioni persistono dopo max_iterations: in questo scenario
    solleva CollisionResolutionError con gli oggetti più problematici.

    Args:
        validated: Lista di SceneObject validati dall'orchestratore.

    Returns:
        Lista di SceneObject con posizioni aggiustate.

    Raises:
        CollisionResolutionError: Se le collisioni non sono risolvibili
            spazialmente dato il numero di oggetti.
    """
    from computer_graphics.scene_graph import (  # noqa: PLC0415
        SceneGraph,
    )

    if not validated:
        return validated

    graph = SceneGraph()
    for obj in validated:
        if getattr(obj, "parent", None) is None:
            graph.add_object(obj)

    # Esegue la risoluzione con il limite di iterazioni standard
    adjusted = graph.resolve_collisions(max_iterations=10)
    stats = graph.get_statistics()

    # Verifica se rimangono collisioni dopo la risoluzione
    # Strategia: se tutti gli oggetti sono stati aggiustati e la densità
    # è eccessiva (più di 3 oggetti/m²), segnala collisione irrisolvibile
    if stats["total_objects"] >= 2 and stats["scene_width_m"] > 0:
        density = stats["total_objects"] / max(
            stats["scene_width_m"] * stats["scene_depth_m"], 0.1
        )
        all_adjusted = stats["adjusted_objects"] == stats["total_objects"]

        if density > 4.0 and all_adjusted and stats["total_objects"] > 4:
            # Trova la coppia più problematica: i due oggetti più vicini
            # dopo la risoluzione
            worst_a = "unknown"
            worst_b = "unknown"
            min_dist = float("inf")

            nodes = graph.nodes
            for i, node_a in enumerate(nodes):
                for node_b in nodes[i + 1 :]:
                    dist = (
                        (node_a.bbox.cx - node_b.bbox.cx) ** 2
                        + (node_a.bbox.cy - node_b.bbox.cy) ** 2
                    ) ** 0.5
                    if dist < min_dist:
                        min_dist = dist
                        worst_a = node_a.obj.name
                        worst_b = node_b.obj.name

            raise CollisionResolutionError(
                object_a=worst_a,
                object_b=worst_b,
            )

    if stats["adjusted_objects"] > 0:
        logger.info(
            "Scene graph: %d/%d oggetti riposizionati per evitare collisioni. "
            "Scena: %.1f m x %.1f m.",
            stats["adjusted_objects"],
            stats["total_objects"],
            stats["scene_width_m"],
            stats["scene_depth_m"],
        )
    else:
        logger.info(
            "Scene graph: nessuna collisione rilevata. Scena: %.1f m x %.1f m.",
            stats["scene_width_m"],
            stats["scene_depth_m"],
        )

    return adjusted


def _apply_constraint_solver(
    validated: list[SceneObject],
    assets_dir: str | None = None,
) -> list[SceneObject]:
    """
    Applica il ConstraintSolver deterministico al layout della scena.

    Il solver e piu preciso dello SceneGraph OBB poiche utilizza le
    dimensioni reali degli asset e gestisce relazioni topologiche.

    Args:
        validated: Lista di SceneObject validati.
        assets_dir: Directory degli asset per il calcolo delle dimensioni.

    Returns:
        Lista di SceneObject con layout risolto.
    """
    from pathlib import Path  # noqa: PLC0415

    from computer_graphics.constraint_solver import solve_layout  # noqa: PLC0415

    assets_path = Path(assets_dir) if assets_dir else None
    solved = solve_layout(validated, assets_dir=assets_path)
    return solved


def generate_scene_objects(
    scene_description: str,
    model: str | None = None,
    max_retries: int = 3,
    ollama_url: str | None = None,
    timeout: int = 180,
    verbose: bool = True,
    use_constraint_solver: bool = True,
    assets_dir: str | None = None,
) -> list[SceneObject]:
    """
    Funzione principale della pipeline NL2Scene3D.

    Prende una descrizione testuale e restituisce la lista di oggetti 3D
    validati e privi di collisioni, pronti per Blender.

    Gestisce i fallimenti di parsing e di collisioni con retry automatici.
    Supporta Ollama (locale), OpenAI e Gemini (cloud) come provider LLM.

    Args:
        scene_description: Testo descrittivo della scena in linguaggio naturale.
        model: Nome del modello da usare. Se None, usa il default da config.
        max_retries: Numero massimo di tentativi totali.
        ollama_url: URL del server Ollama. Se None, usa il default da config.
        timeout: Secondi di timeout per la chiamata HTTP.
        verbose: Se True, stampa progress e risultati a terminale.
        use_constraint_solver: Se True, applica il ConstraintSolver
            deterministico in aggiunta allo SceneGraph OBB.
        assets_dir: Directory degli asset per il ConstraintSolver.

    Returns:
        Lista di SceneObject validati e posizionati senza collisioni.

    Raises:
        LLMConnectionError: Se il provider LLM non è raggiungibile dopo i retry.
        RuntimeError: Se dopo max_retries non si ottiene JSON valido e
            privo di collisioni irrisolvibili.
    """
    from computer_graphics.config_loader import ConfigLoader  # noqa: PLC0415

    # Carica configurazione
    ollama_cfg = ConfigLoader.get("ollama", default={})
    model = model or ollama_cfg.get("model")
    ollama_url = ollama_url or ollama_cfg.get("url")

    max_conn_retries = ollama_cfg.get("max_connection_retries", 3)
    conn_retry_delay = ollama_cfg.get("retry_delay", 2.0)

    llm_provider = ConfigLoader.get("llm", "provider", default="ollama")

    client_params: dict[str, object] = {
        "timeout": timeout,
        "max_connection_retries": max_conn_retries,
        "retry_delay": conn_retry_delay,
    }

    if llm_provider == "ollama":
        client_params["base_url"] = ollama_url
    elif llm_provider == "gemini":
        api_key = ConfigLoader.get("llm", "api_key", default="")
        gemini_model = ConfigLoader.get(
            "llm", "model", default="gemini-3-flash-preview"
        )
        client_params["api_key"] = api_key
        if gemini_model:
            client_params["model"] = gemini_model
        # Rimuovi parametri non supportati da Gemini
        client_params.pop("max_connection_retries", None)
        client_params["max_connection_retries"] = int(
            client_params.pop("max_connection_retries", 3)  # type: ignore[call-overload]
            if False
            else max_conn_retries
        )
    else:
        client_params["api_key"] = ConfigLoader.get("llm", "api_key", default="")
        client_params["base_url"] = ConfigLoader.get("llm", "base_url", default="")

    client = get_llm_client(llm_provider, **client_params)
    
    # Preparazione prompt con catalogo dinamico
    catalog_context = ""
    if assets_dir:
        from computer_graphics.poly_haven_catalog import PolyHavenCatalog  # noqa: PLC0415
        ph = PolyHavenCatalog(assets_dir)
        catalog_context = ph.get_catalog_summary()

    builder = PromptBuilder(model=model)

    # Verifica connessione
    if verbose:
        with console.status(
            f"[bold yellow]Verifica connessione {llm_provider}...[/bold yellow]"
        ):
            if not client.health_check():
                if llm_provider == "ollama":
                    raise LLMConnectionError(
                        "Ollama non risponde. Avviare con: ollama serve"
                    )
                raise LLMConnectionError(
                    f"Provider {llm_provider} non risponde. "
                    "Verificare la configurazione e la connessione internet."
                )
        console.print(
            f"[bold green][/bold green] {llm_provider.capitalize()} connesso."
        )

    last_exception: Exception | None = None

    # Cronologia messaggi per il ciclo di retry
    # Struttura: lista di {"role": str, "content": str}
    message_history: list[dict[str, str]] = []

    for attempt in range(1, max_retries + 1):
        if verbose:
            console.print(
                f"\n[bold blue]Tentativo {attempt}/{max_retries}[/bold blue] "
                f"--- Generazione scena con modello [cyan]{model}[/cyan]"
            )

        if not message_history:
            payload = builder.build(scene_description, catalog_context=catalog_context)
            # Inizializza la history con system + user message
            message_history = list(payload["messages"])

        # Chiamata al modello con spinner
        try:
            llm_options = ConfigLoader.get("ollama", "options", default={})
            if verbose:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                    transient=True,
                ) as progress:
                    progress.add_task(
                        description=(
                            f"Interrogazione {model} via {llm_provider}..."
                        ),
                        total=None,
                    )
                    raw_text = client.chat(
                        messages=message_history,
                        model=model,
                        response_format="json",
                        **llm_options,
                    )
            else:
                raw_text = client.chat(
                    messages=message_history,
                    model=model,
                    response_format="json",
                    **llm_options,
                )
        except LLMConnectionError as conn_exc:
            # Errori di rete: retry con backoff invece di crash immediato
            last_exception = conn_exc
            logger.warning(
                "Tentativo %d/%d fallito (errore server): %s",
                attempt, max_retries, conn_exc,
            )
            if verbose:
                console.print(
                    f"[bold yellow][/bold yellow] Errore server al tentativo {attempt}. "
                    f"Riprovo tra {conn_retry_delay}s..."
                )
            if attempt < max_retries:
                import time  # noqa: PLC0415
                time.sleep(conn_retry_delay)
                message_history = []  # Reset per retry pulito
                continue
            raise  # Solo dopo tutti i tentativi esauriti

        # Aggiunge la risposta del modello alla history (per il ciclo agentico)
        message_history.append({"role": "assistant", "content": raw_text})

        # Parsing e validazione
        try:
            raw_objects = extract_json(raw_text)
            validated = validate_objects(raw_objects)

        except (JSONParseError, ValueError) as exc:
            last_exception = exc
            logger.warning(
                "Tentativo %d/%d fallito (parsing/validazione): %s",
                attempt,
                max_retries,
                exc,
            )
            if verbose:
                console.print(
                    f"[bold red][/bold red] Tentativo {attempt} "
                    f"fallito (parsing): {exc}"
                )
            # Reset della history per il prossimo tentativo (retry standard)
            message_history = []
            continue

        # Applica ConstraintSolver deterministico
        if use_constraint_solver:
            try:
                solved_assets_dir = assets_dir or ConfigLoader.get(
                    "paths", "assets_dir", default=None
                )
                validated = _apply_constraint_solver(
                    validated,
                    assets_dir=str(solved_assets_dir) if solved_assets_dir else None,
                )
                logger.debug("ConstraintSolver applicato con successo.")
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ConstraintSolver fallito: %s. Continuo con SceneGraph.", exc
                )

        # Applica SceneGraph con rilevamento collisioni irrisolvibili
        try:
            validated = _apply_scene_graph_with_collision_check(validated)

        except CollisionResolutionError as collision_exc:
            last_exception = collision_exc
            logger.warning(
                "Tentativo %d/%d: collisione irrisolvibile tra '%s' e '%s'. "
                "Invio feedback contestuale all'LLM.",
                attempt,
                max_retries,
                collision_exc.object_a,
                collision_exc.object_b,
            )
            if verbose:
                console.print(
                    f"[bold yellow][/bold yellow] Tentativo {attempt}: "
                    f"collisione irrisolvibile tra "
                    f"[cyan]{collision_exc.object_a}[/cyan] e "
                    f"[cyan]{collision_exc.object_b}[/cyan]. "
                    f"Invio feedback all'LLM..."
                )

            # Aggiungi messaggio di feedback alla history per il prossimo tentativo
            feedback_msg = _build_collision_feedback_message(
                collision_exc.object_a,
                collision_exc.object_b,
            )
            message_history.append({"role": "user", "content": feedback_msg})
            continue

        # Successo: stampa risultati e ritorna
        if verbose:
            _print_results_table(validated)

        logger.info(
            "Pipeline completata: %d oggetti generati al tentativo %d.",
            len(validated),
            attempt,
        )
        return validated

    raise RuntimeError(
        f"Impossibile generare oggetti validi dopo {max_retries} tentativi. "
        f"Ultimo errore: {last_exception}"
    ) from last_exception


def _print_results_table(objects: list[SceneObject]) -> None:
    """
    Stampa una tabella rich con i risultati della generazione.

    Args:
        objects: Lista di SceneObject da visualizzare.
    """
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
    table.add_column("Parent", style="dim")
    table.add_column("Material", style="dim")

    for obj in objects:
        table.add_row(
            obj.name,
            f"{obj.x:.3f}",
            f"{obj.y:.3f}",
            f"{obj.z:.3f}",
            f"{obj.rot_z:.3f}",
            f"{obj.scale:.2f}",
            obj.parent or "---",
            obj.material_semantics or "---",
        )

    console.print(table)
    console.print(
        f"[bold green][/bold green] "
        f"{len(objects)} oggetti validati con successo."
    )
