"""Deepgram TTS provider for StoryFrame Studio.

Uses the Deepgram Aura REST API to synthesise speech from text.
Requires DEEPGRAM_API_KEY in .env.
"""

from __future__ import annotations

from pathlib import Path

import requests

from core.config import Config
from core.logger import AppLogger
from core.models import TTSResult
from providers.tts_base import TTSProviderBase

_API_URL = "https://api.deepgram.com/v1/speak"
_TIMEOUT = 120  # seconds


class DeepgramTTSProvider(TTSProviderBase):
    """TTS provider backed by the Deepgram Aura API.

    Args:
        config: Application configuration.
        logger: Logger instance.
    """

    def __init__(self, config: Config, logger: AppLogger) -> None:
        self._config = config
        self._logger = logger

    def synthesize(self, text: str, output_path: Path) -> TTSResult:
        """Generate speech with Deepgram Aura and save to *output_path*.

        Args:
            text: Text to synthesise.
            output_path: Destination audio file path.

        Returns:
            TTSResult with the saved audio path.

        Raises:
            RuntimeError: On API failure.
        """
        api_key = self._config.deepgram_api_key
        model = self._config.deepgram_voice_model

        if not api_key:
            raise RuntimeError("DEEPGRAM_API_KEY must be set in .env")

        self._logger.info(
            "Deepgram: synthesising %d chars with model %s", len(text), model
        )

        params = {"model": model}
        headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        }
        payload = {"text": text}

        response = requests.post(
            _API_URL,
            params=params,
            json=payload,
            headers=headers,
            timeout=_TIMEOUT,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Deepgram API error {response.status_code}: {response.text[:300]}"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        self._logger.info("Deepgram: audio saved to %s", output_path)

        return TTSResult(
            audio_path=output_path,
            provider="deepgram",
            metadata={"model": model},
        )
