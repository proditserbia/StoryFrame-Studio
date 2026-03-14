"""Data models for StoryFrame Studio.

Lightweight dataclasses that flow through the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class ScriptSegment:
    """A logical segment of the script (scene/section).

    Attributes:
        index: Zero-based position in the segment list.
        text: The raw text of this segment.
        estimated_duration: Approximate narration duration in seconds.
        image_prompt: Generated image prompt for this segment.
    """

    index: int
    text: str
    estimated_duration: float = 0.0
    image_prompt: str = ""


@dataclass
class TTSResult:
    """Result returned by a TTS provider after synthesis.

    Attributes:
        audio_path: Path to the generated audio file.
        duration_seconds: Duration of the audio in seconds (if available).
        provider: Name of the provider that generated the audio.
        metadata: Extra provider-specific data.
    """

    audio_path: Path
    duration_seconds: Optional[float] = None
    provider: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class ImageResult:
    """Result returned by an image provider after generation.

    Attributes:
        image_path: Path to the saved image file.
        segment_index: The script segment this image belongs to.
        prompt: The prompt that was used.
        provider: Name of the provider.
        metadata: Extra provider-specific data.
    """

    image_path: Path
    segment_index: int
    prompt: str = ""
    provider: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class RunMetadata:
    """Metadata written to ``metadata.json`` for each pipeline run.

    Attributes:
        run_id: Unique run identifier (timestamp-based).
        script_file: Path to the input script file.
        image_instructions_file: Path to the image instructions file.
        tts_provider: Name of the TTS provider used.
        image_provider: Name of the image provider used.
        video_provider: Name of the video provider used.
        tts_result: TTS result metadata.
        image_results: List of image result metadata.
        output_video: Path to the final rendered MP4.
        success: Whether the run completed successfully.
        error: Error message if unsuccessful.
        segments: Number of script segments processed.
    """

    run_id: str
    script_file: str
    image_instructions_file: str
    tts_provider: str
    image_provider: str
    video_provider: str
    tts_result: Optional[dict] = None
    image_results: List[dict] = field(default_factory=list)
    output_video: Optional[str] = None
    success: bool = False
    error: Optional[str] = None
    segments: int = 0

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for JSON output."""
        return {
            "run_id": self.run_id,
            "script_file": self.script_file,
            "image_instructions_file": self.image_instructions_file,
            "tts_provider": self.tts_provider,
            "image_provider": self.image_provider,
            "video_provider": self.video_provider,
            "tts_result": self.tts_result,
            "image_results": self.image_results,
            "output_video": self.output_video,
            "success": self.success,
            "error": self.error,
            "segments": self.segments,
        }
