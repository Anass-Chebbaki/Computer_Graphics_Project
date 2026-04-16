"""Test per il client Ollama (con mock HTTP)."""

from __future__ import annotations

import json

import pytest
import responses as resp_mock

from computer_graphics.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaResponseError,
)


@resp_mock.activate
class TestOllamaClient:
    BASE_URL = "http://localhost:11434"
    CHAT_URL = f"{BASE_URL}/api/chat"
    TAGS_URL = f"{BASE_URL}/api/tags"

    def test_chat_success(self, mock_ollama_response: dict) -> None:
        resp_mock.add(
            resp_mock.POST, self.CHAT_URL,
            json=mock_ollama_response, status=200,
        )
        client = OllamaClient(base_url=self.BASE_URL)
        result = client.chat({"model": "llama3", "messages": [], "stream": False})
        assert isinstance(result, str)
        assert "table" in result

    def test_health_check_true(self) -> None:
        resp_mock.add(
            resp_mock.GET, self.TAGS_URL,
            json={"models": []}, status=200,
        )
        client = OllamaClient(base_url=self.BASE_URL)
        assert client.health_check() is True

    def test_health_check_false_on_connection_error(self) -> None:
        resp_mock.add(
            resp_mock.GET, self.TAGS_URL,
            body=ConnectionError("refused"),
        )
        client = OllamaClient(base_url=self.BASE_URL)
        assert client.health_check() is False

    def test_raises_on_malformed_response(self) -> None:
        resp_mock.add(
            resp_mock.POST, self.CHAT_URL,
            json={"unexpected": "format"}, status=200,
        )
        client = OllamaClient(base_url=self.BASE_URL)
        with pytest.raises(OllamaResponseError):
            client.chat({"model": "llama3", "messages": [], "stream": False})

    def test_list_models(self) -> None:
        resp_mock.add(
            resp_mock.GET, self.TAGS_URL,
            json={"models": [{"name": "llama3:latest"}, {"name": "mistral:latest"}]},
            status=200,
        )
        client = OllamaClient(base_url=self.BASE_URL)
        models = client.list_models()
        assert "llama3:latest" in models
        assert "mistral:latest" in models