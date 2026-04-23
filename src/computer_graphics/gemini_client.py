"""
Client per la comunicazione con Google Gemini API.

Supporta Gemini 3.0 Flash (testo e vision) come provider LLM cloud
in alternativa o in aggiunta a Ollama locale.
"""
from __future__ import annotations

import base64
import logging
import time
from pathlib import Path
from typing import Any

import requests
from requests.exceptions import ConnectionError, ReadTimeout, RequestException

from computer_graphics.llm_client import (
    BaseLLMClient,
    LLMConnectionError as GeminiConnectionError,
    LLMResponseError as GeminiResponseError,
)


logger = logging.getLogger(__name__)

# Endpoint base per Gemini API v1beta
_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Modello di default: Gemini 3.0 Flash (aprile 2026)
_DEFAULT_MODEL = "gemini-3-flash-preview"

# Modello con capacità vision per il critic loop
_VISION_MODEL = "gemini-3-flash-preview"


class GeminiClient(BaseLLMClient):
    """
    Client per interagire con Google Gemini API.

    Supporta sia richieste testuali (scene planning) sia multimodali
    (critic loop con immagini render).

    Attributes:
        api_key: Chiave API Google Gemini.
        model: Nome del modello da utilizzare.
        timeout: Secondi di attesa massima per una risposta.
        max_connection_retries: Tentativi in caso di errore di rete.
        retry_delay: Secondi di attesa tra i tentativi.
    """

    DEFAULT_MODEL: str = _DEFAULT_MODEL
    VISION_MODEL: str = _VISION_MODEL

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        timeout: int = 120,
        max_connection_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_connection_retries = max_connection_retries
        self.retry_delay = retry_delay

    # ------------------------------------------------------------------
    # Metodi pubblici
    # ------------------------------------------------------------------

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """
        Invia una richiesta testuale a Gemini e restituisce la risposta.

        Args:
            messages: Lista di messaggi nel formato OpenAI-compatibile
                ``[{"role": "user", "content": "..."}]``.
            **kwargs: Parametri aggiuntivi (ignorati per compatibilita).

        Returns:
            Stringa con il testo della risposta del modello.

        Raises:
            GeminiConnectionError: Se l'API non e raggiungibile.
            GeminiResponseError: Se la risposta e malformata.
        """
        contents = self._convert_messages_to_contents(messages)
        return self._generate(contents, model=self.model)

    def chat_with_image(
        self,
        text_prompt: str,
        image_path: str | Path,
        model: str | None = None,
    ) -> str:
        """
        Invia una richiesta multimodale (testo + immagine) a Gemini.

        Utilizzato dal critic loop per analizzare visivamente il render
        preliminare e generare feedback correttivo.

        Args:
            text_prompt: Testo del prompt da inviare al modello.
            image_path: Percorso all'immagine PNG/JPEG da allegare.
            model: Modello vision da usare (default: VISION_MODEL).

        Returns:
            Stringa con la risposta testuale del modello.

        Raises:
            GeminiConnectionError: Se l'API non e raggiungibile.
            GeminiResponseError: Se la risposta e malformata.
            FileNotFoundError: Se il file immagine non esiste.
        """
        image_file = Path(image_path)
        if not image_file.exists():
            raise FileNotFoundError(
                f"Immagine per il critic loop non trovata: {image_file.resolve()}"
            )

        image_data = image_file.read_bytes()
        image_b64 = base64.b64encode(image_data).decode("utf-8")
        mime_type = _guess_mime_type(image_file)

        contents = [
            {
                "parts": [
                    {"text": text_prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": image_b64,
                        }
                    },
                ]
            }
        ]

        effective_model = model or self.VISION_MODEL
        return self._generate(contents, model=effective_model)

    def health_check(self) -> bool:
        """
        Verifica che l'API Gemini sia raggiungibile e la chiave sia valida.

        Returns:
            True se l'API risponde correttamente, False altrimenti.
        """
        url = (
            f"{_GEMINI_API_BASE}/{self.model}"
            f"?key={self.api_key}"
        )
        try:
            response = requests.get(url, timeout=10)
            return response.status_code in (200, 400)
        except RequestException:
            return False

    # ------------------------------------------------------------------
    # Metodi privati
    # ------------------------------------------------------------------

    def _generate(
        self,
        contents: list[dict[str, Any]],
        model: str,
    ) -> str:
        """
        Esegue la chiamata REST a Gemini generateContent.

        Args:
            contents: Lista di parti nel formato Gemini API.
            model: Nome del modello da interrogare.

        Returns:
            Testo della risposta estratto dalla struttura JSON.

        Raises:
            GeminiConnectionError: In caso di errori di rete.
            GeminiResponseError: Se la struttura della risposta e inattesa.
        """
        url = f"{_GEMINI_API_BASE}/{model}:generateContent?key={self.api_key}"
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.2,
                "topP": 0.9,
                "maxOutputTokens": 8192,
            },
        }

        for attempt in range(1, self.max_connection_retries + 1):
            try:
                logger.debug(
                    "Tentativo %d/%d --- POST %s (model=%s)",
                    attempt,
                    self.max_connection_retries,
                    url.split("?")[0],
                    model,
                )
                response = requests.post(
                    url,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                content = self._extract_text(data)
                logger.debug(
                    "Risposta Gemini ricevuta (%d caratteri).", len(content)
                )
                return content

            except ConnectionError as exc:
                logger.warning(
                    "Tentativo %d: Gemini API non raggiungibile --- %s",
                    attempt,
                    exc,
                )
                if attempt < self.max_connection_retries:
                    time.sleep(self.retry_delay)
                else:
                    raise GeminiConnectionError(
                        f"Impossibile connettersi a Gemini API dopo "
                        f"{self.max_connection_retries} tentativi. "
                        "Verificare la connessione internet e la chiave API."
                    ) from exc

            except ReadTimeout as exc:
                raise GeminiConnectionError(
                    f"Timeout dopo {self.timeout}s in attesa della risposta Gemini. "
                    "Considerare di aumentare il parametro timeout."
                ) from exc

            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else "?"
                if status == 429:
                    # Rate limit: attendi prima di riprovare
                    wait = self.retry_delay * (attempt * 2)
                    logger.warning(
                        "Gemini rate limit (429). Attesa %.1f s prima del tentativo %d.",
                        wait,
                        attempt + 1,
                    )
                    if attempt < self.max_connection_retries:
                        time.sleep(wait)
                        continue
                raise GeminiConnectionError(
                    f"Errore HTTP {status} da Gemini API: {exc}"
                ) from exc

            except RequestException as exc:
                raise GeminiConnectionError(
                    f"Errore di rete nella comunicazione con Gemini: {exc}"
                ) from exc

        raise GeminiConnectionError("Tutti i tentativi di connessione a Gemini falliti.")

    @staticmethod
    def _convert_messages_to_contents(
        messages: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """
        Converte il formato messaggi OpenAI-compatibile nel formato Gemini.

        I messaggi di sistema vengono anteposti come testo utente poiche
        Gemini gestisce i system prompt in modo diverso da OpenAI.

        Args:
            messages: Lista di messaggi con chiavi ``role`` e ``content``.

        Returns:
            Lista di contenuti nel formato Gemini API.
        """
        contents: list[dict[str, Any]] = []
        system_parts: list[dict[str, str]] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                # Gemini non ha un ruolo system esplicito: lo prependiamo
                system_parts.append({"text": f"[SYSTEM INSTRUCTIONS]\n{content}\n"})
            elif role == "user":
                parts: list[dict[str, str]] = []
                if system_parts:
                    parts.extend(system_parts)
                    system_parts = []
                parts.append({"text": content})
                contents.append({"role": "user", "parts": parts})
            elif role == "assistant":
                contents.append(
                    {"role": "model", "parts": [{"text": content}]}
                )

        return contents

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        """
        Estrae il testo dalla struttura JSON della risposta Gemini.

        Args:
            data: Dizionario JSON restituito dall'API Gemini.

        Returns:
            Stringa con il testo del primo candidato.

        Raises:
            GeminiResponseError: Se la struttura e inattesa o assente.
        """
        try:
            candidates = data.get("candidates", [])
            if not candidates:
                # Controlla se c'e un promptFeedback che indica blocco
                feedback = data.get("promptFeedback", {})
                block_reason = feedback.get("blockReason", "")
                raise GeminiResponseError(
                    f"Gemini non ha restituito candidati. "
                    f"Motivo blocco: {block_reason or 'sconosciuto'}. "
                    f"Chiavi presenti: {list(data.keys())}"
                )
            candidate = candidates[0]
            parts = candidate.get("content", {}).get("parts", [])
            if not parts:
                raise GeminiResponseError(
                    "Risposta Gemini priva di parti testuali."
                )
            text = "".join(p.get("text", "") for p in parts)
            if not text:
                raise GeminiResponseError(
                    "Risposta Gemini contiene parti vuote."
                )
            return text
        except (KeyError, TypeError, IndexError) as exc:
            raise GeminiResponseError(
                f"Struttura risposta Gemini non riconosciuta. "
                f"Chiavi: {list(data.keys())}. Errore: {exc}"
            ) from exc


def _guess_mime_type(path: Path) -> str:
    """
    Determina il MIME type dell'immagine dall'estensione del file.

    Args:
        path: Percorso al file immagine.

    Returns:
        Stringa MIME type (es. ``"image/png"``).
    """
    ext = path.suffix.lower()
    mapping = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    return mapping.get(ext, "image/png")