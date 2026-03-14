# StoryFrame Studio

A production-ready Python desktop application for content creators that generates AI-narrated videos from scripts. Built with Tkinter, FFmpeg, ElevenLabs/Deepgram for narration, and Replicate for image generation.

---

## Table of Contents

- [Overview](#overview)
- [Folder Structure](#folder-structure)
- [Setup](#setup)
- [.env Configuration](#env-configuration)
- [FFmpeg Installation](#ffmpeg-installation)
- [Running the App](#running-the-app)
- [Placing Scripts](#placing-scripts)
- [Editing Image Instructions](#editing-image-instructions)
- [Switching TTS Providers](#switching-tts-providers)
- [How Rendering Works](#how-rendering-works)
- [Future Extensions](#future-extensions)

---

## Overview

StoryFrame Studio takes a plain-text script, generates spoken narration via a TTS API, creates scene images via an AI image API, and renders a final 1080p MP4 video using FFmpeg — all from a clean desktop UI.

**Core pipeline:**
```
Script text → Segment splitting → TTS narration → Image prompts → Image generation → FFmpeg render → MP4
```

**Tech stack:**
- Python 3.11+
- Tkinter (desktop UI, no web server required)
- FFmpeg (rendering, Ken Burns zoom, crossfades)
- ElevenLabs or Deepgram (text-to-speech)
- Replicate (AI image generation)
- python-dotenv (config management)

---

## Folder Structure

```
StoryFrame-Studio/
├── app.py                        # Entry point
├── requirements.txt
├── .env.example                  # Copy to .env and fill in keys
├── README.md
│
├── core/
│   ├── config.py                 # .env loader + validation
│   ├── logger.py                 # Console / file / UI streaming logger
│   ├── models.py                 # Data classes
│   ├── pipeline.py               # Main orchestration pipeline
│   ├── ffmpeg_renderer.py        # FFmpeg rendering (Ken Burns, NVENC)
│   └── utils.py                  # Script splitting, duration estimation
│
├── providers/
│   ├── tts_base.py               # TTS provider interface
│   ├── elevenlabs_tts.py         # ElevenLabs provider
│   ├── deepgram_tts.py           # Deepgram provider
│   ├── image_base.py             # Image provider interface
│   ├── replicate_image.py        # Replicate image provider
│   ├── video_base.py             # Video provider interface (future)
│   └── dummy_video_provider.py   # No-op placeholder
│
├── ui/
│   ├── main_window.py            # Tkinter main window
│   └── worker.py                 # Background thread worker
│
├── prompts/
│   ├── images/
│   │   └── images.txt            # Visual style instructions for image gen
│   └── scripts/
│       └── sample_story.txt      # Example narration script
│
└── projects/
    ├── output/                   # Final MP4 outputs (timestamped folders)
    └── temp/                     # Intermediate files (audio, raw images)
```

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/proditserbia/StoryFrame-Studio.git
cd StoryFrame-Studio
```

### 2. Create a virtual environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your API keys
```

---

## .env Configuration

| Variable | Default | Description |
|---|---|---|
| `TTS_PROVIDER` | `elevenlabs` | Active TTS provider (`elevenlabs` or `deepgram`) |
| `ELEVENLABS_API_KEY` | — | ElevenLabs API key |
| `ELEVENLABS_VOICE_ID` | — | ElevenLabs voice ID |
| `DEEPGRAM_API_KEY` | — | Deepgram API key |
| `DEEPGRAM_VOICE_MODEL` | `aura-asteria-en` | Deepgram Aura model name |
| `IMAGE_PROVIDER` | `replicate` | Image provider (`replicate`) |
| `REPLICATE_API_TOKEN` | — | Replicate API token |
| `REPLICATE_MODEL` | — | Replicate model ID (e.g. `stability-ai/sdxl:...`) |
| `VIDEO_PROVIDER` | `none` | Video provider (future; use `none`) |
| `FFMPEG_PATH` | `ffmpeg` | Path to ffmpeg binary |
| `FFPROBE_PATH` | `ffprobe` | Path to ffprobe binary |
| `USE_NVENC_AUTO` | `true` | Auto-detect NVIDIA NVENC GPU encoder |
| `DEFAULT_FPS` | `30` | Output video frame rate |
| `DEFAULT_RESOLUTION` | `1920x1080` | Output resolution |
| `IMAGE_DURATION_SECONDS` | `8` | Duration each image is shown (seconds) |
| `ZOOM_STYLE` | `ken_burns` | `ken_burns` or `static` |
| `CROSSFADE_DURATION` | `1.0` | Crossfade transition length (seconds) |
| `OUTPUT_DIR` | `projects/output` | Final video output directory |
| `TEMP_DIR` | `projects/temp` | Intermediate files directory |

---

## FFmpeg Installation

FFmpeg must be installed and available on your system PATH.

### Windows
1. Download from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html) (choose a Windows build).
2. Extract and add the `bin/` folder to your system `PATH`.
3. Verify: `ffmpeg -version`

### macOS
```bash
brew install ffmpeg
```

### Linux (Debian/Ubuntu)
```bash
sudo apt update && sudo apt install ffmpeg
```

### Custom path
If FFmpeg is not on PATH, set `FFMPEG_PATH` and `FFPROBE_PATH` in `.env` to the full executable paths.

---

## Running the App

```bash
python app.py
```

The Tkinter window will open. Select your script, image instructions, TTS provider, then click **Start**.

---

## Placing Scripts

Put plain `.txt` files in `prompts/scripts/`.

Each file should contain the full narration text. The app will split it automatically into scenes/segments using paragraph breaks and sentence boundaries.

Example structure:
```
prompts/scripts/
├── sample_story.txt
├── my_horror_episode_1.txt
└── documentary_intro.txt
```

---

## Editing Image Instructions

Edit `prompts/images/images.txt` to define the visual style for image generation.

This file is combined with each script segment to build image prompts. Write it as a list of style directives:

```
Cinematic photorealistic style.
High-contrast dramatic lighting.
No text overlays.
Color palette: deep blues and warm ambers.
```

You can have different `images.txt` files for different projects — just select the correct one in the UI.

---

## Switching TTS Providers

**Option 1 – UI dropdown:** Select "elevenlabs" or "deepgram" from the TTS provider dropdown before starting.

**Option 2 – .env default:** Set `TTS_PROVIDER=deepgram` (or `elevenlabs`) in `.env`.

Make sure the corresponding API keys are filled in `.env`.

### ElevenLabs
- Sign up at [elevenlabs.io](https://elevenlabs.io)
- Copy your API key and a voice ID into `.env`

### Deepgram
- Sign up at [deepgram.com](https://deepgram.com)
- Copy your API key into `.env`
- Optionally change `DEEPGRAM_VOICE_MODEL` (e.g. `aura-luna-en`, `aura-zeus-en`)

---

## How Rendering Works

1. **Script segmentation** — The script is split into segments (by paragraph/sentence).
2. **TTS narration** — The full script text is sent to the selected TTS provider; a single MP3 is returned.
3. **Image prompts** — Each segment is combined with your `images.txt` style instructions to build one image prompt per segment.
4. **Image generation** — Each prompt is sent to Replicate; images are saved locally.
5. **Video clips** — FFmpeg generates a short video clip from each image, with a Ken Burns zoom/pan effect.
6. **Concatenation** — Clips are joined with optional crossfade transitions.
7. **Audio merge** — The narration audio is merged into the video and the result is trimmed to audio length.
8. **Output** — Final MP4 plus `metadata.json` are saved in `projects/output/<timestamp>/`.

### NVENC (GPU acceleration)
If `USE_NVENC_AUTO=true` and an NVIDIA GPU with NVENC is available, the encoder switches to `h264_nvenc` automatically. Otherwise `libx264` (software) is used.

---

## Future Extensions

The codebase is designed for easy extension:

| Extension | Where to add it |
|---|---|
| New TTS provider | Subclass `providers/tts_base.py` |
| New image provider | Subclass `providers/image_base.py` |
| AI video provider (Runway, Pika) | Subclass `providers/video_base.py` |
| LLM prompt rewriting | Add a rewriter step in `core/pipeline.py` between segmentation and image gen |
| Additional UI settings | Extend `ui/main_window.py` controls frame |
| New output format | Extend `core/ffmpeg_renderer.py` |

---

## License

MIT License. See [LICENSE](LICENSE) for details.
