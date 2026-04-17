"""
Gestione dell'input utente.

Raccoglie e normalizza la descrizione testuale della scena.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

console = Console()


class InputHandler:
    """
    Gestisce la ricezione della descrizione testuale della scena.

    Supporta tre modalità:
        - stringa diretta (hardcoded o da codice)
        - input interattivo da terminale
        - lettura da file .txt
    """

    MIN_DESCRIPTION_LENGTH: int = 10
    MAX_DESCRIPTION_LENGTH: int = 2000

    def __init__(self, description: str | None = None) -> None:
        self._description: str | None = description

    # ------------------------------------------------------------------
    # Metodi pubblici
    # ------------------------------------------------------------------

    def get_description(self) -> str:
        """
        Restituisce la descrizione della scena.

        Se non è stata fornita in costruzione, la richiede
        interattivamente all'utente via terminale.

        Returns:
            Stringa con la descrizione testuale normalizzata.

        Raises:
            ValueError: Se la descrizione è troppo corta o troppo lunga.
        """
        if self._description is not None:
            return self._validate_and_clean(self._description)

        return self._prompt_user()

    @classmethod
    def from_string(cls, description: str) -> InputHandler:
        """Factory: crea un handler con descrizione predefinita."""
        return cls(description=description)

    @classmethod
    def from_file(cls, filepath: str | Path) -> InputHandler:
        """
        Factory: legge la descrizione da un file di testo.

        Args:
            filepath: Percorso al file .txt contenente la descrizione.

        Returns:
            InputHandler con la descrizione letta dal file.

        Raises:
            FileNotFoundError: Se il file non esiste.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(
                f"File di descrizione non trovato: {path.resolve()}"
            )
        description = path.read_text(encoding="utf-8").strip()
        return cls(description=description)

    # ------------------------------------------------------------------
    # Metodi privati
    # ------------------------------------------------------------------

    def _prompt_user(self) -> str:
        """Richiede la descrizione interattivamente."""
        console.print(
            "\n[bold cyan]NL2Scene3D[/bold cyan] — "
            "Generazione automatica di scene 3D\n"
        )
        console.print(
            "Descrivi la scena che vuoi generare.\n"
            "[dim]Esempio: una stanza con tavolo, sedia e lampada da terra[/dim]\n"
        )
        raw = Prompt.ask("[bold green]Descrizione scena[/bold green]")
        return self._validate_and_clean(raw)

    def _validate_and_clean(self, text: str) -> str:
        """
        Normalizza e valida la stringa di input.

        Args:
            text: Testo grezzo dell'utente.

        Returns:
            Testo normalizzato.

        Raises:
            ValueError: Se il testo non rispetta i vincoli di lunghezza.
        """
        cleaned = " ".join(text.strip().split())

        if len(cleaned) < self.MIN_DESCRIPTION_LENGTH:
            raise ValueError(
                f"Descrizione troppo breve (min {self.MIN_DESCRIPTION_LENGTH} caratteri). "  # noqa: E501
                f"Fornire più dettagli sulla scena desiderata."
            )

        if len(cleaned) > self.MAX_DESCRIPTION_LENGTH:
            raise ValueError(
                f"Descrizione troppo lunga (max {self.MAX_DESCRIPTION_LENGTH} caratteri). "  # noqa: E501
                f"Lunghezza attuale: {len(cleaned)} caratteri."
            )

        return cleaned
