"""Dummy / no-op video provider for StoryFrame Studio.

Used when VIDEO_PROVIDER=none.  Future providers (Runway, Pika, etc.) can
be added by implementing :class:`providers.video_base.VideoProviderBase`.
"""

from __future__ import annotations

from pathlib import Path

from providers.video_base import VideoProviderBase, VideoResult


class DummyVideoProvider(VideoProviderBase):
    """No-op video provider that returns a placeholder result.

    This exists to keep the architecture ready for real video providers
    without breaking the pipeline when no video API is configured.
    """

    def generate(
        self,
        prompt: str,
        output_path: Path,
        reference_image: Path | None = None,
        duration_seconds: float = 4.0,
    ) -> VideoResult:
        """Return a result indicating no video was generated.

        Args:
            prompt: Ignored.
            output_path: Not written – returned as-is.
            reference_image: Ignored.
            duration_seconds: Ignored.

        Returns:
            A :class:`VideoResult` with a placeholder provider name.
        """
        # TODO: Replace with a real provider implementation.
        return VideoResult(
            video_path=output_path,
            provider="dummy",
            metadata={"note": "No video provider configured."},
        )
