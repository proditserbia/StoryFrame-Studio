"""Narration text pre-processing for StoryFrame Studio.

Prepares script text for TTS synthesis with horror-style pacing:
  - Preserves original wording completely.
  - Inserts subtle pause markers after strong punctuation to create
    a slower, more suspenseful feel without sounding robotic.
"""

from __future__ import annotations

import re

# SSML-style pause inserted after sentence-ending punctuation.
# Most ElevenLabs models interpret a literal ellipsis or em-dash as a brief
# pause without requiring SSML tags, so we use a short pause string that
# blends naturally into narration.
_SENTENCE_PAUSE = "  "  # double space — treated as a micro-pause by ElevenLabs

# Punctuation marks that end a full thought and benefit from a longer pause.
_STRONG_END = re.compile(r'([.!?…]+)(\s+)')
# Em-dash or double-dash — used for dramatic breaks mid-sentence.
_EM_DASH = re.compile(r'(\s*—\s*|\s*--\s*)')


def prepare_horror_narration(text: str) -> str:
    """Add subtle pacing cues to *text* for horror-style TTS narration.

    Behaviour:
    - Replaces single spaces after sentence-ending punctuation with a double
      space so the TTS engine produces a slightly longer inter-sentence pause.
    - Normalises em-dashes to a spaced version so they read as natural beats.
    - Does **not** rewrite or alter any words.

    Args:
        text: Raw script text to prepare.

    Returns:
        Text with light pacing adjustments applied.
    """
    if not text or not text.strip():
        return text

    # Normalise em-dashes / double-dashes to a padded version
    result = _EM_DASH.sub(" — ", text)

    # Insert an extra space after sentence-ending punctuation so that ElevenLabs
    # naturally produces a slightly longer pause between sentences.
    # Normalise whitespace after sentence-ending punctuation.
    # For TTS synthesis, newlines carry no semantic meaning, so all
    # inter-sentence whitespace is normalised to a double-space pause marker.
    result = _STRONG_END.sub(lambda m: m.group(1) + _SENTENCE_PAUSE, result)

    # Collapse any accidental runs of more than two spaces (safety pass)
    result = re.sub(r' {3,}', '  ', result)

    return result
