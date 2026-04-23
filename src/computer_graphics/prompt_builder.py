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
Sei un architetto d'interni professionista che progetta scene 3D realistiche per Blender.
Devi creare un layout di arredamento coerente, realistico e stilisticamente uniforme.

FORMATO OUTPUT: Rispondi SOLO con un array JSON valido. Nessun testo aggiuntivo.
Inizia con [ e termina con ].

CAMPI PER OGNI OGGETTO:
{
  "name": "slug_from_catalog",
  "x": 0.0, "y": 0.0, "z": 0.0,
  "rot_x": 0.0, "rot_y": 0.0, "rot_z": 0.0,
  "scale": 1.0,
  "parent": null,
  "material_semantics": "wood"
}

REGOLA CRITICA SUI NOMI:
- Il campo "name" DEVE essere uno slug esatto dalla lista ASSET DISPONIBILI sotto.
- Se la lista contiene "sofa_03 (antique, leather)", usa "sofa_03" come name.
- NON usare nomi generici come "sofa" o "table". Usa SEMPRE lo slug specifico.
- Se non trovi un asset adatto nella lista, scegli quello più simile tra quelli disponibili.

COORDINATE E ORIENTAMENTO (sistema Blender, 1 unità = 1 metro):
- X = destra/sinistra. Y = avanti/dietro. Z = alto/basso.
- z=0.0 per tutti gli oggetti a terra.
- rot_z = rotazione orizzontale (radianti). 0=rivolto verso Y+, 1.57=rivolto verso X-, 3.14=rivolto verso Y-.

REGOLE DI COMPOSIZIONE SPAZIALE:
1. SOGGIORNO: Il divano sta contro una parete immaginaria a y=-1.5. Il tavolino sta
   DAVANTI al divano, a max 0.6m di distanza (es. y=-0.5). Se c'è una lampada da tavolo
   (desk_lamp_*), mettila SU un tavolino scrivendo il nome esatto del tavolo in "parent" e z=1.0.
   Una lampada da terra (industrial_pipe_lamp) va a lato del divano (es. x=1.5, y=-1.5).
2. LIBRERIE/SCAFFALI: Vanno vicine all'area divano ma dietro o di lato (es. x=-1.5, y=1.5).
   Ruotale con rot_z in modo che guardino verso (0,0).
3. PIANTE: Negli angoli vicini. Esempio: x=1.5, y=1.5.
4. Distanza MINIMA tra oggetti adiacenti: 0.3m. Raggruppa l'arredo strettamente.
5. Non creare scene disperse: tutte le X e Y devono essere comprese tra -2.0 e 2.0.

COERENZA STILISTICA:
- Leggi i TAG tra parentesi nella lista asset. Se l'utente chiede "moderno", evita
  asset con tag "antique", "vintage", "old". Preferisci "modern", "minimal", "clean".
- Se il catalogo non ha un asset moderno per un tipo (es: tutti i divani sono antichi),
  usa comunque il più neutro disponibile.

[[CATALOG_CONTEXT]]
"""


class PromptBuilder:
    """
    Costruisce il payload con i messaggi per il modello.
    """

    def __init__(
        self,
        model: str | None = None,
        system_prompt: str | None = None,
        system_prompt_file: str | Path | None = None,
    ) -> None:
        self.model = model
        self.system_prompt = self._load_system_prompt(system_prompt, system_prompt_file)

    def build(self, scene_description: str, catalog_context: str = "") -> dict:
        """
        Costruisce il payload con i messaggi per il modello.
        """
        system_content = self.system_prompt.replace("[[CATALOG_CONTEXT]]", catalog_context)
        return {
            "messages": [
                {
                    "role": "system",
                    "content": system_content,
                },
                {
                    "role": "user",
                    "content": scene_description,
                },
            ],
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
