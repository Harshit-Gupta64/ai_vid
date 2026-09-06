# ARCHITECTURAL BLUEPRINT: AI_VID PIPELINE OVERHAUL (V4)
**Role**: ARCHITECT (Role 1)  
**Date**: September 5, 2026  
**Status**: PROPOSED — PENDING REVIEW PRIOR TO IMPLEMENTATION  

---

## 1. Executive Summary

This architecture document defines the structural overhaul of the `ai_vid` short-form historical documentary pipeline. The overhaul addresses three core architectural bottlenecks:
1. **Monotonous Pacing**: Replacing the rigid flat validation band (2.2s–3.2s) with **narrative-weight variable pacing** governed by explicit `beat_type` declarations.
2. **Ken Burns & Audio-Video Synchronization Integrity**: Verifying zoompan frame mathematics under duration variance, auditing audio ducking reactivity, and preserving the true unidirectional dependency flow between speech synthesis, word-alignment, and video composition.
3. **Unattended Batch Resilience**: Implementing an isolated, resumable, multi-topic batch orchestration engine that survives unexpected API drops or intermediate task exceptions without stopping the pipeline.

---

## 2. Variable Scene-Duration Design (Pacing Tied to Narrative Weight)

### 2.1 The Narrative Beat Model
The flat 2.2s–3.2s per-scene restriction forces artificial pacing uniformity: an intense 60-ton ship being lifted by a claw requires longer payoff and atmospheric hold, whereas rapid-fire setup clauses require brisk tempo. 

We define four distinct narrative beat categories:

| Beat Type (`beat_type`) | Narrative Function | Target Duration Range | Word Count (~2.8 wps) | Visual & Audio Characteristics |
| :--- | :--- | :--- | :--- | :--- |
| `establishing` | Context, hook, initial staging, premise | **2.0s – 2.8s** | 5 – 8 words | High tempo, punchy hook, rapid camera motion |
| `rising_tension` | Mechanism reveal, logistics, tactical approach | **2.8s – 3.5s** | 8 – 10 words | Steady tracking, mechanical texture, escalating SFX |
| `climax_impact` | Decisive strike, catastrophic failure, trap spring | **3.5s – 5.0s** | 10 – 14 words | Dramatic hold, snap zoom or slow push, peak SFX cue |
| `resolution_loop` | Tactical legacy, historical verdict, loop-back hook | **2.5s – 3.5s** | 7 – 10 words | Wide framing, lingering conclusion, seamless loop |

### 2.2 Storyboard Schema Extension
In `state/storyboard.json`, every scene object in `scenes[]` will declare `beat_type`:

```json
{
  "scene_id": 9,
  "beat_type": "climax_impact",
  "shot_scale": "Extreme Macro Close-Up",
  "time_range": "24.8-29.2",
  "target_duration": 4.4,
  "narration": "Heavy counterweight stones dropped, snapping the cedar hull clean in two.",
  "tactile_material_action": "Massive counterweight stones plunging into water, snapping saturated cedar ribs",
  "visual_description": "Violent fracture of drenched wooden warship ribs bursting under upward lever tension",
  "camera_angle": "low-angle upward impact view",
  "focal_length": "24mm anamorphic wide",
  "lighting_scheme": "violent orange torchlight catching splintering wood and churning sea foam",
  "camera_motion": "slow push-in",
  "sound_fx_cue": "catastrophic_timber_shatter",
  "visual_prompt": "...",
  "diffusion_prompt": "...",
  "negative_prompt": "..."
}
```

### 2.3 LLM Prompt & Programmatic Validator Upgrades (`generate_storyboard.py`)

#### Gemini System Prompt Directives:
- The system instruction will instruct Gemini (`gemini-2.5-flash`) to assign each of the 12–16 scenes to one of the four beat types based on narrative progression:
  - Scenes 1–3: `establishing`
  - Scenes 4–8: `rising_tension`
  - Scenes 9–11: `climax_impact`
  - Scenes 12–14: `resolution_loop`
- Gemini must generate narration lengths calibrated to the scene's beat type (e.g. 5–7 words for `establishing`, 10–14 words for `climax_impact`).

#### Programmatic Validator Rules:
1. **Beat Type Validation**: Every scene must have `beat_type in ["establishing", "rising_tension", "climax_impact", "resolution_loop"]`.
2. **Per-Beat Duration Range**:
   - `establishing`: `2.0 <= target_duration <= 2.8`
   - `rising_tension`: `2.8 <= target_duration <= 3.5`
   - `climax_impact`: `3.5 <= target_duration <= 5.0`
   - `resolution_loop`: `2.5 <= target_duration <= 3.5`
