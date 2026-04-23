"""
Catalogo e downloader di asset 3D da Poly Haven.

Utilizza l'API pubblica di Poly Haven per scaricare modelli GLB con
texture PBR integrate e HDRI per l'illuminazione ambientale.
Licenza CC0: zero restrizioni legali, adatta per ricerca accademica.

API reference: https://api.polyhaven.com
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import requests
from requests.exceptions import RequestException


logger = logging.getLogger(__name__)

# URL base dell'API Poly Haven
_API_BASE = "https://api.polyhaven.com"
_CDN_BASE = "https://dl.polyhaven.org"

# Timeout per le richieste HTTP (secondi)
_API_TIMEOUT = 30
_DOWNLOAD_TIMEOUT = 120

# Mappa semantica: nome oggetto LLM -> query Poly Haven
# Se il nome è già uno slug Poly Haven valido (es: "sofa_03"),
# verrà provato per primo come slug diretto.
_SEMANTIC_MAPPING: dict[str, list[str]] = {
    # Sedute
    "table": ["wooden_table_02", "round_wooden_table_01", "chinese_tea_table"],
    "coffee_table": ["round_wooden_table_01", "wooden_table_02"],
    "dining_table": ["wooden_table_02"],
    "chair": ["bar_chair_round_01", "chinese_stool", "wooden_stool_01"],
    "stool": ["bar_chair_round_01", "wooden_stool_01", "wooden_stool_02"],
    # Lampade
    "lamp": ["desk_lamp_arm_01", "modern_ceiling_lamp_01"],
    "floor_lamp": ["industrial_pipe_lamp"],
    "ceiling_lamp": ["modern_ceiling_lamp_01", "Chandelier_01"],
    "chandelier": ["Chandelier_01", "Chandelier_02", "Chandelier_03"],
    # Divani
    "sofa": ["sofa_03", "sofa_02"],
    "couch": ["sofa_03", "sofa_02"],
    # Scaffali
    "bookshelf": ["steel_frame_shelves_03", "chinese_cabinet"],
    "shelf": ["steel_frame_shelves_03"],
    "cabinet": ["chinese_cabinet"],
    # Altro
    "desk": ["metal_office_desk"],
    "plant": ["potted_plant_04", "pachira_aquatica_01", "calathea_orbifolia_01", "anthurium_botany_01"],
    "vase": ["ceramic_vase_01", "ceramic_vase_02", "brass_vase_01"],
    "picture": ["hanging_picture_frame_01", "hanging_picture_frame_02"],
    "frame": ["fancy_picture_frame_01", "hanging_picture_frame_01"],
    "rug": ["rug"],
}


class PolyHavenCatalog:
    """
    Interfaccia al catalogo Poly Haven per il download di asset 3D e HDRI.

    Gestisce cache locale per evitare download ripetuti. Gli asset vengono
    salvati in ``cache_dir/models/`` e gli HDRI in ``cache_dir/hdri/``.

    Args:
        cache_dir: Directory locale per la cache degli asset scaricati.
        quality: Qualita dei modelli (``"1k"``, ``"2k"``, ``"4k"``).
    """

    def __init__(
        self,
        cache_dir: str | Path,
        quality: str = "2k",
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._quality = quality
        # Evitiamo nidificazioni: salviamo direttamente nella cache_dir
        self._models_dir = self._cache_dir
        self._hdri_dir = self._cache_dir / "hdri"
        self._meta_file = self._cache_dir / "polyhaven_catalog.json"
        # Assicuriamoci che esistano
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self._hdri_dir.mkdir(parents=True, exist_ok=True)
        self._catalog_cache: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Metodi pubblici
    # ------------------------------------------------------------------

    def get_model_path(
        self,
        asset_name: str,
        force_download: bool = False,
    ) -> Path | None:
        """
        Restituisce il percorso locale del modello GLB, scaricandolo se necessario.

        Prima cerca nel mapping semantico, poi tenta il nome diretto.
        Se il modello non esiste su Poly Haven, restituisce None.

        Args:
            asset_name: Nome normalizzato dell'asset (es. ``"table"``).
            force_download: Se True, ri-scarica anche se in cache.

        Returns:
            Path al file .glb locale, oppure None se non trovato.
        """
        polyhaven_slugs = _SEMANTIC_MAPPING.get(asset_name, [asset_name])

        for slug in polyhaven_slugs:
            # Controlla sia .glb che .gltf nella cache
            for ext in [".glb", ".gltf"]:
                cached = self._models_dir / f"{slug}{ext}"
                if cached.exists() and not force_download:
                    logger.debug(
                        "Cache hit per '%s' -> %s", asset_name, cached
                    )
                    return cached

            downloaded = self._download_model(slug)
            if downloaded is not None:
                return downloaded

        logger.warning(
            "Nessun modello Poly Haven trovato per '%s'. "
            "Verra usato il fallback.",
            asset_name,
        )
        return None

    def get_catalog_summary(self) -> str:
        """
        Genera una stringa riassuntiva del catalogo per l'LLM.
        Include slug e categorie per permettere la selezione accurata.
        """
        catalog = self._fetch_catalog("models")
        if not catalog:
            return "Catalogo Poly Haven non disponibile."

        summary = ["ASSET DISPONIBILI (usa questi nomi esatti nel campo 'name'):"]
        
        # Solo categorie rilevanti per interni
        _INTERIOR_CATEGORIES = {
            "furniture", "seating", "lighting", "plants", "decorative",
            "shelves", "table", "appliances", "electronics", "vases",
            "containers", "wall decoration",
        }
        
        categories: dict[str, list[str]] = {}
        for slug, meta in catalog.items():
            cat_list = meta.get("categories", ["other"])
            tags = meta.get("tags", [])
            style_hint = ", ".join(tags[:3])
            
            main_cat = cat_list[0] if cat_list else "other"
            # Filtra solo categorie per interni
            if main_cat.lower() not in _INTERIOR_CATEGORIES:
                # Controlla anche categorie secondarie
                if not any(c.lower() in _INTERIOR_CATEGORIES for c in cat_list):
                    continue
                    
            if main_cat not in categories:
                categories[main_cat] = []
            
            if len(categories[main_cat]) < 100:
                categories[main_cat].append(f"{slug} ({style_hint})")

        for cat, slugs in categories.items():
            summary.append(f"- {cat.upper()}: {', '.join(slugs)}")

        return "\n".join(summary)

    def get_hdri_path(
        self,
        hdri_slug: str | None = None,
        category: str = "outdoor",
        force_download: bool = False,
    ) -> Path | None:
        """
        Restituisce il percorso locale di un file HDRI.

        Se ``hdri_slug`` e None, seleziona un HDRI casuale dalla categoria.

        Args:
            hdri_slug: Nome specifico dell'HDRI (es. ``"studio_small_03"``).
            category: Categoria HDRI per la selezione casuale.
            force_download: Se True, ri-scarica anche se in cache.

        Returns:
            Path al file .hdr locale, oppure None se non trovato.
        """
        if hdri_slug is None:
            hdri_slug = self._pick_hdri_slug(category)
            if hdri_slug is None:
                return None

        cached = self._hdri_dir / f"{hdri_slug}.hdr"
        if cached.exists() and not force_download:
            logger.debug("Cache hit HDRI: %s", cached)
            return cached

        return self._download_hdri(hdri_slug)

    def list_available_models(self, category: str = "models") -> list[str]:
        """
        Restituisce la lista degli slug di modelli disponibili su Poly Haven.

        Args:
            category: Categoria da filtrare (``"models"``, ``"hdris"``, ecc.).

        Returns:
            Lista di slug (nomi identificativi) disponibili.
        """
        catalog = self._fetch_catalog(category)
        return list(catalog.keys())

    def prefetch_assets(self, asset_names: list[str]) -> dict[str, Path | None]:
        """
        Pre-scarica una lista di asset in modo sequenziale.

        Utile per preparare gli asset prima dell'avvio di Blender,
        evitando attese durante la costruzione della scena.

        Args:
            asset_names: Lista di nomi normalizzati degli asset.

        Returns:
            Dizionario ``{nome: path_o_None}`` per ogni asset.
        """
        results: dict[str, Path | None] = {}
        for name in asset_names:
            results[name] = self.get_model_path(name)
            # Rispetta il rate limit dell'API (max ~10 req/s)
            time.sleep(0.1)
        return results

    # ------------------------------------------------------------------
    # Metodi privati
    # ------------------------------------------------------------------

    def _fetch_catalog(self, asset_type: str = "models") -> dict[str, Any]:
        """
        Recupera il catalogo completo degli asset dal server Poly Haven.

        Salva il risultato in cache locale per evitare richieste ripetute.

        Args:
            asset_type: Tipo di asset da recuperare (``"models"``, ``"hdris"``).

        Returns:
            Dizionario slug -> metadati dell'asset.
        """
        cache_key = f"catalog_{asset_type}"
        if self._catalog_cache is not None and cache_key in self._catalog_cache:
            return self._catalog_cache[cache_key]  # type: ignore[return-value]

        # Controlla cache su disco
        meta_file = self._cache_dir / f"polyhaven_{asset_type}_catalog.json"
        if meta_file.exists():
            try:
                with meta_file.open(encoding="utf-8") as fh:
                    data = json.load(fh)
                if self._catalog_cache is None:
                    self._catalog_cache = {}
                self._catalog_cache[cache_key] = data
                logger.debug(
                    "Catalogo Poly Haven caricato da cache: %d asset.", len(data)
                )
                return data
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "Errore lettura cache catalogo: %s. Riscaricare.", exc
                )

        # Fetch da API
        url = f"{_API_BASE}/assets?t={asset_type}"
        try:
            response = requests.get(url, timeout=_API_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            # Salva cache su disco
            with meta_file.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            if self._catalog_cache is None:
                self._catalog_cache = {}
            self._catalog_cache[cache_key] = data
            logger.info(
                "Catalogo Poly Haven scaricato: %d asset (%s).",
                len(data),
                asset_type,
            )
            return data
        except RequestException as exc:
            logger.warning(
                "Impossibile scaricare catalogo Poly Haven: %s. "
                "Uso catalogo vuoto.",
                exc,
            )
            return {}

    def _get_asset_files(self, slug: str) -> dict[str, Any]:
        """
        Recupera i metadati dei file disponibili per un asset specifico.

        Args:
            slug: Identificatore univoco dell'asset.

        Returns:
            Dizionario dei file disponibili con URL e dimensioni.
        """
        url = f"{_API_BASE}/files/{slug}"
        try:
            response = requests.get(url, timeout=_API_TIMEOUT)
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]
        except RequestException as exc:
            logger.debug(
                "Impossibile recuperare file per '%s': %s", slug, exc
            )
            return {}

    def _download_model(self, slug: str) -> Path | None:
        """
        Scarica il modello (GLB o GLTF) per un dato slug da Poly Haven.

        Args:
            slug: Identificatore dell'asset su Poly Haven.

        Returns:
            Path al file di input principale, oppure None in caso di errore.
        """
        files_data = self._get_asset_files(slug)
        if not files_data:
            return None

        # Cerca il file GLB/GLTF nella qualita richiesta
        url = self._find_glb_url(files_data, self._quality)
        if url is None:
            logger.debug(
                "Nessun modello 3D disponibile per '%s' in qualita %s.",
                slug,
                self._quality,
            )
            return None

        # Determina il percorso locale
        ext = ".glb" if ".glb" in url.lower() else ".gltf"
        output_path = self._models_dir / f"{slug}{ext}"

        # Se e un GLTF, dobbiamo scaricare anche i file inclusi (.bin, textures)
        if ext == ".gltf":
            # Trova la sezione dei metadati per questa specifica URL
            # per individuare la lista 'include'
            gltf_section = files_data.get("gltf", {})
            includes: dict[str, Any] = {}
            for q_data in gltf_section.values():
                if q_data.get("gltf", {}).get("url") == url:
                    includes = q_data.get("gltf", {}).get("include", {})
                    break

            # Scarica il file principale
            if not self._download_file(url, output_path):
                return None

            # Scarica i file inclusi mantendo la struttura delle cartelle relativa
            for rel_path, meta in includes.items():
                include_url = meta.get("url")
                if include_url:
                    include_dest = output_path.parent / rel_path
                    self._download_file(include_url, include_dest)

            logger.info("Modello GLTF (multi-file) scaricato: %s", slug)
            return output_path

        # Caso GLB singolo file
        success = self._download_file(url, output_path)
        if success:
            logger.info("Modello GLB scaricato: %s -> %s", slug, output_path)
            return output_path
        return None

    def _download_hdri(self, slug: str) -> Path | None:
        """
        Scarica il file HDRI per un dato slug.

        Args:
            slug: Identificatore dell'HDRI su Poly Haven.

        Returns:
            Path al file .hdr scaricato, oppure None in caso di errore.
        """
        files_data = self._get_asset_files(slug)
        if not files_data:
            return None

        hdri_url = self._find_hdri_url(files_data, self._quality)
        if hdri_url is None:
            logger.debug(
                "Nessun file HDRI disponibile per '%s'.", slug
            )
            return None

        output_path = self._hdri_dir / f"{slug}.hdr"
        success = self._download_file(hdri_url, output_path)
        if success:
            logger.info("HDRI scaricata: %s -> %s", slug, output_path)
            return output_path
        return None

    def _pick_hdri_slug(self, category: str) -> str | None:
        """
        Seleziona uno slug HDRI dalla categoria specificata.

        Preferisce HDRI di interni per scene d'ambiente chiuso.

        Args:
            category: Categoria di preferenza.

        Returns:
            Slug selezionato oppure None se il catalogo e vuoto.
        """
        catalog = self._fetch_catalog("hdris")
        if not catalog:
            return None

        # Filtra per categoria se disponibile nei metadati
        preferred = [
            slug for slug, meta in catalog.items()
            if category.lower() in str(meta.get("categories", [])).lower()
        ]
        pool = preferred if preferred else list(catalog.keys())
        if not pool:
            return None

        # Selezione deterministica basata su hash per riproducibilita
        pool_sorted = sorted(pool)
        idx = int(hashlib.md5(category.encode()).hexdigest(), 16) % len(pool_sorted)
        return pool_sorted[idx]

    @staticmethod
    def _find_glb_url(files_data: dict[str, Any], quality: str) -> str | None:
        """
        Trova l'URL del file GLB (o GLTF) nella qualita richiesta.

        Fallback automatico a qualita inferiore e prova a indovinare il GLB
        se l'API riporta solo il GLTF (comune su Poly Haven).

        Args:
            files_data: Dizionario file dall'API Poly Haven.
            quality: Qualita desiderata (``"1k"``, ``"2k"``, ``"4k"``).

        Returns:
            URL del file (preferibilmente GLB) oppure None.
        """
        if not files_data:
            return None

        gltf_section = files_data.get("gltf", {})
        qualities = [quality, "1k", "2k", "4k"]

        for q in qualities:
            q_data = gltf_section.get(q, {})
            # Prova prima il GLB (singolo file, facile da gestire)
            glb_data = q_data.get("glb", {})
            url = glb_data.get("url")
            if url:
                return str(url)

            # Fallback a GLTF
            gltf_data = q_data.get("gltf", {})
            url = gltf_data.get("url")
            if url:
                return str(url)

        return None

    @staticmethod
    def _find_hdri_url(files_data: dict[str, Any], quality: str) -> str | None:
        """
        Trova l'URL del file HDR nella qualita richiesta.

        Args:
            files_data: Dizionario file dall'API Poly Haven.
            quality: Qualita desiderata.

        Returns:
            URL del file HDR oppure None.
        """
        hdri_section = files_data.get("hdri", {})
        qualities = [quality, "1k", "2k", "4k"]

        for q in qualities:
            q_data = hdri_section.get(q, {})
            hdr_data = q_data.get("hdr", {})
            url = hdr_data.get("url")
            if url:
                return str(url)

        return None

    @staticmethod
    def _download_file(url: str, output_path: Path) -> bool:
        """
        Scarica un file da URL e lo salva su disco.

        Args:
            url: URL del file da scaricare.
            output_path: Percorso di destinazione.

        Returns:
            True se il download e riuscito, False altrimenti.
        """
        try:
            response = requests.get(url, timeout=_DOWNLOAD_TIMEOUT, stream=True)
            response.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
            logger.debug("Download completato: %s", output_path)
            return True
        except RequestException as exc:
            logger.warning(
                "Download fallito per '%s': %s", url, exc
            )
            if output_path.exists():
                output_path.unlink()
            return False