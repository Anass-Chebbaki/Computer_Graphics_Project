"""
Critic Loop visivo basato su Gemini Vision (MLLM).

Implementa il feedback loop multimodale descritto nella proposta v2:
il modello riceve il render preliminare della scena, lo analizza
visivamente, individua problemi spaziali e genera istruzioni correttive
in formato JSON per il prossimo ciclo di generazione.

Corrisponde all'approccio LayoutVLM citato nella traccia del progetto.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from computer_graphics.json_parser import JSONParseError, extract_json
from computer_graphics.validator import SceneObject, validate_objects


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt per il critic
# ---------------------------------------------------------------------------

_CRITIC_SYSTEM_PROMPT = """
Sei un critico esperto di layout 3D. Analizzi il render preliminare di una scena 3D e
identifichi problemi spaziali, producendo un JSON correttivo.

REGOLA ASSOLUTA: Rispondi ESCLUSIVAMENTE con un array JSON valido.
Non aggiungere MAI testo, spiegazioni, commenti, markdown o backtick.

Analisi da eseguire:
1. Oggetti sovrapposti o troppo vicini (distanza < 0.3 m)
2. Oggetti fuori dalla stanza o in posizioni irrealistiche
3. Oggetti fluttuanti o sotto il pavimento
4. Proporzioni errate rispetto al contesto (oggetti troppo grandi o piccoli)
5. Layout incoerente con la descrizione originale

Per ogni problema trovato, includi nell'array una correzione nel formato:
{
  "name": "nome_oggetto",
  "x": nuovo_x,
  "y": nuovo_y,
  "z": nuovo_z,
  "rot_x": rot_x,
  "rot_y": rot_y,
  "rot_z": nuovo_rot_z,
  "scale": nuova_scala,
  "parent": null_o_nome_parent,
  "material_semantics": materiale_o_null,
  "critic_note": "breve spiegazione della correzione"
}

Se la scena e corretta, rispondi con un array vuoto: []
""".strip()


_CRITIC_USER_TEMPLATE = """
Descrizione originale della scena: {description}