3. **Per-Scene Speech Pacing**:
   - Rather than checking only a single aggregate word count, each scene's word count is validated against its own target duration:
     `expected_words = target_duration * 2.8`
     `allowed_range = [max(4, int(expected_words * 0.75)), int(expected_words * 1.25) + 2]`
4. **Encyclopedia Phrasing Ban Tightening**:
   - The current `banned_x_was` regex (`r"^(?:the\s+)?[a-z0-9'\-]+\s+(?:was|were)"`) is over-broad, falsely catching active noun clauses like *"The iron was..."* or *"Timber was..."*.
   - **Fix**: Require capitalized proper nouns or capitalized titular subjects:
     ```python
     banned_proper_noun_was = re.compile(r"^(?:The\s+)?[A-Z][a-z0-9'\-]+\s+(?:was|were)")
     ```
     This strictly targets passive biographical and historical exposition (*"Archimedes was..."*, *"Marcellus was..."*, *"The Consul was..."*) without flagging active material descriptions.

---

## 3. Downstream Math & Synchronization Verification

### 3.1 Verification of `render_short.py` Ken Burns Mathematics
A critical code trace of `render_short.py` reveals the following:

#### Frame Count Handling:
```python
scene_frames = int(duration * fps)
```
In FFmpeg, setting `d={scene_frames}` correctly instructs the `zoompan` filter to run for the exact number of frames corresponding to `duration`. The downstream `trim=duration={duration},setpts=PTS-STARTPTS` then guarantees the stream duration matches `duration`.

#### Bottleneck Identified: Static Increments Clamp Prematurely on Long Scenes:
In `render_short.py` lines 290–301:
- **Push-in (`m_type == 0`)**: `zoompan=z='min(zoom+0.002,1.25)'`
  - At 30 fps, a 5.0s scene has 150 frames.
  - Starting at 1.0, zoom increments by $0.002 	imes 150 = 0.30$.
  - It hits the 1.25 ceiling at frame 125 ($4.17s$) and **freezes dead for the final 0.83 seconds**.
- **Snap zoom-out (`m_type == 3`)**: `zoompan=z='if(eq(on,1),1.22,max(1.0,zoom-0.002))'`
  - Starting at 1.22, decreasing by 0.002 per frame reaches 1.00 at frame 110 ($3.67s$) and **freezes dead for the final 1.33 seconds** of a 5.0s scene.
- **Pan Right & Tilt Down (`m_type == 1, 2`)**: `x+1.2` or `y+1.2`
  - Fixed 1.2 px/frame travel over 150 frames is 180 px. With zoom at 1.12, the crop window width is $1080 / 1.12 = 964$ px, leaving only $1080 - 964 = 116$ px of panning margin before hitting the image edge. The motion halts early at frame 96 ($3.2s$).

#### Mathematical Fix for `render_short.py`:
Normalize the transformation velocity by `scene_frames`:
- **Push-in**: `z_step = 0.22 / scene_frames` $ightarrow$ `z='min(zoom+' + f'{z_step:.5f}' + ',1.25)'`
- **Zoom-out**: `z_step = 0.20 / scene_frames` $ightarrow$ `z='if(eq(on,1),1.22,max(1.02,zoom-' + f'{z_step:.5f}' + '))'`
- **Tracking Pan**: `x_step = (width * 0.09) / scene_frames` $ightarrow$ smooth travel across entire duration without border collision.

### 3.2 Audio & Caption Dependency Direction Analysis
A deep trace of `synthesize.py` confirms:
1. `synthesize.py` synthesizes each scene narration independently via Edge-TTS.
2. It measures the **exact duration of the resulting MP3**:
   ```python
   dur_match = re.search(r"Duration:\s*(\d+):(\d+):([\d\.]+)", probe_res.stderr)
   scene_dur = h * 3600 + m * 60 + s
   ```
3. It updates `current_time_offset += scene_dur` and generates word-level timestamps in `timestamps.json`.
4. **Crucially, lines 234–242 write back the actual measured audio duration into `storyboard.json`**:
   ```python
   for sc, rec in zip(storyboard.get("scenes", []), scene_records):
       sc_dur = round(rec["end_time"] - rec["start_time"], 2)
       sc["target_duration"] = sc_dur
       sc["time_range"] = f"{rec['start_time']:.1f}-{rec['end_time']:.1f}"
   ```
