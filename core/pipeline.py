"""Main processing pipeline for StoryFrame Studio.

Orchestrates:
1. Config validation
2. Script loading
3. Narration-aligned segmentation and visual planning
4. TTS narration generation
5. Per-segment image prompt building and image generation
6. Video rendering via FFmpeg with per-segment durations
7. Metadata output

The pipeline is designed to be called from a background thread.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from core.config import Config
from core.ffmpeg_renderer import FFmpegRenderer
from core.logger import AppLogger
from core.models import ImageResult, RunMetadata, VisualSegment, TTSResult
from core.utils import (
    build_image_prompt,
    create_visual_plan,
    ensure_dir,
    format_time,
    get_audio_duration,
    prepend_silence,
    split_script_into_segments,
)
from providers.image_base import ImageProviderBase
from providers.tts_base import TTSProviderBase


class PipelineError(Exception):
    """Raised for recoverable pipeline failures."""


class Pipeline:
    """Full processing pipeline from script to final video.

    Args:
        config: Application configuration.
        logger: Logger instance (with UI callback already attached).
        cancel_event: Set this event to cancel the running pipeline.
        progress_callback: Called with (step_label, percent_complete).
    """

    STEPS = [
        ("Loading config", 5),
        ("Reading script", 10),
        ("Creating visual plan", 20),
        ("Generating narration", 35),
        ("Generating images", 75),
        ("Rendering video", 95),
        ("Done", 100),
    ]

    def __init__(
        self,
        config: Config,
        logger: AppLogger,
        cancel_event: Optional[threading.Event] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        self._config = config
        self._logger = logger
        self._cancel = cancel_event or threading.Event()
        self._progress = progress_callback or (lambda label, pct: None)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        script_path: Path,
        image_instructions_path: Path,
        tts_provider_name: str,
        segmentation_density: str = "balanced",
    ) -> RunMetadata:
        """Execute the full pipeline.

        Args:
            script_path: Path to the script text file.
            image_instructions_path: Path to the image instructions file.
            tts_provider_name: Selected TTS provider ('elevenlabs' or 'deepgram').
            segmentation_density: Segmentation density preset --
                'sparse', 'balanced', or 'detailed'.

        Returns:
            RunMetadata with the results of the run.
        """
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = ensure_dir(self._config.output_dir / run_id)
        temp_dir = ensure_dir(self._config.temp_dir / run_id)

        metadata = RunMetadata(
            run_id=run_id,
            script_file=str(script_path),
            image_instructions_file=str(image_instructions_path),
            tts_provider=tts_provider_name,
            image_provider=self._config.image_provider,
            video_provider=self._config.video_provider,
            segmentation_density=segmentation_density,
        )

        try:
            self._run_impl(
                run_id,
                run_dir,
                temp_dir,
                script_path,
                image_instructions_path,
                tts_provider_name,
                segmentation_density,
                metadata,
            )
        except Exception as exc:
            if self._cancel.is_set():
                self._logger.warning("Pipeline cancelled.")
                metadata.error = "Cancelled by user."
            else:
                self._logger.exception("Pipeline error: %s", exc)
                metadata.error = str(exc)
            metadata.success = False

        # Always write metadata
        self._write_metadata(run_dir / "metadata.json", metadata)
        return metadata

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_impl(
        self,
        run_id: str,
        run_dir: Path,
        temp_dir: Path,
        script_path: Path,
        image_instructions_path: Path,
        tts_provider_name: str,
        segmentation_density: str,
        metadata: RunMetadata,
    ) -> None:
        # 1 -- Validate config
        self._report("Loading config", 5)
        self._config.validate(tts_override=tts_provider_name)
        self._logger.info("Config validated for provider: %s", tts_provider_name)
        self._check_cancel()

        # 2 -- Load files
        self._report("Reading script", 10)
        script_text = self._load_text(script_path, "script")
        image_instructions = self._load_text(
            image_instructions_path, "image instructions"
        )
        self._check_cancel()

        # 3 -- Segment script and create visual plan
        self._report("Creating visual plan", 20)
        self._logger.info(
            "Segmenting script with density='%s'...", segmentation_density
        )
        raw_segments = split_script_into_segments(
            script_text, density=segmentation_density
        )
        visual_plan: List[VisualSegment] = create_visual_plan(raw_segments)
        metadata.segments = len(visual_plan)

        self._logger.info(
            "Visual plan: %d segments, total estimated %.1fs",
            len(visual_plan),
            sum(s.estimated_duration for s in visual_plan),
        )
        for seg in visual_plan:
            preview = seg.text[:60].replace("\n", " ")
            self._logger.info(
                '[Segment %02d] %s - %s | "%s..."',
                seg.index + 1,
                format_time(seg.estimated_start),
                format_time(seg.estimated_end),
                preview,
            )
        self._check_cancel()

        # 4 -- Build image prompts (segment-specific, based on narration text)
        for seg in visual_plan:
            seg.image_prompt = build_image_prompt(
                seg.text, image_instructions, seg.index
            )
            self._logger.info(
                "[Prompt %02d] Generated image prompt based on segment text",
                seg.index + 1,
            )
        self._check_cancel()

        # 5 -- TTS narration
        self._report("Generating narration", 35)
        tts_provider = self._get_tts_provider(tts_provider_name)
        audio_path = temp_dir / "narration.mp3"
        full_script = " ".join(s.text for s in visual_plan)
        tts_result: TTSResult = tts_provider.synthesize(full_script, audio_path)
        metadata.tts_result = {
            "audio_path": str(tts_result.audio_path),
            "duration_seconds": tts_result.duration_seconds,
            "provider": tts_result.provider,
        }
        self._logger.info("Narration saved to: %s", tts_result.audio_path)

        # Prepend configurable leading silence so narration does not start
        # the very instant the video begins.
        leading_silence = self._config.tts_leading_silence
        if leading_silence > 0:
            self._logger.info(
                "[TTS] Prepending %.2fs of silence before narration.",
                leading_silence,
            )
            silenced_path = temp_dir / "narration_with_silence.mp3"
            if prepend_silence(
                self._config.ffmpeg_path,
                tts_result.audio_path,
                leading_silence,
                silenced_path,
            ):
                tts_result = TTSResult(
                    audio_path=silenced_path,
                    provider=tts_result.provider,
                    metadata=tts_result.metadata,
                )
                self._logger.info(
                    "[TTS] Silence prepended successfully. Audio: %s",
                    silenced_path,
                )
            else:
                self._logger.warning(
                    "[TTS] Failed to prepend silence; using original audio."
                )

        # Refine timing: if actual audio duration is available, scale segment
        # durations proportionally so the total video spans the audio length
        # plus the time consumed by xfade overlaps (each transition shortens
        # the combined video by one crossfade_duration worth of frames, so we
        # add that back to ensure the last narration sentence is not cut off).
        actual_duration = get_audio_duration(
            self._config.ffprobe_path, tts_result.audio_path
        )
        if actual_duration and actual_duration > 0:
            segment_count = len(visual_plan)
            crossfade = self._config.crossfade_duration
            if segment_count > 1:
                target_video_duration = (
                    actual_duration + crossfade * (segment_count - 1)
                )
            else:
                target_video_duration = actual_duration

            self._logger.info(
                "[Timing] Actual audio duration: %.2fs", actual_duration
            )
            self._logger.info(
                "[Timing] Crossfade duration: %.2fs", crossfade
            )
            self._logger.info(
                "[Timing] Segment count: %d", segment_count
            )
            self._logger.info(
                "[Timing] Target video duration after xfade compensation: %.2fs",
                target_video_duration,
            )

            total_estimated = sum(s.estimated_duration for s in visual_plan)
            if total_estimated > 0:
                scale = target_video_duration / total_estimated
                cumulative = 0.0
                for seg in visual_plan:
                    seg.estimated_duration = seg.estimated_duration * scale
                    seg.estimated_start = cumulative
                    seg.estimated_end = cumulative + seg.estimated_duration
                    cumulative += seg.estimated_duration
                self._logger.info(
                    "Segment durations scaled by %.3f to match target video"
                    " duration.",
                    scale,
                )
        else:
            self._logger.info(
                "Audio duration unavailable; using estimated segment timing."
            )
        self._check_cancel()

        # Save visual plan to metadata (after timing refinement)
        metadata.visual_plan = [s.to_dict() for s in visual_plan]

        # 6 -- Generate images (one per segment)
        self._report("Generating images", 45)
        image_provider = self._get_image_provider()
        images_dir = ensure_dir(temp_dir / "images")
        image_results: list[ImageResult] = []

        total_segs = len(visual_plan)
        for seg in visual_plan:
            self._check_cancel()
            img_path = images_dir / f"scene_{seg.index:04d}.png"
            self._logger.info(
                "Generating image %d/%d...",
                seg.index + 1,
                total_segs,
            )
            img_result = image_provider.generate(
                seg.image_prompt, img_path, segment_index=seg.index
            )
            image_results.append(img_result)
            metadata.image_results.append(
                {
                    "segment_index": seg.index,
                    "image_path": str(img_result.image_path),
                    "prompt": img_result.prompt[:120],
                    "provider": img_result.provider,
                }
            )
            pct = 45 + int(((seg.index + 1) / total_segs) * 29)
            self._progress(
                f"Generating image {seg.index + 1}/{total_segs}", pct
            )

        self._check_cancel()

        # 7 -- Render video with per-segment durations
        self._report("Rendering video", 76)
        output_video = run_dir / f"output_{run_id}.mp4"
        renderer = FFmpegRenderer(
            self._config, self._logger, cancel_event=self._cancel
        )

        segment_durations = [s.estimated_duration for s in visual_plan]

        for seg, dur in zip(visual_plan, segment_durations):
            self._logger.info(
                "[Render %02d] Using duration %.1fs", seg.index + 1, dur
            )

        def render_progress(current: int, total: int) -> None:
            pct = 76 + int((current / total) * 20)
            self._progress(f"Rendering clip {current}/{total}", pct)

        renderer.render(
            audio_path=tts_result.audio_path,
            image_results=image_results,
            output_path=output_video,
            segment_durations=segment_durations,
            progress_callback=render_progress,
        )

        metadata.output_video = str(output_video)
        metadata.success = True
        self._report("Done", 100)
        self._logger.info("Pipeline complete. Output: %s", output_video)

    def _check_cancel(self) -> None:
        """Raise PipelineError if cancellation was requested."""
        if self._cancel.is_set():
            raise PipelineError("Cancelled by user.")

    def _report(self, label: str, pct: int) -> None:
        """Forward progress update."""
        self._logger.info("[%d%%] %s", pct, label)
        self._progress(label, pct)

    def _load_text(self, path: Path, label: str) -> str:
        """Load text file content.

        Args:
            path: File path.
            label: Human-readable label for error messages.

        Returns:
            File content as string.

        Raises:
            PipelineError: If the file cannot be read.
        """
        self._logger.info("Loading %s: %s", label, path)
        if not path.exists():
            raise PipelineError(f"{label.capitalize()} file not found: {path}")
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PipelineError(f"Could not read {label} file: {exc}") from exc

    def _get_tts_provider(self, name: str) -> "TTSProviderBase":
        """Instantiate the requested TTS provider.

        Args:
            name: Provider name ('elevenlabs' or 'deepgram').

        Returns:
            A TTS provider instance.
        """
        name = name.lower().strip()
        if name == "elevenlabs":
            from providers.elevenlabs_tts import ElevenLabsTTSProvider
            return ElevenLabsTTSProvider(self._config, self._logger)
        elif name == "deepgram":
            from providers.deepgram_tts import DeepgramTTSProvider
            return DeepgramTTSProvider(self._config, self._logger)
        else:
            raise PipelineError(f"Unknown TTS provider: '{name}'")

    def _get_image_provider(self) -> "ImageProviderBase":
        """Instantiate the configured image provider.

        Returns:
            An image provider instance.
        """
        name = self._config.image_provider.lower().strip()
        if name == "replicate":
            from providers.replicate_image import ReplicateImageProvider
            return ReplicateImageProvider(self._config, self._logger)
        else:
            raise PipelineError(f"Unknown image provider: '{name}'")

    @staticmethod
    def _write_metadata(path: Path, metadata: RunMetadata) -> None:
        """Serialise metadata to JSON.

        Args:
            path: Destination file path.
            metadata: RunMetadata instance.
        """
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(metadata.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            pass  # Non-fatal
