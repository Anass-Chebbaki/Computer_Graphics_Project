"""
Client HTTP per la comunicazione con Ollama.

Gestisce la chiamata REST all'endpoint locale di Ollama,
compresi timeout, errori di connessione e risposte malformate.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests
from requests.exceptions import ConnectionError, ReadTimeout, RequestException

from computer_graphics.llm_client import (
    BaseLLMClient,
)
from computer_graphics.llm_client import (
    LLMConnectionError as OllamaConnectionError,
)
from computer_graphics.llm_client import (
    LLMResponseError as OllamaResponseError,
)

logger = logging.getLogger(__name__)


class OllamaClient(BaseLLMClient):
    """
    Client per interagire con il server Ollama locale.

    Attributes:
        base_url: URL base del server Ollama.
        timeout: Secondi di attesa massima per una risposta.
        max_connection_retries: Tentativi in caso di errore di rete.
    """

    DEFAULT_BASE_URL: str = "http://localhost:11434"
    CHAT_ENDPOINT: str = "/api/chat"
    TAGS_ENDPOINT: str = "/api/tags"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 180,
        max_connection_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_connection_retries = max_connection_retries
        self.retry_delay = retry_delay

    # ------------------------------------------------------------------
    # Metodi pubblici
    # ------------------------------------------------------------------

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """
        Invia una richiesta di chat al modello e restituisce il testo.

        Args:
            messages: Lista di messaggi (role, content).
            **kwargs: Parametri come 'model', 'options', ecc.

        Returns:
            Stringa con il contenuto della risposta del modello.

        Raises:
            OllamaConnectionError: Se il server non è raggiungibile.
            OllamaResponseError: Se la risposta è malformata.
        """
        url = self.base_url + self.CHAT_ENDPOINT
        payload = {"messages": messages, "stream": False, **kwargs}

        # Supporto per Structured Output
        if kwargs.get("response_format") == "json":
            payload["format"] = "json"
            kwargs.pop("response_format")

        for attempt in range(1, self.max_connection_retries + 1):
            try:
                logger.debug(
                    "Tentativo %d/%d — POST %s (model=%s)",
                    attempt,
                    self.max_connection_retries,
                    url,
                    payload.get("model", "unknown"),
                )

                response = requests.post(
                    url,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()

                try:
                    data = response.json()
                    content = self._extract_content(data)
                except ValueError:
                    import json

                    content = ""
                    for line in response.text.strip().split("\n"):
                        if line:
                            chunk = json.loads(line)
                            content += self._extract_content(chunk)

                logger.debug("Risposta ricevuta (%d caratteri)", len(content))
                return content

            except ConnectionError as exc:
                logger.warning(
                    "Tentativo %d: server Ollama non raggiungibile — %s",
                    attempt,
                    exc,
                )
                if attempt < self.max_connection_retries:
                    time.sleep(self.retry_delay)
                else:
                    raise OllamaConnectionError(
                        f"Impossibile connettersi a Ollama su {self.base_url}. "
                        "Verificare che il server sia avviato con: ollama serve"
                    ) from exc

            except ReadTimeout as exc:
                raise OllamaConnectionError(
                    f"Timeout dopo {self.timeout}s in attesa della risposta. "
                    "Considerare di aumentare il parametro timeout o usare un modello più leggero."  # noqa: E501
                ) from exc

            except RequestException as exc:
                raise OllamaConnectionError(
                    f"Errore HTTP nella comunicazione con Ollama: {exc}"
                ) from exc

        # Non dovrebbe mai arrivare qui
        raise OllamaConnectionError("Tutti i tentativi di connessione falliti.")

    def health_check(self) -> bool:
        """
        Verifica che il server Ollama sia attivo e risponda.

        Returns:
            True se il server è raggiungibile, False altrimenti.
        """
        try:
            response = requests.get(
                self.base_url + self.TAGS_ENDPOINT,
                timeout=30,
            )
            return bool(response.status_code == 200)
        except RequestException:
            return False

    def list_models(self) -> list[str]:
        """
        Restituisce l'elenco dei modelli disponibili localmente.

        Returns:
            Lista di nomi modello (es. ["llama3:latest", "mistral:latest"]).
        """
        try:
            response = requests.get(
                self.base_url + self.TAGS_ENDPOINT,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except RequestException as exc:
            raise OllamaConnectionError(
                f"Impossibile recuperare la lista dei modelli: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Metodi privati
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_content(data: dict) -> str:
        """
        Estrae il testo della risposta dalla struttura JSON di Ollama.

        Args:
            data: Dizionario JSON restituito da Ollama.

        Returns:
            Stringa con il contenuto del messaggio.

        Raises:
            OllamaResponseError: Se la struttura è inattesa.
        """
        try:
            content = data["message"]["content"]
            if not isinstance(content, str):
                raise TypeError(f"Expected str, got {type(content)}")
            return content
        except (KeyError, TypeError) as exc:
            raise OllamaResponseError(
                f"Struttura della risposta Ollama non riconosciuta. "
                f"Chiavi presenti: {list(data.keys())}. "
                f"Errore: {exc}"
            ) from exc
