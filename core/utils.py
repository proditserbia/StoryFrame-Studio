"""Utility helpers for StoryFrame Studio."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from core.models import VisualSegment

# ---------------------------------------------------------------------------
# Scene focus classification — visual intelligence layer
# ---------------------------------------------------------------------------

#: Words that indicate the scene is primarily about a physical location or
#: architectural space.  Matched as whole tokens (case-insensitive).
_ENVIRONMENT_KEYWORDS: frozenset[str] = frozenset(
    {
        "house", "room", "hallway", "hall", "attic", "basement", "kitchen",
        "stairs", "staircase", "ceiling", "wall", "floor", "corridor",
        "street", "road", "path", "alley", "bridge", "tunnel", "cave",
        "forest", "woods", "field", "yard", "garden", "garage", "porch",
        "lobby", "entrance", "exit", "office", "bathroom", "bedroom",
        "warehouse", "cabin", "rooftop", "parking", "church", "hospital",
        "school", "apartment", "building", "structure", "landscape",
        "exterior", "interior", "outside", "inside", "upstairs", "downstairs",
    }
)

#: Words that indicate a specific object or detail is the primary visual
#: subject.  Objects are smaller focal elements within the environment.
#: Note: architectural elements such as door, window, stairs are intentionally
#: absent here — they belong to the environment category.
_OBJECT_KEYWORDS: frozenset[str] = frozenset(
    {
        "mug", "cup", "glass", "bottle", "jar", "lamp", "bulb", "light",
        "floorboard", "board", "nail", "hook", "string", "rope", "wire",
        "cable", "clip", "counter", "shelf", "drawer", "handle",
        "knob", "switch", "lock", "key", "box", "bag", "case", "frame",
        "mirror", "photo", "photograph", "note", "letter", "sign", "book",
        "phone", "screen", "pipe", "hatch", "chair",
        "table", "bed", "blanket", "curtain", "rug", "stain", "mark",
        "scratch", "crack", "splinter", "shadow", "reflection", "smear",
    }
)

#: Words that indicate the narrator or a character is experiencing an
#: emotional or physical reaction.  These are *strong* reaction signals
#: (physical or emotional state) that should shift focus toward the person.
_REACTION_KEYWORDS: frozenset[str] = frozenset(
    {
        "fear", "terror", "afraid", "scared", "panic", "dread", "horror",
        "disturbed", "shocked", "trembling", "shaking", "frozen", "paralyzed",
        "paralysed", "breath", "breathing", "breathe", "heartbeat", "heart",
        "pulse", "nausea", "sick", "sweat", "pale", "shiver",
        "whispered", "screamed", "yelled", "cried", "sobbed", "gasped",
        "choked", "froze", "hesitated", "flinched", "startled", "recoiled",
        "trembled", "pounding", "racing", "listening", "waking",
        "woke", "awake", "awoken",
    }
)

#: Set of all valid scene_focus values.  All three scene-intelligence
#: dictionaries below are keyed by exactly these values; keeping a single
#: source of truth prevents silent key mismatches.
_VALID_SCENE_FOCUS: frozenset[str] = frozenset(
    {"environment", "object_detail", "person_in_environment", "reaction_shot"}
)

#: Mapping from scene_focus value to shot_type.
_SHOT_TYPE_MAP: dict[str, str] = {
    "environment": "wide",
    "object_detail": "detail",
    "person_in_environment": "medium",
    "reaction_shot": "medium",
}

#: Composition directives indexed by scene_focus.
_COMPOSITION_DIRECTIVES: dict[str, str] = {
    "environment": (
        "Show the full environment as the primary subject. "
        "Wide shot establishing the location — architecture, space, and "
        "atmosphere fill the frame. Any person present must be a small "
        "figure at mid-distance or further within that environment."
    ),
    "object_detail": (
        "Frame the specific object as the clear focal point while keeping it "
        "anchored within its surrounding environment. "
        "The environment remains visible in the background. "
        "No human figure should dominate the frame."
    ),
    "person_in_environment": (
        "Show the person as a mid-distance figure within their surroundings. "
        "The environment occupies the majority of the frame. "
        "Convey emotion through body language and posture, not facial close-up."
    ),
    "reaction_shot": (
        "Medium shot capturing a character's reaction through body language "
        "and partial framing. Keep the face partially visible at most — "
        "do not fill the frame with the face. "
        "The surrounding environment should still be partially visible to "
        "preserve spatial context."
    ),
}

#: Anti-portrait rules per scene_focus.  These are always injected to prevent
#: the image model from defaulting to portrait compositions.
_ANTI_PORTRAIT_RULES: dict[str, str] = {
    "environment": (
        "DO NOT generate a close-up portrait or headshot. "
        "DO NOT place a single person as the dominant centred subject. "
        "DO NOT fill the frame with a human face. "
        "The image MUST show the environment or location as the primary subject. "
        "Environment-first composition is mandatory."
    ),
    "object_detail": (
        "DO NOT generate a close-up portrait or headshot. "
        "DO NOT fill the frame with a human face. "
        "The image MUST be centred on the described object within its environment. "
        "No person should be the primary subject."
    ),
    "person_in_environment": (
        "DO NOT generate a tight headshot or face close-up. "
        "The person must remain a mid-distance or smaller figure. "
        "The environment must occupy the majority of the frame. "
        "Show the person from behind, in silhouette, or partially obscured if possible."
    ),
    "reaction_shot": (
        "DO NOT fill the entire frame with a face. "
        "The face or upper body may be partially visible but must not become "
        "a standard portrait-style headshot. "
        "Partial framing, shadow, or environmental context must be present."
    ),
}


def classify_scene_focus(text: str) -> str:
    """Classify the visual focus of a narration segment using keyword heuristics.

    Returns one of four focus values that describe what the generated image
    should primarily depict:

    - ``'environment'`` – the location or space is the primary subject.
    - ``'object_detail'`` – a specific object within the environment is the
      focal point.
    - ``'person_in_environment'`` – a person is present but subordinate to
      their environment.
    - ``'reaction_shot'`` – a character's emotional or physical reaction is
      the main subject.

    The classifier is heuristic-based (keyword counting) and deliberately
    generic — it is not hardcoded to any specific content niche.

    **Tokenization note**: the text is lowercased and split into runs of
    ASCII letters only (``[a-z]+``).  This means contractions and
    hyphenated words are split at the punctuation boundary (e.g.
    ``"don't"`` → ``{"don", "t"}``).  For keyword-counting purposes this
    is sufficient and avoids over-matching composite terms.

    **Tie-breaking**: when object and environment hit counts are equal and
    both exceed reaction hits, ``'object_detail'`` wins because the
    condition uses ``>=`` for the environment comparison, biasing toward the
    more specific focus type.  When all three counts are equal and non-zero,
    the reaction-with-environment branch wins (``'person_in_environment'``).

    Default fallback when no keywords match: ``'environment'``.

    Args:
        text: The narration segment text to classify.

    Returns:
        One of ``'environment'``, ``'object_detail'``,
        ``'person_in_environment'``, or ``'reaction_shot'``.
    """
    tokens = set(re.findall(r"[a-z]+", text.lower()))

    env_hits = len(tokens & _ENVIRONMENT_KEYWORDS)
    obj_hits = len(tokens & _OBJECT_KEYWORDS)
    reaction_hits = len(tokens & _REACTION_KEYWORDS)

    # Object-dominant: specific object is the focal element.
    # Uses >= for environment comparison so ties favour the more specific focus.
    if obj_hits > 0 and obj_hits >= env_hits and obj_hits > reaction_hits:
        return "object_detail"

    # Reaction with environmental context → person within environment
    if reaction_hits > 0 and env_hits > 0:
        return "person_in_environment"

    # Pure reaction / emotion with no significant environment cues
    if reaction_hits > 0 and env_hits == 0:
        return "reaction_shot"

    # Environment cues present (including the default fallback)
    return "environment"


def get_shot_type(scene_focus: str) -> str:
    """Return the shot type that corresponds to a given scene_focus value.

    Mapping:

    - ``'environment'`` → ``'wide'``
    - ``'object_detail'`` → ``'detail'``
    - ``'person_in_environment'`` → ``'medium'``
    - ``'reaction_shot'`` → ``'medium'``

    Close shots are intentionally excluded from the automatic mapping.
    They are controlled, rare, and should only appear when explicitly
    warranted by the narration — never as the default.

    Args:
        scene_focus: One of the four scene focus values.

    Returns:
        A shot type string: ``'wide'``, ``'detail'``, ``'medium'``, or
        ``'close'``.
    """
    return _SHOT_TYPE_MAP.get(scene_focus, "wide")

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
    scene_focus: str = "environment",
    shot_type: str = "wide",
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
    5. **SCENE FOCUS / SHOT TYPE** – classified visual focus and shot type
       derived from the narration content.
    6. **COMPOSITION DIRECTIVE** – focus-specific framing instruction.
    7. **ANTI-PORTRAIT RULES** – always-on constraint that prevents the model
       from defaulting to portrait-style images, adapted per focus type.
    8. **CURRENT NARRATION SEGMENT** – the narration text that grounds the
       prompt in the actual story moment.
    9. **TASK** – an explicit output instruction that summarises the rules.

    Any optional block whose text is empty or whitespace-only is silently
    omitted so that missing files do not leave empty sections in the prompt.

    The ``scene_focus`` and ``shot_type`` values are injected regardless of
    what the external text files contain, ensuring stable anti-portrait
    behaviour even when prompt files are absent or minimal.

    Args:
        segment_text: Text of the narration segment for this scene.
        image_instructions: Content of ``prompts/images/images.txt``.
        index: Segment index (zero-based).
        anchor_text: Optional content of ``anchors.txt``.
        shot_rules_text: Optional content of ``shot_rules.txt``.
        negative_text: Optional content of ``negative.txt``.
        scene_focus: Classified visual focus for this segment
            (``'environment'``, ``'object_detail'``,
            ``'person_in_environment'``, or ``'reaction_shot'``).
        shot_type: Derived shot type (``'wide'``, ``'detail'``,
            ``'medium'``, or ``'close'``).

    Returns:
        A formatted image generation prompt string.
    """
    # Normalise inputs
    instructions = image_instructions.strip()
    scene = segment_text.strip().replace("\n", " ")
    # Use _VALID_SCENE_FOCUS as the single source of truth for valid values so
    # that a stale or unknown scene_focus safely falls back to 'environment'.
    safe_focus = scene_focus if scene_focus in _VALID_SCENE_FOCUS else "environment"

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

    # Scene intelligence — always injected, independent of external files
    parts.append(
        f"SCENE FOCUS: {safe_focus}\n"
        f"SHOT TYPE: {shot_type}"
    )

    parts.append(
        f"COMPOSITION DIRECTIVE:\n{_COMPOSITION_DIRECTIVES[safe_focus]}"
    )

    parts.append(
        f"ANTI-PORTRAIT RULES (ALWAYS ENFORCED):\n"
        f"{_ANTI_PORTRAIT_RULES[safe_focus]}"
    )

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
