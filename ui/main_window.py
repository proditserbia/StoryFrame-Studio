"""Main Tkinter window for StoryFrame Studio.

Provides:
- Project folder / script / image-instructions selectors
- TTS provider selector
- Rendering mode indicator
- Start / Cancel controls
- Live-streaming log panel
- Progress bar
- Status label
- Output path display with "Open folder" button
"""

from __future__ import annotations

import os
import platform
import queue
import subprocess
from pathlib import Path
from tkinter import (
    END,
    StringVar,
    Text,
    Tk,
    filedialog,
    messagebox,
    ttk,
)
import tkinter as tk

from core.config import Config
from core.models import RunMetadata
from ui.worker import PipelineWorker, WorkerMessage

# Resolve project root (two levels above this file)
_ROOT = Path(__file__).resolve().parent.parent

_TTS_PROVIDERS = ["elevenlabs", "deepgram"]
_RENDERING_MODES = ["Standard (libx264)", "Hardware NVENC (auto-detect)"]
_IMAGE_PRESETS = {
    "Short (4s)": 4.0,
    "Standard (8s)": 8.0,
    "Long (12s)": 12.0,
}
_DENSITY_OPTIONS = {
    "Sparse (fewer scenes)": "sparse",
    "Balanced": "balanced",
    "Detailed (more scenes)": "detailed",
}


