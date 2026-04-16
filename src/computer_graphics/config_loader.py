"""
Caricamento della configurazione da settings.yaml e variabili d'ambiente.

Priorità (dalla più alta alla più bassa):
1. Variabili d'ambiente (OLLAMA_URL, OLLAMA_MODEL, ecc.)
2. File .env nella root del progetto
3. config/settings.yaml
4. Valori di default hardcoded
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Percorso default al file di configurazione
_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "settings.yaml"

# Mapping variabili d'ambiente → chiavi YAML
_ENV_MAPPING: dict[str, tuple[str, str]] = {
    "OLLAMA_URL": ("ollama", "url"),
    "OLLAMA_MODEL": ("ollama", "model"),
    "OLLAMA_TIMEOUT": ("ollama", "timeout"),
    "ASSETS_DIR": ("paths", "assets_dir"),
    "RENDER_OUTPUT_DIR": ("paths", "render_output_dir"),
    "MAX_RETRIES": ("pipeline", "max_retries"),
    "LOG_LEVEL": ("pipeline", "log_level"),
}

_DEFAULT_CONFIG: dict[str, Any] = {
    "ollama": {
        "url": "http://localhost:11434",
        "model": "llama3",
        "timeout": 180,
        "max_connection_retries": 3,
        "retry_delay": 2.0,
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_predict": 1024,
        },
    },
    "pipeline": {
        "max_retries": 3,
        "verbose": True,
        "log_level": "INFO",
    },
    "paths": {
        "assets_dir": "assets/models",
        "render_output_dir": "assets/renders",
        "prompt_file": "config/prompts/system_prompt.txt",
    },
    "blender": {
        "render_engine": "CYCLES",
        "resolution_x": 1920,
        "resolution_y": 1080,
        "samples": 64,
        "camera_location": [7.0, -7.0, 5.0],
    },
    "validation": {
        "min_description_length": 10,
        "max_description_length": 2000,
        "max_coordinate_value": 50.0,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Unisce ricorsivamente due dizionari."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_dotenv(env_path: Path) -> None:
    """Carica variabili da file .env (implementazione minimale senza dipendenze)."""
    if not env_path.exists():
        return
    with env_path.open(encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()  # noqa: PLW2901
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


class ConfigLoader:
    """Caricatore centralizzato della configurazione."""

    _cache: dict[str, Any] | None = None

    @classmethod
    def load(
        cls,
        config_path: str | Path | None = None,
        force_reload: bool = False,
    ) -> dict[str, Any]:
        """
        Carica la configurazione con priorità: ENV > .env > YAML > default.

        Args:
            config_path: Percorso al file settings.yaml (usa default se None).
            force_reload: Se True, ignora la cache e ricarica.

        Returns:
            Dizionario di configurazione merged.
        """
        if cls._cache is not None and not force_reload:
            return cls._cache

        # 1. Carica .env se presente
        project_root = Path(__file__).parent.parent.parent
        _load_dotenv(project_root / ".env")

        # 2. Parte dalla configurazione di default
        config = _DEFAULT_CONFIG.copy()

        # 3. Merge con settings.yaml
        yaml_path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
        if yaml_path.exists():
            try:
                with yaml_path.open(encoding="utf-8") as fp:
                    yaml_config = yaml.safe_load(fp) or {}
                config = _deep_merge(config, yaml_config)
                logger.debug("Configurazione caricata da: %s", yaml_path)
            except yaml.YAMLError as exc:
                logger.warning("Errore lettura %s: %s. Uso default.", yaml_path, exc)
        else:
            logger.debug(
                "File %s non trovato. Uso configurazione di default.", yaml_path
            )

        # 4. Override con variabili d'ambiente
        for env_key, (section, key) in _ENV_MAPPING.items():
            env_value = os.environ.get(env_key)
            if env_value is not None:
                if section not in config:
                    config[section] = {}
                # Coercizione tipo basata sul default
                default_val = _DEFAULT_CONFIG.get(section, {}).get(key)
                if isinstance(default_val, int):
                    try:
                        config[section][key] = int(env_value)
                    except ValueError:
                        config[section][key] = env_value
                elif isinstance(default_val, float):
                    try:
                        config[section][key] = float(env_value)
                    except ValueError:
                        config[section][key] = env_value
                elif isinstance(default_val, bool):
                    config[section][key] = env_value.lower() in ("true", "1", "yes")
                else:
                    config[section][key] = env_value
                logger.debug("Override da ENV: %s=%s", env_key, env_value)

        cls._cache = config
        return config

    @classmethod
    def get(cls, *keys: str, default: Any = None) -> Any:
        """
        Accesso conveniente a un valore annidato.

        Esempio:
            ConfigLoader.get("ollama", "model")  # -> "llama3"
        """
        config = cls.load()
        current = config
        for key in keys:
            if not isinstance(current, dict):
                return default
            current = current.get(key, default)
        return current

    @classmethod
    def invalidate_cache(cls) -> None:
        """Invalida la cache (utile nei test)."""
        cls._cache = None
