"""Abstract base class for video generation providers.

Placeholder architecture for future video providers such as Runway or Pika Labs.
New providers must subclass VideoProviderBase and implement ``generate``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class VideoResult:
    """Result returned by a video provider.

    Attributes:
        video_path: Path to the generated video file.
        provider: Provider name.
        metadata: Extra provider-specific data.
    """

    def __init__(
        self,
        video_path: Path,
        provider: str = "",
        metadata: dict | None = None,
    ) -> None:
        self.video_path = video_path
        self.provider = provider
        self.metadata: dict = metadata or {}


class VideoProviderBase(ABC):
    """Interface that all video providers must implement."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        output_path: Path,
        reference_image: Path | None = None,
        duration_seconds: float = 4.0,
    ) -> VideoResult:
        """Generate a short video clip from a prompt.

        Args:
            prompt: Text prompt describing the scene.
            output_path: Destination path for the video file.
            reference_image: Optional reference/starting image.
            duration_seconds: Desired clip length.

        Returns:
            A :class:`VideoResult` containing the path and metadata.
        """
