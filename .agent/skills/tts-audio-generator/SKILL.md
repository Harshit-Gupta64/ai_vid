---
name: tts-audio-generator
description: Generate high-fidelity narration audio (using Kokoro-82M or local TTS) and word-level aligned timestamps JSON for automated short-form video compilation.
---

# TTS Audio Generator Skill

This skill reads `state/storyboard.json`, extracts scene narrations, synthesizes voiceover audio using Kokoro-82M (or local TTS backends), and writes both the composite audio (`assets/audio/voiceover.wav`) and the word-level alignment file (`assets/audio/timestamps.json`).

## Architecture & Target Model

- **Primary Engine**: **Kokoro-82M** (`kokoro` / `kokoro-onnx`), an ultra-lightweight, 82M-parameter state-of-the-art open-weights text-to-speech model capable of natural cadence, gravitas, and fast-paced documentary narration.
- **Recommended Voice**: `am_adam` or `bm_george` (deep, authoritative, documentary cadence suited for ancient warfare).
- **Fallback Backends**:
  - `edge-tts` (high-fidelity neural voice, e.g. `en-GB-RyanNeural` or `en-US-ChristopherNeural`)
  - `pyttsx3` (system offline voice)
  - Synthetic carrier-aligned WAV generator (ensures complete pipeline execution and timestamping even without GPU/heavy weights installed).

## Outputs

1. `assets/audio/voiceover.wav`: 24kHz or 48kHz mono/stereo WAV of the complete 45-second narration.
2. `assets/audio/timestamps.json`: Word-by-word timestamp map used by Remotion/FFmpeg for synchronized kinetic captions:
   ```json
   {
     "total_duration": 44.8,
     "sample_rate": 24000,
     "scenes": [
       {
         "scene_id": 1,
         "start_time": 0.0,
         "end_time": 3.12,
         "narration": "In 213 BC, Rome's invincible navy was grabbed by an invisible iron hand.",
         "words": [
           {"word": "In", "start": 0.05, "end": 0.22},
           {"word": "213", "start": 0.24, "end": 0.65},
           {"word": "BC,", "start": 0.68, "end": 0.95},
           {"word": "Rome's", "start": 1.05, "end": 1.42},
           {"word": "invincible", "start": 1.45, "end": 1.98},
           {"word": "navy", "start": 2.02, "end": 2.30},
           {"word": "was", "start": 2.32, "end": 2.45},
           {"word": "grabbed", "start": 2.48, "end": 2.78},
           {"word": "by", "start": 2.80, "end": 2.90},
           {"word": "an", "start": 2.92, "end": 3.01},
           {"word": "invisible", "start": 3.03, "end": 3.45},
           {"word": "iron", "start": 3.48, "end": 3.75},
           {"word": "hand.", "start": 3.78, "end": 4.10}
         ]
       }
     ]
   }
   ```

## Usage

Run via CLI:
```bash
python .agent/skills/tts-audio-generator/scripts/synthesize.py \
  --storyboard state/storyboard.json \
  --output-audio assets/audio/voiceover.wav \
  --output-timestamps assets/audio/timestamps.json \
  --voice am_adam \
  --speed 1.05
```
