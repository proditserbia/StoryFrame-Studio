"""ElevenLabs TTS provider for StoryFrame Studio.

Uses the ElevenLabs REST API to synthesise speech from text.
Requires ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in .env.
"""

from __future__ import annotations

from pathlib import Path

import requests

from core.config import Config
from core.logger import AppLogger
from core.models import TTSResult
from core.narration_prep import prepare_horror_narration
from providers.tts_base import TTSProviderBase

_API_BASE = "https://api.elevenlabs.io/v1"
_TIMEOUT = 120  # seconds

# ---------------------------------------------------------------------------
# Default voice settings tuned for horror narration.
# These produce a calmer, darker, more suspenseful delivery.
# All values can be overridden by subclassing or adjusting here.
# ---------------------------------------------------------------------------
_DEFAULT_VOICE_SETTINGS = {
    # 0.0 = highly variable / expressive, 1.0 = very consistent / stable.
    # A moderate value keeps the voice steady without sounding flat.
    "stability": 0.55,
    # How closely the output resembles the original voice sample.
    "similarity_boost": 0.80,
    # 0.0 = no style exaggeration (calm / neutral).  Keep low for horror.
    "style": 0.10,
    # Boosts speaker clarity, helpful for dramatic low-volume narration.
    "use_speaker_boost": True,
}


class ElevenLabsTTSProvider(TTSProviderBase):
    """TTS provider backed by the ElevenLabs API.

    Args:
        config: Application configuration.
        logger: Logger instance.
    """

    def __init__(self, config: Config, logger: AppLogger) -> None:
        self._config = config
        self._logger = logger

    def synthesize(self, text: str, output_path: Path) -> TTSResult:
        """Generate speech with ElevenLabs and save to *output_path*.

        Args:
            text: Text to synthesise.
            output_path: Destination audio file path.

        Returns:
            TTSResult with the saved audio path.

        Raises:
            RuntimeError: On API failure.
        """
        api_key = self._config.elevenlabs_api_key
        voice_id = self._config.elevenlabs_voice_id

        if not api_key or not voice_id:
            raise RuntimeError(
                "ElevenLabs API key and voice ID must be set in .env"
            )

        self._logger.info(
            "ElevenLabs: synthesising %d chars with voice %s", len(text), voice_id
        )

        # Pre-process text for horror-style pacing (adds subtle pauses,
        # normalises dashes — does NOT alter any words).
        prepared_text = prepare_horror_narration(text)

        url = f"{_API_BASE}/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": prepared_text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": _DEFAULT_VOICE_SETTINGS,
        }

        response = requests.post(url, json=payload, headers=headers, timeout=_TIMEOUT)
        if response.status_code != 200:
            raise RuntimeError(
                f"ElevenLabs API error {response.status_code}: {response.text[:300]}"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        self._logger.info("ElevenLabs: audio saved to %s", output_path)

        return TTSResult(
            audio_path=output_path,
            provider="elevenlabs",
            metadata={"voice_id": voice_id},
        )
