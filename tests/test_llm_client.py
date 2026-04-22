"""Test per la factory llm_client."""

import pytest

from computer_graphics.llm_client import (
    BaseLLMClient,
    get_llm_client,
)
from computer_graphics.ollama_client import OllamaClient
from computer_graphics.openai_client import OpenAIClient


def test_get_llm_client_ollama() -> None:
    """Verifica istanziazione OllamaClient."""
    client = get_llm_client("ollama", base_url="http://local")
    assert isinstance(client, OllamaClient)
    assert isinstance(client, BaseLLMClient)


def test_get_llm_client_openai() -> None:
    """Verifica istanziazione OpenAIClient."""
    client = get_llm_client("openai", api_key="sk-test")
    assert isinstance(client, OpenAIClient)
    assert isinstance(client, BaseLLMClient)


def test_get_llm_client_case_insensitive() -> None:
    """Verifica case insensitivity del provider."""
    client = get_llm_client("OpenAI", api_key="sk-test")
    assert isinstance(client, OpenAIClient)


def test_get_llm_client_invalid() -> None:
    """Verifica errore per provider non supportato."""
    with pytest.raises(ValueError, match="Provider LLM non supportato: unknown"):
        get_llm_client("unknown")
