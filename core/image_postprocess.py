"""Image post-processing utilities for StoryFrame Studio.

Provides helpers for normalising raw images produced by generation providers
into the exact format required by the FFmpeg renderer:
  - RGB PNG
  - 2304 × 1296 pixels (16:9, oversize of 1920×1080 for Ken Burns headroom)
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PIL import Image

# Target dimensions for the renderer (16:9, with Ken Burns motion headroom)
TARGET_WIDTH = 2304
TARGET_HEIGHT = 1296
TARGET_RATIO = TARGET_WIDTH / TARGET_HEIGHT  # ≈ 1.7778


def normalize_to_16x9_png(
    raw_path: Path,
    output_path: Path,
    label: str = "Image",
    log: Optional[Callable[[str], None]] = None,
) -> None:
    """Normalise a raw image to a 2304×1296 RGB PNG suitable for video rendering.

    Steps performed:
    1. Open the image and convert to RGB (handles WebP, JPEG, PNG, etc.).
    2. Centre-crop to a 16:9 aspect ratio (crops the longer axis).
    3. Resize to exactly 2304×1296 using LANCZOS resampling.
    4. Save as a real PNG file.

    Args:
        raw_path: Path to the downloaded/raw image file.
        output_path: Destination path for the normalised PNG (may equal raw_path).
        label: Human-readable label used in log messages (e.g. "Image 03").
        log: Optional callable for log messages; receives a single string.
    """

    def _log(msg: str) -> None:
        if log:
            log(msg)

    with Image.open(raw_path) as img:
        img = img.convert("RGB")
        w, h = img.size
        _log(f"[{label}] Downloaded raw image {w}x{h}")

        img = _center_crop_to_ratio(img, TARGET_RATIO)
        cw, ch = img.size
        if (cw, ch) != (w, h):
            _log(f"[{label}] Cropped to 16:9 ({cw}x{ch})")

        if (cw, ch) != (TARGET_WIDTH, TARGET_HEIGHT):
            img = img.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.LANCZOS)
            _log(f"[{label}] Resized to {TARGET_WIDTH}x{TARGET_HEIGHT}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(output_path), format="PNG")
        _log(f"[{label}] Saved as PNG")


def _center_crop_to_ratio(img: Image.Image, target_ratio: float) -> Image.Image:
    """Centre-crop *img* to *target_ratio* (width / height).

    If the image is already at the target ratio (within 0.1 % tolerance) it is
    returned unchanged.  Otherwise the longer axis is cropped symmetrically.

    Args:
        img: Source PIL image.
        target_ratio: Desired width-to-height ratio.

    Returns:
        Cropped PIL image.
    """
    w, h = img.size
    current_ratio = w / h

    # Allow a small tolerance to avoid unnecessary tiny crops
    if abs(current_ratio - target_ratio) < 0.001:
        return img

    if current_ratio > target_ratio:
        # Image is too wide — crop left and right
        new_w = int(round(h * target_ratio))
        left = (w - new_w) // 2
        return img.crop((left, 0, left + new_w, h))
    else:
        # Image is too tall — crop top and bottom
        new_h = int(round(w / target_ratio))
        top = (h - new_h) // 2
        return img.crop((0, top, w, top + new_h))