5. `render_short.py` then consumes `target_duration` from the updated `storyboard.json`.

**Conclusion**: The dependency runs **Narration Text $ightarrow$ Edge-TTS Audio Duration $ightarrow$ Storyboard Target Duration $ightarrow$ Video Splicing Length**.
Uneven durations do NOT break audio/caption sync because timestamps are measured directly from the generated audio, and video cuts match the audio duration.
However, to achieve a 4.0–5.0s climax beat, the scriptor must generate a correspondingly longer narration clause (10–14 words) for that beat.

---

## 4. Downstream Script Audit: Scripts Assuming Equal Durations

| File | Line(s) | Assumption / Issue | Silent Failure / Risk | Required Fix |
| :--- | :--- | :--- | :--- | :--- |
| `.agent/skills/video-verifier/scripts/deep_qa_inspector.py` | 151–153 | `long_cuts = [d for d in durations if d > 4.5]` | **FATAL FALSE POSITIVE**: Climax cuts of 4.5s–5.0s will fail QA with *"Found cuts exceeding 4.5s"*. | Update threshold to allow climax cuts up to 5.0s (`d > 5.0`). |
| `.agent/skills/video-verifier/scripts/deep_qa_inspector.py` | 148–149 | `avg_cut < 2.0 or avg_cut > 3.8` | **RISK**: If multiple climax beats push average to 3.85s, QA rejects valid documentary. | Expand range to `[2.0s, 4.0s]`. |
| `.agent/skills/remotion-video-compiler/scripts/render_short.py` | 290–301 | Constant per-frame zoom/pan steps (0.002, 1.2px) | **VISUAL ARTIFACT**: 4s–5s scenes clamp and freeze motion prematurely. | Scale motion steps inversely with `scene_frames`. |
| `.agent/skills/remotion-video-compiler/scripts/render_short.py` | 311 | BGM input without loop flag | **AUDIO DROPOUT**: If BGM is shorter than video duration, BGM ends mid-sentence. | Prepend `-stream_loop -1` before BGM input. |
| `.agent/skills/remotion-video-compiler/scripts/verify_video.py` | 146 | Total duration tolerance $\pm 2.0$s | Safe: compares video duration against sum of scenes. | No change required. |
| `.agent/skills/video-verifier/scripts/audit_video.py` | 37–38 | `sample_time = current_time + (duration / 2.0)` | Safe: handles arbitrary durations correctly. | No change required. |

---

## 5. Sidechain Audio Ducking Verification Design

### 5.1 The Issue
The sidechain compression filtergraph in `render_short.py`:
```
[voice_idx:a]volume=1.0,aformat=...,asplit=2[voice_main][voice_sidechain];
[bgm_idx:a]aformat=...[bgm_fmt];
[bgm_fmt][voice_sidechain]sidechaincompress=threshold=0.08:ratio=6:attack=20:release=250:makeup=1.2[ducked_bgm];
[voice_main][ducked_bgm]amix=inputs=2:duration=first:dropout_transition=2,alimiter=limit=0.95[a_out]
```
While syntactically valid, a silent issue arises if:
1. **Input Length Mismatch**: If the BGM track has shorter duration than the voiceover and terminates without looping, `amix` may drop early or sidechain compressor may behave erratically.
2. **Track-Level Reactivity Verification**: Ducking cannot simply be assumed because the filter exists. Implementer 3 must extract the isolated ducked BGM channel and verify differential RMS volume between active dialogue frames and pause/inter-scene intervals.

### 5.2 Verification Protocol
Implementer 3 / Auditor will run an automated probe:
1. Render an audio test mix with voice muted or exported separately as `[ducked_bgm]`.
2. Measure RMS power during known voice timestamps (`start_time` to `end_time` from `timestamps.json`) vs. inter-scene pauses (>300ms gaps).
3. Confirm a measurable drop of $\ge 8$ dB under speech relative to pauses.

---

## 6. Multi-Hour Unattended Batch Orchestration Architecture

### 6.1 Requirements
1. **Bounded Parallelism / Clean Sequencing**: Sequential topic execution with isolated subprocesses to prevent GPU VRAM exhaustion or FFmpeg process contention.
2. **Per-Topic Isolation**: Failure on topic $k$ (network timeout, rate limit, QA violation) must be caught, recorded, and quarantined without impacting topics $k+1 \dots N$.
3. **Resumability**: Mid-run interruption (Ctrl+C, crash) resumes from the last incomplete topic, never re-running already completed topics.
4. **State Machine & Persistence**: Stored in `state/batch_progress.json`.
5. **Comprehensive Markdown Reporting**: Emits `out/BATCH_REPORT.md` with status, timing, duration variance, and deep QA audit logs.

