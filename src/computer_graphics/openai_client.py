"""
Client per la comunicazione con provider compatibili OpenAI.

Supporta GPT-4, Anthropic via proxy, e altri modelli strutturati.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests
from requests.exceptions import ConnectionError, ReadTimeout, RequestException

from computer_graphics.llm_client import (
    BaseLLMClient,
    LLMConnectionError as OpenAIConnectionError,
    LLMResponseError as OpenAIResponseError,
)


logger = logging.getLogger(__name__)


class OpenAIClient(BaseLLMClient):
    """
    Client per interagire con API compatibili OpenAI.
    """

    DEFAULT_BASE_URL: str = "https://api.openai.com/v1"

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 180,
        max_connection_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_connection_retries = max_connection_retries
        self.retry_delay = retry_delay

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Invia richiesta chat via API OpenAI."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {"messages": messages, **kwargs}

        # Supporto per Structured Output
        if kwargs.get("response_format") == "json":
            payload["response_format"] = {"type": "json_object"}
            kwargs.pop("response_format")

        for attempt in range(1, self.max_connection_retries + 1):
            try:
                logger.debug(
                    "Tentativo %d/%d — POST %s",
                    attempt,
                    self.max_connection_retries,
                    url,
                )
                response = requests.post(
                    url, headers=headers, json=payload, timeout=self.timeout
                )
                response.raise_for_status()
                data = response.json()

                content = str(data["choices"][0]["message"]["content"])
                logger.debug("Risposta ricevuta (%d caratteri)", len(content))
                return content

            except ConnectionError as exc:
                if attempt < self.max_connection_retries:
                    time.sleep(self.retry_delay)
                else:
                    raise OpenAIConnectionError(
                        f"Errore connessione OpenAI: {exc}"
                    ) from exc
            except ReadTimeout as exc:
                raise OpenAIConnectionError(
                    f"Timeout OpenAI dopo {self.timeout}s"
                ) from exc
            except (RequestException, KeyError, IndexError) as exc:
                raise OpenAIResponseError(f"Errore risposta OpenAI: {exc}") from exc

        raise OpenAIConnectionError("Tutti i tentativi falliti.")

    def health_check(self) -> bool:
        """Verifica minima della raggiungibilità del base_url."""
        try:
            # Semplice check del base_url o modelli
            response = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            return response.status_code == 200
        except RequestException:
            return False
