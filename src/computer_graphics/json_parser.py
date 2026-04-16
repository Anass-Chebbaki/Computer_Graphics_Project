"""
Fase 4 — Parsing e pulizia del JSON restituito dal modello LLM.

I modelli linguistici non garantiscono output perfettamente puliti:
questo modulo gestisce tutti i casi problematici noti.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)


class JSONParseError(Exception):
    """Sollevata quando non è possibile estrarre un JSON valido."""


def extract_json(raw_text: str) -> list[dict]:
    """
    Estrae e decodifica l'array JSON dal testo grezzo del modello.

    Strategia a cascata:
    1. Parsing diretto (output già pulito)
    2. Estrazione con regex dell'array JSON
    3. Pulizia aggressiva (rimozione commenti, backtick, testo extra)

    Args:
        raw_text: Testo grezzo restituito dal modello LLM.

    Returns:
        Lista di dizionari Python.

    Raises:
        JSONParseError: Se nessuna strategia riesce a estrarre JSON valido.
    """
    if not raw_text or not raw_text.strip():
        raise JSONParseError("La risposta del modello è vuota.")

    logger.debug("Testo grezzo ricevuto (%d caratteri):\n%s", len(raw_text), raw_text[:500])

    # Strategia 1: parsing diretto
    result = _try_direct_parse(raw_text)
    if result is not None:
        logger.debug("Strategia 1 (parsing diretto) riuscita.")
        return result

    # Strategia 2: estrazione con regex
    result = _try_regex_extract(raw_text)
    if result is not None:
        logger.debug("Strategia 2 (regex) riuscita.")
        return result

    # Strategia 3: pulizia aggressiva
    result = _try_aggressive_clean(raw_text)
    if result is not None:
        logger.debug("Strategia 3 (pulizia aggressiva) riuscita.")
        return result

    raise JSONParseError(
        "Impossibile estrarre un array JSON valido dalla risposta del modello.\n"
        f"Primi 200 caratteri della risposta: {raw_text[:200]!r}"
    )


# ---------------------------------------------------------------------------
# Strategie private di parsing
# ---------------------------------------------------------------------------

def _try_direct_parse(text: str) -> list[dict] | None:
    """Tenta il parsing JSON diretto del testo."""
    try:
        data = json.loads(text.strip())
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _try_regex_extract(text: str) -> list[dict] | None:
    """
    Estrae l'array JSON usando regex.
    Gestisce JSON multi-riga e preceduto/seguito da testo.
    """
    # Pattern: primo [ ... ultimo ] con tutto in mezzo (DOTALL)
    pattern = re.compile(r'\[.*\]', re.DOTALL)
    match = pattern.search(text)

    if not match:
        return None

    candidate = match.group(0)
    try:
        data = json.loads(candidate)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, ValueError):
        pass

    return None


def _try_aggressive_clean(text: str) -> list[dict] | None:
    """
    Pulisce il testo con trasformazioni aggressive prima del parsing.

    Gestisce:
    - Backtick markdown (```json ... ```)
    - Commenti JavaScript (// ... e /* ... */)
    - Virgole finali prima di ] o }
    - Testo prima e dopo l'array
    """
    cleaned = text

    # Rimuove blocchi markdown ```json ... ```
    cleaned = re.sub(r'```(?:json)?\s*', '', cleaned)
    cleaned = re.sub(r'```\s*', '', cleaned)

    # Rimuove commenti JavaScript // ...
    cleaned = re.sub(r'//[^\n]*', '', cleaned)

    # Rimuove commenti /* ... */
    cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)

    # Rimuove virgole finali (trailing commas) prima di ] o }
    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)

    # Prova prima il regex sull'output pulito
    return _try_regex_extract(cleaned)