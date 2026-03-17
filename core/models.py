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
class VisualSegment:
    """A narration-aligned visual segment used in the visual plan.

    Each segment maps a slice of the narration text to one image/scene,
    with timing derived from the estimated speech duration of that text.

    Attributes:
        index: Zero-based position in the visual plan.
        text: The narration text for this segment.
        estimated_start: Estimated start time in the final video (seconds).
        estimated_end: Estimated end time in the final video (seconds).
        estimated_duration: Estimated on-screen duration in seconds.
        image_prompt: The image generation prompt for this segment.
        transition_hint: Optional hint for the transition style (e.g. 'fade').
        emphasis_keyword: Optional keyword that describes the visual focus.
    """

    index: int
    text: str
    estimated_start: float
    estimated_end: float
    estimated_duration: float
    image_prompt: str = ""
    transition_hint: str = ""
    emphasis_keyword: str = ""
    scene_focus: str = "environment"
    shot_type: str = "wide"

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for JSON output."""
        return {
            "index": self.index,
            "text": self.text,
            "estimated_start": round(self.estimated_start, 2),
            "estimated_end": round(self.estimated_end, 2),
            "estimated_duration": round(self.estimated_duration, 2),
            "image_prompt": self.image_prompt,
            "transition_hint": self.transition_hint,
            "emphasis_keyword": self.emphasis_keyword,
            "scene_focus": self.scene_focus,
            "shot_type": self.shot_type,
        }


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
        segmentation_density: Density preset used for segmentation.
        tts_result: TTS result metadata.
        image_results: List of image result metadata.
        visual_plan: Serialised list of VisualSegment dicts.
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
    segmentation_density: str = "balanced"
    prompt_sources: List[str] = field(default_factory=list)
    tts_result: Optional[dict] = None
    image_results: List[dict] = field(default_factory=list)
    visual_plan: List[dict] = field(default_factory=list)
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
            "segmentation_density": self.segmentation_density,
            "prompt_sources": self.prompt_sources,
            "tts_result": self.tts_result,
            "image_results": self.image_results,
            "visual_plan": self.visual_plan,
            "output_video": self.output_video,
            "success": self.success,
            "error": self.error,
            "segments": self.segments,
        }
