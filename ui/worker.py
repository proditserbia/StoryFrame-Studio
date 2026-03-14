"""Background worker for StoryFrame Studio.

Runs the pipeline in a daemon thread so the Tkinter UI stays responsive.
Communicates results back to the UI via thread-safe queue messages.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Callable, Optional

from core.config import Config
from core.logger import AppLogger
from core.models import RunMetadata
from core.pipeline import Pipeline


class WorkerMessage:
    """Message posted to the UI result queue.

    Attributes:
        kind: One of 'log', 'progress', 'done', 'error'.
        payload: Kind-specific data.
    """

    def __init__(self, kind: str, payload: object = None) -> None:
        self.kind = kind
        self.payload = payload


class PipelineWorker:
    """Manages a background pipeline thread.

    Args:
        config: Application configuration.
        result_queue: Thread-safe queue for posting messages to the UI.
    """

    def __init__(self, config: Config, result_queue: "queue.Queue[WorkerMessage]") -> None:
        self._config = config
        self._queue = result_queue
        self._cancel_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(
        self,
        script_path: Path,
        image_instructions_path: Path,
        tts_provider_name: str,
        segmentation_density: str = "balanced",
        log_file: Optional[Path] = None,
    ) -> None:
        """Start the pipeline in a background thread.

        Args:
            script_path: Path to the script text file.
            image_instructions_path: Path to the image instructions file.
            tts_provider_name: Selected TTS provider name.
            segmentation_density: Density preset ('sparse', 'balanced',
                or 'detailed').
            log_file: Optional path for persistent log file.
        """
        self._cancel_event.clear()

        self._thread = threading.Thread(
            target=self._run,
            args=(
                script_path,
                image_instructions_path,
                tts_provider_name,
                segmentation_density,
                log_file,
            ),
            daemon=True,
            name="PipelineWorker",
        )
        self._thread.start()

    def cancel(self) -> None:
        """Signal the pipeline to stop at the next safe checkpoint."""
        self._cancel_event.set()

    def is_cancelled(self) -> bool:
        """Return True if cancellation was requested."""
        return self._cancel_event.is_set()

    def is_running(self) -> bool:
        """Return True if the worker thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _run(
        self,
        script_path: Path,
        image_instructions_path: Path,
        tts_provider_name: str,
        segmentation_density: str,
        log_file: Optional[Path],
    ) -> None:
        """Thread body: sets up logger, runs pipeline, posts result."""

        def _ui_log(msg: str) -> None:
            self._queue.put(WorkerMessage("log", msg))

        def _progress(label: str, pct: int) -> None:
            self._queue.put(WorkerMessage("progress", (label, pct)))

        logger = AppLogger(
            name=f"storyframe.{id(self)}",
            log_file=log_file,
            ui_callback=_ui_log,
        )

        pipeline = Pipeline(
            config=self._config,
            logger=logger,
            cancel_event=self._cancel_event,
            progress_callback=_progress,
        )

        try:
            metadata: RunMetadata = pipeline.run(
                script_path=script_path,
                image_instructions_path=image_instructions_path,
                tts_provider_name=tts_provider_name,
                segmentation_density=segmentation_density,
            )
            if metadata.success:
                self._queue.put(WorkerMessage("done", metadata))
            else:
                self._queue.put(
                    WorkerMessage(
                        "error", metadata.error or "Pipeline failed for unknown reason."
                    )
                )
        except Exception as exc:
            self._queue.put(WorkerMessage("error", str(exc)))
