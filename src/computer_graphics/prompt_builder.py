"""
Costruzione del prompt per il modello linguistico.

Il prompt engineering è la parte più critica della pipeline:
determina la qualità e la coerenza del JSON restituito dal modello.
"""

from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------------------
# Prompt di sistema — può essere caricato da file esterno
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_DEFAULT = r"""
Sei un assistente specializzato nella generazione di layout di scene 3D per Blender.

REGOLA ASSOLUTA: Rispondi ESCLUSIVAMENTE con un array JSON valido.
Non aggiungere MAI testo, spiegazioni, commenti, markdown o backtick prima o dopo il JSON.
Non usare commenti JavaScript (//) all'interno del JSON.
Il tuo output deve iniziare esattamente con [ e terminare esattamente con ].

Ogni elemento dell'array rappresenta un oggetto 3D e deve contenere ESATTAMENTE questi campi:
- "name"  : stringa, nome dell'oggetto in inglese minuscolo (es. "table", "chair", "lamp")
- "x"     : numero float, posizione sull'asse X in unità Blender (1 unità = 1 metro)
- "y"     : numero float, posizione sull'asse Y in unità Blender
- "z"     : numero float, posizione sull'asse Z (0.0 = sul pavimento)
- "rot_x" : numero float, rotazione attorno all'asse X in radianti
- "rot_y" : numero float, rotazione attorno all'asse Y in radianti
- "rot_z" : numero float, rotazione attorno all'asse Z in radianti
- "scale" : numero float, scala uniforme dell'oggetto (1.0 = dimensione normale)
- "parent" : stringa o null, nome dell'oggetto padre se gerarchico
- "material_semantics" : stringa o null, tipo materiale (es. "wood", "glass", "metal")

Vincoli spaziali:
- Posiziona gli oggetti in modo realistico, evitando sovrapposizioni.
- Il tavolo tipicamente è a (0.0, 0.0, 0.0). Gli altri oggetti si dispongono attorno.
- Una sedia davanti al tavolo: x circa 0.0, y circa -1.2.
- Una lampada in un angolo: x circa -2.0, y circa -2.0.
- Usa rot_z per orientare gli oggetti (es. 0.785 = 45 gradi, 1.571 = 90 gradi).
- I campi di rotazione sono 0.0 se l'oggetto non richiede orientamento specifico.

Esempio di output CORRETTO per "un tavolo con una sedia e una lampada":
[
  {"name": "table",  "x": 0.0,  "y": 0.0,  "z": 0.0, "rot_x": 0.0, "rot_y": 0.0, "rot_z": 0.0,   "scale": 1.0},  # noqa: E501
  {"name": "chair",  "x": 0.0,  "y": -1.2, "z": 0.0, "rot_x": 0.0, "rot_y": 0.0, "rot_z": 0.0,   "scale": 1.0},  # noqa: E501
  {"name": "lamp",   "x": -2.0, "y": -2.0, "z": 0.0, "rot_x": 0.0, "rot_y": 0.0, "rot_z": 0.785, "scale": 1.0}  # noqa: E501
]

Non includere oggetti non menzionati dall'utente.
Non inventare campi aggiuntivi non presenti nello schema.
"""  # noqa: E501


class PromptBuilder:
    """
    Costruisce il payload da inviare ad Ollama.

    Attributes:
        model: Nome del modello Ollama da utilizzare.
        system_prompt: Testo del prompt di sistema.
    """

    def __init__(
        self,
        model: str | None = None,
        system_prompt: str | None = None,
        system_prompt_file: str | Path | None = None,
    ) -> None:
        self.model = model
        self.system_prompt = self._load_system_prompt(system_prompt, system_prompt_file)

    # ------------------------------------------------------------------
    # Metodi pubblici
    # ------------------------------------------------------------------

    def build(self, scene_description: str) -> dict:
        """
        Costruisce il payload completo per la chiamata ad Ollama.

        Args:
            scene_description: Testo con la descrizione della scena.

        Returns:
            Dizionario compatibile con l'API /api/chat di Ollama.
        """
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": self.system_prompt,
                },
                {
                    "role": "user",
                    "content": scene_description,
                },
            ],
            "stream": False,
            "options": {
                "temperature": 0.2,  # bassa temperatura = output più deterministico
                "top_p": 0.9,
                "num_predict": 1024,  # limite token risposta
            },
        }

    # ------------------------------------------------------------------
    # Metodi privati
    # ------------------------------------------------------------------

    def _load_system_prompt(
        self,
        prompt_text: str | None,
        prompt_file: str | Path | None,
    ) -> str:
        """
        Carica il prompt di sistema con questa priorità:
        1. Testo esplicito passato come argomento
        2. File .txt specificato
        3. Prompt predefinito incluso nel codice
        """
        if prompt_text is not None:
            return prompt_text

        if prompt_file is not None:
            path = Path(prompt_file)
            if path.exists():
                return path.read_text(encoding="utf-8").strip()

        # Tentativo di caricamento dal percorso predefinito del progetto
        default_path = (
            Path(__file__).parent.parent.parent
            / "config"
            / "prompts"
            / "system_prompt.txt"
        )
        if default_path.exists():
            return default_path.read_text(encoding="utf-8").strip()

        return SYSTEM_PROMPT_DEFAULT
