"""Fixtures condivise per tutti i test."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def sample_clean_json() -> str:
    """JSON pulito, output ideale del modello."""
    return json.dumps([
        {"name": "table", "x": 0.0, "y": 0.0, "z": 0.0,
         "rot_x": 0.0, "rot_y": 0.0, "rot_z": 0.0, "scale": 1.0},
        {"name": "chair", "x": 1.2, "y": -0.8, "z": 0.0,
         "rot_x": 0.0, "rot_y": 0.0, "rot_z": 0.785, "scale": 1.0},
        {"name": "lamp",  "x": -2.0, "y": -2.0, "z": 0.0,
         "rot_x": 0.0, "rot_y": 0.0, "rot_z": 0.0, "scale": 1.0},
    ])


@pytest.fixture()
def sample_dirty_text() -> str:
    """Testo sporco con commenti e testo extra (caso reale frequente)."""
    return """
    Ecco gli oggetti della scena come richiesto:

    ```json
    [
      // tavolo centrale
      {"name": "table", "x": 0.0, "y": 0.0, "z": 0.0,
       "rot_x": 0.0, "rot_y": 0.0, "rot_z": 0.0, "scale": 1.0},
      {"name": "chair", "x": "1.2", "y": "-0.8", "z": "0.0",
       "rot_x": 0.0, "rot_y": 0.0, "rot_z": 0.785,},
    ]
    ```

    Spero che questo layout sia utile!
    """


@pytest.fixture()
def valid_objects_list() -> list[dict]:
    """Lista di dizionari già normalizzati."""
    return [
        {"name": "table", "x": 0.0, "y": 0.0, "z": 0.0,
         "rot_x": 0.0, "rot_y": 0.0, "rot_z": 0.0, "scale": 1.0},
        {"name": "chair", "x": 1.2, "y": -0.8, "z": 0.0,
         "rot_x": 0.0, "rot_y": 0.0, "rot_z": 0.785, "scale": 1.0},
    ]


@pytest.fixture()
def ollama_url() -> str:
    return "http://localhost:11434"


@pytest.fixture()
def mock_ollama_response() -> dict:
    """Risposta HTTP simulata di Ollama."""
    return {
        "message": {
            "role": "assistant",
            "content": json.dumps([
                {"name": "table", "x": 0.0, "y": 0.0, "z": 0.0,
                 "rot_x": 0.0, "rot_y": 0.0, "rot_z": 0.0, "scale": 1.0},
            ]),
        },
        "done": True,
    }