class MainWindow:
    """Tkinter application main window.

    Args:
        root: Tk root widget.
        config: Application config loaded from .env.
    """

    def __init__(self, root: Tk, config: Config) -> None:
        self._root = root
        self._config = config
        self._queue: "queue.Queue[WorkerMessage]" = queue.Queue()
        self._worker = PipelineWorker(config, self._queue)
        self._output_path: Path | None = None

        root.title("StoryFrame Studio")
        root.resizable(True, True)
        root.minsize(720, 600)

        self._build_ui()
        self._poll_queue()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create all widgets."""
        pad = {"padx": 8, "pady": 4}

        # ── Top controls frame ─────────────────────────────────────────
        ctrl = ttk.LabelFrame(self._root, text="Project Setup", padding=8)
        ctrl.pack(fill=tk.X, padx=12, pady=(12, 4))
        ctrl.columnconfigure(1, weight=1)

        # Script file
        ttk.Label(ctrl, text="Script file:").grid(row=0, column=0, sticky=tk.W, **pad)
        self._script_var = StringVar(
            value=str(_ROOT / "prompts" / "scripts" / "sample_story.txt")
        )
        ttk.Entry(ctrl, textvariable=self._script_var).grid(
            row=0, column=1, sticky=tk.EW, **pad
        )
        ttk.Button(ctrl, text="Browse…", command=self._browse_script).grid(
            row=0, column=2, **pad
        )

        # Image instructions file
        ttk.Label(ctrl, text="Image instructions:").grid(
            row=1, column=0, sticky=tk.W, **pad
        )
        self._images_var = StringVar(
            value=str(_ROOT / "prompts" / "images" / "images.txt")
        )
        ttk.Entry(ctrl, textvariable=self._images_var).grid(
            row=1, column=1, sticky=tk.EW, **pad
        )
        ttk.Button(ctrl, text="Browse…", command=self._browse_images).grid(
            row=1, column=2, **pad
        )

        # TTS provider
        ttk.Label(ctrl, text="TTS provider:").grid(
            row=2, column=0, sticky=tk.W, **pad
        )
        self._tts_var = StringVar(value=self._config.tts_provider)
        ttk.Combobox(
            ctrl,
            textvariable=self._tts_var,
            values=_TTS_PROVIDERS,
            state="readonly",
            width=20,
        ).grid(row=2, column=1, sticky=tk.W, **pad)

        # Image duration preset
        ttk.Label(ctrl, text="Image duration:").grid(
            row=3, column=0, sticky=tk.W, **pad
        )
        self._preset_var = StringVar(value="Standard (8s)")
        ttk.Combobox(
            ctrl,
            textvariable=self._preset_var,
            values=list(_IMAGE_PRESETS.keys()),
            state="readonly",
            width=20,
        ).grid(row=3, column=1, sticky=tk.W, **pad)

        # Segmentation density
        ttk.Label(ctrl, text="Segmentation:").grid(
            row=4, column=0, sticky=tk.W, **pad
        )
        self._density_var = StringVar(value="Balanced")
        ttk.Combobox(
            ctrl,
            textvariable=self._density_var,
            values=list(_DENSITY_OPTIONS.keys()),
            state="readonly",
            width=24,
        ).grid(row=4, column=1, sticky=tk.W, **pad)

        # Leading silence
        ttk.Label(ctrl, text="Leading silence (s):").grid(
            row=5, column=0, sticky=tk.W, **pad
        )
        self._leading_silence_var = StringVar(
            value=str(self._config.tts_leading_silence)
        )
        ttk.Spinbox(
            ctrl,
            textvariable=self._leading_silence_var,
            from_=0.0,
            to=10.0,
            increment=0.5,
            width=8,
            format="%.1f",
        ).grid(row=5, column=1, sticky=tk.W, **pad)

        # Trailing silence
        ttk.Label(ctrl, text="Trailing silence (s):").grid(
            row=6, column=0, sticky=tk.W, **pad
        )
        self._trailing_silence_var = StringVar(
            value=str(self._config.tts_trailing_silence)
        )
        ttk.Spinbox(
            ctrl,
            textvariable=self._trailing_silence_var,
            from_=0.0,
            to=10.0,
            increment=0.5,
            width=8,
            format="%.1f",
        ).grid(row=6, column=1, sticky=tk.W, **pad)

        # ── Action buttons ─────────────────────────────────────────────
        btn_frame = ttk.Frame(self._root)
        btn_frame.pack(fill=tk.X, padx=12, pady=4)

        self._start_btn = ttk.Button(
            btn_frame, text="▶  Start", command=self._on_start, style="Accent.TButton"
        )
        self._start_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._cancel_btn = ttk.Button(
            btn_frame, text="✖  Cancel", command=self._on_cancel, state=tk.DISABLED
        )
        self._cancel_btn.pack(side=tk.LEFT)

        # ── Progress bar ───────────────────────────────────────────────
        self._progress_var = tk.DoubleVar(value=0.0)
        self._progress = ttk.Progressbar(
            self._root,
            variable=self._progress_var,
            maximum=100,
            mode="determinate",
        )
        self._progress.pack(fill=tk.X, padx=12, pady=4)

        # ── Status label ───────────────────────────────────────────────
        self._status_var = StringVar(value="Ready")
        ttk.Label(
            self._root,
            textvariable=self._status_var,
            foreground="#555",
            anchor=tk.W,
        ).pack(fill=tk.X, padx=12)

        # ── Log panel ──────────────────────────────────────────────────
        log_frame = ttk.LabelFrame(self._root, text="Log Output", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL)
        self._log_text = Text(
            log_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            height=18,
            background="#1e1e1e",
            foreground="#d4d4d4",
            insertbackground="#d4d4d4",
            font=("Consolas", 9) if platform.system() == "Windows" else ("Monospace", 9),
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=self._log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._log_text.pack(fill=tk.BOTH, expand=True)

        # ── Output path display ────────────────────────────────────────
        out_frame = ttk.Frame(self._root)
        out_frame.pack(fill=tk.X, padx=12, pady=(0, 12))

        ttk.Label(out_frame, text="Output:").pack(side=tk.LEFT)
        self._output_var = StringVar(value="—")
        ttk.Label(
            out_frame,
            textvariable=self._output_var,
            foreground="#007acc",
            anchor=tk.W,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        self._open_btn = ttk.Button(
            out_frame,
            text="Open folder",
            command=self._open_output_folder,
            state=tk.DISABLED,
        )
        self._open_btn.pack(side=tk.RIGHT)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _browse_script(self) -> None:
        path = filedialog.askopenfilename(
            title="Select script file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialdir=str(_ROOT / "prompts" / "scripts"),
        )
        if path:
            self._script_var.set(path)

    def _browse_images(self) -> None:
        path = filedialog.askopenfilename(
            title="Select image instructions file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialdir=str(_ROOT / "prompts" / "images"),
        )
        if path:
            self._images_var.set(path)

    def _on_start(self) -> None:
        """Validate inputs then kick off the pipeline worker."""
        script = Path(self._script_var.get().strip())
        images = Path(self._images_var.get().strip())

        if not script.is_file():
            messagebox.showerror("File not found", f"Script file not found:\n{script}")
            return
        if not images.is_file():
            messagebox.showerror(
                "File not found",
                f"Image instructions file not found:\n{images}",
            )
            return

        # Apply image duration preset to config
        preset_label = self._preset_var.get()
        self._config.image_duration_seconds = _IMAGE_PRESETS.get(
            preset_label, self._config.image_duration_seconds
        )

        # Resolve segmentation density
        density_label = self._density_var.get()
        density = _DENSITY_OPTIONS.get(density_label, "balanced")

        # Apply silence settings to config
        try:
            self._config.tts_leading_silence = max(
                0.0, float(self._leading_silence_var.get())
            )
        except ValueError:
            self._config.tts_leading_silence = 0.0
            messagebox.showwarning(
                "Invalid value",
                "Leading silence must be a number. Defaulting to 0.0 s.",
            )
        try:
            self._config.tts_trailing_silence = max(
                0.0, float(self._trailing_silence_var.get())
            )
        except ValueError:
            self._config.tts_trailing_silence = 0.0
            messagebox.showwarning(
                "Invalid value",
                "Trailing silence must be a number. Defaulting to 0.0 s.",
            )

        # Disable Start, enable Cancel
        self._start_btn.config(state=tk.DISABLED)
        self._cancel_btn.config(state=tk.NORMAL)
        self._open_btn.config(state=tk.DISABLED)
        self._output_var.set("Processing…")
        self._progress_var.set(0)
        self._status_var.set("Starting…")
        self._clear_log()

        self._worker.start(
            script_path=script,
            image_instructions_path=images,
            tts_provider_name=self._tts_var.get(),
            segmentation_density=density,
        )

    def _on_cancel(self) -> None:
        """Ask the worker to stop."""
        self._worker.cancel()
        self._status_var.set("Cancelling…")
        self._cancel_btn.config(state=tk.DISABLED)

    def _open_output_folder(self) -> None:
        """Open the output folder in the OS file explorer."""
        if self._output_path is None:
            return
        folder = (
            self._output_path.parent
            if self._output_path.is_file()
            else self._output_path
        )
        system = platform.system()
        try:
            if system == "Windows":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif system == "Darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            messagebox.showwarning("Cannot open folder", str(exc))

    # ------------------------------------------------------------------
    # Queue polling (runs on UI thread via after())
    # ------------------------------------------------------------------

    def _poll_queue(self) -> None:
        """Drain messages from the worker queue and update the UI."""
        try:
            while True:
                msg: WorkerMessage = self._queue.get_nowait()
                if msg.kind == "log":
                    self._append_log(str(msg.payload))
                elif msg.kind == "progress":
                    label, pct = msg.payload  # type: ignore[misc]
                    self._progress_var.set(float(pct))
                    self._status_var.set(label)
                elif msg.kind == "done":
                    self._on_done(msg.payload)  # type: ignore[arg-type]
                elif msg.kind == "error":
                    self._on_error(str(msg.payload))
        except queue.Empty:
            pass
        finally:
            self._root.after(100, self._poll_queue)

    # ------------------------------------------------------------------
    # UI state helpers
    # ------------------------------------------------------------------

    def _on_done(self, metadata: "RunMetadata") -> None:
        """Handle successful pipeline completion."""
        self._start_btn.config(state=tk.NORMAL)
        self._cancel_btn.config(state=tk.DISABLED)
        self._status_var.set("Done ✓")
        self._progress_var.set(100)

        if metadata and metadata.output_video:
            self._output_path = Path(metadata.output_video)
            self._output_var.set(str(self._output_path))
            self._open_btn.config(state=tk.NORMAL)
        else:
            self._output_var.set("Completed (no video path returned)")

        messagebox.showinfo(
            "Complete",
            "Pipeline finished successfully!\n\nOutput: "
            + str(self._output_path or "—"),
        )

    def _on_error(self, message: str) -> None:
        """Handle pipeline error or cancellation."""
        self._start_btn.config(state=tk.NORMAL)
        self._cancel_btn.config(state=tk.DISABLED)

        if self._worker.is_cancelled() or "Cancelled" in message:
            self._status_var.set("Cancelled")
            self._progress_var.set(0)
        else:
            self._status_var.set("Error ✗")
            messagebox.showerror("Pipeline Error", message)

    def _append_log(self, text: str) -> None:
        """Append a line to the log panel and auto-scroll."""
        self._log_text.config(state=tk.NORMAL)
        self._log_text.insert(END, text + "\n")
        self._log_text.see(END)
        self._log_text.config(state=tk.DISABLED)

    def _clear_log(self) -> None:
        """Clear the log panel."""
        self._log_text.config(state=tk.NORMAL)
        self._log_text.delete("1.0", END)
        self._log_text.config(state=tk.DISABLED)
