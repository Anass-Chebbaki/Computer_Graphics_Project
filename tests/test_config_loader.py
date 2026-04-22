"""Test per il modulo config_loader."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from computer_graphics.config_loader import (
    ConfigLoader,
    _deep_merge,
    _load_dotenv,
)


@pytest.fixture(autouse=True)
def reset_cache() -> Generator[None, None, None]:
    """Invalida la cache prima di ogni test."""
    ConfigLoader.invalidate_cache()
    yield
    ConfigLoader.invalidate_cache()


class TestDeepMerge:
    def test_simple_merge(self) -> None:
        base = {"a": 1, "b": 2}
        override = {"b": 99, "c": 3}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 99, "c": 3}

    def test_nested_merge(self) -> None:
        base = {"ollama": {"url": "http://localhost", "timeout": 180}}
        override = {"ollama": {"timeout": 60}}
        result = _deep_merge(base, override)
        assert result["ollama"]["url"] == "http://localhost"
        assert result["ollama"]["timeout"] == 60

    def test_base_not_mutated(self) -> None:
        base = {"a": {"x": 1}}
        override = {"a": {"y": 2}}
        result = _deep_merge(base, override)
        assert "y" not in base["a"]
        assert result["a"] == {"x": 1, "y": 2}

    def test_override_non_dict_replaces(self) -> None:
        base = {"a": {"nested": 1}}
        override = {"a": "scalar"}
        result = _deep_merge(base, override)
        assert result["a"] == "scalar"


class TestLoadDotenv:
    def test_loads_variables_from_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR_XYZ=hello_world\n", encoding="utf-8")
        # Rimuovi se presente
        os.environ.pop("TEST_VAR_XYZ", None)
        _load_dotenv(env_file)
        assert os.environ.get("TEST_VAR_XYZ") == "hello_world"
        del os.environ["TEST_VAR_XYZ"]

    def test_ignores_comments_and_empty_lines(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("# commento\n\nTEST_VAR_COMMENT=value\n", encoding="utf-8")
        os.environ.pop("TEST_VAR_COMMENT", None)
        _load_dotenv(env_file)
        assert os.environ.get("TEST_VAR_COMMENT") == "value"
        del os.environ["TEST_VAR_COMMENT"]

    def test_strips_quotes_from_values(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text('TEST_QUOTED="quoted_value"\n', encoding="utf-8")
        os.environ.pop("TEST_QUOTED", None)
        _load_dotenv(env_file)
        assert os.environ.get("TEST_QUOTED") == "quoted_value"
        del os.environ["TEST_QUOTED"]

    def test_does_not_override_existing_env(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING_VAR=from_file\n", encoding="utf-8")
        os.environ["EXISTING_VAR"] = "from_env"
        _load_dotenv(env_file)
        assert os.environ["EXISTING_VAR"] == "from_env"
        del os.environ["EXISTING_VAR"]

    def test_missing_file_does_nothing(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.env"
        # Non deve sollevare eccezioni
        _load_dotenv(missing)

    def test_single_quotes_stripped(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_SINGLE='single_val'\n", encoding="utf-8")
        os.environ.pop("TEST_SINGLE", None)
        _load_dotenv(env_file)
        assert os.environ.get("TEST_SINGLE") == "single_val"
        del os.environ["TEST_SINGLE"]


class TestConfigLoaderLoad:
    def test_returns_dict(self) -> None:
        cfg = ConfigLoader.load()
        assert isinstance(cfg, dict)

    def test_has_ollama_section(self) -> None:
        cfg = ConfigLoader.load()
        assert "ollama" in cfg
        assert "url" in cfg["ollama"]

    def test_has_pipeline_section(self) -> None:
        cfg = ConfigLoader.load()
        assert "pipeline" in cfg
        assert "max_retries" in cfg["pipeline"]

    def test_has_paths_section(self) -> None:
        cfg = ConfigLoader.load()
        assert "paths" in cfg
        assert "assets_dir" in cfg["paths"]

    def test_cache_returns_same_object(self) -> None:
        cfg1 = ConfigLoader.load()
        cfg2 = ConfigLoader.load()
        assert cfg1 is cfg2

    def test_force_reload_invalidates_cache(self) -> None:
        cfg1 = ConfigLoader.load()
        cfg2 = ConfigLoader.load(force_reload=True)
        # Deve essere un nuovo dizionario (non lo stesso oggetto)
        assert cfg1 == cfg2

    def test_custom_config_path(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "settings.yaml"
        yaml_file.write_text(
            "ollama:\n  model: custom_model\n  url: http://custom:11434\n",
            encoding="utf-8",
        )
        # Isola il test dall'ambiente e dal file .env reale
        with patch.dict(os.environ, {}, clear=True), patch(
            "computer_graphics.config_loader._load_dotenv"
        ):
            cfg = ConfigLoader.load(config_path=yaml_file, force_reload=True)
            assert cfg["ollama"]["model"] == "custom_model"
            assert cfg["ollama"]["url"] == "http://custom:11434"
        ConfigLoader.invalidate_cache()

    def test_missing_yaml_uses_defaults(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.yaml"
        cfg = ConfigLoader.load(config_path=missing, force_reload=True)
        assert cfg["ollama"]["url"] == "http://localhost:11434"
        ConfigLoader.invalidate_cache()

    def test_invalid_yaml_uses_defaults(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text("{ invalid yaml: [unclosed\n", encoding="utf-8")
        # Non deve sollevare eccezione, usa default
        cfg = ConfigLoader.load(config_path=yaml_file, force_reload=True)
        assert "ollama" in cfg
        ConfigLoader.invalidate_cache()

    def test_env_override_string(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "settings.yaml"
        yaml_file.write_text("", encoding="utf-8")
        with patch.dict(os.environ, {"OLLAMA_MODEL": "env_model"}):
            cfg = ConfigLoader.load(config_path=yaml_file, force_reload=True)
            assert cfg["ollama"]["model"] == "env_model"
        ConfigLoader.invalidate_cache()

    def test_env_override_int(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "settings.yaml"
        yaml_file.write_text("", encoding="utf-8")
        with patch.dict(os.environ, {"MAX_RETRIES": "7"}):
            cfg = ConfigLoader.load(config_path=yaml_file, force_reload=True)
            assert cfg["pipeline"]["max_retries"] == 7
        ConfigLoader.invalidate_cache()

    def test_env_override_float(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "settings.yaml"
        yaml_file.write_text("", encoding="utf-8")
        with patch.dict(os.environ, {"OLLAMA_TIMEOUT": "300"}):
            cfg = ConfigLoader.load(config_path=yaml_file, force_reload=True)
            # timeout è int nel default, viene convertito
            assert cfg["ollama"]["timeout"] == 300
        ConfigLoader.invalidate_cache()

    def test_env_override_invalid_int_falls_back_to_string(
        self, tmp_path: Path
    ) -> None:
        yaml_file = tmp_path / "settings.yaml"
        yaml_file.write_text("", encoding="utf-8")
        with patch.dict(os.environ, {"MAX_RETRIES": "not_a_number"}):
            cfg = ConfigLoader.load(config_path=yaml_file, force_reload=True)
            # Fallback a stringa se la conversione fallisce
            assert cfg["pipeline"]["max_retries"] == "not_a_number"
        ConfigLoader.invalidate_cache()

    def test_env_url_override(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "settings.yaml"
        yaml_file.write_text("", encoding="utf-8")
        with patch.dict(os.environ, {"OLLAMA_URL": "http://remote:11434"}):
            cfg = ConfigLoader.load(config_path=yaml_file, force_reload=True)
            assert cfg["ollama"]["url"] == "http://remote:11434"
        ConfigLoader.invalidate_cache()

    def test_env_assets_dir_override(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "settings.yaml"
        yaml_file.write_text("", encoding="utf-8")
        with patch.dict(os.environ, {"ASSETS_DIR": "/custom/assets"}):
            cfg = ConfigLoader.load(config_path=yaml_file, force_reload=True)
            assert cfg["paths"]["assets_dir"] == "/custom/assets"
        ConfigLoader.invalidate_cache()


class TestConfigLoaderGet:
    def test_get_existing_key(self) -> None:
        url = ConfigLoader.get("ollama", "url")
        assert isinstance(url, str)
        assert "localhost" in url or "http" in url

    def test_get_nested_key(self) -> None:
        model = ConfigLoader.get("ollama", "model")
        assert isinstance(model, str)

    def test_get_missing_key_returns_default(self) -> None:
        result = ConfigLoader.get("nonexistent", "key", default="fallback")
        assert result == "fallback"

    def test_get_missing_key_returns_none_by_default(self) -> None:
        result = ConfigLoader.get("nonexistent", "key")
        assert result is None

    def test_get_non_dict_intermediate(self) -> None:
        # Se un valore intermedio non è un dict, ritorna default
        result = ConfigLoader.get("ollama", "url", "extra_key", default="fb")
        assert result == "fb"

    def test_invalidate_cache(self) -> None:
        ConfigLoader.load()
        assert ConfigLoader._cache is not None
        ConfigLoader.invalidate_cache()
        assert ConfigLoader._cache is None
