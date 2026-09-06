# System Architecture: Tactical History Short-Form Video Generator

This document outlines the architecture, data contracts, and execution model for the autonomous end-to-end video generation system.

---

## 1. High-Level Architecture Overview

```
+-------------------------------------------------------------------------------+
|                            Autonomous Agent Workspace                         |
+-------------------------------------------------------------------------------+
        |
        v
+------------------+     state/topic.json      +-------------------+
|   topic-miner    | ------------------------> |   video-scriptor  |
+------------------+                           +-------------------+
                                                         |
                                 +-----------------------+-----------------------+
                                 | state/storyboard.json                         |
                                 v                                               v
                      +----------------------+                       +---------------------+
                      | tts-audio-generator  |                       |   image-generator   |
                      |  (Kokoro-82M / TTS)  |                       |  (ComfyUI / Diff.)  |
                      +----------------------+                       +---------------------+
                                 |                                               |
                  voiceover.wav  |                                               | scene_{1..5}.png
                  timestamps.json|                                               |
                                 +-----------------------+-----------------------+
                                                         |
                                                         v
                                           +----------------------------+
                                           |  remotion-video-compiler   |
                                           |   (Sidechain Auto-Ducking) |
                                           +----------------------------+
                                                         |
                                                         v
                                               out/final_short.mp4
```

---

## 2. Directory Structure & Asset Topology

```
c:/Projects/Videos/
├── .agent/
│   ├── skills/
│   │   ├── topic-miner/
│   │   │   ├── SKILL.md
│   │   │   └── scripts/
│   │   │       └── mine_topics.py
│   │   ├── video-scriptor/
│   │   │   ├── SKILL.md
│   │   │   └── scripts/
│   │   │       └── generate_storyboard.py
│   │   ├── tts-audio-generator/
│   │   │   ├── SKILL.md
│   │   │   └── scripts/
│   │   │       └── synthesize.py
│   │   ├── image-generator/
│   │   │   ├── SKILL.md
│   │   │   └── scripts/
│   │   │       └── generate_frames.py
│   │   └── remotion-video-compiler/
│   │       ├── SKILL.md
│   │       └── scripts/
│   │           ├── render_short.sh
│   │           └── render_short.py
│   └── workflows/
│       └── build-video.md
├── assets/
│   ├── audio/
│   │   ├── voiceover.wav
│   │   └── timestamps.json
│   ├── frames/
│   │   ├── scene_1.png ... scene_5.png
│   ├── bgm/
│   │   └── soundtrack.wav
├── state/
│   ├── topic.json
│   └── storyboard.json
├── out/
│   └── final_short.mp4
├── architecture.md
└── decisions.md
```

---

## 3. Subsystem Breakdown

### 3.1 Topic Miner (`.agent/skills/topic-miner`)
- **Role**: Curates, filters, and structures niche tactical history topics.
- **Contract**: Writes `state/topic.json`.
- **Key Fields**: `id`, `title`, `category`, `historical_era`, `core_anomaly`, `hook_hookline`, `key_facts`, `visual_motifs`.

### 3.2 Video Scriptor (`.agent/skills/video-scriptor`)
- **Role**: Translates raw historical tactical anomalies into a 12 to 16 micro-scene vertical documentary storyboard with variable narrative pacing.
- **Narrative Beat Architecture (`beat_type`)**:
  - `establishing`: 2.0s – 2.8s (~5-8 words). Context, initial staging, hook.
  - `rising_tension`: 2.8s – 3.5s (~8-10 words). Mechanism reveal, tactical approach, assembly.
  - `climax_impact`: 3.5s – 5.0s (~10-14 words). Decisive strike, catastrophic failure, payoff hold.
  - `resolution_loop`: 2.5s – 3.5s (~7-10 words). Historical verdict, tactical legacy, infinite loop hook.
- **Constraint Layer**:
  - Cyclical Shot Scale Rotation: `[Extreme Macro Close-Up, Low-Angle Grounded POV, Wide Tactical Action, Medium Tension Portrait]`.
  - Pacing: ~2.8 words/second, scaled per-scene against each scene's own duration.
  - Phrasing Bans: Strictly forbids `In [year]`, `This/It was`, or passive proper-noun exposition (`X was/were`).
  - Cinema Lens Anchoring: Prefixes `CINEMA_LENS_SUFFIX` (`Arri Alexa LF, 35mm anamorphic prime lens, volumetric torchlight...`) at the start of every diffusion prompt.
- **Contract**: Writes `state/storyboard.json`.

### 3.3 TTS Audio Generator (`.agent/skills/tts-audio-generator`)
- **Role**: Synthesizes speech from narration text and extracts millisecond-accurate word boundaries.
- **Primary Engine**: Kokoro-82M (low footprint, high naturalness).
- **Fallback Chain**: `kokoro` -> `edge-tts` -> `pyttsx3` -> Carrier WAV synthesizer.
- **Contract**: Writes `assets/audio/voiceover.wav` and `assets/audio/timestamps.json`.

### 3.4 Image Generator (`.agent/skills/image-generator`)
- **Role**: Generates vertical 1080x1920 keyframes matching the exact visual prompt of each scene.
- **Primary Engine**: ComfyUI REST API (`/prompt`) or PyTorch Diffusers.
- **Fallback Chain**: Volumetric artistic canvas painter (PIL chiaroscuro generator) ensuring zero-failure execution when GPU servers are cold.
- **Contract**: Writes `assets/frames/scene_{1..5}.png`.

### 3.5 Remotion Video Compiler (`.agent/skills/remotion-video-compiler`)
- **Role**: Assembles video, voiceover, BGM, and kinetic motion.
- **Audio Sidechain Ducking**:
  - Normal Dialogue: BGM compressed down to **-22 dB**.
  - Pauses & Transitions: BGM swells to **-12 dB**.
  - Implemented via FFmpeg `sidechaincompress` audio filter.
- **Visual Engine**: Ken Burns zoom/pan (`zoompan`) and vertical crossfades.
- **Contract**: Writes `out/final_short.mp4`.

---

## 4. State Transition & Contract Specifications

### `state/topic.json`
```json
{
  "id": "archimedes-claw",
  "title": "The Claw of Archimedes: Rome's Maritime Nightmare",
  "category": "siege_engine",
  "historical_era": "Second Punic War (214-212 BC)",
  "core_anomaly": "A counterweight crane that lifted Roman galleys vertically from the ocean.",
  "hook_hookline": "In 213 BC, Rome's invincible navy was plucked out of the sea by an invisible iron hand.",
  "key_facts": ["Designed by Archimedes", "Used counterweight pulleys", "Caused total psychological panic"],
  "visual_motifs": ["Stormy seas", "Iron claw", "Vertical warship", "Fortress ramparts"]
}
```

### `state/storyboard.json`
Contains array of 5 scenes with `time_range`, `target_duration`, `narration`, `diffusion_prompt`, and `sound_fx_cue`.
Total word count strictly kept near 130 words.
Visual prompts strictly suffixed with `--ar 9:16, dark atmospheric oil painting, volumetric lighting, high fidelity`.
