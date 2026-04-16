"""
computer_graphics — Generazione automatica di scene 3D da linguaggio naturale.

Pipeline:
    1. Input utente (testo libero)
    2. Prompt engineering verso Ollama
    3. Chiamata HTTP al modello LLM locale
    4. Parsing e validazione del JSON restituito
    5. Applicazione della scena in Blender via bpy
"""

__version__ = "1.0.0"
__author__ = "Your Name"
__license__ = "MIT"

from computer_graphics.ollama_client import OllamaClient
from computer_graphics.orchestrator import generate_scene_objects
from computer_graphics.validator import SceneObject, validate_objects

__all__ = [
    "generate_scene_objects",
    "OllamaClient",
    "SceneObject",
    "validate_objects",
]
