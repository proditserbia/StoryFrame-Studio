"""Abstract base class for TTS (Text-to-Speech) providers.

New providers must subclass TTSProviderBase and implement ``synthesize``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from core.models import TTSResult


class TTSProviderBase(ABC):
    """Interface that all TTS providers must implement."""

    @abstractmethod
    def synthesize(self, text: str, output_path: Path) -> TTSResult:
        """Convert text to speech and save the audio file.

        Args:
            text: The full narration text to synthesise.
            output_path: Destination path for the audio file.

        Returns:
            A :class:`TTSResult` containing the path and metadata.
        """
