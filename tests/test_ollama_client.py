"""Test estesi per ollama_client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import responses as resp_mock
from requests.exceptions import ConnectionError, ReadTimeout, RequestException

from computer_graphics.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaResponseError,
)


@resp_mock.activate
class TestOllamaClientExtended:
    BASE_URL = "http://localhost:11434"
    CHAT_URL = f"{BASE_URL}/api/chat"
    TAGS_URL = f"{BASE_URL}/api/tags"

    def test_chat_raises_on_read_timeout(self) -> None:
        """Copre la riga ReadTimeout -> OllamaConnectionError."""
        resp_mock.add(
            resp_mock.POST,
            self.CHAT_URL,
            body=ReadTimeout("timeout"),
        )
        client = OllamaClient(
            base_url=self.BASE_URL, timeout=1, max_connection_retries=1
        )
        with pytest.raises(OllamaConnectionError, match="Timeout"):
            client.chat(messages=[], model="llama3", stream=False)

    def test_chat_raises_on_request_exception(self) -> None:
        """Copre RequestException generico -> OllamaConnectionError."""
        resp_mock.add(
            resp_mock.POST,
            self.CHAT_URL,
            body=RequestException("generic error"),
        )
        client = OllamaClient(base_url=self.BASE_URL, max_connection_retries=1)
        with pytest.raises(OllamaConnectionError, match="Errore HTTP"):
            client.chat(messages=[], model="llama3", stream=False)

    def test_chat_retries_on_connection_error(self) -> None:
        """Copre la logica di retry con ConnectionError."""
        # Prima fallisce, poi riesce
        resp_mock.add(
            resp_mock.POST,
            self.CHAT_URL,
            body=ConnectionError("refused"),
        )
        resp_mock.add(
            resp_mock.POST,
            self.CHAT_URL,
            json={
                "message": {
                    "role": "assistant",
                    "content": '[{"name": "table", "x": 0, "y": 0, "z": 0}]',
                }
            },
            status=200,
        )
        client = OllamaClient(
            base_url=self.BASE_URL,
            max_connection_retries=2,
            retry_delay=0.0,
        )
        result = client.chat(messages=[], model="llama3", stream=False)
        assert "table" in result

    def test_chat_raises_connection_error_after_all_retries(self) -> None:
        """Copre il raise finale dopo max_connection_retries."""
        for _ in range(3):
            resp_mock.add(
                resp_mock.POST,
                self.CHAT_URL,
                body=ConnectionError("refused"),
            )
        client = OllamaClient(
            base_url=self.BASE_URL,
            max_connection_retries=3,
            retry_delay=0.0,
        )
        with pytest.raises(OllamaConnectionError, match="Impossibile connettersi"):
            client.chat(messages=[], model="llama3", stream=False)

    def test_list_models_raises_on_connection_error(self) -> None:
        """Copre list_models con RequestException."""
        resp_mock.add(
            resp_mock.GET,
            self.TAGS_URL,
            body=ConnectionError("refused"),
        )
        client = OllamaClient(base_url=self.BASE_URL)
        with pytest.raises(OllamaConnectionError, match="lista dei modelli"):
            client.list_models()

    def test_extract_content_raises_on_missing_message_key(self) -> None:
        """Copre _extract_content con struttura mancante."""
        resp_mock.add(
            resp_mock.POST,
            self.CHAT_URL,
            json={"done": True},
            status=200,
        )
        client = OllamaClient(base_url=self.BASE_URL)
        with pytest.raises(OllamaResponseError):
            client.chat(messages=[], model="llama3", stream=False)

    def test_extract_content_raises_on_non_string_content(self) -> None:
        """Copre _extract_content quando content non è stringa."""
        resp_mock.add(
            resp_mock.POST,
            self.CHAT_URL,
            json={"message": {"role": "assistant", "content": 12345}},
            status=200,
        )
        client = OllamaClient(base_url=self.BASE_URL)
        with pytest.raises(OllamaResponseError):
            client.chat(messages=[], model="llama3", stream=False)

    def test_health_check_returns_false_on_non_200(self) -> None:
        """Health check con status != 200."""
        resp_mock.add(
            resp_mock.GET,
            self.TAGS_URL,
            json={},
            status=500,
        )
        client = OllamaClient(base_url=self.BASE_URL)
        assert client.health_check() is False

    def test_chat_endpoint_url_construction(self) -> None:
        client = OllamaClient(base_url=self.BASE_URL)
        assert client.base_url + client.CHAT_ENDPOINT == self.CHAT_URL

    def test_list_models_empty(self) -> None:
        resp_mock.add(
            resp_mock.GET,
            self.TAGS_URL,
            json={"models": []},
            status=200,
        )
        client = OllamaClient(base_url=self.BASE_URL)
        models = client.list_models()
        assert models == []


# ====== Tests da test_ollama_client_coverage.py ======


class TestOllamaClientChatExceptionsMock:
    @patch("computer_graphics.ollama_client.requests.post")
    def test_connection_error_retries_and_fails(self, mock_post: MagicMock) -> None:
        mock_post.side_effect = ConnectionError("Could not connect")
        client = OllamaClient(max_connection_retries=2, retry_delay=0.1)

        with pytest.raises(
            OllamaConnectionError, match="Impossibile connettersi a Ollama"
        ):
            client.chat(messages=[], model="test")

        assert mock_post.call_count == 2

    @patch("computer_graphics.ollama_client.requests.post")
    def test_read_timeout_error(self, mock_post: MagicMock) -> None:
        mock_post.side_effect = ReadTimeout("Read timeout")
        client = OllamaClient(max_connection_retries=2, retry_delay=0.1)

        with pytest.raises(OllamaConnectionError, match="Timeout dopo"):
            client.chat(messages=[], model="test")

    @patch("computer_graphics.ollama_client.requests.post")
    def test_request_exception(self, mock_post: MagicMock) -> None:
        mock_post.side_effect = RequestException("HTTP error")
        client = OllamaClient(max_connection_retries=2, retry_delay=0.1)

        with pytest.raises(OllamaConnectionError, match="Errore HTTP"):
            client.chat(messages=[], model="test")

    @staticmethod
    def test_extract_content_key_error() -> None:
        with pytest.raises(
            OllamaResponseError,
            match="Struttura della risposta Ollama non riconosciuta",
        ):
            OllamaClient._extract_content({"wrong_key": "value"})

    @staticmethod
    def test_extract_content_type_error() -> None:
        with pytest.raises(
            OllamaResponseError,
            match="Struttura della risposta Ollama non riconosciuta",
        ):
            OllamaClient._extract_content({"message": {"content": 123}})


class TestOllamaClientOtherEndpointsMock:
    @patch("computer_graphics.ollama_client.requests.get")
    def test_health_check_exception(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = RequestException("Failed health check")
        client = OllamaClient()
        assert client.health_check() is False

    @patch("computer_graphics.ollama_client.requests.get")
    def test_list_models_success(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3:latest"},
                {"name": "mistral:latest"},
            ]
        }
        mock_get.return_value = mock_response

        client = OllamaClient()
        models = client.list_models()
        assert models == ["llama3:latest", "mistral:latest"]

    @patch("computer_graphics.ollama_client.requests.get")
    def test_list_models_exception(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = RequestException("Failed to list models")
        client = OllamaClient()

        with pytest.raises(
            OllamaConnectionError,
            match="Impossibile recuperare la lista dei modelli",
        ):
            client.list_models()


class TestOllamaClientAdditional:
    """Test aggiuntivi per ollama_client.py coverage."""

    @patch("computer_graphics.ollama_client.requests.post")
    def test_chat_success_response_extraction(self, mock_post: MagicMock) -> None:
        """Verifica corretta estrazione del contenuto dalla risposta."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"role": "assistant", "content": "test response"}
        }
        mock_post.return_value = mock_response

        client = OllamaClient()
        result = client.chat(messages=[], model="test")
        assert result == "test response"

    @patch("computer_graphics.ollama_client.requests.post")
    def test_chat_http_error_status(self, mock_post: MagicMock) -> None:
        """Test handling di HTTP error status."""
        from requests.exceptions import HTTPError

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = HTTPError("HTTP 500")
        mock_post.return_value = mock_response

        client = OllamaClient()
        with pytest.raises(OllamaConnectionError):
            client.chat(messages=[], model="test")

    @patch("computer_graphics.ollama_client.requests.post")
    def test_chat_json_format_support(self, mock_post: MagicMock) -> None:
        """Verifica il supporto al parametro response_format='json'."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"role": "assistant", "content": "{}"}
        }
        mock_post.return_value = mock_response

        client = OllamaClient()
        client.chat(messages=[], response_format="json")

        # Verifica che 'format': 'json' sia stato aggiunto al payload
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["format"] == "json"

    @patch("computer_graphics.ollama_client.requests.post")
    def test_chat_streaming_fallback(self, mock_post: MagicMock) -> None:
        """Verifica il fallback su parsing manuale se response.json() fallisce."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Not a JSON")
        mock_response.text = (
            '{"message": {"role": "assistant", "content": "chunk1"}}\n'
            '{"message": {"role": "assistant", "content": "chunk2"}}\n'
        )
        mock_post.return_value = mock_response

        client = OllamaClient()
        result = client.chat(messages=[])
        assert result == "chunk1chunk2"

    @patch("computer_graphics.ollama_client.requests.get")
    def test_health_check_success(self, mock_get: MagicMock) -> None:
        """Verifica health_check con successo (status 200)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        client = OllamaClient()
        assert client.health_check() is True
