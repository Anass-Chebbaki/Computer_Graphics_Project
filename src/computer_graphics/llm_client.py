"""Astrazione dei client LLM per supportare diversi provider (Ollama, OpenAI, ecc.)."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Errore base per i client LLM."""


class LLMConnectionError(LLMError):
    """Errore di connessione al provider LLM."""


class LLMResponseError(LLMError):
    """Errore nella risposta del modello."""


class BaseLLMClient(ABC):
    """Classe base astratta per tutti i client LLM."""

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """
        Invia una richiesta al modello e restituisce la risposta testuale.

        Args:
            messages: Lista di messaggi nel formato:
                [{"role": "user", "content": "..."}].
            **kwargs: Parametri aggiuntivi (temperature, model, ecc.).

        Returns:
            Testo della risposta.
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verifica se il servizio è raggiungibile."""
        pass


def get_llm_client(provider: str, **kwargs: Any) -> BaseLLMClient:
    """
    Factory per istanziare il client LLM corretto.

    Args:
        provider: Nome del provider ("ollama", "openai").
        **kwargs: Argomenti per il costruttore del client.

    Returns:
        Istanza di BaseLLMClient.
    """
    provider = provider.lower()

    if provider == "ollama":
        from computer_graphics.ollama_client import OllamaClient

        return OllamaClient(**kwargs)

    if provider == "openai":
        from computer_graphics.openai_client import OpenAIClient

        return OpenAIClient(**kwargs)

    raise ValueError(f"Provider LLM non supportato: {provider}")
