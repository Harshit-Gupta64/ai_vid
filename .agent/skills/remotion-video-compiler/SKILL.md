---
name: remotion-video-compiler
description: Assemble vertical 9:16 short-form video from voiceover, keyframe images, animated kinetic text, and auto-ducked background music (-22dB under dialogue, -12dB during pauses) into out/final_short.mp4 using Remotion / FFmpeg.
---

# Remotion Video Compiler Skill

This skill compiles the final 1080x1920 vertical video (`out/final_short.mp4`) from the generated assets:
- Voiceover narration: `assets/audio/voiceover.wav`
- Word-level timestamps: `assets/audio/timestamps.json`
- Keyframe visual frames: `assets/frames/scene_1.png` ... `assets/frames/scene_5.png`
- Background music (BGM): `assets/bgm/soundtrack.wav` (with automatic procedural generator if empty)
- 5-Scene storyboard metadata: `state/storyboard.json`

## Dynamic Audio Auto-Ducking Specification

The compiler applies professional broadcast auto-ducking to the background music:
- **During Dialogue**: BGM is suppressed to **-22 dB** so the voiceover remains crisp, punchy, and completely intelligible.
- **During Pauses & Scene Transitions**: BGM swells to **-12 dB** to maintain rhythmic momentum and dramatic weight.
- **Sidechain Implementation**: Achieved via FFmpeg `sidechaincompress` or Remotion Web Audio API nodes:
  ```text
  [1:a]asplit[bgm_clean][bgm_sc];
  [0:a][bgm_sc]sidechaincompress=threshold=0.08:ratio=5:attack=40:release=350[ducked_bgm];
  [0:a][ducked_bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]
  ```

## Visual Composition Features

1. **Ken Burns Motion**: Vertical zoom-in (`zoompan=z='min(zoom+0.0015,1.15)'`) and panning to prevent static visual fatigue.
2. **Kinetic Caption Sync**: Words highlight or display in rhythm with `timestamps.json`.
3. **Smooth Crossfades**: Seamless 0.3s dissolve transitions between the 5 tactical scenes.
4. **Resolution & Codec**: 1080x1920, 30fps (or 60fps), H.264 / AAC, YUV420p.

## Usage

Via shell script:
```bash
bash .agent/skills/remotion-video-compiler/scripts/render_short.sh \
  --storyboard state/storyboard.json \
  --audio assets/audio/voiceover.wav \
  --timestamps assets/audio/timestamps.json \
  --frames-dir assets/frames \
  --bgm assets/bgm/soundtrack.wav \
  --output out/final_short.mp4
```

Or via cross-platform Python CLI:
```bash
python .agent/skills/remotion-video-compiler/scripts/render_short.py \
  --storyboard state/storyboard.json \
  --output out/final_short.mp4
```

## Verification

Validate generated video quality and technical specs against the storyboard:
```bash
python .agent/skills/remotion-video-compiler/scripts/verify_video.py \
  --video out/final_short.mp4 \
  --storyboard state/storyboard.json
```
