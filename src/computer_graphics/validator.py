"""
Validazione degli oggetti della scena con Pydantic.

Garantisce che ogni oggetto abbia i campi corretti
e i valori nel range atteso prima di passarli a Blender.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# Nomi di oggetti conosciuti (fallback per suggerimenti)
KNOWN_ASSET_NAMES: set[str] = {
    "table", "chair", "lamp", "desk", "sofa", "bed",
    "bookshelf", "cabinet", "door", "window", "floor",
    "monitor", "keyboard", "plant", "rug", "curtain",
    "fridge", "stove", "sink", "toilet", "bathtub",
}


class SceneObject(BaseModel):
    """
    Modello Pydantic per un singolo oggetto della scena 3D.

    Tutti i valori numerici vengono coercizzati da str a float
    se necessario, per gestire output sporchi del modello LLM.
    """

    name: str = Field(..., min_length=1, max_length=64)
    x: float = Field(default=0.0)
    y: float = Field(default=0.0)
    z: float = Field(default=0.0)
    rot_x: float = Field(default=0.0)
    rot_y: float = Field(default=0.0)
    rot_z: float = Field(default=0.0)
    scale: float = Field(default=1.0, gt=0.0)

    model_config = {"coerce_numbers_to_str": False}

    @field_validator("name", mode="before")
    @classmethod
    def normalise_name(cls, v: Any) -> str:
        """Normalizza il nome: minuscolo, strip, underscore al posto degli spazi."""
        if not isinstance(v, str):
            raise ValueError(f"Il campo 'name' deve essere una stringa, ricevuto: {type(v)}")
        normalised = str(v).strip().lower().replace(" ", "_")
        if not normalised:
            raise ValueError("Il campo 'name' non può essere vuoto dopo la normalizzazione.")
        return normalised

    @field_validator("x", "y", "z", "rot_x", "rot_y", "rot_z", "scale", mode="before")
    @classmethod
    def coerce_numeric(cls, v: Any) -> float:
        """Converte stringhe numeriche a float (gestisce output LLM sporco)."""
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v.strip())
            except ValueError as exc:
                raise ValueError(
                    f"Impossibile convertire '{v}' in float."
                ) from exc
        raise ValueError(f"Tipo non supportato per campo numerico: {type(v)}")

    @model_validator(mode="after")
    def check_reasonable_bounds(self) -> "SceneObject":
        """Avvisa se le coordinate sembrano fuori scala."""
        MAX_COORD = 50.0
        for field_name, value in [("x", self.x), ("y", self.y), ("z", self.z)]:
            if abs(value) > MAX_COORD:
                logger.warning(
                    "Oggetto '%s': valore %s=%.2f sembra fuori scala "
                    "(max atteso: ±%.0f unità Blender).",
                    self.name, field_name, value, MAX_COORD,
                )
        return self

    def suggest_asset_name(self) -> str:
        """
        Suggerisce il nome asset più vicino se il nome non è nella libreria.

        Returns:
            Nome normalizzato o suggerimento basato su similarità.
        """
        if self.name in KNOWN_ASSET_NAMES:
            return self.name

        # Cerca corrispondenza parziale
        for known in KNOWN_ASSET_NAMES:
            if known in self.name or self.name in known:
                logger.debug(
                    "Nome '%s' non in libreria, uso '%s' come fallback.",
                    self.name, known,
                )
                return known

        return self.name  # usa il nome originale, gestirà FileNotFoundError


def validate_objects(raw_objects: list[dict]) -> list[SceneObject]:
    """
    Valida una lista di dizionari grezzi e restituisce SceneObject validati.

    Args:
        raw_objects: Lista di dizionari provenienti dal parsing del JSON LLM.

    Returns:
        Lista di SceneObject Pydantic validati.

    Raises:
        ValueError: Se la lista è vuota o un oggetto non è recuperabile.
    """
    if not raw_objects:
        raise ValueError("La lista di oggetti è vuota. Il modello non ha generato alcun oggetto.")

    if not isinstance(raw_objects, list):
        raise ValueError(
            f"Attesa una lista, ricevuto: {type(raw_objects)}"
        )

    validated: list[SceneObject] = []
    errors: list[str] = []

    for i, obj in enumerate(raw_objects):
        if not isinstance(obj, dict):
            errors.append(f"Oggetto #{i}: atteso dict, ricevuto {type(obj)}")
            continue

        # Aggiunge campi mancanti con default prima della validazione Pydantic
        obj.setdefault("rot_x", 0.0)
        obj.setdefault("rot_y", 0.0)
        obj.setdefault("rot_z", 0.0)
        obj.setdefault("scale", 1.0)

        try:
            scene_obj = SceneObject(**obj)
            validated.append(scene_obj)
            logger.debug(
                "Oggetto #%d validato: %s @ (%.2f, %.2f, %.2f)",
                i, scene_obj.name, scene_obj.x, scene_obj.y, scene_obj.z,
            )
        except Exception as exc:
            errors.append(f"Oggetto #{i} (name={obj.get('name', '?')}): {exc}")

    if errors:
        error_summary = "\n  - ".join(errors)
        logger.warning("Errori di validazione:\n  - %s", error_summary)

        if not validated:
            raise ValueError(
                f"Nessun oggetto valido estratto. Errori:\n  - {error_summary}"
            )

    logger.info(
        "Validazione completata: %d/%d oggetti validi.",
        len(validated), len(raw_objects),
    )
    return validated