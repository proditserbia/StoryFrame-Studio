"""Abstract base class for image generation providers.

New providers must subclass ImageProviderBase and implement ``generate``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from core.models import ImageResult


class ImageProviderBase(ABC):
    """Interface that all image providers must implement."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        output_path: Path,
        segment_index: int = 0,
    ) -> ImageResult:
        """Generate an image from *prompt* and save it to *output_path*.

        Args:
            prompt: The image generation prompt.
            output_path: Destination path for the image file.
            segment_index: Index of the corresponding script segment.

        Returns:
            An :class:`ImageResult` containing the path and metadata.
        """
