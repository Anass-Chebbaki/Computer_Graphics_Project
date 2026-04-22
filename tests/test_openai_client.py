"""Test per il client OpenAI."""

from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import ConnectionError, ReadTimeout, RequestException

from computer_graphics.llm_client import LLMConnectionError, LLMResponseError
from computer_graphics.openai_client import OpenAIClient


@pytest.fixture
def client() -> OpenAIClient:
    """Fixture per OpenAIClient."""
    return OpenAIClient(api_key="test-key", base_url="http://mock-api")


def test_openai_chat_success(client: OpenAIClient) -> None:
    """Test successo chat OpenAI."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Hello world"}}]
    }

    with patch("requests.post", return_value=mock_response) as mock_post:
        response = client.chat([{"role": "user", "content": "hi"}])
        assert response == "Hello world"
        mock_post.assert_called_once()


def test_openai_chat_json_format(client: OpenAIClient) -> None:
    """Test invio response_format='json'."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "{}"}}]}

    with patch("requests.post", return_value=mock_response) as mock_post:
        client.chat([{"role": "user", "content": "hi"}], response_format="json")
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["response_format"] == {"type": "json_object"}


def test_openai_chat_connection_error(client: OpenAIClient) -> None:
    """Test errore di connessione con retry."""
    with patch("requests.post", side_effect=ConnectionError("lost")) as mock_post:
        client.max_connection_retries = 2
        client.retry_delay = 0.01
        with pytest.raises(LLMConnectionError, match="Errore connessione OpenAI"):
            client.chat([{"role": "user", "content": "hi"}])
        assert mock_post.call_count == 2


def test_openai_chat_timeout(client: OpenAIClient) -> None:
    """Test timeout."""
    with (
        patch("requests.post", side_effect=ReadTimeout("timeout")),
        pytest.raises(LLMConnectionError, match="Timeout OpenAI"),
    ):
        client.chat([{"role": "user", "content": "hi"}])


def test_openai_chat_response_error(client: OpenAIClient) -> None:
    """Test errore 500 o altro."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = RequestException("Server Error")

    with (
        patch("requests.post", return_value=mock_response),
        pytest.raises(LLMResponseError, match="Errore risposta OpenAI"),
    ):
        client.chat([{"role": "user", "content": "hi"}])


def test_openai_health_check_success(client: OpenAIClient) -> None:
    """Test health check OK."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    with patch("requests.get", return_value=mock_response):
        assert client.health_check() is True


def test_openai_health_check_fail(client: OpenAIClient) -> None:
    """Test health check FAIL."""
    mock_response = MagicMock()
    mock_response.status_code = 401
    with patch("requests.get", return_value=mock_response):
        assert client.health_check() is False


def test_openai_health_check_exception(client: OpenAIClient) -> None:
    """Test health check EXCEPTION."""
    with patch("requests.get", side_effect=RequestException()):
        assert client.health_check() is False
