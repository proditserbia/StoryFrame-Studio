"""Configuration loader for StoryFrame Studio.

Reads settings from .env and environment variables, validates them based
on the selected providers, and exposes a single Config dataclass throughout
the application.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def _load_env() -> None:
    """Load .env from the project root (one level above core/)."""
    root = Path(__file__).resolve().parent.parent
    env_file = root / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    else:
        # Try to load from the current working directory
        load_dotenv()


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


class Config:
    """Application configuration loaded from environment variables."""

    # --- TTS ---
    tts_provider: str
    elevenlabs_api_key: Optional[str]
    elevenlabs_voice_id: Optional[str]
    deepgram_api_key: Optional[str]
    deepgram_voice_model: str
    tts_leading_silence: float
    tts_trailing_silence: float

    # --- Image ---
    image_provider: str
    replicate_api_token: Optional[str]
    replicate_model: Optional[str]
    image_validation_retries: int

    # --- Video ---
    video_provider: str
    video_provider_api_key: Optional[str]

    # --- FFmpeg ---
    ffmpeg_path: str
    ffprobe_path: str
    use_nvenc_auto: bool
    default_fps: int
    default_resolution: str
    image_duration_seconds: float
    zoom_style: str
    crossfade_duration: float

    # --- Paths ---
    output_dir: Path
    temp_dir: Path

    def __init__(self) -> None:
        _load_env()

        # TTS
        self.tts_provider = os.getenv("TTS_PROVIDER", "elevenlabs").lower().strip()
        self.elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY") or None
        self.elevenlabs_voice_id = os.getenv("ELEVENLABS_VOICE_ID") or None
        self.deepgram_api_key = os.getenv("DEEPGRAM_API_KEY") or None
        self.deepgram_voice_model = os.getenv(
            "DEEPGRAM_VOICE_MODEL", "aura-asteria-en"
        )
        # Seconds of silence to prepend before narration (0 = disabled).
        self.tts_leading_silence = float(
            os.getenv("TTS_LEADING_SILENCE_SECONDS", "0.0")
        )
        # Seconds of silence to append after narration (0 = disabled).
        self.tts_trailing_silence = float(
            os.getenv("TTS_TRAILING_SILENCE_SECONDS", "0.0")
        )

        # Image
        self.image_provider = os.getenv("IMAGE_PROVIDER", "replicate").lower().strip()
        self.replicate_api_token = os.getenv("REPLICATE_API_TOKEN") or None
        self.replicate_model = os.getenv("REPLICATE_MODEL") or None
        # Number of additional generation attempts when post-generation
        # validation fails (0 = no retries; placeholder for future QA).
        self.image_validation_retries = int(
            os.getenv("IMAGE_VALIDATION_RETRIES", "0")
        )

        # Video
        self.video_provider = os.getenv("VIDEO_PROVIDER", "none").lower().strip()
        self.video_provider_api_key = os.getenv("VIDEO_PROVIDER_API_KEY") or None

        # FFmpeg
        self.ffmpeg_path = os.getenv("FFMPEG_PATH", "ffmpeg")
        self.ffprobe_path = os.getenv("FFPROBE_PATH", "ffprobe")
        self.use_nvenc_auto = os.getenv("USE_NVENC_AUTO", "true").lower() == "true"
        self.default_fps = int(os.getenv("DEFAULT_FPS", "30"))
        self.default_resolution = os.getenv("DEFAULT_RESOLUTION", "1920x1080")
        self.image_duration_seconds = float(
            os.getenv("IMAGE_DURATION_SECONDS", "8")
        )
        self.zoom_style = os.getenv("ZOOM_STYLE", "ken_burns")
        self.crossfade_duration = float(os.getenv("CROSSFADE_DURATION", "1.0"))

        # Paths – resolve relative to project root
        root = Path(__file__).resolve().parent.parent
        self.output_dir = root / os.getenv("OUTPUT_DIR", "projects/output")
        self.temp_dir = root / os.getenv("TEMP_DIR", "projects/temp")

    def validate(self, tts_override: Optional[str] = None) -> None:
        """Validate required config keys for the selected providers.

        Args:
            tts_override: Override the TTS provider (from UI dropdown).

        Raises:
            ConfigError: When a required key is missing.
        """
        provider = (tts_override or self.tts_provider).lower().strip()

        if provider == "elevenlabs":
            if not self.elevenlabs_api_key:
                raise ConfigError(
                    "ELEVENLABS_API_KEY is required when TTS_PROVIDER=elevenlabs"
                )
            if not self.elevenlabs_voice_id:
                raise ConfigError(
                    "ELEVENLABS_VOICE_ID is required when TTS_PROVIDER=elevenlabs"
                )
        elif provider == "deepgram":
            if not self.deepgram_api_key:
                raise ConfigError(
                    "DEEPGRAM_API_KEY is required when TTS_PROVIDER=deepgram"
                )
        else:
            raise ConfigError(f"Unknown TTS provider: '{provider}'")

        if self.image_provider == "replicate":
            if not self.replicate_api_token:
                raise ConfigError(
                    "REPLICATE_API_TOKEN is required when IMAGE_PROVIDER=replicate"
                )
            if not self.replicate_model:
                raise ConfigError(
                    "REPLICATE_MODEL is required when IMAGE_PROVIDER=replicate"
                )

    @property
    def resolution_tuple(self) -> tuple[int, int]:
        """Return (width, height) from DEFAULT_RESOLUTION string."""
        parts = self.default_resolution.lower().split("x")
        return int(parts[0]), int(parts[1])
