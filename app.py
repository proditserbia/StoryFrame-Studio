"""StoryFrame Studio – application entry point.

Usage::

    python app.py

Loads the application config from .env, then launches the Tkinter UI.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import messagebox

# Ensure the project root is on sys.path regardless of how the app is launched
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.config import Config
from ui.main_window import MainWindow


def main() -> None:
    """Application entry point."""
    # Load config (does not validate provider keys yet – that happens at run-time)
    config = Config()

    root = tk.Tk()

    # Apply a modern theme if available
    style = tk.ttk.Style(root)
    available = style.theme_names()
    for preferred in ("vista", "aqua", "clam", "alt"):
        if preferred in available:
            style.theme_use(preferred)
            break

    window = MainWindow(root, config)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
