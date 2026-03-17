"""Utility helpers for StoryFrame Studio."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from core.models import VisualSegment

# ---------------------------------------------------------------------------
# Segmentation density presets
# ---------------------------------------------------------------------------

#: Mapping from density name to (min_words, max_words) thresholds.
SEGMENTATION_DENSITY: dict[str, dict[str, int]] = {
    "sparse": {"min_words": 50, "max_words": 150},
    "balanced": {"min_words": 20, "max_words": 80},
    "detailed": {"min_words": 10, "max_words": 40},
}


def split_script_into_segments(
    text: str,
    min_words: int = 20,
    max_words: int = 80,
    density: str = "balanced",
) -> list[str]:
    """Split script text into narration-aligned segments.

    Strategy (in order of preference):
    1. Split on blank lines (paragraph breaks).
    2. If paragraphs are too long, further split at sentence boundaries,
       respecting punctuation pauses (., !, ?) as natural break points.
    3. If paragraphs are too short, merge adjacent ones.

    The ``density`` parameter provides convenient presets that override
    ``min_words`` / ``max_words`` when supplied:

    - ``'sparse'``   – fewer, longer segments (fewer visual changes).
    - ``'balanced'`` – default pacing.
    - ``'detailed'`` – many shorter segments (rapid visual changes).

    Args:
        text: Raw script text.
        min_words: Minimum words per segment (used for merging).
        max_words: Maximum words per segment (used for splitting).
        density: Density preset name.  When recognised, overrides
            ``min_words`` / ``max_words``.

    Returns:
        List of segment strings.
    """
    if density in SEGMENTATION_DENSITY:
        preset = SEGMENTATION_DENSITY[density]
        min_words = preset["min_words"]
        max_words = preset["max_words"]

    # Normalise line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Split into paragraphs
    raw_paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    segments: list[str] = []
    for para in raw_paragraphs:
        words = para.split()
        if len(words) <= max_words:
            segments.append(para)
        else:
            # Split long paragraphs at sentence boundaries (natural pauses)
            sentences = re.split(r"(?<=[.!?])\s+", para)
            current: list[str] = []
            current_count = 0
            for sent in sentences:
                sent_words = sent.split()
                if current_count + len(sent_words) > max_words and current:
                    segments.append(" ".join(current))
                    current = sent_words
                    current_count = len(sent_words)
                else:
                    current.extend(sent_words)
                    current_count += len(sent_words)
            if current:
                segments.append(" ".join(current))

    # Merge segments that are too short
    merged: list[str] = []
    for seg in segments:
        if merged and len(merged[-1].split()) < min_words:
            merged[-1] = merged[-1] + " " + seg
        else:
            merged.append(seg)

    return merged if merged else [text.strip()]


def create_visual_plan(
    segment_texts: list[str],
    words_per_minute: int = 130,
) -> List[VisualSegment]:
    """Build a narration-aligned visual plan from a list of segment texts.

    Each segment receives an estimated start and end time computed
    cumulatively from its word count, using a words-per-minute heuristic.

    Args:
        segment_texts: Ordered list of narration segment strings.
        words_per_minute: Average narration speed (default: 130 wpm).

    Returns:
        Ordered list of :class:`VisualSegment` objects with timing filled in.
    """
    visual_plan: List[VisualSegment] = []
    start_time = 0.0
    for i, text in enumerate(segment_texts):
        duration = estimate_duration(text, words_per_minute)
        end_time = start_time + duration
        seg = VisualSegment(
            index=i,
            text=text,
            estimated_start=start_time,
            estimated_end=end_time,
            estimated_duration=duration,
        )
        visual_plan.append(seg)
        start_time = end_time
    return visual_plan


def format_time(seconds: float) -> str:
    """Format a time in seconds as MM:SS for display in log messages.

    Args:
        seconds: Time in seconds.

    Returns:
        String formatted as ``MM:SS``.
    """
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def estimate_duration(text: str, words_per_minute: int = 130) -> float:
    """Estimate narration duration from word count.

    Args:
        text: Segment text.
        words_per_minute: Average narration speed (default: 130 wpm).

    Returns:
        Estimated duration in seconds.
    """
    word_count = len(text.split())
    return max(1.0, (word_count / words_per_minute) * 60.0)


def build_image_prompt(
    segment_text: str,
    image_instructions: str,
    index: int,
    anchor_text: str = "",
    shot_rules_text: str = "",
    negative_text: str = "",
) -> str:
    """Combine segment text and optional style files into a structured image prompt.

    Prompt sections are assembled in a deterministic order so that each block
    receives appropriate weight from the image model:

    1. **GLOBAL STYLE RULES** – mandatory visual/thematic directives from
       ``images.txt``.  Placed first and flagged as strict rules.
    2. **CONSISTENCY ANCHORS** – cross-scene continuity hints from
       ``anchors.txt`` (optional).
    3. **SHOT RULES** – camera composition guidance from ``shot_rules.txt``
       (optional).
    4. **NEGATIVE CONSTRAINTS** – hard exclusions from ``negative.txt``
       (optional).
    5. **CURRENT NARRATION SEGMENT** – the narration text that grounds the
       prompt in the actual story moment.
    6. **TASK** – an explicit output instruction that summarises the rules.

    Any optional block whose text is empty or whitespace-only is silently
    omitted so that missing files do not leave empty sections in the prompt.

    Args:
        segment_text: Text of the narration segment for this scene.
        image_instructions: Content of ``prompts/images/images.txt``.
        index: Segment index (zero-based).
        anchor_text: Optional content of ``anchors.txt``.
        shot_rules_text: Optional content of ``shot_rules.txt``.
        negative_text: Optional content of ``negative.txt``.

    Returns:
        A formatted image generation prompt string.
    """
    instructions = image_instructions.strip()
    scene = segment_text.strip().replace("\n", " ")

    parts: list[str] = [
        "Follow these visual rules strictly.",
        f"GLOBAL STYLE RULES:\n{instructions}",
    ]

    if anchor_text and anchor_text.strip():
        parts.append(f"CONSISTENCY ANCHORS:\n{anchor_text.strip()}")

    if shot_rules_text and shot_rules_text.strip():
        parts.append(f"SHOT RULES:\n{shot_rules_text.strip()}")

    if negative_text and negative_text.strip():
        parts.append(f"NEGATIVE CONSTRAINTS:\n{negative_text.strip()}")

    parts.append(f"CURRENT NARRATION SEGMENT:\nScene {index + 1}: {scene}")

    parts.append(
        "TASK:\n"
        "Generate one detailed image prompt describing a single cinematic scene "
        "that faithfully represents the narration segment above. "
        "Follow all rules and constraints listed above. "
        "Do not explain anything. Output the image prompt only."
    )

    return "\n\n".join(parts)


def append_silence(
    ffmpeg_path: str,
    audio_path: Path,
    silence_seconds: float,
    output_path: Path,
) -> bool:
    """Append a period of silence to an audio file using FFmpeg.

    Uses the ``apad`` filter to extend the audio with silence for the
    requested duration, effectively inserting silence at the end.

    Args:
        ffmpeg_path: Path or name of the ffmpeg executable.
        audio_path: Source audio file.
        silence_seconds: Duration of silence to append in seconds.
        output_path: Destination audio file path.

    Returns:
        True on success, False on error.
    """
    if silence_seconds <= 0:
        shutil.copy(audio_path, output_path)
        return True

    try:
        result = subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-i", str(audio_path),
                "-af", f"apad=pad_dur={silence_seconds:.3f}",
                "-c:a", "libmp3lame",
                "-q:a", "2",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode == 0
    except Exception:
        return False


def ensure_dir(path: Path) -> Path:
    """Create directory (and parents) if it does not exist.

    Args:
        path: Directory path to create.

    Returns:
        The same path.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def check_ffmpeg(ffmpeg_path: str = "ffmpeg") -> bool:
    """Return True if FFmpeg is available on PATH.

    Args:
        ffmpeg_path: Path or name of the ffmpeg executable.
    """
    try:
        result = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_audio_duration(
    ffprobe_path: str, audio_path: Path
) -> Optional[float]:
    """Use ffprobe to get the duration of an audio file in seconds.

    Args:
        ffprobe_path: Path or name of the ffprobe executable.
        audio_path: Path to the audio file.

    Returns:
        Duration in seconds, or None on error.
    """
    try:
        result = subprocess.run(
            [
                ffprobe_path,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return None


def prepend_silence(
    ffmpeg_path: str,
    audio_path: Path,
    silence_seconds: float,
    output_path: Path,
) -> bool:
    """Prepend a period of silence to an audio file using FFmpeg.

    Uses the ``adelay`` filter to shift all audio channels by the requested
    number of milliseconds, effectively inserting silence at the start.

    Args:
        ffmpeg_path: Path or name of the ffmpeg executable.
        audio_path: Source audio file.
        silence_seconds: Duration of silence to prepend in seconds.
        output_path: Destination audio file path.

    Returns:
        True on success, False on error.
    """
    if silence_seconds <= 0:
        shutil.copy(audio_path, output_path)
        return True

    delay_ms = int(silence_seconds * 1000)
    try:
        result = subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-i", str(audio_path),
                "-af", f"adelay=delays={delay_ms}:all=1",
                "-c:a", "libmp3lame",
                "-q:a", "2",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode == 0
    except Exception:
        return False
