"""Generazione di anteprime 2D del layout della scena tramite Matplotlib."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import math

if TYPE_CHECKING:
    from computer_graphics.validator import SceneObject

logger = logging.getLogger(__name__)


def generate_2d_preview(
    objects: list[SceneObject],
    output_path: str | Path,
    title: str = "NL2Scene3D — 2D Layout Preview",
) -> Path:
    """
    Genera un'immagine PNG con la vista dall'alto (top-down) della scena.

    Mostra i Bounding Box degli oggetti e le loro posizioni relative.

    Args:
        objects: Lista di SceneObject con coordinate e scale.
        output_path: Percorso dove salvare l'immagine.
        title: Titolo del grafico.

    Returns:
        Path del file generato.
    """
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
    except ImportError:
        logger.warning(
            "Matplotlib non trovato. Impossibile generare anteprima 2D."
        )
        return Path(output_path)

    fig, ax = plt.subplots(figsize=(10, 10))
    ax.set_aspect("equal")
    ax.grid(True, linestyle="--", alpha=0.6)

    # Colori per diversi tipi di oggetti
    color_map = {
        "light": "#ffcc00",
        "parent": "#3399ff",
        "child": "#99ccff",
        "default": "#e0e0e0",
    }

    all_x = [0.0]
    all_y = [0.0]
    used_labels: set[str] = set()

    for obj in objects:
        # Calcolo dimensioni approssimative (fallback se non abbiamo SceneGraph)
        w = obj.scale * 0.8
        h = obj.scale * 0.8

        # Gestione rotazione (solo Z per 2D)
        angle = math.degrees(obj.rot_z)

        # Centro dell'oggetto
        cx, cy = obj.x, obj.y
        all_x.append(cx)
        all_y.append(cy)

        # Determina colore
        color = color_map["default"]
        if hasattr(obj, "light_type") and obj.light_type:
            color = color_map["light"]
        elif obj.parent:
            color = color_map["child"]

        # Gestione label unica per la legenda
        label = ""
        if obj.name not in used_labels:
            label = obj.name
            used_labels.add(obj.name)

        # Disegna il rettangolo (orientato)
        r = Rectangle(
            (0, 0),
            w,
            h,
            angle=angle,
            color=color,
            alpha=0.7,
            label=label,
        )

        # Trasformazione per centrare
        import matplotlib.transforms as mtransforms  # noqa: PLC0415

        trans = (
            mtransforms.Affine2D()
            .translate(-w / 2, -h / 2)
            .rotate_deg(angle)
            .translate(cx, cy)
            + ax.transData
        )
        r.set_transform(trans)

        ax.add_patch(r)
        ax.text(
            cx,
            cy,
            obj.name,
            fontsize=8,
            ha="center",
            va="center",
            clip_on=True,
        )

    # Imposta limiti del grafico
    margin = 5.0
    ax.set_xlim(min(all_x) - margin, max(all_x) + margin)
    ax.set_ylim(min(all_y) - margin, max(all_y) + margin)

    ax.set_title(title)
    ax.set_xlabel("X (meters)")
    ax.set_ylabel("Y (meters)")

    if used_labels:
        ax.legend(loc="upper right", fontsize="small", framealpha=0.5)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    plt.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)

    logger.info("Anteprima 2D salvata in: %s", output_path)
    return output_path
