"""Replicate image generation provider for StoryFrame Studio.

Uses the Replicate REST API to generate images from text prompts.
Requires REPLICATE_API_TOKEN and REPLICATE_MODEL in .env.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

import requests

from core.config import Config
from core.image_postprocess import normalize_to_16x9_png
from core.logger import AppLogger
from core.models import ImageResult
from providers.image_base import ImageProviderBase

_API_BASE = "https://api.replicate.com/v1"
_POLL_INTERVAL = 3  # seconds between status polls
_MAX_WAIT = 300  # max seconds to wait for prediction
_TIMEOUT = 30   # HTTP request timeout


class ReplicateImageProvider(ImageProviderBase):
    """Image provider backed by the Replicate API.

    Args:
        config: Application configuration.
        logger: Logger instance.
    """

    def __init__(self, config: Config, logger: AppLogger) -> None:
        self._config = config
        self._logger = logger

    def generate(
        self,
        prompt: str,
        output_path: Path,
        segment_index: int = 0,
        negative_prompt: str = "",
    ) -> ImageResult:
        """Generate an image via Replicate and save it locally.

        Args:
            prompt: Image generation prompt.
            output_path: Destination path for the PNG image.
            segment_index: Script segment index for logging.
            negative_prompt: Optional negative prompt string.  Passed to the
                model as a separate ``negative_prompt`` input field for models
                that support it (e.g. SDXL, Stable Diffusion).  Automatically
                skipped for FLUX models, which do not accept a
                ``negative_prompt`` field and would return an API error.

        Returns:
            ImageResult with the saved image path.

        Raises:
            RuntimeError: If the API call fails or times out.
        """
        token = self._config.replicate_api_token
        model = self._config.replicate_model
        if not token or not model:
            raise RuntimeError(
                "REPLICATE_API_TOKEN and REPLICATE_MODEL must be set in .env"
            )

        # Strip version from model if included (owner/model:version)
        model_ref = model.strip()

        headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
        }

        # Hint the model towards 16:9 output where supported.
        # 1344×768 is a common generation resolution for 16:9 diffusion models;
        # the output is always upscaled to 2304×1296 by normalize_to_16x9_png.
        _image_hint: dict[str, Any] = {
            "aspect_ratio": "16:9",
            "width": 1344,
            "height": 768,
        }

        # FLUX models do not accept a ``negative_prompt`` input field and
        # would return a 422 validation error if we pass one.  All other
        # common Replicate models (SDXL, SD 1.x / 2.x, Kandinsky, etc.)
        # process it as a separate conditioning channel and benefit greatly
        # from having it populated.
        _model_lower = model_ref.lower()
        _supports_negative_prompt = (
            negative_prompt
            and "flux" not in _model_lower
        )

        # Build the shared model input dict once before choosing the endpoint.
        _input: dict[str, Any] = {"prompt": prompt, **_image_hint}
        if _supports_negative_prompt:
            _input["negative_prompt"] = negative_prompt

        # Determine endpoint – models with versions use /predictions
        if ":" in model_ref:
            owner_model, version = model_ref.split(":", 1)
            payload: dict[str, Any] = {
                "version": version,
                "input": _input,
            }
            url = f"{_API_BASE}/predictions"
        else:
            # Latest model version endpoint
            payload = {"input": _input}
            url = f"{_API_BASE}/models/{model_ref}/predictions"

        self._logger.info(
            "Replicate: submitting prediction for segment %d...", segment_index
        )
        resp = requests.post(url, json=payload, headers=headers, timeout=_TIMEOUT)
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Replicate API error {resp.status_code}: {resp.text[:300]}"
            )

        prediction = resp.json()
        pred_id = prediction.get("id", "")
        self._logger.debug("Replicate: prediction id=%s", pred_id)

        # Poll for completion
        image_url = self._poll_prediction(pred_id, headers)

        # Download raw image via requests into a temporary buffer
        label = f"Image {segment_index + 1:02d}"
        self._logger.info("Replicate: downloading raw image for %s", label)
        img_resp = requests.get(image_url, timeout=_TIMEOUT)
        if img_resp.status_code != 200:
            raise RuntimeError(
                f"Failed to download image (HTTP {img_resp.status_code})"
            )

        # Write raw bytes to a temp file so Pillow can open it reliably
        output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path = output_path.with_suffix(".raw_download")
        raw_path.write_bytes(img_resp.content)

        # Normalise to 2304×1296 RGB PNG
        normalize_to_16x9_png(
            raw_path=raw_path,
            output_path=output_path,
            label=label,
            log=lambda msg: self._logger.info("%s", msg),
        )

        # Remove the raw download temp file
        try:
            raw_path.unlink()
        except OSError:
            pass

        self._logger.info("Replicate: image saved – segment %d", segment_index)
        return ImageResult(
            image_path=output_path,
            segment_index=segment_index,
            prompt=prompt,
            provider="replicate",
            metadata={"prediction_id": pred_id, "image_url": image_url},
        )

    def _poll_prediction(
        self, prediction_id: str, headers: dict
    ) -> str:
        """Poll the Replicate API until a prediction is complete.

        Args:
            prediction_id: Replicate prediction ID.
            headers: Authorisation headers.

        Returns:
            URL of the first generated image.

        Raises:
            RuntimeError: If the prediction fails or times out.
        """
        status_url = f"{_API_BASE}/predictions/{prediction_id}"
        deadline = time.monotonic() + _MAX_WAIT

        while time.monotonic() < deadline:
            resp = requests.get(status_url, headers=headers, timeout=_TIMEOUT)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Replicate poll error {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
            status = data.get("status", "")
            self._logger.debug("Replicate: prediction status=%s", status)

            if status == "succeeded":
                output = data.get("output")
                if not output:
                    raise RuntimeError("Replicate returned no output URLs.")
                # output may be a list or a single URL
                return output[0] if isinstance(output, list) else output

            if status in ("failed", "canceled"):
                err = data.get("error", "unknown error")
                raise RuntimeError(f"Replicate prediction {status}: {err}")

            time.sleep(_POLL_INTERVAL)

        raise RuntimeError(
            f"Replicate prediction timed out after {_MAX_WAIT}s."
        )
