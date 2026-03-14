"""Utility helpers for StoryFrame Studio."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional


def split_script_into_segments(
    text: str, min_words: int = 20, max_words: int = 80
) -> list[str]:
    """Split script text into narrative segments.

    Strategy (in order of preference):
    1. Split on blank lines (paragraph breaks).
    2. If paragraphs are too long, further split at sentence boundaries.
    3. If paragraphs are too short, merge adjacent ones.

    Args:
        text: Raw script text.
        min_words: Minimum words per segment (for merging).
        max_words: Maximum words per segment (for splitting).

    Returns:
        List of segment strings.
    """
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
            # Split long paragraphs at sentence boundaries
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
    segment_text: str, image_instructions: str, index: int
) -> str:
    """Combine segment text and image instructions into an image prompt.

    Args:
        segment_text: Text of the script segment.
        image_instructions: Content of prompts/images/images.txt.
        index: Segment index (used for uniqueness hint).

    Returns:
        A formatted image generation prompt string.
    """
    instructions = image_instructions.strip()
    # Summarise the segment text into a visual scene description
    # In a full version this could call an LLM rewriter module.
    scene = segment_text.strip().replace("\n", " ")
    prompt = (
        f"Scene {index + 1}: {scene}\n\n"
        f"Visual style and requirements:\n{instructions}"
    )
    return prompt


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