### 6.2 Data Contracts

#### `state/batch_queue.json` (Input Queue):
```json
{
  "batch_name": "ancient_warfare_anomalies_v4",
  "topics": [
    "archimedes-claw",
    "battle-of-carrhae-camel-train",
    "byzantine-cheirosiphona",
    "battle-of-pelusium-cat-shields",
    "flaming-war-pigs-megara"
  ]
}
```

#### `state/batch_progress.json` (Resumable State):
```json
{
  "batch_id": "batch_20260905_120000",
  "last_updated": "2026-09-05T12:30:00Z",
  "total_topics": 5,
  "completed": [
    {
      "topic_id": "archimedes-claw",
      "status": "SUCCESS",
      "duration": 47.2,
      "scenes": 13,
      "duration_variance": {"min": 2.2, "max": 4.8, "std_dev": 0.82},
      "video_path": "out/releases_v4/archimedes-claw/final_short.mp4",
      "timestamp": "2026-09-05T12:15:00Z"
    }
  ],
  "failed": [
    {
      "topic_id": "byzantine-cheirosiphona",
      "stage": "image_generation",
      "error": "HTTP 429: Rate limit exceeded after 4 retries",
      "timestamp": "2026-09-05T12:25:00Z"
    }
  ],
  "in_progress": null,
  "pending": [
    "battle-of-pelusium-cat-shields",
    "flaming-war-pigs-megara"
  ]
}
```

### 6.3 Orchestrator Architecture (`.agent/skills/remotion-video-compiler/scripts/run_batch.py`)
```
+-------------------------------------------------------------+
|                      Batch Orchestrator                     |
|            (Reads state/batch_queue.json & progress)        |
+-------------------------------------------------------------+
                              |
              +---------------+---------------+
              |                               |
       [Skip Completed]            [Execute Next Topic]
                                              |
                   +--------------------------v--------------------------+
                   | Topic Isolation Sub-Pipeline                        |
                   | 1. state/topic.json generation                      |
                   | 2. video-scriptor (with beat-type pacing)           |
                   | 3. tts-audio-generator (synchronizes durations)     |
                   | 4. image-generator (consistent topic seed)          |
                   | 5. remotion-video-compiler (normalized zoompan)     |
                   | 6. deep_qa_inspector (5-vector audit)               |
                   +-----------------------------------------------------+
                                              |
                          +-------------------+-------------------+
                          |                                       |
                   [QA Passed]                             [Exception/QA Fail]
                          |                                       |
              Mark "SUCCESS" in Progress              Mark "FAILED" in Progress
              Copy to out/releases_v4/                Quarantine logs & continue
                          |                                       |
                          +-------------------+-------------------+
                                              |
                                      [Next Topic in Queue]
                                              |
                                  [Generate BATCH_REPORT.md]
```

---

## 7. Implementation Roadmap & Role Handoff

1. **ROLE 1 (ARCHITECT)**: Completed with this specification in `PLAN.md`.
2. **ROLE 2 (IMPLEMENTER - video-scriptor)**:
   - Add `beat_type` to schema and Gemini prompt.
   - Update `validate_storyboard_data` to check per-beat-type duration ranges and per-scene word counts.
   - Tighten `banned_proper_noun_was` regex.
3. **ROLE 3 (IMPLEMENTER - render_short.py & audio verification & batch runner)**:
   - Normalize zoompan velocities by `scene_frames`.
   - Add `-stream_loop -1` to BGM input.
   - Build `run_batch.py` with resumability, isolation, and markdown summary generation.
4. **ROLE 4 (IMPLEMENTER - image-generator)**:
   - Check seed derivation: verified already hashed from `topic_id`. Skip code changes; confirm in report.
5. **ROLE 5 (QA/TESTER)**:
   - Execute pipeline against 2 brand new topics from catalog (e.g. `byzantine-cheirosiphona`, `battle-of-pelusium-cat-shields`).
   - Measure real duration variance (min/max/stddev) and check frame perceptual hashes.
6. **ROLE 6 (AUDITOR)**:
   - Independent verification without self-trust: test pause ducking, test resume after simulated SIGINT, produce `AUDIT.md`.
