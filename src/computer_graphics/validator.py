"""
Validazione degli oggetti della scena con Pydantic v2.

Garantisce che ogni oggetto abbia i campi corretti e i valori nel range
atteso prima di passarli a Blender.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Nomi di oggetti conosciuti (fallback per suggerimenti e scene graph)
# ---------------------------------------------------------------------------
KNOWN_ASSET_NAMES: set[str] = {
    "table",
    "chair",
    "lamp",
    "desk",
    "sofa",
    "bed",
    "bookshelf",
    "cabinet",
    "door",
    "window",
    "floor",
    "monitor",
    "keyboard",
    "plant",
    "rug",
    "curtain",
    "fridge",
    "stove",
    "sink",
    "toilet",
    "bathtub",
}

# Tipi di luce supportati
LightType = Literal["POINT", "SUN", "SPOT", "AREA"]

# Semantiche materiali supportate
MaterialSemantic = Literal[
    "wood",
    "glass",
    "fabric",
    "metal",
    "plastic",
    "concrete",
    "ceramic",
    "leather",
    "marble",
    "rubber",
]


class LightObject(BaseModel):
    """
    Modello Pydantic per una sorgente luminosa nella scena 3D.

    Generato dall'LLM e consumato da setup_lighting() in scene_builder.

    Attributes:
        name: Identificatore univoco della luce.
        light_type: Tipo Blender della sorgente ("POINT", "SUN", "SPOT", "AREA").
        x: Posizione sull'asse X in unità Blender.
        y: Posizione sull'asse Y in unità Blender.
        z: Posizione sull'asse Z in unità Blender.
        color: Tripla RGB normalizzata [0.0, 1.0].
        energy: Potenza della luce in Watt (Cycles) o unità arbitrarie (EEVEE).
        spot_size: Angolo del cono in radianti (solo SPOT).
    """

    name: str = Field(default="light", min_length=1, max_length=64)
    light_type: LightType = Field(default="POINT")
    x: float = Field(default=0.0)
    y: float = Field(default=0.0)
    z: float = Field(default=3.0)
    color: tuple[float, float, float] = Field(default=(1.0, 1.0, 1.0))
    energy: float = Field(default=100.0, gt=0.0)
    spot_size: float = Field(default=0.785, gt=0.0)  # ~45 gradi

    model_config = {"coerce_numbers_to_str": False}

    @field_validator("color", mode="before")
    @classmethod
    def validate_color(cls, v: object) -> tuple[float, float, float]:
        """Valida e normalizza la tripla RGB."""
        if isinstance(v, (list, tuple)) and len(v) == 3:  # type: ignore[arg-type]
            r, g, b = (float(c) for c in v)  # type: ignore[union-attr]
            return (
                max(0.0, min(1.0, r)),
                max(0.0, min(1.0, g)),
                max(0.0, min(1.0, b)),
            )
        raise ValueError(
            f"Il campo 'color' deve essere una tripla RGB [r, g, b], ricevuto: {v}"
        )

    @field_validator("x", "y", "z", "energy", "spot_size", mode="before")
    @classmethod
    def coerce_numeric(cls, v: object) -> float:
        """Converte stringhe numeriche a float."""
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v.strip())
            except ValueError as exc:
                raise ValueError(f"Impossibile convertire '{v}' in float.") from exc
        raise ValueError(f"Tipo non supportato per campo numerico: {type(v)}")


class SceneObject(BaseModel):
    """
    Modello Pydantic per un singolo oggetto della scena 3D.

    Tutti i valori numerici vengono coercizzati da str a float se necessario,
    per gestire output sporchi del modello LLM.

    Attributes:
        name: Nome dell'oggetto in inglese minuscolo.
        x: Posizione asse X (relativa al parent se parent != None).
        y: Posizione asse Y (relativa al parent se parent != None).
        z: Posizione asse Z.
        rot_x: Rotazione attorno a X in radianti.
        rot_y: Rotazione attorno a Y in radianti.
        rot_z: Rotazione attorno a Z in radianti.
        scale: Scala uniforme (1.0 = dimensioni originali dell'asset).
        parent: Nome dell'oggetto parent nella gerarchia .
            Se None, l'oggetto è a radice della scena.
            Le coordinate x, y, z sono relative al parent.
        material_semantics: Semantica del materiale per shader procedurali
            . Es. "wood", "glass", "fabric".
    """

    name: str = Field(..., min_length=1, max_length=64)
    x: float = Field(default=0.0)
    y: float = Field(default=0.0)
    z: float = Field(default=0.0)
    rot_x: float = Field(default=0.0)
    rot_y: float = Field(default=0.0)
    rot_z: float = Field(default=0.0)
    scale: float = Field(default=1.0, gt=0.0)

    # Implementazione della gerarchia genitore-figlio per gli oggetti della scena.
    parent: str | None = Field(
        default=None,
        description=(
            "Nome del parent nella gerarchia. Le coordinate sono relative "
            "all'origine del parent. Esempio: 'monitor' ha parent='desk'."
        ),
    )

    # Supporto per l'assegnazione di materiali procedurali e semantici.
    material_semantics: MaterialSemantic | None = Field(
        default=None,
        description=(
            "Semantica del materiale per shader procedurali in bpy. "
            "Valori: 'wood', 'glass', 'fabric', 'metal', 'plastic', ecc."
        ),
    )
    color_override: tuple[float, float, float] | None = Field(
        default=None,
        description="Colore RGB [0.0, 1.0] che sovrascrive quello del materiale base.",
    )

    model_config = {"coerce_numbers_to_str": False}

    @field_validator("color_override", mode="before")
    @classmethod
    def validate_color_override(cls, v: object) -> tuple[float, float, float] | None:
        """Riutilizza la logica di validazione colore per l'override."""
        if v is None:
            return None
        return LightObject.validate_color(v)

    @field_validator("name", mode="before")
    @classmethod
    def normalise_name(cls, v: object) -> str:
        """Normalizza il nome: minuscolo, strip, underscore al posto degli spazi."""
        if not isinstance(v, str):
            raise ValueError(
                f"Il campo 'name' deve essere una stringa, ricevuto: {type(v)}"
            )
        normalised = str(v).strip().lower().replace(" ", "_")
        if not normalised:
            raise ValueError(
                "Il campo 'name' non può essere vuoto dopo la normalizzazione."
            )
        return normalised

    @field_validator("x", "y", "z", "rot_x", "rot_y", "rot_z", "scale", mode="before")
    @classmethod
    def coerce_numeric(cls, v: object) -> float:
        """Converte stringhe numeriche a float (gestisce output LLM sporco)."""
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v.strip())
            except ValueError as exc:
                raise ValueError(f"Impossibile convertire '{v}' in float.") from exc
        raise ValueError(f"Tipo non supportato per campo numerico: {type(v)}")

    @field_validator("parent", mode="before")
    @classmethod
    def normalise_parent(cls, v: object) -> str | None:
        """Normalizza il nome del parent (minuscolo, strip) o None."""
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            raise ValueError(
                f"Il campo 'parent' deve essere str o None, ricevuto: {type(v)}"
            )
        return str(v).strip().lower().replace(" ", "_")

    @model_validator(mode="after")
    def check_reasonable_bounds(self) -> SceneObject:
        """Avvisa se le coordinate sembrano fuori scala."""
        max_coord = 50.0
        for field_name, value in [
            ("x", self.x),
            ("y", self.y),
            ("z", self.z),
        ]:
            if abs(value) > max_coord:
                logger.warning(
                    "Oggetto '%s': valore %s=%.2f sembra fuori scala "
                    "(max atteso: +/-%.0f unità Blender).",
                    self.name,
                    field_name,
                    value,
                    max_coord,
                )

        import math

        for field_name, value in [
            ("rot_x", self.rot_x),
            ("rot_y", self.rot_y),
            ("rot_z", self.rot_z),
        ]:
            if abs(value) > math.pi * 4:
                logger.warning(
                    "Oggetto '%s': rotazione %s=%.2f anomala "
                    "(maggiore di due giri completi).",
                    self.name,
                    field_name,
                    value,
                )

        if self.scale <= 0.0 or self.scale > 100.0:
            logger.warning(
                "Oggetto '%s': scala %.2f fuori scala (attesa 0 < scale <= 100).",
                self.name,
                self.scale,
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
        for known in KNOWN_ASSET_NAMES:
            if known in self.name or self.name in known:
                logger.debug(
                    "Nome '%s' non in libreria, uso '%s' come fallback.",
                    self.name,
                    known,
                )
                return known
        return self.name


def validate_objects(raw_objects: list[dict[str, object]]) -> list[SceneObject]:
    """
    Valida una lista di dizionari grezzi e restituisce SceneObject validati.

    Args:
        raw_objects: Lista di dizionari provenienti dal parsing del JSON LLM.

    Returns:
        Lista di SceneObject Pydantic validati.

    Raises:
        ValueError: Se la lista è vuota o nessun oggetto è recuperabile.
    """
    if not raw_objects:
        raise ValueError(
            "La lista di oggetti è vuota. " "Il modello non ha generato alcun oggetto."
        )
    if not isinstance(raw_objects, list):
        raise ValueError(f"Attesa una lista, ricevuto: {type(raw_objects)}")

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
        # Nuovi campi opzionali — default sicuri
        obj.setdefault("parent", None)
        obj.setdefault("material_semantics", None)

        try:
            scene_obj = SceneObject(**obj)  # type: ignore[arg-type]
            validated.append(scene_obj)
            logger.debug(
                "Oggetto #%d validato: %s @ (%.2f, %.2f, %.2f) parent=%s",
                i,
                scene_obj.name,
                scene_obj.x,
                scene_obj.y,
                scene_obj.z,
                scene_obj.parent,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Oggetto #{i} (name={obj.get('name', '?')}): {exc}")

    if errors:
        error_summary = "\n - ".join(errors)
        logger.warning("Errori di validazione:\n - %s", error_summary)
        if not validated:
            raise ValueError(
                f"Nessun oggetto valido estratto. Errori:\n - {error_summary}"
            )

    logger.info(
        "Validazione completata: %d/%d oggetti validi.",
        len(validated),
        len(raw_objects),
    )
    return validated


def validate_lights(
    raw_lights: list[dict[str, object]],
) -> list[LightObject]:
    """
    Valida una lista di dizionari grezzi e restituisce LightObject validati.

    Args:
        raw_lights: Lista di dizionari provenienti dal parsing del JSON LLM
            relativi alle sorgenti luminose.

    Returns:
        Lista di LightObject Pydantic validati. Lista vuota se input vuoto.
    """
    if not raw_lights:
        return []

    validated: list[LightObject] = []
    for i, light in enumerate(raw_lights):
        if not isinstance(light, dict):
            logger.warning("Luce #%d: atteso dict, ricevuto %s", i, type(light))
            continue
        try:
            light_obj = LightObject(**light)  # type: ignore[arg-type]
            validated.append(light_obj)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Luce #%d (name=%s): %s", i, light.get("name", "?"), exc)

    return validated
