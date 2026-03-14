"""Logger for StoryFrame Studio.

Provides a unified logger that:
- writes to the console (stderr)
- writes to a log file
- streams messages to a Tkinter UI callback in real time

Usage::

    from core.logger import AppLogger
    logger = AppLogger(log_file=run_dir / "run.log", ui_callback=my_func)
    logger.info("Hello world")
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Callable, Optional


class _UIHandler(logging.Handler):
    """Logging handler that forwards records to a Tkinter-safe callback."""

    def __init__(self, callback: Callable[[str], None]) -> None:
        super().__init__()
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._callback(msg)
        except Exception:  # pragma: no cover
            self.handleError(record)


class AppLogger:
    """Application-level logger wrapping the standard logging module.

    Args:
        name: Logger name (default: ``storyframe``).
        log_file: Optional path to write log output to.
        ui_callback: Optional callable that receives formatted log strings.
                     Must be thread-safe (use ``root.after`` from Tkinter side).
    """

    def __init__(
        self,
        name: str = "storyframe",
        log_file: Optional[Path] = None,
        ui_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.DEBUG)
        # Avoid adding duplicate handlers if logger already configured
        if self._logger.handlers:
            self._logger.handlers.clear()

        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
        )

        # Console handler
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        console.setLevel(logging.DEBUG)
        self._logger.addHandler(console)

        # File handler
        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(fmt)
            fh.setLevel(logging.DEBUG)
            self._logger.addHandler(fh)

        # UI streaming handler
        if ui_callback is not None:
            ui_h = _UIHandler(ui_callback)
            ui_h.setFormatter(fmt)
            ui_h.setLevel(logging.DEBUG)
            self._logger.addHandler(ui_h)

    # Convenience wrappers ------------------------------------------------

    def debug(self, msg: str, *args: object) -> None:
        self._logger.debug(msg, *args)

    def info(self, msg: str, *args: object) -> None:
        self._logger.info(msg, *args)

    def warning(self, msg: str, *args: object) -> None:
        self._logger.warning(msg, *args)

    def error(self, msg: str, *args: object) -> None:
        self._logger.error(msg, *args)

    def exception(self, msg: str, *args: object) -> None:
        self._logger.exception(msg, *args)

    def set_ui_callback(self, callback: Callable[[str], None]) -> None:
        """Attach or replace the UI streaming handler at runtime."""
        # Remove old UI handlers
        self._logger.handlers = [
            h for h in self._logger.handlers if not isinstance(h, _UIHandler)
        ]
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
        )
        ui_h = _UIHandler(callback)
        ui_h.setFormatter(fmt)
        ui_h.setLevel(logging.DEBUG)
        self._logger.addHandler(ui_h)
