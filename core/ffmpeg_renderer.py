"""FFmpeg rendering module for StoryFrame Studio.

Handles:
- NVENC auto-detection
- Ken Burns (zoom/pan) effect per image
- Crossfade transitions between images
- Final MP4 output with embedded narration audio

All heavy lifting is delegated to FFmpeg subprocesses.
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Callable, List, Optional

from core.config import Config
from core.logger import AppLogger
from core.models import ImageResult


def _detect_nvenc(ffmpeg_path: str, logger: AppLogger) -> bool:
    """Return True if h264_nvenc encoder is available.

    Args:
        ffmpeg_path: Path to ffmpeg executable.
        logger: Logger instance.
    """
    try:
        result = subprocess.run(
            [ffmpeg_path, "-encoders"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        available = "h264_nvenc" in result.stdout
        if available:
            logger.info("NVENC encoder detected – hardware acceleration enabled.")
        else:
            logger.info("NVENC not available – using libx264 (software encoding).")
        return available
    except Exception as exc:
        logger.warning("Could not check NVENC availability: %s", exc)
        return False


class FFmpegRenderer:
    """Renders the final MP4 from images and narration audio.

    Args:
        config: Application config.
        logger: Logger instance.
        cancel_event: Optional threading.Event; if set, rendering aborts.
    """

    def __init__(
        self,
        config: Config,
        logger: AppLogger,
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        self._config = config
        self._logger = logger
        self._cancel = cancel_event or threading.Event()
        self._use_nvenc: Optional[bool] = None

    def _encoder(self) -> str:
        if self._use_nvenc is None:
            if self._config.use_nvenc_auto:
                self._use_nvenc = _detect_nvenc(
                    self._config.ffmpeg_path, self._logger
                )
            else:
                self._use_nvenc = False
        return "h264_nvenc" if self._use_nvenc else "libx264"

    def render(
        self,
        audio_path: Path,
        image_results: List[ImageResult],
        output_path: Path,
        segment_durations: Optional[List[float]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Path:
        """Render the final video.

        Pipeline:
        1. For each image, generate a short video clip with Ken Burns effect,
           using the per-segment duration from ``segment_durations`` when
           provided, falling back to the global ``IMAGE_DURATION_SECONDS``.
        2. Concatenate clips with optional crossfades.
        3. Mix in narration audio and produce final MP4.

        Args:
            audio_path: Path to the narration audio file.
            image_results: Ordered list of image generation results.
            output_path: Destination path for the output MP4.
            segment_durations: Per-segment durations in seconds.  When
                provided, each clip uses its own duration from this list.
                Falls back to ``config.image_duration_seconds`` for any
                missing entry.
            progress_callback: Called with (current_step, total_steps).

        Returns:
            Path to the rendered MP4.

        Raises:
            RuntimeError: If FFmpeg fails or is cancelled.
        """
        if not image_results:
            raise RuntimeError("No images provided for rendering.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        encoder = self._encoder()
        width, height = self._config.resolution_tuple
        fps = self._config.default_fps
        fallback_duration = self._config.image_duration_seconds
        crossfade = self._config.crossfade_duration

        self._logger.info(
            "Renderer: %d image(s), encoder=%s, %dx%d @%dfps",
            len(image_results),
            encoder,
            width,
            height,
            fps,
        )

        clip_paths: list[Path] = []
        clip_durations: list[float] = []
        total = len(image_results)

        # --- Step 1: generate per-image clips ---
        for i, img_result in enumerate(image_results):
            if self._cancel.is_set():
                raise RuntimeError("Rendering cancelled by user.")

            # Use per-segment duration if available, otherwise fall back
            if segment_durations and i < len(segment_durations):
                duration = segment_durations[i]
            else:
                duration = fallback_duration

            clip_path = output_path.parent / f"_clip_{i:04d}.mp4"
            self._generate_clip(
                img_result.image_path,
                clip_path,
                duration=duration,
                width=width,
                height=height,
                fps=fps,
                encoder=encoder,
                zoom_style=self._config.zoom_style,
            )
            clip_paths.append(clip_path)
            clip_durations.append(duration)
            if progress_callback:
                progress_callback(i + 1, total)
            self._logger.info("  Clip %d/%d rendered (%.1fs).", i + 1, total, duration)

        if self._cancel.is_set():
            raise RuntimeError("Rendering cancelled by user.")

        # --- Step 2: concatenate clips ---
        concat_path = output_path.parent / "_concat.mp4"
        self._concatenate_clips(
            clip_paths, concat_path, crossfade=crossfade,
            clip_durations=clip_durations,
        )

        if self._cancel.is_set():
            raise RuntimeError("Rendering cancelled by user.")

        # --- Step 3: merge audio ---
        self._merge_audio(
            concat_path,
            audio_path,
            output_path,
            encoder=encoder,
        )

        # Cleanup temporary clips
        for p in clip_paths + [concat_path]:
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass

        self._logger.info("Render complete: %s", output_path)
        return output_path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_ffmpeg(self, args: list[str], step_label: str) -> None:
        """Run an FFmpeg command and raise RuntimeError on failure.

        Args:
            args: Full ffmpeg command as a list.
            step_label: Human-readable label for logging.
        """
        self._logger.debug("FFmpeg [%s]: %s", step_label, " ".join(args))
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            stdout, stderr = proc.communicate(timeout=600)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError(f"FFmpeg timed out during '{step_label}'.")

        if proc.returncode != 0:
            err_msg = stderr.decode(errors="replace").strip()[-500:]
            raise RuntimeError(
                f"FFmpeg failed during '{step_label}': {err_msg}"
            )

    def _generate_clip(
        self,
        image_path: Path,
        output: Path,
        duration: float,
        width: int,
        height: int,
        fps: int,
        encoder: str,
        zoom_style: str,
    ) -> None:
        """Generate a video clip from a single image with optional Ken Burns.

        Args:
            image_path: Source image.
            output: Destination clip path.
            duration: Duration in seconds.
            width, height: Output resolution.
            fps: Frames per second.
            encoder: Video encoder (libx264 or h264_nvenc).
            zoom_style: 'ken_burns' or 'static'.
        """
        total_frames = int(duration * fps)

        if zoom_style == "ken_burns":
            # Gentle zoom-in: scale image up slightly then crop
            # zoompan filter: zoom from 1.0 to 1.05 over duration
            zoom_speed = 0.0005  # zoom increment per frame
            vf = (
                f"scale={width * 2}:{height * 2},"
                f"zoompan=z='min(zoom+{zoom_speed},1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={total_frames}:s={width}x{height}:fps={fps},"
                f"scale={width}:{height}"
            )
        else:
            vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"

        crf_args = ["-crf", "18"] if encoder == "libx264" else ["-cq", "18"]
        preset = "fast" if encoder == "libx264" else "p4"
        preset_flag = "-preset"

        cmd = [
            self._config.ffmpeg_path,
            "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-vf", vf,
            "-c:v", encoder,
            preset_flag, preset,
            *crf_args,
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            str(output),
        ]
        self._run_ffmpeg(cmd, f"clip_{output.stem}")

    def _concatenate_clips(
        self,
        clip_paths: list[Path],
        output: Path,
        crossfade: float,
        clip_durations: Optional[List[float]] = None,
    ) -> None:
        """Concatenate video clips, with optional crossfade transitions.

        Args:
            clip_paths: Ordered list of clip paths.
            output: Destination path.
            crossfade: Crossfade duration in seconds (0 = no crossfade).
            clip_durations: Per-clip durations used to compute xfade offsets.
                Falls back to ``config.image_duration_seconds`` when absent.
        """
        if len(clip_paths) == 1:
            # Single clip – just copy
            import shutil
            shutil.copy(clip_paths[0], output)
            return

        # Build a concat filter for crossfade using xfade
        # We build a complex filter graph
        inputs: list[str] = []
        for p in clip_paths:
            inputs += ["-i", str(p)]

        # Build xfade chain
        n = len(clip_paths)
        filter_parts: list[str] = []
        prev = "[0:v]"

        cumulative_offset = 0.0
        for i in range(1, n):
            # Use the actual duration of the preceding clip for the offset
            if clip_durations and (i - 1) < len(clip_durations):
                clip_dur = clip_durations[i - 1]
            else:
                clip_dur = self._config.image_duration_seconds
            cumulative_offset += clip_dur - crossfade
            offset = max(cumulative_offset, 0)
            out_label = f"[xf{i}]" if i < n - 1 else "[vout]"
            filter_parts.append(
                f"{prev}[{i}:v]xfade=transition=fade:duration={crossfade}"
                f":offset={offset}{out_label}"
            )
            prev = f"[xf{i}]"

        filter_str = ";".join(filter_parts)

        cmd = [
            self._config.ffmpeg_path,
            "-y",
            *inputs,
            "-filter_complex", filter_str,
            "-map", "[vout]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            str(output),
        ]
        self._run_ffmpeg(cmd, "concatenate")

    def _merge_audio(
        self,
        video_path: Path,
        audio_path: Path,
        output: Path,
        encoder: str,
    ) -> None:
        """Merge narration audio into the video, trimming to audio length.

        Args:
            video_path: Source video (no audio).
            audio_path: Narration audio file.
            output: Final output path.
            encoder: Video encoder.
        """
        crf_args = ["-crf", "18"] if encoder == "libx264" else ["-cq", "18"]
        preset = "fast" if encoder == "libx264" else "p4"

        cmd = [
            self._config.ffmpeg_path,
            "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", encoder,
            "-preset", preset,
            *crf_args,
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output),
        ]
        self._run_ffmpeg(cmd, "merge_audio")
