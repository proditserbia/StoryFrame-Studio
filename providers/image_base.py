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
        negative_prompt: str = "",
    ) -> ImageResult:
        """Generate an image from *prompt* and save it to *output_path*.

        Args:
            prompt: The image generation prompt.
            output_path: Destination path for the image file.
            segment_index: Index of the corresponding script segment.
            negative_prompt: Optional negative prompt string listing elements
                to exclude from the generated image.  Passed as a separate
                conditioning input to models that support it (e.g. SDXL,
                Stable Diffusion).  Ignored silently by models that do not
                accept a ``negative_prompt`` field.

        Returns:
            An :class:`ImageResult` containing the path and metadata.
        """
