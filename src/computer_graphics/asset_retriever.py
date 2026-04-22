"""
Retrieval semantico degli asset 3D tramite embedding vettoriale leggero.

Implementa una ricerca semantica basata su TF-IDF con cosine similarity
senza dipendenze da librerie ML pesanti, compatibile con l'ambiente Blender.
Consente di trovare il file asset più simile al nome/descrizione generato
dall'LLM anche in caso di mismatch lessicale.
"""

from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path


logger = logging.getLogger(__name__)

# Formati asset supportati in ordine di priorità
_SUPPORTED_EXTS: list[str] = [".obj", ".fbx", ".glb", ".gltf"]

# Separatori per la tokenizzazione
_TOKEN_RE = re.compile(r"[_\-\s]+")


# ---------------------------------------------------------------------------
# Tokenizzazione e TF-IDF leggero
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Tokenizza una stringa in token minuscoli.

    Args:
        text: Stringa di input.

    Returns:
        Lista di token non vuoti.
    """
    return [t for t in _TOKEN_RE.split(text.lower().strip()) if t]


def _term_freq(tokens: list[str]) -> dict[str, float]:
    """Calcola la Term Frequency normalizzata.

    Args:
        tokens: Lista di token.

    Returns:
        Dizionario ``{token: tf}``.
    """
    if not tokens:
        return {}
    counts: dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    total = len(tokens)
    return {t: c / total for t, c in counts.items()}


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Calcola la cosine similarity tra due vettori sparsi.

    Args:
        vec_a: Primo vettore (dizionario token -> peso).
        vec_b: Secondo vettore (dizionario token -> peso).

    Returns:
        Valore di similarità in ``[0.0, 1.0]``.
    """
    common = set(vec_a) & set(vec_b)
    if not common:
        return 0.0

    dot = sum(vec_a[t] * vec_b[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Indice degli asset
# ---------------------------------------------------------------------------


class AssetIndex:
    """Indice semantico degli asset presenti nella libreria.

    Costruisce vettori TF-IDF per ogni asset trovato nella directory e
    permette di cercare l'asset più simile a una query testuale.

    Args:
        assets_dir: Directory contenente i file asset.
    """

    def __init__(self, assets_dir: str | Path) -> None:
        self._assets_dir = Path(assets_dir)
        self._index: list[dict[str, object]] = []
        self._build_index()

    def _build_index(self) -> None:
        """Scansiona la directory e costruisce l'indice dei vettori TF-IDF."""
        if not self._assets_dir.exists():
            logger.warning("AssetIndex: directory '%s' non trovata.", self._assets_dir)
            return

        seen_basenames: set[Path] = set()
        paths_to_index: list[Path] = []

        for ext in _SUPPORTED_EXTS:
            for p in self._assets_dir.rglob(f"*{ext}"):
                basename = p.with_suffix("")
                if basename not in seen_basenames:
                    seen_basenames.add(basename)
                    paths_to_index.append(p)

        # Primo passaggio: calcola TF e frequenza dei documenti (DF)
        temp_data: list[tuple[Path, str, dict[str, float], list[str]]] = []
        doc_counts: dict[str, int] = {}

        for path in paths_to_index:
            stem = path.stem.lower()
            tokens = _tokenize(stem)
            tf_vec = _term_freq(tokens)
            temp_data.append((path, stem, tf_vec, tokens))

            # Conta in quanti documenti appare ogni token (per IDF)
            for t in tf_vec:
                doc_counts[t] = doc_counts.get(t, 0) + 1

        # Secondo passaggio: calcola pesi TF-IDF e costruisce l'indice
        num_docs = len(paths_to_index)
        for path, stem, tf_vec, tokens in temp_data:
            tfidf_vec: dict[str, float] = {}
            for t, tf in tf_vec.items():
                # IDF = log(N / df) + 1
                idf = math.log(num_docs / doc_counts[t]) + 1.0
                tfidf_vec[t] = tf * idf

            self._index.append(
                {
                    "name": stem,
                    "path": path,
                    "vector": tfidf_vec,
                    "tokens": tokens,
                }
            )

        logger.debug(
            "AssetIndex: %d asset indicizzati da '%s'.",
            len(self._index),
            self._assets_dir,
        )

    def find_best_match(
        self,
        query: str,
        threshold: float = 0.1,
    ) -> Path | None:
        """Trova il file asset più simile semanticamente alla query.

        Prima tenta un match esatto (case-insensitive), poi calcola la
        cosine similarity tra i vettori TF-IDF della query e di ogni asset.

        Args:
            query: Nome o descrizione generata dall'LLM.
            threshold: Soglia minima di similarità per considerare un match valido.

        Returns:
            Percorso al file asset più simile, oppure ``None`` se nessun match
            supera la soglia.
        """
        if not self._index:
            return None

        query_clean = query.lower().strip()

        # 1. Match esatto
        for entry in self._index:
            if entry["name"] == query_clean:
                logger.debug("AssetIndex: match esatto per '%s'.", query)
                return entry["path"]  # type: ignore[return-value]

        # 2. Ricerca semantica
        query_vec = _term_freq(_tokenize(query_clean))
        best_score = -1.0
        best_path: Path | None = None

        for entry in self._index:
            score = _cosine_similarity(query_vec, entry["vector"])  # type: ignore[arg-type]
            if score > best_score:
                best_score = score
                best_path = entry["path"]  # type: ignore[assignment]

        if best_score >= threshold and best_path is not None:
            logger.info(
                "AssetIndex: '%s' -> '%s' (score=%.3f).",
                query,
                best_path.stem,
                best_score,
            )
            return best_path

        logger.debug(
            "AssetIndex: nessun match per '%s' (best_score=%.3f < threshold=%.3f).",
            query,
            best_score,
            threshold,
        )
        return None

    def find_best_match_path_for_name(
        self,
        name: str,
        assets_dir: Path,
        threshold: float = 0.1,
    ) -> Path | None:
        """Cerca il file asset per nome con fallback semantico.

        Primo tenta i percorsi esatti per ogni estensione supportata, poi
        usa la ricerca semantica dell'indice.

        Args:
            name: Nome normalizzato dell'asset (es. ``"wooden_table"``).
            assets_dir: Directory degli asset.
            threshold: Soglia cosine similarity per il fallback semantico.

        Returns:
            Percorso al file trovato, oppure ``None``.
        """
        # Tentativo esatto
        for ext in _SUPPORTED_EXTS:
            candidate = assets_dir / f"{name}{ext}"
            if candidate.exists():
                return candidate

        # Fallback semantico
        return self.find_best_match(name, threshold=threshold)

    def export_metadata(self, output_path: Path) -> None:
        """Esporta i metadati dell'indice in formato JSON.

        Args:
            output_path: Percorso del file JSON di output.
        """
        data = [
            {
                "name": e["name"],
                "path": str(e["path"]),
                "tokens": e["tokens"],
            }
            for e in self._index
        ]
        with output_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        logger.info("AssetIndex metadata esportati in: %s", output_path)
