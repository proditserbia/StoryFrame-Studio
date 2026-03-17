# StoryFrame Studio

A production-ready Python desktop application for content creators that generates AI-narrated videos from scripts. Built with Tkinter, FFmpeg, ElevenLabs/Deepgram for narration, and Replicate for image generation.

StoryFrame Studio is **niche-neutral by design**. The application code, UI, and architecture are generic so the same app can be reused for horror stories, mystery narration, documentary voiceovers, educational content, or any other narrated YouTube format. All visual and thematic customisation lives in editable `.txt` files — no code changes required to retheme.

---

## Table of Contents

- [Overview](#overview)
- [Folder Structure](#folder-structure)
- [Prompt File Architecture](#prompt-file-architecture)
- [Setup](#setup)
- [.env Configuration](#env-configuration)
- [FFmpeg Installation](#ffmpeg-installation)
- [Running the App](#running-the-app)
- [Placing Scripts](#placing-scripts)
- [Retheme for a New Niche](#retheme-for-a-new-niche)
- [Prompt File Reference](#prompt-file-reference)
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
│   └── utils.py                  # Script splitting, prompt building, helpers
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
│   ├── images/                   # Default (generic) prompt files
│   │   ├── images.txt            # ← required: global visual style rules
│   │   └── anchors.txt           # ← optional: cross-scene consistency hints
│   ├── scripts/
│   │   └── sample_story.txt      # Example narration script
│   └── presets/
│       └── horror/               # Ready-to-use horror channel preset
│           ├── images.txt        # Horror visual style
│           ├── anchors.txt       # Horror consistency anchors
│           ├── shot_rules.txt    # Horror camera / shot rules
│           ├── negative.txt      # Horror negative constraints
│           └── sample_story.txt  # Horror story example
│
└── projects/
    ├── output/                   # Final MP4 outputs (timestamped folders)
    └── temp/                     # Intermediate files (audio, raw images)
```

---

## Prompt File Architecture

All visual and thematic adaptation happens through editable text files in the `prompts/` folder — not through code changes.

### How prompt assembly works

For each script segment, the app builds an image prompt by combining text-file blocks in this fixed order:

```
1. GLOBAL STYLE RULES      ← images.txt          (required)
2. CONSISTENCY ANCHORS     ← anchors.txt          (optional)
3. SHOT RULES              ← shot_rules.txt       (optional)
4. NEGATIVE CONSTRAINTS    ← negative.txt         (optional)
5. CURRENT NARRATION SEGMENT  ← the script text
6. TASK                    ← built-in instruction
```

Optional files are discovered automatically in the **same directory** as the selected `images.txt`. If a file is absent, its block is silently skipped. The pipeline logs which files were loaded:

```
[Prompt] Loaded images.txt
[Prompt] Loaded anchors.txt
[Prompt] shot_rules.txt not found, skipping.
[Prompt] negative.txt not found, skipping.
```

The final assembled prompt for every segment is saved in `metadata.json` under the `visual_plan` array so you can inspect and debug what was sent to the image model.

### Switching niches

To adapt the app to a new niche, point the **Image instructions** file picker at the `images.txt` inside a different preset folder. The app automatically loads all optional sibling files (`anchors.txt`, `shot_rules.txt`, `negative.txt`) from that same folder.

**Example — switch to the horror preset:**

1. Open StoryFrame Studio.
2. Click **Browse…** next to *Image instructions*.
3. Navigate to `prompts/presets/horror/` and select `images.txt`.
4. The app loads all four horror files automatically.

**Example — create your own preset:**

```
prompts/presets/my-documentary/
├── images.txt        ← visual style (required)
├── anchors.txt       ← consistency rules (optional)
├── shot_rules.txt    ← camera rules (optional)
└── negative.txt      ← exclusions (optional)
```

No code changes required. Just create the folder, write your text files, and select the `images.txt` in the UI.

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
| `TTS_LEADING_SILENCE_SECONDS` | `0.0` | Seconds of silence before narration starts |
| `TTS_TRAILING_SILENCE_SECONDS` | `0.0` | Seconds of silence after narration ends |
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
├── episode_01.txt
└── documentary_intro.txt
```

---

## Retheme for a New Niche

StoryFrame Studio ships with:

- `prompts/images/` — generic niche-neutral defaults (used out of the box)
- `prompts/presets/horror/` — a ready-to-use horror channel preset

**To use the horror preset:**
1. In the UI, click **Browse…** next to *Image instructions*.
2. Navigate to `prompts/presets/horror/` and select `images.txt`.
3. The four horror files (`images.txt`, `anchors.txt`, `shot_rules.txt`, `negative.txt`) are all loaded automatically.

**To create your own preset:**
1. Create a new folder, e.g. `prompts/presets/mystery/`.
2. Add your `images.txt` (required) and any optional files.
3. Select that `images.txt` in the UI.

No Python code changes are ever needed to retheme.

---

## Prompt File Reference

| File | Required | Purpose |
|---|---|---|
| `images.txt` | **Yes** | Global visual style rules; defines the look and mood of every generated image |
| `anchors.txt` | No | Cross-scene consistency anchors; keeps lighting, colour, and character depiction uniform |
| `shot_rules.txt` | No | Camera and composition rules; controls framing, angle, and shot type priorities |
| `negative.txt` | No | Hard exclusions passed to the image model to suppress unwanted content |

All optional files are auto-discovered from the **same directory** as the selected `images.txt`. Missing files are logged and skipped gracefully.

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

1. **Script segmentation** — The script is split into segments (by paragraph/sentence boundary).
2. **TTS narration** — The full script text is sent to the selected TTS provider; a single MP3 is returned.
3. **Prompt assembly** — For each segment, the app builds one image prompt by combining the loaded text-file blocks (style rules, anchors, shot rules, negatives) with the narration text.
4. **Image generation** — Each prompt is sent to Replicate; images are saved locally.
5. **Video clips** — FFmpeg generates a short video clip from each image, with a Ken Burns zoom/pan effect.
6. **Concatenation** — Clips are joined with optional crossfade transitions.
7. **Audio merge** — The narration audio is merged into the video and the result is trimmed to audio length.
8. **Output** — Final MP4 plus `metadata.json` (including all assembled prompts) are saved in `projects/output/<timestamp>/`.

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
| New niche preset | Add a folder under `prompts/presets/` with text files |
| LLM prompt rewriting | Add a rewriter step in `core/pipeline.py` between segmentation and image gen |
| Additional UI settings | Extend `ui/main_window.py` controls frame |
| New output format | Extend `core/ffmpeg_renderer.py` |

---

## License

MIT License. See [LICENSE](LICENSE) for details.