Analizza il render allegato e restituisci le correzioni necessarie come array JSON.
Correggi solo gli oggetti con problemi evidenti; mantieni invariati quelli posizionati correttamente.
""".strip()


# ---------------------------------------------------------------------------
# Risultato del critic
# ---------------------------------------------------------------------------


class CriticResult:
    """
    Risultato dell'analisi del critic loop.

    Attributes:
        corrections: Lista di dict con le correzioni suggerite.
        has_corrections: True se sono state trovate correzioni da applicare.
        raw_response: Risposta grezza del modello.
    """

    def __init__(
        self,
        corrections: list[dict[str, Any]],
        raw_response: str,
    ) -> None:
        self.corrections = corrections
        self.raw_response = raw_response

    @property
    def has_corrections(self) -> bool:
        """True se il critic ha suggerito almeno una correzione."""
        return len(self.corrections) > 0

    def __repr__(self) -> str:
        return (
            f"CriticResult(corrections={len(self.corrections)}, "
            f"has_corrections={self.has_corrections})"
        )


# ---------------------------------------------------------------------------
# Critic Loop
# ---------------------------------------------------------------------------


class CriticLoop:
    """
    Loop di feedback visivo basato su MLLM (Gemini Vision).

    Esegue iterazioni di analisi visiva del render e correzione del layout
    fino a convergenza o al raggiungimento del numero massimo di iterazioni.

    Args:
        gemini_client: Istanza di GeminiClient con supporto vision.
        max_iterations: Numero massimo di iterazioni del feedback loop.
        render_quality_threshold: Soglia minima di qualita del render
            sotto la quale non ha senso eseguire il critic.
    """

    def __init__(
        self,
        gemini_client: Any,
        max_iterations: int = 3,
    ) -> None:
        self._client = gemini_client
        self.max_iterations = max_iterations

    def run(
        self,
        objects: list[SceneObject],
        render_path: str | Path,
        scene_description: str,
        render_callback: Any | None = None,
    ) -> tuple[list[SceneObject], list[CriticResult]]:
        """
        Esegue il critic loop visivo sulla scena.

        Flusso per ogni iterazione:
        1. Analizza il render con Gemini Vision.
        2. Estrae le correzioni JSON dalla risposta.
        3. Applica le correzioni agli SceneObject.
        4. Se richiesto, ri-renderizza la scena aggiornata.
        5. Ripete fino a convergenza o max_iterations.

        Args:
            objects: Lista iniziale di SceneObject.
            render_path: Percorso al render PNG preliminare.
            scene_description: Descrizione testuale originale della scena.
            render_callback: Funzione opzionale ``(objects) -> render_path``
                per ri-renderizzare la scena dopo ogni iterazione.

        Returns:
            Tupla ``(oggetti_corretti, lista_risultati_critic)``.
        """
        current_objects = list(objects)
        current_render = Path(render_path)
        results: list[CriticResult] = []

        for iteration in range(1, self.max_iterations + 1):
            if not current_render.exists():
                logger.warning(
                    "CriticLoop iterazione %d: render non trovato in %s. Stop.",
                    iteration,
                    current_render,
                )
                break

            logger.info(
                "CriticLoop iterazione %d/%d: analisi render %s...",
                iteration,
                self.max_iterations,
                current_render,
            )

            critic_result = self._analyze_render(
                current_render,
                scene_description,
            )
            results.append(critic_result)

            if not critic_result.has_corrections:
                logger.info(
                    "CriticLoop iterazione %d: nessuna correzione necessaria. "
                    "Layout validato.",
                    iteration,
                )
                break

            logger.info(
                "CriticLoop iterazione %d: %d correzioni suggerite.",
                iteration,
                len(critic_result.corrections),
            )

            # Applica correzioni
            current_objects = self._apply_corrections(
                current_objects, critic_result.corrections
            )

            # Re-render se disponibile il callback
            if render_callback is not None and iteration < self.max_iterations:
                try:
                    new_render = render_callback(current_objects)
                    if new_render is not None:
                        current_render = Path(new_render)
                        logger.info(
                            "CriticLoop: nuovo render generato -> %s",
                            current_render,
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "CriticLoop: errore durante re-render: %s. "
                        "Interruzione del loop.",
                        exc,
                    )
                    break
            else:
                # Senza callback non possiamo aggiornare il render
                break

        logger.info(
            "CriticLoop completato: %d iterazioni, %d correzioni totali.",
            len(results),
            sum(len(r.corrections) for r in results),
        )
        return current_objects, results

    def _analyze_render(
        self,
        render_path: Path,
        scene_description: str,
    ) -> CriticResult:
        """
        Invia il render a Gemini Vision e analizza la risposta.

        Args:
            render_path: Percorso al file PNG del render.
            scene_description: Descrizione testuale della scena.

        Returns:
            CriticResult con le correzioni estratte.
        """
        user_prompt = _CRITIC_USER_TEMPLATE.format(
            description=scene_description
        )
        full_prompt = f"{_CRITIC_SYSTEM_PROMPT}\n\n{user_prompt}"

        try:
            raw_response = self._client.chat_with_image(
                text_prompt=full_prompt,
                image_path=render_path,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "CriticLoop: errore nella chiamata Gemini Vision: %s. "
                "Nessuna correzione applicata.",
                exc,
            )
            return CriticResult(corrections=[], raw_response=str(exc))

        corrections = self._parse_corrections(raw_response)
        return CriticResult(corrections=corrections, raw_response=raw_response)

    @staticmethod
    def _parse_corrections(raw_response: str) -> list[dict[str, Any]]:
        """
        Estrae le correzioni JSON dalla risposta del critic.

        Rimuove il campo ``critic_note`` che non fa parte dello schema
        SceneObject prima della validazione Pydantic.

        Args:
            raw_response: Testo grezzo della risposta Gemini.

        Returns:
            Lista di dizionari con le correzioni da applicare.
        """
        try:
            raw_objects = extract_json(raw_response)
        except JSONParseError as exc:
            logger.warning(
                "CriticLoop: impossibile estrarre JSON dalla risposta: %s.",
                exc,
            )
            return []

        if not raw_objects:
            return []

        cleaned: list[dict[str, Any]] = []
        for obj in raw_objects:
            if not isinstance(obj, dict):
                continue
            # Rimuovi campi non-standard prima della validazione
            note = obj.pop("critic_note", None)
            if note:
                logger.debug("Nota critica per '%s': %s", obj.get("name", "?"), note)
            cleaned.append(obj)

        return cleaned

    @staticmethod
    def _apply_corrections(
        objects: list[SceneObject],
        corrections: list[dict[str, Any]],
    ) -> list[SceneObject]:
        """
        Applica le correzioni suggerite dal critic agli SceneObject.

        Solo i campi numerici (x, y, z, rot_z, scale) vengono aggiornati.
        I campi semantici (name, parent, material_semantics) restano invariati
        per preservare la coerenza della scena.

        Args:
            objects: Lista corrente di SceneObject.
            corrections: Lista di correzioni dal critic.

        Returns:
            Lista aggiornata di SceneObject.
        """
        correction_map: dict[str, dict[str, Any]] = {
            str(c.get("name", "")): c
            for c in corrections
            if c.get("name")
        }

        _NUMERIC_FIELDS = frozenset(
            {"x", "y", "z", "rot_x", "rot_y", "rot_z", "scale"}
        )

        result: list[SceneObject] = []
        for obj in objects:
            correction = correction_map.get(obj.name)
            if correction is None:
                result.append(obj)
                continue

            update: dict[str, Any] = {}
            for field_name in _NUMERIC_FIELDS:
                if field_name in correction:
                    try:
                        update[field_name] = float(correction[field_name])
                    except (TypeError, ValueError):
                        pass

            if update:
                updated_obj = obj.model_copy(update=update)
                logger.debug(
                    "CriticLoop: correzione applicata a '%s': %s",
                    obj.name,
                    update,
                )
                result.append(updated_obj)
            else:
                result.append(obj)

        return result